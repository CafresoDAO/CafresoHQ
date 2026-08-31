#!/usr/bin/env python3
"""The onboarding step says "Say hi to your CEO" — then made you find
the input yourself.

Getting Started's "Open chat" CTA navigated to the chat view and left
focus on <body> (verified live: activeElement === BODY after the click).
The app already has one idiom for "put the boss in the composer": the
global `/` shortcut and the failed-message RETRY both focus
`.composer textarea`. A CTA whose own copy is an instruction to type
should land the same way.

Now onChat navigates AND focuses the composer (deferred a beat, since
the chat view may still be mounting). Verified live after: activeElement
is the composer textarea.

Run: python3 scripts/test_say_hi_lands_ready_to_type.py
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
    print('"say hi" lands ready to type')
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')

    m = re.search(r'onChat=\{[^\n]*\}', app)
    check('the GettingStarted onChat prop exists', m is not None)
    site = m.group(0) if m else ''
    check('it still navigates via navTo (not the windowed-mode no-op '
          'setActiveView)', "navTo('chat')" in site, site)
    check('it focuses the composer',
          ".querySelector('.composer textarea')" in site and '.focus()' in site,
          site)
    check('...with the SAME selector the / shortcut uses (one idiom, '
          'not two drifting ones)',
          site.count("'.composer textarea'") == 1
          and re.search(r"e\.key === '/'[\s\S]{0,120}\.composer textarea", app) is not None)
    check('the focus is deferred for the view mount', 'setTimeout' in site, site)

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
