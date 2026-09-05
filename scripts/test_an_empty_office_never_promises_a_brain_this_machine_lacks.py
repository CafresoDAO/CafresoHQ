#!/usr/bin/env python3
"""The empty-desk alarm told a brand-new boss that setup was already done.

The ⚠ NOBODY HIRED chip fires on the one state every office starts in —
no coworkers, no brain — and it lives in the PINNED cluster of the topbar,
the one place a message can never scroll away from. Its tooltip was a
fixed string:

    Your desks are empty. Hire someone at the front desk — several
    candidates are already on this machine and need no setup at all.

Written on a box where four local brains were detected, and true only
there. Measured on a cold first run with nothing configured, the same
state scripts/test_a_coworker_is_never_hired_with_no_brain_at_all.py
measures: `candidateBrain([])` is null, every card on the shelf the office
opens BY ITSELF reads "no brain yet — add one in Settings → Connections",
and a hire off that screen lands `{"name":"Vera","model":""}` on the
roster. Both halves of the sentence were false at once — nothing was on
this machine, and setup was the entire remaining job — and it was the
loudest, reddest, unscrollable thing on the screen saying it.

The office already knew the answer. The candidates deck runs the one deep
probe this product has (/agent/drivers?probe=1, plus its own
`candidateReady` rule) and kept the result to itself, so the topbar had
nothing to read and printed a developer's machine instead. The fix is a
mirror, not a second probe: hire.jsx publishes what it measured, and the
chip's sentence is chosen from it — `undefined` (nobody has looked) says
only what needs no probe, `[]` names the brain the boss still has to get,
and a real find still says so with the count that was measured.

Deleting the sentence was not on the table: an empty-desk chip that says
nothing about the route out is a worse chip than a wrong one, so every
branch here is also checked for a door.

Run: python3 scripts/test_an_empty_office_never_promises_a_brain_this_machine_lacks.py
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
APP = ROOT / 'app.jsx'
CAST = ROOT / 'app' / 'cast.jsx'
HIRE = ROOT / 'modals' / 'hire.jsx'
RUNTIME = ROOT / 'hq-runtime.jsx'
sys.path.insert(0, str(ROOT / 'scripts'))

FAILS = []

# The exact claim that was pinned to the topbar of every fresh install.
OLD_CLAIM = 'several candidates are already on this machine'


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Comments first — this fix's own comments quote the bad sentence."""
    src = re.sub(r'\{/\*.*?\*/\}', '', src, flags=re.S)
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift(src, start_marker, end_marker):
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


# ───────────────────────────────────────────── §1: the claim is not hardcoded
def the_topbar_does_not_hold_the_claim():
    app = strip_comments(APP.read_text(encoding='utf-8'))

    check('the pinned empty-desk alarm no longer carries a fixed claim about '
          'this machine',
          OLD_CLAIM not in app,
          'app.jsx still ships the sentence verbatim — it is false on every '
          'machine that is not the one it was written on')

    chip = re.search(r'agents\.length === 0 && \(.{0,400}?title=(\{[^\n]*|"[^"]*")',
                     app, re.S)
    check('…and its tooltip is computed rather than typed',
          chip is not None and 'emptyOfficeNote' in chip.group(1),
          'the chip must read the sentence off what was measured'
          if chip is None else chip.group(1).strip())

    check('the topbar reads the front desk\'s measurement instead of guessing',
          'frontDeskBrainsSync' in app and 'onFrontDeskBrainsChange' in app,
          'nothing in app.jsx subscribes to what the candidates deck found')

    hire = strip_comments(HIRE.read_text(encoding='utf-8'))
    check('the candidates deck publishes what its probe found',
          'noteFrontDeskBrains(readyIds)' in hire,
          'hire.jsx measures readyIds and keeps it private, which is how the '
          'topbar came to invent its own answer')
    check('…and never publishes while the probe is still running',
          re.search(r'if \(probing\) return;\s*\n\s*try \{ HQ\.noteFrontDeskBrains',
                    hire) is not None,
          '"still checking" reported as "found nothing" just moves the lie')

    rt = strip_comments(RUNTIME.read_text(encoding='utf-8'))
    check('the mirror is a mirror — it starts no probe of its own',
          'function noteFrontDeskBrains' in rt
          and 'fetch' not in lift(rt, 'let _frontDeskBrains',
                                  'function onFrontDeskBrainsChange'),
          'the deep check belongs to the deliberate moment that already runs it')
    check('never-measured is distinguishable from measured-empty',
          re.search(r'let _frontDeskBrains;', rt) is not None
          and 'function frontDeskBrainsSync() { return _frontDeskBrains; }' in rt,
          'without an "undefined" state the topbar cannot tell "nobody looked" '
          'from "nothing here"')


# ─────────────────────────────────────── §2: the three sentences, run for real
def the_sentence_follows_the_measurement():
    bare = strip_comments(CAST.read_text(encoding='utf-8'))
    check('the sentence lives in one pure helper',
          re.search(r'^function emptyOfficeNote\(found\)', bare, re.M) is not None,
          'read from a closure it is impure and cannot be driven here')

    if not shutil.which('node'):
        print('  SKIP (node) — the source checks above still ran')
        return

    fn = lift(bare, 'function emptyOfficeNote', 'function withHandoff')
    js = ('const SRC = ' + json.dumps(fn) + ';\n' + r'''
const emptyOfficeNote = new Function(SRC + ' return emptyOfficeNote;')();
console.log(JSON.stringify({
  // Nobody has looked yet — the state the topbar is in for the first
  // seconds of every session, before the candidates deck has probed.
  unknown: emptyOfficeNote(undefined),
  nulled:  emptyOfficeNote(null),
  // Looked, and this machine really has nothing. The measured first run.
  none:    emptyOfficeNote([]),
  // Looked, and found some. The machine the old sentence was written on.
  one:     emptyOfficeNote(['ollama']),
  four:    emptyOfficeNote(['lmstudio','ollama','claude-code','codex']),
  // A count is as good as a list; junk is "nobody looked", never a claim.
  counted: emptyOfficeNote(2),
  junk:    emptyOfficeNote('lots'),
}));
''')
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        check('the lifted helper runs', False, p.stderr.strip()[:500])
        return
    r = json.loads(p.stdout.strip().split('\n')[-1])
    for k in sorted(r):
        print(f'        {k:8} {r[k]!r}')

    door = lambda s: ('front desk' in s) or ('candidates' in s)  # noqa: E731

    check('every branch still says the desks are empty',
          all('desks are empty' in v for v in r.values()),
          'that is the fact the alarm exists to report')
    check('every branch still points at a way out',
          all(door(v) for v in r.values()),
          'a chip that only complains is worse than the wrong one it replaced')
    check('no branch is silent',
          all(len(v) > 40 for v in r.values()), {k: len(v) for k, v in r.items()})

    check('before anyone has looked, the chip claims nothing about the machine',
          'already set up on this machine' not in r['unknown']
          and 'found no brain' not in r['unknown'],
          r['unknown'])
    check('…and an absent measurement reads the same as an unknown one',
          r['nulled'] == r['unknown'], r['nulled'])
    check('…and junk is treated as "nobody looked", never as a count',
          r['junk'] == r['unknown'], r['junk'])

    check('on a machine with nothing on it, the chip says so',
          'found no brain' in r['none'], r['none'])
    check('…and names the second thing the boss still has to get',
          'Settings' in r['none']
          and ('LM Studio' in r['none'] or 'Ollama' in r['none']),
          r['none'])
    check('…and never claims setup is already done there',
          'need no' not in r['none'] and 'already set up' not in r['none'],
          r['none'])

    # The half that must KEEP working: the developer's machine the old
    # sentence was written for is still described, and correctly.
    check('on a machine where brains ARE found, the chip still says so',
          'already set up on this machine' in r['four'], r['four'])
    check('…with the count that was actually measured',
          '4 brains' in r['four'] and 'one brain' in r['one'],
          [r['four'], r['one']])
    check('…and a count is read the same as a list',
          '2 brains' in r['counted'], r['counted'])
    check('…and it never says "several" over a number it knows',
          'several' not in ' '.join(r.values()),
          'the old sentence hedged with a word that fitted any machine')


# ──────────────────────────────── §3: the real topbar, in a real first run
CHIP_JS = r"""(() => {
  const b = [...document.querySelectorAll('button.chip')]
    .find(x => /NOBODY HIRED/.test(x.textContent||''));
  return b ? { text: b.textContent, title: b.title } : null;
})()"""


def make_handler(drivers):
    """The repo, served as serve.py serves it, plus one answer the office
    really asks for: /agent/drivers. `drivers=None` leaves it 404 — the
    unreachable back office of a cold first run."""
    import ui_manifest
    T = __import__(
        'test_the_office_ticker_and_the_lobby_door_are_measured_on_a_real_phone')

    class H(T.Handler):
        def do_GET(self):
            if self.path.split('?')[0] == '/agent/drivers':
                if drivers is None:
                    self.send_error(503, 'no back office')
                    return
                body = json.dumps({'drivers': drivers}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return super().do_GET()
    return T, H


def measure(label, drivers, expect, forbid):
    T, H = make_handler(drivers)
    if not (ROOT / 'dist-ui' / 'manifest.json').exists():
        check('the HQ UI is built', False,
              'dist-ui/manifest.json is missing; run `npm run build` first')
        return
    chrome = T.find_chrome()
    if chrome is None:
        print('  SKIP — no headless browser on this machine, so the topbar '
              'itself was not measured. It installs nothing: set $CHROME_PATH '
              'to measure it.')
        return
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{srv.server_address[1]}/hq.html'
    profile = tempfile.mkdtemp(prefix='cafresohq-chip-')
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
            check(f'[{label}] the browser announced a DevTools endpoint',
                  False, str(chrome))
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
        # The alarm is the point: an office with nothing configured and
        # nobody hired must be showing it at all.
        T.wait_for(
            ws,
            "[...document.querySelectorAll('button.chip')]"
            ".some(x => /NOBODY HIRED/.test(x.textContent||''))",
            30, 'the ⚠ NOBODY HIRED alarm to appear on a first run')
        # Beat 2: the office opens the candidate book itself, which is what
        # runs the probe the chip now reads. Wait for it, then let the
        # measurement land.
        T.wait_for(ws, "!!document.querySelector('.hire-board')", 30,
                   'the candidate book to open by itself on a first run')
        time.sleep(1.2)
        chip = T.evaluate(ws, CHIP_JS)
        check(f'[{label}] the alarm is on the screen', chip is not None)
        if chip is None:
            return
        print(f"        {chip['title']!r}")
        check(f'[{label}] it never ships the old fixed claim',
              OLD_CLAIM not in chip['title'], chip['title'])
        check(f'[{label}] it says what is actually true here',
              expect in chip['title'],
              f'expected {expect!r} in {chip["title"]!r}')
        for bad in forbid:
            check(f'[{label}] it does not claim {bad!r}',
                  bad not in chip['title'], chip['title'])
        check(f'[{label}] and it still names the way out',
              'front desk' in chip['title'] or 'candidates' in chip['title'],
              chip['title'])
    finally:
        if ws:
            ws.close()
        proc.kill()
        proc.wait(timeout=10)
        srv.shutdown()
        shutil.rmtree(profile, ignore_errors=True)


READY_OLLAMA = [{
    'id': 'ollama', 'label': 'Ollama',
    'detect': {'installed': True, 'version': 'reachable'},
}]


def main():
    print('an empty office never promises a brain this machine lacks')
    the_topbar_does_not_hold_the_claim()
    print()
    the_sentence_follows_the_measurement()
    print()
    print('  a cold first run, in a real browser, with no back office:')
    try:
        measure('nothing found', None, 'found no brain on this machine',
                ['already set up on this machine'])
    except Exception as exc:  # noqa: BLE001
        check('the first run rendered so it could be measured', False,
              f'{type(exc).__name__}: {exc}')
    print()
    print('  the same office on a machine that DOES have a brain:')
    try:
        measure('one brain found', READY_OLLAMA,
                'one brain is already set up on this machine',
                ['found no brain'])
    except Exception as exc:  # noqa: BLE001
        check('the found-brain run rendered so it could be measured', False,
              f'{type(exc).__name__}: {exc}')

    print()
    if FAILS:
        print(f'FAIL — {len(FAILS)} check(s): ' + '; '.join(FAILS[:6]))
        return 1
    print('PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
