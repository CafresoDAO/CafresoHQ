#!/usr/bin/env python3
"""useFileStored() dropped a pre-hydration edit on the floor forever —
app/storage.jsx.

useFileStored backs nearly every durable entity in the app (agents, tasks,
messages, activity, memory/context, receipts, pins, windows, missions,
workflows, meetings, projects…). Its mount effect fetches the on-disk file
async, ~100-300ms after first render, and `hydratedRef` exists specifically
to hold the file PUT until that fetch settles — the block comment right
above it (persist()) narrates the exact wipe this guards against: writing an
empty boot-time seed over a real file before the fetch has even had a
chance to say otherwise.

But the guard only holds the write — it never releases it. Trace a genuine
edit that lands in that same pre-hydration window (the same window app.jsx's
own `memory` comment names by example: "a REMEMBER click that lands before
the fetch settles"):

  1. setter() fires. dirtyRef flips true. persist(next) runs: localStorage
     is written immediately (the UI looks fine), but the file PUT is
     skipped — `if (!hydratedRef.current) return;` — because hydratedRef
     is still false.
  2. The mount fetch resolves moments later. hydratedRef flips true.
     dirtyRef.current is true and the value differs from the seed (a REAL
     edit, not a boot-time echo), so the dirty-guard fires and the effect
     returns immediately to keep the local edit as authoritative in
     memory/localStorage.
  3. Nothing in that return path ever calls persist() again. The held
     write from step 1 is never replayed. If nothing else touches this
     store for the rest of the session, the edit lives in localStorage
     ONLY — the on-disk file never receives it. A different browser,
     device, or a fresh container mount-fetch on this same one all read
     the stale file forever, and there is no error, toast, or log anywhere
     to say so.

Fix: when the dirty-guard decides to keep the local edit over the fetch,
flush it — `persist(valRef.current)` — before returning. hydratedRef is
already true at that point, so this persist() call actually reaches the
debounced disk PUT this time instead of bailing again.

This test extracts the REAL `_shapeMatches` and `useFileStored` functions
from app/storage.jsx (brace-balanced, handles the destructured-object
default parameter) and executes them under Node with a minimal hooks shim
(useState/useRef/useEffect/useCallback), fake timers that only fire on
demand, a fake localStorage, and a controllable fake `fetch` (the mount GET
is held open until the test resolves it; PUT calls are recorded).

Run: python3 scripts/test_pre_hydration_edit_reaches_the_file.py
(skips the live-execution check if `node` isn't on PATH — the source-shape
check still runs everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'storage.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_function(src, name):
    """Brace-balanced extraction of `function NAME(...) { ... }`.

    Must skip past the parameter LIST first — useFileStored's last
    parameter is a destructured object with a default (`{ sensitive =
    false, ... } = {}`), and a naive "first `{` after the name" search
    lands on that destructuring brace instead of the function body.
    """
    m = re.search(r'function ' + re.escape(name) + r'\s*\(', src)
    if not m:
        return None
    p = src.index('(', m.start())
    depth = 0
    while p < len(src):
        if src[p] == '(':
            depth += 1
        elif src[p] == ')':
            depth -= 1
            if depth == 0:
                p += 1
                break
        p += 1
    j = src.find('{', p)
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

/* ---- fake window / fetch: the mount GET is held open; PUTs are recorded ---- */
let _getResolve = null;
let _getPromise = null;
const resetGet = () => { _getPromise = new Promise((res) => { _getResolve = res; }); };
resetGet();
const putCalls = [];
globalThis.fetch = (url, opts) => {
  if (opts && opts.method === 'PUT') {
    putCalls.push({ url, body: JSON.parse(opts.body) });
    return Promise.resolve({ ok: true });
  }
  return _getPromise;
};
globalThis.window = { _API_BASE: '', dispatchEvent: () => {} };
globalThis.CustomEvent = function (type, opts) { this.type = type; this.detail = opts && opts.detail; };

/* ---- minimal hooks shim ---- */
function makeRoot(componentFn) {
  const slots = [];
  let cursor = 0;
  let pendingEffects = [];
  const depsChanged = (a, b) => {
    if (a === undefined || b === undefined) return true;
    if (a.length !== b.length) return true;
    return a.some((x, k) => !Object.is(x, b[k]));
  };
  const HooksReact = {
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
    useCallback(fn, deps) {
      const i = cursor++;
      if (!(i in slots)) slots[i] = { kind: 'cb', fn, deps: undefined };
      const slot = slots[i];
      if (depsChanged(deps, slot.deps)) { slot.fn = fn; slot.deps = deps; }
      return slot.fn;
    },
  };
  const root = {
    render(...args) {
      cursor = 0;
      pendingEffects = [];
      globalThis.React = HooksReact;
      const result = componentFn(HooksReact, ...args);
      for (const e of pendingEffects) {
        const slot = slots[e.i];
        if (!depsChanged(e.deps, slot.deps)) continue;
        if (slot.cleanup) { slot.cleanup(); slot.cleanup = null; }
        const c = e.fn();
        slot.cleanup = typeof c === 'function' ? c : null;
        slot.deps = e.deps;
      }
      return result;
    },
  };
  return root;
}

/* useFileStored's real source destructures useStateA/useEffectA/useRefA at
   module scope (aliases for React.useState/useEffect/useRef). We don't pull
   in that top-of-module line, so alias them here the same way before
   splicing in the extracted body. `React.useCallback` is called directly
   in the real source (not aliased), which our shim's global `React` (reset
   every render() call above) already satisfies. */
const useStateA = (...a) => React.useState(...a);
const useEffectA = (...a) => React.useEffect(...a);
const useRefA = (...a) => React.useRef(...a);

__SHAPE_MATCHES__
__USE_FILE_STORED__

async function main() {
  const out = {};

  /* Genuine edit lands BEFORE the mount fetch resolves — persist() must
     bail on the PUT at that instant (hydratedRef still false). Then the
     fetch resolves with DIFFERENT server data; the dirty-guard decides to
     keep the local edit. The edit must still reach the file exactly once. */
  for (const k of Object.keys(_store)) delete _store[k];
  putCalls.length = 0;
  resetGet();
  {
    const root = makeRoot((React) => useFileStored('k1', 'state', 'thing', [], null, {}));
    const [, setter] = root.render();
    setter(() => ['edited']);
    out.localStorageRightAfterEdit = _store['k1'] || null;
    out.putsBeforeHydration = putCalls.length;

    _getResolve({ ok: true, json: () => Promise.resolve(['fromServer']) });
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    fireAllTimers();
    await Promise.resolve(); await Promise.resolve();

    out.putsAfterHydrationSettles = putCalls.length;
    out.lastPutBody = putCalls.length ? putCalls[putCalls.length - 1].body : null;
  }

  /* Control: no edit at all before hydration (dirtyRef stays false) — the
     fetched file must simply be adopted, no spurious PUT. Confirms the fix
     doesn't turn every mount into a needless write. */
  for (const k of Object.keys(_store)) delete _store[k];
  putCalls.length = 0;
  resetGet();
  {
    const root = makeRoot((React) => useFileStored('k2', 'state', 'thing2', [], null, {}));
    root.render();
    _getResolve({ ok: true, json: () => Promise.resolve(['fromServer2']) });
    await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
    fireAllTimers();
    await Promise.resolve(); await Promise.resolve();
    out.untouchedAdoptsFetch = _store['k2'] || null;
    out.untouchedPuts = putCalls.length;
  }

  console.log(JSON.stringify(out));
}
main();
'''


def main():
    src = SRC.read_text(encoding='utf-8')

    shape_matches = extract_function(src, '_shapeMatches')
    use_file_stored = extract_function(src, 'useFileStored')
    check('_shapeMatches extracted from app/storage.jsx', bool(shape_matches))
    check('useFileStored extracted from app/storage.jsx', bool(use_file_stored))

    check('the dirty-guard flushes the held write '
          '(persist(valRef.current)) before the pre-existing keep-theirs return',
          bool(use_file_stored) and bool(re.search(
              r'if\s*\(dirtyRef\.current\s*&&\s*!untouched\s*&&\s*!mergeOnDirty\)\s*persist\(valRef\.current\);'
              r'\s*\n\s*if\s*\(dirtyRef\.current\s*&&\s*!untouched\s*&&\s*!mergeOnDirty\)\s*return;',
              use_file_stored)),
          'no persist(valRef.current) found guarding the same condition just before the return')
    check('the original dirty-guard return line is untouched, verbatim '
          '(other suites — #177\'s messages/activity coverage — string-match '
          'this exact line; it must survive alongside the new flush)',
          'if (dirtyRef.current && !untouched && !mergeOnDirty) return;' in src)

    node = shutil.which('node')
    if not (node and shape_matches and use_file_stored):
        print('  skip  live execution (node not on PATH or extraction failed)')
    else:
        script = (HARNESS
                  .replace('__SHAPE_MATCHES__', shape_matches)
                  .replace('__USE_FILE_STORED__', use_file_stored))
        with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                         encoding='utf-8') as f:
            f.write(script)
            path = f.name
        try:
            r = subprocess.run([node, path], capture_output=True, text=True, timeout=60)
        finally:
            Path(path).unlink(missing_ok=True)
        check('harness ran clean', r.returncode == 0, (r.stderr or r.stdout).strip()[:600])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])

            check('the edit lands in localStorage immediately (UI looks fine)',
                  out.get('localStorageRightAfterEdit') == '["edited"]',
                  out.get('localStorageRightAfterEdit'))
            check('no file PUT is attempted before hydration settles '
                  '(the original guard against wiping the file with a boot seed)',
                  out.get('putsBeforeHydration') == 0, out.get('putsBeforeHydration'))
            check('the pre-hydration edit reaches the file exactly once '
                  'after the fetch settles and confirms it as a real edit — '
                  'this is the bug: it never did before the fix',
                  out.get('putsAfterHydrationSettles') == 1,
                  out.get('putsAfterHydrationSettles'))
            check('the flushed PUT carries the edited value, not the stale seed',
                  out.get('lastPutBody') == ['edited'], out.get('lastPutBody'))

            check('control: an untouched mount adopts the fetched file',
                  out.get('untouchedAdoptsFetch') == '["fromServer2"]',
                  out.get('untouchedAdoptsFetch'))
            check('control: adopting an untouched fetch fires no extra PUT',
                  out.get('untouchedPuts') == 0, out.get('untouchedPuts'))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
