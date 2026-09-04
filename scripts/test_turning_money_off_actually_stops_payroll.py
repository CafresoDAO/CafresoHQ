#!/usr/bin/env python3
"""Turning Money & Payments OFF promised "Scheduled payroll stops running".
It didn't. The salary timer kept moving real ICP, with the UI hidden.

Settings → MODULES → 💰 Money & Payments is the master switch. Switching it
off pops a confirm dialog (`toggleMoney`, modals/settings.jsx) that makes
three promises in the boss's own words:

    • All agent spending is paused immediately.
    • Balances are NOT deleted — they stay on-chain under your Internet
      Identity and reappear when you turn this back on.
    • Scheduled payroll stops running.

What the off-path actually did on the chain was ONE call:

    await chain().wallet.pauseAll(true)

which lands on `setAllSpendPaused` in src/cafresohq_state/main.mo. That
flag is read in exactly one place — `recordSpend`, the cap gate the browser
calls before signing an AGENT-INITIATED transfer. It has nothing to do with
payroll. The canister says so itself, in the comment directly above the
other setter:

    /// Per-user payroll kill switch (independent of setAllSpendPaused).
    public shared (msg) func setPayrollPaused(paused : Bool) : async () {

and the timer path proves it: `scanPayroll` skips a user only
`if (not isPayrollPaused(user))`, `processDue` re-validates with
`isPayrollPaused` alone (twice, once after the balance await), and
`runPayrollNow` returns "paused" only for `isPayrollPaused`. None of the
three ever consults `isAllPaused` / `allSpendPaused`.

So the third bullet was false, and falsely in the direction that costs
money: a boss with a standing salary who turned Money off kept an on-chain
timer transferring their ICP to agent subaccounts out of the allowance they
had signed, once per period, indefinitely. And they could not see or stop
it — `moneyOn` gates the entire 💰 AGENT WALLETS panel, so the payout log,
the allowance readout, and ⏸ PAUSE PAYROLL (the only control that sets the
flag that does stop the timer) all render only while money is ON. The
switch that was supposed to stop payroll was also the switch that hid the
button that stops payroll.

Fix: the off-path now also calls `chain().payroll.pause(true)`. A failure
there is surfaced through the panel's `err` line (which renders on MODULES,
a panel that stays visible with money off) naming ⏸ PAUSE PAYROLL, instead
of being swallowed like the best-effort spend pause — because unlike the
spend pause, nothing else in the app blocks this one.

This test reads BOTH halves of the contract out of the real sources: the
dialog's promise from modals/settings.jsx, and the canister's proof that
`wallet.pauseAll` cannot possibly keep it. If the promise is ever made
again without the call that delivers it, this fails.

Run: python3 scripts/test_turning_money_off_actually_stops_payroll.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / 'modals' / 'settings.jsx'
STATE_MO = ROOT / 'src' / 'cafresohq_state' / 'main.mo'
FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name
          + (('  — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def toggle_money_body(src):
    """The real `const toggleMoney = async () => { ... };` body, taken by
    brace balance so the whole handler is examined, not a fixed window."""
    i = src.find('const toggleMoney')
    if i < 0:
        return None
    j = src.find('{', i)
    depth = 0
    for n in range(j, len(src)):
        if src[n] == '{':
            depth += 1
        elif src[n] == '}':
            depth -= 1
            if depth == 0:
                return src[i:n + 1]
    return None


def off_path(body):
    """Everything after the ON branch returns — i.e. the turn-OFF half."""
    m = re.search(r"Turn off Money", body)
    return body[m.start():] if m else None


def mo_func(src, name):
    """One `func <name>(...)` body from main.mo, by brace balance."""
    m = re.search(r'func\s+' + re.escape(name) + r'\s*\(', src)
    if not m:
        return None
    j = src.find('{', m.end())
    depth = 0
    for n in range(j, len(src)):
        if src[n] == '{':
            depth += 1
        elif src[n] == '}':
            depth -= 1
            if depth == 0:
                return src[m.start():n + 1]
    return None


def main():
    print('Turning Money off stops the on-chain payroll timer it promises to stop')
    src = SETTINGS.read_text(encoding='utf-8')
    mo = STATE_MO.read_text(encoding='utf-8')

    body = toggle_money_body(src)
    check('found toggleMoney (the Money & Payments master switch handler)',
          body is not None)
    if not body:
        print('\n1 FAILED — cannot locate the handler')
        return 1

    off = off_path(body)
    check('found the turn-OFF branch of toggleMoney', off is not None)
    if not off:
        print('\n1 FAILED — cannot locate the off-path')
        return 1

    # ── half 1: the promise the dialog makes ──────────────────────────────
    check('the off dialog still promises "Scheduled payroll stops running" '
          '(the claim under test)',
          'Scheduled payroll stops running' in off, off[:200])

    # ── half 2: the canister proves wallet.pauseAll cannot keep it ────────
    check('main.mo documents the payroll switch as independent of the spend '
          'switch (so one cannot stand in for the other)',
          'independent of setAllSpendPaused' in mo)

    for fn in ('scanPayroll', 'processDue', 'runPayrollNow'):
        f = mo_func(mo, fn)
        check(f'found {fn} in main.mo', f is not None)
        if not f:
            continue
        check(f'{fn} gates on isPayrollPaused', 'isPayrollPaused' in f)
        check(f'{fn} does NOT consult the spend kill switch — '
              f'wallet.pauseAll alone can never stop it',
              'isAllPaused' not in f and 'allSpendPaused' not in f, fn)

    # ── the fix: the off-path actually sets the flag that stops the timer ─
    check('the off-path calls wallet.pauseAll (blocks agent-initiated sends)',
          re.search(r'wallet\.pauseAll\(\s*true\s*\)', off) is not None)
    check('the off-path ALSO calls payroll.pause(true) — the only flag the '
          'salary timer reads (this is the fix)',
          re.search(r'payroll\.pause\(\s*true\s*\)', off) is not None,
          'promised "Scheduled payroll stops running" but never set '
          'payrollPaused; the timer kept paying out of the signed allowance '
          'with the whole money UI hidden')

    # ── and a failure to stop it is not swallowed ─────────────────────────
    m = re.search(r'payroll\.pause\(\s*true\s*\)\s*;?\s*\}?\s*(catch\s*\([^)]*\)\s*\{)',
                  off)
    check('a failed payroll.pause is caught', m is not None)
    if m:
        tail = off[m.end():m.end() + 400]
        check('a failed payroll.pause is SURFACED, not swallowed like the '
              'best-effort spend pause — nothing else in the app blocks this '
              'one, so silence here leaves real money moving',
              'setErr' in tail, tail[:120])
        check('and the message names ⏸ PAUSE PAYROLL, the control that does '
              'stop it (only reachable with Money back ON)',
              'PAUSE PAYROLL' in tail, tail[:200])

    print()
    if FAILS:
        print(f'{len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
