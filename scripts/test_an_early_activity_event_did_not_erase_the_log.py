#!/usr/bin/env python3
"""useFileStored's mount-fetch race — the OTHER branch, still open after the
messages-registry fix (app/storage.jsx, app.jsx).

The mount effect that hydrates a useFileStored value from disk has always
had a "local edits win" guard:

    if (dirtyRef.current && !untouched) return;   // a real edit — keep theirs

That is the right call for a plain snapshot (tasks, agents, memory, ...): a
fetched file is a whole document, there's no way to reconcile it against a
live edit, so discarding it and keeping the in-memory copy is the safe
choice. `activity` and `messages` are not documents, they're LOGS, and both
were given merge-by-id transforms (mergeByIdCap, mergeMessages) that read the
CURRENT in-memory ref themselves and union it with the fetch — exactly what
the "keep theirs" guard was supposed to make unnecessary.

Except the guard runs BEFORE the transform is ever called. `return` exits
the whole `.then(data => { ... })` callback, so the instant dirtyRef flips
true (any setActivity call before the mount fetch resolves) and the value
has genuinely changed, `transform` — mergeByIdCap and all — never executes.
The fetched history isn't merged AND discarded by mergeByIdCap's own logic;
it's discarded by the hook before mergeByIdCap is ever asked.

Measured live (2026-09-03, PORT=48321 python3 serve.py):
  1. Seeded /hq/state/activity with three historical entries (act_hist1..3),
     one of them an unread ATTENTION row ("hit a snag on the report").
  2. Loaded the app fresh (cleared localStorage) with the activity GET
     artificially delayed ~9s (test-only fetch monkeypatch, removed before
     commit) to widen the window without changing any real code.
  3. ~200ms in, dispatched `cafresohq:agentActivity` — the same event
     agent_runner fires on every vault write, not a rare boot corner case —
     which calls logActivity -> setActivity, flipping dirtyRef true.
  4. Confirmed in-flight state held only the one new entry (dirty, as
     expected) while the fetch was still pending.
  5. Once the delayed fetch resolved: state STAYED at one entry. The three
     historical entries, including the unread attention row, never
     appeared — not in `activity`, not in the bell, not in the AgentInbox.
  6. A second activity event triggered the debounced disk write, which then
     overwrote hq-state/activity.json, permanently erasing the three
     historical entries — the coworker's unresolved failure gone from disk
     with no error anywhere.

Fix: `useFileStored` gained an opt-in `mergeOnDirty` option. When set, the
mount-fetch guard no longer returns early on a real edit — it still calls
`transform`, trusting a log-shaped transform to reconcile the two sides
itself (which mergeByIdCap and mergeMessages already do). `activity`'s
useFileStored call in app.jsx now passes `{ mergeOnDirty: true }`; every
other useFileStored consumer (tasks, agents, memory, workflows, meetings,
projects, receipts, pins, windows, messages...) is untouched and keeps the
exact "keep theirs" behavior it had before — this test asserts that too, not
just the activity fix, since a flag that silently changed everyone's
behavior would be a worse bug than the one it closes.

This test lifts the REAL mount-fetch callback body and the REAL
mergeByIdCap out of app/storage.jsx by exact source-anchored extraction (not
a line range, not a hand-copied reimplementation) and executes them for
real under Node, so a regression that removes the `mergeOnDirty` escape
hatch — or that flips it on for everyone — fails this test.

Run: python3 scripts/test_an_early_activity_event_did_not_erase_the_log.py
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


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_const_statement(src, name):
    """Pull `const <name> = ...;` out of src by balancing (), {}, [] and
    stopping at the first top-level `;` — not by line number. Skips over
    strings/template literals so a stray `;` or bracket inside one doesn't
    end the scan early. (Same helper the messages-registry-merge test uses.)
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


def extract_mount_fetch_effect_body(src):
    """Pull the body of useFileStored's mount-fetch `.then(data => { ... })`
    callback — the exact code that decides whether a dirty session adopts,
    merges, or discards the fetched file. Anchored on the two lines that
    bracket it (both verified unique in the file below), not a line range."""
    m = re.search(
        r"\.then\(data => \{\n(.*?)\n      \}\)\n      /\* Unreachable server",
        src, re.S)
    if not m:
        raise AssertionError('mount-fetch .then(data => {...}) body not found')
    return m.group(1)


def main():
    storage_src = STORAGE_JSX.read_text(encoding='utf-8')
    app_src = APP_JSX.read_text(encoding='utf-8')

    merge_src = extract_const_statement(storage_src, 'mergeByIdCap')
    check('mergeByIdCap extracted from app/storage.jsx', 'mergeByIdCap' in merge_src)

    effect_body = extract_mount_fetch_effect_body(storage_src)
    check('mount-fetch effect body extracted from app/storage.jsx',
          'transform ? transform(data) : data' in effect_body)

    # --- source-shape checks -------------------------------------------------

    check("useFileStored's options destructure a mergeOnDirty flag (default false)",
          re.search(r"function useFileStored\([^)]*\{\s*sensitive = false,\s*persistTransform = null,\s*mergeOnDirty = false\s*\}\s*=\s*\{\}\)", storage_src) is not None,
          'signature not found or mergeOnDirty missing/misdefaulted')

    check('the dirty-edit guard is gated by !mergeOnDirty, not removed outright',
          'if (dirtyRef.current && !untouched && !mergeOnDirty) return;' in storage_src)

    wiring_m = re.search(
        r"useFileStored\(\s*\n\s*k\('activity'\)[^;]*mergeByIdCap\(activityRef\.current,\s*fetched,\s*200\)[^;]*\{\s*mergeOnDirty:\s*true\s*\}\)",
        app_src)
    check("app.jsx wires { mergeOnDirty: true } into activity's useFileStored call",
          wiring_m is not None)

    # messages must NOT have picked up mergeOnDirty as a side effect of this
    # fix — it stays scoped to activity alone (messages' own race, if any,
    # is a separate, already-claimed area).
    messages_call_m = re.search(r"useFileStored\(k\('messages'\)[^;]*mergeMessages\(messagesRef\.current,\s*fetched\)\);", app_src)
    check("messages' useFileStored call is untouched by this fix (no mergeOnDirty)",
          messages_call_m is not None and 'mergeOnDirty' not in messages_call_m.group(0))

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted hook logic)',
          has_node, 'skipping the live-execution checks')

    if not has_node:
        print()
        print(('FAILED: %s' % FAILS) if FAILS else 'source-shape checks passed (node unavailable, live checks skipped)')
        return 1 if FAILS else 0

    harness = """
'use strict';
__MERGE_BY_ID_CAP__

const results = [];
function check(name, cond, detail) { results.push([name, !!cond, detail === undefined ? null : detail]); }

// Re-creates the exact local scope the extracted `.then(data => {...})`
// body runs in, then executes that body verbatim inside an IIFE (a bare
// `return;` in the extracted source exits the IIFE, exactly as it exits
// the real .then() callback).
function runEffect(opts) {
  const hydratedRef = { current: false };
  const dirtyRef = { current: !!opts.dirty };
  const valRef = { current: opts.initialVal };
  const seedRef = { current: opts.seed };
  const mergeOnDirty = !!opts.mergeOnDirty;
  const transform = opts.transform;
  const persistTransform = opts.persistTransform || null;
  const setValCalls = [];
  const setVal = (v) => { setValCalls.push(v); };
  const localStorage = { setItem: () => {} };
  const lsKey = 'test-key';
  const persist = () => {};
  const data = opts.data;

  (function () {
__EFFECT_BODY__
  })();

  return { hydrated: hydratedRef.current, setValCalls, finalVal: valRef.current };
}

// --- Scenario A: the bug as measured — dirty real edit, log-shaped
// transform, mergeOnDirty NOT set (the pre-fix default everywhere). ------
{
  const activityRefLike = { current: [{ id: 'new', ts: 100, text: 'wrote a note' }] };
  const fetched = [
    { id: 'h1', ts: 1, priority: 'routine', text: 'walked onto the floor' },
    { id: 'h2', ts: 2, priority: 'routine', text: 'finished the brief' },
    { id: 'h3', ts: 3, priority: 'attention', unread: true, text: 'hit a snag on the report' },
  ];
  const transform = (f) => mergeByIdCap(activityRefLike.current, f, 200);
  const out = runEffect({
    dirty: true, initialVal: activityRefLike.current, seed: JSON.stringify([]),
    mergeOnDirty: false, transform, data: fetched,
  });
  check('THE BUG, reproduced: without mergeOnDirty, a dirty real edit never calls setVal at all',
    out.setValCalls.length === 0, out.setValCalls);
  check('THE BUG, reproduced: the fetched history (incl. the unread attention row) never enters state',
    out.finalVal.length === 1, out.finalVal);
}

// --- Scenario B: the fix — identical preconditions, mergeOnDirty: true. --
{
  const activityRefLike = { current: [{ id: 'new', ts: 100, text: 'wrote a note' }] };
  const fetched = [
    { id: 'h1', ts: 1, priority: 'routine', text: 'walked onto the floor' },
    { id: 'h2', ts: 2, priority: 'routine', text: 'finished the brief' },
    { id: 'h3', ts: 3, priority: 'attention', unread: true, text: 'hit a snag on the report' },
  ];
  const transform = (f) => mergeByIdCap(activityRefLike.current, f, 200);
  const out = runEffect({
    dirty: true, initialVal: activityRefLike.current, seed: JSON.stringify([]),
    mergeOnDirty: true, transform, data: fetched,
  });
  check('THE FIX: with mergeOnDirty, a dirty real edit still merges (setVal called once)',
    out.setValCalls.length === 1, out.setValCalls);
  const merged = out.setValCalls[0] || [];
  check('THE FIX: all four entries present — nothing from the fetched history was dropped',
    merged.length === 4, merged);
  check('THE FIX: the unread attention row survived the merge',
    merged.some(e => e.id === 'h3' && e.priority === 'attention' && e.unread === true), merged);
  check('THE FIX: newest-first order preserved (the freshly-logged entry leads)',
    merged[0].id === 'new', merged);
  check('THE FIX: hydratedRef still flips true (file writes may proceed after this)',
    out.hydrated === true);
}

// --- Scenario C: a clean mount (nothing logged before the fetch landed) —
// behavior must be identical whether mergeOnDirty is set or not. ---------
for (const flag of [false, true]) {
  const activityRefLike = { current: [] };
  const fetched = [{ id: 'h1', ts: 1 }, { id: 'h2', ts: 2 }];
  const transform = (f) => mergeByIdCap(activityRefLike.current, f, 200);
  const out = runEffect({
    dirty: false, initialVal: [], seed: JSON.stringify([]),
    mergeOnDirty: flag, transform, data: fetched,
  });
  check('clean mount merges the fetched file regardless of mergeOnDirty=' + flag,
    out.setValCalls.length === 1 && out.finalVal.length === 2, out);
}

// --- Scenario D: dirtyRef set by a boot-time normalizing write that
// reproduced the exact seed (untouched=true) — must still merge, same as
// before this fix, regardless of mergeOnDirty. ---------------------------
for (const flag of [false, true]) {
  const activityRefLike = { current: [] };
  const fetched = [{ id: 'h1', ts: 1 }];
  const transform = (f) => mergeByIdCap(activityRefLike.current, f, 200);
  const out = runEffect({
    dirty: true, initialVal: [], seed: JSON.stringify([]),   // untouched: val === seed
    mergeOnDirty: flag, transform, data: fetched,
  });
  check('dirty-but-untouched (boot echo) still merges, mergeOnDirty=' + flag,
    out.setValCalls.length === 1 && out.finalVal.length === 1, out);
}

// --- Scenario E: a snapshot-style consumer (tasks/agents-shaped — no
// mergeOnDirty, transform that does NOT reconcile against in-memory) must
// KEEP the original protective behavior: a real edit discards the fetch. --
{
  const transform = (fetchedDoc) => fetchedDoc.map(t => ({ ...t, cleaned: true }));
  const out = runEffect({
    dirty: true, initialVal: [{ id: 'liveEdit' }], seed: JSON.stringify([]),
    mergeOnDirty: false, transform, data: [{ id: 'staleSnapshot' }],
  });
  check('snapshot-style consumer (mergeOnDirty unset): a real edit still keeps theirs, discarding the stale fetch',
    out.setValCalls.length === 0 && out.finalVal.length === 1 && out.finalVal[0].id === 'liveEdit', out);
}

console.log(JSON.stringify(results));
"""
    harness = harness.replace('__MERGE_BY_ID_CAP__', merge_src).replace('__EFFECT_BODY__', effect_body)

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
    print(('FAILED: %s' % FAILS) if FAILS else 'activity mount-fetch merge race: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
