#!/usr/bin/env python3
"""Worklog helpers (app/worklog.jsx) — pure-function suite.

These decide whether the board tells the boss the truth about an
in-progress job: when it started, and whether anyone is actually on it
(OFFICE_AS_INTERFACE §4 — `agent.status` is the only authority on "is this
coworker working right now").

The module is import-free, so it runs verbatim under node minus its export
line.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'app' / 'worklog.jsx'

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
    proc = subprocess.run(['node', '--input-type=module', '-e', src + '\n' + cases_js],
                          cwd=ROOT, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit('node harness failed to run')
    return json.loads(proc.stdout.strip().split('\n')[-1])


def main():
    print('worklog')
    if not shutil.which('node'):
        print('  SKIP  node not on PATH')
        return 0
    if not SRC.is_file():
        print(f'  FAIL  missing {SRC}')
        return 1

    out = run_js(r'''
const R = {};
const T0 = 1000000;
// (MIN/HOUR/DAY are already declared by the module under test.)
// ── applyStatus: the startedAt invariant ────────────────────────────────
R.stamps       = applyStatus({ id: 'a', status: 'inbox' }, 'doing', T0).startedAt;
R.keepsClock   = applyStatus({ id: 'a', status: 'doing', startedAt: T0 }, 'doing', T0 + HOUR).startedAt;
R.clearsOnDone = 'startedAt' in applyStatus({ id: 'a', status: 'doing', startedAt: T0 }, 'done', T0);
R.clearsOnBack = 'startedAt' in applyStatus({ id: 'a', status: 'doing', startedAt: T0 }, 'inbox', T0);
R.noStampInbox = 'startedAt' in applyStatus({ id: 'a', status: 'inbox' }, 'inbox', T0);
R.keepsFields  = applyStatus({ id: 'a', status: 'inbox', title: 'T', assignedTo: 'x' }, 'doing', T0).title;
R.pure         = (() => { const t = { id: 'a', status: 'inbox' }; applyStatus(t, 'doing', T0); return 'startedAt' in t; })();
// ── isStalled: agent.status is the only authority ───────────────────────
const doing = { status: 'doing' };
R.stallActive  = isStalled(doing, { status: 'active' });
R.stallBusy    = isStalled(doing, { status: 'busy' });
R.stallIdle    = isStalled(doing, { status: 'idle' });
R.stallAway    = isStalled(doing, { status: 'away' });
R.stallStuck   = isStalled(doing, { status: 'stuck' });
R.stallNoOwner = isStalled(doing, null);
R.stallInbox   = isStalled({ status: 'inbox' }, null);
R.stallDone    = isStalled({ status: 'done' }, null);
R.stallNull    = isStalled(null, null);
// ── sittingFor ──────────────────────────────────────────────────────────
R.sitPlain     = sittingFor({ startedAt: T0 }, T0 + 5 * MIN);
R.sitUnstamped = sittingFor({ status: 'doing' }, T0);
R.sitFuture    = sittingFor({ startedAt: T0 + HOUR }, T0);
// ── durationLabel ───────────────────────────────────────────────────────
R.dJustNow = durationLabel(30000);
R.dMin     = durationLabel(5 * MIN);
R.dHour    = durationLabel(2 * HOUR);
R.dHourMin = durationLabel(2 * HOUR + 14 * MIN);
R.dDay     = durationLabel(DAY);
R.dDays    = durationLabel(3 * DAY);
R.dNull    = durationLabel(null);
// ── worklogLine ─────────────────────────────────────────────────────────
R.lineOnIt    = worklogLine({ status: 'doing', startedAt: T0 }, { status: 'active' }, T0 + 5 * MIN);
R.lineNobody  = worklogLine({ status: 'doing', startedAt: T0 }, { status: 'idle' }, T0 + 2 * HOUR);
R.lineNoOwner = worklogLine({ status: 'doing', startedAt: T0 }, null, T0 + 2 * HOUR);
R.lineNoStamp = worklogLine({ status: 'doing' }, { status: 'idle' }, T0);
R.lineInbox   = worklogLine({ status: 'inbox', startedAt: T0 }, null, T0);
R.lineDone    = worklogLine({ status: 'done' }, { status: 'idle' }, T0);
R.lineNoStuck = /stuck|fail|error/i.test([R.lineOnIt, R.lineNobody, R.lineNoOwner, R.lineNoStamp].join(' '));
console.log(JSON.stringify(R));
''')

    # applyStatus
    check('entering doing stamps startedAt', out['stamps'] == 1000000)
    check('re-entering doing does NOT restart the clock',
          out['keepsClock'] == 1000000, str(out['keepsClock']))
    check('leaving for done clears the stamp', out['clearsOnDone'] is False)
    check('reopening to inbox clears the stamp', out['clearsOnBack'] is False)
    check('a non-doing move adds no stamp', out['noStampInbox'] is False)
    check('other task fields survive', out['keepsFields'] == 'T')
    check('the input task is not mutated', out['pure'] is False)

    # isStalled — §4: agent.status is the authority
    check('an active owner means someone is on it', out['stallActive'] is False)
    check('a busy owner means someone is on it', out['stallBusy'] is False)
    check('an idle owner means nobody is on it', out['stallIdle'] is True)
    check('an away owner means nobody is on it', out['stallAway'] is True)
    check('a snagged owner means nobody is on it', out['stallStuck'] is True)
    check('no owner at all means nobody is on it', out['stallNoOwner'] is True)
    check('an inbox task is never stalled', out['stallInbox'] is False)
    check('a done task is never stalled', out['stallDone'] is False)
    check('a missing task is never stalled', out['stallNull'] is False)

    # sittingFor
    check('reports elapsed since startedAt', out['sitPlain'] == 300000)
    check('an unstamped task reports nothing rather than guessing',
          out['sitUnstamped'] is None)
    check('a clock-skewed future stamp reports nothing', out['sitFuture'] is None)

    # durationLabel
    check('under a minute reads "just now"', out['dJustNow'] == 'just now')
    check('minutes', out['dMin'] == '5m')
    check('a whole number of hours drops the minutes', out['dHour'] == '2h')
    check('hours and minutes', out['dHourMin'] == '2h 14m', str(out['dHourMin']))
    check('one day is singular', out['dDay'] == '1 day')
    check('several days', out['dDays'] == '3 days')
    check('no duration yields no label', out['dNull'] is None)

    # worklogLine
    check('someone on it reads "on it · 5m"', out['lineOnIt'] == 'on it · 5m',
          str(out['lineOnIt']))
    check('an idle owner reads "nobody\'s on this · 2h"',
          out['lineNobody'] == "nobody's on this · 2h", str(out['lineNobody']))
    check('no owner reads the same', out['lineNoOwner'] == "nobody's on this · 2h")
    check('an unstamped task still reports who is on it, without a time',
          out['lineNoStamp'] == "nobody's on this", str(out['lineNoStamp']))
    check('an inbox task gets no line', out['lineInbox'] is None)
    check('a done task gets no line', out['lineDone'] is None)
    check('a job nobody picked up is never called stuck or failed (§5)',
          out['lineNoStuck'] is False)

    print()
    if FAILS:
        print(f'worklog: {len(FAILS)} FAILED — ' + ', '.join(FAILS))
        return 1
    print('worklog: all checks passed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
