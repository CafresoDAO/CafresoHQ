#!/usr/bin/env python3
"""Closing the tab within 1.5s of an edit un-did that edit by morning —
app/storage.jsx.

`useFileStored` is how the office persists everything a beta tester makes on
day one: the roster (memory/agents.json), the chat registry, tasks, activity,
projects, meetings. Its `persist()` writes localStorage synchronously and the
mirrored server FILE on a 1500ms debounce.

Nothing flushed that debounce when the page went away. A tab close is not an
unmount — React runs no cleanup — so the pending PUT simply evaporated and
hq-state/<name>.json kept the contents it held BEFORE the boss's last action.

That alone would be survivable, because localStorage still had the edit. It is
not survivable, because of what the mount fetch does next session:

    let untouched = false;
    try { untouched = JSON.stringify(valRef.current) === seedRef.current; } catch (_e) {}
    ...
    const merged = transform ? transform(data) : data;
    setVal(merged);
    localStorage.setItem(lsKey, JSON.stringify(merged));

A freshly reloaded tab has edited nothing, so `untouched` is true and the FILE
wins — and the newer localStorage copy is overwritten with the stale one. The
last thing the boss did is then gone from both halves at once, with no error,
no toast and no log line. Day two opens on day one minus its final act.

The window is not narrow in practice. `messages` re-arms the debounce on every
streamed chunk, so the timer does not even start counting until 1.5s after the
reply stops moving — close the tab on a finished answer and the whole exchange
never reached disk. Same for `activity`, which the agent_runner shim writes on
every vault write.

The fix is the standard one: stamp what the debounce owes (`pendingRef`), and
flush it on `pagehide` / `visibilitychange`-to-hidden with `keepalive: true` so
the browser completes the PUT after the document is gone. It fires only while a
write is genuinely outstanding — `at` is stamped when the 1500ms timer is armed
— so an ordinary tab switch costs nothing, and it deliberately leaves the
timer's own body (the error-reporting path) untouched.

This suite lifts the REAL `_shapeMatches` and `useFileStored` out of
app/storage.jsx and runs them under Node with the same hooks shim, fake timers,
fake localStorage and controllable fetch the sibling useFileStored suites use —
plus a fake `window`/`document` that can actually fire `pagehide`. It plays the
whole two-session story: edit, close the tab WITHOUT firing the debounce, then
mount a second session against the file the first one left behind.

Run: python3 scripts/test_the_last_thing_you_did_before_closing_the_tab_survives_the_night.py
(skips the live-execution check if `node` isn't on PATH — the source-shape
checks still run everywhere)
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


def strip_comments(src):
    """Drop /* ... */ and // ... so an explanatory comment can never satisfy
    (or trip) a source-shape check below."""
    out = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(?m)^\s*//.*$', '', out)


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
const dropAllTimers = () => { _timers.clear(); };   // "the tab went away"

/* ---- fake localStorage (survives a "reload"; only the timers reset) ---- */
const _store = {};
globalThis.localStorage = {
  getItem: (k) => (k in _store ? _store[k] : null),
  setItem: (k, v) => { _store[k] = String(v); },
  removeItem: (k) => { delete _store[k]; },
};

/* ---- the server's copy of the file, and a fetch that speaks to it ---- */
let _file = null;                 // what hq-state/<name>.json holds right now
let _getResolve = null;
let _getPromise = null;
const resetGet = () => { _getPromise = new Promise((res) => { _getResolve = res; }); };
resetGet();
const landTheFetch = () => _getResolve({ ok: true, json: () => Promise.resolve(_file) });
const putCalls = [];
globalThis.fetch = (url, opts) => {
  if (opts && opts.method === 'PUT') {
    putCalls.push({ url, body: JSON.parse(opts.body), keepalive: !!opts.keepalive });
    _file = JSON.parse(opts.body);          // the server really stores it
    return Promise.resolve({ ok: true });
  }
  return _getPromise;
};

/* ---- fake window/document that can actually fire the unload signals ---- */
const _listeners = { window: {}, document: {} };
const _mkTarget = (bag) => ({
  addEventListener: (t, fn) => { (bag[t] = bag[t] || []).push(fn); },
  removeEventListener: (t, fn) => { bag[t] = (bag[t] || []).filter(f => f !== fn); },
});
globalThis.window = Object.assign(_mkTarget(_listeners.window),
  { _API_BASE: '', dispatchEvent: () => {} });
globalThis.document = Object.assign(_mkTarget(_listeners.document),
  { visibilityState: 'visible' });
const firePagehide = () => { for (const fn of (_listeners.window.pagehide || []).slice()) fn(); };
const fireHidden = () => {
  document.visibilityState = 'hidden';
  for (const fn of (_listeners.document.visibilitychange || []).slice()) fn();
  document.visibilityState = 'visible';
};
const clearListeners = () => { _listeners.window = {}; _listeners.document = {};
  Object.assign(globalThis.window, _mkTarget(_listeners.window));
  Object.assign(globalThis.document, _mkTarget(_listeners.document)); };
globalThis.CustomEvent = function (type, opts) { this.type = type; this.detail = opts && opts.detail; };
globalThis.console = { log: console.log, warn: () => {} };

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
  return {
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
}

const useStateA = (...a) => React.useState(...a);
const useEffectA = (...a) => React.useEffect(...a);
const useRefA = (...a) => React.useRef(...a);

__SHAPE_MATCHES__
__USE_FILE_STORED__

const settle = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };

const LS = 'cafresohq_hq_v1:tasks';

/* Session one: mount against whatever the file says, let it hydrate, make one
   edit, then end the session the way `closer` says. */
async function sessionOne(closer) {
  resetGet();
  clearListeners();
  putCalls.length = 0;
  const root = makeRoot((React) => useFileStored(LS, 'state', 'tasks', []));
  root.render();
  landTheFetch();
  await settle();
  const [, setter] = root.render();
  setter(() => [{ id: 't1', title: 'the last thing I did', done: true }]);
  closer();                                  // tab closes / hides / lingers
  await settle();
}

/* Session two: a brand new tab. localStorage persists; timers, listeners and
   the in-memory hooks do not. */
async function sessionTwo() {
  resetGet();
  clearListeners();
  const root = makeRoot((React) => useFileStored(LS, 'state', 'tasks', []));
  root.render();
  landTheFetch();
  await settle();
  fireAllTimers();
  await settle();
  const [val] = root.render();
  return val;
}

async function main() {
  const out = {};

  /* ── 1. The bug: edit, close the tab inside the debounce window ────── */
  _file = [];
  for (const k of Object.keys(_store)) delete _store[k];
  await sessionOne(() => { firePagehide(); dropAllTimers(); });
  out.closePuts = putCalls.length;
  out.closeKeepalive = putCalls.length ? putCalls[putCalls.length - 1].keepalive : null;
  out.fileAfterClose = _file;
  out.day2 = await sessionTwo();
  out.day2Local = JSON.parse(_store[LS] || 'null');

  /* ── 2. Same story, but the tab was only backgrounded ──────────────── */
  _file = [];
  for (const k of Object.keys(_store)) delete _store[k];
  await sessionOne(() => { fireHidden(); dropAllTimers(); });
  out.hiddenFile = _file;

  /* ── 3. Control: an ordinary tab switch with NOTHING outstanding must
         not fire a redundant PUT (13 stores × every tab switch). ─────── */
  _file = [];
  for (const k of Object.keys(_store)) delete _store[k];
  resetGet();
  clearListeners();
  putCalls.length = 0;
  {
    const root = makeRoot((React) => useFileStored(LS, 'state', 'tasks', []));
    root.render();
    landTheFetch();
    await settle();
    const [, setter] = root.render();
    setter(() => [{ id: 't1' }]);
    fireAllTimers();                 // the debounce paid, normally
    await settle();
    const afterDebounce = putCalls.length;
    fireHidden(); firePagehide();    // now switch tabs a couple of times
    await settle();
    out.idlePutsBefore = afterDebounce;
    out.idlePutsAfter = putCalls.length;
  }

  /* ── 4. Control: nothing is flushed for a `sensitive` store (API keys
         have no file half at all, by design). ───────────────────────── */
  for (const k of Object.keys(_store)) delete _store[k];
  resetGet();
  clearListeners();
  putCalls.length = 0;
  {
    const root = makeRoot((React) => useFileStored(
      'cafresohq_hq_v1:secret', 'state', 'secret', {}, null, { sensitive: true }));
    const [, setter] = root.render();
    setter(() => ({ apiKey: 'sk-nope' }));
    firePagehide(); fireHidden();
    await settle();
    out.sensitivePuts = putCalls.length;
  }

  /* ── 5. Control: a pre-hydration edit is still NOT written to the file
         by the unload flush — hydratedRef exists to stop a fresh browser
         PUTting its empty seed over a real office. ──────────────────── */
  for (const k of Object.keys(_store)) delete _store[k];
  resetGet();
  clearListeners();
  putCalls.length = 0;
  {
    const root = makeRoot((React) => useFileStored(LS, 'state', 'tasks', []));
    const [, setter] = root.render();       // fetch deliberately left hanging
    setter(() => [{ id: 'early' }]);
    firePagehide();
    await settle();
    out.preHydrationPuts = putCalls.length;
  }

  console.log(JSON.stringify(out));
}
main();
'''


def main():
    print('the last thing you did before closing the tab is still there tomorrow')

    src = SRC.read_text(encoding='utf-8')
    bare = strip_comments(src)

    shape_matches = extract_function(src, '_shapeMatches')
    use_file_stored = extract_function(src, 'useFileStored')
    check('_shapeMatches extracted from app/storage.jsx', bool(shape_matches))
    check('useFileStored extracted from app/storage.jsx', bool(use_file_stored))

    bare_ufs = strip_comments(use_file_stored or '')

    check('persist() records what the debounce still owes disk, with a stamp',
          bool(re.search(r'pendingRef\.current\s*=\s*\{[^}]*\bat:\s*Date\.now\(\)', bare_ufs)),
          'no pendingRef bookkeeping found next to the 1500ms debounce')
    check('a pagehide listener is registered (the close/navigate signal that '
          'actually fires — `unload` does not on a bfcache-eligible page)',
          "'pagehide'" in bare_ufs)
    check('…and visibilitychange-to-hidden, for the route that never comes back',
          "'visibilitychange'" in bare_ufs and 'hidden' in bare_ufs)
    check('the flush PUT uses keepalive so the browser finishes it after the '
          'document is gone', 'keepalive: true' in bare_ufs)
    check('both listeners are torn down again on cleanup',
          "removeEventListener('pagehide'" in bare_ufs
          and "removeEventListener('visibilitychange'" in bare_ufs)
    check('the debounce timer body is left exactly as it was — it is the '
          'error-reporting path, and this fix is the last-gasp path',
          "if (!r.ok) throw new Error(`HTTP ${r.status}`);" in src
          and "target: 'file'" in src)

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
        check('harness ran clean', r.returncode == 0, (r.stderr or r.stdout).strip()[:800])
        if r.returncode == 0:
            out = json.loads(r.stdout.strip().splitlines()[-1])

            check('THE BUG: closing the tab inside the 1500ms debounce still '
                  'writes the edit to the file',
                  out.get('closePuts') == 1, out.get('closePuts'))
            check('…and that write is a keepalive PUT, so it survives the '
                  'document being torn down',
                  out.get('closeKeepalive') is True, out.get('closeKeepalive'))
            check('the file on disk holds the boss\'s last action',
                  [t.get('id') for t in (out.get('fileAfterClose') or [])] == ['t1'],
                  out.get('fileAfterClose'))
            check('DAY TWO: the office opens holding what day one ended with — '
                  'this is the loss the fix exists to stop',
                  [t.get('id') for t in (out.get('day2') or [])] == ['t1'],
                  out.get('day2'))
            check('…and the stale file never overwrote the newer localStorage '
                  'copy on the way in',
                  [t.get('id') for t in (out.get('day2Local') or [])] == ['t1'],
                  out.get('day2Local'))
            check('a backgrounded tab (visibilitychange → hidden) flushes too',
                  [t.get('id') for t in (out.get('hiddenFile') or [])] == ['t1'],
                  out.get('hiddenFile'))

            check('control: a tab switch with nothing outstanding fires no '
                  'redundant PUT (13 file-backed stores would each pay one)',
                  out.get('idlePutsBefore') == 1 and out.get('idlePutsAfter') == 1,
                  (out.get('idlePutsBefore'), out.get('idlePutsAfter')))
            check('control: a sensitive store is never written to disk, flush '
                  'or no flush', out.get('sensitivePuts') == 0,
                  out.get('sensitivePuts'))
            check('control: a pre-hydration edit is still withheld — hydratedRef '
                  'stops a fresh browser PUTting its empty seed over a real office',
                  out.get('preHydrationPuts') == 0, out.get('preHydrationPuts'))

    if FAILS:
        print('\n%d check(s) failed' % len(FAILS))
        sys.exit(1)
    print('\nall checks passed')


if __name__ == '__main__':
    main()
