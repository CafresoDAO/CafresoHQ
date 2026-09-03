#!/usr/bin/env python3
"""Memory Shelf localStorage key was NOT scoped to the office — app.jsx,
app/storage.jsx.

hq.cafreso.com serves every office (container) from ONE origin, split only
by URL path: `/u/<slug>/hq.html`, with Caddy stripping `/u/<slug>` before
the request reaches that container's own serve.py (see claude-client.jsx's
`_API_BASE` derivation — `window._API_BASE` ends up literally `/u/<slug>`).
Each container's `/hq/memory/context` file is therefore already correctly
isolated per office: different containers, different processes, different
state directories. That part was never broken.

localStorage is scoped by ORIGIN, not path. app/storage.jsx already has a
helper for exactly this mismatch — `ks(n)` — which is `k(n)` plus the
office's slug (parsed out of `_API_BASE`) appended to the key, so a browser
that has opened two different offices doesn't let one bleed into the
other's cache. It is wired up for five onboarding flags (coachSeen,
tourSeen, gettingStartedDone, firstDeliverySeen, cliDismissed in app.jsx)
specifically so, per its own comment, "a NEW user/container shows the
New-User guide, instead of inheriting a 'seen' flag from a prior account in
the same browser."

The Memory Shelf's `useFileStored` call used the OTHER helper, `k('memory')`
— no slug, one shared slot (`cafresohq_hq_v1:memory`) for every office a
browser has ever opened. useFileStored reads that slot as its very first
paint, before the mount-fetch to the (correctly per-office) file has
resolved, so:

  1. Opening Office B after Office A rendered Office A's saved long-term
     memory — the boss's own facts, preferences, rules about a DIFFERENT
     business — as Office B's notes for the first ~100-300ms of every load.
  2. If the boss acts in that window (a REMEMBER click lands before the
     fetch settles), useFileStored's dirty-guard keeps the "genuine edit"
     over the "stale" fetch and its debounced write persists the leaked
     entries into Office B's own memory/context.json — a permanent
     cross-tenant write, not just a rendering glitch.

Fix: `useFileStored(ks('memory'), ...)` instead of `useFileStored(k('memory'), ...)`
in app.jsx — the exact pattern already used for the five onboarding flags.

This test lifts the REAL `k`, `ks` and `STORE_KEY` definitions out of
app/storage.jsx by exact source-anchored extraction (not a line range, not
a hand-copied reimplementation) and runs them under Node with a fake
`window` whose `_API_BASE` changes between two simulated offices, so a
regression that reverts the memory call to `k(...)` — or that accidentally
widens the fix onto some OTHER store's call site — fails this test.

Run: python3 scripts/test_a_second_office_never_inherits_the_first_offices_memory.py
(skips the live-execution checks if `node` isn't on PATH — the source-shape
checks still run everywhere)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORAGE_JSX = ROOT / 'app' / 'storage.jsx'
APP_JSX = ROOT / 'app.jsx'
FAILS = []

# Every OTHER useFileStored-backed collection in app.jsx, keyed by its `k('name')`
# argument. These are documented (in the fix's own comment) as sharing the same
# unscoped-key gap and are deliberately NOT touched by this fix — a Memory Shelf
# fix that quietly rescoped the whole app would be a bigger, unreviewed change.
OTHER_KEYED_STORES = [
    'agents', 'messages', 'openWindows', 'tasks', 'experience',
    'receipts', 'pins', 'missions', 'workflows', 'projects', 'meetings',
]


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_const_statement(src, name):
    """Pull `const <name> = ...;` out of src by balancing (), {}, [] and
    stopping at the first top-level `;` — not by line number. Skips over
    strings/template literals so a stray `;` or bracket inside one doesn't
    end the scan early. (Same helper the messages-registry-merge and
    activity-race tests use.)
    """
    m = re.search(r'const\s+' + re.escape(name) + r'\s*=\s*', src)
    if not m:
        raise AssertionError('const %s = ... not found' % name)
    i = m.end()
    start = m.start()
    depth = 0
    n = len(src)
    in_str = None
    while i < n:
        c = src[i]
        if in_str:
            if c == '\\':
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in '"\'`':
            in_str = c
        elif c in '({[':
            depth += 1
        elif c in ')}]':
            depth -= 1
        elif c == ';' and depth == 0:
            return src[start:i + 1]
        i += 1
    raise AssertionError('unterminated statement for const %s' % name)


def main():
    storage_src = STORAGE_JSX.read_text(encoding='utf-8')
    app_src = APP_JSX.read_text(encoding='utf-8')

    store_key_src = extract_const_statement(storage_src, 'STORE_KEY')
    k_src = extract_const_statement(storage_src, 'k')
    ks_src = extract_const_statement(storage_src, 'ks')

    check('STORE_KEY extracted from app/storage.jsx', "'cafresohq_hq_v1'" in store_key_src)
    check('k extracted from app/storage.jsx', k_src.strip().startswith('const k ='))
    check('ks extracted from app/storage.jsx', ks_src.strip().startswith('const ks ='))

    # --- source-shape / wiring checks (run even without node) ---------------

    check("app.jsx's memory useFileStored call uses ks('memory'), not k('memory')",
          re.search(r"useFileStored\(ks\('memory'\),\s*'memory',\s*'context',\s*SEED_MEMORY\)", app_src) is not None)

    check("k('memory') is no longer wired into memory's useFileStored call",
          re.search(r"useFileStored\(k\('memory'\)", app_src) is None)

    for store in OTHER_KEYED_STORES:
        m = re.search(r"useFileStored\(\s*\n?\s*k\('%s'\)" % re.escape(store), app_src)
        check("scope check: '%s' still uses the unscoped k(...) (untouched by this fix)" % store,
              m is not None, 'expected k(%r) call site not found — did this fix widen or a rename land?' % store)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted k/ks logic)',
          has_node, 'skipping the live-execution checks')

    if not has_node:
        print()
        print(('FAILED: %s' % FAILS) if FAILS else 'source-shape checks passed (node unavailable, live checks skipped)')
        return 1 if FAILS else 0

    harness = """
'use strict';
const window = { _API_BASE: undefined };
%s
%s
%s

const results = [];
function check(name, cond, detail) { results.push([name, !!cond, detail === undefined ? null : detail]); }

// --- Scenario 1: no _API_BASE at all (bare local dev) -> the 'local' slug. -
window._API_BASE = undefined;
check("no _API_BASE -> ks('memory') falls back to the 'local' slug",
  ks('memory') === STORE_KEY + ':memory:local', ks('memory'));

// --- Scenario 2 & 3: two different offices on the SAME origin, distinguished
// only by the /u/<slug> path Caddy would have stripped before this container
// ever saw the request. ------------------------------------------------------
window._API_BASE = '/u/1a2b3c4d5e6f7890';
const ksOfficeA = ks('memory');
window._API_BASE = '/u/9f8e7d6c5b4a3210';
const ksOfficeB = ks('memory');

check("ks('memory') differs between two offices sharing one origin",
  ksOfficeA !== ksOfficeB, [ksOfficeA, ksOfficeB]);
check("ks('memory') embeds Office A's own slug",
  ksOfficeA === STORE_KEY + ':memory:1a2b3c4d5e6f7890', ksOfficeA);
check("ks('memory') embeds Office B's own slug",
  ksOfficeB === STORE_KEY + ':memory:9f8e7d6c5b4a3210', ksOfficeB);

// --- Scenario 4: contrast with the OLD (buggy) k('memory') — proving this
// really is the shared, unscoped slot the leak came from, exactly as
// documented, not a hypothetical. ------------------------------------------
window._API_BASE = '/u/1a2b3c4d5e6f7890';
const kOfficeA = k('memory');
window._API_BASE = '/u/9f8e7d6c5b4a3210';
const kOfficeB = k('memory');
check("THE BUG, contrasted: unscoped k('memory') is IDENTICAL across offices (what ks() fixes)",
  kOfficeA === kOfficeB && kOfficeA === STORE_KEY + ':memory', [kOfficeA, kOfficeB]);

// --- Scenario 5: the actual leak, simulated end to end with one shared fake
// localStorage object (the real mechanism: one browser origin, two offices).
{
  const fakeLocalStorage = {};
  const SEED_MEMORY = [];  // app.jsx's real default when nothing has ever been saved

  // Office A boots first, saves two private long-term memory notes.
  window._API_BASE = '/u/1a2b3c4d5e6f7890';
  const officeAEntries = [
    { id: 'mem_aaaa', tag: 'PEOPLE', text: 'Office A: our biggest client is Acme Corp', date: 1000 },
    { id: 'mem_bbbb', tag: 'RULE', text: 'Office A: never quote a price over email', date: 2000 },
  ];
  fakeLocalStorage[ks('memory')] = JSON.stringify(officeAEntries);

  // Same browser, same origin, now opens a DIFFERENT office. useFileStored's
  // lazy initializer does exactly this: localStorage.getItem(key) ?? initial.
  window._API_BASE = '/u/9f8e7d6c5b4a3210';
  const officeBInitialRaw = fakeLocalStorage[ks('memory')];
  const officeBInitial = officeBInitialRaw == null ? SEED_MEMORY : JSON.parse(officeBInitialRaw);

  check('THE FIX: Office B\\'s first paint does NOT contain Office A\\'s memory entries',
    officeBInitial.length === 0, officeBInitial);
  check('THE FIX: Office B never even sees Office A\\'s client name',
    !JSON.stringify(officeBInitial).includes('Acme Corp'), officeBInitial);

  // Contrast: what the OLD unscoped key would have done in the same scenario.
  const fakeLocalStorageOld = {};
  window._API_BASE = '/u/1a2b3c4d5e6f7890';
  fakeLocalStorageOld[k('memory')] = JSON.stringify(officeAEntries);
  window._API_BASE = '/u/9f8e7d6c5b4a3210';
  const officeBInitialOldRaw = fakeLocalStorageOld[k('memory')];
  const officeBInitialOld = officeBInitialOldRaw == null ? SEED_MEMORY : JSON.parse(officeBInitialOldRaw);
  check('THE BUG, reproduced against the old key: Office B WOULD have inherited Office A\\'s private notes',
    officeBInitialOld.length === 2 && officeBInitialOld.some(m => m.text.includes('Acme Corp')), officeBInitialOld);
}

console.log(JSON.stringify(results));
""" % (store_key_src, k_src, ks_src)

    proc = subprocess.run(['node', '-e', harness], capture_output=True, text=True, cwd=str(ROOT))
    if proc.returncode != 0:
        check('node harness ran without throwing', False, proc.stderr.strip()[-2000:])
        print()
        print('FAILED: %s' % FAILS)
        return 1

    try:
        node_results = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as e:
        check('node harness produced parseable JSON', False, '%s — stdout: %r' % (e, proc.stdout[:2000]))
        print()
        print('FAILED: %s' % FAILS)
        return 1

    for item in node_results:
        name, cond = item[0], item[1]
        detail = item[2] if len(item) > 2 else ''
        check(name, cond, detail)

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'memory-shelf office scoping: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
