#!/usr/bin/env python3
"""The Situation Wall's "N working" count undercounted active coworkers.

Reproduced by reading the source. A run that just finished sits at
`status: 'active', mood: 'done'` for the §4 8-second window while it
reports its result (app.jsx sets this at least three places: 2866, 4084,
4849). During that window the coworker's desk is lit and animated —
`anyLive`, the desk pose, the sub-agent pose, and the mini-avatar-strip
status dot in ui/office.jsx all treat `status === 'busy' || status ===
'active'` as the same "working" state, and so does the topbar's own
WORKING chip in app.jsx (line ~6343).

But the Situation Wall's `busyCount`, in ui/office.jsx, used to read:

    const busyCount = agents.filter(a => a.status === 'busy').length;

— 'active' excluded. So a coworker whose desk was visibly lit and
animated, and who the topbar chip counted as WORKING, was silently
dropped from the Situation Wall's own "N working" label for the same
instant of the same state: two counters in the same file/app disagreeing
about how many coworkers were working right now.

Run: python3 scripts/test_the_situation_wall_undercounted_who_was_working.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICE = (ROOT / 'ui/office.jsx').read_text(encoding='utf-8')
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('the Situation Wall undercounted who was working')

    m = re.search(r"const busyCount = agents\.filter\(a => ([^)]*)\)\.length;", OFFICE)
    check('found busyCount', m is not None)
    cond = m.group(1) if m else ''

    check("busyCount's filter checks status === 'busy'",
          "a.status === 'busy'" in cond)
    check("busyCount's filter ALSO checks status === 'active', matching every "
          "other 'is this coworker working' check in the same file",
          "a.status === 'active'" in cond)

    # Every other "is this coworker working" predicate in ui/office.jsx must
    # keep using the same busy-or-active pair, so this fix does not drift
    # from them again later.
    other_checks = re.findall(r"status === 'busy' \|\| a?\.?status === 'active'", OFFICE)
    check('at least 3 other status===busy||active checks remain in ui/office.jsx '
          '(anyLive, desk pose, mini-avatar dot, sub-agent pose)',
          len(other_checks) >= 3, len(other_checks))

    # The topbar's own WORKING chip (app.jsx) must still count the same way —
    # this fix's whole point is making busyCount agree with that chip.
    check("app.jsx's topbar WORKING chip counts busy-or-active (the number "
          "busyCount must now match)",
          re.search(r"agents\.filter\(a=>a\.status==='busy'\|\|a\.status==='active'\)\.length.*WORKING",
                     APP) is not None)

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
