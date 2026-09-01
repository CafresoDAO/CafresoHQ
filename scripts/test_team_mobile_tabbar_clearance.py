#!/usr/bin/env python3
"""TeamView's staff roster was unclickable behind the mobile tab bar —
same class of bug, same root cause shape, as the Tasks-board tab-bar
clearance bug already fixed (see docs/OFFICE_AS_INTERFACE.md).

The two mobile media-query blocks in styles.css that reserve bottom
clearance for the fixed tab bar named an explicit selector `.team-view`
in both the base (72px) and standalone/PWA (80px) blocks. But TeamView
(`views/core.jsx`) actually renders `<div className="view-team" ...>` —
the reverse word order. No element anywhere in the codebase ever has
class `team-view` (confirmed via grep), so this selector matched
nothing since it was written: the staff roster had zero reserved space
above the fixed mobile tab bar.

Measured live at 390x700: after scrolling `.team-grid` to its max
scrollTop, the last coworker card's rect (top:618, bottom:700) was
physically overlapped by the fixed `.mobile-tabbar` (top:630, bottom:700)
— `document.elementFromPoint` at the card's center resolved to
`.mtab.active`, not the card. A tap there activates the tab bar instead
of opening that coworker's inspect panel.

Found by a background hunt agent sweeping previously-uncovered areas.

Fix: renamed the selector in both clearance blocks (styles.css) from
`.team-view` to `.view-team` to match the actual className TeamView
renders.

Run: python3 scripts/test_team_mobile_tabbar_clearance.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
CSS = ROOT / 'styles.css'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def mobile_blocks(css):
    out = []
    for m in re.finditer(
        r'@media \(max-width: 768px\)|@media all and \(display-mode: standalone\)', css
    ):
        i = m.start()
        depth, k = 0, css.index('{', i)
        while k < len(css):
            if css[k] == '{':
                depth += 1
            elif css[k] == '}':
                depth -= 1
                if depth == 0:
                    out.append(css[i:k + 1])
                    break
            k += 1
    return out


def selector_lists_naming(block, member, pattern):
    """True if some selector LIST containing `member` as one of its
    comma-separated parts has a rule body matching `pattern`. Deliberately
    not `member in block` — a stray textual mention (e.g. in a comment)
    must not pass."""
    for sel_match in re.finditer(r'([.\w,\s>*-]+)\{([^}]*)\}', block):
        selectors, body = sel_match.group(1), sel_match.group(2)
        parts = [p.strip() for p in selectors.split(',')]
        if member in parts and re.search(pattern, body):
            return True
    return False


def main():
    print("TeamView's staff roster clears the fixed mobile tab bar")

    core = CORE.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    blocks = mobile_blocks(css)
    check('found at least one max-width:768px block', bool(blocks))

    check('TeamView still renders its content as "view-team" '
          '(the reverse word order from the old, never-matching '
          '".team-view" selector)',
          bool(re.search(r'<div className="view-team"', core)),
          'views/core.jsx: if this class is renamed, the mobile '
          'clearance rules below have to follow it or the bug comes '
          'right back')

    check('the stale ".team-view" selector (which never matched any '
          'real element) is gone from styles.css entirely',
          '.team-view' not in css)

    base = next((b for b in blocks if 'calc(72px' in b and '.view,' in b), None)
    check('found the base-mobile clearance block (72px)', base is not None)
    if base is not None:
        check('.view-team is in the base-mobile clearance selector list',
              selector_lists_naming(base, '.view-team', r'padding-bottom:\s*calc\(72px'))

    pwa = next((b for b in blocks if 'calc(80px' in b and '.mobile-chat-view' in b), None)
    check('found the standalone/PWA clearance block (80px)', pwa is not None)
    if pwa is not None:
        check('.view-team is in the standalone/PWA clearance selector list too',
              selector_lists_naming(pwa, '.view-team', r'padding-bottom:\s*calc\(80px'),
              'fixing only one block leaves the other viewport class stranded')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
