#!/usr/bin/env python3
"""Messages-registry merge race — app/storage.jsx mergeMessages + persistableMessages.

useFileStored's mount-time fetch is documented as merging the file with
whatever's already in memory, but the hook itself just *overwrites* React
state with whatever the fetch returns; the merging is left to the caller's
transform argument. That's harmless for state nobody writes between mount and
the fetch landing. It is NOT harmless for `messages`: createMessage() appends
to it (and flushes to localStorage) synchronously, while the matching file
write is debounced 1.5s behind. A same-tab reload inside that window used to
let the mount-time fetch's older file content silently stomp a message that
had already been created — the boss's DM/handoff just vanishes on reload, no
error, no trace.

`activity` hit the identical shape of race (in-memory log vs. debounced file
write) and was fixed with a merge-by-id transform (mergeByIdCap); `messages`
never got the equivalent until now. This test lifts the real mergeMessages
and persistableMessages functions out of app/storage.jsx BY NAME (brace-
balanced source extraction, not a line range) and runs them for real under
Node, so a regression that reintroduces the overwrite — or that changes which
side wins a collision — fails this test rather than waiting for someone to
notice a message missing after a reload.

Run: python3 scripts/test_messages_registry_merge.py
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
STORAGE_JSX = os.path.join(ROOT, 'app', 'storage.jsx')
APP_JSX = os.path.join(ROOT, 'app.jsx')

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract_const_statement(src, name):
    """Pull `const <name> = ...;` out of src by balancing (), {}, [] and
    stopping at the first top-level `;` — not by line number, and not by
    literal-matching the body text. Works whether the arrow body is a `{...}`
    block or a bare expression, and skips over strings/template literals so a
    stray `;` or bracket inside one doesn't end the scan early."""
    m = re.search(r'const\s+' + re.escape(name) + r'\s*=\s*', src)
    if not m:
        raise AssertionError('const %s = ... not found' % name)
    i = m.end()
    start = m.start()
    depth = 0
    n = len(src)
    in_str = None  # None, or one of '"', "'", '`'
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
    with open(STORAGE_JSX, 'r', encoding='utf-8') as f:
        storage_src = f.read()
    with open(APP_JSX, 'r', encoding='utf-8') as f:
        app_src = f.read()

    cap_src = extract_const_statement(storage_src, 'MESSAGES_CAP')
    history_cap_src = extract_const_statement(storage_src, 'HISTORY_CAP')
    trim_src = extract_const_statement(storage_src, 'trimHistory')
    persistable_src = extract_const_statement(storage_src, 'persistableMessages')
    merge_src = extract_const_statement(storage_src, 'mergeMessages')

    check('persistableMessages extracted from app/storage.jsx', 'persistableMessages' in persistable_src)
    check('mergeMessages extracted from app/storage.jsx', 'mergeMessages' in merge_src)
    # The one line that actually matters for this bug: in-memory must be
    # written into the id map AFTER fetched, so it overwrites on collision.
    try:
        order_ok = merge_src.index('of (Array.isArray(fetched)') < merge_src.index('of (Array.isArray(inMem)')
    except ValueError:
        order_ok = False
    check('source order puts inMem writes after fetched writes (in-memory wins)', order_ok, merge_src)

    # The wiring: app.jsx must actually pass mergeMessages as useFileStored's
    # transform for `messages`, reading messagesRef — not just define the
    # function somewhere and never call it.
    wiring_m = re.search(
        r"useFileStored\(k\('messages'\)[^;]*mergeMessages\(messagesRef\.current,\s*fetched\)",
        app_src)
    check('app.jsx wires mergeMessages as the messages transform', wiring_m is not None)
    check('messagesRef is declared before the useFileStored(messages) call',
          app_src.index('const messagesRef = useRefA(')
          < app_src.index("useFileStored(k('messages')"))

    harness = """
'use strict';
%s
%s
%s
%s

%s

const results = [];
function check(name, cond) { results.push([name, !!cond]); }

// --- persistableMessages -------------------------------------------------

check('non-array input -> []', Array.isArray(persistableMessages(null)) && persistableMessages(null).length === 0);
check('non-array input (undefined) -> []', persistableMessages(undefined).length === 0);

{
  const many = [];
  for (let i = 0; i < 600; i++) many.push({ id: 'm' + i, ts: i, history: [] });
  const capped = persistableMessages(many);
  check('caps at 500 entries', capped.length === 500);
  check('cap keeps the most recent tail (rolling), not the head', capped[0].id === 'm100' && capped[capped.length - 1].id === 'm599');
}

{
  // trimHistory keeps the OPENING entry (the `created` record a boss reads a
  // handoff FOR) plus the most recent HISTORY_CAP-1 — not a plain tail slice.
  // 40 entries (at: 0..39) -> [at:0, at:11..at:39] = 1 + 29 = 30 kept.
  const hist = [];
  for (let i = 0; i < 40; i++) hist.push({ at: i });
  const out = persistableMessages([{ id: 'x', history: hist }]);
  check('history pruned to 30 (opening entry + most recent 29)', out[0].history.length === 30);
  check('history prune keeps the OPENING entry, not the oldest-of-the-tail',
    out[0].history[0].at === 0, out[0].history[0]);
  check('history prune keeps the newest entry', out[0].history[29].at === 39);
  check('history prune records what it dropped', out[0].historyDropped === 10, out[0].historyDropped);
}

check('missing history field becomes []', persistableMessages([{ id: 'y' }])[0].history.length === 0);

// --- mergeMessages ---------------------------------------------------------

{
  // Baseline: nothing in memory yet, file has the full history.
  const fetched = [{ id: 'a', ts: 1, state: 'open' }, { id: 'b', ts: 2, state: 'open' }];
  const out = mergeMessages([], fetched);
  check('empty in-memory: merge returns the fetched set', out.length === 2 &&
    out.some(m => m.id === 'a') && out.some(m => m.id === 'b'));
}

{
  // useFileStored can hand the transform whatever a malformed file or a
  // corrupt localStorage mirror parsed to — not necessarily an array. Both
  // sides guard independently; a guard removed from either must not throw.
  let threw = false, out = null;
  try { out = mergeMessages(null, [{ id: 'a', ts: 1 }]); } catch (_e) { threw = true; }
  check('non-array inMem does not throw, and the fetched side still comes through',
    !threw && out && out.length === 1 && out[0].id === 'a');

  threw = false; out = null;
  try { out = mergeMessages([{ id: 'a', ts: 1 }], undefined); } catch (_e) { threw = true; }
  check('non-array fetched does not throw, and the in-memory side still comes through',
    !threw && out && out.length === 1 && out[0].id === 'a');
}

{
  // Baseline: file empty (e.g. never written yet), memory has messages.
  const inMem = [{ id: 'a', ts: 1, state: 'open' }];
  const out = mergeMessages(inMem, []);
  check('empty fetched: merge returns the in-memory set', out.length === 1 && out[0].id === 'a');
}

{
  // THE BUG: msgB was created in-memory (and flushed to localStorage) after
  // the debounced file write already fired with only msgA in it. The
  // mount-time fetch resolves with the stale file content. Before the fix,
  // useFileStored's setVal(merged) with merged === fetched would drop msgB
  // outright on a same-tab reload.
  const inMem = [
    { id: 'a', ts: 1, state: 'open' },
    { id: 'b', ts: 2, state: 'open' },
  ];
  const staleFetched = [{ id: 'a', ts: 1, state: 'open' }]; // b hasn't landed on disk yet
  const out = mergeMessages(inMem, staleFetched);
  check('a message missing from the stale file is NOT dropped', out.some(m => m.id === 'b'));
  check('the file-only message is also kept', out.some(m => m.id === 'a'));
  check('nothing invented: exactly the union, no dupes', out.length === 2);
}

{
  // Collision: the same id exists on both sides with different content.
  // In-memory must win — it's always the more recent side (see comment
  // above mergeMessages in app/storage.jsx).
  const inMem = [{ id: 'a', ts: 5, state: 'resolved', note: 'fresh' }];
  const staleFetched = [{ id: 'a', ts: 1, state: 'open', note: 'stale' }];
  const out = mergeMessages(inMem, staleFetched);
  check('id collision: in-memory copy wins over the stale file copy',
    out.length === 1 && out[0].state === 'resolved' && out[0].note === 'fresh');
}

{
  // The merge result must still go through persistableMessages' cap/prune —
  // it's not a bypass of the normal persistence rules, just a smarter input.
  // 600 fetched + 1 in-memory deliberately exceeds the 500 cap so this check
  // is load-bearing: with the cap step skipped the union would be 601 long.
  const many = [];
  for (let i = 0; i < 600; i++) many.push({ id: 'f' + i, ts: i });
  const inMem = [{ id: 'new', ts: 999 }];
  const out = mergeMessages(inMem, many);
  check('merged output still respects the 500 cap', out.length === 500, out.length);
  check('merged output includes the in-memory-only entry', out.some(m => m.id === 'new'));
}

console.log(JSON.stringify(results));
""" % (cap_src, history_cap_src, trim_src, persistable_src, merge_src)

    proc = subprocess.run(['node', '-e', harness], capture_output=True, text=True, cwd=ROOT)
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

    for name, cond in node_results:
        check(name, cond)

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'messages registry merge: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
