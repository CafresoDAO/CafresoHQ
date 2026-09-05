#!/usr/bin/env python3
"""The receipts tray was the one store in the office with no ceiling (app.jsx).

Every store the office keeps has a bound, or is a snapshot whose size is the
size of the thing it describes. The activity log — the receipts tray's own
neighbour, three hundred lines up in app.jsx, feeding the same bell — is
capped twice over: `logActivity` slices to 200 as it writes a row, and the
mount-fetch transform hands `mergeByIdCap(..., fetched, 200)` the same
number so a reload cannot undo it.

`receipts` had neither. `recordReceipt` was `setReceipts(prev => [r,
...prev])` and the mount transform unioned the file with memory and sorted,
full stop. One stamped decision is ~220 bytes; a CLI agent under the
PreToolUse hook asks for one every few seconds all day; nothing ever removed
a row. The array lived in memory, was mirrored into localStorage, was
re-serialised WHOLE into hq-state/receipts.json on every new row, and was
walked end-to-end by the bell's mergedNotifications memo on every render.

Measured live 2026-09-05 (PORT=8811 python3 serve.py, real browser, real
tray): 255 approvals POSTed to /approvals/external, each one clicked
APPROVE in the UI. `cafresohq_hq_v1:receipts` came back 256 entries /
57,039 bytes with no sign of levelling off, and the bell's own title read
"256 unread notifications". localStorage's ~5MB is per ORIGIN, not per key,
so the store that grows without a bound is not the only casualty when it
finally lands on the quota: the roster, the tasks and the chat share that
budget, and unlike the receipts they have nothing to fall back on.

Fix: RECEIPTS_CAP, applied in the same two places the activity log applies
its number — at the write, and at the mount-fetch merge. A cap on only one
of them is undone by the next reload, which is why this test insists on
both. After the fix, the same drive held at exactly 200 in localStorage and
in the file, with the newest stamp still on top.

This test lifts the REAL updater and the REAL mount transform out of
app.jsx by source-anchored extraction — not a line range, not a hand-copied
reimplementation — and runs them for real under Node, so a regression that
drops either half fails here.

Run: python3 scripts/test_a_long_day_of_stamps_does_not_grow_the_receipts_tray_forever.py
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
APP_JSX = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def balanced_from(src, start):
    """Return src[start:end] where end closes the bracket nesting opened at
    or after `start`, stopping at the first point where depth returns to 0
    after having been positive. Skips strings/template literals."""
    i = start
    depth = 0
    opened = False
    in_str = None
    n = len(src)
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
            opened = True
        elif c in ')}]':
            depth -= 1
            if opened and depth == 0:
                return src[start:i + 1]
        i += 1
    raise AssertionError('unterminated bracket run at offset %d' % start)


def extract_receipts_transform(src):
    """The `(fetched) => { ... }` load transform passed to receipts'
    useFileStored call. Anchored on the k('receipts') call itself."""
    m = re.search(r"useFileStored\(k\('receipts'\),\s*'state',\s*'receipts',\s*\[\],\s*", src)
    if not m:
        raise AssertionError("receipts useFileStored(...) call not found")
    arrow = re.compile(r'\(fetched\)\s*=>\s*\{').search(src, m.end())
    if not arrow or arrow.start() - m.end() > 4:
        raise AssertionError("receipts load transform (fetched) => {...} not found")
    body = balanced_from(src, arrow.end() - 1)
    return '(fetched) => ' + body


def extract_record_updater(src):
    """The updater recordReceipt hands setReceipts when a decision is
    stamped. Anchored on the setReceipts call that adds a row (the only one
    that prepends), not on a line number."""
    m = re.search(r'setReceipts\(prev\s*=>\s*\[r,\s*\.\.\.prev\]', src)
    if not m:
        raise AssertionError("recordReceipt's setReceipts(prev => [r, ...prev]...) not found")
    call = balanced_from(src, m.start() + len('setReceipts'))
    return call[1:-1]   # strip the outer ( )


def main():
    src = APP_JSX.read_text(encoding='utf-8')

    cap_m = re.search(r'const RECEIPTS_CAP = (\d+);', src)
    check('app.jsx names a bound for the receipts tray (RECEIPTS_CAP)',
          cap_m is not None, 'no `const RECEIPTS_CAP = <n>;` in app.jsx')
    if cap_m is None:
        print()
        print('FAILED: %s' % FAILS)
        return 1
    cap = int(cap_m.group(1))
    check('the bound is a real number, not zero or something absurd',
          10 <= cap <= 5000, cap)

    transform_src = extract_receipts_transform(src)
    check('receipts load transform extracted from app.jsx',
          'byId' in transform_src and 'decidedAt' in transform_src)

    updater_src = extract_record_updater(src)
    check("recordReceipt's setReceipts updater extracted from app.jsx",
          updater_src.startswith('prev'))

    # --- source-shape: BOTH halves carry the bound ---------------------------
    # A cap at the write alone is undone by the next reload (the mount fetch
    # adopts the whole file); a cap at the merge alone lets a single long
    # session grow without limit until it is reloaded. The activity log
    # applies its number in both places and so must this.
    check('the write path caps the row it just added',
          'RECEIPTS_CAP' in updater_src,
          'recordReceipt appends without a bound — a long day still grows forever')
    check('the mount-fetch merge caps the file it just adopted',
          'RECEIPTS_CAP' in transform_src,
          'a reload re-adopts the whole unbounded file, undoing the write cap')

    has_node = bool(shutil.which('node'))
    check('node is on PATH (needed to genuinely execute the extracted logic)',
          has_node, 'skipping the live-execution checks')
    if not has_node:
        print()
        print(('FAILED: %s' % FAILS) if FAILS else
              'source-shape checks passed (node unavailable, live checks skipped)')
        return 1 if FAILS else 0

    harness = """
'use strict';
const RECEIPTS_CAP = __CAP__;
const results = [];
function check(name, cond, detail) { results.push([name, !!cond, detail === undefined ? null : detail]); }

const updater  = __UPDATER__;
const transform = __TRANSFORM__;

// --- a long day at the desk: stamp 5x the bound, one row at a time --------
const STAMPS = RECEIPTS_CAP * 5;
let receipts = [];
let r = null;
for (let i = 0; i < STAMPS; i++) {
  r = { id: 'rc_' + i, title: 'Bash: stamp ' + i, decision: 'approved', decidedAt: 1000 + i };
  receipts = updater(receipts);
}
check('a day of ' + STAMPS + ' stamps leaves the tray at the bound, not at ' + STAMPS,
      receipts.length === RECEIPTS_CAP, receipts.length);
check('the newest stamp is still the top row', receipts[0] && receipts[0].id === 'rc_' + (STAMPS - 1),
      receipts[0] && receipts[0].id);
check('the oldest stamps are the ones that fell off',
      !receipts.some(x => x.id === 'rc_0'), 'rc_0 survived');
check('nothing is duplicated on the way out',
      new Set(receipts.map(x => x.id)).size === receipts.length);

// --- and a reload does not re-adopt an old, oversized file ----------------
// receiptsRef is what the transform reads for "recorded in the first ~1.5s".
const receiptsRef = { current: [
  { id: 'rc_live', title: 'stamped while the fetch was in flight', decidedAt: 9e12 },
] };
const fetched = [];
for (let i = 0; i < STAMPS; i++) {
  fetched.push({ id: 'old_' + i, title: 'Bash: stamp ' + i, decidedAt: 1000 + i });
}
const merged = transform(fetched);
check('a ' + STAMPS + '-row file on disk is adopted down to the bound',
      merged.length === RECEIPTS_CAP, merged.length);
check('the merge still keeps the newest first',
      merged.every((x, i) => i === 0 || (merged[i - 1].decidedAt || 0) >= (x.decidedAt || 0)));
check('a row stamped while the fetch was in flight survives the trim',
      merged.some(x => x.id === 'rc_live'));
check('what the trim dropped is the oldest end of the file',
      !merged.some(x => x.id === 'old_0'), 'old_0 survived');

// --- a file that is already inside the bound is left whole ---------------
receiptsRef.current = [];
const small = transform([
  { id: 'a', decidedAt: 3 }, { id: 'b', decidedAt: 1 }, { id: 'c', decidedAt: 2 },
]);
check('a short history is not trimmed, only sorted',
      small.length === 3 && small.map(x => x.id).join('') === 'acb', small.map(x => x.id).join(''));

console.log(JSON.stringify(results));
"""
    harness = (harness
               .replace('__CAP__', str(cap))
               .replace('__UPDATER__', updater_src)
               .replace('__TRANSFORM__', transform_src))

    proc = subprocess.run([shutil.which('node'), '-e', harness],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        check('the extracted receipts logic runs under node', False,
              (proc.stderr or proc.stdout).strip()[:600])
    else:
        try:
            for name, ok, detail in json.loads(proc.stdout.strip().splitlines()[-1]):
                check(name, ok, detail)
        except (ValueError, IndexError) as e:
            check('node harness produced readable results', False,
                  '%s :: %s' % (e, proc.stdout[:400]))

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
