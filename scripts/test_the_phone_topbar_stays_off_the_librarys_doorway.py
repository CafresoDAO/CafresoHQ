#!/usr/bin/env python3
"""Two mobile overlaps, one cause each: chrome positioned by assumption.

1. The topbar's ⌗ ROOMS menu pill. On ≤768px every other chip in the
   status row is `mobile-hidden`, but the ROOMS TopbarMenu never got the
   class — it overflowed the collapsed topbar and floated ON TOP of the
   view below it. Measured live at 375×812: the pill (y=45) sat across
   the Library's 📁 Files tab (y=52), eating its top-left corner and its
   taps. Every one of its six rooms (Memory shelf, Stand-up, Research,
   Meetings, Workflows, night toggle) is already in the MobileTabBar's
   Tools drawer with its badges, so on a phone the pill was a duplicate
   door parked on someone else's doorway. Fix: TopbarMenu takes a
   className, the ROOMS call site passes mobile-hidden.

2. The graph analytics panel. Its `top` was a hardcoded 50 — the height
   of the toolbar when it fits on ONE line. On a phone the toolbar wraps
   to three lines (~246px measured), and the panel painted straight
   through the wrapped controls; the earlier zIndex fix kept the buttons
   clickable but not readable. Fix: a ResizeObserver on the toolbar sets
   the panel's top to the toolbar's real bottom edge + 6, so the panel
   starts below the controls at every wrap count (measured after:
   toolbar bottom 256, panel top 262, toggle hit-testable).

Run: python3 scripts/test_the_phone_topbar_stays_off_the_librarys_doorway.py
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
    print("the phone topbar stays off the Library's doorway")
    app = (ROOT / 'app.jsx').read_text(encoding='utf-8')
    panels = (ROOT / 'ui' / 'panels.jsx').read_text(encoding='utf-8')
    graph = (ROOT / 'views' / 'graph.jsx').read_text(encoding='utf-8')
    office = (ROOT / 'ui' / 'office.jsx').read_text(encoding='utf-8')

    # ── 1. the ROOMS pill hides on mobile ───────────────────────────────
    check('TopbarMenu accepts a className',
          'function TopbarMenu({ label, title, items, className' in panels)
    check('...and actually applies it to its wrapper',
          re.search(r"'topbar-menu' \+ \(className", panels) is not None)
    rooms_site = re.search(r'<TopbarMenu[\s\S]{0,120}label="⌗ ROOMS"', app)
    check('the ROOMS call site exists', rooms_site is not None)
    check('the ROOMS pill is mobile-hidden',
          rooms_site is not None and 'className="mobile-hidden"' in rooms_site.group(0),
          '— without it the pill overflows the collapsed topbar and floats '
          'over the Files tab at phone widths')

    # ...which is only honest because the drawer really does carry every
    # room the pill offers. If a room leaves the drawer, this fails and the
    # pill (or a new door) must come back on mobile.
    for label in ('Memory', 'Stand-up', 'Research', 'Meeting', 'Workflow'):
        check("the Tools drawer still carries '%s'" % label,
              "label: '%s'" % label in office)
    check('the drawer still carries the night toggle',
          "night ? 'Day' : 'Night'" in office)

    # ── 2. the analytics panel starts below the toolbar's REAL bottom ───
    check("the panel's top is measured state, not a constant",
          "top: panelTop, right: 10" in graph,
          "— a hardcoded `top: 50` assumes a one-line toolbar; phones wrap "
          'it to three')
    check('no hardcoded top: 50 panel remains', 'top: 50,' not in graph)
    check('the toolbar carries the ref being measured',
          'ref: toolbarRef' in graph)
    check('a ResizeObserver tracks the toolbar through wraps and resizes',
          'new ResizeObserver(measure)' in graph
          and 'ro.observe(el)' in graph and 'ro.disconnect()' in graph)
    check('the measurement is bottom-edge + margin',
          'el.offsetTop + el.offsetHeight + 6' in graph)
    check('the default matches the one-line toolbar (desktop unchanged '
          'before first measure)',
          'setPanelTop] = useSV(50)' in graph)

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
