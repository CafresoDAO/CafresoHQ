#!/usr/bin/env python3
"""A fresh chat window opened on top of the Task Board's own ADD button.

Measured live (2026-09-03) on a brand-new office session, no stored
geometry, 1280x720 -- the single most common "brand new boss" viewport.
`_chatAnchor`'s stock formula (`y = Math.max(8, VH - h - 80)`) put the
window at y=180. The Task Board's own "+ NEW" add-task row (opened) puts
its ADD button at y~191-224. A real click on ADD at its rendered
coordinates hit the chat window's drag handle instead --
`document.elementFromPoint` confirmed it, resolving to the window's
`position:fixed; z-index:300` div, not the button -- and the task was
never created. No error, no visual break: the input just sat there
un-submitted. Only a `.click()` called directly on the button element,
bypassing hit-testing, actually filed the task.

The fix has two halves, and either one alone does nothing observable:

1. `CHAT_TOP_FLOOR = 235` in app/windows.jsx floors `_chatAnchor`'s y term
   so a fresh/re-anchored window can never open above that line -- clearing
   the measured ADD-button row with a little margin. It is deliberately
   NOT threaded into `_chatGeometryStale` or `_chatClamp`: both of those
   also govern a position the boss chose by dragging, and
   test_a_window_never_covers_the_way_out.py pins that a deliberate
   placement clear of the rail (x=300, y=120) must never be moved again --
   "the boss's choice is final" for every axis this file does not treat as
   a hard floor.

2. app.jsx's `chatWinGeo` lazy initializer -- the value `useStored` falls
   back to when localStorage has nothing yet, i.e. exactly a brand-new
   session -- used to carry its OWN hand-rolled copy of the old formula
   (`y: Math.max(8, H - h - 80)`), independent of `_chatAnchor` and never
   synced with it. Fixing `_chatAnchor` alone did nothing for a fresh
   office, because a fresh office never actually called it -- it called
   this duplicate instead, and `_chatGeometryStale` sees the duplicate's
   output as a complete, in-bounds, off-the-rail geometry with nothing to
   repair. The fix deletes the duplicate and has the initializer call the
   real, now-exported `_chatAnchor(W, H, _railRight())` directly.

This file checks both halves. It does not re-run
test_a_window_never_covers_the_way_out.py's own sweep (rail-overlap on
resize, the deliberate-placement contract, the no-rail pinned default) --
those stay that file's job. This one is specifically about a SHORT fresh
viewport and about there being ONE formula, not two.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = ROOT / 'app' / 'windows.jsx'
APP = ROOT / 'app.jsx'
FAILS = []

# The measured reproduction viewport and the ADD button's measured bottom
# edge on it (elementFromPoint confirmed the overlap up to y=224.4).
FRESH = (1280, 720)
ADD_BUTTON_BOTTOM = 224.4


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(src, name):
    """The source of one top-level `function name(...) {...}`, brace-matched."""
    m = re.search(r'^function %s\s*\(' % re.escape(name), src, re.M)
    if not m:
        return None
    i = src.index('{', m.end() - 1)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    return None


def lift_const(src, name):
    """The one line `const NAME = ...;`, verbatim."""
    m = re.search(r'^const %s = .+;$' % re.escape(name), src, re.M)
    return m.group(0) if m else None


def lift_block(src, marker):
    """The brace-balanced block starting at the first `{` at/after `marker`.

    Used for app.jsx's `useStored(k('chatWinGeoV2'), () => { ... })`
    initializer, which is a `const [x, y] = useStored(key, () => {...});`
    statement, not a top-level `function name(...) {...}` -- `lift()`'s
    pattern does not match it.
    """
    i = src.find(marker)
    if i == -1:
        return None
    b = src.index('{', i)
    depth = 0
    for j in range(b, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return None


PROBE = '''
const OUT = {};
// The measured bug: a brand-new session, no stored geometry, on the
// single most common short-viewport size. No rail (Chat is a top-level
// view; the reproduction was measured before the rail entered the
// picture, and the floor has to hold with or without it).
OUT.freshShort = _chatAnchor(%(fw)d, %(fh)d, 0);
// A viewport tall enough that the natural formula already clears the
// floor on its own -- this must come out EXACTLY as it did before the
// floor existed, or the floor is doing more than advertised.
OUT.freshTall = _chatAnchor(1280, 800, 0);
// The floor still has to hold with a rail present (x is rail-aware, y is not).
OUT.freshShortWithRail = _chatAnchor(1280, 700, 232);
// A viewport tall enough that the floor binds nowhere near the boundary --
// confirms this is a floor (max), not a clamp that pins everything to 235.
OUT.freshVeryTall = _chatAnchor(1280, 900, 0);
console.log(JSON.stringify(OUT));
'''


def run_probe():
    src = WINDOWS.read_text(encoding='utf-8')
    floor_const = lift_const(src, 'CHAT_TOP_FLOOR')
    if floor_const is None:
        return None, 'could not lift CHAT_TOP_FLOOR from app/windows.jsx'
    anchor = lift(src, '_chatAnchor')
    if anchor is None:
        return None, 'could not lift _chatAnchor from app/windows.jsx'
    tmp = ROOT / '.add-button-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        (tmp / 'probe.js').write_text(
            floor_const + '\n\n' + anchor + '\n\n' + (PROBE % {'fw': FRESH[0], 'fh': FRESH[1]}),
            encoding='utf-8')
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'probe.js')],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, 'node: ' + p.stderr.strip()[:300]
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('a fresh chat window does not cover the ADD button')
    if not shutil.which('node'):
        print('  SKIP  node not available — cannot run the real helpers')
        return 0

    win_src = WINDOWS.read_text(encoding='utf-8')
    app_src = APP.read_text(encoding='utf-8')

    print('1. the floor is a named constant, not a re-typed literal')
    const_line = lift_const(win_src, 'CHAT_TOP_FLOOR')
    check('CHAT_TOP_FLOOR is declared in app/windows.jsx',
          const_line is not None,
          'expected a top-level `const CHAT_TOP_FLOOR = <n>;`')
    check('...set to the measured value, 235',
          const_line is not None and re.search(r'=\s*235\s*;', const_line) is not None,
          f'got: {const_line!r}')
    anchor_body = lift(win_src, '_chatAnchor')
    check('_chatAnchor reads CHAT_TOP_FLOOR rather than a bare number',
          anchor_body is not None and 'CHAT_TOP_FLOOR' in anchor_body,
          'a literal 235 typed directly into _chatAnchor would pass every '
          'check below today and silently drift from the constant tomorrow')

    print('2. the floor is exported so app.jsx can share it, not copy it')
    m = re.search(r'^export\s*\{[^}]*\}\s*;', win_src, re.M)
    check('app/windows.jsx exports _chatAnchor',
          bool(m) and '_chatAnchor' in m.group(0), m.group(0) if m else 'no export found')
    check('...and _railRight',
          bool(m) and '_railRight' in m.group(0), m.group(0) if m else 'no export found')
    imp = re.search(r"^import\s*\{[^}]*\}\s*from\s*'\./app/windows\.jsx'\s*;", app_src, re.M)
    check('app.jsx imports _chatAnchor from app/windows.jsx',
          bool(imp) and '_chatAnchor' in imp.group(0),
          imp.group(0) if imp else 'no matching import found')
    check('...and _railRight',
          bool(imp) and '_railRight' in imp.group(0),
          imp.group(0) if imp else 'no matching import found')

    print('3. there is one formula now, not two')
    init = lift_block(app_src, "useStored(k('chatWinGeoV2')")
    check('the chatWinGeoV2 initializer exists in app.jsx', init is not None)
    check('...and calls the real _chatAnchor',
          init is not None and '_chatAnchor(' in init,
          'app.jsx: the lazy initial value for a brand-new session must '
          'come from the same place every later repair does')
    check('...instead of a second, hand-rolled formula',
          init is not None and 'Math.max(8,' not in init,
          "app.jsx: `Math.max(8, H - h - 80)` was the duplicate's own copy "
          "of the pre-floor arithmetic -- its presence here means a fresh "
          "session bypasses _chatAnchor (and CHAT_TOP_FLOOR) entirely, "
          "exactly the state that shipped the bug")

    r, err = run_probe()
    if r is None:
        print('  FAIL  could not run the real helpers: ' + str(err))
        return 1

    print('4. the measured reproduction, fixed')
    fs = r['freshShort']
    check(f'{FRESH} with no rail clears the ADD button',
          fs['y'] > ADD_BUTTON_BOTTOM,
          f'anchor at {FRESH} = {fs} -- y must clear {ADD_BUTTON_BOTTOM}, the '
          'measured bottom edge of the Task Board\'s ADD button')
    check('...by landing exactly on the floor, not some other number',
          fs['y'] == 235, f'got y={fs["y"]}')

    print('5. the floor does not move what already clears it')
    ft = r['freshTall']
    check('a tall-enough viewport keeps the pre-fix default exactly',
          ft['y'] == (800 - 460 - 80),
          f'anchor at (1280, 800) = {ft} -- must equal the old '
          'unfloored value (260), unchanged, or the floor is doing more '
          'than the ADD button needed')
    fvt = r['freshVeryTall']
    check('...and a viewport far past the boundary is untouched too',
          fvt['y'] == (900 - 460 - 80),
          f'anchor at (1280, 900) = {fvt} -- expected y=360')

    print('6. the floor holds with a rail in the layout too')
    fsr = r['freshShortWithRail']
    check('a short viewport with the rail present also clears the floor',
          fsr['y'] == 235, f'anchor at (1280, 700, rail=232) = {fsr}')
    check('...and x still clears the rail, unrelated to this fix',
          fsr['x'] >= 232, f'got x={fsr["x"]}')

    print()
    if FAILS:
        print(f'ADD button: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('ADD button: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
