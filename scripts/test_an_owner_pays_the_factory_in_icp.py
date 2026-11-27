#!/usr/bin/env python3
"""An owner pays the factory in ICP and gets cycles, on a real replica
(docs/FACTORY_PAY_IN.md).

Starts from the factory that is live today (scripts/replica_harness/factory/
live_main.mo, a pinned copy), gives it an owner, a budget and a project, then
upgrades it to src/cf_factory/main.mo and checks nothing was lost. Then walks
the pay-in beside scripts/replica_harness/mock_icp.mo, which plays the ICP
ledger and the cycles minting canister: the happy path, every retry, the
limits, the pause switch and refunds.

Throwaway local replica on port 4984. Skipped without dfx, and under GitHub
Actions unless CAFRESOHQ_REPLICA=1.

    python3 scripts/test_an_owner_pays_the_factory_in_icp.py
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 4984
DFX_VERSION = os.environ.get('CAFRESOHQ_STATE_DFX', '0.24.3')
FAILS = []
IDS = ['fpi_owner', 'fpi_payer', 'fpi_payer2', 'fpi_agent', 'fpi_stranger']
T = 1_000_000_000_000
ICP = 100_000_000
FEE = 10_000
RATE = 15_197                      # cycles per e8s, as the mock mints
MARKUP = 1_000                     # cost plus 10%
MIN, MAX, DAY = ICP // 10, 5 * ICP, 40 * ICP
OLD_ARGS = (f'minCreateCycles = {T // 2} : nat; minUpgradeCycles = {T // 10} : nat; '
            f'reserveCycles = {T // 2} : nat; opFeeCycles = 1_000_000_000 : nat')


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)[:500]) if not cond else ''))
    if not cond:
        FAILS.append(name)


def credit(e8s):
    return e8s * RATE * 10_000 // (10_000 + MARKUP)


def nat(out):
    m = re.search(r'\(?([\d_]+) : nat', out)
    return int(m.group(1).replace('_', '')) if m else -1


def fields(out):
    return {k: int(v.replace('_', '')) for k, v in re.findall(r'(\w+) = ([\d_]+) : (?:nat|int)\b', out)}


def sub_hex(principal):
    """The subaccount that stands for a principal: its length, its bytes, zeros."""
    raw = base64.b32decode(principal.replace('-', '').upper() + '=' * (-len(principal.replace('-', '')) % 8))[4:]
    return (bytes([len(raw)]) + raw).ljust(32, b'\0').hex()


def account_id(principal, sub):
    """The ICP ledger's account identifier, worked out here and not by the canister under test."""
    t = principal.replace('-', '').upper()
    raw = base64.b32decode(t + '=' * (-len(t) % 8))[4:]
    h = hashlib.sha224(b'\x0aaccount-id' + raw + bytes.fromhex(sub)).digest()
    return (zlib.crc32(h).to_bytes(4, 'big') + h).hex()


def blob(hexs):
    return 'blob "' + ''.join('\\' + hexs[i:i + 2] for i in range(0, len(hexs), 2)) + '"'


class Replica:
    def __init__(self, tmp):
        self.tmp = tmp
        self.env = dict(os.environ, DFX_VERSION=DFX_VERSION, DFX_WARNING='-mainnet_plaintext_identity')

    def dfx(self, *args, identity=None, timeout=300):
        cmd = ['dfx', *args] + (['--identity', identity] if identity else [])
        return subprocess.run(cmd, cwd=self.tmp, env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def call(self, who, canister, method, arg='()', query=False, extra=()):
        a = ['canister', 'call', canister, method, arg, '--output', 'idl', *extra] + (['--query'] if query else [])
        r = self.dfx(*a, identity=who)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())

    def principal(self, who):
        return self.dfx('identity', 'get-principal', identity=who).stdout.strip()


def project(tmp, factory_main):
    (Path(tmp) / 'dfx.json').write_text(json.dumps({
        'version': 1,
        'canisters': {'cf_factory': {'type': 'motoko', 'main': factory_main},
                      'mock_icp': {'type': 'motoko', 'main': 'harness/mock_icp.mo'}},
        'defaults': {'build': {'args': '', 'packtool': ''}},
        'networks': {'local': {'bind': f'127.0.0.1:{PORT}', 'type': 'ephemeral'}},
    }))


def main():
    print('an owner pays the factory in ICP and gets cycles, on a real replica')
    if not shutil.which('dfx'):
        print('  skipped: dfx is not on PATH')
        return 0
    if os.environ.get('GITHUB_ACTIONS') and os.environ.get('CAFRESOHQ_REPLICA') != '1':
        print('  skipped under GITHUB_ACTIONS (set CAFRESOHQ_REPLICA=1 to run the replica here)')
        return 0
    tmp = tempfile.mkdtemp(prefix='hq-payin-')
    (Path(tmp) / 'src').symlink_to(ROOT / 'src')
    (Path(tmp) / 'harness').symlink_to(ROOT / 'scripts/replica_harness')
    project(tmp, 'harness/factory/live_main.mo')
    rep = Replica(tmp)
    try:
        # ── the stored data of the live factory still fits the new one ──
        cache = rep.dfx('cache', 'show').stdout.strip()
        moc = [f'{cache}/moc', '--package', 'base', f'{cache}/base']
        for name, src in (('old', 'scripts/replica_harness/factory/live_main.mo'), ('new', 'src/cf_factory/main.mo')):
            subprocess.run(moc + ['--stable-types', str(ROOT / src), '-o', str(Path(tmp) / f'{name}.wasm')],
                           capture_output=True, text=True)
        r = subprocess.run(moc + ['--stable-compatible', str(Path(tmp) / 'old.most'), str(Path(tmp) / 'new.most')],
                           capture_output=True, text=True)
        check("the new factory can read the live factory's stored data (moc --stable-compatible)",
              r.returncode == 0 and (Path(tmp) / 'new.most').exists(), r.stderr)

        for i in IDS:
            rep.dfx('identity', 'new', i, '--storage-mode', 'plaintext', '--force')
        with open(Path(tmp) / 'replica.log', 'w') as fh:
            r = subprocess.run(['dfx', 'start', '--clean', '--background'], cwd=tmp, env=rep.env,
                               stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, timeout=300)
        check('the replica starts', r.returncode == 0)
        r = rep.dfx('deploy', 'cf_factory', '--argument', f'(record {{ {OLD_ARGS} }})', identity='fpi_owner', timeout=600)
        check("today's live factory deploys", r.returncode == 0, r.stderr[-300:])
        r = rep.dfx('deploy', 'mock_icp', identity='fpi_owner', timeout=600)
        check('the mock ICP ledger and minting canister deploy', r.returncode == 0, r.stderr[-300:])
        if FAILS:
            return 1
        rep.dfx('ledger', 'fabricate-cycles', '--canister', 'mock_icp', '--t', '1000', identity='fpi_owner')
        factory = rep.dfx('canister', 'id', 'cf_factory').stdout.strip()
        mock = rep.dfx('canister', 'id', 'mock_icp').stdout.strip()
        owner, payer, payer2, agent, stranger = (rep.principal(i) for i in IDS)
        wallet = rep.dfx('identity', 'get-wallet', identity='fpi_owner').stdout.strip()
        far = int(time.time() * 1e9) + 30 * 86_400 * 10**9

        # ── state made on the live version ──────────────────────────────
        rep.call('fpi_owner', 'cf_factory', 'deposit', '()', extra=('--with-cycles', str(5 * T), '--wallet', wallet))
        rep.call('fpi_owner', 'cf_factory', 'setBudget', f'(principal "{agent}", {3 * T} : nat, 2 : nat, {far} : int)',
                 extra=('--wallet', wallet))
        ok, out = rep.call('fpi_agent', 'cf_factory', 'createProject', f'(principal "{wallet}", "hello", {T} : nat)')
        check('on the live version: an owner deposits, sets a budget, and the agent makes a project', ok and 'canisterId' in out, out)
        before = fields(rep.call('fpi_stranger', 'cf_factory', 'factoryStatus', '()', query=True)[1])

        # ── upgrade, pay-in left off ────────────────────────────────────
        project(tmp, 'src/cf_factory/main.mo')
        r = rep.dfx('deploy', 'cf_factory', '--argument', f'(record {{ {OLD_ARGS} }})', identity='fpi_owner', timeout=600)
        if r.returncode != 0:
            r = rep.dfx('deploy', 'cf_factory', '--argument', f'(record {{ {OLD_ARGS}; pay = null }})', identity='fpi_owner', timeout=600)
            check('the upgrade needs "pay = null" spelled out (the old arguments alone were refused)', r.returncode == 0, r.stderr[-400:])
        else:
            check("the upgrade takes today's install arguments unchanged", True)
        after = fields(rep.call('fpi_stranger', 'cf_factory', 'factoryStatus', '()', query=True)[1])
        check('the upgrade keeps what the factory owes owners and the fees it took',
              after.get('owed') == before.get('owed') and after.get('feesTaken') == before.get('feesTaken') and before.get('owed', 0) > 0,
              (before, after))
        ok, out = rep.call('fpi_agent', 'cf_factory', 'projectsForMe', '()', query=True)
        check('...and the project', ok and 'name = "hello"' in out, out[:300])
        ok, out = rep.call('fpi_agent', 'cf_factory', 'budgetsForMe', '()', query=True)
        check('...and the budget, with what was used', ok and 'cap = 3_000_000_000_000' in out and 'used = 1_000_000_000_000' in out, out[:300])
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'settle', f'(principal "{payer}", variant {{ ICP }})')
        check('with no pay settings, paying is off', ok and 'not turned on' in out, out)
        ok, out = rep.call('fpi_agent', 'cf_factory', 'status', '(1 : nat)')
        check('...and projects work as before', ok and 'running' in out, out[:200])

        # ── turn pay-in on ──────────────────────────────────────────────
        pay = (f'pay = opt record {{ icpLedger = principal "{mock}"; cmc = principal "{mock}"; markupBps = {MARKUP} : nat; '
               f'minIcp = {MIN} : nat; maxIcp = {MAX} : nat; dayIcp = {DAY} : nat }}')
        r = rep.dfx('deploy', 'cf_factory', '--upgrade-unchanged', '--argument', f'(record {{ {OLD_ARGS}; {pay} }})',
                    identity='fpi_owner', timeout=600)
        check('a second upgrade turns pay-in on', r.returncode == 0, r.stderr[-400:])
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'payStats', '()', query=True)
        check('payStats shows it on, with the 10% markup', ok and 'on = true' in out and 'markupBps = 1_000' in out, out)

        def deposit_acct(p):
            return f'record {{ owner = principal "{factory}"; subaccount = opt {blob(sub_hex(p))} }}'

        def fund(p, e8s):
            return rep.call('fpi_stranger', 'mock_icp', 'mint', f'({deposit_acct(p)}, {e8s} : nat)')

        def settle(p, who='fpi_stranger'):
            return rep.call(who, 'cf_factory', 'settle', f'(principal "{p}", variant {{ ICP }})')

        def balance(who='fpi_payer'):
            return nat(rep.call(who, 'cf_factory', 'myBalance', '()', query=True)[1])

        def held(acct):
            return nat(rep.call('fpi_stranger', 'mock_icp', 'icrc1_balance_of', f'({acct})', query=True)[1])

        # ── the deposit address ─────────────────────────────────────────
        ok, out = rep.call('fpi_payer', 'cf_factory', 'depositAddress', '()', query=True)
        legacy = (re.search(r'legacyAccountId = "([0-9a-f]+)"', out) or [None, ''])[1]
        want = account_id(factory, sub_hex(payer))
        check("the deposit address is the factory's account for that owner, and the older account id is the ledger's own hash of it",
              ok and len(legacy) == 64 and legacy == want and blob(sub_hex(payer)).lower() in out.lower().replace('\\\\', '\\'), (out, want))
        ok, out2 = rep.call('fpi_stranger', 'cf_factory', 'depositAddressFor', f'(principal "{payer}")', query=True)
        check('anyone (an agent, say) can read an owner their address', ok and legacy in out2, out2)

        # ── the happy path ──────────────────────────────────────────────
        fund(payer, 2 * ICP + FEE)
        rep.call('fpi_stranger', 'cf_factory', 'refreshRate', '()')
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'quote', f'(variant {{ ICP }}, {2 * ICP} : nat)', query=True)
        q = fields(out)
        check('quote says what 2 ICP buys: cost plus 10%', ok and q.get('cycles') == credit(2 * ICP) and q.get('rateAt', 0) > 0, out)
        fs0 = fields(rep.call('fpi_stranger', 'cf_factory', 'factoryStatus', '()', query=True)[1])
        ok, out = settle(payer)
        check('anyone can settle for the owner', ok and 'credited' in out, out)
        expect = credit(2 * ICP)
        check("the owner's balance rises by exactly the quote", balance() == expect, (balance(), expect))
        fs1 = fields(rep.call('fpi_stranger', 'cf_factory', 'factoryStatus', '()', query=True)[1])
        minted = 2 * ICP * RATE
        check('the factory really received the cycles, owes the owner their share, and kept the rest as its fee',
              fs1.get('owed') == fs0.get('owed') + expect and fs1.get('feesTaken') == fs0.get('feesTaken') + minted - expect
              and fs1.get('cycles', 0) - fs0.get('cycles', 0) > minted * 99 // 100, (fs0, fs1))
        check('the deposit address is empty afterwards', held(deposit_acct(payer)) == 0, held(deposit_acct(payer)))
        ok, out = settle(payer)
        check('settling again finds nothing to do', ok and 'the deposit holds 0.00000000 ICP' in out and balance() == expect, out)

        # ── the paid cycles are real: the owner spends them ─────────────
        ok, out = rep.call('fpi_payer', 'cf_factory', 'setBudget', f'(principal "{agent}", {2 * T} : nat, 1 : nat, {far} : int)')
        ok, out = rep.call('fpi_agent', 'cf_factory', 'createProject', f'(principal "{payer}", "paid", {T} : nat)')
        check('an agent builds a canister with cycles the owner paid for in ICP', ok and 'canisterId' in out, out)
        expect -= T

        # ── retries ─────────────────────────────────────────────────────
        fund(payer, ICP + FEE)
        rep.call('fpi_stranger', 'mock_icp', 'mock_fail_notify', '(1 : nat, "processing")')
        ok, out = settle(payer)
        check('minting not finished: settle says to call again, and nothing is credited yet',
              ok and 'call settle again' in out and balance() == expect, out)
        ok, out = rep.call('fpi_payer', 'cf_factory', 'refund', '(variant { ICP })')
        check("a refund can't cut in on a payment that is part-way through", ok and 'part-way' in out, out)
        ok, out = settle(payer)
        expect += credit(ICP)
        check('...the second settle finishes it, once', ok and 'credited' in out and balance() == expect, (out, balance(), expect))

        fund(payer, ICP + FEE)
        rep.call('fpi_stranger', 'mock_icp', 'mock_fail_notify', '(1 : nat, "reject")')
        ok, out = settle(payer)
        check('the minting canister rejects the call: the ICP is safe and nothing is credited',
              ok and 'the ICP is safe' in out and balance() == expect, out)
        settle(payer)
        ok, out = settle(payer)
        expect += credit(ICP)
        check('...settle again credits it once, and a third call adds nothing', balance() == expect, (balance(), expect))

        fund(payer, ICP + FEE)
        blocks0 = nat(rep.call('fpi_stranger', 'mock_icp', 'mock_blocks', '()', query=True)[1])
        rep.call('fpi_stranger', 'mock_icp', 'mock_fail_transfer', '(1 : nat)')
        ok, out = settle(payer)
        check('the ledger rejects the transfer call: the deposit stays put',
              ok and 'call settle again' in out and held(deposit_acct(payer)) == ICP + FEE and balance() == expect, out)
        ok, out = settle(payer)
        expect += credit(ICP)
        blocks1 = nat(rep.call('fpi_stranger', 'mock_icp', 'mock_blocks', '()', query=True)[1])
        check('...the retry moves the ICP once and credits once', 'credited' in out and balance() == expect and blocks1 == blocks0 + 1,
              (out, balance(), expect, blocks0, blocks1))

        fund(payer, ICP + FEE)
        rep.call('fpi_stranger', 'mock_icp', 'mock_fail_notify', '(1 : nat, "refund")')
        ok, out = settle(payer)
        check('the minting canister sends the ICP back: the owner is told, and nothing is credited',
              ok and 'sent the ICP back' in out and balance() == expect and held(deposit_acct(payer)) == ICP - 3 * FEE, (out, held(deposit_acct(payer))))
        ok, out = rep.call('fpi_payer', 'cf_factory', 'myPayments', '()', query=True)
        check('...and their payment list shows where it stopped', ok and 'failed' in out and 'mock: refunded' in out, out[:300])
        ok, out = settle(payer)
        expect += credit(ICP - 4 * FEE)
        check('...settling again pays in what came back', 'credited' in out and balance() == expect, (out, balance(), expect))


        # ── what the review asked for ───────────────────────────────────
        def last_id():
            out = rep.call('fpi_payer', 'cf_factory', 'myPayments', '()', query=True)[1]
            return int(re.search(r'\bid = ([\d_]+)', out).group(1).replace('_', ''))

        def blocks():
            return nat(rep.call('fpi_stranger', 'mock_icp', 'mock_blocks', '()', query=True)[1])

        r = rep.dfx('canister', 'call', 'cf_factory', 'settle', f'(principal "{payer}", variant {{ ICP }})', '--output', 'idl', identity='anonymous')
        check('an anonymous caller is turned away before the factory calls anything', 'sign in' in r.stdout + r.stderr, r.stdout + r.stderr)

        fund(payer, ICP + FEE)
        b0 = blocks()
        rep.call('fpi_stranger', 'mock_icp', 'mock_lose_transfer_reply', '(1 : nat)')
        ok, out = settle(payer)
        check('the transfer goes through but its reply is lost: the factory says to call again',
              ok and 'call settle again' in out and held(deposit_acct(payer)) == 0 and balance() == expect, out)
        ok, out = settle(payer)
        expect += credit(ICP)
        check('...the retry finds the same transfer (no second one) and credits once',
              'credited' in out and balance() == expect and blocks() == b0 + 1, (out, balance(), expect, b0, blocks()))

        fund(payer, ICP + FEE)
        results = []
        ts = [threading.Thread(target=lambda: results.append(settle(payer)[1])) for _ in range(5)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        expect += credit(ICP)
        check('five settles at once credit one payment', balance() == expect and sum('credited' in x for x in results) >= 1,
              (balance(), expect, [x[:80] for x in results]))

        fund(payer, ICP + FEE)
        rep.call('fpi_stranger', 'mock_icp', 'mock_fail_notify', '(1 : nat, "other")')
        ok, out = settle(payer)
        check('the minting canister says try later: the payment stays open', ok and 'call settle again' in out and balance() == expect, out)
        # an upgrade in the middle, with today's arguments and no pay settings
        r = rep.dfx('deploy', 'cf_factory', '--upgrade-unchanged', '--argument', f'(record {{ {OLD_ARGS} }})', identity='fpi_owner', timeout=600)
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'payStats', '()', query=True)
        check('an upgrade that leaves the pay settings out keeps them', r.returncode == 0 and 'on = true' in out and 'markupBps = 1_000' in out, out + r.stderr[-200:])
        ok, out = settle(payer)
        expect += credit(ICP)
        check('...and the payment that was part-way through finishes after it', 'credited' in out and balance() == expect, (out, balance(), expect))

        fund(payer, ICP + FEE)
        rep.call('fpi_stranger', 'mock_icp', 'mock_fail_notify', '(1 : nat, "invalid")')
        ok, out = settle(payer)
        pid = last_id()
        check('the minting canister refuses the transfer: the payment stops as failed, uncredited',
              ok and 'refused the transfer' in out and balance() == expect, out)
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'retryPayment', f'({pid} : nat, null)')
        check("a stranger can't reopen a payment", ok and 'controllers only' in out, out)
        ok, out = rep.call('fpi_owner', 'cf_factory', 'retryPayment', f'({pid} : nat, null)')
        check('the operator reopens it', ok and 'ok' in out, out)
        ok, out = settle(payer)
        expect += credit(ICP)
        check('...and settle then credits it, once', 'credited' in out and balance() == expect, (out, balance(), expect))
        ok, out = rep.call('fpi_owner', 'cf_factory', 'retryPayment', f'({pid} : nat, null)')
        check('a credited payment cannot be reopened', ok and 'already credited' in out, out)
        ok, out = rep.call('fpi_owner', 'cf_factory', 'retryPayment', f'(1 : nat, opt ({b0} : nat64))')
        check("...nor can another payment be pointed at a block that is taken", ok and ('already credited' in out or 'belongs to payment' in out), out)

        fund(payer, ICP + FEE)
        rep.call('fpi_stranger', 'mock_icp', 'mock_fail_notify', '(1 : nat, "lie")')
        ok, out = settle(payer)
        pid = last_id()
        check('a minting canister that claims cycles it never sent is not believed', ok and 'nothing was credited' in out and balance() == expect, out)
        rep.call('fpi_owner', 'cf_factory', 'retryPayment', f'({pid} : nat, null)')
        ok, out = settle(payer)
        expect += credit(ICP)
        check('...and the real answer is credited after the operator reopens it', 'credited' in out and balance() == expect, (out, balance(), expect))

        fund(payer, ICP + FEE)
        rep.call('fpi_stranger', 'mock_icp', 'mock_fail_notify', '(1 : nat, "processing")')
        settle(payer)
        pid = last_id()
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'closePayment', f'({pid} : nat, "test")')
        check("a stranger can't close a payment", ok and 'controllers only' in out, out)
        ok, out = rep.call('fpi_owner', 'cf_factory', 'closePayment', f'({pid} : nat, "test")')
        check('the operator can close a payment that is stuck, so the owner is not locked out', ok and 'ok' in out, out)
        fund(payer, ICP // 5 + FEE)
        ok, out = settle(payer)
        expect += credit(ICP // 5)
        check('...the owner can pay again', 'credited' in out and balance() == expect, (out, balance(), expect))
        rep.call('fpi_owner', 'cf_factory', 'retryPayment', f'({pid} : nat, null)')
        ok, out = settle(payer)
        expect += credit(ICP)
        check('...and the closed payment can still be reopened and credited', 'credited' in out and balance() == expect, (out, balance(), expect))

        # ── limits ──────────────────────────────────────────────────────
        fund(payer, ICP // 20)
        ok, out = settle(payer)
        check('a deposit under 0.1 ICP is not taken', ok and 'smallest payment is 0.10000000 ICP' in out and balance() == expect, out)
        ok, out = rep.call('fpi_payer', 'cf_factory', 'refund', '(variant { ICP })')
        mine = f'record {{ owner = principal "{payer}"; subaccount = null }}'
        check('...and refund sends it back to the owner, less the ledger fee', ok and 'ok' in out and held(mine) == ICP // 20 - FEE, (out, held(mine)))
        ok, out = rep.call('fpi_payer', 'cf_factory', 'refund', '(variant { ICP })')
        check('a refund after everything is settled has nothing to return', ok and 'nothing to refund' in out, out)
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'refund', '(variant { ICP })')
        check("a stranger's refund reaches nobody else's deposit", ok and 'nothing to refund' in out, out)

        rep.call('fpi_stranger', 'mock_icp', 'mint', f'(record {{ owner = principal "{payer2}"; subaccount = null }}, {ICP} : nat)')
        rep.call('fpi_payer2', 'mock_icp', 'icrc2_approve',
                 f'(record {{ spender = record {{ owner = principal "{factory}"; subaccount = null }}; amount = {ICP // 2 + 2 * FEE} : nat }})')
        ok, out = rep.call('fpi_payer2', 'cf_factory', 'payIcp', f'({ICP // 2} : nat)')
        check('a wallet that can approve pays in one call (payIcp)',
              ok and 'credited' in out and balance('fpi_payer2') == credit(ICP // 2), (out, balance('fpi_payer2')))
        ok, out = rep.call('fpi_payer2', 'cf_factory', 'payIcp', f'({ICP // 2} : nat)')
        check('...and only what was approved', ok and 'InsufficientAllowance' in out and balance('fpi_payer2') == credit(ICP // 2), out)

        fund(payer, 6 * ICP + FEE)
        ok, out = settle(payer)
        expect += credit(5 * ICP)
        check('a deposit over the 5 ICP cap is taken 5 ICP at a time', 'credited' in out and balance() == expect and held(deposit_acct(payer)) == ICP,
              (out, balance(), expect))
        ok, out = settle(payer)
        expect += credit(ICP - FEE)
        check('...and the rest on the next settle', 'credited' in out and balance() == expect, (out, balance(), expect))

        # a new pay setting replaces the stored one: set today's limit just above what was taken
        today = fields(rep.call('fpi_stranger', 'cf_factory', 'payStats', '()', query=True)[1]).get('icpToday', 0)
        tight = pay.replace(f'dayIcp = {DAY} : nat', f'dayIcp = {max(today + ICP // 2, MAX)} : nat')
        r = rep.dfx('deploy', 'cf_factory', '--upgrade-unchanged', '--argument', f'(record {{ {OLD_ARGS}; {tight} }})',
                    identity='fpi_owner', timeout=600)
        fund(payer, 2 * ICP + FEE)
        ok, out = settle(payer)
        check("past the day's limit for all owners, a payment waits", r.returncode == 0 and ok and "today's limit" in out and balance() == expect, out)
        p2 = f'record {{ owner = principal "{payer2}"; subaccount = null }}'
        had = held(p2)
        rep.call('fpi_payer2', 'mock_icp', 'icrc2_approve',
                 f'(record {{ spender = record {{ owner = principal "{factory}"; subaccount = null }}; amount = {ICP} : nat }})')
        ok, out = rep.call('fpi_payer2', 'cf_factory', 'payIcp', f'({ICP * 3 // 4} : nat)')
        check('...and payIcp refuses before it takes any ICP', ok and "today's limit" in out and held(p2) == had - FEE, (out, had, held(p2)))
        r = rep.dfx('deploy', 'cf_factory', '--upgrade-unchanged', '--argument',
                    f'(record {{ {OLD_ARGS}; {pay.replace("minIcp = " + str(MIN), "minIcp = 0")} }})', identity='fpi_owner', timeout=600)
        check('settings that make no sense (a smallest payment of 0) make the upgrade fail, and the old ones stay',
              r.returncode != 0 and 'on = true' in rep.call('fpi_stranger', 'cf_factory', 'payStats', '()', query=True)[1], r.stderr[-200:])

        # ── the pause switch ────────────────────────────────────────────
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'setPayPaused', '(true)')
        check('only a controller can pause payments', ok and 'controllers only' in out, out)
        ok, out = rep.call('fpi_owner', 'cf_factory', 'setPayPaused', '(true)')
        check('a controller pauses payments', ok and 'ok' in out, out)
        ok, out = settle(payer)
        check('...settle stops', ok and 'paused' in out, out)
        ok, out = rep.call('fpi_agent', 'cf_factory', 'status', '(2 : nat)')
        check('...projects keep working', ok and 'running' in out, out[:200])
        ok, out = rep.call('fpi_payer', 'cf_factory', 'refund', '(variant { ICP })')
        check('...and an owner can still take an unsettled deposit back', ok and 'ok' in out and held(deposit_acct(payer)) == 0, out)
        rep.call('fpi_owner', 'cf_factory', 'setPayPaused', '(false)')

        # ── the books ───────────────────────────────────────────────────
        ok, out = settle(payer, who='fpi_payer')
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'settle', f'(principal "{payer}", variant {{ ckUSDT }})')
        check('ckUSDT is refused for now', ok and 'not accepted yet' in out, out)
        fs = fields(rep.call('fpi_stranger', 'cf_factory', 'factoryStatus', '()', query=True)[1])
        check('at the end the factory holds at least what it owes owners plus its reserve',
              fs.get('cycles', 0) >= fs.get('owed', 1) + fs.get('reserve', 0), fs)
        ok, out = rep.call('fpi_stranger', 'cf_factory', 'payStats', '()', query=True)
        st = fields(out)
        check('payStats counts every payment and the ICP turned into cycles', st.get('payments') == 15 and st.get('icpBurned', 0) > 18 * ICP, out)
        ok, out = rep.call('fpi_agent', 'cf_factory', 'getApiDoc', '()', query=True)
        check('the API doc tells an assistant how paying works', ok and 'settle(owner' in out and 'depositAddressFor' in out, out[-300:])
    finally:
        rep.dfx('stop')
        for i in IDS:
            rep.dfx('identity', 'remove', i, '--drop-wallets')
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(('%d FAILED: %s' % (len(FAILS), FAILS)) if FAILS else 'factory pay-in: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
