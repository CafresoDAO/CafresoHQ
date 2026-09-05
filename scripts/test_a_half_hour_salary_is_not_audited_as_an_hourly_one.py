#!/usr/bin/env python3
"""`hq payroll` reported a salary that pays twice an hour as an hourly one.

`hq payroll` (views/terminal.jsx) is the audit line: the one surface that
reads back what the state canister's payroll timer is actually going to
do -- amount, period, mode, per agent. It printed the period as

    ${_hqshFmt(s.amount, s.token)} / ${Math.round(s.periodSecs / 3600)}h

`Math.round(secs / 3600)` is the exact expression OFFICE_AS_INTERFACE #330
pulled out of the Settings panel, still alive on the surface that REPORTS
the schedule rather than the one that sets it. A period is not an amount,
but it is the number that decides how OFTEN the amount leaves, and rounding
it to whole hours is lossy in exactly that direction.

Driven under node against the real command with real salary rows:

    0.05 ICP every 1800 s (30 min)  ->  "0.05 ICP / 1h"
    0.05 ICP every  900 s (15 min)  ->  "0.05 ICP / 0h"
    0.05 ICP every   60 s           ->  "0.05 ICP / 0h"
    0.05 ICP every 5400 s (90 min)  ->  "0.05 ICP / 2h"

The first line is the bad one: 0.05 ICP twice an hour is 2.4 ICP a day, and
the audit line said 1h -- 1.2 ICP a day, half the real burn against the
signed payroll budget. The next two say a salary that is running every
quarter hour, or every minute, has a period of zero hours. Only whole-hour
multiples were ever told truthfully.

Every one of those periods is a first-class setting, not a corner: settings
`hoursToSecs` accepts 0.5 and 0.25, `savePay` deliberately allows down to
the canister's own 60-second floor ("minimum 60 seconds -- 0.02 h"), and
#330 fixed `secsToHoursText` precisely so sub-hour periods read back
honestly in the panel. This line never got that fix.

Fix: `_hqshEvery(secs)` prints the stored period exactly and never rounds --
hours only when the seconds ARE whole hours, minutes when they are whole
minutes, otherwise the seconds themselves. `hq wallets`, two commands up,
already prints its cap window as raw seconds for the same reason.

This test lifts the REAL `HQSH_COMMANDS` object out of views/terminal.jsx
and runs `hq payroll` under node against a stub chain, asserting the lines
it prints.

Run: python3 scripts/test_a_half_hour_salary_is_not_audited_as_an_hourly_one.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMINAL = ROOT / 'views' / 'terminal.jsx'
SETTINGS = ROOT / 'modals' / 'settings.jsx'
MAIN_MO = ROOT / 'src' / 'cafresohq_state' / 'main.mo'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Block and line comments out, so a comment quoting the old broken
    expression can never satisfy a grep for that expression."""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift(src, anchor):
    """Brace-match a top-level declaration so the REAL implementation runs in
    the harness rather than being pattern-matched from a distance."""
    i = src.index(anchor)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise SystemExit('could not brace-match ' + anchor)


def run(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


print('a half-hour salary is not audited as an hourly one')

SRC = TERMINAL.read_text(encoding='utf-8')
CODE = strip_comments(SRC)

# ── The premise: these periods are settings the office really stores. ────
SET = strip_comments(SETTINGS.read_text(encoding='utf-8'))
MO = strip_comments(MAIN_MO.read_text(encoding='utf-8'))
check('the state canister really floors a salary period at 60 seconds, so a '
      'sub-hour period is a schedule it will genuinely run',
      re.search(r'periodSecs\s*<\s*60', MO) is not None)
check('Settings really accepts a fractional-hour period (hoursToSecs is a '
      'plain hours*3600, not a whole-hour box)',
      re.search(r'return Math\.round\(n \* 3600\);', SET) is not None)
check('Settings reads a sub-hour period back honestly (#330), which is the '
      'contract this audit line has to match',
      re.search(r'setPayHrs\(secsToHoursText\(s\.periodSecs\)\)', SET) is not None)

# ── The real `hq payroll` command, driven under node. ────────────────────
HARNESS = (lift(SRC, 'const HQSH_DECIMALS =') + ';\n'
           + lift(SRC, 'function _hqshFmt(') + '\n'
           + lift(SRC, 'function _hqshEvery(') + '\n'
           + lift(SRC, 'const HQSH_COMMANDS =') + ';\n')

out = run(HARNESS + """
const rows = [
  ['half_hourly', 1800],
  ['quarter',      900],
  ['every_minute',  60],
  ['hourly',      3600],
  ['ninety',      5400],
  ['daily',      86400],
  ['odd',         3661],
];
const chain = { payroll: {
  list: async () => ({ paused: false, salaries: rows.map(([id, secs]) => ({
    agentId: id, amount: '5000000', token: 'ICP', periodSecs: secs,
    mode: 'salary', active: true,
  })) }),
  allowance: async () => ({ allowance: '100000000' }),
}};
const text = await HQSH_COMMANDS.payroll.run(chain, []);
const got = {};
for (const line of text.split('\\n')) {
  const m = /^\\s*(\\w+)\\s+(.*?)\\s\\ssalary/.exec(line);
  if (m) got[m[1]] = m[2];
}
console.log(JSON.stringify(got));
""")

check('every salary row still prints', len(out) == 7, out)

check('a salary paying 0.05 ICP every 30 minutes is NOT audited as hourly — '
      'that line understated the real burn against the signed payroll '
      'budget by half',
      out.get('half_hourly') != '0.05 ICP / 1h', out.get('half_hourly'))
check('...it says 30 minutes', out.get('half_hourly') == '0.05 ICP / 30m',
      out.get('half_hourly'))

check('a salary paying every 15 minutes is not audited as a period of zero '
      'hours', out.get('quarter') != '0.05 ICP / 0h', out.get('quarter'))
check('...it says 15 minutes', out.get('quarter') == '0.05 ICP / 15m',
      out.get('quarter'))

check('a salary at the canister\'s own 60-second floor is not audited as a '
      'period of zero hours', out.get('every_minute') != '0.05 ICP / 0h',
      out.get('every_minute'))
check('...it says 1 minute', out.get('every_minute') == '0.05 ICP / 1m',
      out.get('every_minute'))

check('a 90-minute salary is not rounded up to 2h — a third longer than it '
      'really is', out.get('ninety') != '0.05 ICP / 2h', out.get('ninety'))
check('...it says 90 minutes', out.get('ninety') == '0.05 ICP / 90m',
      out.get('ninety'))

check('a period that is neither whole hours nor whole minutes is shown as '
      'the seconds it actually is, never rounded to a prettier number',
      out.get('odd') == '0.05 ICP / 3661s', out.get('odd'))

check('an hourly salary still reads "1h"', out.get('hourly') == '0.05 ICP / 1h',
      out.get('hourly'))
check('a daily salary still reads "24h"', out.get('daily') == '0.05 ICP / 24h',
      out.get('daily'))

# ── The helper itself, on the edges the audit line can be handed. ────────
out2 = run(HARNESS + """
const cases = [0, 1800, 900, 60, 3600, 5400, 86400, 3661, 30];
const got = {};
for (const c of cases) got[String(c)] = _hqshEvery(c);
got['null'] = _hqshEvery(null);
got['undefined'] = _hqshEvery(undefined);
got['nan'] = _hqshEvery('abc');
console.log(JSON.stringify(got));
""")
check('a stored 0 is not printed as "0h" as though it were a real hour count',
      out2['0'] != '0h', out2['0'])
check('a sub-minute period is shown in seconds', out2['30'] == '30s', out2['30'])
check('a missing or non-numeric period never invents a number',
      out2['null'] != '0h' and out2['undefined'] != '0h' and out2['nan'] != '0h',
      (out2['null'], out2['undefined'], out2['nan']))

# ── No path back to the rounding. ───────────────────────────────────────
check('the payroll audit line no longer rounds seconds into whole hours',
      re.search(r'Math\.round\(s\.periodSecs\s*/\s*3600\)', CODE) is None)
check('no `Math.round(… / 3600)` survives anywhere in the hq shell',
      re.search(r'Math\.round\([^)]*/\s*3600\)', CODE) is None)
check('the payroll line reads the period through _hqshEvery',
      re.search(r'\$\{_hqshEvery\(s\.periodSecs\)\}', CODE) is not None)
check('_hqshEvery is still defined in this file',
      re.search(r'function _hqshEvery\(secs\)', CODE) is not None)
check('`hq wallets` still prints its cap window exactly, in raw seconds — '
      'the neighbour this fix was made consistent with',
      re.search(r'window \$\{w\.windowSecs\}s', CODE) is not None)

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
    sys.exit(1)
print('all ok')
