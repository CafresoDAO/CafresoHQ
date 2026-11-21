#!/usr/bin/env python3
"""The graph's motion (2026-11-21, Anthony: "do 1-3 ... get to mvp").

1. A rebuild keeps the map where it was. The Library rebuilds the graph after
   every saved note, and each rebuild used to replay the seed ring and up to six
   seconds of layout, so a busy office's map never sat still. Now the engine
   takes the last positions (views/graph.jsx KEPT_LAYOUT) and only newcomers settle.
2. The hover highlight fades (CSS `ease`, 150 ms in, 120 ms out) instead of
   snapping. The colour maths must land exactly on its end colours, so a
   finished fade looks the same as the old instant one.
3. prefers-reduced-motion: no bloom, no fades, no camera flights.

Lifts the REAL helpers out of graph-engine.js and runs them under node.

    python3 scripts/test_the_graph_fades_and_keeps_its_place.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = (ROOT / 'graph-engine.js').read_text(encoding='utf-8')
VIEW = (ROOT / 'views' / 'graph.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def lift(name):
    m = re.search(r'^function %s\([^)]*\) \{' % name, ENGINE, re.M)
    if not m:
        return None
    i, depth = m.end() - 1, 0
    for j in range(i, len(ENGINE)):
        if ENGINE[j] == '{':
            depth += 1
        elif ENGINE[j] == '}':
            depth -= 1
            if depth == 0:
                return ENGINE[m.start():j + 1]
    return None


def main():
    print('the graph fades, and keeps its place')
    parts = {n: lift(n) for n in ('cssEase', 'hslToRgb', 'toRgb', 'mixColor')}
    for n, body in parts.items():
        check(f'{n} lifted from graph-engine.js', body is not None)
    if FAILS:
        print('\n%d FAILED' % len(FAILS))
        return 1
    harness = 'const _rgbCache = new Map();\n' + '\n'.join(parts.values()) + r'''
const out = {
  e0: cssEase(0), e1: cssEase(1), eMid: cssEase(0.5), eQuarter: cssEase(0.25),
  mono: [0.1, 0.2, 0.4, 0.6, 0.8, 0.95].map(cssEase).every((v, i, a) => i === 0 || v >= a[i - 1]),
  hexEnd: mixColor('#9a9a9a', '#353535', 1), hexStart: mixColor('#9a9a9a', '#353535', 0),
  hexHalf: mixColor('#000000', '#ffffff', 0.5),
  hsl: toRgb('hsl(0, 100%, 50%)'),
  rgb: toRgb('rgb(10, 20, 30)'),
  odd: mixColor('red', 'blue', 0.7),
};
console.log(JSON.stringify(out));
'''
    res = subprocess.run(['node', '-e', harness], capture_output=True, text=True, timeout=30)
    check('the helpers run under node', res.returncode == 0, res.stderr.strip()[:300])
    if res.returncode != 0:
        print('\n%d FAILED' % len(FAILS))
        return 1
    o = json.loads(res.stdout.strip().splitlines()[-1])
    check('ease starts at 0 and ends at 1', o['e0'] == 0 and o['e1'] == 1, o)
    check('ease is front-loaded like CSS `ease` (0.5 → ~0.80)', abs(o['eMid'] - 0.8024) < 0.01, o['eMid'])
    check('ease never runs backwards', o['mono'], o)
    check('a finished fade lands exactly on the end colour', o['hexEnd'] == '#353535', o['hexEnd'])
    check('an unstarted fade is the start colour, untouched', o['hexStart'] == '#9a9a9a', o['hexStart'])
    check('halfway is halfway', o['hexHalf'] in ('rgb(128,128,128)', 'rgb(127,127,127)'), o['hexHalf'])
    check('hsl() colours (folder mode) can be mixed', [round(v) for v in o['hsl']] == [255, 0, 0], o['hsl'])
    check('rgb() colours can be mixed', o['rgb'] == [10, 20, 30], o['rgb'])
    check('a colour it cannot read switches at the midpoint instead of breaking', o['odd'] == 'blue', o['odd'])

    # ── 1. a rebuild keeps the map ──────────────────────────────────────
    check('the view hands the last layout to the next mount',
          'positions: kept && kept.positions, camera: kept && kept.camera' in VIEW)
    check('...remembered before the old engine is destroyed',
          VIEW.index('rememberLayout(engineRef.current);') < VIEW.index("engineRef.current && engineRef.current.destroy()"))
    check('...and per source, so a concept map never inherits link positions',
          'KEPT_LAYOUT[sourceRef.current]' in VIEW and 'eng.__source = sourceRef.current' in VIEW)
    check('the engine places kept nodes and only settles newcomers',
          '_placeFrom(positions)' in ENGINE and "this._mode === 'settle' && this._newCount" in ENGINE)
    check('the opening bloom plays once per page load',
          'bloomedThisSession = true' in ENGINE and '!bloomedThisSession' in ENGINE)
    check('the open note only moves the camera when it is out of view',
          "this._moveCamera(path, {}, false)" in ENGINE and 'framedGraphToViewport' in ENGINE)

    # ── 2. hover fades ──────────────────────────────────────────────────
    check('hover fades in over 150 ms and out over 120 ms',
          'const FADE_IN_MS = 150;' in ENGINE and 'const FADE_OUT_MS = 120;' in ENGINE)
    check('enter, leave, click and stage-click all go through the fade',
          ENGINE.count('this._focusChanged();') >= 5, ENGINE.count('this._focusChanged();'))

    # ── 3. reduced motion ───────────────────────────────────────────────
    check('reduced motion is read from the OS setting',
          "matchMedia('(prefers-reduced-motion: reduce)')" in ENGINE)
    check('...and it skips the bloom', "!bloomedThisSession && !this._reduced ? 'bloom' : 'static'" in ENGINE)
    check('...the fades', 'fx.dur = this._reduced ? 0 : ms' in ENGINE)
    check('...and the camera flights', 'if (this._reduced) cam.setState(to);' in ENGINE)

    print()
    print(('%d FAILED: %s' % (len(FAILS), FAILS)) if FAILS else 'graph motion: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
