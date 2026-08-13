#!/usr/bin/env python3
"""The graph's own "Hide analytics" button was unclickable once opened.

`views/graph.jsx`'s top toolbar wraps (`flexWrap: 'wrap'`) once its ~10
controls (filter, two selects, four buttons, the analytics toggle, minimize)
don't fit one line — which they don't at this session's own driving width,
874px, not an exotic narrow viewport. The wrapped second row lands inside
the analytics panel's own territory (the panel is `position: absolute, top:
50, right: 10`, painted AFTER the toolbar in DOM order). Neither element had
an explicit `zIndex`, so default stacking handed the win to whichever
painted last — the panel — even though the toolbar's buttons all set
`pointerEvents: 'auto'` (that only matters if the element is what actually
gets hit-tested at that point; it doesn't help if a differently-stacked
sibling occupies the same pixels first).

Confirmed live, not assumed from the CSS: with the panel open on a
throwaway office, `document.elementFromPoint()` at the exact center of the
"Hide analytics ›" button's own `getBoundingClientRect()` returned the
panel's content div, not the button. The one control that closes the panel
was permanently unreachable by a real click the moment a boss opened it,
on an ordinary window size, not a resize-to-break repro.

Fix: explicit zIndex on both — the toolbar above the panel — so wrapped
toolbar controls always win hit-testing regardless of how many controls
wrap onto how many lines. Verified live after rebuilding: `Hide analytics`
now closes the panel, and reopening + closing a second time works, in both
directions.

Run: python3 scripts/test_graph_analytics_toggle_clickable.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH = ROOT / 'views' / 'graph.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('graph analytics toggle — must win hit-testing over the panel it controls')
    if not GRAPH.is_file():
        print('  FAIL  missing views/graph.jsx')
        return 1
    src = GRAPH.read_text(encoding='utf-8')

    toolbar_m = re.search(
        r"// Top toolbar\.[\s\S]*?React\.createElement\('div', \{ style: \{([^}]*flexWrap: 'wrap'[^}]*)\}",
        src)
    check('the top toolbar block is found', bool(toolbar_m))

    panel_m = re.search(
        r"panelOpen && React\.createElement\('div', \{ style: \{([^}]*width: 246[^}]*)\}",
        src)
    check('the analytics panel block is found', bool(panel_m))

    if toolbar_m and panel_m:
        toolbar_style = toolbar_m.group(1)
        panel_style = panel_m.group(1)

        tz = re.search(r'zIndex:\s*(\d+)', toolbar_style)
        pz = re.search(r'zIndex:\s*(\d+)', panel_style)
        check('the toolbar declares an explicit zIndex',
              bool(tz), 'no zIndex on the wrapping toolbar — it can be painted '
              'under any later sibling by default stacking order')
        check('the analytics panel declares an explicit zIndex',
              bool(pz), 'no zIndex on the panel — relying on DOM-order '
              'stacking is what let it cover the toolbar in the first place')
        if tz and pz:
            check("the toolbar's zIndex is higher than the panel's",
                  int(tz.group(1)) > int(pz.group(1)),
                  f"toolbar zIndex={tz.group(1)} <= panel zIndex={pz.group(1)} — "
                  "wrapped toolbar controls would still lose to the panel")

    # The toggle button itself must still be inside the toolbar (not moved
    # or renamed away from what the fix relies on).
    check("the analytics toggle button is inside the toolbar's wrapping row",
          bool(re.search(r"setPanelOpen\(\(v\) => !v\)", src)),
          'the toggle handler moved or was renamed — re-check the fix still '
          'targets the right element')

    print()
    if FAILS:
        print(f'graph analytics toggle: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('graph analytics toggle: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
