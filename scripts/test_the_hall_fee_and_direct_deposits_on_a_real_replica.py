#!/usr/bin/env python3
"""The hall fee, direct deposits and the #TooOld hardening, on a real replica
(docs/HALL_FEE_AND_OPEN_HIRING.md).

- Fee: a rate the plan admin sets (capped at 10%), fixed per job at posting,
  taken only from what the worker earns, sent to the treasury net of its own
  ledger fee, waived when too small; refunds carry none; 0 is the old hall.
- confirmDeposit: a job funded by a plain transfer into its escrow account
  (what a mandate's spend does), not by transfer_from.
- #TooOld on a fund retry: the hall reads the escrow before asking again, so a
  deposit that already landed is never taken twice.

Deploys the real hall next to the mock ICRC-2 ledger (port 4981) with six dfx
identities. Every balance is read from the ledger. Skipped without dfx, and
under GitHub Actions unless CAFRESOHQ_REPLICA=1.

    python3 scripts/test_the_hall_fee_and_direct_deposits_on_a_real_replica.py
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 4981
DFX_VERSION = os.environ.get('CAFRESOHQ_STATE_DFX', '0.24.3')
FAILS = []
IDS = ['hall_t_admin', 'hall_t_boss', 'hall_t_operator', 'hall_t_worker', 'hall_t_treasury', 'hall_t_stranger']
E8 = 100_000_000


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)[:400]) if not cond else ''))
    if not cond:
        FAILS.append(name)


class Replica:
    def __init__(self, tmp):
        self.tmp = tmp
        self.env = dict(os.environ, DFX_VERSION=DFX_VERSION, DFX_WARNING='-mainnet_plaintext_identity')

    def dfx(self, *args, identity, timeout=300):
        return subprocess.run(['dfx', *args, '--identity', identity], cwd=self.tmp, env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def call(self, who, canister, method, arg='()', query=False):
        r = self.dfx('canister', 'call', canister, method, arg, '--output', 'idl', *(['--query'] if query else []), identity=who)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())


def nat(out):
    m = re.search(r'\(([\d_]+) : nat\)', out)
    return int(m.group(1).replace('_', '')) if m else None


def main():
    print('the hall fee, direct deposits and #TooOld, on a real replica')
    if not shutil.which('dfx'):
        print('  skipped: dfx is not on PATH')
        return 0
    if os.environ.get('GITHUB_ACTIONS') and os.environ.get('CAFRESOHQ_REPLICA') != '1':
        print('  skipped under GITHUB_ACTIONS (set CAFRESOHQ_REPLICA=1 to run the replica here)')
        return 0
    tmp = tempfile.mkdtemp(prefix='hq-hallfee-')
    (Path(tmp) / 'src').symlink_to(ROOT / 'src')
    (Path(tmp) / 'harness').symlink_to(ROOT / 'scripts' / 'replica_harness')
    (Path(tmp) / 'dfx.json').write_text(json.dumps({
        'version': 1,
        'canisters': {
            'mock_ledger': {'type': 'motoko', 'main': 'harness/mock_ledger.mo'},
            'cafresohq_market': {'type': 'motoko', 'main': 'src/cafresohq_market/main.mo'},
        },
        'defaults': {'build': {'args': '', 'packtool': ''}},
        'networks': {'local': {'bind': f'127.0.0.1:{PORT}', 'type': 'ephemeral'}},
    }))
    rep = Replica(tmp)
    try:
        for i in IDS:
            subprocess.run(['dfx', 'identity', 'new', i, '--storage-mode', 'plaintext', '--force'], cwd=tmp, env=rep.env,
                           stdin=subprocess.DEVNULL, capture_output=True)
        with open(Path(tmp) / 'replica.log', 'w') as fh:
            r = subprocess.run(['dfx', 'start', '--clean', '--background'], cwd=tmp, env=rep.env,
                               stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, timeout=300)
        check('the replica starts', r.returncode == 0)
        for c in ('mock_ledger', 'cafresohq_market'):
            r = rep.dfx('deploy', c, identity='hall_t_admin', timeout=600)
            check(f'{c} deploys', r.returncode == 0, r.stderr[-300:])
        if FAILS:
            return 1
        led = rep.dfx('canister', 'id', 'mock_ledger', identity='hall_t_admin').stdout.strip()
        hall = rep.dfx('canister', 'id', 'cafresohq_market', identity='hall_t_admin').stdout.strip()
        pr = {i: rep.dfx('identity', 'get-principal', identity=i).stdout.strip() for i in IDS}
        boss, operator, worker, treasury, stranger = (pr[i] for i in IDS[1:])
        acct = lambda p: f'record {{ owner = principal "{p}"; subaccount = null }}'

        def bal(p):
            return nat(rep.call('hall_t_admin', 'mock_ledger', 'icrc1_balance_of', f'({acct(p)})', query=True)[1])

        fee = nat(rep.call('hall_t_admin', 'mock_ledger', 'icrc1_fee', '()', query=True)[1])
        rep.call('hall_t_admin', 'cafresohq_market', 'market_admin_add_ledger', f'(principal "{led}")')
        rep.call('hall_t_admin', 'mock_ledger', 'mint', f'({acct(boss)}, {100 * E8} : nat)')
        ok, out = rep.call('hall_t_operator', 'cafresohq_market', 'putListing',
                           f'(record {{ id = null; name = "Builder"; role = "Coding Agent"; pitch = "Motoko"; brain = "Sonnet"; '
                           f'tags = vec {{ "code" }}; ledger = principal "{led}"; price = {E8} : nat; payoutSub = null; active = true }})')
        lid = nat(out.replace('ok = ', '('))
        lid = int(re.search(r'ok = ([\d_]+)', out).group(1)) if 'ok =' in out else None
        check('the operator lists a coworker', lid is not None, out)
        rep.call('hall_t_operator', 'cafresohq_market', 'linkWorker', f'({lid} : nat, principal "{worker}")')

        def post(price=E8):
            ok, out = rep.call('hall_t_boss', 'cafresohq_market', 'postJob',
                               f'(record {{ title = "Review"; brief = "Review a canister"; kind = "code"; tags = vec {{ "code" }}; '
                               f'listing = opt ({lid} : nat); ledger = principal "{led}"; price = {price} : nat; deadlineSecs = 3600 : nat }})')
            m = re.search(r'ok = ([\d_]+)', out)
            return int(m.group(1).replace('_', '')) if m else out

        def approve(amount):
            return rep.call('hall_t_boss', 'mock_ledger', 'icrc2_approve',
                            f'(record {{ spender = {acct(hall)}; amount = {amount} : nat; from_subaccount = null; expected_allowance = null; '
                            'expires_at = null; fee = null; memo = null; created_at_time = null })')

        def fund(jid, price=E8):
            approve(price + 2 * fee)
            return rep.call('hall_t_boss', 'cafresohq_market', 'fundJob', f'({jid} : nat)')

        def work_and_accept(jid):
            rep.call('hall_t_worker', 'cafresohq_market', 'claimJob', f'({jid} : nat)')
            body = 'done'
            rep.call('hall_t_worker', 'cafresohq_market', 'deliverJob',
                     f'({jid} : nat, "done", "{body}", "{hashlib.sha256(body.encode()).hexdigest()}")')
            return rep.call('hall_t_boss', 'cafresohq_market', 'acceptDelivery', f'({jid} : nat, 5 : nat)')

        # ── no fee: the old hall ────────────────────────────────────────
        j1 = post(); fund(j1)
        before = bal(operator)
        ok, out = work_and_accept(j1)
        check('with no fee set, the worker receives exactly the price', ok and bal(operator) - before == E8, (out, bal(operator) - before))

        # ── the admin sets a fee ────────────────────────────────────────
        ok, out = rep.call('hall_t_stranger', 'cafresohq_market', 'market_admin_set_fee', f'(500 : nat, opt {acct(treasury)})')
        check("a stranger can't set the fee", not ok, out)
        ok, out = rep.call('hall_t_admin', 'cafresohq_market', 'market_admin_set_fee', f'(1001 : nat, opt {acct(treasury)})')
        check('the fee is capped at 10% in code', not ok and '1,000' in out, out)
        ok, out = rep.call('hall_t_admin', 'cafresohq_market', 'market_admin_set_fee', f'(500 : nat, opt {acct(treasury)})')
        check('the plan admin sets 5% to the treasury', ok, out)

        j2 = post(); fund(j2)
        check('a job posted now carries 5%', '500' in rep.call('hall_t_admin', 'cafresohq_market', 'jobHallFeeBps', f'({j2} : nat)', query=True)[1])
        op0, tr0 = bal(operator), bal(treasury)
        ok, out = work_and_accept(j2)
        cut = E8 * 500 // 10_000
        check('the worker receives the price minus 5%', bal(operator) - op0 == E8 - cut, (bal(operator) - op0, E8 - cut))
        check('the treasury receives 5% minus the ledger fee it paid itself', bal(treasury) - tr0 == cut - fee, (bal(treasury) - tr0, cut - fee))
        esc = rep.call('hall_t_admin', 'cafresohq_market', 'escrowAccount', f'({j2} : nat)', query=True)[1]
        sub = re.search(r'subaccount = opt (blob "[^"]*")', esc).group(1)
        held = nat(rep.call('hall_t_admin', 'mock_ledger', 'icrc1_balance_of',
                            f'(record {{ owner = principal "{hall}"; subaccount = opt {sub[5:] if False else sub} }})', query=True)[1])
        check('...and the escrow is empty afterwards', held == 0, held)

        # the rate is fixed at posting
        j3 = post(); fund(j3)
        rep.call('hall_t_admin', 'cafresohq_market', 'market_admin_set_fee', f'(1000 : nat, opt {acct(treasury)})')
        op0 = bal(operator)
        work_and_accept(j3)
        check('a fee change never touches a job already posted (still 5%)', bal(operator) - op0 == E8 - cut, bal(operator) - op0)

        # refunds carry no fee
        j4 = post(); fund(j4)
        b0, tr0 = bal(boss), bal(treasury)
        ok, out = rep.call('hall_t_boss', 'cafresohq_market', 'cancelJob', f'({j4} : nat, "changed my mind")')
        check('a cancelled job refunds the whole price, with no fee', ok and bal(boss) - b0 == E8 and bal(treasury) == tr0, (out, bal(boss) - b0))

        # waived when too small to pay its own way
        rep.call('hall_t_admin', 'cafresohq_market', 'market_admin_set_fee', f'(100 : nat, opt {acct(treasury)})')
        small = 100 * fee
        rep.call('hall_t_operator', 'cafresohq_market', 'putListing',
                 f'(record {{ id = opt ({lid} : nat); name = "Builder"; role = "Coding Agent"; pitch = "Motoko"; brain = "Sonnet"; '
                 f'tags = vec {{ "code" }}; ledger = principal "{led}"; price = {small} : nat; payoutSub = null; active = true }})')
        j5 = post(small); fund(j5, small)
        op0, tr0 = bal(operator), bal(treasury)
        work_and_accept(j5)
        check('a fee too small to cover its own ledger fee is waived: the worker gets the full price',
              bal(operator) - op0 == small and bal(treasury) == tr0, (bal(operator) - op0, small))

        # ── confirmDeposit: funded by a plain transfer into escrow ──────
        rep.call('hall_t_admin', 'cafresohq_market', 'market_admin_set_fee', f'(0 : nat, null)')
        j6 = post(small)
        esc = rep.call('hall_t_admin', 'cafresohq_market', 'escrowAccount', f'({j6} : nat)', query=True)[1]
        sub = re.search(r'subaccount = opt (blob "[^"]*")', esc).group(1)
        to = f'record {{ owner = principal "{hall}"; subaccount = opt {sub} }}'
        ok, out = rep.call('hall_t_boss', 'cafresohq_market', 'confirmDeposit', f'({j6} : nat)')
        check('confirmDeposit refuses an empty escrow', ok and 'needs price + fee' in out, out)
        rep.call('hall_t_boss', 'mock_ledger', 'icrc1_transfer',
                 f'(record {{ to = {to}; amount = {small + fee} : nat; fee = null; memo = null; from_subaccount = null; created_at_time = null }})')
        ok, out = rep.call('hall_t_stranger', 'cafresohq_market', 'confirmDeposit', f'({j6} : nat)')
        check("a stranger can't confirm someone else's job", ok and 'not your job' in out, out)
        ok, out = rep.call('hall_t_boss', 'cafresohq_market', 'confirmDeposit', f'({j6} : nat)')
        check('the boss confirms a direct deposit and the job is funded', ok and 'ok' in out, out)
        op0 = bal(operator)
        work_and_accept(j6)
        check('...and the worker is paid from it like any other job', bal(operator) - op0 == small, bal(operator) - op0)

        # ── #TooOld on a fund retry: read the escrow, never take twice ──
        j7 = post(small)
        rep.call('hall_t_boss', 'mock_ledger', 'icrc2_approve',
                 f'(record {{ spender = {acct(hall)}; amount = 0 : nat; from_subaccount = null; expected_allowance = null; '
                 'expires_at = null; fee = null; memo = null; created_at_time = null })')
        ok, out = rep.call('hall_t_boss', 'cafresohq_market', 'fundJob', f'({j7} : nat)')
        check('a first fund attempt fails (no allowance) and its stamp is remembered', ok and 'allowance' in out, out)
        esc = rep.call('hall_t_admin', 'cafresohq_market', 'escrowAccount', f'({j7} : nat)', query=True)[1]
        sub = re.search(r'subaccount = opt (blob "[^"]*")', esc).group(1)
        to = f'record {{ owner = principal "{hall}"; subaccount = opt {sub} }}'
        # As if that first attempt had landed after all: the deposit is in escrow.
        rep.call('hall_t_boss', 'mock_ledger', 'icrc1_transfer',
                 f'(record {{ to = {to}; amount = {small + fee} : nat; fee = null; memo = null; from_subaccount = null; created_at_time = null }})')
        rep.call('hall_t_admin', 'mock_ledger', 'mock_set_window', '(2 : nat)')
        time.sleep(4)
        approve(small + 2 * fee)
        b0 = bal(boss)
        ok, out = rep.call('hall_t_boss', 'cafresohq_market', 'fundJob', f'({j7} : nat)')
        check('a #TooOld retry finds the deposit in escrow and marks the job funded', ok and 'duplicate' in out, out)
        check('...without taking the boss\'s money a second time', bal(boss) == b0, (b0, bal(boss)))
        j8 = post(small)
        rep.call('hall_t_boss', 'mock_ledger', 'icrc2_approve',
                 f'(record {{ spender = {acct(hall)}; amount = 0 : nat; from_subaccount = null; expected_allowance = null; '
                 'expires_at = null; fee = null; memo = null; created_at_time = null })')
        rep.call('hall_t_boss', 'cafresohq_market', 'fundJob', f'({j8} : nat)')
        time.sleep(4)
        approve(small + 2 * fee)
        ok, out = rep.call('hall_t_boss', 'cafresohq_market', 'fundJob', f'({j8} : nat)')
        check('a #TooOld retry with an empty escrow says it never landed', ok and 'never landed' in out, out)
        ok, out = rep.call('hall_t_boss', 'cafresohq_market', 'fundJob', f'({j8} : nat)')
        check('...and the next try funds it with a fresh stamp', ok and 'ok' in out, out)

        ok, out = rep.call('hall_t_stranger', 'cafresohq_market', 'getApiDoc', '()', query=True)
        check('the API doc explains both ways to fund and the fee', ok and 'confirmDeposit' in out and 'never from refunds' in out, out[:200])
    finally:
        subprocess.run(['dfx', 'stop'], cwd=tmp, env=rep.env, stdin=subprocess.DEVNULL, capture_output=True)
        for i in IDS:
            subprocess.run(['dfx', 'identity', 'remove', i, '--drop-wallets'], cwd=tmp, env=rep.env,
                           stdin=subprocess.DEVNULL, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(('%d FAILED: %s' % (len(FAILS), FAILS)) if FAILS else 'hall fee: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
