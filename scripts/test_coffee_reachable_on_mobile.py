#!/usr/bin/env python3
""""Coffee" is a floor-only action, and the ledger has to keep saying so.

Measured 2026-08-12 at 375×812: of the 15 controls inside `.px-scene`, 14
are under the 44px touch minimum (the coffee mugs are 12×12). That alone is
a documented-open P1 — `docs/strategy/06-app-update-todo.md` Track 6. What
lifts it above cosmetic is reachability: sending a coworker for coffee STOPS
whatever they are running and clears their desk, and on a phone the only way
to trigger it is that 12×12 mug. The mobile Team roster — which is 19/21
controls over 44px, so touch sizing was clearly considered — has no coffee
control at all.

This file does NOT assert "the targets are too small". A test that pins a
bug in place is worse than no test. It asserts the two things that must stay
true together:

  1. The code fact the ledger entry rests on — `onCoffee` is wired on the
     office floor and nowhere in views/core.jsx (the Team roster).
  2. That OFFICE_AS_INTERFACE.md's "Known open" list still carries the entry
     describing it.

So it fires in BOTH directions. Give coffee a roster path and (1) breaks —
good news, and the ledger now overstates the gap, so it must be updated.
Delete the ledger entry while the gap remains and (2) breaks. Either way the
document and the code cannot drift apart silently, which is the failure this
ledger already got caught in once (see the Night Shift correction, same
section).

Run: python3 scripts/test_coffee_reachable_on_mobile.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICE = ROOT / 'ui' / 'office.jsx'
CORE = ROOT / 'views' / 'core.jsx'
DOC = ROOT / 'docs' / 'OFFICE_AS_INTERFACE.md'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('coffee on mobile — floor-only action, and the ledger says so')
    for p in (OFFICE, CORE, DOC):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    office = OFFICE.read_text(encoding='utf-8')
    core = CORE.read_text(encoding='utf-8')
    doc = DOC.read_text(encoding='utf-8')

    # ── (1) the code fact ──────────────────────────────────────────────────
    # Word-bounded, not `in`: a bare substring test passes against
    # `onCoffeeXX`, so it could not tell "the handler is wired" from "the
    # handler was renamed away". Caught by fire-testing this very check.
    has_coffee = lambda s: bool(re.search(r'\bonCoffee\b', s))

    check('the office floor still wires onCoffee',
          has_coffee(office),
          'ui/office.jsx: if the mug lost its handler, coffee is not '
          'reachable ANYWHERE and this is no longer a sizing question')

    roster_has_coffee = has_coffee(core)
    check('the mobile Team roster still has no coffee control',
          not roster_has_coffee,
          'views/core.jsx: a roster coffee control would be the fix for the '
          'ledger entry this test guards — GOOD NEWS, but the "Known open" '
          'bullet in OFFICE_AS_INTERFACE.md now overstates the gap and has '
          'to be corrected or removed. Do not just delete this check.')

    # ── (2) the ledger entry that describes it ─────────────────────────────
    check('the ledger carries the floor-not-touch-sized entry',
          '**The office floor is not touch-sized, and "coffee" has no other door.**' in doc,
          'docs/OFFICE_AS_INTERFACE.md: the gap is real and measured; the '
          '"Known open, honestly" list is where it belongs')
    check('...and cites the measurements rather than asserting vibes',
          all(s in doc for s in ('12×12', '11px', '15 controls')),
          'docs/OFFICE_AS_INTERFACE.md: this ledger is only worth anything '
          'if its claims carry the numbers behind them')
    check('...and records why a blanket hit-area expansion is unsafe',
          '.px-cab' in doc and '.px-couch' in doc,
          'docs/OFFICE_AS_INTERFACE.md: the 11px cabinet/sofa gap is the '
          'reason the obvious fix is wrong — losing that turns the entry '
          'into an invitation to break two working controls')

    print()
    if FAILS:
        print(f'coffee on mobile: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('coffee on mobile: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
