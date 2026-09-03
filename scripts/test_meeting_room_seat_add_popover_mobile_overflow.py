#!/usr/bin/env python3
"""The Meeting Room's "+ Seat someone" popover could shove the whole modal
into horizontal scroll on a phone — features.jsx / styles.css.

MeetingRoom (features.jsx) renders seated coworkers plus one dashed
"+ Seat someone" tile in a `repeat(auto-fill, minmax(140px, 1fr))` grid
(`.meeting-attendee-grid`, styles.css). On a narrow modal that grid packs
two columns, so which column the seat-add tile lands in flips with the
runtime seat count. Clicking it opens `.seat-add-popover`, a fixed
240px-wide panel anchored `position: absolute; left: 0` off that tile.

Reproduced live at a 375px viewport with an odd number of coworkers
already seated (so the seat-add tile falls in the grid's right column):
the popover's own rect started ~57.8px to the right of where 240px of
room actually remained, and `.modal-body`'s scrollWidth read 437 against
a 375 clientWidth — the fixed-width popover was forcing the entire
Meeting Room modal to scroll sideways, not just clipping its own edge
(`.modal-body` only sets `overflow-y: auto`, and CSS computes the paired
`overflow-x` as `auto` too, so the overflow surfaces as a real scrollbar).

Same shape as the add-session menu clamp already used in
views/terminal.jsx's ProjectTerminal: a static CSS anchor can't fix this
because the side that needs clamping flips with the tile's column, so the
fix measures the tile's `getBoundingClientRect()` at open time and only
then decides which side to anchor the popover to. After the fix, the same
375px / odd-seat-count repro measured `.modal-body` clientWidth/scrollWidth
as 375/375 (no overflow), and the popover carried `align-right` so it hugs
the tile's right edge (`left: auto; right: 0`) instead of running off it.

Run: python3 scripts/test_meeting_room_seat_add_popover_mobile_overflow.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / 'features.jsx'
CSS = ROOT / 'styles.css'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_function(src, name):
    """Balanced-brace slice of `function <name>(...) { ... }`, since a
    plain regex with a length cap would either miss the tail of a long
    component or bleed into whatever function follows it."""
    m = re.search(r'function %s\s*\([^)]*\)\s*\{' % re.escape(name), src)
    if not m:
        return ''
    # m already ends on the body's opening brace — MeetingRoom's own params
    # destructure `{ participants, ... }`, so re-searching for the next '{'
    # from m.start() would grab that param brace instead of the body's.
    depth, k = 0, m.end() - 1
    start = k
    while k < len(src):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[start:k + 1]
        k += 1
    return ''


def top_level_rule(css, selector_literal):
    """The literal rule text for `selector_literal`, but only the
    occurrence that sits outside every @media block — i.e. unconditional,
    not folded into a breakpoint by accident."""
    mobile = mobile_blocks(css)
    without_media = css.replace(mobile, '') if mobile else css
    m = re.search(re.escape(selector_literal) + r'\s*\{([^}]*)\}', without_media)
    return m.group(1) if m else None


def mobile_blocks(css):
    """Every @media (max-width: 768px) block, concatenated — styles.css has
    ~23 of them, and this fix must NOT be one of them (it's JS-driven off
    window.innerWidth, not a fixed breakpoint), so checks need the ability
    to tell 'inside a media block' from 'top level' apart."""
    out = []
    for m in re.finditer(r'@media \(max-width: 768px\)', css):
        depth, k = 0, css.index('{', m.start())
        while k < len(css):
            if css[k] == '{':
                depth += 1
            elif css[k] == '}':
                depth -= 1
                if depth == 0:
                    out.append(css[m.start():k + 1])
                    break
            k += 1
    return '\n'.join(out)


def main():
    print('Meeting Room seat-add popover — no horizontal overflow on mobile')
    for p in (FEATURES, CSS):
        if not p.is_file():
            print(f'  FAIL  missing {p}')
            return 1
    features = FEATURES.read_text(encoding='utf-8')
    css = CSS.read_text(encoding='utf-8')

    room = extract_function(features, 'MeetingRoom')
    check('found the MeetingRoom function body', bool(room),
          'features.jsx: expected `function MeetingRoom(...) { ... }`')

    # ── the tile is measured, not statically anchored ───────────────────────
    check('a ref is attached to the seat-add tile',
          bool(re.search(r'\bseatAddRef\s*=\s*(?:useRF|useRef)\(null\)', room)),
          'features.jsx: MeetingRoom needs a ref on .seat-add to measure its '
          'rect before deciding which side to open the popover on')
    check('...and that ref is actually wired to the seat-add tile',
          bool(re.search(r'className="seat seat-add"[^>]*\bref=\{seatAddRef\}', room)),
          'features.jsx: a ref declared but not attached measures nothing')

    toggle = re.search(r'const toggleAdd = \(\) => \{.*?\n  \};', room, re.S)
    check('toggleAdd() exists and measures the tile before opening',
          bool(toggle) and 'getBoundingClientRect' in toggle.group(0),
          'features.jsx: the popover side must be decided from the tile\'s '
          'live position, not a fixed CSS anchor, since which grid column '
          'it lands in depends on the runtime seat count')
    if toggle:
        body = toggle.group(0)
        check('...against the popover\'s real width (240px)',
              bool(re.search(r'\bPOPOVER_W\s*=\s*240\b', body)),
              'features.jsx: the threshold must match .seat-add-popover\'s '
              'actual width in styles.css, not an arbitrary guess')
        check('...and against the viewport, with edge breathing room',
              bool(re.search(r'window\.innerWidth\s*-\s*\d+', body)),
              'features.jsx: comparing to window.innerWidth (not the modal\'s '
              'own width) is what makes this work regardless of the modal\'s '
              'own min(94vw, maxW) sizing')
        check('...and flips addAlignRight from that measurement',
              bool(re.search(r'setAddAlignRight\(', body)),
              'features.jsx: the measurement is pointless if it never '
              'reaches state')

    check('the seat-add tile opens via toggleAdd, not a raw toggle',
          bool(re.search(r'className="seat seat-add"[^>]*\bonClick=\{toggleAdd\}', room)),
          'features.jsx: reverting to onClick={() => setAddOpen(o => !o)} '
          'would open the popover without ever measuring the tile')

    # ── the popover actually wears the flip ──────────────────────────────────
    check('the popover className conditionally adds align-right',
          bool(re.search(
              r"className=\{'meeting-attendee-grid seat-add-popover'\s*\+\s*"
              r"\(addAlignRight\s*\?\s*' align-right'\s*:\s*''\)\}", room)),
          'features.jsx: addAlignRight is measured but never applied to the '
          'popover it was measured for')

    # ── the CSS side of the flip, and that it stays unconditional ───────────
    base_rule = top_level_rule(css, '.seat-add-popover')
    check('.seat-add-popover keeps its fixed 240px width',
          bool(base_rule) and bool(re.search(r'width:\s*240px', base_rule or '')),
          'styles.css: if this width changes, POPOVER_W in features.jsx must '
          'change with it or the measurement lies')

    align_rule = top_level_rule(css, '.seat-add-popover.align-right')
    check('.seat-add-popover.align-right exists at the top level (not inside a media block)',
          align_rule is not None,
          'styles.css: this must be unconditional — the JS decides *when* to '
          'apply it off window.innerWidth, so folding it into a fixed '
          '@media breakpoint would make it wrong at exactly the widths the '
          'JS was measuring for')
    check('...and it re-anchors to the tile\'s right edge',
          bool(align_rule) and 'left: auto' in align_rule and 'right: 0' in align_rule,
          'styles.css: without both `left: auto` and `right: 0` the base '
          'rule\'s `left: 0` still wins and the popover still overflows')

    print()
    if FAILS:
        print(f'meeting room seat-add popover: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('meeting room seat-add popover: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
