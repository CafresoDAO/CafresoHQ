#!/usr/bin/env python3
"""A job that snagged after it was finished can be finished again.

`xpRecord()` (app/experience.jsx) enforces the ledger's "a job completes
once" promise so that every double-fire path is safe. It used to enforce it
with `prev.some(e => e.taskId === taskId && e.outcome === 'done')` — a scan
of the WHOLE log, meaning "has this job EVER completed", when the thing that
makes a double-fire a double-fire is that the completion is still STANDING.

A task can leave `done`: the board moves cards between columns and
`applyStatus` in app.jsx carries its own note about a re-opened task not
inheriting a stale age. So the sequence below is ordinary office work:

    done  (Kenji delivers it)          → recorded
    snag  (re-opened, next run fails)  → recorded
    done  (Mira picks it up, delivers) → SILENTLY DROPPED

and two user-visible things then stuck, both of them reading as current:

  * Mira got no credit at all — `xpStats()` counted zero jobs and zero
    streak for a delivery that really happened. That is the résumé ledger
    (§5, the Phase B→C bridge) losing work, and it is append-only, so
    nothing later repairs it.
  * `xpLastAttempt()` reports this job's NEWEST entry. With the success on
    the floor the newest entry stayed the snag, so the inbox card
    (features.jsx, ui/office.jsx) kept printing "⚠ Kenji hit a snag on
    this" and `workflowStatusBits` (modals/collab.jsx) kept counting the
    step as "1 failed — needs you" — forever, on a step that had since
    succeeded. modals/collab.jsx's own comment promises the opposite in so
    many words: it "clears itself the moment a retry succeeds".

Fix: scan back to this job's newest entry only. A standing 'done' is still
dropped (double-fire, unchanged); a 'snag' since the last completion means
the job really was re-attempted, and that re-attempt's success is a
completion the log has never held.

Runs the REAL source under node with the import/export lines stripped, the
same harness pattern as scripts/test_experience.py.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'experience.jsx'
COLLAB = ROOT / 'modals' / 'collab.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def run_js(cases_js):
    text = SRC.read_text(encoding='utf-8')
    src = '\n'.join(ln for ln in text.split('\n')
                    if not ln.startswith('import ') and not ln.startswith('export '))
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('a retried job can be finished twice')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
const AGENTS = [{ id: 'kenji', name: 'Kenji' }, { id: 'mira', name: 'Mira' }];

/* ── The office story, in order ──────────────────────────────────────── */
let L = [];
L = xpRecord(L, { agentId: 'kenji', kind: 'brief', outcome: 'done', taskId: 'tk_1',
                  title: 'Q3 brief', at: 100 });
// Re-opened on the board; the next run comes back empty.
L = xpRecord(L, { agentId: 'kenji', kind: 'brief', outcome: 'snag', taskId: 'tk_1',
                  title: 'Q3 brief', at: 200 });
R.afterSnag = L.length;                       // 2 — both recorded, always did
// Mira picks it up and delivers.
L = xpRecord(L, { agentId: 'mira', kind: 'brief', outcome: 'done', taskId: 'tk_1',
                  title: 'Q3 brief', at: 300 });

R.retryRecorded = L.length;                   // 3 — the delivery reaches the log
R.miraJobs      = xpStats(L, 'mira').jobs;    // 1 — she is credited for it
R.miraStreak    = xpStats(L, 'mira').streak;  // 1
R.cardWarning   = xpLastAttemptText(xpLastAttempt(L, 'tk_1', AGENTS));  // '' — cleared
R.lastOutcome   = (xpLastAttempt(L, 'tk_1', AGENTS) || {}).outcome;     // 'done'

/* The exact expression modals/collab.jsx's workflowStatusBits uses to count
   a failed step. It must stop counting this step once the retry lands. */
R.stillCountsFailed = (xpLastAttempt(L, 'tk_1') || {}).outcome === 'snag';

/* ── And the double-fire guard the change must NOT weaken ────────────── */
const one = xpRecord([], { agentId: 'a1', kind: 'brief', outcome: 'done', taskId: 't1', at: 1 });
R.dedupeSameAgent   = xpRecord(one, { agentId: 'a1', kind: 'brief', outcome: 'done', taskId: 't1', at: 2 }).length;
R.dedupeOtherAgent  = xpRecord(one, { agentId: 'a2', kind: 'task',  outcome: 'done', taskId: 't1', at: 2 }).length;
/* Interleaved OTHER jobs must not be mistaken for this job's newest entry:
   a snag on a DIFFERENT task sitting after t1's done is not a re-attempt of
   t1, so t1's double-fire is still dropped. */
const noisy = xpRecord(one, { agentId: 'a1', kind: 'draft', outcome: 'snag', taskId: 't2', at: 2 });
R.dedupeThroughNoise = xpRecord(noisy, { agentId: 'a1', kind: 'brief', outcome: 'done', taskId: 't1', at: 3 }).length;
// A done with no taskId (an un-keyed job) is never deduped — unchanged.
R.noTaskIdAppends = xpRecord(one, { agentId: 'a1', kind: 'mission', outcome: 'done', at: 4 }).length;
// A snag after a done still records, and snag→done on a fresh job still does.
R.snagAfterDone = xpRecord(one, { agentId: 'a1', kind: 'brief', outcome: 'snag', taskId: 't1', at: 2 }).length;
R.snagThenDone  = xpRecord(noisy, { agentId: 'a1', kind: 'draft', outcome: 'done', taskId: 't2', at: 3 }).length;
// Still append-only: no input array was mutated along the way.
R.appendOnly = one.length === 1;

/* A THIRD cycle — done, snag, done, snag, done — still books every real
   completion, so the guard is a standing-completion rule and not a
   one-shot exemption. */
let C = L;
C = xpRecord(C, { agentId: 'mira', kind: 'brief', outcome: 'snag', taskId: 'tk_1', at: 400 });
C = xpRecord(C, { agentId: 'mira', kind: 'brief', outcome: 'done', taskId: 'tk_1', at: 500 });
R.thirdCycle = C.length;                      // 5
R.miraJobsEnd = xpStats(C, 'mira').jobs;      // 2

console.log(JSON.stringify(R));
''')

    check('a snag after a completion records (unchanged)', out['afterSnag'] == 2,
          str(out['afterSnag']))

    # ── The bug ───────────────────────────────────────────────────────
    check('the retry that succeeded reaches the ledger',
          out['retryRecorded'] == 3,
          f"ledger has {out['retryRecorded']} entries, expected 3 — the "
          'second completion was dropped')
    check('the coworker who delivered it is credited with the job',
          out['miraJobs'] == 1, str(out['miraJobs']))
    check('...and it counts toward their streak', out['miraStreak'] == 1,
          str(out['miraStreak']))
    check('the inbox card stops warning about the snag',
          out['cardWarning'] == '',
          f'card still reads {out["cardWarning"]!r}')
    check("xpLastAttempt's newest entry for the job is the success",
          out['lastOutcome'] == 'done', repr(out['lastOutcome']))
    check('the workflow panel stops counting the step as failed',
          out['stillCountsFailed'] is False)

    # ── What must not have been weakened ──────────────────────────────
    check('a double-fired done is still dropped (same agent)',
          out['dedupeSameAgent'] == 1, str(out['dedupeSameAgent']))
    check('a double-fired done is still dropped (any agent)',
          out['dedupeOtherAgent'] == 1, str(out['dedupeOtherAgent']))
    check("another job's snag does not unlock this job's double-fire",
          out['dedupeThroughNoise'] == 2, str(out['dedupeThroughNoise']))
    check('a done with no taskId still appends', out['noTaskIdAppends'] == 2,
          str(out['noTaskIdAppends']))
    check('a snag after a done still records', out['snagAfterDone'] == 2)
    check('snag then done on one job both record', out['snagThenDone'] == 3)
    check('the input ledger is never mutated', out['appendOnly'])
    check('a second re-open/retry cycle records too', out['thirdCycle'] == 5,
          str(out['thirdCycle']))
    check('...and both of that coworker\'s deliveries count',
          out['miraJobsEnd'] == 2, str(out['miraJobsEnd']))

    # ── The promise this restores is written down in collab.jsx ────────
    if COLLAB.is_file():
        check('modals/collab.jsx still reads the newest entry per step '
              '(the surface this fix un-sticks)',
              "xpLastAttempt(experience, t.id)" in COLLAB.read_text(encoding='utf-8'))

    print()
    if FAILS:
        print(f'{len(FAILS)} failure(s): ' + '; '.join(FAILS))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
