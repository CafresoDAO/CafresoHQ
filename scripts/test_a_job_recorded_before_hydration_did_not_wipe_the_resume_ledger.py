#!/usr/bin/env python3
"""A job recorded before hydration must not wipe the experience ledger
(app.jsx, app/storage.jsx).

`experience` is the append-only job history behind OFFICE_AS_INTERFACE §5's
Phase B->C résumé bridge — every completed task and finished mission,
forever, is what `xpStats` derives Jobs/Snags/Streak/Affinity from for the
roster card and the Performance-review panel. It lives on useFileStored,
whose mount fetch hydrates it from hq-state/experience.json ~100-300ms after
first render, and whose "local edits win" guard has always read:

    if (dirtyRef.current && !untouched && !mergeOnDirty) return;

#177/#232 closed this hole for `activity`/`messages` (log-shaped transforms
that already read the current in-memory value via a ref and union it with
the fetch, so returning before the transform ran just threw the fetched
history away) by wiring `{ mergeOnDirty: true }`. #379 did the same for
`receipts`, adding a `receiptsClearedRef` because that store has a real
CLEAR ALL action a plain union can't express.

`experience` had NEITHER: no merge transform at all, and no `mergeOnDirty`.
The Night Shift poller a few hundred lines up in app.jsx calls `poll()`
synchronously on mount and awaits two same-origin fetches
(`/missions/scheduled`, `/missions/runs`) before its first `recordXp` call —
this is not a rare race, it fires on every load where a night run finished
before the page opened, and routinely beats `experience`'s own mount-fetch
back. With no transform to fall back on:

  1. `recordXp` fires in the first ~100-300ms, flipping dirtyRef with a
     ledger that no longer matches the empty seed.
  2. The mount fetch resolves with the real ledger file. The guard returns
     before ANY transform runs (there is none) — the entire on-disk job
     history for every coworker is discarded, not merged.
  3. The next job's debounced PUT overwrites hq-state/experience.json with
     only this session's own new entry. Every prior job this coworker (or
     any other) ever logged — their whole résumé — gone from disk, silently,
     and their roster card's Jobs/Streak/Affinity numbers reset under them.

The fix: a plain union transform (this store has no clear-all action to
disambiguate against, unlike `receipts`) wired with `{ mergeOnDirty: true }`,
de-duped on the full JSON-serialized entry (this ledger carries no id, and
xpRecord itself allows a 'snag' and a later 'done' to legitimately share one
taskId, so keying on taskId alone would wrongly collapse two real jobs into
one) and re-sorted ascending by `at` (xpStats' streak walk reads the ledger
newest-last).

This test lifts the REAL mount-fetch callback body out of app/storage.jsx
(the same source-anchored extraction the receipts/messages/activity sibling
tests use), lifts the REAL experience transform + `mergeOnDirty` wiring out
of app.jsx by brace-balanced extraction (not a hand-copied duplicate), and
executes the lot under Node.

Run: python3 scripts/test_a_job_recorded_before_hydration_did_not_wipe_the_resume_ledger.py
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


def extract_mount_fetch_effect_body(src):
    """Pull the body of useFileStored's mount-fetch `.then(data => { ... })`
    callback — the exact code that decides whether a dirty session adopts,
    merges, or discards the fetched file. Anchored on the two lines that
    bracket it, not a line range. (Same helper the receipts/messages/activity
    sibling tests use.)"""
    m = re.search(
        r"\.then\(data => \{\n(.*?)\n      \}\)\n      /\* Unreachable server",
        src, re.S)
    if not m:
        raise AssertionError('mount-fetch .then(data => {...}) body not found')
    return m.group(1)


def extract_experience_wiring(app_src):
    """The real experience useFileStored call. Returns (transform_src, opts_src)
    by brace/paren balancing from the anchor, not a hand-copied duplicate."""
    m = re.search(
        r"useFileStored\(k\('experience'\), 'state', 'experience', \[\],\s*\(fetched\) => \{",
        app_src)
    if not m:
        raise AssertionError("experience's useFileStored call not found")
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

    transform_body, opts_src = extract_experience_wiring(app_src)
    check("experience's union transform extracted from app.jsx",
          'JSON.stringify(e)' in transform_body)
    check('THE FIX, statically: app.jsx wires { mergeOnDirty: true } onto the experience call',
          re.search(r'mergeOnDirty:\s*true', opts_src) is not None, opts_src)
    check('THE FIX, statically: recordXp still routes through xpRecord (append-only guard untouched)',
          'setExperience(prev => xpRecord(prev, entry))' in app_src)

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
    transform_fn_src = 'function experienceTransform(fetched) ' + transform_body[transform_body.index('{'):]

    harness = """
'use strict';
let experienceRef = { current: [] };
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

// The résumé file on disk: two historical jobs, from a session before this one.
const fetchedFile = [
  { at: 100, agentId: 'a_mira', kind: 'brief', outcome: 'done', taskId: 't_1', title: 'Q3 market scan' },
  { at: 200, agentId: 'a_mira', kind: 'task', outcome: 'snag', taskId: 't_2', title: 'vendor outreach' },
];
// The job the Night Shift poller's recordXp logs ~200ms in, before the fetch:
// a mission that finished overnight, before this session's experience.json
// mount-fetch resolved.
const earlyJob = { at: 400, agentId: 'a_kip', kind: 'mission', outcome: 'done', taskId: 'run_9', title: 'overnight crawl' };

// --- Scenario A: THE BUG, as this store shipped for many releases — no
// merge transform at all (transform: null), so an early job means the
// guard in storage.jsx returns before anything can reconcile fetched vs.
// in-memory. -----------------------------------------------------------
{
  experienceRef = { current: [earlyJob] };
  const out = runEffect({
    dirty: true, initialVal: experienceRef.current, seed: JSON.stringify([]),
    mergeOnDirty: false, transform: null, data: fetchedFile,
  });
  check('THE BUG, reproduced: with no transform, an early job means setVal is never called',
    out.setValCalls.length === 0, out.setValCalls);
  check('THE BUG, reproduced: the fetched résumé (2 historical jobs) never enters state',
    out.finalVal.length === 1, out.finalVal);
}

// --- Scenario B: THE FIX — the real experience transform, wired with
// mergeOnDirty: true, same early job. -----------------------------------
{
  experienceRef = { current: [earlyJob] };
  const out = runEffect({
    dirty: true, initialVal: experienceRef.current, seed: JSON.stringify([]),
    mergeOnDirty: true, transform: experienceTransform, data: fetchedFile,
  });
  check('THE FIX: an early job no longer discards the fetched résumé (setVal called once)',
    out.setValCalls.length === 1, out.setValCalls);
  const merged = out.setValCalls[0] || [];
  check('THE FIX: all three entries present — two from disk plus the early job',
    merged.length === 3, merged);
  check('THE FIX: the historical snag (t_2) survived',
    merged.some(e => e.taskId === 't_2' && e.outcome === 'snag'), merged);
  check('THE FIX: the early job (run_9) is in the merged result',
    merged.some(e => e.taskId === 'run_9' && e.agentId === 'a_kip'), merged);
  check('THE FIX: hydratedRef still flips true (file writes may proceed after this)',
    out.hydrated === true);
  check('THE FIX: sorted ascending by `at` (xpStats reads the ledger newest-last)',
    merged.every((e, i) => i === 0 || (merged[i - 1].at || 0) <= (e.at || 0)), merged);
}

// --- Scenario C: a retried job — the SAME taskId legitimately appears
// twice (a 'snag' on disk, a 'done' recorded in-session after a retry).
// The two entries are distinct events and must both survive the merge,
// not collapse into one just because they share a taskId. --------------
{
  const retryDone = { at: 500, agentId: 'a_mira', kind: 'task', outcome: 'done', taskId: 't_2', title: 'vendor outreach' };
  experienceRef = { current: [retryDone] };
  const out = runEffect({
    dirty: true, initialVal: experienceRef.current, seed: JSON.stringify([]),
    mergeOnDirty: true, transform: experienceTransform, data: fetchedFile,
  });
  const merged = out.setValCalls[0] || [];
  const t2Entries = merged.filter(e => e.taskId === 't_2');
  check('retried job: both the original snag and the later done for the same taskId survive',
    t2Entries.length === 2
      && t2Entries.some(e => e.outcome === 'snag')
      && t2Entries.some(e => e.outcome === 'done'),
    merged);
}

// --- Scenario D: clean mount (no early job) — unchanged behavior: the
// file is adopted whole. -------------------------------------------------
{
  experienceRef = { current: [] };
  const out = runEffect({
    dirty: false, initialVal: [], seed: JSON.stringify([]),
    mergeOnDirty: true, transform: experienceTransform, data: fetchedFile,
  });
  check('clean mount still adopts the résumé ledger whole',
    out.setValCalls.length === 1 && out.finalVal.length === 2, out.finalVal);
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
          'experience mount-fetch merge race: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
