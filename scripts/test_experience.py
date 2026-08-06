#!/usr/bin/env python3
"""Experience ledger (app/experience.jsx) — pure-function suite.

The ledger is the Phase B→C résumé bridge (OFFICE_AS_INTERFACE §5): append-
only, per-agent, per-task-type. Its invariants are the product promise —
a job completes once, a snag resets the streak, and the affinity label only
claims a specialty that was actually earned — so they get pinned here.

The module is import-free by design; we strip the export line and run the
REAL source under node (same pattern as test_artifacts.py).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'experience.jsx'

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
    script = src + '\n' + cases_js
    proc = subprocess.run(['node', '--input-type=module', '-e', script],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('experience ledger')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
const rec = (l, e) => xpRecord(l, e);

// ── xpRecord: append + guards ───────────────────────────────────────────
const base = [];
const l1 = rec(base, { agentId: 'a1', kind: 'brief', outcome: 'done', taskId: 't1', title: 'Brief one', at: 1 });
R.appends            = l1.length === 1 && l1[0].kind === 'brief' && l1[0].outcome === 'done';
R.appendOnly         = base.length === 0;                       // input never mutated
R.dedupeDone         = rec(l1, { agentId: 'a1', kind: 'brief', outcome: 'done', taskId: 't1', at: 2 }).length === 1;
R.dedupeAcrossAgents = rec(l1, { agentId: 'a2', kind: 'task', outcome: 'done', taskId: 't1', at: 2 }).length === 1;
R.snagAfterDoneOk    = rec(l1, { agentId: 'a1', kind: 'brief', outcome: 'snag', taskId: 't1', at: 2 }).length === 2;
const l2 = rec(l1, { agentId: 'a1', kind: 'draft', outcome: 'snag', taskId: 't2', at: 2 });
R.snagThenDone       = rec(l2, { agentId: 'a1', kind: 'draft', outcome: 'done', taskId: 't2', at: 3 }).length === 3;
R.rejectsNoAgent     = rec(l1, { kind: 'task', outcome: 'done', taskId: 't9' }).length === 1;
R.rejectsBadOutcome  = rec(l1, { agentId: 'a1', kind: 'task', outcome: 'maybe', taskId: 't9' }).length === 1;
R.toleratesNonArray  = rec(null, { agentId: 'a1', outcome: 'done', kind: 'task', taskId: 'tx', at: 1 }).length === 1;
R.defaultsKind       = rec([], { agentId: 'a1', outcome: 'done', taskId: 'tx', at: 1 })[0].kind;
R.keepsUnknownKind   = rec([], { agentId: 'a1', kind: 'weird', outcome: 'done', taskId: 'tx', at: 1 })[0].kind;
R.truncatesTitle     = rec([], { agentId: 'a1', outcome: 'done', taskId: 'tx', at: 1, title: 'x'.repeat(200) })[0].title.length;

// ── xpStats ─────────────────────────────────────────────────────────────
const mk = (agentId, kind, outcome, i) => ({ at: i, agentId, kind, outcome, taskId: 'k' + i });
const led = [
  mk('a1', 'brief', 'done', 1), mk('a1', 'brief', 'done', 2), mk('a2', 'page', 'done', 3),
  mk('a1', 'page', 'snag', 4), mk('a1', 'draft', 'done', 5), mk('a1', 'brief', 'done', 6),
];
const s1 = xpStats(led, 'a1');
R.jobs        = s1.jobs;                 // 4 dones for a1
R.snags       = s1.snags;                // 1
R.streak      = s1.streak;               // 2 (snag at index 3 breaks it)
R.byKindBrief = s1.byKind.brief;         // 3
R.affinity    = s1.affinity;             // brief × 3
R.otherAgent  = xpStats(led, 'a2').jobs; // per-agent isolation
R.emptyStats  = xpStats([], 'a1');
R.trailingSnag = xpStats([mk('a1', 'task', 'done', 1), mk('a1', 'task', 'snag', 2)], 'a1').streak;
R.allDoneStreak = xpStats([mk('a1', 'task', 'done', 1), mk('a1', 'task', 'done', 2)], 'a1').streak;
// generic tasks are never a specialty; one of something isn't one either
R.noGenericAffinity = xpStats([mk('a1', 'task', 'done', 1), mk('a1', 'task', 'done', 2)], 'a1').affinity;
R.noSingleAffinity  = xpStats([mk('a1', 'brief', 'done', 1)], 'a1').affinity;

// ── labels + taskKind ───────────────────────────────────────────────────
R.labelPlural   = xpKindLabel('brief', 12);
R.labelSingular = xpKindLabel('mission', 1);
R.labelUnknown  = xpKindLabel('weird', 2);
R.kindStarter   = taskKind({ starter: 'brief' });
R.kindPlain     = taskKind({ title: 'x' });
R.kindWeird     = taskKind({ starter: 'nonsense' });
R.kindNull      = taskKind(null);
R.affText       = xpAffinityText(s1);
R.affTextEmpty  = xpAffinityText(xpStats([], 'a1'));
// ── xpLastAttempt — what happened last time on THIS task ───────────────
const AG = [{ id: 'a5', name: 'Kenji' }, { id: 'a1', name: 'Miko' }];
const LED = [
  { at: 100, agentId: 'a1', kind: 'brief', outcome: 'snag', taskId: 'tk_1' },
  { at: 200, agentId: 'a5', kind: 'brief', outcome: 'snag', taskId: 'tk_1' },
  { at: 150, agentId: 'a1', kind: 'draft', outcome: 'done', taskId: 'tk_2' },
];
R.laNone      = xpLastAttempt(LED, 'tk_missing', AG);
R.laNoTaskId  = xpLastAttempt(LED, null, AG);
R.laLatest    = xpLastAttempt(LED, 'tk_1', AG);          // 200 beats 100
R.laText      = xpLastAttemptText(xpLastAttempt(LED, 'tk_1', AG));
R.laDoneText  = xpLastAttemptText(xpLastAttempt(LED, 'tk_2', AG));  // '' — nothing to warn about
R.laFiredName = xpLastAttempt(LED, 'tk_1', [{ id: 'a1', name: 'Miko' }]);   // a5 no longer hired
R.laFiredText = xpLastAttemptText(R.laFiredName);
R.laNullAgents= xpLastAttemptText(xpLastAttempt(LED, 'tk_1', null));
R.laEmptyLed  = xpLastAttempt([], 'tk_1', AG);
console.log(JSON.stringify(R));
''')

    # xpRecord — append-only + the one-done-per-job promise
    check('appends a done entry', out['appends'])
    check('never mutates the input ledger', out['appendOnly'])
    check('a job completes once (same agent)', out['dedupeDone'])
    check('a job completes once (any agent)', out['dedupeAcrossAgents'])
    check('a snag after a done still records', out['snagAfterDoneOk'])
    check('snag then done on one task both record', out['snagThenDone'])
    check('rejects an entry without an agent', out['rejectsNoAgent'])
    check('rejects an unknown outcome', out['rejectsBadOutcome'])
    check('tolerates a non-array ledger', out['toleratesNonArray'])
    check('kind defaults to task', out['defaultsKind'] == 'task')
    check('unknown kinds are preserved verbatim', out['keepsUnknownKind'] == 'weird')
    check('titles are capped at 80 chars', out['truncatesTitle'] == 80)

    # xpStats
    check('counts jobs', out['jobs'] == 4, str(out['jobs']))
    check('counts snags', out['snags'] == 1)
    check('a snag resets the streak', out['streak'] == 2, str(out['streak']))
    check('per-kind tallies', out['byKindBrief'] == 3)
    check('affinity is the strongest earned kind',
          out['affinity'] == {'kind': 'brief', 'count': 3}, repr(out['affinity']))
    check('agents are isolated', out['otherAgent'] == 1)
    check('empty ledger yields zeros',
          out['emptyStats']['jobs'] == 0 and out['emptyStats']['streak'] == 0
          and out['emptyStats']['affinity'] is None)
    check('trailing snag means streak 0', out['trailingSnag'] == 0)
    check('unbroken run counts fully', out['allDoneStreak'] == 2)
    check('generic tasks are never a specialty', out['noGenericAffinity'] is None)
    check('one completion is not an affinity yet', out['noSingleAffinity'] is None)

    # labels + kinds
    check('plural label', out['labelPlural'] == '12 research briefs')
    check('singular label', out['labelSingular'] == '1 night shift')
    check('unknown kind labels as jobs', out['labelUnknown'] == '2 jobs')
    check('starter task keeps its card kind', out['kindStarter'] == 'brief')
    check('plain task is a generic job', out['kindPlain'] == 'task')
    check('unrecognised starter falls back', out['kindWeird'] == 'task')
    check('null task tolerated', out['kindNull'] == 'task')
    check('affinity text reads like a résumé line', out['affText'] == '3 research briefs')
    check('affinity text empty when unearned', out['affTextEmpty'] == '')

    # ── xpLastAttempt: the card remembers who already tried ───────────
    # A snagged task returns to the inbox unassigned (correct — it must stay
    # re-delegatable), but the card used to come back looking untouched, so
    # the obvious next move was handing it back to the coworker it just beat.
    check('no attempt on this task reads as nothing', out['laNone'] is None)
    check('a missing task id is tolerated', out['laNoTaskId'] is None)
    check('the LATEST attempt wins, not the first',
          out['laLatest']['agentId'] == 'a5' and out['laLatest']['at'] == 200,
          str(out['laLatest']))
    check('a snag reads as one office sentence',
          out['laText'] == 'Kenji hit a snag on this', out['laText'])
    check('a task whose last attempt SUCCEEDED says nothing',
          out['laDoneText'] == '', repr(out['laDoneText']))
    check('a let-go coworker keeps the fact, loses the name',
          out['laFiredName']['name'] is None, str(out['laFiredName']))
    check('...and still reads as a sentence, never a blank or "undefined"',
          out['laFiredText'] == 'someone since let go hit a snag on this',
          out['laFiredText'])
    check('a null roster is tolerated', 'hit a snag on this' in out['laNullAgents'])
    check('an empty ledger reads as nothing', out['laEmptyLed'] is None)

    print()
    if FAILS:
        print(f'experience ledger: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('experience ledger: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
