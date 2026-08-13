#!/usr/bin/env python3
"""The CEO panel's "Sit 1:1" quietly downgraded to the plain chat panel.

Two places in the app carry the identical label "Sit down with CafresoHQ
for a one-to-one": the office floor's 1:1 sofa (`ui/office.jsx`, wired to
`setFocus(true)` in `app.jsx`) and the CEO panel's own "Sit 1:1" quick
action (`ui/panels.jsx`'s `CEOPanel`). Only the floor's version opened
`FocusMode` — the dedicated "1:1 WITH CAFRESOHQ · QUIET ROOM · NO
DISTRACTIONS" overlay. The CEO panel's `onSitWithCEO` was wired to
`() => { navTo('chat'); }`, which just opens the ordinary multi-thread
chat panel — same label, silently different (lesser) experience,
depending on which of the two identically-worded entry points a boss
used.

Found live: clicked the CEO panel's own "Sit 1:1" button and got the
regular Chat window, not the quiet room. Confirmed `CEOPanel` already
wraps every quick action in a `fire()` helper that calls `onClose()`
after the action fires regardless of what that action does, so fixing
`onSitWithCEO` to match the floor's `setFocus(true)` needed no other
change. Verified live after rebuilding: the CEO panel's "Sit 1:1" now
opens the same quiet room, with the same shared chat history, and
"LEAVE ROOM" returns cleanly to the normal view.

Run: python3 scripts/test_ceo_panel_sit_1on1.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('CEO panel "Sit 1:1" — must match the floor sofa, not downgrade to plain chat')
    if not APP.is_file():
        print('  FAIL  missing app.jsx')
        return 1
    src = APP.read_text(encoding='utf-8')

    floor_m = re.search(r'onSitWithCEO=\{\(\)\s*=>\s*setFocus\(true\)\}', src)
    check('the office floor sofa opens FocusMode (setFocus(true))',
          bool(floor_m),
          'the floor wiring itself changed — re-check both call sites, '
          'not just the CEOPanel one this test targets')

    ceo_panel_m = re.search(
        r'<CEOPanel\b[\s\S]{0,800}?/>', src)
    check('the <CEOPanel> element is found', bool(ceo_panel_m))
    if ceo_panel_m:
        block = ceo_panel_m.group(0)
        check("CEOPanel's onSitWithCEO opens FocusMode, not navTo('chat')",
              bool(re.search(r"onSitWithCEO=\{\(\)\s*=>\s*setFocus\(true\)\}", block)),
              "found something other than setFocus(true) — this is exactly "
              "the bug: the CEO panel's own \"Sit 1:1\" button carries the "
              "same label as the floor sofa but silently opened plain Chat "
              "instead of the quiet-room FocusMode overlay")
        check("CEOPanel's onSitWithCEO does NOT fall back to navTo('chat')",
              'navTo(\'chat\')' not in block and "navTo(\"chat\")" not in block)

    print()
    if FAILS:
        print(f'CEO panel Sit 1:1: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('CEO panel Sit 1:1: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
