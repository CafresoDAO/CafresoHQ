#!/usr/bin/env python3
"""The "Research missions" badge said 0 while a night shift was running.

Two surfaces show a live count of running research missions and both open
the same MissionsModal when clicked:

    app.jsx (mobile tab bar)
        missionCount={missions.filter(m => m.status === 'running').length}
    app.jsx (desktop "⌗ ROOMS" menu, key: 'research')
        count: missions.filter(m=>m.status==='running').length

Both counted only `missions` — app.jsx's own in-browser Research-mission
state (see the doc comment on `nightShiftBoard`, a few hundred lines
above: `missions` "only ever holds in-browser Research missions"). Server
-side Night Shift runs ("close the laptop, work continues") live in
`nightShiftBoard`, polled every 15s from `/missions/scheduled` +
`/missions/runs` specifically so surfaces above the Missions modal could
see them running. Both counters skipped it.

The modal behind either button — `MissionsModal`, opened by both
`onOpenResearch`/`setMissionsOpen(true)` — renders `<NightShiftSection
agents={agents} />` (missions.jsx), i.e. the exact content this badge is
a doorway to. Schedule a night shift with nothing running in the browser
tab: both badges read 0/blank, and the room behind the door is not empty.

This is the same bug class already fixed twice this session for the same
underlying gap — `onStopAll` (`running = localRunning + nightRunning`)
and the `anyBusy` prop (`|| nightShiftBoard.length > 0`) — applied here
to the two remaining counters that were never updated.

**The fix** adds `+ nightShiftBoard.length` to both count expressions.

Run: python3 scripts/test_research_badge_counts_night_shift_too.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / 'app.jsx').read_text(encoding='utf-8')
OFFICE = (ROOT / 'ui/office.jsx').read_text(encoding='utf-8')
MISSIONS = (ROOT / 'missions.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('Research missions badge: does it count what the modal behind it shows?')

    # ── 1. both count expressions fold in nightShiftBoard ────────────────
    mobile_m = re.search(
        r"missionCount=\{missions\.filter\(m => m\.status === 'running'\)\.length"
        r"(\s*\+\s*nightShiftBoard\.length)?\}", APP)
    check('mobile tab bar missionCount includes nightShiftBoard.length',
          mobile_m is not None and mobile_m.group(1) is not None,
          mobile_m.group(0) if mobile_m else 'prop not found at all')

    desktop_m = re.search(
        r"key: 'research',[^}]*?count: missions\.filter\(m=>m\.status==='running'\)\.length"
        r"(\s*\+\s*nightShiftBoard\.length)?", APP, re.S)
    check("desktop '⌗ ROOMS' menu's research count includes nightShiftBoard.length",
          desktop_m is not None and desktop_m.group(1) is not None,
          desktop_m.group(0) if desktop_m else 'menu item not found at all')

    # ── 2. the modal behind both buttons is the one that actually shows
    #        night shift missions — corroborates the badge SHOULD count them
    check('MobileTabBar\'s onOpenResearch opens the same modal as the desktop menu',
          'onOpenResearch={() => setMissionsOpen(true)}' in APP, APP[:0])
    check("MissionsModal renders NightShiftSection — the room behind the badge "
          "really does contain night shift missions",
          '<NightShiftSection agents={agents} />' in MISSIONS, MISSIONS[:0])

    # ── 3. MobileTabBar still just forwards missionCount as-is — the fix
    #        belongs at the call site (app.jsx), not smuggled into the
    #        component, so a future caller with different needs isn't stuck
    #        with this assumption baked in
    check("MobileTabBar's Research badge still just reads the missionCount prop "
          "it's given, unchanged — the combining logic lives at the call site",
          "badge: missionCount || 0" in OFFICE, OFFICE[:0])

    # ── 4. mechanism, run for real: with nothing running in-browser but two
    #        night shifts scheduled, both expressions must still read 2 ──────
    if not shutil.which('node'):
        print('  SKIP  node not on PATH — the mechanism check needs it')
    else:
        js = r'''
const missions = [{status: 'paused'}, {status: 'done'}];
const nightShiftBoard = [{id: 'n1'}, {id: 'n2'}];
const mobileMissionCount = missions.filter(m => m.status === 'running').length + nightShiftBoard.length;
const desktopResearchCount = missions.filter(m=>m.status==='running').length + nightShiftBoard.length;
console.log(JSON.stringify({ mobileMissionCount, desktopResearchCount }));
'''
        p = subprocess.run(['node', '-e', js], capture_output=True, text=True, timeout=15)
        if p.returncode != 0:
            check('the mechanism harness runs', False, p.stderr.strip()[:400])
        else:
            out = json.loads(p.stdout)
            check('a night-shift-only office (nothing running in-browser) still '
                  'shows a non-zero mobile badge',
                  out['mobileMissionCount'] == 2, out)
            check('...and a non-zero desktop menu count, matching what '
                  'NightShiftSection would actually render',
                  out['desktopResearchCount'] == 2, out)

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
