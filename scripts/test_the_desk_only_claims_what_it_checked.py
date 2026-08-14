#!/usr/bin/env python3
"""Two claims the office made that nothing had checked.

**Hermes.** `HermesDriver.detect()` has always measured the gateway —
`version = 'gateway up' if gateway_running() else ''`, a loopback connect.
Nothing read it. The front desk gated Hermes on the binary existing and
printed a fixed line:

    Hermes                                  [FOUND]
    Already set up in your container — ready to work.

Measured on this machine while that card was on screen: the gateway was
down (`version: ''`), and there is no container anywhere in the detection
path — Hermes is a binary in ~/.local/bin and a config in ~/.hermes. Two
assertions, neither checked, one of them false at the moment it rendered.

Its siblings are not treated this way: ollama and lmstudio are gated on
exactly this kind of liveness probe. §3.1 says no runtime gets special
treatment and names Hermes as the original mistake — an earlier pass
corrected that card's *register* and left its *exemption* in place. Being
excused from the liveness check is special treatment.

**LM Studio.** Settings said "not answering — start it and reopen this"
whenever `det.installed`. For the local-daemon family `installed` is
`bool(base_url)` and the base URL has a default, so it is true on every
machine that has ever run this app. Measured here: no LM Studio.app, no
`lms` on PATH, and the office instructing me to start it. The other branch
of that ternary could never run.

Nothing in the detection path can tell "installed and stopped" from "never
installed". The fix is not a better guess — it is a sentence that does not
need one.

Run: python3 scripts/test_the_desk_only_claims_what_it_checked.py
"""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HIRE = ROOT / 'modals' / 'hire.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def run_js(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def lift_const(src, name):
    m = re.search(r'(?m)^\s*const\s+' + re.escape(name) + r'\s*=', src)
    if not m:
        return ''
    i, d, k = m.start(), 0, m.end()
    while k < len(src):
        c = src[k]
        if c in '([{':
            d += 1
        elif c in ')]}':
            d -= 1
        elif c == ';' and d == 0:
            break
        k += 1
    return src[i:k + 1].strip()


def brace_match(src, j):
    d, k = 0, j
    while k < len(src):
        if src[k] == '{':
            d += 1
        elif src[k] == '}':
            d -= 1
            if d == 0:
                return src[j:k + 1]
        k += 1
    return ''


def lift_braced(src, marker):
    """The `{ … }` JSX expression that starts at `marker`, brace-matched.
    Returns '' when the marker is gone so a deletion is a named failure."""
    i = src.find(marker)
    return brace_match(src, i) if i >= 0 else ''


def child_expr(src, class_name):
    """The `{ … }` child of the element carrying `className="<class_name>"`.

    Anchored on the ELEMENT, not on how its expression happens to open. The
    first version keyed the badge off `{c.probeError ? (c.service` — which
    is the very thing an arm reverting the badge deletes, so that arm made
    the lift return '' and skipped the check instead of failing it. A test
    whose anchor is the fix cannot see the fix removed.

    Skips the rest of the opening tag brace-aware, so an attribute with its
    own expression (`title={…}`) is not mistaken for the child."""
    i = src.find(f'className="{class_name}"')
    if i < 0:
        return ''
    d, k = 0, i
    while k < len(src):
        c = src[k]
        if c == '{':
            d += 1
        elif c == '}':
            d -= 1
        elif c == '>' and d == 0:
            break
        k += 1
    j = src.find('{', k)
    return brace_match(src, j) if j >= 0 else ''


def main():
    print('the front desk may only claim what detection established')

    # ── 1. the gateway probe reaches the surfaces ───────────────────────
    # As a package member — hermes.py uses relative imports.
    sys.path.insert(0, str(ROOT))
    try:
        from drivers import hermes
    except Exception as e:                                  # pragma: no cover
        print(f'  SKIP  drivers/hermes.py will not import — {e}')
        hermes = None

    if hermes:
        drv = hermes.HermesDriver()
        real = hermes.gateway_running
        try:
            hermes.gateway_running = lambda: False
            down = drv.detect(probe_version=True)
            hermes.gateway_running = lambda: True
            up = drv.detect(probe_version=True)
        finally:
            hermes.gateway_running = real

        check('a stopped gateway is reported, not just measured',
              down.get('probeError'),
              'detect() has always run the loopback connect; the result had '
              'nowhere to land, so every surface kept saying "ready to work"')
        check('...as a predicate the surfaces can conjugate',
              (down.get('probeError') or '').startswith('is not')
              and 'Hermes' not in (down.get('probeError') or ''),
              f"{down.get('probeError')!r} — two callers each supply their "
              'own subject')
        check('...with the address in the detail, not the sentence',
              ':' in (down.get('probeDetail') or '')
              and ':' not in (down.get('probeError') or ''),
              f"{down.get('probeDetail')!r} / {down.get('probeError')!r} — §6")
        check('a running gateway reports no problem',
              up.get('probeError') == '' and up.get('version') == 'gateway up',
              up)
        check('...and the down case still reports no version',
              down.get('version') == '', down.get('version'))

    if not shutil.which('node'):
        print('  SKIP  node not on PATH — UI checks skipped')
        return 1 if FAILS else 0

    hire = HIRE.read_text(encoding='utf-8')
    settings = SETTINGS.read_text(encoding='utf-8')

    # ── 2. the desk's fixed copy asserts nothing it cannot see ──────────
    desk = lift_const(hire, 'FRONT_DESK')
    check('the front desk still has its card copy', bool(desk), 'modals/hire.jsx')
    if desk:
        cards = run_js(desk + '\nconsole.log(JSON.stringify(FRONT_DESK));')
        for cid, c in cards.items():
            found = c.get('found', '')
            check(f'{cid}: the found line claims nothing about a container',
                  'container' not in found.lower(),
                  f'{found!r} — nothing in the detection path looks for one, '
                  'and on this machine there is not one')
            check(f'{cid}: ...and does not promise readiness on its own',
                  'ready to work' not in found.lower(),
                  f'{found!r} — readiness is a live fact; a constant cannot '
                  'carry it, and this one outlived a gateway that was down')

        services = {k for k, v in cards.items() if v.get('service')}
        check('the runtimes that must be RUNNING are marked as such',
              services == {'hermes', 'lmstudio', 'ollama'},
              f'{sorted(services)} — this picks the remedy sentence; get it '
              'wrong and the office tells someone to reinstall a service '
              'they only had to start')

    # ── 3. the card carries the state through ───────────────────────────
    card = lift_braced(hire, '{ ...def, driverId: d.id,')
    check('the front desk still builds a card object', bool(card), 'modals/hire.jsx')
    if card:
        SCOPE = ("const def = { id:'a_cli_hermes', name:'Hermes', service:true,"
                 " cloud:false, found:'x' };\nconst d = { id:'hermes' };\n"
                 "const localDaemon = false;\n"
                 "const det = { installed:true, authenticated:true,"
                 " probeError:'is not running', probeDetail:'nothing is"
                 " listening on 127.0.0.1:8642' };\n")
        obj = run_js(SCOPE + f'console.log(JSON.stringify({card}));')
        check('a stopped service is not diagnosed as needing a sign-in',
              obj.get('needsLogin') is False, obj)
        check('...and the card knows it is a service',
              obj.get('service') is True and obj.get('probeError'), obj)

    # ── 4. the remedy fits the problem ──────────────────────────────────
    note = child_expr(hire, 'frontdesk-note')
    check('the note still branches on the probe', bool(note), 'modals/hire.jsx')
    if note:
        expr = note[1:-1]
        svc = run_js("const c = { name:'Hermes', service:true, found:'x',"
                     " probeError:'is not running', needsLogin:false };"
                     f'console.log(JSON.stringify({expr}));')
        cli = run_js("const c = { name:'Codex', service:false, found:'x',"
                     " probeError:'will not start', needsLogin:false };"
                     f'console.log(JSON.stringify({expr}));')
        check('a stopped service is told to start, not to reinstall',
              'reinstall' not in svc and 'repair' not in svc
              and 'Starting it' in svc,
              f'{svc!r} — "it needs repairing or reinstalling first" is the '
              'CLI remedy; on a service that is the same wrong diagnosis in '
              'a different costume')
        check('...and a broken program is still told the truth about itself',
              'reinstalling' in cli and 'Starting it' not in cli, cli)
        check('both name what was observed before any remedy',
              svc.startswith('Hermes is on this machine, but it is not running')
              and cli.startswith('Codex is on this machine, but it will not start'),
              (svc[:60], cli[:60]))

        ok = run_js("const c = { name:'Llama', service:true, probeError:'',"
                    " found:'Already running on this machine.',"
                    ' needsLogin:false };'
                    f'console.log(JSON.stringify({expr}));')
        check('a runtime that IS ready still reads as before',
              ok == 'Already running on this machine.', ok)

    badge = child_expr(hire, 'post-tag')
    check('the card still has a badge', bool(badge), 'modals/hire.jsx')
    if badge:
        def tag(c):
            return run_js(f'const c = {c};'
                          f'console.log(JSON.stringify({badge[1:-1]}));')
        check('the badge distinguishes stopped from broken',
              tag("{service:true, probeError:'is not running'}") == 'NOT RUNNING'
              and tag("{service:false, probeError:'will not start'}") == "WON'T START",
              'one of these is a five-second fix and one is not; a shared '
              'badge makes the boss investigate the wrong one')
        check('...and a ready runtime is still just FOUND',
              tag("{service:true, probeError:''}") == 'FOUND', badge)

    # ── 5. Settings stops assuming the software is installed ────────────
    lifted = '\n'.join(lift_const(settings, n)
                       for n in ('broken', 'live', 'offText'))
    check('Settings still computes a per-runtime state', bool(lifted.strip()),
          'modals/settings.jsx')
    if lifted.strip():
        S = ("const id='lmstudio'; const isDaemon=true; const det="
             "{installed:true,authenticated:true,version:'',probeError:'',"
             "detail:'http://localhost:1234/v1'};\n")
        got = run_js(S + lifted + 'console.log(JSON.stringify({live,offText}));')
        check('a daemon that did not answer is not called live',
              got['live'] is False, got)
        check('...and the office does not order a start it cannot justify',
              'start it and reopen this' not in got['offText'],
              f"{got['offText']!r} — `installed` is bool(base_url) with a "
              'default, so this fired on a machine with no LM Studio at all')
        check('...it leaves room for never-installed',
              'if you have not yet' in got['offText']
              or 'install' in got['offText'].lower(),
              f"{got['offText']!r} — detection cannot tell stopped from "
              'absent, so the sentence must not pick one')

    # The driver-row block: from the list of runtimes it maps over to the
    # start of the next panel. Bounded by what the code IS rather than by a
    # magic character count or the spelling of the expression under test —
    # the first version anchored on the exact ternary, an unrelated edit to
    # that same ternary moved it, `str.find` returned -1, and the slice
    # quietly became the last character of the file.
    _i = settings.find("['claude-code'")
    _e = settings.find('cb-panel', _i) if _i >= 0 else -1
    sub = settings[_i:_e] if _i >= 0 and _e > _i else ''
    check('the Settings driver rows are still there', bool(sub),
          'modals/settings.jsx')
    check('a local daemon is not described as signed in',
          "isDaemon ? 'answering on this machine'" in sub,
          'its `authenticated` is hardcoded true because there is no account '
          'to sign in to — "signed in" names a step that does not exist')
    check('...and its dot says running, not ready-to-serve-an-account',
          "isDaemon ? '● running'" in sub, sub[:200])

    print()
    if FAILS:
        print(f'unchecked-claims: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('unchecked-claims: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
