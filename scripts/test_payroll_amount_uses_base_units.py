#!/usr/bin/env python3
"""A payroll amount typed in Settings was silently paid at 1/10^decimals
of the intended size.

`AgentWalletCard`'s `load()` (modals/settings.jsx) reads `s.amount` and
`s.lowWatermark` back from `chain().payroll.list()` through
`fromBaseUnits(value, dec)` — the same round-trip contract `saveCap`
already honors correctly for `spendCap` via `toBaseUnits(capAmt, dec)`
on write. But `savePay` wrote `amount`/`lowWatermark` as raw
`parseFloat(...)` floats, with no decimal-scaling at all: typing
"0.01 ICP" (8 decimals) sent the float `0.01` where the canister
expects the base-unit integer `1000000` — the actual base-unit value
of 0.01 ICP. Off by a factor of 10^8, "0.01 ICP per day" salary paid
(or refilled at) an amount indistinguishable from zero, with the UI
still reporting "Payroll saved" as a clean success.

Proven purely from this file's own round-trip: it reads these exact
fields back in base units (fromBaseUnits) but was writing them as plain
decimal floats — a self-contained inconsistency, regardless of what the
shell/canister does elsewhere.

Found by a background hunt agent sweeping previously-unswept areas
(Night Shift, approval/hire flow, search, Settings, CEO 1:1, export/
publish, workflow/mission system, chat, vault/Library).

Fix: `savePay` now converts both `amount` and `lowWatermark` through
`toBaseUnits(..., dec)`, matching `saveCap`'s existing pattern exactly.

A related call, `PayrollBudgetPanel.approve()` (same file, ~line 681),
also passes a raw `parseFloat(amt)` to `chain().payroll.approve(...)` —
left untouched here. Its own comment ("approve() is the ONE real
signature (shell-confirmed)") suggests it triggers a live ICRC-2
approval signed in the shell, the same category as `wallet.fund`/
`wallet.send` (which also take raw human decimal amounts, converted
shell-side) rather than a plain state-canister field write like `put`.
Converting it without shell-side confirmation risks introducing the
opposite bug, so it's deferred rather than guessed at.

Run: python3 scripts/test_payroll_amount_uses_base_units.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / 'modals' / 'settings.jsx'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def main():
    print('savePay converts amount/lowWatermark to base units before writing them on-chain')

    src = SETTINGS.read_text(encoding='utf-8')

    m = re.search(r"const savePay = async \(\) => \{(.*?)\n  \};", src, re.S)
    check('savePay is still present', m is not None)
    body = m.group(1) if m else ''

    check('load() still reads payroll amount/lowWatermark back through '
          'fromBaseUnits (the contract savePay must match on write)',
          bool(re.search(r"setPayAmt\(fromBaseUnits\(s\.amount,\s*dec\)\)", src))
          and bool(re.search(r"setPayWm\(fromBaseUnits\(s\.lowWatermark,\s*dec\)\)", src)))

    check("savePay looks up this token's decimals, the same way saveCap does",
          "const dec = WALLET_TOKEN_DECIMALS[payTok] ?? 8;" in body)

    check("amount is converted through toBaseUnits before being sent to "
          "chain().payroll.put — a raw parseFloat here was the actual "
          "off-by-10^decimals bug",
          "amount: toBaseUnits(payAmt, dec)" in body)
    check("amount is no longer sent as a raw parseFloat",
          not re.search(r"amount:\s*parseFloat\(payAmt\)", body))

    check("lowWatermark is converted through toBaseUnits in refill mode too",
          "lowWatermark: payMode === 'refill' ? toBaseUnits(payWm, dec) : '0'" in body)
    check("lowWatermark is no longer sent as a raw parseFloat",
          not re.search(r"lowWatermark:.*parseFloat\(payWm\)", body))

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
