#!/usr/bin/env python3
"""A mission timer that fires after its tab lost the runner lease must not run (missions.jsx).

Bug: useMissionRunner elects ONE runner tab via a localStorage lease
(MISSION_LEASE_KEY) precisely so two open tabs never both fire iterations of
the same mission — duplicate vault notes, double token burn, racing PUTs.
But the lease was only consulted when ARMING a timer (the scheduling loop's
`if (!_haveMissionLease()) continue;`). Inside `fire` itself the call was
`_haveMissionLease();` with the RESULT DISCARDED — a heartbeat renewal only.

So a tab that lost the lease after arming a timer — the 5s heartbeat starved
past the 15s TTL by background-tab timer throttling, a laptop suspend, or
the pagehide handover — still held that timer, and when it fired it ran a
full iteration concurrently with the new leader tab's. The exact failure the
lease exists to prevent, through the one code path the lease never gated.

Fix: `fire` now gates on the result — `if (!_haveMissionLease()) return;` —
which still renews the heartbeat when this tab holds (or can reclaim a
stale) lease, and stands down when another tab verifiably owns it.

This lifts the REAL useMissionRunner source out of missions.jsx
(brace-balanced extraction, like test_workspace_terminal_key.py), isolates
the `fire` callback the same way, and checks the invariant directly:
inside `fire`, _haveMissionLease() must be consumed as a guard, never called
as a bare result-discarded statement; and the scheduling loop's own arm-time
gate must still be there (the fix must be an addition, not a relocation).
Run: python3 scripts/test_mission_fire_checks_lease_before_running.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'missions.jsx'

FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + detail) if detail else ""}')


def extract_braced(src, open_pat):
    """Brace-balanced extraction: match `open_pat` (which must end at or just
    before a '{') and return the span through its balancing '}'."""
    m = re.search(open_pat, src)
    if not m:
        return None
    i = src.find('{', m.start())
    if i == -1:
        return None
    depth = 0
    j = i
    while j < len(src):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
        j += 1
    return None


def strip_comments(src):
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'(^|\s)//[^\n]*', r'\1', src)


def main():
    print('missions — fire() must consult the runner lease, not just renew it')
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1
    text = SRC.read_text(encoding='utf-8')

    runner = extract_braced(text, r'function\s+useMissionRunner\s*\([^)]*\)\s*\{')
    check('useMissionRunner extracted from missions.jsx', runner is not None)
    if runner is None:
        print('\n1 failure(s)')
        return 1

    fire = extract_braced(runner, r'const\s+fire\s*=\s*async\s*\(\s*\)\s*=>\s*\{')
    check('fire callback extracted from useMissionRunner', fire is not None)
    if fire is None:
        print('\n2 failure(s)')
        return 1

    fire_code = strip_comments(fire)
    runner_code = strip_comments(runner)

    # 1) The fix: fire must stand down when this tab does not hold the lease.
    gated = re.search(r'if\s*\(\s*!\s*_haveMissionLease\s*\(\s*\)\s*\)\s*return\b',
                      fire_code)
    check('fire gates on the lease — if (!_haveMissionLease()) return', bool(gated))

    # 2) The regression: a bare, result-discarded call in statement position
    #    (`_haveMissionLease();`) is exactly the old renew-only form. Every
    #    remaining call inside fire must be consumed (inside an if/assignment).
    bare = re.findall(r'(?:^|[;{}\n])\s*_haveMissionLease\s*\(\s*\)\s*;', fire_code)
    check('no bare result-discarded _haveMissionLease(); left inside fire',
          len(bare) == 0, repr(bare))

    # 3) The arm-time gate in the scheduling loop must survive too — the fix
    #    is an ADDITION at fire time, not a relocation of the existing guard.
    loop_only = runner_code.replace(fire_code, '')
    arm_gate = re.search(r'if\s*\(\s*!\s*_haveMissionLease\s*\(\s*\)\s*\)\s*continue\b',
                         loop_only)
    check('scheduling loop keeps its own arm-time lease gate (continue)', bool(arm_gate))

    print()
    print(('FAILED: %s' % FAILS) if FAILS else 'mission fire lease gate: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
