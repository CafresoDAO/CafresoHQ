#!/usr/bin/env python3
"""Grabbing a window's title bar teleported it hundreds of pixels away.

`app/windows.jsx` renders a floating window from a CLAMPED geometry and
started its drag gesture from the RAW stored one. Those are not the same
number, and the difference is exactly how far the window jumped on the first
pixel of the drag -- then mouseup committed the jump.

WindowFrame. `openWindows` is file-backed (app.jsx line 506) and rides along
in saved workspaces, so geometry laid out on a big monitor comes back on a
small one. The render has always clamped it:

    let w = Math.max(280, Math.min(g.w, VW - 16));
    let x = Math.max(8, Math.min(g.x, VW - w - 8));   // ... and y likewise

while `startGesture` recorded

    const g = geometry || { x: 80, y: 80, w: 480, h: 420 };
    dragRef.current = { ... origX: g.x, origY: g.y, ... };

A workspace saved at 2560x1440 with a window at x=1600 y=1000 restores on a
1440x900 laptop drawn at x=532 y=192. Press the title bar and move one pixel
and `onMove` writes `el.style.left = ds.origX + dx` -- 1601 -- so the window
leaps 1068px right and 808px down out from under the cursor, and `onUp`
persists it.

ChatWindow had the same shape with a narrower entrance, which is why it is
worth checking separately: its stored geometry only has to clear
`_chatGeometryStale` (w > VW-12, h > VH-12, x < rail) to be left alone, but
`_chatClamp` additionally caps width at the space beside the rail and y at
VH-h-8. `{x:900, y:700, w:400, h:460}` at 1280x800 with a 232px rail is NOT
stale -- the repair effect deliberately leaves it -- and still renders at
y=332. Grabbing it dropped it 368px.

Fix: one clamp, two callers. `_frameClamp` comes out of WindowFrame's render
as a pure function, the component computes it once above `startGesture`, and
both the render and the gesture origin read that. ChatWindow's `startGesture`
calls the `_chatClamp` its render already used.

This file runs the SHIPPED `startGesture` -- lifted out of each component and
called with stubs -- rather than a re-implementation, because a copy of the
origin logic would agree with itself while the app did something else. That
is the whole bug: two pieces of geometry arithmetic that each looked right.

Run: python3 scripts/test_a_window_does_not_jump_when_you_grab_it.py
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

# WindowFrame: a workspace saved on a 2560x1440 monitor, restored on a laptop.
FRAME_VP = (1440, 900)
FRAME_GEO = {'x': 1600, 'y': 1000, 'w': 900, 'h': 700}
# ChatWindow: a geometry `_chatGeometryStale` deliberately does NOT repair.
CHAT_VP = (1280, 800)
CHAT_RAIL = 232
CHAT_GEO = {'x': 900, 'y': 700, 'w': 400, 'h': 460}


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def _match_braces(src, i):
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return j
    return -1


def lift_fn(src, name):
    """The source of one top-level `function name(...) {...}`, brace-matched."""
    m = re.search(r'^function %s\s*\(' % re.escape(name), src, re.M)
    if not m:
        return None
    i = src.index('{', m.end() - 1)
    j = _match_braces(src, i)
    return src[m.start():j + 1] if j > 0 else None


def _body_open(src, start):
    """Index of the `{` that opens a function body, skipping the destructured
    props in the parameter list (`function WindowFrame({ title, ... })`)."""
    i = src.index('(', start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '(':
            depth += 1
        elif src[j] == ')':
            depth -= 1
            if depth == 0:
                return src.index('{', j)
    return -1


def lift_gesture(src, component):
    """The verbatim `const startGesture = (e, mode) => {...};` belonging to
    one component — the shipped gesture, so this file cannot drift from it."""
    start = src.index('function %s' % component)
    end = _match_braces(src, _body_open(src, start))
    body = src[start:end + 1]
    m = re.search(r'const startGesture = \(e, mode\) => \{', body)
    if not m:
        return None
    j = _match_braces(body, m.end() - 1)
    return body[m.start():j + 1] + ';' if j > 0 else None


def component_body(src, component):
    start = src.index('function %s' % component)
    end = _match_braces(src, _body_open(src, start))
    return src[start:end + 1]


PROBE = '''
const OUT = {};

// ── WindowFrame ──────────────────────────────────────────────────────────
{
  const geo = %(FRAME_GEO)s;
  const vw = %(FVW)d, vh = %(FVH)d;
  const shown = _frameClamp(geo, vw, vh);
  OUT.frameStored = geo;
  OUT.frameShown  = shown;
  const ds = FRAME_DRIVE(vw, vh, geo);
  OUT.frameOrigin = { x: ds.origX, y: ds.origY, w: ds.origW, h: ds.origH };
}

// ── ChatWindow ───────────────────────────────────────────────────────────
{
  const geo = %(CHAT_GEO)s;
  const vw = %(CVW)d, vh = %(CVH)d;
  OUT.chatStored = geo;
  OUT.chatShown  = _chatClamp(geo, vw, vh, %(RAIL)d);
  OUT.chatStale  = _chatGeometryStale(geo, vw, vh, %(RAIL)d);
  const ds = CHAT_DRIVE(vw, vh, geo);
  OUT.chatOrigin = { x: ds.origX, y: ds.origY, w: ds.origW, h: ds.origH };
}

console.log(JSON.stringify(OUT));
'''


def build_driver(name, gesture, preamble):
    """One `NAME_DRIVE(vw, vh, geometry)` around the lifted gesture."""
    return '''
function %s(vw, vh, geometry) {
  globalThis.window = { innerWidth: vw, innerHeight: vh,
                        addEventListener: noop, removeEventListener: noop };
  const dragRef = { current: null };
  const winRef  = { current: null };
  const maximized = false, minW = 320, minH = 240;
  const setGeometry = noop, onToggleMax = null;
  const _workArea = () => ({ x: 8, y: 54, w: vw - 16, h: vh - 140 });
%s
%s
  startGesture({ button: 0, clientX: 500, clientY: 400, preventDefault: noop }, 'move');
  return dragRef.current;
}
''' % (name, preamble, gesture)


def run_probe():
    src = WINDOWS.read_text(encoding='utf-8')
    pieces = []
    for fn in ('_chatGeometryStale', '_chatClamp', '_frameClamp'):
        body = lift_fn(src, fn)
        if body is None:
            return None, 'could not lift %s from app/windows.jsx' % fn
        pieces.append(body)

    frame_g = lift_gesture(src, 'WindowFrame')
    chat_g = lift_gesture(src, 'ChatWindow')
    if not frame_g or not chat_g:
        return None, 'could not lift startGesture from WindowFrame/ChatWindow'

    head = '''
const noop = () => {};
const _CURSORS = {};
const document = { body: { style: {} } };
function _railRight() { return %d; }
''' % CHAT_RAIL

    # WindowFrame's gesture reads `_shown`, which the component computes from
    # `_frameClamp` above it. Recreating that one line here is the only part
    # of the component this file re-types, and check 1 pins it to the render.
    pieces.append(build_driver(
        'FRAME_DRIVE', frame_g,
        '  const _shown = _frameClamp(geometry || { x: 80, y: 80, w: 480, h: 420 }, vw, vh);'))
    pieces.append(build_driver('CHAT_DRIVE', chat_g, '  const isTouch = false;'))

    body = PROBE % {
        'FRAME_GEO': json.dumps(FRAME_GEO),
        'FVW': FRAME_VP[0], 'FVH': FRAME_VP[1],
        'CHAT_GEO': json.dumps(CHAT_GEO), 'CVW': CHAT_VP[0], 'CVH': CHAT_VP[1],
        'RAIL': CHAT_RAIL,
    }

    tmp = ROOT / '.window-jump-probe-tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        (tmp / 'probe.js').write_text(head + '\n\n'.join(pieces) + '\n\n' + body,
                                      encoding='utf-8')
        p = subprocess.run([shutil.which('node') or 'node', str(tmp / 'probe.js')],
                           cwd=ROOT, capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            return None, 'node: ' + p.stderr.strip()[:400]
        return json.loads(p.stdout.strip().splitlines()[-1]), None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    print('a window does not jump when you grab it')
    if not shutil.which('node'):
        print('  SKIP  node not available — cannot run the real gesture')
        return 0

    src = WINDOWS.read_text(encoding='utf-8')

    print('1. one clamp, not a copy per caller')
    check('_frameClamp exists as a pure top-level function',
          lift_fn(src, '_frameClamp') is not None,
          'app/windows.jsx: WindowFrame\'s clamp has to be reachable from '
          'outside the render, or the gesture cannot share it')
    frame = component_body(src, 'WindowFrame')
    check('WindowFrame renders from _frameClamp rather than inline arithmetic',
          '_frameClamp(' in frame and 'let { x, y, w, h } = _shown;' in frame,
          'app/windows.jsx: a second copy of the clamp in the render is the '
          'exact drift this bug was made of')

    r, err = run_probe()
    if r is None:
        print('  FAIL  could not run the gesture: ' + str(err))
        return 1

    print('2. WindowFrame — a workspace restored on a smaller screen')
    st, sh = r['frameStored'], r['frameShown']
    check('the fixture really is a geometry the render moves',
          (sh['x'], sh['y']) == (532, 192) and (st['x'], st['y']) == (1600, 1000),
          f'stored {st} renders at {sh} on {FRAME_VP} — if this has changed, '
          'the checks below are about some other bug')
    og = r['frameOrigin']
    check('the drag starts from where the window is drawn',
          og['x'] == sh['x'] and og['y'] == sh['y'],
          f'startGesture recorded origin {og}, drawn at {sh} — the first '
          f'pixel of the drag would jump it {abs(og["x"] - sh["x"])}px right '
          f'and {abs(og["y"] - sh["y"])}px down, out from under the cursor')
    check('...and from the size it is drawn at',
          og['w'] == sh['w'] and og['h'] == sh['h'],
          f'origin size {og["w"]}x{og["h"]} vs drawn {sh["w"]}x{sh["h"]} — a '
          'resize would snap the window to the stored size first')

    print('3. ChatWindow — a geometry the repair effect deliberately keeps')
    check('the fixture is NOT stale, so nothing repairs it',
          r['chatStale'] is False,
          f'{CHAT_GEO} at {CHAT_VP} rail={CHAT_RAIL} — if the repair took '
          'this one, the clamp would never be the thing on screen')
    cst, csh = r['chatStored'], r['chatShown']
    check('...and the clamp still moves it',
          (csh['x'], csh['y']) != (cst['x'], cst['y']),
          f'stored {cst} renders at {csh} — a fixture the clamp leaves alone '
          'proves nothing')
    cog = r['chatOrigin']
    check('the drag starts from where the window is drawn',
          cog['x'] == csh['x'] and cog['y'] == csh['y'],
          f'startGesture recorded origin {cog}, drawn at {csh} — grabbing the '
          f'title bar dropped the chat {abs(cog["y"] - csh["y"])}px')

    print('4. the gesture reads the clamp, not the store')
    fg = lift_gesture(src, 'WindowFrame')
    cg = lift_gesture(src, 'ChatWindow')
    check('WindowFrame\'s gesture does not re-read the raw geometry',
          'const g = geometry' not in fg,
          'app/windows.jsx: the stored value is where the window WAS asked to '
          'be, not where it is')
    check('ChatWindow\'s gesture clamps before taking its origin',
          '_chatClamp(' in cg and 'const g = geometry;' not in cg,
          'app/windows.jsx: same')

    print()
    if FAILS:
        print(f'window jump: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('window jump: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
