#!/usr/bin/env python3
"""The first hire of a brand-new office was a coworker with no brain.

Measured 2026-09-05 on a cold first run — the real `hq.html`, the real
`dist-ui/bundle`, headless Chrome, nothing configured anywhere, which is
exactly the state a beta tester opens the product in. The office opens
the candidate book by itself (app.jsx, "beat 2" of the CEO's welcome), so
this is not a corner the boss went looking for; it is the screen the
product puts in front of them.

Every card on that shelf read

    no brain yet — add one in Settings → Connections

because `candidateBrain([])` is null and `candidates` rewrites each
template's `model` to `''` (modals/hire.jsx). The boss clicked Vera. The
form opened with:

    NAME    Vera
    BRAIN   — pick a model —          (and no note of any kind)
    footer  A new desk will be assigned on spawn.
    HIRE ✓  live, enabled, no tooltip

They pressed it. `cafresohq_hq_v1:agents` then held

    [{"name": "Vera", "model": "", "role": "Virtual Assistant"}]

A coworker at a desk, on the roster, in the ticker, who can never answer
anything — hired through the front door with the office saying nothing at
all. Onboarding step 2 ticks. That is a "success" leaving nothing usable
behind, and it is the one hire a first run is most likely to make.

The office already knew. TWO surfaces on that exact screen had the answer
and neither was consulted by this door:

  · ⚡ SEED SWARM, one tile away, refuses the identical hire out loud —
    "There is no brain on this machine yet, so these 7 would sit at their
    desks unable to work."
  · The BRAIN row's own warning — "⚠ this brain isn't signed in yet" —
    opens `if (!provider) return null;`. It was written for a brain that
    exists and is not signed in, and `parseModelId('')` has no provider,
    so on the ONE state a fresh install actually produces it returned
    nothing. The check that was supposed to catch this was silent
    precisely because the failure was total rather than partial.

So the fix is `hireNeedsNote`'s job, not a fourth copy of the idea: one
sentence carrying the reason AND the route, read by both HIRE ✓'s
`disabled` state and the footer hint the boss can see without hovering
(#324's shape, #299's before that). The brain is a third argument for the
same reason the roster became the second one — a prop read from a closure
would be impure and unliftable, and this suite drives the helper verbatim
under node.

Run: python3 scripts/test_a_coworker_is_never_hired_with_no_brain_at_all.py
"""
from __future__ import annotations

import http.server
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIRE = ROOT / 'modals' / 'hire.jsx'
sys.path.insert(0, str(ROOT / 'scripts'))

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Comments first — this fix's own comments quote the bad shape."""
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift(src, start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


# ─────────────────────────────────────────────────────── §1 + §2: the helper
def source_and_helper():
    src = HIRE.read_text(encoding='utf-8')
    bare = strip_comments(src)

    check('the door that answers "why can HIRE ✓ not go through" knows '
          'about the brain',
          re.search(r'^function hireNeedsNote\(name, currentAgents, model\)',
                    bare, re.M) is not None,
          'hireNeedsNote must take the brain as a declared parameter — read '
          'from a closure it is impure and cannot be driven here')

    check('every reader of the note hands it the brain',
          re.search(r'hireNeedsNote\((?!name, currentAgents, model\))', bare)
          is None,
          'a call site that drops an argument is a door that quietly stops '
          'asking the question')

    if not shutil.which('node'):
        print('  SKIP (node) — the source checks above still ran')
        return

    fn = lift(bare, 'function hireNeedsNote', 'const FRONT_DESK')
    js = ('const SRC = ' + json.dumps(fn) + ';\n' + r'''
const hireNeedsNote = new Function(SRC + ' return hireNeedsNote;')();
const OK = 'ollama:llama3.1:latest';
console.log(JSON.stringify({
  // The measured first run: a candidate prefilled onto a machine with no
  // brain, so `model` is the empty string the shelf rewrote it to.
  brainless: hireNeedsNote('Vera', [], ''),
  // A brain that IS set clears the note and lets the button live.
  withBrain: hireNeedsNote('Vera', [], OK),
  // A paid brain nobody has signed into is a DIFFERENT complaint — the
  // BRAIN row's own warning owns that one, and this door must not
  // double up on it or the boss reads two blocks for one field.
  unsigned:  hireNeedsNote('Vera', [], 'anthropic:claude-haiku-4-5-20251001'),
  // Whitespace is not a brain, and an unset state must not throw inside
  // the render of the whole dialog.
  spaces:    hireNeedsNote('Vera', [], '   '),
  missing:   hireNeedsNote('Vera', [], undefined),
  nulled:    hireNeedsNote('Vera', [], null),
  // The name questions still come first: a blank NAME outranks a blank
  // BRAIN, because that is the box the cursor is already in.
  noName:    hireNeedsNote('', [], ''),
  taken:     hireNeedsNote('Vera', [{name: 'Vera', role: 'Analyst'}], OK),
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted helper runs', False, p.stderr.strip()[:500])
        return
    r = json.loads(p.stdout.strip().split('\n')[-1])

    note = r['brainless']
    check('a coworker with no brain has a reason to be refused',
          bool(note),
          'an empty note means HIRE ✓ is live and silent over a hire that '
          'lands on the roster as {"name":"Vera","model":""}')
    check('…and it is a sentence, not shorthand',
          len(note) > 30 and note.rstrip().endswith('.'), note)
    check('…that names the field by the label printed above the box',
          'BRAIN' in note, note)
    check('…and says what the boss can do about it',
          'Settings' in note or 'pick' in note.lower(), note)
    check('an absent or blank brain reads the same as no brain',
          r['spaces'] == note and r['missing'] == note and r['nulled'] == note,
          [r['spaces'], r['missing'], r['nulled']])
    check('a brain that is set lets the button live',
          r['withBrain'] == '', r['withBrain'])
    check('a brain that merely needs signing in is left to the BRAIN row',
          r['unsigned'] == '',
          'the row already says "⚠ this brain isn\'t signed in yet"; two '
          'blocks for one field is worse than one: ' + str(r['unsigned']))
    check('a blank NAME still outranks a blank BRAIN',
          'NAME' in r['noName'], r['noName'])
    check('a name somebody already answers to still outranks it',
          'already works here' in r['taken'], r['taken'])


# ──────────────────────────────────────── §3: the screen a beta tester sees
# Boots the REAL app the way serve.py assembles it, in headless Chrome,
# with nothing configured — so `/agent/drivers` is unreachable, no brain is
# found, and the candidate book is exactly the one measured above. Drives
# it the way a person does: wait for the book to open itself, click the
# first candidate, read the form. No new dependency; see the note in
# scripts/test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone.py
BOARD_JS = r"""(() => {
  const c = [...document.querySelectorAll('.hire-board .post-card')]
    .find(x => /CANDIDATE/.test((x.querySelector('.post-tag')||{}).textContent||''));
  if (!c) return null;
  const out = {
    name: (c.querySelector('.post-name')||{}).textContent || '',
    vendor: (c.querySelector('.post-vendor')||{}).textContent || '',
  };
  c.click();
  return out;
})()"""

FORM_JS = r"""(() => {
  const rows = [...document.querySelectorAll('.form-grid .form-row')];
  const lbl = r => ((r.querySelector('label')||{}).textContent||'');
  const brainRow = rows.find(r => /BRAIN/.test(lbl(r)));
  const nameRow  = rows.find(r => /NAME/.test(lbl(r)));
  const sel = brainRow && brainRow.querySelector('select');
  const shell = document.querySelector('[data-modal-shell]') || document;
  const hire = [...shell.querySelectorAll('button')]
    .find(b => /HIRE ✓/.test(b.textContent||''));
  const footHint = [...shell.querySelectorAll('.hint')]
    .find(h => h.parentElement && h.parentElement.querySelector('button'));
  return {
    nameValue: nameRow ? (nameRow.querySelector('input')||{}).value : null,
    brainValue: sel ? sel.value : null,
    brainShows: sel && sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : null,
    hireFound: !!hire,
    hireDisabled: hire ? !!hire.disabled : null,
    hireTitle: hire ? (hire.title || '') : '',
    footHint: footHint ? footHint.textContent : '',
  };
})()"""


def on_a_real_first_run():
    import ui_manifest  # noqa: F401  (imported for its side-effect check)
    T = __import__(
        'test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone')

    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        check('the HQ UI is built', False,
              'dist-ui/manifest.json is missing; run `npm run build` first')
        return
    chrome = T.find_chrome()
    if chrome is None:
        print('  SKIP — no headless browser on this machine, so the screen '
              'itself was not measured. It installs nothing: set $CHROME_PATH '
              'to measure it.')
        return
    print(f'  using  {chrome}')

    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), T.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_address[1]}/hq.html'
    profile = tempfile.mkdtemp(prefix='cafresohq-hire-')
    proc = subprocess.Popen(
        [str(chrome), '--headless=new', '--remote-debugging-port=0',
         f'--user-data-dir={profile}', '--no-sandbox', '--disable-gpu',
         '--hide-scrollbars', '--mute-audio', '--no-first-run',
         '--no-default-browser-check', '--disable-extensions',
         '--disable-background-timer-throttling',
         '--disable-renderer-backgrounding', 'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    ws = None
    try:
        endpoint = None
        deadline = time.time() + 30
        while time.time() < deadline:
            line = proc.stderr.readline().decode('utf-8', 'replace')
            if not line:
                break
            hit = re.search(r'ws://\S+', line)
            if hit:
                endpoint = hit.group(0)
                break
        if not endpoint:
            check('the browser announced a DevTools endpoint', False, str(chrome))
            return
        host = re.match(r'ws://([^/]+)/', endpoint).group(1)
        with urllib.request.urlopen(f'http://{host}/json/list', timeout=15) as fh:
            targets = json.load(fh)
        page = next(t for t in targets if t['type'] == 'page')
        ws = T.WS(page['webSocketDebuggerUrl'])
        ws.call('Page.enable')
        ws.call('Runtime.enable')
        ws.call('Emulation.setDeviceMetricsOverride', {
            'width': 1280, 'height': 900, 'deviceScaleFactor': 1,
            'mobile': False})
        ws.call('Page.navigate', {'url': url})
        T.wait_for(ws, "!document.getElementById('cafreso-boot')", 45,
                   'the app to mount and the boot splash to clear')
        T.wait_for(ws, "!!document.querySelector('.hire-board')", 30,
                   'the candidate book to open by itself on a first run')

        card = T.evaluate(ws, BOARD_JS)
        check('the first run puts a candidate in front of the boss',
              card is not None,
              'no CANDIDATE card on the board the office just opened')
        if card is None:
            return
        check('…on a machine with no brain, the card says so',
              'no brain yet' in (card['vendor'] or ''),
              f"{card['name']}'s brain line reads {card['vendor']!r} — this "
              'suite needs the brainless shelf to measure the door')
        print(f"        clicked {card['name']} · {card['vendor']}")

        T.wait_for(ws, "!!document.querySelector('.form-grid')", 15,
                   'the hire form to open on the candidate')
        # One frame for the note to render beside the picker.
        time.sleep(0.6)
        f = T.evaluate(ws, FORM_JS)
        print('        ' + json.dumps(f))

        check('the form really did open on the brainless candidate',
              f['nameValue'] == card['name'] and not (f['brainValue'] or '').strip(),
              f"NAME {f['nameValue']!r} · BRAIN {f['brainValue']!r}")
        check('HIRE ✓ is on the screen to be pressed', f['hireFound'])
        check('HIRE ✓ will not hire a coworker who has no brain',
              f['hireDisabled'] is True,
              'the button is live — pressing it puts {"name":"'
              + str(f['nameValue']) + '","model":""} on the roster and ticks '
              'onboarding step 2')
        check('…and the reason is VISIBLE, not hover-only',
              'BRAIN' in (f['footHint'] or ''),
              f"the footer reads {f['footHint']!r} — a tooltip alone is "
              'unreachable on a touch screen, and this footer was cheerfully '
              'saying "A new desk will be assigned on spawn."')
        check('…and it is carried by the tooltip too',
              'BRAIN' in (f['hireTitle'] or ''), repr(f['hireTitle']))
    finally:
        if ws:
            ws.close()
        proc.kill()
        proc.wait(timeout=10)
        srv.shutdown()
        shutil.rmtree(profile, ignore_errors=True)


def main():
    print('a coworker is never hired with no brain at all')
    source_and_helper()
    print()
    print('  on a real first run, in a real browser:')
    try:
        on_a_real_first_run()
    except Exception as exc:  # noqa: BLE001
        check('the first run rendered so it could be measured', False,
              f'{type(exc).__name__}: {exc}')

    print()
    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS[:6]))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
