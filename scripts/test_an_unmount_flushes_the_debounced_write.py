#!/usr/bin/env python3
"""An unmount flushes the debounced write, never drops it — views/core.jsx.

Bug: useStoredV persists state to localStorage behind a 250ms debounce, and
its effect cleanup — the right thing between renders — was also the last
word on unmount: it cancelled the pending write and nothing ever wrote.
ProjectTerminal remounts on key={project.id} when the boss switches
projects, and a streaming chat calls setMsgs on every chunk (chunks land
well under 250ms apart), so the timer reset continuously and never fired
during a whole reply. Switch projects mid-stream or right after it and the
entire turn — the boss's own message included — vanished from the very
storage whose stated job is "Survives project switches ... without losing
context" (views/terminal.jsx).

Fix: a ref mirrors the latest {key, v, persistTransform}; a mount-only
effect's cleanup flushes that value to localStorage on unmount, after the
debounce effect's own cleanup has cancelled the timer.

This test extracts the REAL `useStoredV` from views/core.jsx (brace-
balanced) and executes it under Node with a minimal hooks shim, fake
timers that never fire, and a fake localStorage:
  1. mount → stream two quick set() calls → unmount before the debounce
     fires → the latest value MUST be in localStorage (drops without fix);
  2. the persistTransform (terminal msgs' slice cap) applies to the
     unmount flush too;
  3. key=null (in-memory only) writes nothing on unmount;
  4. the ordinary debounced write still works when the timer DOES fire.

Run: python3 scripts/test_an_unmount_flushes_the_debounced_write.py
(the live-execution checks are skipped if `node` isn't on PATH — the
source-shape checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'views' / 'core.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_function(src, name):
    """Brace-balanced extraction of `function NAME(...) { ... }`."""
    m = re.search(r'function ' + re.escape(name) + r'\s*\(', src)
    if not m:
        return None
    j = src.find('{', m.end())
    if j == -1:
        return None
    depth = 0
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


HARNESS = r'''
'use strict';
/* ---- fake timers: nothing fires unless the test says so ---- */
const _timers = new Map();
let _tid = 0;
globalThis.setTimeout = (fn, _ms) => { _tid += 1; _timers.set(_tid, fn); return _tid; };
globalThis.clearTimeout = (id) => { _timers.delete(id); };
const fireAllTimers = () => {
  for (const [id, fn] of [..._timers.entries()]) { _timers.delete(id); fn(); }
};

/* ---- fake localStorage ---- */
const _store = {};
globalThis.localStorage = {
  getItem: (k) => (k in _store ? _store[k] : null),
  setItem: (k, v) => { _store[k] = String(v); },
  removeItem: (k) => { delete _store[k]; },
};

/* ---- minimal hooks shim: render / re-render / unmount with effect
        cleanups run in mount order, the way React runs them ---- */
function makeRoot(componentFn) {
  const slots = [];
  let cursor = 0;
  let pendingEffects = [];
  let mounted = true;
  const React = {
    useState(init) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { kind: 'state', v: typeof init === 'function' ? init() : init };
      const slot = slots[i];
      const set = (nv) => { slot.v = typeof nv === 'function' ? nv(slot.v) : nv; };
      return [slot.v, set];
    },
    useRef(init) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { kind: 'ref', current: init };
      return slots[i];
    },
    useEffect(fn, deps) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { kind: 'effect', deps: undefined, cleanup: null };
      pendingEffects.push({ i, fn, deps });
    },
  };
  const depsChanged = (a, b) => {
    if (a === undefined || b === undefined) return true;
    if (a.length !== b.length) return true;
    return a.some((x, k) => !Object.is(x, b[k]));
  };
  const root = {
    result: null,
    render(...args) {
      if (!mounted) throw new Error('render after unmount');
      cursor = 0;
      pendingEffects = [];
      root.result = componentFn(React, ...args);
      for (const e of pendingEffects) {
        const slot = slots[e.i];
        if (!depsChanged(e.deps, slot.deps)) continue;
        if (slot.cleanup) { slot.cleanup(); slot.cleanup = null; }
        const c = e.fn();
        slot.cleanup = typeof c === 'function' ? c : null;
        slot.deps = e.deps;
      }
      return root.result;
    },
    unmount() {
      mounted = false;
      for (const slot of slots) {
        if (slot && slot.kind === 'effect' && slot.cleanup) { slot.cleanup(); slot.cleanup = null; }
      }
    },
  };
  return root;
}

__USE_STORED_V__

const out = {};

/* 1. The terminal-shaped loss: stream sets < 250ms apart, unmount before
      the debounce ever fires. The latest value must survive. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  const KEY = 'cafresohq_terminal:msgs:proj-a:s1';
  const root = makeRoot((React) => {
    const R = React;
    /* useStoredV closes over the module-level `React`; point it at the shim. */
    globalThis.React = R;
    return useStoredV(KEY, []);
  });
  let [v, set] = root.render();
  set([{ role: 'user', content: 'hi' }]);
  [v, set] = root.render();
  set([{ role: 'user', content: 'hi' }, { role: 'assistant', segs: [{ text: 'chunk1', type: 'text' }] }]);
  [v, set] = root.render();
  root.unmount();                       // debounce still pending — never fired
  out.unmountFlushed = _store[KEY] || null;
}

/* 2. persistTransform (the msgs slice cap) applies on the unmount flush. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  const KEY = 'k2';
  const root = makeRoot((React) => {
    globalThis.React = React;
    return useStoredV(KEY, [], (xs) => xs.slice(-2));
  });
  let [v, set] = root.render();
  set([1, 2, 3, 4]);
  root.render();
  root.unmount();
  out.transformOnFlush = _store[KEY] || null;
}

/* 3. key=null is in-memory only: unmount writes nothing. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  const root = makeRoot((React) => {
    globalThis.React = React;
    return useStoredV(null, ['x']);
  });
  const [, set] = root.render();
  set(['x', 'y']);
  root.render();
  root.unmount();
  out.nullKeyWrites = Object.keys(_store).length;
}

/* 4. The ordinary debounced write is untouched: timer fires → written. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  const KEY = 'k4';
  const root = makeRoot((React) => {
    globalThis.React = React;
    return useStoredV(KEY, 'a');
  });
  const [, set] = root.render();
  set('b');
  root.render();
  fireAllTimers();
  out.debouncedWrite = _store[KEY] || null;
}

console.log(JSON.stringify(out));
'''


def main():
    src = SRC.read_text(encoding='utf-8')

    fn = extract_function(src, 'useStoredV')
    check('useStoredV extracted from views/core.jsx', bool(fn))

    # Source shape: a mount-only effect whose cleanup writes localStorage —
    # the unmount flush. Cheap tripwire that runs even without node.
    check('useStoredV carries an unmount flush (mount-only cleanup that setItem-s)',
          bool(fn) and bool(re.search(
              r'useEffect\(\(\)\s*=>\s*\(\)\s*=>\s*\{[\s\S]*?localStorage\.setItem[\s\S]*?\},\s*\[\]\)',
              fn)),
          'no mount-only cleanup writing localStorage found in useStoredV')

    node = shutil.which('node')
    if not (node and fn):
        print('  skip  live execution (node not on PATH or extraction failed)')
    else:
        script = HARNESS.replace('__USE_STORED_V__', fn)
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as f:
            f.write(script)
            path = f.name
        try:
            r = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
        finally:
            Path(path).unlink(missing_ok=True)
        check('harness ran clean', r.returncode == 0, (r.stderr or r.stdout).strip()[:400])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])

            flushed = out.get('unmountFlushed')
            parsed = json.loads(flushed) if flushed else None
            check('unmount before the debounce fires still writes the latest msgs',
                  isinstance(parsed, list) and len(parsed) == 2
                  and parsed[1].get('segs', [{}])[0].get('text') == 'chunk1',
                  'localStorage after unmount: %r' % (flushed,))

            check('persistTransform applies to the unmount flush too',
                  out.get('transformOnFlush') == '[3,4]',
                  out.get('transformOnFlush'))

            check('a null key stays in-memory only (no write on unmount)',
                  out.get('nullKeyWrites') == 0, out.get('nullKeyWrites'))

            check('the ordinary debounced write still lands when the timer fires',
                  out.get('debouncedWrite') == '"b"', out.get('debouncedWrite'))

    if FAILS:
        print('\nFAILED: ' + ', '.join(FAILS))
        sys.exit(1)
    print('\nall ok')


if __name__ == '__main__':
    main()
