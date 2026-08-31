#!/usr/bin/env python3
"""Every boot of the office logged the same four 404s: /favicon.ico.

hq.html declares its PNG icons properly, but browsers request
/favicon.ico unconditionally regardless of what <link rel=icon> says —
so with no route for it, every page load produced devtools console
errors and server log noise (measured: 4 x "Failed to load resource:
404" on a single boot, and a /favicon.ico 404 pair per load in the
serve.py log). Fix: serve.py answers /favicon.ico with the same
assets/favicon-32.png the page already declares (verified live after
restart: 200, image/png, 1082 bytes).

Run: python3 scripts/test_the_tab_icon_answers_the_door.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the tab icon answers the door')
    serve = (ROOT / 'serve.py').read_text(encoding='utf-8')
    hq = (ROOT / 'hq.html').read_text(encoding='utf-8')

    check('serve.py routes /favicon.ico',
          "_p0 == '/favicon.ico'" in serve)
    check('...to the same PNG the page declares',
          re.search(r"'/favicon\.ico':[\s\S]{0,400}favicon-32\.png", serve),
          '— the route and the <link rel=icon> should agree on the artwork')
    check('the icon file exists', (ROOT / 'assets' / 'favicon-32.png').is_file())
    check('hq.html still declares its icons for browsers that DO read the '
          'link tags',
          'assets/favicon-32.png' in hq and 'assets/favicon-16.png' in hq)
    # The route must sit BEFORE the gated static fallthrough — it exists so
    # the request never reaches send_error(404) at all.
    check('the route answers before the static fallthrough',
          serve.index("_p0 == '/favicon.ico'") < serve.index('_static_path_allowed(_p0)'))

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
