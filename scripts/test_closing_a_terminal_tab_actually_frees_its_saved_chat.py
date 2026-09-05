#!/usr/bin/env python3
""""× End session" has to actually free the tab's saved conversation.

The standalone Terminal (views/misc.jsx TerminalView) and every Projects
terminal share views/terminal.jsx's ProjectTerminal. Its header sells
"× to close tab", and closeSession() ended with a tidy-up block that deleted
the tab's four localStorage keys — cafresohq_terminal:{mode,msgs,model,auth}
— because "msgs can be hundreds of KB after a long conversation".

That delete never survived the render it triggered. closeSession() calls
setSessions(next) first; React then unmounts the closed TerminalSession, and
views/core.jsx's useStoredV has an UNMOUNT FLUSH (added so switching projects
mid-stream can't drop the boss's typing) that writes mode/msgs/model/auth
straight back under the very keys the handler had just removed a moment
earlier. Deterministic, not a race: the handler runs before the commit, the
flush runs during it, and the flush is the last writer.

So closing a terminal tab freed nothing, ever. Every closed tab left its whole
transcript in localStorage under a session uuid nothing can ever reach again,
and localStorage is one shared ~5MB quota for the entire office. Once it
filled, setItem started throwing into useStoredV's and useStored's swallowed
`catch (_e) { /* quota exceeded, etc */ }` — live terminal chats, tasks and
memory quietly stop persisting across reloads, with no error shown anywhere.

Fix: closeSession queues the session id on a ref; a useEffect keyed on
`sessions` does the removal. React flushes a deleted subtree's cleanup before
the surviving tree's effects, so the removal becomes the last word.

Part 1 and 2 drive the REAL useStoredV (lifted from views/core.jsx) under a
tiny React shim in node, to show that ordering — and only ordering — decides
whether the keys survive. Part 3 measures the real ProjectTerminal source.

Run: python3 scripts/test_closing_a_terminal_tab_actually_frees_its_saved_chat.py
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CORE = ROOT / 'views' / 'core.jsx'
TERM = ROOT / 'views' / 'terminal.jsx'

FAILS: list[str] = []


def check(label: str, cond: bool, detail: str = '') -> None:
    print(f'  {"ok  " if cond else "FAIL"}  {label}'
          + (f' — {detail}' if detail and not cond else ''))
    if not cond:
        FAILS.append(label)


def brace_lift(src: str, opener: str) -> str:
    """The whole block starting at `opener`, by balancing braces."""
    i = src.index(opener)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


print('closing a terminal tab actually frees its saved chat')

# ── 1 + 2: the real useStoredV, under a shim, in both orderings ──────────
if not shutil.which('node'):
    print('  SKIP  node not on PATH — running the source checks only')
    R = None
else:
    core = CORE.read_text(encoding='utf-8')
    js = r'''
// Minimal React shim: enough for one component's useState/useRef/useEffect.
function makeReact() {
  const slots = []; let ix = 0; let effects = []; let cleanups = [];
  const runCleanups = () => { while (cleanups.length) { const c = cleanups.pop(); if (c) c(); } };
  const R = {
    useState(init) {
      const i = ix++;
      if (!(i in slots)) slots[i] = [typeof init === 'function' ? init() : init];
      return [slots[i][0], (nv) => { slots[i][0] = typeof nv === 'function' ? nv(slots[i][0]) : nv; }];
    },
    useRef(init) { const i = ix++; if (!(i in slots)) slots[i] = { current: init }; return slots[i]; },
    useEffect(fn, _deps) { effects.push(fn); },
  };
  return {
    R,
    render(fn) {
      runCleanups();          // as React does before re-running an effect
      ix = 0; effects = [];
      const out = fn();
      for (const e of effects) { const c = e(); if (c) cleanups.push(c); }
      return out;
    },
    unmount: runCleanups,
  };
}

// localStorage shim.
const STORE = new Map();
globalThis.localStorage = {
  getItem: k => (STORE.has(k) ? STORE.get(k) : null),
  setItem: (k, v) => { STORE.set(k, String(v)); },
  removeItem: k => { STORE.delete(k); },
};

const KEY = 'cafresohq_terminal:msgs:hq-global-terminal:uuid-1';

function scenario(purgeBeforeUnmount) {
  STORE.clear();
  const host = makeReact();
  globalThis.React = host.R;
  let setMsgs;
  host.render(() => {
    const [msgs, set] = useStoredV(KEY, []);
    setMsgs = set;
    return msgs;
  });
  // A long conversation the boss then closes the tab on.
  setMsgs([{ role: 'user', content: 'x'.repeat(200) }]);
  host.render(() => { const [m, s] = useStoredV(KEY, []); setMsgs = s; return m; });
  if (purgeBeforeUnmount) localStorage.removeItem(KEY);   // the old handler
  host.unmount();                                          // React commits the close
  if (!purgeBeforeUnmount) localStorage.removeItem(KEY);   // the effect, post-commit
  return { left: STORE.has(KEY), bytes: (STORE.get(KEY) || '').length };
}

console.log(JSON.stringify({
  before: scenario(true),
  after: scenario(false),
}));
'''
    js = brace_lift(core, 'function useStoredV(') + '\n' + js
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on useStoredV lifted from views/core.jsx')
    R = json.loads(proc.stdout.strip().split('\n')[-1])

    print('=== the mechanism: who writes last wins ===')
    check('removing the key BEFORE the tab unmounts leaves it in storage',
          R['before']['left'] is True,
          "useStoredV's unmount flush no longer rewrites the key — if that "
          'flush is gone, re-check views/core.jsx before trusting this fix')
    check('...with the whole transcript still in it',
          R['before']['bytes'] > 100, f"{R['before']['bytes']} bytes left behind")
    check('removing it AFTER the unmount flush actually frees it',
          R['after']['left'] is False,
          'even the post-commit ordering left the key — the purge itself is wrong')

# ── 3: the real ProjectTerminal uses the ordering that works ─────────────
print('=== ProjectTerminal purges after the close commits, not before ===')
term = TERM.read_text(encoding='utf-8')
close_src = brace_lift(term, 'const closeSession = (id) =>')


def code_only(src: str) -> str:
    """Comments explain the fix and name what it removed — measure the code."""
    src = re.sub(r'/\*[\s\S]*?\*/', '', src)
    return '\n'.join(l for l in src.split('\n') if not l.strip().startswith('//'))


check('closeSession() no longer deletes the keys inline',
      'localStorage.removeItem' not in code_only(close_src),
      'the handler still removes the keys synchronously — the closed tab\'s '
      'useStoredV unmount flush writes every one of them straight back, so '
      '"× End session" frees nothing and localStorage grows without bound')

check('closeSession() hands the closed session id to the purge queue',
      re.search(r'purgeRef\.current\.push\(', close_src) is not None,
      'nothing records which session was closed for the deferred purge')

# The deferred purge itself: an effect (so React has already flushed the
# deleted subtree's cleanup) that removes all four suffixes.
purge_effect = None
for m in re.finditer(r'React\.useEffect\(\(\) => \{', term):
    body = brace_lift(term[m.start():], 'React.useEffect(() => {')
    if 'localStorage.removeItem' in body and 'purgeRef' in body:
        purge_effect = term[m.start():m.start() + len(body) + 40]
        break

check('a React effect does the removal instead', purge_effect is not None,
      'no useEffect removes the cafresohq_terminal keys — a purge outside the '
      'effect phase runs before the unmount flush and is undone by it')

if purge_effect:
    for suffix in ('mode', 'msgs', 'model', 'auth'):
        check(f"the deferred purge still frees '{suffix}'",
              f"'{suffix}'" in purge_effect,
              f'{suffix} is no longer cleared when a tab is closed')
    check('the purge effect re-runs when the session list changes',
          re.search(r'\}, \[\s*sessions\b', purge_effect) is not None,
          'the effect is not keyed on `sessions`, so closing a tab may never '
          'trigger it')
    check('the purge uses the same key shape closeSession used to',
          'cafresohq_terminal:${suffix}:${pid}:' in purge_effect,
          'the deferred purge builds a different key than useStoredV writes, '
          'so it deletes nothing')

print()
if FAILS:
    print(f'FAILED ({len(FAILS)}): ' + '; '.join(FAILS[:6]))
    sys.exit(1)
print("PASS: closing a terminal tab actually frees its saved chat")
