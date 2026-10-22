#!/usr/bin/env python3
"""cafresohq_state used to run two recurring timers forever: a payroll scan
every 300 s and a Night Shift wake scan every 120 s, 1008 paid messages a
day on a canister that is idle almost all of the time, with wake switched
off on mainnet. A tick is a message the canister pays for whether or not it
has work, and the state canister has been wiped twice by running dry.

So, like the hiring hall, each loop now aims ONE setTimer at the earliest
moment its scan could act and re-aims from what is left; nothing due, no
timer. This suite pins that design by reading the source, and compiles it
with the pinned dfx where it is on PATH:

  * no recurringTimer anywhere, and both timers are setTimers;
  * the due functions mirror their scans' gates: payroll skips paused
    users and inactive salaries, worker pay counts only when pay is
    configured, wake counts nothing unless enabled + URL + secret are set;
  * every path that creates a due moment re-arms: putSalary, unpausing,
    runPayrollNow, search_admin_set_pay, worker POSTs (fulfill accrues),
    putMissionSchedule, enabling wake, both ticks, postupgrade, and the
    fresh-install lines at the actor tail;
  * ticks clear their id before running and never land closer than the old
    scan period (aimAt's floor), the wait is clamped to [1 s, 1 day], and a
    re-arm may only move the tick EARLIER (no starving other tenants);
  * the actor is a classic `actor` without `transient` (moc 0.13.4, the
    pinned dfx 0.24.3's compiler, parses neither keyword);
  * `dfx build cafresohq_state --check` passes (skipped without dfx).

Run:  python3 scripts/test_the_state_canister_ticks_only_when_money_or_a_wake_is_due.py
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src' / 'cafresohq_state' / 'main.mo'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok   ' if cond else '  FAIL ') + name + (('' if cond else '  -- ' + str(detail)[:300])))
    if not cond:
        FAILS.append(name)


def body_of(src, header_regex):
    """Source text of the function whose header matches, up to the next
    top-level `  func`/`  public`/`  system` header at the same indent."""
    m = re.search(header_regex, src)
    if not m:
        return ''
    rest = src[m.end():]
    n = re.search(r'\n  (?:public |system |func |stable |let |var |//)', rest)
    return rest[: n.start()] if n else rest


def main():
    print('the state canister ticks only when money or a wake is due')
    src = SRC.read_text()

    check('no recurring timer anywhere in the state canister', 'recurringTimer' not in src)
    check('the payroll timer is a setTimer aimed in nanoseconds',
          re.search(r'Timer\.setTimer<system>\(#nanoseconds \(Int\.abs\(at - now\(\)\)\), payrollTick\)', src) is not None)
    check('the wake timer is a setTimer aimed in nanoseconds',
          re.search(r'Timer\.setTimer<system>\(#nanoseconds \(Int\.abs\(at - now\(\)\)\), wakeTick\)', src) is not None)
    check('a classic actor: no `persistent actor`, no `transient` (moc 0.13.4 parses neither)',
          re.search(r'^persistent actor', src, re.M) is None and re.search(r'^\s+transient (let|var) ', src, re.M) is None)

    pdue = body_of(src, r'\n  func payrollNextDue\(\) : \?Int \{')
    check('payroll due skips paused users (twice: salaries and pending payouts)',
          pdue.count('if (not isPayrollPaused(user))') == 2, pdue.count('if (not isPayrollPaused(user))'))
    check('payroll due counts only active salaries', 'if (s.active) { best := earliest(best, s.nextRunAt) }' in pdue)
    check('a pending payout is due when the scan would retry it',
          pdue.count('best := earliest(best, po.ts + PENDING_RETRY_MIN_AGE_NS)') == 2)
    check('worker pay counts only when configured, over the same threshold the sweep uses',
          'if (workerPayConfigured()) {' in pdue and 'let threshold = workerPayThreshold();' in pdue)
    sweep = body_of(src, r'\n  func scanWorkerPayouts\(\) : async \(\) \{')
    check('the sweep uses the same gate and threshold helpers',
          'if (not workerPayConfigured()) { return };' in sweep and 'let threshold = workerPayThreshold();' in sweep)

    wdue = body_of(src, r'\n  func wakeNextDue\(\) : \?Int \{')
    check('wake due is null unless enabled + URL + secret (the same gate as scanWake)',
          'if (not wakeEnabled or wakeGatewayUrl == "" or wakeSecret.size() == 0) { return null };' in wdue)
    check('wake due counts only enabled mirrors', 'if (s.enabled) { best := earliest(best, s.nextRunAt) }' in wdue)

    for name, arm in [('payroll', 'armPayrollTimer'), ('wake', 'armWakeTimer')]:
        b = body_of(src, r'\n  func ' + arm + r'<system>\(\) \{')
        due_fn = 'payrollNextDue' if name == 'payroll' else 'wakeNextDue'
        check(f'{name}: nothing due means no timer at all',
              f'let due = switch ({due_fn}()) {{ case (?d) d; case null {{ return }} }};' in b)
        check(f'{name}: aimed through aimAt (floor + clamp)', re.search(r'let at = aimAt\(due, \w+LastTickAt, \w+_SCAN_SECS\);', b) is not None)
        check(f'{name}: an armed timer that fires no later is kept', re.search(r'if \(armedNoLaterThan\(\w+TimerId, \w+TimerAt, at\)\) \{ return \};', b) is not None)
    for name, tick, scans in [('payroll', 'payrollTick', ['scanPayroll', 'scanWorkerPayouts']), ('wake', 'wakeTick', ['scanWake'])]:
        b = body_of(src, r'\n  func ' + tick + r'\(\) : async \(\) \{')
        idv = 'payrollTimerId' if name == 'payroll' else 'wakeTimerId'
        check(f'{name}: the tick clears its id and stamps the floor BEFORE it runs',
              b.lstrip().startswith(f'{idv} := null;'))
        check(f'{name}: a trapped scan cannot stop the re-aim',
              all(f'try {{ await {s}() }} catch (_e) {{}};' in b for s in scans))
        check(f'{name}: the tick re-aims after it runs', b.rstrip().endswith(('armPayrollTimer' if name == 'payroll' else 'armWakeTimer') + '<system>();\n  };'))

    aim = body_of(src, r'\n  func aimAt\(due : Int, lastTickAt : Int, scanSecs : Nat\) : Int \{')
    check('two ticks never land closer than the old scan period', 'let floor = lastTickAt + secsToNs(scanSecs);' in aim)
    check('the wait is clamped between one second and a day',
          'TIMER_MIN_WAIT_NS : Int = 1_000_000_000;' in src and 'TIMER_MAX_WAIT_NS : Int = 86_400_000_000_000;' in src
          and 'n + TIMER_MIN_WAIT_NS' in aim and 'n + TIMER_MAX_WAIT_NS' in aim)
    keep = body_of(src, r'\n  func armedNoLaterThan\(')
    check('a re-arm only moves the tick earlier, and a long-overdue id is presumed dead',
          'armedAt <= at and armedAt + TIMER_DEAD_SLACK_NS > now()' in keep)

    for fn, header, arm in [
        ('putSalary', r'\n  public shared \(msg\) func putSalary\(', 'armPayrollTimer'),
        ('setPayrollPaused', r'\n  public shared \(msg\) func setPayrollPaused\(', 'armPayrollTimer'),
        ('runPayrollNow', r'\n  public shared \(msg\) func runPayrollNow\(', 'armPayrollTimer'),
        ('search_admin_set_pay', r'\n  public shared \(msg\) func search_admin_set_pay\(', 'armPayrollTimer'),
        ('putMissionSchedule', r'\n  public shared \(msg\) func putMissionSchedule\(', 'armWakeTimer'),
        ('setWakeConfig', r'\n  public shared \(msg\) func setWakeConfig\(', 'armWakeTimer'),
    ]:
        check(f'{fn} re-arms the {arm[3:].replace("Timer", "").lower()} timer', f'{arm}<system>()' in body_of(src, header), fn)
    check('a worker POST (fulfill accrues pay) re-arms the payroll timer',
          'case (?res) { if (searchPayRateE8s != 0) { armPayrollTimer<system>() }; res };' in src)
    up = body_of(src, r'\n  system func postupgrade\(\) \{')
    check('an upgrade re-aims both timers from state', 'armPayrollTimer<system>();' in up and 'armWakeTimer<system>();' in up)
    check('a fresh install aims both from the actor tail, as the last declarations',
          src.rstrip().endswith('armPayrollTimer<system>();\n  armWakeTimer<system>();\n}'))

    if shutil.which('dfx'):
        env = dict(os.environ, DFX_VERSION=(ROOT / '.dfx-version').read_text().strip() if (ROOT / '.dfx-version').exists() else '0.24.3')
        r = subprocess.run(['dfx', 'build', 'cafresohq_state', '--check'], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=600)
        check('dfx build cafresohq_state --check passes', r.returncode == 0, (r.stderr or r.stdout)[-400:])
    else:
        print('  skip compile check: dfx is not on PATH')

    if FAILS:
        print(f'FAILED: {len(FAILS)}'); return 1
    print('OK'); return 0


if __name__ == '__main__':
    sys.exit(main())
