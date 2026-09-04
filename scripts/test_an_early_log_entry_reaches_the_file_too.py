#!/usr/bin/env python3
"""The pre-hydration flush skipped the two stores that needed it most —
app/storage.jsx.

#232 found that useFileStored() held a file PUT until the mount fetch
settled (hydratedRef) and then never released it: an edit landing in that
~300ms window reached localStorage and nothing else, so a second browser or
device read the stale file forever. Its fix replays the held write:

    if (dirtyRef.current && !untouched && !mergeOnDirty) persist(valRef.current);
    if (dirtyRef.current && !untouched && !mergeOnDirty) return;

Read the guard, not the intent. `!mergeOnDirty` is on BOTH lines, so the
flush only ever runs on the branch that returns — the plain-snapshot stores
(agents, tasks, memory, pins…). The stores that carry `mergeOnDirty: true`
do not return there. They fall through, union the fetch with what is in
memory (mergeByIdCap / mergeMessages), write state and localStorage, and
reach the end of the handler without persist() being called once. The held
write is still held. Same bug #232 named, on the other half of the fork.

The two stores with the flag are `activity` and `messages` — the office's
activity log and the durable registry of every agent-to-agent handoff, which
app.jsx calls "the system-of-record for every handoff".

And on `activity` the window is not a rare race. app.jsx's own comment says
the agent_runner shim dispatches `cafresohq:agentActivity` on every vault
write, so a fresh office that starts working immediately routinely logs its
first entry before the mount fetch resolves. Trace it:

  1. logActivity() → setter → dirtyRef = true → persist(): localStorage gets
     the entry, the PUT is skipped (`if (!hydratedRef.current) return;`).
  2. The fetch resolves. hydratedRef = true. The value differs from the seed,
     so untouched is false — a REAL edit. mergeOnDirty is true, so neither
     #232 line fires and the handler continues.
  3. mergeByIdCap unions the fetched history with the new entry. setVal and
     localStorage.setItem both take the union. Nothing calls persist().
  4. hq-state/activity.json still holds only what it held before. Close the
     tab and the entry the boss watched land is gone from disk; open the
     office on another device and it was never there. No error, no toast, no
     log line anywhere.

Fix: flush on this path too — `persist(merged)` when the session is dirty
and genuinely edited. `merged` rather than valRef.current because the union
is what state and localStorage now hold, so it is what disk should hold.
Unreachable for every other store, which returned above.

This suite extracts the REAL `_shapeMatches` and `useFileStored` from
app/storage.jsx and runs them under Node with a hooks shim, fake timers that
fire only on demand, a fake localStorage and a controllable fetch (the mount
GET is held open; PUTs are recorded). The mergeOnDirty transform is the real
`mergeByIdCap`, lifted from the same file.

Run: python3 scripts/test_an_early_log_entry_reaches_the_file_too.py
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

    Skips the parameter LIST first: useFileStored's last parameter is a
    destructured object with a default, and a naive "first `{` after the
    name" lands on that destructuring brace instead of the body.
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


def extract_arrow(src, name):
    """Brace-balanced extraction of `const NAME = (...) => { ... };`."""
    m = re.search(r'const ' + re.escape(name) + r'\s*=\s*\(', src)
    if not m:
        return None
    j = src.find('{', src.index('=>', m.start()))
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

/* The real source destructures these aliases at module scope; we don't pull
   in that line, so re-alias them here before splicing the extracted bodies. */
const useStateA = (...a) => React.useState(...a);
const useEffectA = (...a) => React.useEffect(...a);
const useRefA = (...a) => React.useRef(...a);

__SHAPE_MATCHES__
__MERGE_BY_ID_CAP__
__USE_FILE_STORED__

const settle = async () => {
  for (let i = 0; i < 8; i++) await Promise.resolve();
};

async function main() {
  const out = {};

  /* ── The activity log, wired exactly as app.jsx wires it ──────────────
     A fresh office (empty localStorage) whose first vault write logs an
     entry ~200ms in, before the mount fetch resolves. mergeOnDirty:true and
     the real mergeByIdCap as the transform. */
  for (const k of Object.keys(_store)) delete _store[k];
  putCalls.length = 0;
  resetGet();
  {
    const memRef = { current: [] };
    const root = makeRoot((React) => useFileStored(
      'act', 'state', 'activity', [],
      (fetched) => mergeByIdCap(memRef.current, fetched, 200),
      { mergeOnDirty: true }));
    const [, setter] = root.render();

    setter(() => { const v = [{ id: 'new', ts: 500, priority: 'attention' }]; memRef.current = v; return v; });
    out.putsBeforeHydration = putCalls.length;

    _getResolve({ ok: true, json: () => Promise.resolve([{ id: 'old', ts: 100, priority: 'routine' }]) });
    await settle();
    fireAllTimers();
    await settle();

    out.mergedInLocalStorage = (JSON.parse(_store['act'] || '[]')).map(e => e.id).sort();
    out.activityPuts = putCalls.length;
    out.activityPutIds = putCalls.length
      ? putCalls[putCalls.length - 1].body.map(e => e.id).sort() : null;
  }

  /* ── The message registry: same flag, same shape, its own store ─────── */
  for (const k of Object.keys(_store)) delete _store[k];
  putCalls.length = 0;
  resetGet();
  {
    const memRef = { current: [] };
    const root = makeRoot((React) => useFileStored(
      'msg', 'state', 'messages', [],
      (fetched) => {
        const byId = new Map();
        for (const m of (fetched || [])) byId.set(m.id, m);
        for (const m of (memRef.current || [])) byId.set(m.id, m);
        return [...byId.values()];
      },
      { mergeOnDirty: true }));
    const [, setter] = root.render();
    setter(() => { const v = [{ id: 'handoff-1' }]; memRef.current = v; return v; });
    _getResolve({ ok: true, json: () => Promise.resolve([{ id: 'handoff-0' }]) });
    await settle();
    fireAllTimers();
    await settle();
    out.messagePuts = putCalls.length;
    out.messagePutIds = putCalls.length
      ? putCalls[putCalls.length - 1].body.map(m => m.id).sort() : null;
  }

  /* ── Control: mergeOnDirty with NO edit before the fetch ─────────────
     dirtyRef never flips, so the fetch is simply adopted and the fix must
     not invent a write. */
  for (const k of Object.keys(_store)) delete _store[k];
  putCalls.length = 0;
  resetGet();
  {
    const memRef = { current: [] };
    const root = makeRoot((React) => useFileStored(
      'act2', 'state', 'activity2', [],
      (fetched) => mergeByIdCap(memRef.current, fetched, 200),
      { mergeOnDirty: true }));
    root.render();
    _getResolve({ ok: true, json: () => Promise.resolve([{ id: 'old', ts: 100, priority: 'routine' }]) });
    await settle();
    fireAllTimers();
    await settle();
    out.untouchedPuts = putCalls.length;
    out.untouchedAdopted = (JSON.parse(_store['act2'] || '[]')).map(e => e.id);
  }

  /* ── Control: #232's own case still behaves ─────────────────────────
     A plain snapshot store (no mergeOnDirty) keeps its local edit, returns,
     and flushes exactly one PUT carrying the edit — not the fetch. */
  for (const k of Object.keys(_store)) delete _store[k];
  putCalls.length = 0;
  resetGet();
  {
    const root = makeRoot((React) => useFileStored('k1', 'state', 'thing', [], null, {}));
    const [, setter] = root.render();
    setter(() => ['edited']);
    _getResolve({ ok: true, json: () => Promise.resolve(['fromServer']) });
    await settle();
    fireAllTimers();
    await settle();
    out.snapshotPuts = putCalls.length;
    out.snapshotPutBody = putCalls.length ? putCalls[putCalls.length - 1].body : null;
  }

  console.log(JSON.stringify(out));
}
main();
'''


def main():
    src = SRC.read_text(encoding='utf-8')

    shape_matches = extract_function(src, '_shapeMatches')
    use_file_stored = extract_function(src, 'useFileStored')
    merge_by_id_cap = extract_arrow(src, 'mergeByIdCap')
    check('_shapeMatches extracted from app/storage.jsx', bool(shape_matches))
    check('useFileStored extracted from app/storage.jsx', bool(use_file_stored))
    check('mergeByIdCap extracted from app/storage.jsx', bool(merge_by_id_cap))

    check('the merge-and-adopt path flushes the held write too '
          '(persist(merged) after the union is written to state/localStorage)',
          bool(use_file_stored) and bool(re.search(
              r'if\s*\(dirtyRef\.current\s*&&\s*!untouched\)\s*persist\(merged\);',
              use_file_stored)),
          'no unconditional-on-mergeOnDirty flush found on the adopt path')
    check("#232's keep-theirs flush and return survive verbatim "
          '(its own suite string-matches them)',
          'if (dirtyRef.current && !untouched && !mergeOnDirty) persist(valRef.current);' in src
          and 'if (dirtyRef.current && !untouched && !mergeOnDirty) return;' in src)

    node = shutil.which('node')
    if not (node and shape_matches and use_file_stored and merge_by_id_cap):
        print('  skip  live execution (node not on PATH or extraction failed)')
    else:
        script = (HARNESS
                  .replace('__SHAPE_MATCHES__', shape_matches)
                  .replace('__MERGE_BY_ID_CAP__', merge_by_id_cap)
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

            check('the early entry never PUTs before hydration '
                  '(the guard #232 exists to keep)',
                  out.get('putsBeforeHydration') == 0, out.get('putsBeforeHydration'))
            check('the union of file history + the early entry reaches localStorage',
                  out.get('mergedInLocalStorage') == ['new', 'old'],
                  out.get('mergedInLocalStorage'))
            check('THE BUG: the merged activity log reaches the FILE exactly once '
                  '— it never did, so the entry lived only in this browser',
                  out.get('activityPuts') == 1, out.get('activityPuts'))
            check('the flushed PUT carries both the fetched history and the new entry',
                  out.get('activityPutIds') == ['new', 'old'], out.get('activityPutIds'))

            check('the same holds for the message registry '
                  '(the system-of-record for every handoff)',
                  out.get('messagePuts') == 1, out.get('messagePuts'))
            check('the registry PUT carries the union, not just the session entry',
                  out.get('messagePutIds') == ['handoff-0', 'handoff-1'],
                  out.get('messagePutIds'))

            check('control: an untouched mergeOnDirty mount adopts the fetch',
                  out.get('untouchedAdopted') == ['old'], out.get('untouchedAdopted'))
            check('control: adopting an untouched fetch fires no PUT',
                  out.get('untouchedPuts') == 0, out.get('untouchedPuts'))

            check("control: #232's plain-snapshot flush still fires exactly once",
                  out.get('snapshotPuts') == 1, out.get('snapshotPuts'))
            check("control: and still carries the local edit, not the server copy",
                  out.get('snapshotPutBody') == ['edited'], out.get('snapshotPutBody'))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
