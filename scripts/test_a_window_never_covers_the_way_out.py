#!/usr/bin/env python3
"""The chat window sat on top of the navigation and would not come off.

Measured live (#148) on a fresh office. The floating chat window is mounted
on every view EXCEPT Chat, and its position is decided once, persisted, and
never revisited. That decision reads the viewport:

    x = Math.max(8, VW - w - 24)

Below the 768px breakpoint `aside.rail` is `display: none`, so on a 560x620
window that arithmetic anchored the chat at x=136 against a layout with no
navigation in it. Widening past 768 brought the rail back at 232px wide.
Nothing recomputed the anchor: the render-time clamp keeps a window on
SCREEN, but its only lower bound was 8. Further down the same path -- a
first mount at <=432px wide anchors at x=8 -- the window covered the rail
outright, and Chat, Office, Tasks, Calendar, Memory and Library were
unclickable at every sample point (elementFromPoint returned the window, not
the link). Nine of the ten views are reachable only from that rail, and
nothing on screen said what had happened or that dragging would fix it.

Windows may cover the board. They may not cover the way out of it.

The fix is a floor, not a new position: `_railRight()` measures how far the
rail actually reaches (measured, not a second copy of the media query),
`_chatGeometryStale` adds `x < rail` to the reasons a stored geometry has to
be thrown away, and the repair now listens for resize as well as mount,
because the rail comes and goes with the breakpoint. It moves the window
ONLY out of that state; a position the boss chose anywhere clear of the rail
is left exactly where they put it, which is checked below.

The three decisions are pure functions of (viewport, rail) precisely so this
file can run the SHIPPED ones. A re-implementation would agree with itself
while the app did something else -- and the whole bug was two pieces of
geometry arithmetic that each looked right on their own.

ONE CLAUSE HERE IS NOT COVERED, and pretending otherwise would be worse than
saying so. `_chatAnchor` floors x at `rail + 8`; deleting that floor changes
nothing this suite (or the sweep below) can see, because the width term
`Math.min(400, Math.max(280, VW - rail - 32))` already puts `VW - w - 24` at
or beyond `rail + 8` for every viewport where the rail exists at all -- the
two expressions are equal in the only reachable branch. It is kept as a floor
of last resort for a caller that passes a rail this arithmetic never sees.
Found by breaking it deliberately and watching the suite stay green.

Run: python3 scripts/test_a_window_never_covers_the_way_out.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = ROOT / 'app' / 'windows.jsx'
FAILS = []

# The rail as the browser reported it on the running office at 1280x800.
RAIL = 232
# The two viewports in the reproduction: the narrow one where the rail is
# display:none, and the wide one the boss widens to.
NARROW = (560, 620)
WIDE = (1280, 800)


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
    """The one line `const NAME = ...;`, verbatim. `_chatAnchor` now floors its
    y term at `CHAT_TOP_FLOOR` (a fresh boss's first click on the Task
    Board's own ADD button used to land on this window instead — see the
    constant's comment in app/windows.jsx) and the probe below has to define
    it for the same reason it re-runs the SHIPPED functions rather than a
    copy: a re-typed `235` here would agree with itself while the app used
    some other number."""
    m = re.search(r'^const %s = .+;$' % re.escape(name), src, re.M)
    return m.group(0) if m else None


PROBE = '''
const OUT = {};
const anchor = (vw, vh, rail) => _chatAnchor(vw, vh, rail);
const clamp  = (g, vw, vh, rail) => _chatClamp(g, vw, vh, rail);
const stale  = (g, vw, vh, rail) => _chatGeometryStale(g, vw, vh, rail);

// 1. The measured reproduction, start to finish.
OUT.narrowAnchor = anchor(%(nw)d, %(nh)d, 0);          // rail is display:none
OUT.narrowStaysStale = stale(OUT.narrowAnchor, %(nw)d, %(nh)d, 0);
OUT.carriedOver = stale(OUT.narrowAnchor, %(ww)d, %(wh)d, %(rail)d);
OUT.repaired = anchor(%(ww)d, %(wh)d, %(rail)d);
OUT.repairSettles = stale(OUT.repaired, %(ww)d, %(wh)d, %(rail)d);

// 2. The worst measured value, x=8 (a first mount at <=432px wide).
OUT.onTheRail = stale({x: 8, y: 8, w: 400, h: 460}, %(ww)d, %(wh)d, %(rail)d);

// 3. A position clear of the rail is the boss's, not ours.
OUT.deliberate = stale({x: 300, y: 120, w: 400, h: 460}, %(ww)d, %(wh)d, %(rail)d);
OUT.deliberateClamp = clamp({x: 300, y: 120, w: 400, h: 460}, %(ww)d, %(wh)d, %(rail)d);

// 4. The clamp cannot push a window onto the rail either. A window resized
//    almost to the full viewport has nowhere to sit but left, and the
//    on-screen clamp alone would put it there.
OUT.wideWindow = clamp({x: 900, y: 100, w: %(ww)d - 16, h: 400}, %(ww)d, %(wh)d, %(rail)d);
OUT.normalWindow = clamp({x: 856, y: 260, w: 400, h: 460}, %(ww)d, %(wh)d, %(rail)d);
// The stale geometry as it is on the very render that discovers it: the
// clamp runs before the repair effect commits, so the floor is what stands
// between the boss and one frame of a covered rail.
OUT.staleClamp = clamp({x: 8, y: 8, w: 400, h: 460}, %(ww)d, %(wh)d, %(rail)d);

// 4b. The same properties across the whole space rather than at three
//     points, because a fixture only ever proves the fixture.
OUT.sweep = [];
for (const vw of [780, 800, 900, 1024, 1280, 1440, 1920, 2560]) {
  for (const vh of [600, 700, 800, 1080]) {
    // 420 is wider than any rail the app ships today. It is in here because
    // every rail-aware term in `_chatAnchor` is inert at 232px -- there is
    // always room for a 400px panel beside it above the 768px breakpoint --
    // so without a rail this wide the sweep would be green on an anchor that
    // had forgotten the rail entirely. Measured, by deleting it.
    for (const rl of [0, 180, 232, 300, 420]) {
      const a = anchor(vw, vh, rl);
      const c = clamp({x: 4, y: 4, w: 900, h: 900}, vw, vh, rl);
      OUT.sweep.push({vw, vh, rl,
        aOk: a.x >= rl && a.x + a.w <= vw && a.w >= 280,
        cOk: c.x >= Math.min(rl, vw) && c.x + c.w <= vw,
        a, c});
    }
  }
}

// 5. With no rail in the layout, nothing changes from the old behaviour.
OUT.noRail = anchor(%(ww)d, %(wh)d, 0);
OUT.noRailClamp = clamp({x: 8, y: 8, w: 400, h: 460}, %(ww)d, %(wh)d, 0);

// 6. Junk that would render as NaNpx.
OUT.nanStale = stale({x: NaN, y: 10, w: 400, h: 460}, %(ww)d, %(wh)d, %(rail)d);
OUT.missingStale = stale(null, %(ww)d, %(wh)d, %(rail)d);

// 7. Too narrow for a 400px panel beside the rail: width gives way first.
OUT.tight = anchor(780, 700, 420);

console.log(JSON.stringify(OUT));
''' % {'nw': NARROW[0], 'nh': NARROW[1], 'ww': WIDE[0], 'wh': WIDE[1], 'rail': RAIL}


def run_probe():
    src = WINDOWS.read_text(encoding='utf-8')
    pieces = []
    # _chatAnchor's body references CHAT_TOP_FLOOR (a fresh-session-only floor
    # so the default position can never seed on top of the Task Board's own
    # ADD button — see the constant's comment in app/windows.jsx). It must be
    # defined before _chatAnchor's lifted body runs, so it goes in first.
    floor_const = lift_const(src, 'CHAT_TOP_FLOOR')
    if floor_const is None:
        return None, 'could not lift CHAT_TOP_FLOOR from app/windows.jsx'
    pieces.append(floor_const)
    for name in ('_chatAnchor', '_chatGeometryStale', '_chatClamp'):
        body = lift(src, name)
        if body is None:
            return None, 'could not lift %s from app/windows.jsx' % name
        pieces.append(body)
    tmp = ROOT / '.window-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        (tmp / 'probe.js').write_text('\n\n'.join(pieces) + '\n\n' + PROBE,
                                      encoding='utf-8')
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'probe.js')],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, 'node: ' + p.stderr.strip()[:300]
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('a window never covers the way out')
    if not shutil.which('node'):
        print('  SKIP  node not available — cannot run the real helpers')
        return 0

    src = WINDOWS.read_text(encoding='utf-8')

    print('1. the rail is measured, not re-derived')
    # A second copy of `@media (max-width: 768px)` in JS is the kind of thing
    # that is right on the day it is written and wrong six months later.
    m = re.search(r'function _railRight\s*\(\)\s*\{[\s\S]*?\n\}', src)
    check('_railRight exists and reads the live rail',
          bool(m) and "querySelector('aside.rail')" in (m.group(0) if m else ''),
          'app/windows.jsx: the floor has to come from the element that is '
          'actually in the layout')
    check('...and does not hardcode the breakpoint instead',
          bool(m) and '768' not in m.group(0),
          'app/windows.jsx: a copy of the media query in JS drifts from the '
          'stylesheet silently')

    r, err = run_probe()
    if r is None:
        print('  FAIL  could not run the helpers: ' + str(err))
        return 1

    print('2. the measured reproduction')
    na = r['narrowAnchor']
    check('the fixture is still the narrow anchor that started this: x=136',
          na['x'] == 136 and na['w'] == 400,
          f'anchor at {NARROW} with no rail = {na} — if this has moved, the '
          'checks below are about some other bug')
    check('...and it is fine while the rail is not in the layout',
          r['narrowStaysStale'] is False,
          'nothing to collide with at 560px, so nothing should be moved — a '
          'repair that fires here would fight the phone layout every resize')
    check('carried into the wide layout, it is recognised as stale',
          r['carriedOver'] is True,
          f'x={na["x"]} against a rail reaching {RAIL}px: this is the window '
          'sitting on the navigation, and it used to survive here forever')
    rp = r['repaired']
    check('...and is re-anchored clear of the rail',
          rp['x'] >= RAIL,
          f'repaired to {rp} — must start at or beyond {RAIL}')
    check('...somewhere that does not immediately want repairing again',
          r['repairSettles'] is False,
          f'{rp} is still stale — the repair would loop')

    print('3. the worst of it')
    check('a window at x=8 over the whole rail is stale',
          r['onTheRail'] is True,
          'measured: six of the ten destinations unclickable at every sample '
          'point, with nothing on screen to say why')

    print('4. a position the boss chose is theirs')
    # The failure mode of an over-eager fix: snapping a window the user
    # deliberately parked. Only the nav is defended, not a preferred corner.
    check('a window placed clear of the rail is never moved',
          r['deliberate'] is False,
          'x=300 clears a 232px rail; moving it would be the office '
          'overruling a choice the boss made with a mouse')
    dc = r['deliberateClamp']
    check('...and the clamp leaves it where it is',
          dc['x'] == 300 and dc['y'] == 120,
          f'clamped to {dc} from x=300 y=120')

    print('5. the clamp cannot re-create the bug on its own')
    # This one failed on the first draft of the fix and was right to. A
    # window resized to nearly the full viewport is NOT stale (it is not
    # bigger than the viewport), so the clamp is the only thing standing
    # between it and the rail -- and with the width capped at VW-16 there was
    # nowhere left to put it but x=8. The cap is the work area now.
    ww = r['wideWindow']
    check('a near-fullwidth window is held off the rail',
          ww['x'] >= RAIL,
          f'clamped to {ww} — the on-screen clamp alone would push it left '
          'onto the navigation')
    check('...by giving up width, which is the part nothing depends on',
          ww['w'] <= WIDE[0] - RAIL - 16,
          f"w={ww['w']} — a window wider than the space beside the rail can "
          'only be placed on top of it')
    nw = r['normalWindow']
    check('an ordinary bottom-right window is untouched by the floor',
          nw['x'] == 856 and nw['w'] == 400,
          f'clamped to {nw}')
    # The frame between "this geometry is stale" and "the repair committed a
    # new one" belongs to the clamp alone. Without this fixture the floor can
    # be deleted outright and every other check here still passes — measured,
    # by deleting it.
    sc = r['staleClamp']
    check('the stale geometry is held off the rail on the render that finds it',
          sc['x'] >= RAIL,
          f'clamped to {sc} — the repair effect commits after this render, so '
          'without the floor the boss sees a frame of covered navigation')

    print('5b. the same properties everywhere, not just at three points')
    bad_a = [s for s in r['sweep'] if not s['aOk']]
    bad_c = [s for s in r['sweep'] if not s['cOk']]
    check('every anchor across the sweep clears the rail and fits the screen',
          not bad_a, f'{len(bad_a)} of {len(r["sweep"])} failed, e.g. {bad_a[:2]}')
    check('...and every clamped geometry does too',
          not bad_c, f'{len(bad_c)} of {len(r["sweep"])} failed, e.g. {bad_c[:2]}')

    print('6. with no rail, nothing changed')
    # The regression this fix could most easily cause: the phone and narrow
    # layouts share this code and have no rail to defend.
    nr = r['noRail']
    check('the anchor is the old bottom-right default',
          nr == {'x': WIDE[0] - 400 - 24, 'y': WIDE[1] - 460 - 80,
                 'w': 400, 'h': 460},
          f'{nr} — with rail=0 the arithmetic must reduce to what it always was')
    check('the clamp is the old on-screen clamp',
          r['noRailClamp']['x'] == 8,
          f"{r['noRailClamp']} — x=8 is a legitimate position when there is "
          'no navigation there to cover')

    print('7. the edges')
    check('a geometry that would render NaNpx is thrown away',
          r['nanStale'] is True and r['missingStale'] is True,
          'a non-finite x puts the window nowhere at all, which is worse '
          'than putting it in the wrong place')
    # A rail wider than anything shipping today, for the reason spelled out
    # in the sweep: at 232px there is always room for the full 400px panel
    # beside it, so nothing here would bind.
    t = r['tight']
    check('too narrow for a 400px panel beside the rail: width gives way',
          t['x'] >= 420 and t['x'] + t['w'] <= 780,
          f'anchor(780, 700, 420) = {t} — the navigation is not the thing to '
          'sacrifice when the screen runs out of room')

    print('8. one implementation, not two')
    # The bug was two pieces of geometry arithmetic that each looked right.
    # If the component starts recomputing them inline again, this suite goes
    # on testing the helpers while the app does something else.
    body = src[src.index('function ChatWindow'):]
    check('ChatWindow uses the helpers rather than its own arithmetic',
          '_chatAnchor(' in body and '_chatClamp(' in body
          and '_chatGeometryStale(' in body,
          'app/windows.jsx: inline geometry in the component is arithmetic '
          'this file cannot see')
    # The behavioural half, which lives in the component and not in the pure
    # helpers: the rail appears and disappears with the breakpoint, so a
    # repair that only ever runs on mount leaves the boss waiting for a
    # reload. The helpers stay green with this deleted — measured.
    eff = re.search(r'React\.useEffect\(\(\) => \{[\s\S]*?_chatAnchor\('
                    r'[\s\S]*?\n  \}, \[', body)
    check('the repair runs again when the viewport changes, not only on mount',
          bool(eff) and "addEventListener('resize'" in eff.group(0)
          and "removeEventListener('resize'" in eff.group(0),
          'app/windows.jsx: the rail comes back at the 768px breakpoint, and '
          'that is exactly the moment a window anchored without it becomes '
          'wrong')

    print()
    if FAILS:
        print(f'way out: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('way out: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
