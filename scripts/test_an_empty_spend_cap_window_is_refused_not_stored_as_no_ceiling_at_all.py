#!/usr/bin/env python3
"""Clearing the "per ___ h" box switched the agent spend cap OFF, and the
panel then showed the boss "24".

Two windows in Settings -> ICP Services are typed in hours and stored
on-chain in seconds: the agent wallet's rolling SPEND-CAP window
(`windowSecs`) and the payroll PERIOD (`periodSecs`). Neither is an
amount; both decide how much money moves.

`saveCap` used to write

    windowSecs: Math.max(0, Math.round(parseFloat(capHrs || '0') * 3600))

so an empty box (or a typed 0) stored windowSecs = 0. In
src/cafresohq_state/main.mo that is not "zero hours", it is a documented
MODE -- recordSpend reads `windowSecs == 0` as "per-transaction cap only"
and rolls the window on EVERY call, so `spent0` resets to 0 each time and
the gate collapses to `amount > spendCap` alone. A 0.1 ICP cap the boss
set meaning "0.1 ICP a day, autonomously" became 0.1 ICP PER TRANSFER,
with no ceiling on the day at all.

`load()` then covered it up: `String(Math.round(0 / 3600) || 24)` is
"24", so the box the boss read afterwards claimed a stored window of
86400 seconds while the stored window was 0. The same `|| 24` mislabelled
every genuine sub-half-hour setting -- a real 900-second window also read
back "24" -- and pressing SAVE on that screen wrote the 24 hours the boss
had been shown.

The payroll box leaked the other way: `Math.max(60, ...)` turned an empty
period into `periodSecs = 60`, the canister's own minimum (putSalary
rejects anything under 60s), i.e. a salary due every minute against the
signed payroll budget -- and the read-back showed it as 24 h again.

And `parseFloat('abc')` is NaN, so `Math.max(60, NaN)` is NaN: a
non-numeric box put NaN across the bridge as a period.

This test drives the REAL `hoursToSecs` / `secsToHoursText` lifted out of
modals/settings.jsx under node, and asserts the numbers.

Run: python3 scripts/test_an_empty_spend_cap_window_is_refused_not_stored_as_no_ceiling_at_all.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / 'modals' / 'settings.jsx'
MAIN_MO = ROOT / 'src' / 'cafresohq_state' / 'main.mo'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def strip_comments(src):
    """Block and line comments out, so an explanatory comment describing the
    old broken expression can never satisfy a grep for that expression."""
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    return re.sub(r'^\s*//.*$', '', src, flags=re.M)


def lift_function(src, name):
    """Brace-match `function <name>(...) { ... }` so the REAL implementation
    runs in the harness rather than being pattern-matched from a distance."""
    m = re.search(r'\nfunction ' + re.escape(name) + r'\s*\(', src)
    if not m:
        raise SystemExit('could not find function ' + name + ' in settings.jsx')
    i = src.index('{', m.end())
    depth, k = 0, i
    while k < len(src):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():k + 1]
        k += 1
    raise SystemExit('could not brace-match ' + name)


def run(js):
    p = subprocess.run(['node', '--input-type=module', '-e', js],
                       cwd=ROOT, capture_output=True, text=True, timeout=60)
    if p.returncode != 0:
        print(p.stderr, file=sys.stderr)
        raise SystemExit('node harness failed on source lifted from the app')
    return json.loads(p.stdout.strip().split('\n')[-1])


print('an empty spend-cap window is refused, not stored as no ceiling at all')

SRC = SETTINGS.read_text(encoding='utf-8')
CODE = strip_comments(SRC)

# ── The premise, in the canister's own source. ───────────────────────────
MO = strip_comments(MAIN_MO.read_text(encoding='utf-8'))
check('the state canister really treats windowSecs == 0 as "roll every call" '
      '— a stored 0 is a removed ceiling, not a zero-length one',
      re.search(r'rolled\s*=\s*w\.windowSecs\s*==\s*0\s+or', MO) is not None)
check('the state canister really floors a salary period at 60 seconds, so a '
      'clamp to 60 is the fastest payroll it will accept',
      re.search(r'periodSecs\s*<\s*60', MO) is not None)

HARNESS = lift_function(SRC, 'hoursToSecs') + '\n' + lift_function(SRC, 'secsToHoursText')

# ── hoursToSecs: what the boxes send on-chain. ───────────────────────────
out = run(HARNESS + """
const cases = ['', '0', '  ', 'abc', '-4', '24', '0.5', '0.25', '1', '48'];
const got = {};
for (const c of cases) got[c] = hoursToSecs(c);
console.log(JSON.stringify(got));
""")

check('an EMPTY window box no longer becomes 0 seconds (which on-chain is '
      '"cap applies per transfer, forever") — it is refused',
      out[''] is None, 'hoursToSecs("") = %r' % (out[''],))
check('a typed 0 is refused too', out['0'] is None, 'hoursToSecs("0") = %r' % (out['0'],))
check('a whitespace-only box is refused', out['  '] is None, out['  '])
check('a non-numeric box is refused rather than sending NaN across the '
      'bridge (Math.max(60, NaN) === NaN)',
      out['abc'] is None, 'hoursToSecs("abc") = %r' % (out['abc'],))
check('a negative window is refused', out['-4'] is None, out['-4'])

check('24 h is still exactly 86400 s', out['24'] == 86400, out['24'])
check('1 h is still exactly 3600 s', out['1'] == 3600, out['1'])
check('48 h is still exactly 172800 s', out['48'] == 172800, out['48'])
check('half an hour is 1800 s, not rounded away', out['0.5'] == 1800, out['0.5'])
check('a quarter hour is 900 s', out['0.25'] == 900, out['0.25'])

# ── secsToHoursText: what the box shows the boss afterwards. ─────────────
out2 = run(HARNESS + """
const cases = [0, 60, 900, 1800, 3600, 86400, 172800];
const got = {};
for (const c of cases) got[String(c)] = secsToHoursText(c);
got['null'] = secsToHoursText(null);
got['undefined'] = secsToHoursText(undefined);
console.log(JSON.stringify(got));
""")

check('a stored window of 0 s is NOT displayed as "24" — the old '
      '`Math.round(0/3600) || 24` showed 86400 s of ceiling that was not '
      'there at all',
      out2['0'] != '24', 'secsToHoursText(0) = %r' % (out2['0'],))
check('a stored window of 0 s reads back as 0', out2['0'] == '0', out2['0'])
check('a real 900 s (15 min) window is not displayed as "24" either — SAVE '
      'on that screen used to write 86400 s over it, a 96x widening',
      out2['900'] != '24', out2['900'])
check('900 s reads back as 0.25 h', out2['900'] == '0.25', out2['900'])
check('a 60 s payroll period reads back as 0.0167 h, not "24"',
      out2['60'] == '0.0167', out2['60'])
check('1800 s reads back as 0.5 h', out2['1800'] == '0.5', out2['1800'])
check('86400 s still reads back as plain "24"', out2['86400'] == '24', out2['86400'])
check('3600 s still reads back as plain "1"', out2['3600'] == '1', out2['3600'])
check('172800 s reads back as "48"', out2['172800'] == '48', out2['172800'])
check('a missing value reads back as 0, never an invented 24',
      out2['null'] == '0' and out2['undefined'] == '0',
      (out2['null'], out2['undefined']))

# ── The round trip: what the boss sees is what SAVE writes back. ─────────
out3 = run(HARNESS + """
const stored = [900, 1800, 3600, 86400, 172800];
const got = {};
for (const s of stored) got[String(s)] = hoursToSecs(secsToHoursText(s));
console.log(JSON.stringify(got));
""")
for stored in ('900', '1800', '3600', '86400', '172800'):
    check('a stored %s s window survives display -> SAVE unchanged' % stored,
          out3[stored] == int(stored),
          '%s -> %r' % (stored, out3[stored]))

# ── The call sites: no path back to the old expressions. ────────────────
check('saveCap sends the validated windowSecs, not a raw parseFloat of the box',
      re.search(r'windowSecs:\s*Math\.max\(0,\s*Math\.round\(parseFloat', CODE) is None
      and re.search(r'const windowSecs = hoursToSecs\(capHrs\);', CODE) is not None)
check('saveCap refuses instead of writing when the window box is not a '
      'positive number',
      re.search(r'if \(windowSecs === null\) \{\s*setMsg\([^\n]*\n?[^\n]*return;', CODE) is not None)
check('savePay sends the validated periodSecs, not Math.max(60, …)',
      re.search(r'periodSecs:\s*Math\.max\(60', CODE) is None
      and re.search(r'const periodSecs = hoursToSecs\(payHrs\);', CODE) is not None)
check('savePay refuses a period the canister would run every minute',
      re.search(r'periodSecs === null \|\| periodSecs < 60', CODE) is not None)
check('load() reads both boxes back through secsToHoursText, so no `|| 24` '
      'survives on either window',
      re.search(r'setCapHrs\(secsToHoursText\(p\.windowSecs\)\)', CODE) is not None
      and re.search(r'setPayHrs\(secsToHoursText\(s\.periodSecs\)\)', CODE) is not None
      and re.search(r'/\s*3600\)\s*\|\|\s*24', CODE) is None)
check('togglePause re-writes the SAVED policy verbatim (?? not ||), so '
      'pausing cannot change a stored 0 window as a side effect',
      re.search(r'windowSecs:\s*policy\?\.windowSecs \?\?', CODE) is not None
      and re.search(r'spendCap:\s*policy\?\.spendCap \?\?', CODE) is not None)

print()
if FAILS:
    print('FAILED (%d): %s' % (len(FAILS), '; '.join(FAILS)))
    sys.exit(1)
print('all ok')
