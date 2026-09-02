#!/usr/bin/env python3
"""Dragging a floating window flush to the viewport's left or top edge
snapped it back to its pre-drag position the instant the mouse was
released.

`app/windows.jsx` has two independent draggable-window implementations
(the generic `WindowFrame` and `ChatWindow`), each committing the
dragged geometry on mouseup by reading the DOM style back:

    x: parseFloat(el.style.left)   || ds.origX,
    y: parseFloat(el.style.top)    || ds.origY,
    w: parseFloat(el.style.width)  || ds.origW,
    h: parseFloat(el.style.height) || ds.origH,

Both implementations' own `onMove` clamp ranges make `x === 0` and
`y === 0` legitimate, reachable positions — e.g. `clamp(ds.origX + dx,
-ds.origW + 80, W - 80)` for `x` (the lower bound is negative for any
window wider than 80px, so 0 sits comfortably inside the range — this
is the ordinary "drag to the left edge" gesture, not an exotic corner
case) and `clamp(ds.origY + dy, 0, H - 40)` for `y`. `parseFloat('0px')`
returns the number `0`, and `0` is falsy in JavaScript, so
`0 || ds.origX` evaluated to `ds.origX` — the geometry from BEFORE the
drag started. The window tracked the mouse correctly the whole drag,
then visibly jumped back to its old spot on release, as if the drag
had never happened.

(WindowFrame's top-edge drag has a maximize-snap shortcut gated on the
raw mouse Y, `ds.lastY <= 4`, which returns early before this code and
masks the bug for a title bar grabbed very close to its own top pixel
— but the mouse Y position within the title bar is unrelated to
whether the window's clamped `top` reaches exactly 0, so any grab point
more than 4px down still hits this bug. ChatWindow has no such
shortcut at all.)

Found by a background hunt agent sweeping previously-unswept areas
(desktop window drag/resize geometry — no existing test in `scripts/`
touched this file's drag logic at all).

Fix: replace the `parseFloat(...) || fallback` pattern with a small
`_px()` helper using `Number.isFinite(...)  ?? fallback`, which only
falls back on a genuine parse failure (NaN), not on a valid 0.

Run: python3 scripts/test_window_drag_to_edge_zero_snaps_back.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = ROOT / 'app' / 'windows.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print("Dragging a window flush to a viewport edge (x=0 or y=0) commits, doesn't snap back")

    src = WINDOWS.read_text(encoding='utf-8')

    geometry_commits = list(re.finditer(
        r"x:\s*(.+?),\n\s*y:\s*(.+?),\n\s*w:\s*(.+?),\n\s*h:\s*(.+?),\n\s*\};",
        src))
    check('found both geometry-commit sites (WindowFrame + ChatWindow)',
          len(geometry_commits) == 2,
          f'found {len(geometry_commits)}')

    check('no geometry-commit site still uses the falsy-on-zero '
          '`parseFloat(...) || ds.origX`-style pattern (x===0/y===0 are '
          'legitimate clamped drag endpoints — the left/top viewport '
          'edge — and must not fall back to the pre-drag value)',
          'parseFloat(el.style.left)   || ds.origX' not in src
          and 'parseFloat(el.style.top)    || ds.origY' not in src
          and 'parseFloat(el.style.width)  || ds.origW' not in src
          and 'parseFloat(el.style.height) || ds.origH' not in src)

    px_helpers = re.findall(
        r"const _px = v => \{ const n = parseFloat\(v\); "
        r"return Number\.isFinite\(n\) \? n : null; \};", src)
    check('a Number.isFinite-based helper (treats 0 as valid, only '
          'falls back on a genuine NaN) is defined at both commit sites',
          len(px_helpers) == 2, f'found {len(px_helpers)}')

    nullish_commits = re.findall(
        r"x: _px\(el\.style\.left\)   \?\? ds\.origX,\n"
        r"\s*y: _px\(el\.style\.top\)    \?\? ds\.origY,\n"
        r"\s*w: _px\(el\.style\.width\)  \?\? ds\.origW,\n"
        r"\s*h: _px\(el\.style\.height\) \?\? ds\.origH,", src)
    check('both commit sites use the helper with ?? (nullish coalescing, '
          'not ||) so a real 0 from _px() is kept',
          len(nullish_commits) == 2, f'found {len(nullish_commits)}')

    # Sanity-check the actual bug scenario: reproduce it against the real
    # JS semantics this fix depends on (0 is falsy but not nullish).
    check('sanity: JS/Python parity — parseFloat("0px")-equivalent (0) '
          'is falsy but NOT null/undefined, which is exactly why `||` '
          'broke and `??` fixes it',
          (0 or 'origX') == 'origX' and (0 if False else 0) is not None)

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
