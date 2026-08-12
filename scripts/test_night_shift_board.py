#!/usr/bin/env python3
"""The office-floor Night Shift board was wired to the wrong `missions`.

Found live during a northstar MVP audit pass: scheduled a real server-side
Night Shift mission (POST /missions/schedule, agent Llama, "close the laptop,
work continues"), confirmed it was genuinely running via
hq-state/mission-runs.json (startedAt set, finishedAt: 0, iterations
advancing) — and watched the office floor bulletin board the whole time. It
never showed a thing.

Root cause: `OfficeView`'s Night Shift board (ui/office.jsx) filtered a
`missions` prop that app.jsx fills with browser-only "Research" missions
(the ones with the "keep this tab open" warning). Server-side Night Shift
schedules/runs (night_runner.py) are polled from /missions/scheduled and
/missions/runs entirely inside `NightShiftSection`'s own component state
(missions.jsx) and were never lifted up to app.jsx, let alone passed to
OfficeView. The board's render code was correct; its data source was
disconnected from the feature it exists to show. A Night Shift mission
could run for hours and the boss's own office floor would say nothing.

Fix: app.jsx now polls /missions/scheduled itself (same 15s cadence
NightShiftSection already uses), cross-references the `running` id list
against `schedules` for topic/agent, and passes the result to OfficeView as
a new `nightShiftBoard` prop. office.jsx's derivation reads that prop
instead of the browser-mission `missions` state.

Static checks only — these are component closures, not exported pure
functions (same constraint as this session's other views/*.jsx,
features.jsx and app.jsx suites).

Run: python3 scripts/test_night_shift_board.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / 'app.jsx'
OFFICE = ROOT / 'ui' / 'office.jsx'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('night shift board — real server-side data on the office floor')
    if not APP.is_file() or not OFFICE.is_file():
        print('  FAIL  missing source file(s)')
        return 1
    app_src = APP.read_text(encoding='utf-8')
    office_src = OFFICE.read_text(encoding='utf-8')

    # ── app.jsx: the poll exists and feeds a dedicated state, not `missions` ──
    check('app.jsx declares nightShiftBoard state',
          bool(re.search(r"const \[nightShiftBoard, setNightShiftBoard\] = useStateA\(\[\]\);", app_src)),
          'app.jsx: needs its own state — the browser-mission `missions` '
          'array is the wrong data source for this feature')
    check("the poll hits /missions/scheduled",
          "'/missions/scheduled'" in app_src or '/missions/scheduled' in app_src,
          'app.jsx: must fetch the same server-side schedule endpoint '
          'NightShiftSection uses')
    check('the poll cross-references `running` ids against `schedules`',
          bool(re.search(r"runningIds\.has\(s\.id\)", app_src)),
          'app.jsx: a schedule is only board-worthy while it is actually '
          'executing right now, not just scheduled for later')
    check('board entries carry status: "running"',
          bool(re.search(r"status:\s*'running'", app_src)),
          "app.jsx: office.jsx's filter reads m.status === 'running'")
    check('the poll is visibility-aware (skips while the tab is hidden)',
          bool(re.search(r"nightShiftBoard[\s\S]{0,1500}document\.hidden", app_src)),
          'app.jsx: same convention as the backend-health probe — avoid '
          'polling a backgrounded tab')

    # ── app.jsx passes the new prop into <OfficeView>, not the old one ────────
    check('<OfficeView> receives nightShiftBoard={nightShiftBoard}',
          bool(re.search(r'nightShiftBoard=\{nightShiftBoard\}', app_src)),
          'app.jsx: OfficeView must actually receive the real data')

    # ── ui/office.jsx: signature + derivation read the new prop ───────────────
    check('OfficeView accepts a nightShiftBoard prop',
          bool(re.search(r'function OfficeView\(\{[^}]*nightShiftBoard = \[\][^}]*\}\)', office_src)),
          'ui/office.jsx: the component signature must declare the new prop')
    check('OfficeView no longer takes the browser-mission `missions` prop',
          not bool(re.search(r'function OfficeView\(\{[^}]*[^a-zA-Z]missions = \[\][^}]*\}\)', office_src)),
          'ui/office.jsx: the old prop name should be gone, not just shadowed — '
          'keeping it around invites something to silently start feeding it '
          'browser missions again')
    check('nightMissions derives from nightShiftBoard',
          bool(re.search(r"const nightMissions = \(nightShiftBoard \|\| \[\]\)\.filter", office_src)),
          'ui/office.jsx: the derivation must read the prop that actually '
          'carries server-side Night Shift data')

    print()
    if FAILS:
        print(f'night shift board: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('night shift board: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
