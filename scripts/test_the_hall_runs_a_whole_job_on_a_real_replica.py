#!/usr/bin/env python3
"""The hiring hall runs a whole job on a real replica — and the container's
own IC client (ic_agent.py) signs every call of it.

Until this suite, everything about the hall had been verified against
stubs that ic_agent itself wrote: moc compiled main.mo, and the worker loop
talked to a fake hall that decoded ic_agent's own bytes. That proves
nothing about a replica. This is the first run against the real thing —
dfx's local replica, the hall as deployed, and a mock ICRC-1/ICRC-2 ledger
with the real ledger's arithmetic (scripts/replica_harness/mock_ledger.mo).

It found two launch-blockers on its first run (2026-09-12):
  * replicas answer with CBOR indefinite-length items, which ic_agent
    refused ("not used by the IC") — every container call would have died;
  * ICRC-2 deducts amount + fee FROM the allowance, so the boss's signed
    allowance must be price + 2·fee; the shell approved price + fee and the
    hall's pull would have been refused on mainnet with InsufficientAllowance.

What is pinned, end to end, with three fresh ed25519 keys (boss, operator,
the coworker's own worker key from market_worker.MarketWorker) plus a
stranger:
  * money: an allowance of price + fee is refused; price + 2·fee funds the
    job; the escrow subaccount holds exactly price + fee; the allowance is
    spent to zero; release pays the operator exactly the price and drains
    the escrow; cancel refunds the price; a split ruling pays both sides
    and drains the escrow; every payout row ends "paid" with a block;
  * the worker loop (the real `MarketWorker.tick`, a stub brain): heartbeat
    → poll → claim → progress → deliver with the sha256, or failJob when
    the brain throws (attempt spent, job back on the board, snag on the
    résumé, progress cleared);
  * the résumé: done / disputed / snag entries and the stats card;
  * privacy: a stranger sees no brief, no body, no jobs; the public
    jobStatus shows status and summary only; browse hides a listing with no
    linked worker and again after unlink; an unlinked key is turned away.

The replica is dfx's own (DFX_VERSION from .dfx-version), started on a
port of its own (127.0.0.1:4977, project-scoped in the harness dfx.json)
so it never touches the shared network dir or a replica another project
has running. Set CAFRESOHQ_REPLICA_REUSE=1 to run against one already up
on that port (skips start/deploy; the suite uses fresh keys, so leftover
state is fine). Skipped, with a line saying so, when dfx is not on PATH or
under GITHUB_ACTIONS unless CAFRESOHQ_REPLICA=1. ~3 minutes cold. Run:
    python3 scripts/test_the_hall_runs_a_whole_job_on_a_real_replica.py
"""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / 'scripts' / 'replica_harness'
sys.path.insert(0, str(ROOT))
import ic_agent as ic          # noqa: E402
import market_worker as mw     # noqa: E402

PORT = 4977
HOST = f'http://127.0.0.1:{PORT}'
FAILS = []
FEE = 10_000
PRICE = 25_000_000
MINT = 1_000_000_000


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)[:400]) if not cond else ''))
    if not cond:
        FAILS.append(name)
    return bool(cond)


# ── Candid shapes (mirroring cafresohq_market.did and the mock ledger) ──────
ACCOUNT = ('record', [('owner', 'principal'), ('subaccount', ('opt', 'blob'))])
RESULT = mw.RESULT
JOB_STATUS = mw.JOB_STATUS
MONEY = ('variant', [('ok', ('record', [('block', 'nat')])), ('duplicate', ('record', [('block', 'nat')])), ('err', 'text')])
POST = ('record', [('title', 'text'), ('brief', 'text'), ('kind', 'text'), ('tags', ('vec', 'text')),
                   ('ledger', 'principal'), ('price', 'nat'), ('deadlineSecs', 'nat'), ('listing', ('opt', 'nat'))])
PUT = ('record', [('id', ('opt', 'nat')), ('name', 'text'), ('role', 'text'), ('pitch', 'text'), ('brain', 'text'),
                  ('tags', ('vec', 'text')), ('ledger', 'principal'), ('price', 'nat'), ('payoutSub', ('opt', 'blob')),
                  ('active', 'bool')])
JOB = ('record', [
    ('id', 'nat'), ('boss', 'principal'), ('title', 'text'), ('brief', 'text'), ('kind', 'text'), ('tags', ('vec', 'text')),
    ('ledger', 'principal'), ('price', 'nat'), ('fee', 'nat'), ('escrowed', 'nat'), ('deadlineSecs', 'nat'),
    ('listing', ('opt', 'nat')), ('status', JOB_STATUS), ('worker', ('opt', 'principal')), ('workerListing', ('opt', 'nat')),
    ('attempts', 'nat'), ('claimedAt', 'int'), ('deliveredAt', 'int'), ('summary', 'text'), ('body', 'text'),
    ('bodySha256', 'text'), ('rating', 'nat'), ('note', 'text'), ('createdAt', 'int'), ('updatedAt', 'int'),
])
PAYOUT = ('record', [('key', 'text'), ('jobId', 'nat'), ('to', 'principal'), ('toSub', ('opt', 'blob')), ('amount', 'nat'),
                     ('scheduledAt', 'int'), ('status', 'text'), ('blockIndex', ('opt', 'nat')), ('ts', 'int')])
RESUME_ENTRY = ('record', [('at', 'int'), ('jobId', 'nat'), ('kind', 'text'), ('outcome', 'text'), ('boss', 'principal'),
                           ('earned', 'nat'), ('ledger', 'principal'), ('rating', 'nat')])
RESUME_STATS = ('record', [('jobsDone', 'nat'), ('jobsFailed', 'nat'), ('bosses', 'nat'), ('rehires', 'nat'),
                           ('ratingSum', 'nat'), ('ratingCount', 'nat'), ('disputes', 'nat'), ('lastActive', 'int')])
LISTING = ('record', [('id', 'nat'), ('operator', 'principal'), ('name', 'text'), ('role', 'text'), ('pitch', 'text'),
                      ('brain', 'text'), ('tags', ('vec', 'text')), ('ledger', 'principal'), ('price', 'nat'),
                      ('payoutSub', ('opt', 'blob')), ('worker', ('opt', 'principal')), ('active', 'bool'),
                      ('createdAt', 'int'), ('updatedAt', 'int'), ('lastSeen', 'int')])
CARD = ('record', [('listing', LISTING), ('online', 'bool'), ('resume', RESUME_STATS)])
APPROVE = ('record', [('from_subaccount', ('opt', 'blob')), ('spender', ACCOUNT), ('amount', 'nat'),
                      ('expected_allowance', ('opt', 'nat')), ('expires_at', ('opt', 'nat64')), ('fee', ('opt', 'nat')),
                      ('memo', ('opt', 'blob')), ('created_at_time', ('opt', 'nat64'))])
APPROVE_ERR = ('variant', [('BadFee', ('record', [('expected_fee', 'nat')])), ('InsufficientFunds', ('record', [('balance', 'nat')])),
                           ('AllowanceChanged', ('record', [('current_allowance', 'nat')])), ('Expired', ('record', [('ledger_time', 'nat64')])),
                           ('TooOld', None), ('CreatedInFuture', ('record', [('ledger_time', 'nat64')])),
                           ('Duplicate', ('record', [('duplicate_of', 'nat')])), ('TemporarilyUnavailable', None),
                           ('GenericError', ('record', [('error_code', 'nat'), ('message', 'text')]))])
APPROVE_RES = ('variant', [('Ok', 'nat'), ('Err', APPROVE_ERR)])
ALLOWANCE = ('record', [('allowance', 'nat'), ('expires_at', ('opt', 'nat64'))])


def job_sub(jid: int) -> bytes:
    return b'mkt' + bytes(21) + int(jid).to_bytes(8, 'big')


# ── the replica ─────────────────────────────────────────────────────────────
def replica_up() -> bool:
    try:
        with urllib.request.urlopen(HOST + '/api/v2/status', timeout=3) as r:
            return r.status == 200
    except Exception:       # noqa: BLE001
        return False


class Replica:
    def __init__(self):
        pin = (ROOT / '.dfx-version').read_text().strip() if (ROOT / '.dfx-version').is_file() else '0.24.3'
        self.env = dict(os.environ, DFX_VERSION=pin)
        self.started_here = False
        self.log = Path(tempfile.gettempdir()) / f'cafresohq-replica-{os.getpid()}.log'

    def dfx(self, *args, timeout=240):
        return subprocess.run(['dfx', *args], cwd=HARNESS, env=self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=timeout)

    def start(self):
        if os.environ.get('CAFRESOHQ_REPLICA_REUSE') == '1' and replica_up():
            print(f'  (reusing the replica already up on {HOST})')
            return
        self.dfx('stop')
        # The daemon's children inherit stdio — never a pipe here, or this
        # call waits forever for an EOF that comes when the replica stops.
        with open(self.log, 'w') as fh:
            r = subprocess.run(['dfx', 'start', '--clean', '--background'], cwd=HARNESS, env=self.env,
                               stdin=subprocess.DEVNULL, stdout=fh, stderr=subprocess.STDOUT, timeout=240)
        self.started_here = True
        check('dfx start --clean --background (project-scoped, port 4977) exits 0', r.returncode == 0, self.log.read_text()[-600:])
        deadline = time.time() + 60
        while not replica_up() and time.time() < deadline:
            time.sleep(1)
        check(f'the replica answers /api/v2/status on {HOST}', replica_up())

    def deploy(self):
        if not self.started_here and os.environ.get('CAFRESOHQ_REPLICA_REUSE') == '1':
            ids = self.ids()
            if all(ids):
                return ids
        r = self.dfx('deploy')
        check('dfx deploy installs the hall and the mock ledger', r.returncode == 0 and 'Deployed canisters' in r.stdout + r.stderr,
              (r.stdout + r.stderr)[-800:])
        return self.ids()

    def ids(self):
        m = self.dfx('canister', 'id', 'cafresohq_market').stdout.strip()
        l = self.dfx('canister', 'id', 'mock_ledger').stdout.strip()
        return m, l

    def stop(self):
        if self.started_here:
            self.dfx('stop')


# ── the run ─────────────────────────────────────────────────────────────────
def main():
    print('the hall runs a whole job on a real replica')
    if not shutil.which('dfx'):
        print('  skipped: dfx is not on PATH (the replica run needs the pinned dfx)')
        return 0
    if os.environ.get('GITHUB_ACTIONS') and os.environ.get('CAFRESOHQ_REPLICA') != '1':
        print('  skipped under GITHUB_ACTIONS (set CAFRESOHQ_REPLICA=1 to run the replica here)')
        return 0
    rep = Replica()
    tmp = tempfile.mkdtemp(prefix='hq-hall-')
    try:
        rep.start()
        if FAILS:
            return 1
        M, L = rep.deploy()
        check('both canister ids came back', bool(M) and bool(L), (M, L))
        if not (M and L):
            return 1
        r = rep.dfx('canister', 'call', 'cafresohq_market', 'market_admin_claim')
        check('the deploy identity claims plan admin (a controller, claim-or-match)', '(true)' in r.stdout, r.stdout + r.stderr)
        r = rep.dfx('canister', 'call', 'cafresohq_market', 'market_admin_add_ledger', f'(principal "{L}")')
        check('the mock ledger is allowlisted without an upgrade', r.returncode == 0, r.stdout + r.stderr)
        run_flow(rep, M, L, tmp)
    finally:
        rep.stop()
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILS:
        print(f'replica run: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:8]))
        return 1
    print('replica run: all checks passed')
    return 0


def run_flow(rep, M, L, tmp):
    Lp = ic.Principal.from_text(L)
    Mp = ic.Principal.from_text(M)
    boss_id, op_id, stranger_id = ic.Ed25519Identity.generate(), ic.Ed25519Identity.generate(), ic.Ed25519Identity.generate()
    boss, op, stranger, anon = (ic.Agent(HOST, i) for i in (boss_id, op_id, stranger_id, None))

    def bal(owner, sub=None):
        return anon.call(L, 'icrc1_balance_of', [ACCOUNT], [{'owner': owner, 'subaccount': sub}], ret_types=['nat'], query=True)[0]

    def allowance():
        return anon.call(L, 'icrc2_allowance', [('record', [('account', ACCOUNT), ('spender', ACCOUNT)])],
                         [{'account': {'owner': boss_id.principal, 'subaccount': None}, 'spender': {'owner': Mp, 'subaccount': None}}],
                         ret_types=[ALLOWANCE], query=True)[0]['allowance']

    def approve(amount):
        return boss.call(L, 'icrc2_approve', [APPROVE], [{'from_subaccount': None, 'spender': {'owner': Mp, 'subaccount': None},
                                                         'amount': amount, 'expected_allowance': None, 'expires_at': None,
                                                         'fee': None, 'memo': None, 'created_at_time': None}], ret_types=[APPROVE_RES])[0]

    def job(jid, who=boss):
        return who.call(M, 'getJob', ['nat'], [jid], ret_types=[('opt', JOB)], query=True)[0]

    def status(jid):
        return anon.call(M, 'jobStatus', ['nat'], [jid], ret_types=[('opt', mw.PUBLIC_STATUS)], query=True)[0]

    def post(title, brief, lid):
        r = boss.call(M, 'postJob', [POST], [{'title': title, 'brief': brief, 'kind': 'copy', 'tags': ['copy'], 'ledger': Lp,
                                              'price': PRICE, 'deadlineSecs': 3600, 'listing': lid}], ret_types=[RESULT])[0]
        return r.get('ok'), r.get('err')

    def fund(jid):
        return boss.call(M, 'fundJob', ['nat'], [jid], ret_types=[MONEY])[0]

    def payouts(jid):
        return boss.call(M, 'jobPayouts', ['nat'], [jid], ret_types=[('vec', PAYOUT)], query=True)[0]

    def resume(lid):
        return anon.call(M, 'getResume', ['nat'], [lid], ret_types=[('vec', RESUME_ENTRY)], query=True)[0]

    def card(lid):
        return anon.call(M, 'getListing', ['nat'], [lid], ret_types=[('opt', CARD)], query=True)[0]

    def browse():
        return anon.call(M, 'browseListings', ['nat', 'nat'], [0, 100], ret_types=[('vec', CARD)], query=True)[0]

    # ── the money faucet, and the ledger's fee as the hall will read it ─────
    check('ic_agent reads the ledger fee with an anonymous query', anon.call(L, 'icrc1_fee', ret_types=['nat'], query=True)[0] == FEE)
    boss.call(L, 'mint', [ACCOUNT, 'nat'], [{'owner': boss_id.principal, 'subaccount': None}, MINT], ret_types=['nat'])
    check('a signed update through ic_agent lands (mint → balance)', bal(boss_id.principal) == MINT, bal(boss_id.principal))

    # ── the operator lists a coworker; the coworker's own key gets linked ───
    r = op.call(M, 'putListing', [PUT], [{'id': None, 'name': 'Mira', 'role': 'Copywriter', 'pitch': 'Blog posts that read like a person wrote them.',
                                         'brain': 'ollama:llama3.1', 'tags': ['copy', 'blog'], 'ledger': Lp, 'price': PRICE,
                                         'payoutSub': None, 'active': True}], ret_types=[RESULT])[0]
    lid = r.get('ok')
    check('putListing (a ten-field record encoded by ic_agent) is accepted', lid is not None, r)
    check('browse hides a listing with no linked worker', all(c['listing']['id'] != lid for c in browse()))

    brain_calls = []

    def brain(brief, cfg, offer):
        brain_calls.append(offer['id'])
        if 'EXPLODE' in brief:
            raise RuntimeError('the brain choked on this one')
        return f"# {offer['title']}\n\nDone as asked: {brief[:80]}\n\n— Mira"

    w = mw.MarketWorker(tmp, run_task=brain)
    w.configure({'canister': M, 'host': HOST, 'enabled': False, 'driver': 'ollama', 'model': 'ollama:llama3.1'})
    wa = ic.Agent(HOST, w.identity())
    wp = w.identity().principal
    check('an unlinked key polling the hall is told it is not linked', w.tick(wa, M) == 0 and 'link' in w.state['lastError'], w.state['lastError'])
    r = op.call(M, 'linkWorker', ['nat', 'principal'], [lid, wp], ret_types=[RESULT])[0]
    check('the operator links the coworker\'s own principal to the listing', r.get('ok') == lid, r)
    check('browse shows the listing once a worker is linked', any(c['listing']['id'] == lid for c in browse()))
    w.state['lastHeartbeat'] = 0
    check('a tick with nothing posted works 0 jobs and reports linked', w.tick(wa, M) == 0 and w.state['linked'] is True, w.state)
    check('the heartbeat puts the coworker at their desk (online)', (card(lid) or {}).get('online') is True, card(lid))

    # ── job A: the happy path, money first ──────────────────────────────────
    A, err = post('Write the launch post', 'Write a 300-word launch post for the hiring hall.', lid)
    check('the boss posts a job addressed to the listing', A is not None, err)
    check('the public jobStatus shows it posted', (status(A) or {}).get('status') == {'posted': None}, status(A))
    check('a stranger cannot read the job at all', job(A, stranger) is None)
    check('the boss reads their own brief back', (job(A) or {}).get('brief', '').startswith('Write a 300-word'))

    r = approve(PRICE + FEE)
    check('approve(price + fee) itself succeeds on the ledger', 'Ok' in r, r)
    r = fund(A)
    check('…but the hall\'s pull is refused: ICRC-2 needs an allowance of amount + fee (price + 2·fee)',
          'err' in r and 'allowance' in r['err'], r)
    check('the job is still posted after the refused pull', (job(A) or {}).get('status') == {'posted': None})
    check('only the approve fee left the boss\'s account', bal(boss_id.principal) == MINT - FEE, bal(boss_id.principal))

    r = approve(PRICE + 2 * FEE)
    check('approve(price + 2·fee) — what the shell now signs', 'Ok' in r, r)
    r = fund(A)
    check('fundJob pulls the deposit into escrow', 'ok' in r and isinstance(r['ok'].get('block'), int), r)
    check('the job\'s escrow subaccount holds exactly price + fee', bal(Mp, job_sub(A)) == PRICE + FEE, bal(Mp, job_sub(A)))
    check('the allowance is spent to zero', allowance() == 0, allowance())
    check('the boss paid two approve fees, the deposit and its fee',
          bal(boss_id.principal) == MINT - 2 * FEE - (PRICE + FEE) - FEE, bal(boss_id.principal))
    j = job(A)
    check('the job is funded with fee and escrowed recorded', j['status'] == {'funded': None} and j['fee'] == FEE and j['escrowed'] == PRICE + FEE, j)
    r = fund(A)
    check('funding it again is refused before the ledger is touched', 'err' in r and 'already funded' in r['err'], r)

    # ── the coworker takes it, does it, files it ────────────────────────────
    w.state['lastHeartbeat'] = 0
    n = w.tick(wa, M)
    check('one tick of the real worker loop claims, works and delivers the job', n == 1 and brain_calls == [A], (n, brain_calls, w.state['lastError']))
    j = job(A)
    body = f"# Write the launch post\n\nDone as asked: Write a 300-word launch post for the hiring hall.\n\n— Mira"
    check('the delivery carries the body, its first line as summary, and the sha256',
          j['status'] == {'delivered': None} and j['body'] == body and j['summary'] == '# Write the launch post'
          and j['bodySha256'] == hashlib.sha256(body.encode()).hexdigest(), {k: j[k] for k in ('status', 'summary', 'bodySha256')})
    check('the job remembers the worker and its listing', j['worker'] == wp and j['workerListing'] == lid)
    s = status(A)
    check('the public status shows delivered + summary and nothing else', s['status'] == {'delivered': None} and s['summary'] == '# Write the launch post' and 'body' not in s, s)
    check('the operator can read the job on their listing', (job(A, op) or {}).get('body') == body)

    # ── the stamp: accept and pay ───────────────────────────────────────────
    r = boss.call(M, 'acceptDelivery', ['nat', 'nat'], [A, 5], ret_types=[MONEY])[0]
    check('acceptDelivery releases the escrow', 'ok' in r, r)
    check('the operator received exactly the price', bal(op_id.principal) == PRICE, bal(op_id.principal))
    check('the escrow subaccount is empty', bal(Mp, job_sub(A)) == 0, bal(Mp, job_sub(A)))
    p = payouts(A)
    check('one payout row: <id>#release, paid, with the block',
          len(p) == 1 and p[0]['key'] == f'{A}#release' and p[0]['status'] == 'paid' and p[0]['blockIndex'] is not None and p[0]['amount'] == PRICE, p)
    j = job(A)
    check('the job is accepted, rated 5, escrowed 0', j['status'] == {'accepted': None} and j['rating'] == 5 and j['escrowed'] == 0)
    rs = resume(lid)
    check('the résumé has one "done" entry with the earnings and rating',
          len(rs) == 1 and rs[0]['outcome'] == 'done' and rs[0]['earned'] == PRICE and rs[0]['rating'] == 5 and rs[0]['jobId'] == A, rs)
    st = (card(lid) or {}).get('resume', {})
    check('the stats card counts it', st.get('jobsDone') == 1 and st.get('ratingSum') == 5 and st.get('ratingCount') == 1 and st.get('bosses') == 1, st)
    r = boss.call(M, 'acceptDelivery', ['nat', 'nat'], [A, 5], ret_types=[MONEY])[0]
    check('accepting twice pays nothing twice', 'err' in r and bal(op_id.principal) == PRICE, r)

    # ── job B: rejected, then ruled a 40/60 split by the plan admin ─────────
    B, _ = post('Rewrite the about page', 'Rewrite the about page in plain words.', lid)
    approve(PRICE + 2 * FEE)
    fund(B)
    w.state['lastHeartbeat'] = 0
    check('the coworker delivers job B', w.tick(wa, M) == 1 and (job(B) or {}).get('status') == {'delivered': None})
    r = boss.call(M, 'rejectDelivery', ['nat', 'text'], [B, 'this is not plain words'], ret_types=[RESULT])[0]
    check('the boss rejects it into a dispute', r.get('ok') == B and job(B)['status'] == {'disputed': None}, r)
    check('the dispute is on the résumé', any(e['outcome'] == 'disputed' and e['jobId'] == B for e in resume(lid)))
    try:
        boss.call(M, 'resolveDispute', ['nat', ('variant', [('payWorker', None), ('refundBoss', None), ('split', 'nat')]), 'text'],
                  [B, {'split': 40}, 'boss'], ret_types=[MONEY])
        check('the boss cannot rule on their own dispute', False, 'the call was accepted')
    except ic.CanisterReject as e:
        check('the boss cannot rule on their own dispute (rejected: only the plan admin)', 'plan admin' in str(e), e)
    op_before, boss_before = bal(op_id.principal), bal(boss_id.principal)
    r = rep.dfx('canister', 'call', 'cafresohq_market', 'resolveDispute', f'({B} : nat, variant {{ split = 40 : nat }}, "forty to the coworker")')
    check('the plan admin rules a 40% split', 'ok' in r.stdout, r.stdout + r.stderr)
    worker_amt = PRICE * 40 // 100
    boss_amt = (PRICE + FEE) - worker_amt - FEE - FEE
    check('the operator got 40% of the price', bal(op_id.principal) == op_before + worker_amt, (bal(op_id.principal) - op_before, worker_amt))
    check('the boss got the rest net of the two move fees', bal(boss_id.principal) == boss_before + boss_amt, (bal(boss_id.principal) - boss_before, boss_amt))
    check('the escrow is drained by the split', bal(Mp, job_sub(B)) == 0, bal(Mp, job_sub(B)))
    p = payouts(B)
    check('two payout rows, split-w and split-b, both paid', sorted(x['key'] for x in p) == sorted([f'{B}#split-w', f'{B}#split-b']) and all(x['status'] == 'paid' for x in p), p)
    check('the job ends accepted', job(B)['status'] == {'accepted': None})

    # ── job C: funded, then cancelled — the price comes back ────────────────
    C, _ = post('A job nobody will take', 'Never mind.', lid)
    approve(PRICE + 2 * FEE)
    fund(C)
    before = bal(boss_id.principal)
    r = boss.call(M, 'cancelJob', ['nat', 'text'], [C, 'changed my mind'], ret_types=[MONEY])[0]
    check('cancelJob on a funded job refunds', 'ok' in r, r)
    check('the boss gets the price back (the two fees are spent)', bal(boss_id.principal) == before + PRICE, bal(boss_id.principal) - before)
    check('the escrow is empty after the refund', bal(Mp, job_sub(C)) == 0)
    check('the job reads refunded or cancelled', job(C)['status'] in ({'refunded': None}, {'cancelled': None}), job(C)['status'])

    # ── job D: the brain throws → failJob, back on the board, one attempt spent
    D, _ = post('An impossible one', 'EXPLODE: do the impossible.', lid)
    approve(PRICE + 2 * FEE)
    fund(D)
    w.state['lastHeartbeat'] = 0
    n = w.tick(wa, M)
    j = job(D)
    check('when the brain throws the loop files failJob and works 0 jobs', n == 0 and w.state['jobsFailed'] == 1, (n, w.state['lastError']))
    check('the job is back to funded with one attempt spent and no worker', j['status'] == {'funded': None} and j['attempts'] == 1 and j['worker'] is None, {k: j[k] for k in ('status', 'attempts', 'worker')})
    check('the snag is on the résumé', any(e['outcome'] == 'snag' and e['jobId'] == D for e in resume(lid)))
    check('the progress note is cleared with the claim', boss.call(M, 'jobProgress', ['nat'], [D], ret_types=[('opt', 'text')], query=True)[0] is None)
    check('the escrow still holds the deposit for the next taker', bal(Mp, job_sub(D)) == PRICE + FEE)

    # ── privacy and the unlink ──────────────────────────────────────────────
    check('a stranger has no jobs', stranger.call(M, 'myJobs', ret_types=[('vec', JOB)], query=True)[0] == [])
    r = stranger.call(M, 'claimJob', ['nat'], [D], ret_types=[RESULT])[0]
    check('a stranger\'s key cannot claim', 'err' in r and 'not linked' in r['err'], r)
    r = op.call(M, 'unlinkWorker', ['nat'], [lid], ret_types=[RESULT])[0]
    check('the operator unlinks the key in one call', r.get('ok') == lid, r)
    w.state['lastHeartbeat'] = 0
    check('the unlinked key is turned away on its next tick', w.tick(wa, M) == 0 and w.state['linked'] is False)
    check('browse hides the listing again', all(c['listing']['id'] != lid for c in browse()))


if __name__ == '__main__':
    sys.exit(main())
