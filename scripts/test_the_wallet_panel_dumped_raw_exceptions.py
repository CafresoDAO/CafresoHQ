#!/usr/bin/env python3
"""The wallet and payroll panels showed raw exception text, not a message.

Reproduced by reading the source. `modals/settings.jsx` imports `cleanCause`
from app/floor.jsx specifically for this screen — the file-level comment at
the top of the file explains why: `snagCause` names a BRAIN in every
sentence, and nothing on this screen is one, so `cleanCause` strips the raw
error without inventing a cause. `IcpServicesPanel`, four call sites in the
same file, already used it correctly.

`AgentWalletCard` (refreshBalances, saveCap, fund, togglePause, savePay,
payNow, stopPay) and `PayrollBudgetPanel` (approve, togglePause) — nine
call sites across the two panels that actually move or gate money — did
not. Every one of them caught its error and rendered it with:

    setMsg(String(e.message || e))

A raw IC canister reject message, or a raw JS error's full string form
(sometimes including a stack, a URL, or a JSON blob), landing verbatim in
a UI meant to say "insufficient funds" or "budget not signed" in words a
non-engineer boss could act on. The screen already had the exact tool
built for this job, imported, and used correctly two panels below.

Run: python3 scripts/test_the_wallet_panel_dumped_raw_exceptions.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = (ROOT / 'modals/settings.jsx').read_text(encoding='utf-8')
FLOOR = (ROOT / 'app/floor.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def brace_lift(src, opener):
    i = src.index(opener)
    parens = 0
    j = None
    for k in range(i, len(src)):
        c = src[k]
        if c == '(':
            parens += 1
        elif c == ')':
            parens -= 1
        elif c == '{' and parens == 0:
            j = k
            break
    if j is None:
        raise AssertionError('no body brace found lifting ' + opener)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError('unbalanced braces lifting ' + opener)


def main():
    print('the wallet panel dumped raw exceptions')

    # ── 0. cleanCause is a real, already-imported helper on this screen ─────
    check('cleanCause is defined in app/floor.jsx', 'function cleanCause(raw)' in FLOOR)
    # The import widened in #402 (officeCause joined cleanCause for the
    # office-restore mirror PUTs, which DO have the office as their subject).
    # What this line is for is that cleanCause is imported here at all, so
    # match the named import rather than the whole statement.
    check('modals/settings.jsx imports it',
          re.search(r"import \{[^}]*\bcleanCause\b[^}]*\} from '\.\./app/floor\.jsx';",
                    SETTINGS) is not None)

    # ── 1. no call site in this file still hands a raw exception to setMsg ──
    check('no setMsg(String(e.message || e)) remains anywhere in the file',
          'setMsg(String(e.message || e))' not in SETTINGS,
          '— this was the raw, un-cleaned form')

    # ── 2. the two money-moving panels specifically now route through it ────
    wallet = brace_lift(SETTINGS, 'function AgentWalletCard(')
    wallet_sites = ['refreshBalances', 'saveCap', 'fund', 'togglePause', 'savePay', 'payNow', 'stopPay']
    for name in wallet_sites:
        fn = re.search(r'const %s = async \(\) => \{[\s\S]*?\n  \};' % name, wallet)
        check('AgentWalletCard.%s() cleans its error before showing it' % name,
              fn is not None and 'cleanCause(' in fn.group(0),
              '— found raw exception text instead' if fn else 'could not locate the function')

    payroll = brace_lift(SETTINGS, 'function PayrollBudgetPanel(')
    payroll_sites = ['approve', 'togglePause']
    for name in payroll_sites:
        fn = re.search(r'const %s = async \([^)]*\) => \{[\s\S]*?\n  \};' % name, payroll)
        check('PayrollBudgetPanel.%s() cleans its error before showing it' % name,
              fn is not None and 'cleanCause(' in fn.group(0),
              '— found raw exception text instead' if fn else 'could not locate the function')

    # ── 3. the fix didn't touch anything except the error-display line —
    #        confirm the money-moving calls themselves are untouched ────────
    check('fund() still confirms the exact amount/destination before sending',
          'YOUR main account' in wallet and 'real on-chain transfer' in wallet)
    check('payNow() still confirms before running payroll',
          'Run payroll for' in wallet)
    check('stopPay() still confirms before stopping payroll',
          'Stop payroll for' in wallet)

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
