#!/usr/bin/env python3
"""A coworker's overnight Night Shift run left zero mark on their record.

`app/experience.jsx`'s own ledger contract draws no line between mission
kinds: "What counts as a job: a TASK completion... and a MISSION that ran
its schedule." The roster card and Inspect panel both read `xpStats()` for
Jobs, streak, and Snags, and app.jsx's own Gazette code calls a finished
Night Shift run "the Gazette's lead story — [it alone] justif[ies] the
paper even when nothing else happened while away."

But `recordXp` (app.jsx) / `setExperience` had exactly two callers before
this fix: app.jsx's task-completion paths, and missions.jsx's own client
loop for in-browser Research missions. Night Shift missions run inside
night_runner.py, a separate server-side process that writes finished runs
straight to mission-runs.json and has no way to call into the browser's
ledger itself. Every consumer of `/missions/runs` (the Missions modal, the
office floor board, the Gazette) only ever DISPLAYED these runs — nothing
recorded them. A coworker could run a clean 6-round overnight shift with 4
vault notes written, or fail every round of one, and their roster card's
Jobs/streak/Snags would read exactly as it did the day before.

The fix folds Night Shift runs into the ledger from the same poll that
already lifts `/missions/runs` into `nightShiftRuns` (task #28), keyed by
`taskId === run.id` against a live ref of the ledger — the same key the
task and mission paths already use — so a run already recorded is never
recorded twice across repeat 15s polls.

Run: python3 scripts/test_night_shift_runs_reach_the_xp_ledger.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
EXPERIENCE = ROOT / 'app' / 'experience.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def extract(text, start_marker, end_marker):
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j + len(end_marker)]


def run(js):
    proc = subprocess.run(['node', '--input-type=module', '-e', js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the real files')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def collect(runs, ledger=None):
    """Drive the real per-run recordXp decision block from app.jsx, plus
       the real xpRecord/xpStats from app/experience.jsx, against a given
       starting ledger. Returns the final ledger and the recorded calls."""
    app = APP.read_text(encoding='utf-8')
    exp = EXPERIENCE.read_text(encoding='utf-8')
    loop = extract(app, '        for (const r of (rj.runs || [])) {', '\n        }')
    xp_record = extract(exp, 'function xpRecord(', '\n}\n')
    xp_stats = extract(exp, 'function xpStats(', '\n}\n')
    js = """
const rj = { runs: %s };
let ledger = %s;
const calls = [];
const experienceRef = { current: ledger };
const recordXp = (entry) => { calls.push(entry); ledger = xpRecord(ledger, entry); experienceRef.current = ledger; };
/* task #36 threaded a logActivity call through this same loop, resolving
   the run's agent off agentsRef — mocked here so this file keeps testing
   only what it's about (the XP ledger), same as it did before that fix. */
const agentsRef = { current: [] };
const logActivity = () => {};
%s
%s
%s
console.log(JSON.stringify({ ledger, calls }));
""" % (json.dumps(runs), json.dumps(ledger or []), loop, xp_record, xp_stats)
    return run(js)


def main():
    print('a Night Shift run reaches the same ledger a task or an in-browser mission does')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    app = APP.read_text(encoding='utf-8')

    # ── 0. plumbing: the ref this all depends on actually tracks state ──
    check('experienceRef exists and is kept in sync with `experience`',
          'const experienceRef = useRefA([]);' in app
          and "useEffectA(() => { experienceRef.current = experience; }, [experience]);" in app,
          'app.jsx: without this the dedup check below reads stale or empty '
          'state and either never fires or double-records every poll')

    # ── 1. a clean finished run records a job ────────────────────────────
    clean = {'id': 'nsh_run_1', 'agentId': 'a1', 'topic': 'competitor scan',
              'startedAt': 1000, 'finishedAt': 9000, 'iterations': 6, 'errors': 0}
    R = collect([clean])
    check('a clean overnight run records exactly one entry',
          len(R['calls']) == 1, R.get('calls'))
    if R['calls']:
        c = R['calls'][0]
        check('...as a done job, keyed to the run and its agent',
              c.get('outcome') == 'done' and c.get('agentId') == 'a1'
              and c.get('kind') == 'mission' and c.get('taskId') == 'nsh_run_1',
              c)
    # pull xpStats over the resulting ledger to prove the roster card's own
    # math sees it, not just that recordXp was called with a plausible shape
    exp = EXPERIENCE.read_text(encoding='utf-8')
    xp_stats_src = extract(exp, 'function xpStats(', '\n}\n')
    stats = run("""
const ledger = %s;
%s
console.log(JSON.stringify(xpStats(ledger, 'a1')));
""" % (json.dumps(R['ledger']), xp_stats_src))
    check('...and the roster card\'s own xpStats() counts it as a job',
          stats.get('jobs') == 1 and stats.get('streak') == 1, stats)

    # ── 2. a run that failed every round records a snag, not a done ─────
    failed = {'id': 'nsh_run_2', 'agentId': 'a1', 'topic': 'flaky brain',
               'startedAt': 1000, 'finishedAt': 9000, 'iterations': 0, 'errors': 4}
    R2 = collect([failed])
    check('a run that never produced a good round still records — as a snag',
          len(R2['calls']) == 1 and R2['calls'][0].get('outcome') == 'snag',
          R2.get('calls'))

    # ── 3. still-running / never-really-started runs record nothing ─────
    still_running = {'id': 'nsh_run_3', 'agentId': 'a1', 'topic': 'wip',
                       'startedAt': 1000, 'finishedAt': 0, 'iterations': 2, 'errors': 0}
    empty_finish = {'id': 'nsh_run_4', 'agentId': 'a1', 'topic': 'never started',
                      'startedAt': 1000, 'finishedAt': 9000, 'iterations': 0, 'errors': 0}
    R3 = collect([still_running, empty_finish])
    check('a mid-flight run (finishedAt: 0) is not recorded yet',
          not any(c['taskId'] == 'nsh_run_3' for c in R3['calls']), R3.get('calls'))
    check('a finished run with neither a good round nor an error is not a job',
          not any(c['taskId'] == 'nsh_run_4' for c in R3['calls']), R3.get('calls'))

    # ── 4. the dedup: seeing the same run again across polls records once ─
    already = [{'at': 1, 'agentId': 'a1', 'kind': 'mission', 'outcome': 'done', 'taskId': 'nsh_run_1'}]
    R4 = collect([clean], ledger=already)
    check('a run already in the ledger is never recorded twice',
          len(R4['calls']) == 0,
          f'{R4.get("calls")!r} — this is the 15s-poll dedup: without it, a '
          'finished run still showing in /missions/runs would inflate Jobs '
          'or restamp a Snag on every single poll forever')

    # ── 5. two runs finishing in the same poll both land ─────────────────
    other_agent_snag = dict(failed, id='nsh_run_5', agentId='a2')
    R5 = collect([clean, other_agent_snag])
    check('two different finished runs in one poll both record',
          len(R5['calls']) == 2
          and {c['taskId'] for c in R5['calls']} == {'nsh_run_1', 'nsh_run_5'},
          R5.get('calls'))

    print()
    if FAILS:
        print(f'night shift XP: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('night shift XP: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
