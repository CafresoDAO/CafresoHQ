#!/usr/bin/env python3
"""The approval inbox and agent keys run on a real replica
(docs/AGENT_ECONOMY_ON_ICP.md §3 and §4.3, Phase 1).

An agent gets its own principal; its owner registers it in cafresohq_state.
The key may post requests to its owner's inbox and read the ones it posted,
and nothing else. The owner decides a request, and deciding records the
answer only: the canister never acts on one.

Deploys the real src/cafresohq_state/main.mo to a throwaway local replica
(port 4978) and drives it with four dfx identities: an owner, the agent's
key, a second owner, and a stranger. Skipped without dfx, and under
GitHub Actions unless CAFRESOHQ_REPLICA=1.

    python3 scripts/test_the_inbox_and_agent_keys_on_a_real_replica.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 4978
DFX_VERSION = os.environ.get('CAFRESOHQ_STATE_DFX', '0.24.3')
FAILS = []
IDS = ['hq_t_owner', 'hq_t_agent', 'hq_t_owner2', 'hq_t_stranger']


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)[:300]) if not cond else ''))
    if not cond:
        FAILS.append(name)


class Replica:
    def __init__(self, tmp):
        self.tmp = tmp
        self.env = dict(os.environ, DFX_VERSION=DFX_VERSION, DFX_WARNING='-mainnet_plaintext_identity')

    def dfx(self, *args, identity=None, timeout=240):
        cmd = ['dfx', *args]
        if identity:
            cmd += ['--identity', identity]
        return subprocess.run(cmd, cwd=self.tmp, env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def call(self, who, method, arg='()', query=False):
        a = ['canister', 'call', 'cafresohq_state', method, arg, '--output', 'idl']
        if query:
            a.append('--query')
        r = self.dfx(*a, identity=who)
        return (r.returncode == 0, (r.stdout + r.stderr).strip())

    def principal(self, who):
        return self.dfx('identity', 'get-principal', identity=who).stdout.strip()


def main():
    print('the approval inbox and agent keys, on a real replica')
    if not shutil.which('dfx'):
        print('  skipped: dfx is not on PATH')
        return 0
    if os.environ.get('GITHUB_ACTIONS') and os.environ.get('CAFRESOHQ_REPLICA') != '1':
        print('  skipped under GITHUB_ACTIONS (set CAFRESOHQ_REPLICA=1 to run the replica here)')
        return 0
    tmp = tempfile.mkdtemp(prefix='hq-inbox-')
    (Path(tmp) / 'src').symlink_to(ROOT / 'src')
    (Path(tmp) / 'dfx.json').write_text(json.dumps({
        'version': 1,
        'canisters': {'cafresohq_state': {'type': 'motoko', 'main': 'src/cafresohq_state/main.mo'}},
        'defaults': {'build': {'args': '', 'packtool': ''}},
        'networks': {'local': {'bind': f'127.0.0.1:{PORT}', 'type': 'ephemeral'}},
    }))
    rep = Replica(tmp)
    try:
        for i in IDS:
            rep.dfx('identity', 'new', i, '--storage-mode', 'plaintext', '--force')
        # --background leaves the replica holding stdout/stderr: hand it a file, not a pipe,
        # or this call never returns (the hall suite does the same).
        with open(Path(tmp) / 'replica.log', 'w') as fh:
            r = subprocess.run(['dfx', 'start', '--clean', '--background'], cwd=tmp, env=rep.env,
                               stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, timeout=300)
        check('the replica starts', r.returncode == 0, (Path(tmp) / 'replica.log').read_text()[-400:])
        r = rep.dfx('deploy', 'cafresohq_state', identity='hq_t_owner', timeout=600)
        check('cafresohq_state deploys', r.returncode == 0, r.stderr[-400:])
        if FAILS:
            return 1
        owner, agent, owner2, stranger = (rep.principal(i) for i in IDS)

        # ── agent keys ───────────────────────────────────────────────────
        ok, out = rep.call('hq_t_owner', 'registerAgentKey', f'("builder", principal "{agent}")')
        check('an owner registers an agent key', ok, out)
        ok, out = rep.call('hq_t_owner', 'listAgentKeys', '()', query=True)
        check('...and sees it listed', ok and agent in out and '"builder"' in out, out)
        ok, out = rep.call('hq_t_stranger', 'agentKeyInfo', f'(principal "{agent}")', query=True)
        check('anyone can read which owner and agent a key belongs to', ok and owner in out and '"builder"' in out, out)
        ok, out = rep.call('hq_t_owner2', 'registerAgentKey', f'("thief", principal "{agent}")')
        check("another owner can't claim a key that is already registered", not ok and 'another agent' in out, out)
        ok, out = rep.call('hq_t_owner', 'registerAgentKey', f'("me", principal "{owner}")')
        check("an owner can't register their own principal as an agent", not ok, out)
        ok, out = rep.call('hq_t_agent', 'registerAgentKey', f'("sub", principal "{stranger}")')
        check("an agent key can't own agents of its own", not ok and 'cannot own agents' in out, out)
        ok, out = rep.call('hq_t_agent', 'listAgentWallets', '()', query=True)
        check("the agent key sees none of its owner's wallets (everything else is keyed by caller)", ok and 'vec {}' in out, out)

        # ── the inbox ────────────────────────────────────────────────────
        payload = json.dumps({'token': 'ICP', 'amount': '0.5', 'to': 'aaaaa-aa'}).replace('"', '\\"')
        ok, out = rep.call('hq_t_agent', 'postRequest', f'("builder", "send", "Send 0.5 ICP to a test canister", "{payload}", 0)')
        check('the agent key posts a request to its owner', ok and '1' in out, out)
        ok, out = rep.call('hq_t_agent', 'postRequest', '("someone-else", "send", "x", "", 0)')
        check('an agent key posts only for its own agent', not ok and 'its own agent' in out, out)
        ok, out = rep.call('hq_t_owner', 'postRequest', '("builder", "deploy", "Deploy cf_agents to a test canister", "{}", 0)')
        check('a headless office posts as the owner too', ok and '2' in out, out)
        ok, out = rep.call('hq_t_owner', 'postRequest', '("builder", "launch-missiles", "x", "", 0)')
        check('an unknown kind is refused', not ok and 'unknown kind' in out, out)
        ok, out = rep.call('hq_t_owner', 'postRequest', f'("builder", "other", "{"x" * 301}", "", 0)')
        check('an over-long summary is refused', not ok and 'too long' in out, out)
        ok, out = rep.call('hq_t_owner', 'postRequest', '("builder", "other", "x", "", 99999999)')
        check('a TTL over 30 days is refused', not ok and 'ttl' in out, out)
        ok, out = rep.call('hq_t_stranger', 'postRequest', '("builder", "send", "lands in my own inbox", "", 0)')
        check("a stranger's request lands in the stranger's own inbox", ok, out)

        ok, out = rep.call('hq_t_owner', 'listRequests', '(opt variant { pending })', query=True)
        check('the owner sees both pending requests, newest first',
              ok and out.count('id = ') == 2 and out.index('id = 2') < out.index('id = 1'), out)
        check("...and not the stranger's", 'lands in my own inbox' not in out, out)
        ok, out = rep.call('hq_t_stranger', 'listRequests', '(null)', query=True)
        check("the stranger can't see the owner's inbox", ok and 'Send 0.5 ICP' not in out, out)
        ok, out = rep.call('hq_t_agent', 'getRequest', '(1)', query=True)
        check('the agent reads the request it posted', ok and 'Send 0.5 ICP' in out, out)
        ok, out = rep.call('hq_t_agent', 'getRequest', '(2)', query=True)
        check("the agent can't read a request it didn't post", ok and '(null)' in out, out)

        ok, out = rep.call('hq_t_agent', 'decideRequest', '(1, true, "")')
        check("an agent key can't approve its own request", not ok and 'cannot decide' in out, out)
        # The stranger's own inbox holds only its request 1; the owner's request 2 isn't there.
        ok, out = rep.call('hq_t_stranger', 'decideRequest', '(2, true, "")')
        check("a stranger can't decide the owner's request (it isn't in their inbox)", ok and 'false' in out, out)
        ok, out = rep.call('hq_t_owner', 'getRequest', '(2)', query=True)
        check("...and the owner's request is still pending", ok and 'pending' in out, out)
        ok, out = rep.call('hq_t_owner', 'decideRequest', '(1, true, "signed in the shell")')
        check('the owner approves', ok and 'true' in out, out)
        ok, out = rep.call('hq_t_agent', 'getRequest', '(1)', query=True)
        check('...and the agent sees the answer and the note', ok and 'approved' in out and 'signed in the shell' in out, out)
        ok, out = rep.call('hq_t_owner', 'decideRequest', '(1, false, "")')
        check('a decided request stays decided', ok and 'false' in out, out)
        ok, out = rep.call('hq_t_agent', 'withdrawRequest', '(2)')
        check("the agent can't withdraw a request it didn't post", ok and 'false' in out, out)
        ok, out = rep.call('hq_t_owner', 'withdrawRequest', '(2)')
        check('the owner can withdraw any pending request', ok and 'true' in out, out)
        ok, out = rep.call('hq_t_owner', 'listRequests', '(opt variant { pending })', query=True)
        check('nothing is pending now', ok and 'id = ' not in out, out)

        # ── expiry is read, not ticked ──────────────────────────────────
        ok, out = rep.call('hq_t_owner', 'postRequest', '("builder", "vote", "Vote yes on 7", "", 1)')
        check('a one-second request is posted', ok, out)
        import time
        time.sleep(3)
        ok, out = rep.call('hq_t_owner', 'listRequests', '(opt variant { expired })', query=True)
        check('...and reads as expired once its time is up', ok and 'Vote yes on 7' in out, out)
        ok, out = rep.call('hq_t_owner', 'decideRequest', '(3, true, "")')
        check("an expired request can't be approved", ok and 'false' in out, out)

        # ── revoking ────────────────────────────────────────────────────
        ok, out = rep.call('hq_t_owner', 'revokeAgentKey', '("builder")')
        check('the owner revokes the key', ok and 'true' in out, out)
        ok, out = rep.call('hq_t_agent', 'postRequest', '("builder", "send", "after revoke", "", 0)')
        check("after revoking, the old key's posts land in its own inbox, not the owner's", ok, out)
        ok, out = rep.call('hq_t_owner', 'listRequests', '(null)', query=True)
        check("...so the owner's inbox never sees them", ok and 'after revoke' not in out, out)
        ok, out = rep.call('hq_t_owner2', 'registerAgentKey', f'("builder2", principal "{agent}")')
        check('a revoked key is free to be registered again', ok, out)
    finally:
        rep.dfx('stop')
        for i in IDS:
            rep.dfx('identity', 'remove', i, '--drop-wallets')
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print(('%d FAILED: %s' % (len(FAILS), FAILS)) if FAILS else 'inbox and agent keys: all checks passed')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
