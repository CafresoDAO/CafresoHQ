#!/usr/bin/env python3
"""Raising a window must put it on TOP of a hydrated stack (app.jsx winZRef).

Bug: the desktop window manager hands out z-order from a monotonic counter
(`winZRef`), and synced that counter to the persisted windows' max z in a
ONCE-ONLY effect (`}, [])`). But `openWindows` is file-backed (useFileStored):
in a fresh browser context it seeds `[]` and the real list only arrives when
the mount fetch settles — after the once-only effect has already run against
the empty seed. (applyWorkspace replaces the list wholesale the same way.)
The counter then sat at 1 under a stack persisted at z=5,6,7…, so every
`winZRef.current + 1` was a z BELOW the whole pile: clicking a window to
raise it sent it to the BACK instead, a freshly launched app opened behind
the stack, and `focused` (the Esc target, the highlight) stayed on a window
the boss wasn't looking at — one click per unit of deficit until the counter
ground past the file's max z.

Fix: the sync effect re-runs whenever the LIST is replaced (`[openWindows]`
deps), so the counter is caught up before the boss can click anything.

This lifts the REAL snippets out of app.jsx — the winZRef declaration + sync
effect (paren-balanced), and the focusWindow callback — and replays the exact
hydration sequence under node with a mini hook runtime that honours React's
deps semantics (an effect re-runs only when a dep changes identity). No
reimplementation of the arithmetic: the shipped effect body, the shipped
deps array and the shipped focusWindow decide the outcome.
Run: python3 scripts/test_a_click_on_a_window_never_sends_it_to_the_back.py
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def balanced_span(src, start, opener='(', closer=')'):
    """Return the end index just past the span that balances src[start]."""
    depth = 0
    j = start
    while j < len(src):
        c = src[j]
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return None


def extract_zref_and_effect(text):
    """`const winZRef = useRefA(1);` through the sync effect's `);` —
    paren-balanced from `React.useEffect(` so the deps array ships too."""
    decl = re.search(r'const winZRef = useRefA\(1\);', text)
    if not decl:
        return None
    eff = re.search(r'React\.useEffect\(', text[decl.end():])
    if not eff:
        return None
    open_paren = decl.end() + eff.end() - 1
    end = balanced_span(text, open_paren)
    if end is None:
        return None
    # include the trailing ';'
    if end < len(text) and text[end] == ';':
        end += 1
    return text[decl.start():end]


def extract_focus_window(text):
    """`const focusWindow = useCallbackA(` … paren-balanced … `);`"""
    m = re.search(r'const focusWindow = useCallbackA\(', text)
    if not m:
        return None
    end = balanced_span(text, m.end() - 1)
    if end is None:
        return None
    if end < len(text) and text[end] == ';':
        end += 1
    return text[m.start():end]


HARNESS = r'''
'use strict';
// ── Mini hook runtime — honest React deps semantics ─────────────────────
// refs live in slots so they survive re-renders; effects are collected per
// render and flushed with an Object.is elementwise deps comparison, so a
// `[]`-deps effect runs exactly once and a `[openWindows]` effect re-runs
// when the list is replaced. This is the semantics the fix leans on.
const _slots = [];
let _cursor = 0;
let _effects = [];
const _prevDeps = [];
function useRefA(init) {
  const i = _cursor++;
  if (!(i in _slots)) _slots[i] = { current: init };
  return _slots[i];
}
const React = { useEffect: (cb, deps) => { _effects.push([cb, deps]); } };
const useCallbackA = (fn) => fn;

let state = { openWindows: [] };
const setOpenWindows = (u) =>
  { state.openWindows = typeof u === 'function' ? u(state.openWindows) : u; };

function render() {
  _cursor = 0; _effects = [];
  const openWindows = state.openWindows;
  // ── REAL app.jsx source, lifted verbatim ──
__ZREF_AND_EFFECT__
__FOCUS_WINDOW__
  // ── flush effects (React deps rules) ──
  _effects.forEach(([cb, deps], i) => {
    const prev = _prevDeps[i];
    const changed = prev === undefined || !deps || deps.length !== prev.length
      || deps.some((d, j) => !Object.is(d, prev[j]));
    _prevDeps[i] = deps;
    if (changed) cb();
  });
  return { focusWindow, winZRef };
}

// 1. Fresh browser context: the mirror is empty, openWindows seeds [].
render();
// 2. The mount fetch settles and adopts the persisted file — three windows,
//    z handed out by a previous session's counter.
state.openWindows = [
  { view: 'tasks',  z: 5, minimized: false },
  { view: 'memory', z: 6, minimized: false },
  { view: 'team',   z: 7, minimized: false },
];
const api = render();
// 3. The boss clicks the BOTTOM window to bring it forward.
api.focusWindow('tasks');
const z = {};
for (const w of state.openWindows) z[w.view] = w.z;
const raised = z.tasks > z.memory && z.tasks > z.team;
console.log(JSON.stringify({ z, raised, counter: api.winZRef.current }));
'''


def main():
    print('window manager — a click raises a hydrated window, never buries it')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    zref = extract_zref_and_effect(text)
    check('winZRef declaration + sync effect extracted from app.jsx',
          zref is not None)
    focus = extract_focus_window(text)
    check('focusWindow extracted from app.jsx', focus is not None)
    if zref is None or focus is None:
        print('\nFAILED: %s' % FAILS)
        return 1

    # The counter must be the thing focusWindow spends — otherwise this
    # harness would be exercising something the click path never touches.
    check('focusWindow hands out z from winZRef', 'winZRef' in focus)

    js = HARNESS.replace('__ZREF_AND_EFFECT__', zref) \
                .replace('__FOCUS_WINDOW__', focus)
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                     encoding='utf-8') as f:
        f.write(js)
        path = f.name
    try:
        run = subprocess.run(['node', path], capture_output=True, text=True,
                             timeout=30)
    finally:
        Path(path).unlink(missing_ok=True)
    check('node ran the lifted source', run.returncode == 0,
          (run.stderr or '').strip()[:200])
    if run.returncode != 0:
        print('\nFAILED: %s' % FAILS)
        return 1

    out = json.loads(run.stdout.strip().splitlines()[-1])
    check('counter caught up to the hydrated stack (>= 7)',
          out['counter'] >= 7, f'counter={out["counter"]}')
    check('clicking the bottom window put it on TOP of the stack',
          out['raised'], f'z after click: {out["z"]}')

    print()
    print(('FAILED: %s' % FAILS) if FAILS
          else 'window raise after hydration: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
