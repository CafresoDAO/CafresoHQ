#!/usr/bin/env python3
"""A mission an hour into a 4-hour run looked exactly like a finished one.

Reproduced by reading the source. `night_runner.py`'s `run_mission()` sets
`run['finishedAt'] = 0` when the run record is created and only assigns a
real timestamp at the very end, after its whole iteration loop exits —
whether that end is normal completion, an abort, or an error-streak pause.
Every iteration in between calls `on_progress(dict(run))` with a snapshot
where `finishedAt` is still 0 (serve.py's `_night_log_run` writes that
snapshot straight to mission-runs.json, unfiltered).

Two surfaces read `/missions/runs` and render each row from `r.lastError`
alone — `✓` if falsy, `⚠` if not — with no check on `r.finishedAt` at all:
`missions.jsx`'s "RECENT NIGHT RUNS" list and `views/terminal.jsx`'s
`hq night runs` command. A mission scheduled for 6 rounds over an hour that
had completed only its first round — real progress, five more pending —
showed `✓ ... 1 round · 1 note`: visually identical to a mission that had
actually finished successfully. Nothing on screen said it wasn't done.

(app.jsx's Gazette filter already trusts `finishedAt` as the completion
signal for this exact field — `(x.finishedAt||0) > prevSeen` — so this is
two surfaces that never adopted a check the rest of the app already relies
on, not a case where the signal didn't exist.)

Run: python3 scripts/test_a_running_mission_looked_finished.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MISSIONS = (ROOT / 'missions.jsx').read_text(encoding='utf-8')
TERMINAL = (ROOT / 'views/terminal.jsx').read_text(encoding='utf-8')
NIGHT_RUNNER = (ROOT / 'night_runner.py').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('a running mission looked finished')

    # ── 0. finishedAt really is 0 for the whole run, not just at creation ──
    # (confirms this is a real snapshot-in-flight scenario, not hypothetical)
    check('run record is created with finishedAt: 0',
          "'finishedAt': 0," in NIGHT_RUNNER)
    check('finishedAt is only assigned a real value after the iteration loop',
          re.search(r"while int\(time\.time\(\) \* 1000\) < deadline:[\s\S]*?"
                     r"run\['finishedAt'\] = int\(time\.time\(\) \* 1000\)",
                     NIGHT_RUNNER) is not None)
    check('on_progress fires mid-loop with that still-0 snapshot',
          re.search(r"if on_progress:\s*\n\s*try:\s*\n\s*on_progress\(dict\(run\)\)",
                     NIGHT_RUNNER) is not None)

    # ── 1. missions.jsx's RECENT NIGHT RUNS list now distinguishes in-flight ──
    m = re.search(r"RECENT NIGHT RUNS[\s\S]{0,1500}", MISSIONS)
    check('found the RECENT NIGHT RUNS block', m is not None)
    block = m.group(0) if m else ''
    check('missions.jsx checks r.finishedAt before deciding the row icon',
          'r.finishedAt' in block,
          '— a mid-flight run would render identically to a finished one')
    check('...the icon itself branches on inFlight, not just lastError',
          re.search(r"inFlight \? '▶'", block) is not None,
          '— an in-flight run must not fall through to the ✓/⚠ ternary')
    check('...and says so in words, not just a different glyph',
          re.search(r"inFlight \? ' · still running'", block) is not None)

    # ── 2. views/terminal.jsx\'s `hq night runs` twin gets the same check ──
    t = re.search(r"args\[0\] === 'runs'\)[\s\S]{0,700}", TERMINAL)
    check('found the `hq night runs` handler', t is not None)
    tblock = t.group(0) if t else ''
    check('terminal.jsx checks r.finishedAt too',
          'r.finishedAt' in tblock,
          '— the CLI twin of the same list had the identical gap')
    check('...the icon itself branches on inFlight, not just lastError',
          re.search(r"inFlight \? '▶'", tblock) is not None,
          '— an in-flight run must not fall through to the ✓/⚠ ternary')
    check('...and also says "still running" rather than staying silent',
          re.search(r"inFlight \? ' · still running'", tblock) is not None)

    print()
    if FAILS:
        print('%d check(s) failed:' % len(FAILS))
        for f in FAILS:
            print('  - ' + f)
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
