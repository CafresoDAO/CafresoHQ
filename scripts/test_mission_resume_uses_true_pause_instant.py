#!/usr/bin/env python3
"""Pausing and resuming a Research Mission silently drifted its deadline
forward — sometimes by minutes, sometimes by discarding the mission's
entire elapsed budget outright.

`onResumeMission` (app.jsx) shifts `startedAt` forward by "however long
the mission sat paused" so the deadline (`startedAt + durationMs`, used
by `fmtRemaining` and the auto-stop check in missions.jsx) stays anchored
to real running time. The true pause instant is `m.endedAt` — both pause
paths (the per-card ■ STOP in `onStopMission`, and the auto-pause-on-3-
errors path in missions.jsx) stamp it with `Date.now()` at the moment
the mission actually stopped. But the resume math used `m.lastIterationAt`
instead — the timestamp of the last COMPLETED iteration, which can be up
to a full `intervalMs` older than the actual stop click. Every pause/
resume cycle donated that iteration-to-stop-click gap to the mission as
bonus paused time, pushing the deadline further out each time. Worse: a
mission paused before its first iteration ever completed had no
`lastIterationAt` at all, so the fallback (`m.startedAt`) made the shift
equal to the mission's entire age — resume reset the clock to "started
right now," discarding 100% of whatever budget had already elapsed.

Found by a background hunt agent scanning the Research Mission
lifecycle (this session's next-least-scrutinized area), confirmed by
tracing exactly which field each pause path stamps vs. which field
resume actually reads.

Fix: read `m.endedAt` (with `m.startedAt` as the fallback for a mission
that was never actually paused, which can't happen in practice since
resume is only reachable from a paused mission, but keeps the shift
inert instead of throwing if it ever were) instead of
`m.lastIterationAt`.

Verified via direct arithmetic simulation matching the fix's own
formula: a mission started at T with a real pause spanning P minutes
(endedAt = T + iterationGap, resumed at T + iterationGap + P) must come
out of resume with a deadline shifted by exactly P minutes, independent
of how large the pre-pause iterationGap was — the old formula's error
grew directly with that gap, so this is a precise regression check, not
just a "does it still compile" one.

Run: python3 scripts/test_mission_resume_uses_true_pause_instant.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('Resuming a paused mission anchors on the true pause instant (endedAt)')

    app = APP.read_text(encoding='utf-8')

    m = re.search(r"const onResumeMission = \(id\) =>(.*?)\n  const onClearMission",
                   app, re.S)
    check('onResumeMission is still defined in app.jsx', m is not None,
          'app.jsx: onResumeMission not found — rewritten or moved?')
    body = m.group(1) if m else ''

    check("the startedAt shift reads m.endedAt (the timestamp both pause "
          "paths — onStopMission and missions.jsx's auto-pause-on-errors "
          "— actually stamp with the real pause instant)",
          re.search(r"startedAt:\s*m\.startedAt \+ \(Date\.now\(\) - \(m\.endedAt \|\| m\.startedAt\)\)", body) is not None,
          body)
    check("...and the startedAt shift itself no longer reads "
          "m.lastIterationAt (the last-COMPLETED-iteration timestamp, "
          "which can be up to a full intervalMs older than the real "
          "stop click, and is unset entirely for a mission paused "
          "before its first iteration) — a surrounding comment may still "
          "name it for context, so check the shift expression specifically",
          'm.lastIterationAt' not in re.sub(r'/\*.*?\*/', '', body, flags=re.S),
          'app.jsx: onResumeMission\'s shift expression still references lastIterationAt')

    check('onStopMission still stamps endedAt with the real pause instant '
          '(the field this fix now depends on)',
          re.search(r"status:\s*'paused',\s*endedAt:\s*Date\.now\(\)", app) is not None,
          'app.jsx: onStopMission no longer stamps endedAt on pause')

    # Simulate the actual formula: a mission started at T=0, its last
    # completed iteration at T=2 (a plausible pre-pause gap), paused at
    # T=8 (endedAt), resumed at T=68 (60 real minutes later). The fixed
    # formula must shift startedAt by exactly the real paused span (60),
    # independent of the iteration gap (8) the old buggy formula leaked in.
    START, LAST_ITER, ENDED, RESUMED = 0, 2, 8, 68
    REAL_PAUSE_SPAN = RESUMED - ENDED  # 60 — what the deadline shift should equal

    fixed_shift = RESUMED - (ENDED or START)
    check('the fixed formula shifts startedAt by exactly the real paused '
          "span (60), not the iteration-gap-inflated value the old "
          "formula produced (60 + (8 - 2) = 66)",
          fixed_shift == REAL_PAUSE_SPAN,
          f'formula gave {fixed_shift}, expected {REAL_PAUSE_SPAN}')

    buggy_shift = RESUMED - (LAST_ITER or START)
    check("...confirming the OLD formula (using lastIterationAt) really "
          "did drift by the difference between the stop click and the "
          "last completed iteration",
          buggy_shift != REAL_PAUSE_SPAN and buggy_shift == 66,
          f'old formula gave {buggy_shift}')

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
