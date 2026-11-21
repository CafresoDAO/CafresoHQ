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

    # Since 2026-11-21 the always-open analysis card is gone; what the toggle
    # opens is the Obsidian-style settings panel (.obs-graph-settings), and the
    # toolbar is .obs-graph-bar, a single non-wrapping row. The invariant is
    # the same: the panel must never sit on top of the button that closes it.
    css = (ROOT / 'styles.css').read_text(encoding='utf-8')
    bar = re.search(r'\.obs-graph-bar \{([^}]*)\}', css)
    panel = re.search(r'\.obs-graph-settings \{([^}]*)\}', css)
    btn = re.search(r'\.obs-graph-btn \{([^}]*)\}', css)
    check('the toolbar rule is found', bool(bar))
    check('the settings panel rule is found', bool(panel))
    check('the toolbar button rule is found', bool(btn))
    if bar and panel and btn:
        num = lambda rx, txt: int(re.search(rx, txt).group(1)) if re.search(rx, txt) else None
        bar_top, btn_h = num(r'top:\s*(\d+)px', bar.group(1)), num(r'height:\s*(\d+)px', btn.group(1))
        panel_top = num(r'top:\s*(\d+)px', panel.group(1))
        check('the toolbar does not wrap onto the panel', 'flex-wrap: wrap' not in bar.group(1))
        check('the panel starts below the toolbar row, so it cannot cover the toggle',
              None not in (bar_top, btn_h, panel_top) and panel_top >= bar_top + btn_h,
              f'bar top {bar_top} + button {btn_h} vs panel top {panel_top}')
    check('the old analysis card is gone', 'width: 246' not in src)
    check('the settings toggle is inside the toolbar row',
          bool(re.search(r"obs-graph-btn' \+ \(panelOpen[\s\S]{0,200}setPanelOpen\(\(v\) => !v\)", src)),
          'the toggle handler moved or was renamed — re-check the fix still '
          'targets the right element')
    check('settings start closed', "useSV(persisted.drawerOpen === true)" in src)

    print()
    if FAILS:
        print(f'graph analytics toggle: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:5]))
        return 1
    print('graph analytics toggle: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
