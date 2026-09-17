#!/usr/bin/env python3
"""The hiring hall used to tick every 60 seconds, forever, whether or not it
had a job. Measured on the live hall on 2026-09-17: one timer tick costs
~28.6 M cycles on its 13-node subnet with an EMPTY job map (the message plus
the collector's pass over the heap), so the clock alone burned ~41 B/day —
4.2 T in a hundred days — against 0.95 B/day of storage. The state canister
died of the same thing in August.

So the hall no longer ticks on a clock. It aims ONE timer at the next moment
a job can change on its own, runs `tend` then, and re-aims from what is
left; no such job, no timer. This suite pins that design by reading the
source, and compiles it where the pinned dfx is on PATH:

  * no recurringTimer anywhere in the hall;
  * `dueAt` names exactly the five states `tend` can move on its own
    (claimed, delivered, failed-with-escrow, funded, posted) and nothing
    else, so a settled job can never keep the timer alive;
  * every transition INTO one of those states re-arms: postJob, fundJob
    (both branches), claimJob, deliverJob, the public snag path — plus the
    tick itself, postupgrade, and the fresh-install line at the actor tail;
  * the wait is clamped between one second and a day (no busy loop, and a
    daily re-check even if a due time was computed wrong);
  * `rearmTend` is a no-op while a timer is armed, and the tick clears the
    id BEFORE it runs, so a re-arm from inside `tend` cannot double-arm;
  * `dfx build cafresohq_market --check` passes (skipped without dfx).

Run:  python3 scripts/test_the_hall_ticks_only_while_a_job_can_change_on_its_own.py
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'src' / 'cafresohq_market' / 'main.mo'
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
    n = re.search(r'\n  (?:public |system |func |transient |stable |let |var )', rest)
    return rest[: n.start()] if n else rest


def main():
    print('the hall ticks only while a job can change on its own')
    src = SRC.read_text()

    check('no recurring timer anywhere in the hall', 'recurringTimer' not in src)
    check('the one timer is a setTimer aimed in nanoseconds',
          re.search(r'Timer\.setTimer<system>\(#nanoseconds \w+, tendOnce\)', src) is not None)

    due = body_of(src, r'\n  func dueAt\(j : Job\) : \?Int \{')
    states = set(re.findall(r'case \(#(\w+)\)', due))
    check('dueAt names exactly the five states tend can move on its own',
          states == {'claimed', 'delivered', 'failed', 'funded', 'posted'}, states)
    check('a failed job is due only while it still holds escrow',
          re.search(r'case \(#failed\) \{ if \(j\.escrowed > 0\)', due) is not None)
    check('a settled job never keeps the timer alive (the default arm is null)',
          re.search(r'case _ \{ null \}', due) is not None)

    for fn, header in [
        ('postJob',   r'\n  public shared \(msg\) func postJob\('),
        ('fundJob',   r'\n  public shared \(msg\) func fundJob\('),
        ('claimJob',  r'\n  public shared \(msg\) func claimJob\('),
        ('deliverJob', r'\n  public shared \(msg\) func deliverJob\('),
    ]:
        b = body_of(src, header)
        check(f'{fn} re-arms the timer', 'rearmTend<system>()' in b, fn)
    fund = body_of(src, r'\n  public shared \(msg\) func fundJob\(')
    check('fundJob re-arms on BOTH of its funded branches', fund.count('rearmTend<system>()') == 2, fund.count('rearmTend<system>()'))
    check('the public snag path re-arms after releaseClaim',
          re.search(r'releaseClaim\(j, reason\);\n    rearmTend<system>\(\);', src) is not None)
    check('the tick re-aims after it runs',
          re.search(r'func tendOnce\(\) : async \(\) \{\n    tendTimerId := null;\n    try \{ await tend\(\) \} catch \(_\) \{\};\n    rearmTend<system>\(\);', src) is not None)
    check('an upgrade re-aims from the jobs on record',
          'system func postupgrade() { rearmTend<system>() };' in src)
    check('a fresh install aims from the actor tail, as the last declaration',
          src.rstrip().endswith('rearmTend<system>();   // fresh install; MUST be the last declaration\n};'.rstrip()))

    rearm = body_of(src, r'\n  func rearmTend<system>\(\) \{')
    check('rearmTend is a no-op while a timer is armed',
          re.search(r'switch \(tendTimerId\) \{ case \(\?_\) \{ return \}; case null \{\} \};', rearm) is not None)
    check('the wait is clamped between one second and a day',
          'TEND_MIN_WAIT_NS : Int = 1_000_000_000;' in src and 'TEND_MAX_WAIT_NS : Int = 86_400_000_000_000;' in src
          and 'if (wait < TEND_MIN_WAIT_NS) { TEND_MIN_WAIT_NS } else if (wait > TEND_MAX_WAIT_NS) { TEND_MAX_WAIT_NS } else { wait }' in rearm)
    check('nothing due means no timer at all', re.search(r'case null \{\};\n      case \(\?due\)', rearm) is not None)

    if shutil.which('dfx'):
        env = dict(os.environ, DFX_VERSION=(ROOT / '.dfx-version').read_text().strip() if (ROOT / '.dfx-version').exists() else '0.24.3')
        r = subprocess.run(['dfx', 'build', 'cafresohq_market', '--check'], cwd=ROOT, env=env,
                           capture_output=True, text=True, timeout=600)
        check('dfx build cafresohq_market --check passes', r.returncode == 0, (r.stderr or r.stdout)[-400:])
    else:
        print('  skip compile check: dfx is not on PATH')

    if FAILS:
        print(f'FAILED: {len(FAILS)}'); return 1
    print('OK'); return 0


if __name__ == '__main__':
    sys.exit(main())
