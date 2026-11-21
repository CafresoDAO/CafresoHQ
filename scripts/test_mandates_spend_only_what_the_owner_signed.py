#!/usr/bin/env python3
"""Mandates spend only what the owner signed, on a real replica
(docs/AGENT_ECONOMY_ON_ICP.md §4.2, Phase 2).

An owner signs one ICRC-2 allowance to cafresohq_mandates and creates a mandate
for one agent: a per-transfer cap, a window cap, a list of purposes, optional
allowed recipients, and an expiry. The agent can then spend inside those limits
without a click per transfer, and every spend leaves a receipt.

Deploys the real src/cafresohq_mandates/main.mo next to the hall's mock ledger
(scripts/replica_harness/mock_ledger.mo, real ICRC-2 arithmetic and dedup) on a
throwaway local replica (port 4979), with four dfx identities: owner, agent,
a second agent, and a stranger. Every balance is checked on the ledger itself.
Skipped without dfx, and under GitHub Actions unless CAFRESOHQ_REPLICA=1.

    python3 scripts/test_mandates_spend_only_what_the_owner_signed.py
"""
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
PORT = 4979
DFX_VERSION = os.environ.get('CAFRESOHQ_STATE_DFX', '0.24.3')
FAILS = []
IDS = ['mdt_t_owner', 'mdt_t_agent', 'mdt_t_agent2', 'mdt_t_stranger']
E8 = 100_000_000


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)[:400]) if not cond else ''))
    if not cond:
        FAILS.append(name)


class Replica:
    def __init__(self, tmp):
        self.tmp = tmp
        self.env = dict(os.environ, DFX_VERSION=DFX_VERSION, DFX_WARNING='-mainnet_plaintext_identity')

    def dfx(self, *args, identity=None, timeout=300):
        cmd = ['dfx', *args] + (['--identity', identity] if identity else [])
        return subprocess.run(cmd, cwd=self.tmp, env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def call(self, who, canister, method, arg='()', query=False):
        a = ['canister', 'call', canister, method, arg, '--output', 'idl'] + (['--query'] if query else [])
        r = self.dfx(*a, identity=who)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())

    def principal(self, who):
        return self.dfx('identity', 'get-principal', identity=who).stdout.strip()


def nat(out):
    m = re.search(r'\(([\d_]+) : nat\)', out)
    return int(m.group(1).replace('_', '')) if m else None


def main():
    print('mandates spend only what the owner signed, on a real replica')
    if not shutil.which('dfx'):
        print('  skipped: dfx is not on PATH')
        return 0
    if os.environ.get('GITHUB_ACTIONS') and os.environ.get('CAFRESOHQ_REPLICA') != '1':
        print('  skipped under GITHUB_ACTIONS (set CAFRESOHQ_REPLICA=1 to run the replica here)')
        return 0
    tmp = tempfile.mkdtemp(prefix='hq-mandates-')
    (Path(tmp) / 'src').symlink_to(ROOT / 'src')
    (Path(tmp) / 'harness').symlink_to(ROOT / 'scripts' / 'replica_harness')
    (Path(tmp) / 'dfx.json').write_text(json.dumps({
        'version': 1,
        'canisters': {
            'mock_ledger': {'type': 'motoko', 'main': 'harness/mock_ledger.mo'},
            'cafresohq_mandates': {'type': 'motoko', 'main': 'src/cafresohq_mandates/main.mo'},
        },
        'defaults': {'build': {'args': '', 'packtool': ''}},
        'networks': {'local': {'bind': f'127.0.0.1:{PORT}', 'type': 'ephemeral'}},
    }))
    rep = Replica(tmp)
    try:
        for i in IDS:
            rep.dfx('identity', 'new', i, '--storage-mode', 'plaintext', '--force')
        with open(Path(tmp) / 'replica.log', 'w') as fh:
            r = subprocess.run(['dfx', 'start', '--clean', '--background'], cwd=tmp, env=rep.env,
                               stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, timeout=300)
        check('the replica starts', r.returncode == 0)
        r = rep.dfx('deploy', 'mock_ledger', identity='mdt_t_owner', timeout=600)
        check('the mock ledger deploys', r.returncode == 0, r.stderr[-300:])
        ledger = rep.dfx('canister', 'id', 'mock_ledger').stdout.strip()
        r = rep.dfx('deploy', 'cafresohq_mandates', '--argument',
                    f'(record {{ ledgers = vec {{ record {{ ledger = principal "{ledger}"; token = "MOCK" }} }} }})',
                    identity='mdt_t_owner', timeout=600)
        check('cafresohq_mandates deploys', r.returncode == 0, r.stderr[-300:])
        if FAILS:
            return 1
        mand = rep.dfx('canister', 'id', 'cafresohq_mandates').stdout.strip()
        owner, agent, agent2, stranger = (rep.principal(i) for i in IDS)
        payee = stranger  # any account can receive
        fee = nat(rep.call('mdt_t_owner', 'mock_ledger', 'icrc1_fee', '()', query=True)[1])

        def bal(p):
            return nat(rep.call('mdt_t_owner', 'mock_ledger', 'icrc1_balance_of',
                                f'(record {{ owner = principal "{p}"; subaccount = null }})', query=True)[1])

        rep.call('mdt_t_owner', 'mock_ledger', 'mint', f'(record {{ owner = principal "{owner}"; subaccount = null }}, {100 * E8} : nat)')
        ok, out = rep.call('mdt_t_owner', 'mock_ledger', 'icrc2_approve',
                           f'(record {{ spender = record {{ owner = principal "{mand}"; subaccount = null }}; amount = {10 * E8} : nat; '
                           'from_subaccount = null; expected_allowance = null; expires_at = null; fee = null; memo = null; created_at_time = null })')
        check('the owner signs one allowance to the mandates canister', ok and 'Ok' in out, out)

        far = int(time.time() * 1e9) + 30 * 86_400 * 10**9

        def mandate_args(**k):
            d = dict(agent=agent, title='Builder: test spending', per=1 * E8, win=2 * E8, secs=60,
                     allowed='vec {}', purposes='vec { "cycles"; "tip" }', exp=far)
            d.update(k)
            return (f'(record {{ agent = principal "{d["agent"]}"; title = "{d["title"]}"; ledger = principal "{ledger}"; '
                    f'fromSubaccount = null; perTransferMax = {d["per"]} : nat; windowMax = {d["win"]} : nat; '
                    f'windowSecs = {d["secs"]} : nat; allowedTo = {d["allowed"]}; purposes = {d["purposes"]}; expiresAt = {d["exp"]} : int }})')

        # ── creating ─────────────────────────────────────────────────────
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'createMandate', mandate_args())
        check('the owner creates a mandate for the agent', ok and 'ok = 1' in out, out)
        for label, kw, why in [
            ('a ledger off the allowlist is refused', {}, None),
            ('windowMax under perTransferMax is refused', {'win': E8 // 2}, 'windowMax'),
            ('a window under 60 s is refused', {'secs': 10}, 'windowSecs'),
            ('an unknown purpose is refused', {'purposes': 'vec { "gambling" }'}, 'unknown purpose'),
            ('an expiry in the past is refused', {'exp': 1}, 'expiresAt'),
            ('a lifetime under an hour is refused', {'exp': int(time.time() * 1e9) + 60 * 10**9}, 'an hour'),
            ("a window that can't cover one transfer plus the fee is refused", {'win': E8}, 'ledger fee'),
            ('the owner as their own agent is refused', {'agent': owner}, 'its own principal'),
        ]:
            if why is None:
                arg = mandate_args().replace(f'ledger = principal "{ledger}"', f'ledger = principal "{mand}"')
                ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'createMandate', arg)
                check(label, ok and 'allowlist' in out, out)
            else:
                ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'createMandate', mandate_args(**kw))
                check(label, ok and why in out, out)

        def spend(who, amount, purpose='cycles', mid=1, to=None, note='test'):
            to = to or payee
            return rep.call(who, 'cafresohq_mandates', 'spend',
                            f'(record {{ mandateId = {mid} : nat; to = record {{ owner = principal "{to}"; subaccount = null }}; '
                            f'amount = {amount} : nat; purpose = "{purpose}"; note = "{note}"; memo = null }})')

        # ── spending inside the limits ──────────────────────────────────
        before_owner, before_payee = bal(owner), bal(payee)
        ok, out = spend('mdt_t_agent', E8 // 2)
        check('the agent spends 0.5 inside its caps', ok and 'ok = record' in out, out)
        check('...the payee received exactly 0.5 on the ledger', bal(payee) - before_payee == E8 // 2, (bal(payee), before_payee))
        check('...and the owner paid 0.5 plus the ledger fee', before_owner - bal(owner) == E8 // 2 + fee, (before_owner, bal(owner), fee))

        # ── refusals ────────────────────────────────────────────────────
        ok, out = spend('mdt_t_stranger', 1000)
        check("a stranger can't spend from the mandate", ok and 'only this mandate' in out, out)
        ok, out = spend('mdt_t_agent2', 1000)
        check("another agent can't spend from it", ok and 'only this mandate' in out, out)
        ok, out = spend('mdt_t_agent', E8 + 1)
        check('over the per-transfer cap is refused', ok and 'per-transfer cap' in out, out)
        ok, out = spend('mdt_t_agent', 1000, purpose='payroll')
        check("a purpose the mandate doesn't cover is refused", ok and "doesn't cover" in out, out)
        ok, out = spend('mdt_t_agent', E8)
        check('a second spend that fits the window works', ok and 'ok = record' in out, out)
        ok, out = spend('mdt_t_agent', E8 // 2 + 1)
        left = 2 * E8 - (E8 // 2 + fee) - (E8 + fee)
        check('over the window cap is refused; the cap counts fees and says what is left',
              ok and 'window cap' in out and f'{left} left' in out.replace('_', ''), (out, left))
        before = bal(payee)
        check('...and nothing moved for the refused spends', bal(payee) == before)

        # ── pause, pauseAll, revoke, expiry ────────────────────────────
        rep.call('mdt_t_owner', 'cafresohq_mandates', 'pauseMandate', '(1, true)')
        ok, out = spend('mdt_t_agent', 1000)
        check('a paused mandate refuses', ok and 'paused' in out, out)
        rep.call('mdt_t_owner', 'cafresohq_mandates', 'pauseMandate', '(1, false)')
        rep.call('mdt_t_owner', 'cafresohq_mandates', 'pauseAll', '(true)')
        ok, out = spend('mdt_t_agent', 1000)
        check("the owner's pause-all stops it too", ok and 'paused' in out, out)
        rep.call('mdt_t_owner', 'cafresohq_mandates', 'pauseAll', '(false)')
        ok, out = rep.call('mdt_t_stranger', 'cafresohq_mandates', 'pauseMandate', '(1, true)')
        check("a stranger can't pause someone else's mandate", ok and 'not your mandate' in out, out)

        # recipients allowlist
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'createMandate',
                           mandate_args(allowed=f'vec {{ record {{ owner = principal "{payee}"; subaccount = null }} }}', title='only the payee'))
        mid2 = 2
        ok, out = spend('mdt_t_agent', 1000, mid=mid2, to=agent2)
        check('a recipient off the allowed list is refused', ok and "doesn't allow that recipient" in out, out)
        ok, out = spend('mdt_t_agent', 1000, mid=mid2, to=payee)
        check('the allowed recipient is paid', ok and 'ok = record' in out, out)

        # window resets
        time.sleep(62)
        ok, out = spend('mdt_t_agent', E8)
        check('a new window starts after windowSecs', ok and 'ok = record' in out, out)

        # allowance runs out: a known refusal gives the reservation back
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'createMandate',
                           mandate_args(per=50 * E8, win=60 * E8, title='bigger than the allowance'))
        ok, out = spend('mdt_t_agent', 40 * E8, mid=3)
        check('a spend over the ledger allowance is refused by the ledger', ok and 'allowance' in out, out)
        ok, out = rep.call('mdt_t_agent', 'cafresohq_mandates', 'mandatesForMe', '()', query=True)
        m3 = out[out.find('id = 3'):] if 'id = 3' in out else ''
        check("...and the refused amount doesn't count against the window", 'windowSpent = 0' in m3, m3[:600])

        # receipts
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'receiptsFor', '(1)', query=True)
        check('the owner sees a receipt for every spend from mandate 1', ok and out.count('status = "ok"') == 3, out[:600])
        ok, out = rep.call('mdt_t_stranger', 'cafresohq_mandates', 'receiptsFor', '(1)', query=True)
        check("a stranger can't read the receipts", ok and 'vec {}' in out, out)
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'receiptsFor', '(3)', query=True)
        check('the refused spend is on record as failed', ok and 'failed:' in out, out[:400])
        ok, out = rep.call('mdt_t_agent', 'cafresohq_mandates', 'retrySpend', '(1, 1)')
        check("a settled receipt can't be retried", ok and 'only a receipt in the unknown' in out, out)

        # revoke and expiry
        rep.call('mdt_t_owner', 'cafresohq_mandates', 'revokeMandate', '(1)')
        ok, out = spend('mdt_t_agent', 1000)
        check('a revoked mandate refuses', ok and 'revoked' in out, out)
        # fees count: many tiny spends can't drain the owner through fees (Builder's review, 2)
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'createMandate',
                           mandate_args(per=1000, win=2 * (1 + fee) + fee, title='tiny spends'))
        check('a mandate sized for two tiny spends is created', ok and 'ok = 4' in out, out)
        r1, r2, r3 = (spend('mdt_t_agent', 1, mid=4) for _ in range(3))
        check('two 1-unit spends fit; the third is refused because the fees used the window',
              'ok = record' in r1[1] and 'ok = record' in r2[1] and 'window cap' in r3[1], (r1, r2, r3))

        # deleting frees room, but only once a mandate is stopped
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'deleteMandate', '(4)')
        check("a live mandate can't be deleted", ok and 'revoke it first' in out, out)
        rep.call('mdt_t_owner', 'cafresohq_mandates', 'revokeMandate', '(4)')
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'deleteMandate', '(4)')
        check('a revoked mandate can be deleted', ok and 'ok = 4' in out, out)
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'myMandates', '()', query=True)
        check('...and it is gone from the owner\'s list', ok and 'id = 4' not in out, out[:300])

        ok, out = rep.call('mdt_t_stranger', 'cafresohq_mandates', 'addLedger', f'(principal "{stranger}", "X")')
        check("only a controller can add a ledger", not ok and 'controllers only' in out, out)
        ok, out = rep.call('mdt_t_stranger', 'cafresohq_mandates', 'getApiDoc', '()', query=True)
        check('the API doc explains it to an assistant', ok and 'retrySpend' in out and 'never instructions' in out, out[:200])
        # a ledger taken off the allowlist stops existing mandates (Builder's review, 5)
        ok, out = rep.call('mdt_t_owner', 'cafresohq_mandates', 'removeLedger', f'(principal "{ledger}")')
        check('a controller takes the ledger off the allowlist', ok, out)
        ok, out = spend('mdt_t_agent', 1000, mid=2, to=payee)
        check('...and existing mandates on it stop spending', ok and 'allowlist' in out, out)
    finally:
        rep.dfx('stop')
        for i in IDS:
            rep.dfx('identity', 'remove', i, '--drop-wallets')
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(('%d FAILED: %s' % (len(FAILS), FAILS)) if FAILS else 'mandates: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
