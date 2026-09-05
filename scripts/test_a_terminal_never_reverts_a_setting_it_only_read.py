#!/usr/bin/env python3
"""A view never reverts a setting it only READ — views/core.jsx useStoredV.

Bug: useStoredV writes its value back to localStorage on a 250ms debounce
AND on unmount (the flush added so a project switch mid-stream can't drop
the boss's typing). Both wrote unconditionally — including for a value the
component never changed.

One call site makes that a real revert, not a harmless echo.
views/terminal.jsx:384 reads the GLOBAL key
`cafresohq_terminal:popoutAllowed` through this hook and destructures no
setter at all:

    const [popoutAllowed] = useStoredV('cafresohq_terminal:popoutAllowed', false);

The only writer is Settings → Appearance → Advanced, which writes
localStorage directly (modals/settings.jsx `toggleTerminalPopout`). So:
open the Terminal view, open Settings, switch native terminal pop-outs ON
— the hook is still holding the `false` it read at mount, because nothing
re-reads the key — then leave the Terminal view. The unmount flush writes
that stale `false` straight back. The boss's switch was ON when they left
Settings and OFF the next time they looked, with nothing said anywhere,
and the PTY tab it gates (`ptyTabVisible`) never appeared.

Fix: remember the raw string the hook READ, and whether this component's
setter has been called since. An UNTOUCHED value is persisted only while
the key still holds exactly what was read — so the seed write for a key
nobody else owns survives, and the revert-someone-else's-write does not.
A touched value always writes, so the unmount flush keeps doing its job.

This test extracts the REAL `useStoredV` from views/core.jsx (brace-
balanced) and executes it under Node with the same minimal hooks shim,
fake timers and fake localStorage the sibling suite uses:
  1. the live revert: mount untouched → Settings writes `true` → unmount
     MUST leave `true` on the key (writes `false` without the fix);
  2. the same through the debounce timer instead of the unmount;
  3. a value the component DID change still flushes on unmount;
  4. an untouched value still seeds a key nobody else has touched.
Plus a structural check that the terminal's popout read really is
setter-less, so this stays a test of a live call site.

Run: python3 scripts/test_a_terminal_never_reverts_a_setting_it_only_read.py
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
TERM = ROOT / 'views' / 'terminal.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
POPOUT_KEY = 'cafresohq_terminal:popoutAllowed'
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

/* ---- minimal hooks shim (same as the sibling unmount-flush suite) ---- */
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

const POPOUT = '__POPOUT_KEY__';
const out = {};

/* 1. The live revert. Terminal on screen reading the global popout flag
      with no setter; Settings flips it ON while that view is mounted;
      the boss leaves the Terminal view. The switch must stay ON. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  _store[POPOUT] = 'false';                         // switch starts off
  const root = makeRoot((React) => {
    globalThis.React = React;
    return useStoredV(POPOUT, false);               // note: no setter, ever
  });
  const [seen] = root.render();
  out.readAtMount = seen;
  // Settings -> Appearance -> Advanced (modals/settings.jsx writes it directly)
  _store[POPOUT] = 'true';
  root.unmount();                                   // boss leaves the Terminal view
  out.afterUnmount = _store[POPOUT];
}

/* 2. Same clobber through the debounce timer rather than the unmount —
      a re-render with a new key/value would re-arm it. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  _store[POPOUT] = 'false';
  const root = makeRoot((React) => {
    globalThis.React = React;
    return useStoredV(POPOUT, false);
  });
  root.render();
  _store[POPOUT] = 'true';
  fireAllTimers();
  out.afterTimer = _store[POPOUT];
  root.unmount();
  out.afterTimerAndUnmount = _store[POPOUT];
}

/* 3. A value this component DID change still flushes on unmount — the
      terminal-msgs guarantee the flush exists for must not regress. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  const KEY = 'cafresohq_terminal:msgs:proj-a:s1';
  const root = makeRoot((React) => {
    globalThis.React = React;
    return useStoredV(KEY, []);
  });
  let [v, set] = root.render();
  set([{ role: 'user', content: 'hi' }]);
  [v, set] = root.render();
  root.unmount();
  out.touchedFlush = _store[KEY] || null;
}

/* 3b. …and a touched value wins even when the key moved under it: this
       component owns the edit, so it is not an echo. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  const KEY = 'k3b';
  _store[KEY] = '"a"';
  const root = makeRoot((React) => {
    globalThis.React = React;
    return useStoredV(KEY, 'a');
  });
  const [, set] = root.render();
  set('mine');
  root.render();
  _store[KEY] = '"someone else"';
  root.unmount();
  out.touchedBeatsRace = _store[KEY];
}

/* 4. The untouched SEED write still happens for a key nobody else owns —
      absent key in, default value written out. */
{
  for (const k of Object.keys(_store)) delete _store[k];
  const KEY = 'k4';
  const root = makeRoot((React) => {
    globalThis.React = React;
    return useStoredV(KEY, 'chat');
  });
  root.render();
  fireAllTimers();
  out.seedWrite = _store[KEY] || null;
}

console.log(JSON.stringify(out));
'''


def main():
    src = SRC.read_text(encoding='utf-8')
    fn = extract_function(src, 'useStoredV')
    check('useStoredV extracted from views/core.jsx', bool(fn))

    # The call site this is about must still be setter-less, or the test is
    # guarding a scenario that no longer exists.
    term = TERM.read_text(encoding='utf-8')
    check('views/terminal.jsx still reads the popout flag with no setter',
          bool(re.search(r'const \[\s*popoutAllowed\s*\]\s*=\s*useStoredV\(\s*[\'"]'
                         + re.escape(POPOUT_KEY) + r'[\'"]', term)),
          'popoutAllowed is no longer a setter-less useStoredV read')

    settings = SETTINGS.read_text(encoding='utf-8')
    check('Settings is the other writer of that same key',
          POPOUT_KEY in settings and 'localStorage.setItem(POPOUT_KEY' in settings,
          'modals/settings.jsx no longer writes the popout key directly')

    node = shutil.which('node')
    if not (node and fn):
        print('  skip  live execution (node not on PATH or extraction failed)')
    else:
        script = HARNESS.replace('__USE_STORED_V__', fn).replace('__POPOUT_KEY__', POPOUT_KEY)
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

            check('the hook read the switch as OFF at mount (the stale copy)',
                  out.get('readAtMount') is False, out.get('readAtMount'))
            check('leaving the Terminal view does not switch the setting back off',
                  out.get('afterUnmount') == 'true',
                  'popout key after unmount: %r (the boss set it to true)'
                  % (out.get('afterUnmount'),))
            check('the debounce does not switch the setting back off either',
                  out.get('afterTimer') == 'true', out.get('afterTimer'))
            check('…and neither does the debounce followed by the unmount',
                  out.get('afterTimerAndUnmount') == 'true',
                  out.get('afterTimerAndUnmount'))

            flushed = out.get('touchedFlush')
            parsed = json.loads(flushed) if flushed else None
            check('a value this view DID change still flushes on unmount',
                  isinstance(parsed, list) and len(parsed) == 1
                  and parsed[0].get('content') == 'hi',
                  'localStorage after unmount: %r' % (flushed,))
            check('an edit this view owns is written even if the key moved',
                  out.get('touchedBeatsRace') == '"mine"', out.get('touchedBeatsRace'))
            check('an untouched default still seeds a key nobody else owns',
                  out.get('seedWrite') == '"chat"', out.get('seedWrite'))

    if FAILS:
        print('\nFAILED: ' + ', '.join(FAILS))
        sys.exit(1)
    print('\nall ok')


if __name__ == '__main__':
    main()
