#!/usr/bin/env python3
"""Buying furniture credited the coworker's P&L as money EARNED.

Reproduced by reading the source. `cafresohq:moneyEvent` is not an
income-only channel. Three places fire it:

  · app.jsx tip watcher      kind:'tip'      — a credit landed
  · app.jsx payroll watcher  kind:'payday'   — salary landed
  · modals/collab.jsx        kind:'furnish'  — a SIGNED sGLDT PURCHASE
                                               that just settled ('paid')

The office's COWORKER P&L board (ui/office.jsx) keeps a live per-agent
{earnedRaw, spentRaw} and renders `▲earned ▼spent =net`. Its live
listener used to read:

    const onMoney = (e) => {
      const d = e.detail || {};
      if (!d.agentId || !d.amountRaw) return;
      ... earnedRaw: cur.earnedRaw + BigInt(d.amountRaw) ...

— no `kind` filter at all. The furnish event carries agentId, an
amountRaw in e8s, and token 'sGLDT', which is exactly the token the
office treasury is denominated in, so it passed the `d.token !==
cur.token` guard and landed in EARNED. Spending 20 sGLDT on a desk plant
made the wall read ▲20 earned and moved net +20 instead of -20: a 40
sGLDT error in the boss's favour, on the one surface in the product that
claims to be the team's books.

The same event also rained coins labelled `+20 sGLDT` over the buyer's
desk — the identical lie in its second rendering.

Run: python3 scripts/test_a_purchase_is_not_a_payday.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OFFICE = (ROOT / 'ui/office.jsx').read_text(encoding='utf-8')
COLLAB = (ROOT / 'modals/collab.jsx').read_text(encoding='utf-8')
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


print('a purchase is not a payday')

# ── The premise: a spend really is broadcast on this channel. ────────────
check("modals/collab.jsx dispatches a moneyEvent with kind:'furnish' after a "
      "purchase settles (the spend this board must not bank)",
      re.search(r"cafresohq:moneyEvent", COLLAB) is not None
      and re.search(r"kind:\s*'furnish'", COLLAB) is not None)

check("that furnish event carries agentId + amountRaw + token:'sGLDT', so it "
      "clears every other guard on the P&L listener",
      re.search(r"agentId:[^}]*amountRaw:[^}]*token:\s*'sGLDT'[^}]*kind:\s*'furnish'",
                COLLAB, re.S) is not None)

# ── The fix: the P&L listener only banks income kinds. ───────────────────
pl = re.search(
    r"const \[plTotals, setPlTotals\].*?window\.addEventListener\('cafresohq:moneyEvent', onMoney\);",
    OFFICE, re.S)
check("found the COWORKER P&L live-totals listener in ui/office.jsx",
      pl is not None)
pl_src = pl.group(0) if pl else ''

check("the P&L listener credits earnedRaw (the ▲ half of the board)",
      'earnedRaw' in pl_src and 'BigInt(d.amountRaw)' in pl_src)

check("the P&L listener names the income kinds it will bank",
      re.search(r"tip:\s*true", pl_src) is not None
      and re.search(r"payday:\s*true", pl_src) is not None,
      'expected an EARNING_KINDS-style allowlist of tip + payday')

check("it does NOT bank 'furnish' — a purchase is not income",
      re.search(r"furnish:\s*true", pl_src) is None)

guard = re.search(r"if \(!d\.agentId \|\| !d\.amountRaw([^)]*)\) return;", pl_src)
check("the listener's early-return guard exists", guard is not None)
check("the guard rejects any event whose kind is not an earning kind, before "
      "it reaches setPlTotals",
      guard is not None and 'EARNING_KINDS' in guard.group(1),
      guard.group(1).strip() if guard else '')

# The listener must be a strict allowlist, not a furnish-shaped blocklist:
# a future spend kind must not sail through the way furnish did.
check("the filter is an allowlist (unknown/new kinds are ignored), not a "
      "one-off !== 'furnish' patch",
      "!== 'furnish'" not in pl_src and "!= 'furnish'" not in pl_src)

# ── Second rendering: the desk chip's sign. ──────────────────────────────
chip = re.search(r"px-tipamount.*?</div>", OFFICE, re.S)
check('found the Tip Rain amount chip', chip is not None)
chip_src = chip.group(0) if chip else ''
check("the desk chip does not print a spend as '+' — a furnish shows a minus",
      "'furnish' ? '−' : '+'" in chip_src or "'furnish' ? '-' : '+'" in chip_src,
      chip_src[:160])

print()
if FAILS:
    print('%d check(s) failed:' % len(FAILS))
    for f in FAILS:
        print('  - ' + f)
    sys.exit(1)
print('all checks passed')
