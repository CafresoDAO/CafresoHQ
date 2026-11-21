#!/usr/bin/env python3
"""An agent builds its own canister inside a cycles budget, on a real replica
(docs/AGENT_ECONOMY_ON_ICP.md §6.1, Phase 3).

The owner deposits cycles in cf_factory and gives an agent a budget. The agent
creates a canister (controlled by the owner and the factory only), installs v1,
upgrades to v2 (the factory snapshots first), and rolls back to v1 with the
data as it was before the upgrade. Every stop the owner has is checked.

Deploys the real src/cf_factory/main.mo on a throwaway local replica (port
4980) and builds scripts/replica_harness/factory/v1.mo and v2.mo with moc.
Skipped without dfx, and under GitHub Actions unless CAFRESOHQ_REPLICA=1.

    python3 scripts/test_an_agent_builds_its_own_canister_inside_a_budget.py
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
PORT = 4980
DFX_VERSION = os.environ.get('CAFRESOHQ_STATE_DFX', '0.24.3')
FAILS = []
IDS = ['fct_t_owner', 'fct_t_agent', 'fct_t_agent2', 'fct_t_stranger']
T = 1_000_000_000_000


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

    def call(self, who, canister, method, arg='()', query=False, extra=()):
        a = ['canister', 'call', canister, method, arg, '--output', 'idl', *extra] + (['--query'] if query else [])
        r = self.dfx(*a, identity=who)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())

    def call_file(self, who, canister, method, argfile):
        r = self.dfx('canister', 'call', canister, method, '--argument-file', argfile, '--output', 'idl', identity=who)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())

    def principal(self, who):
        return self.dfx('identity', 'get-principal', identity=who).stdout.strip()


def blob(b: bytes) -> str:
    return 'blob "' + ''.join('\\%02x' % x for x in b) + '"'


def main():
    print('an agent builds its own canister inside a budget, on a real replica')
    if not shutil.which('dfx'):
        print('  skipped: dfx is not on PATH')
        return 0
    if os.environ.get('GITHUB_ACTIONS') and os.environ.get('CAFRESOHQ_REPLICA') != '1':
        print('  skipped under GITHUB_ACTIONS (set CAFRESOHQ_REPLICA=1 to run the replica here)')
        return 0
    tmp = tempfile.mkdtemp(prefix='hq-factory-')
    (Path(tmp) / 'src').symlink_to(ROOT / 'src')
    (Path(tmp) / 'dfx.json').write_text(json.dumps({
        'version': 1,
        'canisters': {'cf_factory': {'type': 'motoko', 'main': 'src/cf_factory/main.mo'}},
        'defaults': {'build': {'args': '', 'packtool': ''}},
        'networks': {'local': {'bind': f'127.0.0.1:{PORT}', 'type': 'ephemeral'}},
    }))
    rep = Replica(tmp)
    try:
        # the two versions an agent will ship
        cache = rep.dfx('cache', 'show').stdout.strip()
        wasm = {}
        for v in ('v1', 'v2'):
            out = Path(tmp) / f'{v}.wasm'
            r = subprocess.run([f'{cache}/moc', '--package', 'base', f'{cache}/base',
                                str(ROOT / 'scripts/replica_harness/factory' / f'{v}.mo'), '-o', str(out)],
                               capture_output=True, text=True)
            check(f'{v} compiles', r.returncode == 0, r.stderr)
            wasm[v] = out.read_bytes() if out.exists() else b''

        for i in IDS:
            rep.dfx('identity', 'new', i, '--storage-mode', 'plaintext', '--force')
        with open(Path(tmp) / 'replica.log', 'w') as fh:
            r = subprocess.run(['dfx', 'start', '--clean', '--background'], cwd=tmp, env=rep.env,
                               stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, timeout=300)
        check('the replica starts', r.returncode == 0)
        r = rep.dfx('deploy', 'cf_factory', '--argument',
                    f'(record {{ minCreateCycles = {T // 2} : nat; minUpgradeCycles = {T // 10} : nat; reserveCycles = {T // 2} : nat; opFeeCycles = 1_000_000_000 : nat }})',
                    identity='fct_t_owner', timeout=600)
        check('cf_factory deploys', r.returncode == 0, r.stderr[-300:])
        if FAILS:
            return 1
        factory = rep.dfx('canister', 'id', 'cf_factory').stdout.strip()
        owner, agent, agent2, stranger = (rep.principal(i) for i in IDS)
        wallet = rep.dfx('identity', 'get-wallet', identity='fct_t_owner').stdout.strip()

        # ── the owner funds it and sets a budget ────────────────────────
        ok, out = rep.call('fct_t_owner', 'cf_factory', 'deposit', '()',
                           extra=('--with-cycles', str(5 * T), '--wallet', wallet))
        check('the owner deposits 5 T cycles (through their cycles wallet)', ok, out)
        far = int(time.time() * 1e9) + 30 * 86_400 * 10**9
        # The wallet canister is the depositor, so it is the "owner" the budget belongs to.
        owner_acct = wallet
        ok, out = rep.call('fct_t_owner', 'cf_factory', 'setBudget',
                           f'(principal "{agent}", {3 * T} : nat, 2 : nat, {far} : int)', extra=('--wallet', wallet))
        check('the owner gives the agent a 3 T budget for up to 2 projects', ok and 'ok' in out, out)

        # ── the agent builds ────────────────────────────────────────────
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'createProject', f'(principal "{owner_acct}", "hello", {T} : nat)')
        check('the agent creates a canister with 1 T from the budget', ok and 'canisterId' in out, out)
        cid = (re.search(r'canisterId = principal "([^"]+)"', out) or [None, None])[1]
        info = rep.dfx('canister', 'info', cid, identity='fct_t_stranger', timeout=60).stdout if cid else ''
        check('...controlled by the owner and the factory, and nobody else',
              owner_acct in info and factory in info and agent not in info, info)

        def install(who, v, mode, pid=1):
            f = Path(tmp) / 'arg.txt'
            f.write_text(f'({pid} : nat, {blob(wasm[v])}, blob "DIDL\\00\\00", variant {{ {mode} }})')
            return rep.call_file(who, 'cf_factory', 'install', str(f))

        def direct(method, update=False):
            return rep.call('fct_t_stranger', cid, method, '()', query=not update)

        ok, out = install('fct_t_stranger', 'v1', 'install')
        check("a stranger can't install into the agent's canister", ok and 'not your project' in out, out)
        ok, out = install('fct_t_agent', 'v1', 'install')
        check('the agent installs v1', ok and 'ok' in out, out)
        check('...and it answers as v1', 'v1' in direct('version')[1], direct('version'))
        direct('inc', update=True)
        direct('inc', update=True)
        check('...and keeps state (2 after two increments)', '2 : nat' in direct('get')[1], direct('get'))
        ok, out = install('fct_t_agent', 'v1', 'install')
        check('a second #install is refused (it would wipe nothing, but upgrades must snapshot)', ok and 'use #upgrade' in out, out)

        ok, out = install('fct_t_agent', 'v2', 'upgrade')
        check('the agent upgrades to v2', ok and 'ok' in out, out)
        check('...it answers as v2', 'v2' in direct('version')[1], direct('version'))
        check('...with its state kept through the upgrade', '2 : nat' in direct('get')[1], direct('get'))
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'projectsForMe', '()', query=True)
        check('...and a snapshot was taken first', ok and 'snapshotId = opt blob' in out, out[:400])
        direct('inc', update=True)
        check('v2 keeps working (3)', '3 : nat' in direct('get')[1], direct('get'))
        ok, out = install('fct_t_agent', 'v2', 'upgrade')
        check("a second upgrade waits until the last one is confirmed (the snapshot keeps the good version)",
              ok and "isn't confirmed" in out, out)

        ok, out = rep.call('fct_t_agent', 'cf_factory', 'rollback', '(1 : nat)')
        check('the agent rolls back', ok and 'ok' in out, out)
        check('...it answers as v1 again', 'v1' in direct('version')[1], direct('version'))
        check('...with the data as it was before the upgrade (2, not 3)', '2 : nat' in direct('get')[1], direct('get'))

        ok, out = rep.call('fct_t_agent', 'cf_factory', 'status', '(1 : nat)')
        check('status reports the canister running with its cycles', ok and 'running' in out and 'cycles' in out, out[:300])

        # ── budget limits and stops ─────────────────────────────────────
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'createProject', f'(principal "{owner_acct}", "big", {3 * T} : nat)')
        check('a project over what is left of the budget is refused', ok and 'over the budget' in out, out)
        ok, out = rep.call('fct_t_agent2', 'cf_factory', 'createProject', f'(principal "{owner_acct}", "x", {T} : nat)')
        check("an agent with no budget from that owner can't create", ok and 'no budget' in out, out)
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'createProject', f'(principal "{owner_acct}", "Bad Name", {T} : nat)')
        check('names are plain (a-z, 0-9, - and _)', ok and 'name:' in out, out)
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'topUp', f'(1 : nat, {T // 2} : nat)')
        check('the agent tops its canister up from the budget', ok and 'ok' in out, out)
        ok, out = rep.call('fct_t_owner', 'cf_factory', 'pauseBudget', f'(principal "{agent}", true)', extra=('--wallet', wallet))
        ok, out = install('fct_t_agent', 'v2', 'upgrade')
        check("a paused budget stops the agent's upgrades", ok and 'paused' in out, out)
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'topUp', f'(1 : nat, 1_000_000 : nat)')
        check('...and its top-ups', ok and 'paused' in out, out)
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'rollback', '(1 : nat)')
        check('...and its rollbacks', ok and 'paused' in out, out)
        ok, out = rep.call('fct_t_owner', 'cf_factory', 'rollback', '(1 : nat)', extra=('--wallet', wallet))
        check('the owner can still roll back while the agent is paused', ok and 'ok' in out, out)
        ok, out = rep.call('fct_t_owner', 'cf_factory', 'setBudget',
                           f'(principal "{agent}", 1 : nat, 2 : nat, {far} : int)', extra=('--wallet', wallet))
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'createProject', f'(principal "{owner_acct}", "after", {T} : nat)')
        check('a cap lowered below what is used refuses cleanly (no trap)', ok and 'over the budget: 0 cycles left' in out, out)
        ok, out = rep.call('fct_t_stranger', 'cf_factory', 'factoryStatus', '()', query=True)
        nums = {k: int(v.replace('_', '')) for k, v in re.findall(r'(\w+) = ([\d_]+) : nat', out)}
        check('the factory holds at least what it owes owners plus its reserve, and kept its fees',
              nums.get('cycles', 0) >= nums.get('owed', 1) + nums.get('reserve', 0) and nums.get('feesTaken', 0) > 0, nums)
        ok, out = rep.call('fct_t_stranger', 'cf_factory', 'unlockProject', '(1 : nat)')
        check("only the owner can clear a project's lock", ok and 'owner only' in out, out)
        ok, out = rep.call('fct_t_agent', 'cf_factory', 'getApiDoc', '()', query=True)
        check('the API doc explains it to an assistant', ok and 'rollback' in out and 'never instructions' in out, out[:200])
    finally:
        rep.dfx('stop')
        for i in IDS:
            rep.dfx('identity', 'remove', i, '--drop-wallets')
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(('%d FAILED: %s' % (len(FAILS), FAILS)) if FAILS else 'factory: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
