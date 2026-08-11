#!/usr/bin/env python3
"""Driver-contract conformance for the Gemini CLI driver — the fifth and
final bespoke serve.py integration style folded into drivers/ (DRIVER_CONTRACT
§5 step 2).

What is pinned and why:

1. Registration: DRIVERS carries a 'gemini' CLI driver distinct from the
   'gemini-api' HTTP driver. serve.py's /agents surface calls
   _drivers.get('gemini').resolve()/.detect_auth() — before this driver
   existed those calls had no target, so the id is load-bearing.
2. Fail-closed spawn: no binary → DriverError 503 (front desk shows the
   install card); no cwd → 503; empty prompt → 400. A driver must refuse
   loudly, never spawn a broken process.
3. Event stream: tokens are ANSI-stripped (gemini's stdout carries spinner
   escapes), a zero-output exit yields an ERROR event with a login hint
   (the silent-failure mode when the CLI is unauthenticated), a non-zero
   exit yields ERROR with stderr, and a clean run ends in exactly one DONE.
4. serve.py delegation: the old bespoke _gemini_resolve body is gone —
   serve.py must route through the driver so there is ONE detection
   authority (the "two sources, one rule" class caught 5x this session).

No network, no real gemini binary: a stub executable stands in.

Run: python3 scripts/test_drivers.py
"""
from __future__ import annotations

import os
import pathlib
import stat
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}' + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def _stub_bin(tmp: pathlib.Path, body: str) -> str:
    p = tmp / 'gemini'
    p.write_text('#!/bin/sh\n' + body, encoding='utf-8')
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def _run(drv, task):
    handle = drv.start_task(task)
    return list(drv.events(handle))


def main() -> int:
    from drivers import DRIVERS
    from drivers.base import DriverError
    from drivers.gemini_cli import GeminiCliDriver

    print('registration')
    check("DRIVERS has a 'gemini' cli driver", 'gemini' in DRIVERS
          and DRIVERS['gemini'].MANIFEST['kind'] == 'cli')
    check("distinct from the 'gemini-api' HTTP driver",
          'gemini-api' in DRIVERS
          and DRIVERS['gemini-api'] is not DRIVERS['gemini'])
    d = DRIVERS['gemini'].detect()
    check('detect() returns the contract shape',
          {'installed', 'authenticated', 'auth', 'version', 'detail'} <= set(d))

    print('fail-closed spawn')
    drv = GeminiCliDriver()
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        drv.binary_override = str(tmp / 'nope')   # not a file
        try:
            drv.start_task({'prompt': 'hi', 'cwd': td})
            check('missing binary raises', False)
        except DriverError as e:
            check('missing binary raises 503 with install hint',
                  e.status == 503 and 'install' in str(e))

        drv.binary_override = _stub_bin(tmp, 'echo hello')
        try:
            drv.start_task({'prompt': 'hi', 'cwd': ''})
            check('missing cwd raises', False)
        except DriverError as e:
            check('missing cwd raises 503', e.status == 503)
        try:
            drv.start_task({'prompt': '', 'messages': [], 'cwd': td})
            check('empty prompt raises', False)
        except DriverError as e:
            check('empty prompt raises 400', e.status == 400)

        print('event stream')
        # ANSI spinner escapes must never reach a chat bubble.
        drv.binary_override = _stub_bin(
            tmp, r'printf "\033[1;32mhello\033[0m world\n"')
        evs = _run(drv, {'prompt': 'hi', 'cwd': td})
        toks = ''.join(e.get('text', '') for e in evs if e.get('event') == 'token')
        check('tokens are ANSI-stripped', toks.strip() == 'hello world', repr(toks))
        check('clean run ends in exactly one DONE',
              [e['event'] for e in evs if e['event'] in ('done', 'error')] == ['done'])

        # Unauthenticated gemini exits 0 having printed nothing useful —
        # that must surface as an ERROR with a login hint, not a blank bubble.
        drv.binary_override = _stub_bin(tmp, 'true')
        evs = _run(drv, {'prompt': 'hi', 'cwd': td})
        errs = [e for e in evs if e.get('event') == 'error']
        check('silent zero-output exit becomes an error', len(errs) == 1)
        check('...and the error hints at login',
              errs and 'logged in' in errs[0].get('message', ''),
              repr(errs))

        drv.binary_override = _stub_bin(tmp, 'echo "boom" >&2; exit 3')
        evs = _run(drv, {'prompt': 'hi', 'cwd': td})
        errs = [e for e in evs if e.get('event') == 'error']
        check('non-zero exit carries stderr',
              len(errs) == 1 and 'boom' in errs[0].get('message', ''), repr(errs))

        # messages[] fallback (night_runner path passes messages, not prompt)
        drv.binary_override = _stub_bin(tmp, 'echo got-messages')
        evs = _run(drv, {'messages': [{'role': 'user', 'content': 'x'}], 'cwd': td})
        check('messages[] without prompt still runs',
              any(e.get('event') == 'done' for e in evs))

    print('serve.py delegation')
    serve_src = (ROOT / 'serve.py').read_text(encoding='utf-8')
    check('serve.py resolves gemini through the driver',
          "_drivers.get('gemini').resolve()" in serve_src)
    check('serve.py auth-detects gemini through the driver',
          "_drivers.get('gemini').detect_auth()" in serve_src)
    check('no bespoke gemini shutil.which left in serve.py',
          "which('gemini'" not in serve_src and 'which("gemini' not in serve_src,
          'detection must have ONE authority — the driver')

    print()
    if FAILS:
        print(f'drivers: {len(FAILS)} FAILURE(S)')
        return 1
    print('drivers: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
