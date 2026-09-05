#!/usr/bin/env python3
"""A message created before hydration must not wipe the registry file
(app.jsx, app/storage.jsx).

`messages` is the system-of-record for every agent<->agent handoff — the
registry the boss reads to answer "what happened to the task I sent
Selvin?". It lives on useFileStored, whose mount fetch hydrates it from
hq-state/messages.json ~100-300ms after first render, and whose "local
edits win" guard has always read:

    if (dirtyRef.current && !untouched && !mergeOnDirty) return;

`messages` was given the log-shaped mergeMessages transform (it reads the
CURRENT in-memory value via messagesRef and unions it with the fetch) —
but never the `mergeOnDirty: true` option that makes the guard actually
HAND the transform anything on a dirty mount. #177 closed this exact hole
for `activity` and recorded, in so many words, that "the same latent gap
likely still exists there too" for messages. It did:

  1. A message is created in the first ~300ms — a dispatch fired by a
     boot-resumed run, a DM the boss sends the instant the office paints —
     flipping dirtyRef with a value that no longer matches the seed.
  2. The mount fetch resolves with the real registry file. The guard
     returns before mergeMessages is ever called: the entire durable
     history is discarded, not merged.
  3. The next registry write's debounced PUT overwrites
     hq-state/messages.json with only the session's own entries. Every
     prior handoff record — gone from disk, silently.

The fix is one option at the call site: app.jsx's messages useFileStored
call now passes `{ mergeOnDirty: true }`, the exact treatment activity
already has. Safe for this consumer because the registry only appends and
transitions (every setMessages call is `[...prev, msg]` or a `.map`) —
nothing deletes a message in-session, so the union can never resurrect
something a user removed.

This test lifts the REAL mount-fetch callback body, the REAL mergeMessages
(and its helpers persistableMessages/trimHistory and their caps) out of
app/storage.jsx by source-anchored extraction, parses the REAL mergeOnDirty
wiring off the messages call in app.jsx, and executes the lot under Node —
so a regression that drops the option, or breaks the guard, fails here.

Run: python3 scripts/test_a_message_created_before_hydration_did_not_wipe_the_registry.py
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
    end the scan early. (Same helper the activity-merge test uses.)"""
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
    bracket it, not a line range."""
    m = re.search(
        r"\.then\(data => \{\n(.*?)\n      \}\)\n      /\* Unreachable server",
        src, re.S)
    if not m:
        raise AssertionError('mount-fetch .then(data => {...}) body not found')
    return m.group(1)


def extract_messages_wiring(app_src):
    """The real messages useFileStored call: transform shape + whether the
    options object carries mergeOnDirty: true. Returns (found, flag)."""
    m = re.search(
        r"useFileStored\(k\('messages'\),\s*'state',\s*'messages',\s*\[\],\s*"
        r"\(fetched\) => mergeMessages\(messagesRef\.current,\s*fetched\)"
        r"(?:,\s*(\{[^;]*?\}))?\);",
        app_src)
    if not m:
        return False, False
    opts = m.group(1) or ''
    return True, re.search(r'mergeOnDirty:\s*true', opts) is not None


def main():
    storage_src = STORAGE_JSX.read_text(encoding='utf-8')
    app_src = APP_JSX.read_text(encoding='utf-8')

    # The real merge machinery, lifted whole. mergeMessages hands its union
    # back through persistableMessages, which needs trimHistory + both caps.
    lifted = '\n'.join(extract_const_statement(storage_src, name) for name in
                       ('MESSAGES_CAP', 'HISTORY_CAP', 'trimHistory',
                        'persistableMessages', 'mergeMessages'))
    check('mergeMessages + persistableMessages + trimHistory + caps extracted from app/storage.jsx',
          'mergeMessages' in lifted and 'persistableMessages' in lifted)

    effect_body = extract_mount_fetch_effect_body(storage_src)
    check('mount-fetch effect body extracted from app/storage.jsx',
          'transform ? transform(data) : data' in effect_body)

    # --- source-shape checks -------------------------------------------------

    check('the dirty-edit guard is still gated by !mergeOnDirty (the #177 escape hatch exists)',
          'if (dirtyRef.current && !untouched && !mergeOnDirty) return;' in storage_src)

    found, wired = extract_messages_wiring(app_src)
    check("messages' useFileStored call found in app.jsx (log-shaped mergeMessages transform)", found)
    check("THE FIX, statically: app.jsx wires { mergeOnDirty: true } onto the messages call", wired)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted hook logic)',
          has_node, 'skipping the live-execution checks')

    if not has_node:
        print()
        print(('FAILED: %s' % FAILS) if FAILS else
              'source-shape checks passed (node unavailable, live checks skipped)')
        return 1 if FAILS else 0

    harness = """
'use strict';
__LIFTED__

const results = [];
function check(name, cond, detail) { results.push([name, !!cond, detail === undefined ? null : detail]); }

// Re-creates the exact local scope the extracted `.then(data => {...})`
// body runs in, then executes that body verbatim inside an IIFE (a bare
// `return;` in the extracted source exits the IIFE, exactly as it exits
// the real .then() callback).
function runEffect(opts) {
  const hydratedRef = { current: false };
  const dirtyRef = { current: !!opts.dirty };
  // #408: the cross-reload "this browser still owes disk a write" note,
  // read by the adoption body alongside dirtyRef. `opts.unpaid` so this
  // harness can still drive the case it was written for (a live
  // pre-hydration edit) with nothing outstanding from an earlier page.
  const unpaidRef = { current: !!opts.unpaid };
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

// The registry file on disk: three durable handoff records, one still open.
const fetchedFile = [
  { id: 'msg_h1', from: 'boss', to: 'Selvin', state: 'completed', history: [{ t: 'created' }, { t: 'completed' }] },
  { id: 'msg_h2', from: 'Selvin', to: 'Kip', state: 'failed', history: [{ t: 'created' }, { t: 'failed' }] },
  { id: 'msg_h3', from: 'boss', to: 'Kip', state: 'in_progress', history: [{ t: 'created' }] },
];
// The message a boot-resumed dispatch created ~200ms in, before the fetch.
const earlyMsg = { id: 'msg_new', from: 'boss', to: 'Selvin', state: 'queued', history: [{ t: 'created' }] };

// --- Scenario A: the bug — early message, flag as it was pre-#209 (off). --
{
  const ref = { current: [earlyMsg] };
  const transform = (fetched) => mergeMessages(ref.current, fetched);
  const out = runEffect({
    dirty: true, initialVal: ref.current, seed: JSON.stringify([]),
    mergeOnDirty: false, transform, data: fetchedFile,
  });
  check('THE BUG, reproduced: without mergeOnDirty, an early message means setVal is never called',
    out.setValCalls.length === 0, out.setValCalls);
  check('THE BUG, reproduced: the fetched registry (3 durable handoffs) never enters state',
    out.finalVal.length === 1, out.finalVal);
}

// --- Scenario B: the fix — same preconditions, the flag AS WIRED in
// app.jsx (parsed off the real call site, not hardcoded true). ------------
{
  const ref = { current: [earlyMsg] };
  const transform = (fetched) => mergeMessages(ref.current, fetched);
  const out = runEffect({
    dirty: true, initialVal: ref.current, seed: JSON.stringify([]),
    mergeOnDirty: __WIRED__, transform, data: fetchedFile,
  });
  check('THE FIX, as wired: an early message no longer discards the fetched registry (setVal called once)',
    out.setValCalls.length === 1, out.setValCalls);
  const merged = out.setValCalls[0] || [];
  check('THE FIX, as wired: all four records present — three from disk plus the early message',
    merged.length === 4, merged);
  check('THE FIX, as wired: the open in_progress handoff survived',
    merged.some(m => m.id === 'msg_h3' && m.state === 'in_progress'), merged);
  check('THE FIX, as wired: hydratedRef still flips true (file writes may proceed after this)',
    out.hydrated === true);
}

// --- Scenario C: id conflict — an early state TRANSITION of a record that
// also exists in the file. In-memory must win (mergeMessages' contract), so
// the fresher state is kept, not the file's stale copy. -------------------
{
  const transitioned = { ...fetchedFile[2], state: 'completed', history: [{ t: 'created' }, { t: 'completed' }] };
  const ref = { current: [transitioned] };
  const transform = (fetched) => mergeMessages(ref.current, fetched);
  const out = runEffect({
    dirty: true, initialVal: ref.current, seed: JSON.stringify([]),
    mergeOnDirty: __WIRED__, transform, data: fetchedFile,
  });
  const merged = out.setValCalls[0] || [];
  const h3 = merged.find(m => m.id === 'msg_h3');
  check('id conflict: the in-memory transition wins over the stale file copy',
    merged.length === 3 && h3 && h3.state === 'completed', merged);
}

// --- Scenario D: clean mount (no early message) — unchanged behavior:
// the file is adopted whole. ----------------------------------------------
{
  const ref = { current: [] };
  const transform = (fetched) => mergeMessages(ref.current, fetched);
  const out = runEffect({
    dirty: false, initialVal: [], seed: JSON.stringify([]),
    mergeOnDirty: __WIRED__, transform, data: fetchedFile,
  });
  check('clean mount still adopts the registry file whole',
    out.setValCalls.length === 1 && out.finalVal.length === 3, out.finalVal);
}

console.log(JSON.stringify(results));
"""
    harness = (harness
               .replace('__LIFTED__', lifted)
               .replace('__EFFECT_BODY__', effect_body)
               .replace('__WIRED__', 'true' if wired else 'false'))

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
    print(('FAILED: %s' % FAILS) if FAILS else
          'messages mount-fetch merge race: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
