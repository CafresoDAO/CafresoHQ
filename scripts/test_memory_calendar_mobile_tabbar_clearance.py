#!/usr/bin/env python3
"""Memory and Calendar's last rows were unclickable behind the mobile tab bar —
same class of bug, same root cause shape, as the Tasks-board and TeamView
tab-bar clearance bugs already fixed (see docs/OFFICE_AS_INTERFACE.md).

The two mobile media-query blocks in styles.css that reserve bottom
clearance for the fixed tab bar (base 72px, standalone/PWA 80px) never
named `.view-memory` or `.view-calendar` at all — not a reversed word
order like the TeamView bug, simply omitted entirely. MemoryPage
(`views/core.jsx`) renders `<div className="view-memory">` and
CalendarView renders `<div className="view-calendar">`, so on mobile
neither view ever reserved space above the fixed `.mobile-tabbar`: the
last memory entry / last calendar row sat directly behind it.

Found by a background hunt agent sweeping previously-uncovered areas,
after two consecutive tab-bar-clearance bugs of the identical shape
(Tasks, then TeamView) prompted an explicit check for more instances of
the same pattern.

Fix: added `.view-memory, .view-calendar` to both clearance selector
lists in styles.css, mirroring the TeamView fix exactly.

Run: python3 scripts/test_memory_calendar_mobile_tabbar_clearance.py
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
    print("Memory's and Calendar's content clears the fixed mobile tab bar")

    core = CORE.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')
    blocks = mobile_blocks(css)
    check('found at least one max-width:768px block', bool(blocks))

    check('MemoryPage still renders its content as "view-memory"',
          bool(re.search(r'<div className="view-memory"', core)),
          'views/core.jsx: if this class is renamed, the mobile '
          'clearance rules below have to follow it or the bug comes '
          'right back')
    check('CalendarView still renders its content as "view-calendar"',
          bool(re.search(r'<div className="view-calendar"', core)),
          'views/core.jsx: if this class is renamed, the mobile '
          'clearance rules below have to follow it or the bug comes '
          'right back')

    base = next((b for b in blocks if 'calc(72px' in b and '.view,' in b), None)
    check('found the base-mobile clearance block (72px)', base is not None)
    if base is not None:
        check('.view-memory is in the base-mobile clearance selector list',
              selector_lists_naming(base, '.view-memory', r'padding-bottom:\s*calc\(72px'))
        check('.view-calendar is in the base-mobile clearance selector list',
              selector_lists_naming(base, '.view-calendar', r'padding-bottom:\s*calc\(72px'))

    pwa = next((b for b in blocks if 'calc(80px' in b and '.mobile-chat-view' in b), None)
    check('found the standalone/PWA clearance block (80px)', pwa is not None)
    if pwa is not None:
        check('.view-memory is in the standalone/PWA clearance selector list too',
              selector_lists_naming(pwa, '.view-memory', r'padding-bottom:\s*calc\(80px'),
              'fixing only one block leaves the other viewport class stranded')
        check('.view-calendar is in the standalone/PWA clearance selector list too',
              selector_lists_naming(pwa, '.view-calendar', r'padding-bottom:\s*calc\(80px'),
              'fixing only one block leaves the other viewport class stranded')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
