#!/usr/bin/env python3
"""A receipt stamped before hydration must not wipe the receipts ledger
(app.jsx, app/storage.jsx).

`receipts` is the audit trail this codebase's own ReceiptsModal calls
"stamped approvals · audit trail" — every APPROVE/REJECT decision and every
elevated tool call, filed on-chain-adjacent as the one durable record a boss
can scroll back through months later. It lives on useFileStored, whose
mount fetch hydrates it from hq-state/receipts.json ~100-300ms after first
render, and whose "local edits win" guard has always read:

    if (dirtyRef.current && !untouched && !mergeOnDirty) return;

#177/#209 closed this exact hole for `activity` and `messages` by wiring
`{ mergeOnDirty: true }` onto their calls, because both are log-shaped
transforms (mergeByIdCap / mergeMessages) that already read the CURRENT
in-memory value via a ref and union it with the fetch — so returning before
the transform ever ran didn't protect anything, it just threw the fetched
history away. `receipts` carries the identical union-by-id transform and
the identical exposure:

  1. A receipt is recorded in the first ~300ms — a coworker's elevated tool
     call lands, or an external approval the boss already decided is
     recorded the instant the office paints — flipping dirtyRef with a
     value that no longer matches the seed.
  2. The mount fetch resolves with the real ledger file. The guard returns
     before the union transform is ever called: the entire on-disk history
     is discarded, not merged.
  3. The next receipts write's debounced PUT overwrites hq-state/receipts.json
     with only the session's own new rows. Every prior approval/rejection —
     the audit trail's whole reason to exist — gone from disk, silently.

`receipts` was left off `#177`'s blanket fix on purpose (see the ledger:
"receipts sits on a similar inline union transform but was left alone on
purpose... that one needs its own reasoned fix, not this flag") because
`onClearReceipts` is a REAL in-session deletion (`setReceipts([])`), and a
plain union-by-id merge can only ADD or overwrite entries — it cannot
express "this id is gone". Wiring `mergeOnDirty: true` alone would have
resurrected every receipt the boss just cleared the instant the mount fetch
landed.

The fix: `receiptsClearedRef`, flipped only by `onClearReceipts`, checked
first in the transform. When the boss's last action was CLEAR ALL, the
transform returns `[]` (honoring the clear, which also writes back to
disk) instead of merging; otherwise it merges exactly as before, so a
receipt recorded in the pre-hydration window is no longer silently lost.

This test lifts the REAL mount-fetch callback body out of app/storage.jsx
(the same source-anchored extraction the messages/activity sibling test
uses), lifts the REAL receipts transform + `mergeOnDirty` wiring out of
app.jsx by brace-balanced extraction (not a hand-copied duplicate), and
executes the lot under Node.

Run: python3 scripts/test_a_receipt_recorded_before_hydration_did_not_wipe_the_ledger.py
(skips the live-execution checks if `node` isn't on PATH — the
source-shape checks still run everywhere)
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
    end the scan early. (Same helper the messages/activity merge tests use.)"""
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


def extract_receipts_wiring(app_src):
    """The real receipts useFileStored call. Returns (transform_src, opts_src)
    by brace/paren balancing from the anchor, not a hand-copied duplicate."""
    m = re.search(r"useFileStored\(k\('receipts'\), 'state', 'receipts', \[\],\s*\(fetched\) => \{", app_src)
    if not m:
        raise AssertionError("receipts' useFileStored call not found")
    body_start = app_src.index('{', m.start())
    depth = 0
    i = body_start
    while i < len(app_src):
        if app_src[i] == '{':
            depth += 1
        elif app_src[i] == '}':
            depth -= 1
            if depth == 0:
                break
        i += 1
    transform_body = app_src[body_start:i + 1]
    # Whatever follows the transform's closing brace up to the call's own
    # closing `)` is the options object (or nothing, pre-fix).
    rest = app_src[i + 1:i + 200]
    m2 = re.search(r'^\s*,\s*(\{.*?\})\s*\)\s*;', rest, re.S)
    opts_src = m2.group(1) if m2 else ''
    return transform_body, opts_src


def main():
    storage_src = STORAGE_JSX.read_text(encoding='utf-8')
    app_src = APP_JSX.read_text(encoding='utf-8')

    effect_body = extract_mount_fetch_effect_body(storage_src)
    check('mount-fetch effect body extracted from app/storage.jsx',
          'transform ? transform(data) : data' in effect_body)
    check('the dirty-edit guard is still gated by !mergeOnDirty (the #177 escape hatch exists)',
          'if (dirtyRef.current && !untouched && !mergeOnDirty) return;' in storage_src)

    transform_body, opts_src = extract_receipts_wiring(app_src)
    check("receipts' union-by-id transform extracted from app.jsx",
          'byId.set' in transform_body)
    check('THE FIX, statically: the transform checks receiptsClearedRef before merging',
          'receiptsClearedRef.current' in transform_body)
    check('THE FIX, statically: app.jsx wires { mergeOnDirty: true } onto the receipts call',
          re.search(r'mergeOnDirty:\s*true', opts_src) is not None, opts_src)
    check('THE FIX, statically: onClearReceipts sets receiptsClearedRef before clearing',
          re.search(r'onClearReceipts = \(\) => \{ receiptsClearedRef\.current = true; setReceipts\(\[\]\); \};', app_src) is not None)

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted hook logic)',
          has_node, 'skipping the live-execution checks')

    if not has_node:
        print()
        print(('FAILED: %s' % FAILS) if FAILS else
              'source-shape checks passed (node unavailable, live checks skipped)')
        return 1 if FAILS else 0

    # Turn `(fetched) => { ... }` into a standalone function declaration the
    # harness can call directly.
    transform_fn_src = 'function receiptsTransform(fetched) ' + transform_body[transform_body.index('{'):]

    harness = """
'use strict';
const RECEIPTS_CAP = 200;
const receiptsClearedRef = { current: false };
let receiptsRef = { current: [] };
__TRANSFORM__

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
  const persist = (v) => { persistCalls.push(v); };
  const persistCalls = [];
  const data = opts.data;

  (function () {
__EFFECT_BODY__
  })();

  return { hydrated: hydratedRef.current, setValCalls, finalVal: valRef.current, persistCalls };
}

// The ledger file on disk: three durable stamped decisions.
const fetchedFile = [
  { id: 'rc_h1', title: 'wrote Research/q3.md', by: 'Nova', kind: 'deliverable', decision: 'executed', decidedAt: 100 },
  { id: 'rc_h2', title: 'send 0.05 ICP to a vendor', by: 'Mika', kind: 'awaiting stamp', decision: 'approved', decidedAt: 200 },
  { id: 'rc_h3', title: 'delete the staging bucket', by: 'Kip', kind: 'awaiting stamp', decision: 'rejected', decidedAt: 300 },
];
// The receipt an elevated tool call recorded ~200ms in, before the fetch.
const earlyReceipt = { id: 'rc_new', title: 'ran a shell command', by: 'Selvin', kind: 'tool-execution', decision: 'executed', decidedAt: 400 };

// --- Scenario A: the bug — early receipt, mergeOnDirty OFF (pre-fix wiring,
// as this store shipped for many releases before this fix). --------------
{
  receiptsRef = { current: [earlyReceipt] };
  const out = runEffect({
    dirty: true, initialVal: receiptsRef.current, seed: JSON.stringify([]),
    mergeOnDirty: false, transform: receiptsTransform, data: fetchedFile,
  });
  check('THE BUG, reproduced: without mergeOnDirty, an early receipt means setVal is never called',
    out.setValCalls.length === 0, out.setValCalls);
  check('THE BUG, reproduced: the fetched ledger (3 stamped decisions) never enters state',
    out.finalVal.length === 1, out.finalVal);
}

// --- Scenario B: the fix — same preconditions, mergeOnDirty ON (as wired
// in app.jsx) and no clear in play. ---------------------------------------
{
  receiptsClearedRef.current = false;
  receiptsRef = { current: [earlyReceipt] };
  const out = runEffect({
    dirty: true, initialVal: receiptsRef.current, seed: JSON.stringify([]),
    mergeOnDirty: true, transform: receiptsTransform, data: fetchedFile,
  });
  check('THE FIX: an early receipt no longer discards the fetched ledger (setVal called once)',
    out.setValCalls.length === 1, out.setValCalls);
  const merged = out.setValCalls[0] || [];
  check('THE FIX: all four rows present — three from disk plus the early receipt',
    merged.length === 4, merged);
  check('THE FIX: the rejected decision survived',
    merged.some(r => r.id === 'rc_h3' && r.decision === 'rejected'), merged);
  check('THE FIX: hydratedRef still flips true (file writes may proceed after this)',
    out.hydrated === true);
  check('THE FIX: the merged union is ALSO written back to disk (persist called), so the recovered history is not lost again on the next reload',
    out.persistCalls.length === 1 && out.persistCalls[0].length === 4, out.persistCalls);
}

// --- Scenario C: CLEAR ALL raced against the same mount fetch — the boss's
// last action was a real deletion, not an append. Must NOT resurrect the
// file's rows. -------------------------------------------------------------
{
  receiptsClearedRef.current = true;
  receiptsRef = { current: [] };
  const out = runEffect({
    dirty: true, initialVal: receiptsRef.current, seed: JSON.stringify([fetchedFile[0]]),
    mergeOnDirty: true, transform: receiptsTransform, data: fetchedFile,
  });
  check('CLEAR ALL: the transform is reached (mergeOnDirty true) rather than skipped',
    out.setValCalls.length === 1, out.setValCalls);
  check('CLEAR ALL: the clear is honored — the fetched file\\'s 3 rows are NOT resurrected',
    Array.isArray(out.setValCalls[0]) && out.setValCalls[0].length === 0, out.setValCalls);
  check('CLEAR ALL: the empty result is written back to disk too (the clear actually reaches the file)',
    out.persistCalls.length === 1 && out.persistCalls[0].length === 0, out.persistCalls);
  receiptsClearedRef.current = false;
}

// --- Scenario D: id conflict — an amended receipt (settleReceipt patched
// its outcome in-session) that also exists in the file. In-memory must win
// (the transform's own `.set` ordering: fetched first, current second). --
{
  const amended = { ...fetchedFile[1], outcome: 'shipped', outcomeText: 'Shipped — live on the Internet Computer: https://x' };
  receiptsRef = { current: [amended] };
  const out = runEffect({
    dirty: true, initialVal: receiptsRef.current, seed: JSON.stringify([]),
    mergeOnDirty: true, transform: receiptsTransform, data: fetchedFile,
  });
  const merged = out.setValCalls[0] || [];
  const h2 = merged.find(r => r.id === 'rc_h2');
  check('id conflict: the in-memory amendment (settleReceipt outcome) wins over the stale file copy',
    merged.length === 3 && h2 && h2.outcome === 'shipped', merged);
}

// --- Scenario E: clean mount (no early receipt) — unchanged behavior: the
// file is adopted whole. ---------------------------------------------------
{
  receiptsRef = { current: [] };
  const out = runEffect({
    dirty: false, initialVal: [], seed: JSON.stringify([]),
    mergeOnDirty: true, transform: receiptsTransform, data: fetchedFile,
  });
  check('clean mount still adopts the ledger file whole',
    out.setValCalls.length === 1 && out.finalVal.length === 3, out.finalVal);
}

console.log(JSON.stringify(results));
"""
    harness = (harness
               .replace('__TRANSFORM__', transform_fn_src)
               .replace('__EFFECT_BODY__', effect_body))

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
          'receipts mount-fetch merge race: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
