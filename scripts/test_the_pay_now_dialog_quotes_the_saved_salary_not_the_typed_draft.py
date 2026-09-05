#!/usr/bin/env python3
"""The boss approved 0.01 ICP and 5 ICP left the payroll budget.

Settings -> ICP Services -> a coworker's wallet card has ONE payroll row:
a mode picker, an amount box, a token dropdown, a period, then [SAVE] and
[* NOW]. The inputs are a DRAFT until SAVE is pressed -- `savePay` is the
only thing that writes them on-chain.

`* NOW` calls `chain().payroll.run(agentId)`, which is `runPayrollNow` in
src/cafresohq_state/main.mo. It takes an agentId and nothing else: it looks
the salary up by id and hands the STORED `s.amount` (a base-unit integer)
to the ledger through `processDue`/`executeTransfer`. The typed boxes are
not part of that call and cannot be.

BEFORE, the confirm dialog quoted the boxes:

    `Run payroll for ${agent.name} right now?\\n\\nPays ${payAmt} ${payTok}
     from your signed payroll budget (the budget cap still applies).`

So with a saved salary of 5 ICP, a boss who typed 0.01 into the amount box
and pressed * NOW was asked to approve

    Pays 0.01 ICP from your signed payroll budget

and 500000000 base units -- 5 ICP -- left their signed ICRC-2 allowance.
499x the sum consented to, irreversibly, out of the boss's own main
account. The token dropdown carried the same lie: draft sGLDT over a saved
ICP salary asked for gold and sent ICP.

AFTER, the dialog is built from the saved row (`savedPayStatement`), and
when the draft disagrees it says so instead of silently paying the other
number.

This test drives the real helpers out of modals/settings.jsx under node and
asserts the quoted figure round-trips to the exact stored base-unit integer.

Run: python3 scripts/test_the_pay_now_dialog_quotes_the_saved_salary_not_the_typed_draft.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / 'modals' / 'settings.jsx'
STATE_MO = ROOT / 'src' / 'cafresohq_state' / 'main.mo'
FAILS = []


def check(name, cond, detail=''):
    if cond:
        print(f'  ok    {name}')
    else:
        FAILS.append(name)
        print(f'  FAIL  {name}{("  — " + str(detail)) if detail else ""}')


def strip_comments(text):
    """Block and line comments out, so this file's own prose (which quotes the
    old buggy expression on purpose) can never satisfy a source check."""
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
    return re.sub(r'^\s*//.*$', '', text, flags=re.M)


def grab(src, name):
    """Pull one top-level `function name(...) { ... }` out by brace balance."""
    m = re.search(r'^function %s\s*\(' % re.escape(name), src, re.M)
    if not m:
        return None
    i = src.index('{', m.start())
    depth = 0
    for j in range(i, len(src)):
        if src[j] == '{':
            depth += 1
        elif src[j] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():j + 1]
    return None


print('the pay-now dialog quotes the saved salary, not the typed draft')

if not shutil.which('node'):
    print('  SKIP  node not on PATH')
    raise SystemExit(0)
if not SETTINGS.is_file():
    print(f'  FAIL  missing {SETTINGS}')
    raise SystemExit(1)

raw = SETTINGS.read_text(encoding='utf-8')
src = strip_comments(raw)

# ── 0. the premise: * NOW pays the STORED salary, by agentId alone ───────
if STATE_MO.is_file():
    mo = STATE_MO.read_text(encoding='utf-8')
    check('runPayrollNow still takes an agentId and nothing else — the typed '
          'boxes are not part of the call',
          re.search(r'func runPayrollNow\(agentId : Text\) : async Text', mo) is not None,
          'if the canister grew an amount parameter this test is about nothing')

check('payroll.run() is still called with the agent id alone',
      re.search(r'chain\(\)\.payroll\.run\(agentId\)', src) is not None)
check('savePay is still the only writer of the payroll amount',
      'amount: toBaseUnits(payAmt, dec)' in src)

# ── 1. the dialog no longer quotes the unsaved draft ─────────────────────
m = re.search(r'const payNow = async \(\) => \{(.*?)\n  \};', src, re.S)
check('payNow is still present', m is not None)
body = m.group(1) if m else ''

check('the confirm no longer interpolates the draft amount box as the sum '
      'being paid',
      re.search(r'Pays \$\{payAmt\} \$\{payTok\}', body) is None,
      'the boxes are unsaved — the chain pays the stored row')
check('the confirm is built from the saved salary row',
      'savedPayStatement(sal, WALLET_TOKEN_DECIMALS)' in body)
check('an unsaved edit is named rather than silently ignored',
      'payDraftDiffers(' in body)
check('no saved salary means nothing to confirm and nothing to run',
      re.search(r'if \(!stated\)', body) is not None)

# ── 2. drive the real helpers: the quoted figure IS the stored integer ───
helpers = [grab(src, n) for n in ('fromBaseUnits', 'savedPayStatement', 'payDraftDiffers')]
check('fromBaseUnits / savedPayStatement / payDraftDiffers are all extractable',
      all(helpers))
if not all(helpers):
    print()
    print(f'{len(FAILS)} FAILED')
    raise SystemExit(1)

decimals = re.search(r'const WALLET_TOKEN_DECIMALS = \{[^}]*\};', src)
check('WALLET_TOKEN_DECIMALS is still the decimals table', decimals is not None)

harness = r'''
const OUT = [];
// A saved 5 ICP salary; the boss has typed 0.01 into the box without SAVE.
const sal = { agentId: 'ada', token: 'ICP', amount: '500000000', mode: 'salary' };
const stated = savedPayStatement(sal, WALLET_TOKEN_DECIMALS);
OUT.push(['quoted', stated && stated.amount]);
OUT.push(['quotedToken', stated && stated.token]);
OUT.push(['storedRaw', stated && stated.raw]);
// The quoted figure must round-trip to the exact base-unit integer the
// canister will hand the ledger — no float anywhere on that path.
OUT.push(['roundTrip', String(toBaseUnits(stated.amount, WALLET_TOKEN_DECIMALS[stated.token]))]);
OUT.push(['draftFlagged', payDraftDiffers(stated, '0.01', 'ICP')]);
OUT.push(['tokenSwapFlagged', payDraftDiffers(stated, '5', 'sGLDT')]);
OUT.push(['cleanDraftNotFlagged', payDraftDiffers(stated, '5', 'ICP')]);
OUT.push(['cleanDraftWhitespace', payDraftDiffers(stated, ' 5 ', 'ICP')]);
// A 6-decimal token must not be quoted with 8-decimal scaling.
const usdt = { agentId: 'ada', token: 'ckUSDT', amount: '1500000' };
const su = savedPayStatement(usdt, WALLET_TOKEN_DECIMALS);
OUT.push(['usdt', su && su.amount]);
OUT.push(['usdtRoundTrip', String(toBaseUnits(su.amount, WALLET_TOKEN_DECIMALS['ckUSDT']))]);
// No saved row → nothing to confirm.
OUT.push(['none', savedPayStatement(null, WALLET_TOKEN_DECIMALS)]);
console.log(JSON.stringify(OUT));
'''

js = '\n'.join([decimals.group(0), grab(src, 'toBaseUnits')] + helpers + [harness])
proc = subprocess.run(['node', '--input-type=module', '-e', js],
                      cwd=str(ROOT), capture_output=True, text=True, timeout=60)
if proc.returncode != 0:
    print(proc.stdout)
    print(proc.stderr, file=sys.stderr)
    raise SystemExit('node harness failed on modals/settings.jsx')
got = dict(json.loads(proc.stdout.strip().split('\n')[-1]))

check('a saved 500000000-base-unit salary is quoted as 5 ICP, not the typed 0.01',
      got['quoted'] == '5', got['quoted'])
check('the token quoted is the saved one', got['quotedToken'] == 'ICP', got['quotedToken'])
check('the quoted figure round-trips to the exact stored base-unit integer',
      got['roundTrip'] == '500000000' == got['storedRaw'],
      f"{got['roundTrip']} vs {got['storedRaw']}")
check('an unsaved amount edit is detected', got['draftFlagged'] is True)
check('an unsaved token swap is detected', got['tokenSwapFlagged'] is True)
check('a draft matching the saved row is not flagged',
      got['cleanDraftNotFlagged'] is False)
check('stray whitespace alone is not an unsaved edit',
      got['cleanDraftWhitespace'] is False)
check('a 6-decimal token is quoted at its own scale (1500000 ckUSDT base '
      'units = 1.5, not 0.015)', got['usdt'] == '1.5', got['usdt'])
check('the 6-decimal quote round-trips exactly',
      got['usdtRoundTrip'] == '1500000', got['usdtRoundTrip'])
check('no saved salary yields no statement to quote', got['none'] is None)

print()
if FAILS:
    print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
    raise SystemExit(1)
print('all checks passed')
