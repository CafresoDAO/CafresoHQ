#!/usr/bin/env python3
"""The Hall <-> agent directory link, on a real replica.

An operator links a listing to its worker's entry in cf_agents (the obsidian-computer
agent directory) once the directory says that key is an Active agent. Every job that worker
delivers and the boss accepts is then written to the agent's public track record, confirmed,
with the boss as counterparty and the Hall as source; the agent's card says where to hire it.
The directory being missing, refusing or not a canister at all never touches a job's money.

Runs the real Hall and the mock ICRC ledger (built with the Hall's moc, from dfx 0.24.3) as custom
wasm next to the real cf_agents and mock membership (dfx 0.29.1), on one dfx 0.29.1 replica on
port 4983. cf_agents comes from an obsidian-computer checkout that has the recorder methods:
set OBSIDIAN_COMPUTER=/path/to/obsidian-computer (default: ../obsidian-computer). Skipped without
dfx or that checkout, and under GitHub Actions unless CAFRESOHQ_REPLICA=1.

    OBSIDIAN_COMPUTER=../obsidian-agent-directory python3 scripts/test_the_hall_writes_track_records_to_the_directory_on_a_real_replica.py
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
PORT = 4983
HALL_DFX = os.environ.get('CAFRESOHQ_STATE_DFX', '0.24.3')
DIR_DFX = os.environ.get('CF_AGENTS_DFX', '0.29.1')
OC = Path(os.environ.get('OBSIDIAN_COMPUTER', ROOT.parent / 'obsidian-computer')).resolve()
FAILS = []
IDS = ['hd_t_admin', 'hd_t_boss', 'hd_t_operator', 'hd_t_worker', 'hd_t_sponsor', 'hd_t_stranger', 'hd_t_worker2']
E8 = 100_000_000


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + (('  — ' + str(detail)[:400]) if not cond else ''))
    if not cond:
        FAILS.append(name)


def moc_of(version):
    env = dict(os.environ, DFX_VERSION=version)
    cache = subprocess.run(['dfx', 'cache', 'show'], env=env, capture_output=True, text=True, stdin=subprocess.DEVNULL).stdout.strip()
    return Path(cache)


class Replica:
    def __init__(self, tmp):
        self.tmp = tmp
        self.env = dict(os.environ, DFX_VERSION=DIR_DFX, DFX_WARNING='-mainnet_plaintext_identity')

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
    print('the hall writes track records to the agent directory, on a real replica')
    if not shutil.which('dfx'):
        print('  skipped: dfx is not on PATH')
        return 0
    if os.environ.get('GITHUB_ACTIONS') and os.environ.get('CAFRESOHQ_REPLICA') != '1':
        print('  skipped under GITHUB_ACTIONS (set CAFRESOHQ_REPLICA=1 to run the replica here)')
        return 0
    agents_src = OC / 'canisters' / 'agents' / 'main.mo'
    if not agents_src.exists() or 'recordJob' not in agents_src.read_text():
        print(f'  skipped: no cf_agents with recordJob at {agents_src} (set OBSIDIAN_COMPUTER)')
        return 0
    tmp = tempfile.mkdtemp(prefix='hq-halldir-')
    t = Path(tmp)
    (t / 'oc').symlink_to(OC / 'canisters')
    # The Hall and the mock ledger are classic actors on the Hall's own moc: build them as custom wasm.
    hc = moc_of(HALL_DFX)
    for name, src in (('hall', ROOT / 'src/cafresohq_market/main.mo'), ('ledger', ROOT / 'scripts/replica_harness/mock_ledger.mo')):
        r = subprocess.run([str(hc / 'moc'), '--package', 'base', str(hc / 'base'), str(src), '-o', str(t / f'{name}.wasm')],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        check(f'{name} builds with the hall moc', r.returncode == 0, r.stderr[-300:])
        r = subprocess.run([str(hc / 'moc'), '--idl', '--package', 'base', str(hc / 'base'), str(src), '-o', str(t / f'{name}.did')],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if FAILS:
        return 1
    (t / 'dfx.json').write_text(json.dumps({
        'version': 1,
        'canisters': {
            'mock_ledger': {'type': 'custom', 'wasm': 'ledger.wasm', 'candid': 'ledger.did'},
            'cafresohq_market': {'type': 'custom', 'wasm': 'hall.wasm', 'candid': 'hall.did'},
            'mock_membership': {'type': 'motoko', 'main': 'oc/test/mock_membership.mo'},
            'cf_agents': {'type': 'motoko', 'main': 'oc/agents/main.mo'},
        },
        'defaults': {'build': {'args': '', 'packtool': ''}},
        'networks': {'local': {'bind': f'127.0.0.1:{PORT}', 'type': 'ephemeral'}},
    }))
    rep = Replica(tmp)
    try:
        for i in IDS:
            subprocess.run(['dfx', 'identity', 'new', i, '--storage-mode', 'plaintext', '--force'], cwd=tmp, env=rep.env,
                           stdin=subprocess.DEVNULL, capture_output=True)
        with open(t / 'replica.log', 'w') as fh:
            r = subprocess.run(['dfx', 'start', '--clean', '--background'], cwd=tmp, env=rep.env,
                               stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, timeout=300)
        check('the replica starts', r.returncode == 0)
        for c in ('mock_ledger', 'cafresohq_market', 'mock_membership'):
            r = rep.dfx('deploy', c, '--no-wallet', identity='hd_t_admin', timeout=600)
            check(f'{c} deploys', r.returncode == 0, r.stderr[-300:])
        mem = rep.dfx('canister', 'id', 'mock_membership', identity='hd_t_admin').stdout.strip()
        r = rep.dfx('deploy', 'cf_agents', '--no-wallet', '--argument',
                    f'(record {{ membership = principal "{mem}"; vouchIntervalSeconds = opt (0 : nat) }})', identity='hd_t_admin', timeout=600)
        check('cf_agents deploys', r.returncode == 0, r.stderr[-300:])
        if FAILS:
            return 1
        cid = lambda c: rep.dfx('canister', 'id', c, identity='hd_t_admin').stdout.strip()
        led, hall, dirc = cid('mock_ledger'), cid('cafresohq_market'), cid('cf_agents')
        pr = {i: rep.dfx('identity', 'get-principal', identity=i).stdout.strip() for i in IDS}
        boss, operator, worker, sponsor, stranger, worker2 = (pr[i] for i in IDS[1:])
        acct = lambda p: f'record {{ owner = principal "{p}"; subaccount = null }}'

        def bal(p):
            return nat(rep.call('hd_t_admin', 'mock_ledger', 'icrc1_balance_of', f'({acct(p)})', query=True)[1])

        fee = nat(rep.call('hd_t_admin', 'mock_ledger', 'icrc1_fee', '()', query=True)[1])
        rep.call('hd_t_admin', 'cafresohq_market', 'market_admin_add_ledger', f'(principal "{led}")')
        rep.call('hd_t_admin', 'mock_ledger', 'mint', f'({acct(boss)}, {100 * E8} : nat)')
        ok, out = rep.call('hd_t_operator', 'cafresohq_market', 'putListing',
                           f'(record {{ id = null; name = "Builder"; role = "Coding Agent"; pitch = "Motoko"; brain = "Sonnet"; '
                           f'tags = vec {{ "code" }}; ledger = principal "{led}"; price = {E8} : nat; payoutSub = null; active = true }})')
        m = re.search(r'ok = ([\d_]+)', out)
        lid = int(m.group(1).replace('_', '')) if m else None
        check('the operator lists a coworker', lid is not None, out)
        rep.call('hd_t_operator', 'cafresohq_market', 'linkWorker', f'({lid} : nat, principal "{worker}")')

        n = [0]

        def job(jid_worker='hd_t_worker'):
            n[0] += 1
            ok, out = rep.call('hd_t_boss', 'cafresohq_market', 'postJob',
                               f'(record {{ title = "Review number {n[0]}"; brief = "Review a canister"; kind = "code"; tags = vec {{ "code" }}; '
                               f'listing = opt ({lid} : nat); ledger = principal "{led}"; price = {E8} : nat; deadlineSecs = 3600 : nat }})')
            m = re.search(r'ok = ([\d_]+)', out)
            jid = int(m.group(1).replace('_', ''))
            rep.call('hd_t_boss', 'mock_ledger', 'icrc2_approve',
                     f'(record {{ spender = {acct(hall)}; amount = {E8 + 2 * fee} : nat; from_subaccount = null; expected_allowance = null; '
                     'expires_at = null; fee = null; memo = null; created_at_time = null })')
            rep.call('hd_t_boss', 'cafresohq_market', 'fundJob', f'({jid} : nat)')
            rep.call(jid_worker, 'cafresohq_market', 'claimJob', f'({jid} : nat)')
            body = f'review {n[0]}'
            sha = hashlib.sha256(body.encode()).hexdigest()
            rep.call(jid_worker, 'cafresohq_market', 'deliverJob', f'({jid} : nat, "done", "{body}", "{sha}")')
            before = bal(operator)  # earnings go to the listing operator's account
            ok, out = rep.call('hd_t_boss', 'cafresohq_market', 'acceptDelivery', f'({jid} : nat, 5 : nat)')
            return ok and 'err' not in out, bal(operator) - before, sha, out

        def records(p):
            return rep.call('hd_t_admin', 'cf_agents', 'trackRecord', f'(principal "{p}", null, 50 : nat)', query=True)[1]

        def settled(p, want=None):
            # The hall sends the record after the payout without waiting on it: give it a moment.
            out = records(p)
            for _ in range(12):
                if want is not None and want in out:
                    break
                time.sleep(1)
                out = records(p)
            return out

        def hire(p):
            return rep.call('hd_t_admin', 'cf_agents', 'hireInfo', f'(principal "{p}")', query=True)[1]

        # ── no directory set ───────────────────────────────────────────
        ok, out = rep.call('hd_t_operator', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        check('without a directory, linkDirectory says so', 'no agent directory' in out, out)
        ok, out = rep.call('hd_t_stranger', 'cafresohq_market', 'market_admin_set_directory', f'(opt principal "{dirc}")')
        check('a stranger cannot set the directory', not ok, out)
        ok, out = rep.call('hd_t_admin', 'cafresohq_market', 'market_admin_set_directory', f'(opt principal "{dirc}")')
        check('the plan admin sets the directory', ok, out)

        # ── the worker is not an agent yet ─────────────────────────────
        ok, out = rep.call('hd_t_worker', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        check('an unregistered worker key cannot be linked', "isn't an Active agent" in out, out)
        rep.call('hd_t_admin', 'mock_membership', 'set', f'(principal "{sponsor}", opt (9_999_999_999_000_000_000 : int))')
        ok, out = rep.call('hd_t_sponsor', 'cf_agents', 'vouch', f'(principal "{worker}")')
        check('a Developer vouches for the worker', ok and 'err' not in out, out)
        ok, out = rep.call('hd_t_worker', 'cf_agents', 'register',
                           '(record { name = "Builder"; description = "Reviews Motoko canisters."; capabilities = vec { "code" }; '
                           'freeTags = vec {}; reach = variant { chat }; provider = opt "Claude, Sonnet 5.5" })')
        check('the worker registers in the directory', ok and 'err' not in out, out)

        ok, out = rep.call('hd_t_stranger', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        check('a stranger cannot link the listing', "only the listing's worker key" in out, out)
        ok, out = rep.call('hd_t_operator', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        check("even the operator cannot link the agent's card for it", "only the listing's worker key" in out, out)
        ok, out = rep.call('hd_t_worker', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        check('the agent links its own listing', ok and 'ok' in out, out)
        ok, out = rep.call('hd_t_admin', 'cafresohq_market', 'listingAgentOf', f'({lid} : nat)', query=True)
        check('the hall knows which agent the listing is', worker in out, out)
        check('the Hall is not a recorder yet, so the card has no hire link', '(null)' in hire(worker), hire(worker))

        # ── not a recorder: the job still pays, nothing is written ────
        ok, got, sha, out = job()
        check('a job pays the operator while the directory refuses the hall', ok and got == E8, (got, out))
        check('and nothing lands on the track record', 'contentSha256' not in settled(worker), records(worker))

        # ── a recorder: accepted jobs are written, confirmed ──────────
        ok, out = rep.call('hd_t_admin', 'cf_agents', 'addRecorder', f'(principal "{hall}")')
        check('the directory controller makes the hall a recorder', ok and 'err' not in out, out)
        rep.call('hd_t_worker', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        h = hire(worker)
        check('linking again publishes the hire link', hall in h and re.search(r'listing = %d' % lid, h.replace('_', '')), h)
        ok, got, sha, out = job()
        recs = settled(worker, sha)
        check('an accepted job pays the operator in full', ok and got == E8, (got, out))
        check('it is on the track record with its delivery hash', sha in recs, recs)
        check('confirmed, with the boss as counterparty and the hall as source',
              'confirmedAt = opt' in recs and boss in recs and f'source = opt principal "{hall}"' in recs, recs)
        check('the value is what the worker earned, in the ledger symbol', '"MOCK"' in recs and re.search(r'amount = 100_000_000', recs), recs)
        summ = rep.call('hd_t_admin', 'cf_agents', 'trackSummary', f'(principal "{worker}")', query=True)[1]
        check('the summary counts one confirmed job', re.search(r'confirmed = 1 ', summ) and re.search(r'total = 1 ', summ), summ)
        ok, out = rep.call('hd_t_admin', 'cf_agents', 'http_request',
                           f'(record {{ method = "GET"; url = "/agent/{worker}.json"; headers = vec {{}}; body = blob "" }})', query=True)
        check('the public agent card says where to hire it', 'hire' in out and hall in out, out[-300:])

        ok, out = rep.call('hd_t_boss', 'cafresohq_market', 'postJob',
                           f'(record {{ title = "Two\\nlines"; brief = "b"; kind = "code"; tags = vec {{}}; listing = opt ({lid} : nat); '
                           f'ledger = principal "{led}"; price = {E8} : nat; deadlineSecs = 3600 : nat }})')
        if 'ok =' in out:
            jid = int(re.search(r'ok = ([\d_]+)', out).group(1).replace('_', ''))
            rep.call('hd_t_boss', 'mock_ledger', 'icrc2_approve',
                     f'(record {{ spender = {acct(hall)}; amount = {E8 + 2 * fee} : nat; from_subaccount = null; expected_allowance = null; '
                     'expires_at = null; fee = null; memo = null; created_at_time = null })')
            rep.call('hd_t_boss', 'cafresohq_market', 'fundJob', f'({jid} : nat)')
            rep.call('hd_t_worker', 'cafresohq_market', 'claimJob', f'({jid} : nat)')
            sha2 = hashlib.sha256(b'two lines').hexdigest()
            rep.call('hd_t_worker', 'cafresohq_market', 'deliverJob', f'({jid} : nat, "done", "two lines", "{sha2}")')
            rep.call('hd_t_boss', 'cafresohq_market', 'acceptDelivery', f'({jid} : nat, 5 : nat)')
            check('a title the directory would refuse is recorded under a plain one',
                  sha2 in settled(worker, sha2) and 'a job from the Hiring Hall' in records(worker), records(worker)[-400:])
        else:
            check('the hall takes a title with a line break', False, out)

        # ── a directory that is not a directory never blocks money ────
        rep.call('hd_t_admin', 'cafresohq_market', 'market_admin_set_directory', f'(opt principal "{led}")')
        ok, got, sha, out = job()
        check('a broken directory does not stop the payout', ok and got == E8, (got, out))
        ok, out = rep.call('hd_t_worker', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        check("linking against a broken directory says it didn't answer", "didn't answer" in out, out)
        rep.call('hd_t_admin', 'cafresohq_market', 'market_admin_set_directory', f'(opt principal "{dirc}")')
        check('that job is not on the record', sha not in settled(worker))
        ok, out = rep.call('hd_t_admin', 'cafresohq_market', 'listingAgentOf', f'({lid} : nat)', query=True)
        check('a changed directory starts with no links', '(null)' in out, out)
        ok, out = rep.call('hd_t_worker', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        check('the agent links again', ok and 'ok' in out, out)

        # ── a boss who is the operator earns the agent no record ───────
        rep.call('hd_t_admin', 'mock_ledger', 'mint', f'({acct(operator)}, {10 * E8} : nat)')
        ok, out = rep.call('hd_t_operator', 'cafresohq_market', 'postJob',
                           f'(record {{ title = "Self dealing"; brief = "b"; kind = "code"; tags = vec {{}}; listing = opt ({lid} : nat); '
                           f'ledger = principal "{led}"; price = {E8} : nat; deadlineSecs = 3600 : nat }})')
        m = re.search(r'ok = ([\d_]+)', out)
        if m:
            jid = int(m.group(1).replace('_', ''))
            rep.call('hd_t_operator', 'mock_ledger', 'icrc2_approve',
                     f'(record {{ spender = {acct(hall)}; amount = {E8 + 2 * fee} : nat; from_subaccount = null; expected_allowance = null; '
                     'expires_at = null; fee = null; memo = null; created_at_time = null })')
            rep.call('hd_t_operator', 'cafresohq_market', 'fundJob', f'({jid} : nat)')
            rep.call('hd_t_worker', 'cafresohq_market', 'claimJob', f'({jid} : nat)')
            sha3 = hashlib.sha256(b'self').hexdigest()
            rep.call('hd_t_worker', 'cafresohq_market', 'deliverJob', f'({jid} : nat, "done", "self", "{sha3}")')
            ok, out = rep.call('hd_t_operator', 'cafresohq_market', 'acceptDelivery', f'({jid} : nat, 5 : nat)')
            check('the operator can still hire its own coworker', ok and 'ok' in out, out)
            check('but that job is not written to the track record', sha3 not in settled(worker), records(worker)[-300:])
        else:
            check('the operator posts a job on its own listing', False, out)

        # ── a different worker key drops the link ──────────────────────
        ok, out = rep.call('hd_t_operator', 'cafresohq_market', 'linkWorker', f'({lid} : nat, principal "{worker2}")')
        check('the operator swaps the worker key', ok, out)
        ok, out = rep.call('hd_t_admin', 'cafresohq_market', 'listingAgentOf', f'({lid} : nat)', query=True)
        check('the directory link is gone with the old key', '(null)' in out, out)
        check("and the old agent's card no longer points here", '(null)' in hire(worker), hire(worker))
        before = records(worker)
        ok, got, sha, out = job('hd_t_worker2')
        check("the new key's job pays", ok and got == E8, (got, out))
        check("and nothing is written to the old agent's record", settled(worker) == before)

        # ── unlinkDirectory ──────────────────────────────────────────────
        rep.call('hd_t_operator', 'cafresohq_market', 'linkWorker', f'({lid} : nat, principal "{worker}")')
        rep.call('hd_t_worker', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        check('relinked', hall in hire(worker), hire(worker))
        ok, out = rep.call('hd_t_stranger', 'cafresohq_market', 'unlinkDirectory', f'({lid} : nat)')
        check('a stranger cannot unlink', 'not your listing' in out, out)
        ok, out = rep.call('hd_t_worker', 'cafresohq_market', 'unlinkDirectory', f'({lid} : nat)')
        check('the agent can unlink itself', ok and 'ok' in out and '(null)' in hire(worker), (out, hire(worker)))
        rep.call('hd_t_worker', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        ok, out = rep.call('hd_t_operator', 'cafresohq_market', 'unlinkDirectory', f'({lid} : nat)')
        check('the operator unlinks', ok and 'ok' in out, out)
        check('the card no longer points here', '(null)' in hire(worker), hire(worker))
        before = records(worker)
        ok, got, sha, out = job()
        check('an unlinked job pays and writes nothing', ok and got == E8 and settled(worker) == before, (got, out))

        # ── unlinkWorker clears it too ───────────────────────────────────
        rep.call('hd_t_worker', 'cafresohq_market', 'linkDirectory', f'({lid} : nat)')
        rep.call('hd_t_operator', 'cafresohq_market', 'unlinkWorker', f'({lid} : nat)')
        ok, out = rep.call('hd_t_admin', 'cafresohq_market', 'listingAgentOf', f'({lid} : nat)', query=True)
        check('unlinkWorker drops the directory link', '(null)' in out and '(null)' in hire(worker), (out, hire(worker)))
    finally:
        subprocess.run(['dfx', 'stop'], cwd=tmp, env=rep.env, stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
        for i in IDS:
            subprocess.run(['dfx', 'identity', 'remove', i], cwd=tmp, env=rep.env, stdin=subprocess.DEVNULL, capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)
    print(f'{"FAILED: " + str(len(FAILS)) if FAILS else "all passed"}')
    return 1 if FAILS else 0


if __name__ == '__main__':
    sys.exit(main())
