#!/usr/bin/env python3
"""A mission auto-paused after three errors in a row never touched the XP
ledger — so §5's own promise ("Outcomes: 'done' or 'snag' (a failed run —
resets the streak)") and the roster tooltip's promise ("N runs came back
empty or failed") both silently excluded an entire category of real,
non-user-initiated mission failure.

The task path has always drawn this correctly: app.jsx's dispatchToAgent
catch block distinguishes an aborted (user-stopped) run from a genuine
failure via the controller's own abort signal, and only records a snag
for the latter (`if (!aborted) recordXp({..., outcome:'snag'})`). Missions
draw the identical distinction in their own data model — `pauseNote` for a
boss-stop, `lastError` for a real failure (see
scripts/test_a_paused_mission_says_why.py) — but the auto-pause branch
that stamps `lastError` after three consecutive errors never called
`recordXp` at all. A coworker whose scheduled mission errored out three
times in a row and got auto-paused kept a perfect streak on their card,
the same night their work silently failed.

A prior ledger entry (docs/OFFICE_AS_INTERFACE.md, "the ledger's snag
rule") investigated the task-vs-mission snag asymmetry and closed it as
correct — but that investigation only checked dispatchToAgent (chat/DM),
never missions.jsx's own scheduling loop, where this gap actually lived.

This file deliberately does NOT touch the sibling "agent removed" branch
a few lines below the auto-pause block. That branch fires when the
mission's agent no longer exists in `agents` — which happens when the
boss fires/dismisses the coworker mid-mission (dismissal never touches
`missions` state; see app.jsx's onFire-style handlers). That is a boss
action ending the run, not the coworker failing at it — the same shape
as a user-stop, which §5 explicitly keeps off the ledger. Locking that
exclusion in below alongside the fix, so it reads as a decision, not an
oversight.

Run: python3 scripts/test_mission_failures_write_a_snag.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = ROOT / 'missions.jsx'
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


def main():
    print('a mission that fails for real earns a snag, same as a task')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0

    miss = MISSIONS.read_text(encoding='utf-8')
    exp = EXPERIENCE.read_text(encoding='utf-8')

    # ── 1. extract the real auto-pause block and the real ledger fns ────
    autopause = extract(
        miss,
        '      if ((m.errors || 0) >= 3) {',
        '\n        continue;\n      }',
    )
    check('extracted the auto-pause block', autopause.strip().startswith('if ((m.errors'),
          'missions.jsx shape changed — update the extraction markers')

    xp_record = extract(exp, 'function xpRecord(', '\n}\n')
    xp_stats = extract(exp, 'function xpStats(', '\n}\n')

    FIXTURE = {'id': 'nm_1', 'agentId': 'a1', 'topic': 'watch the ledger',
               'status': 'running', 'errors': 3, 'startedAt': 1000}

    # Drive the real auto-pause block against a mock ctx/setMissions/standDown,
    # wrapped in the same `for (const m of missions)` shape it actually lives
    # inside, since it uses a bare `continue`.
    harness = """
const missions = [%s];
let recorded = null, paused = null, stoodDown = null;
const ctx = { recordXp: (e) => { recorded = e; } };
const setMissions = (fn) => { paused = fn(missions)[0]; };
const standDown = (agentId) => { stoodDown = agentId; };
for (const m of missions) {
  %s
}
%s
%s
let ledger = [];
ledger = xpRecord(ledger, { agentId: 'a1', kind: 'mission', outcome: 'done', taskId: 'earlier', at: 1 });
const beforeStats = xpStats(ledger, 'a1');
ledger = xpRecord(ledger, recorded);
const afterStats = xpStats(ledger, 'a1');
console.log(JSON.stringify({ recorded, paused, stoodDown, beforeStats, afterStats }));
""" % (json.dumps(FIXTURE), autopause, xp_record, xp_stats)
    R = run(harness)

    check('the auto-pause records a snag',
          R['recorded'] is not None and R['recorded'].get('outcome') == 'snag',
          f'recordXp was called with {R["recorded"]!r} — a mission auto-paused '
          'after 3 errors is a real failure and must land a snag, same as the '
          'task path does for a non-aborted error')
    check('...against the mission\'s own agent and id',
          R['recorded'] and R['recorded'].get('agentId') == 'a1'
          and R['recorded'].get('kind') == 'mission' and R['recorded'].get('taskId') == 'nm_1',
          R.get('recorded'))
    check('the mission still auto-pauses (unchanged behavior)',
          R['paused'] and R['paused'].get('status') == 'paused', R.get('paused'))
    check('the agent still stands down (unchanged behavior)',
          R['stoodDown'] == 'a1', R.get('stoodDown'))

    # ── 2. the real ledger math actually breaks the streak ──────────────
    check('before the snag, one completion is one job and a streak of 1',
          R['beforeStats']['jobs'] == 1 and R['beforeStats']['streak'] == 1,
          R.get('beforeStats'))
    check('after the snag, the roster tooltip\'s promise is true: it counts',
          R['afterStats']['snags'] == 1,
          f'{R["afterStats"]!r} — the tooltip on views/core.jsx and ui/panels.jsx '
          'reads "N runs came back empty or failed"; before this fix N could '
          'never include an auto-paused mission')
    check('...and the streak (🔥) actually resets',
          R['afterStats']['streak'] == 0,
          f'{R["afterStats"]!r} — a coworker whose scheduled mission errored out '
          'three times in a row kept a perfect streak on their card')
    check('jobs is untouched by a snag',
          R['afterStats']['jobs'] == 1, R.get('afterStats'))

    # ── 3. the sibling "agent removed" branch stays deliberately silent ─
    removed = re.search(
        r"status: 'error', endedAt: Date\.now\(\), lastError: 'agent removed'",
        miss)
    check('the "agent removed" branch still exists as expected',
          bool(removed), 'missions.jsx shape changed')
    if removed:
        # Look at the ~200 chars around the match for a recordXp call —
        # there must be none. This is the boundary of the fix, checked so a
        # future edit that "completes the pattern" here gets caught: firing
        # a coworker mid-mission is a boss action, not their failure.
        window = miss[removed.start():removed.start() + 260]
        check('...and still does not record a snag for a boss-caused dismissal',
              'recordXp' not in window,
              'a coworker fired mid-mission would be charged a snag for a run '
              'the boss ended, not one they failed — the same thing §5 already '
              'refuses to do for a plain user-stop')

    # ── 4. exactly one new call site, in the right place ────────────────
    sites = [m.start() for m in re.finditer(r'ctx\.recordXp\(', miss)]
    check('missions.jsx now has exactly 4 recordXp call sites',
          len(sites) == 4,
          f'found {len(sites)} — 3 pre-existing "done" sites (self-complete, '
          'deadline-reached in the scheduling loop, deadline-reached at fire '
          'time) plus this new snag site')

    print()
    if FAILS:
        print(f'mission snag recording: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:3]))
        return 1
    print('mission snag recording: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
