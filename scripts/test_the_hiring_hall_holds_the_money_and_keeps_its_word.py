#!/usr/bin/env python3
"""The hiring hall (src/cafresohq_market/main.mo) holds real money in escrow.
This suite pins the promises its header makes, the way
test_worker_payout_sweep_does_not_wipe_mid_sweep_accrual.py pins the state
canister's: a genuine moc compile under the pinned dfx, plus structural
checks on the source that a refactor cannot quietly undo.

What is pinned:
  * it compiles (dfx build --check, DFX_VERSION from .dfx-version; skipped
    when dfx is not on PATH) and the in-repo .did matches what moc emits;
  * exactly-once money: `moveOut` and `fundJob` write their state BEFORE the
    ledger await, dedup on #Duplicate, re-read the row after an await, and
    the unknown-outcome catch never restores escrow;
  * a payout key is never issued twice with a fresh created_at_time — the
    in-flight guard is there and `retryPayout` reuses the old stamp;
  * caller keying: only two methods take a principal argument (linkWorker,
    market_admin_add_ledger), every boss/operator update refuses the
    anonymous caller, and every private query returns nothing to it;
  * the worker's authority is exactly claim/progress/deliver/fail/heartbeat/
    poll — a worker key cannot post, fund, accept, list, link or rule;
  * schema-evolution: the field sets of Job, Listing, Payout and ResumeEntry
    are pinned exactly. moc 0.13 can read an upgraded stable var only when
    the old record is a subtype of the new one, so a field may be REMOVED
    from these but never ADDED; anything new goes in a side table. If this
    check fails on an added field, that is the check working;
  * the ICP ledger is in the allowlist, the body cap is 64 KiB, the timer is
    the last declaration, and dfx.json declares the canister.

Run: python3 scripts/test_the_hiring_hall_holds_the_money_and_keeps_its_word.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MO = ROOT / 'src' / 'cafresohq_market' / 'main.mo'
DID = ROOT / 'src' / 'cafresohq_market' / 'cafresohq_market.did'

FAILS = []


def check(name, cond, detail=''):
    print(('  ok    ' if cond else '  FAIL  ') + name + ((' — ' + str(detail)) if not cond else ''))
    if not cond:
        FAILS.append(name)


def body_of(src, marker):
    """The text of one `func name(` … up to its closing brace (brace-balanced)."""
    i = src.index(marker)
    j = src.index('{', i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == '{':
            depth += 1
        elif src[k] == '}':
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise ValueError('unbalanced')


def func_text(src, name):
    """From `func name(` to the next top-level declaration — works for the
    one-line `= async …` methods that have no brace body."""
    i = src.index(f'func {name}(')
    m = re.search(r'\n  (?:public |func |///|// ──|ignore )', src[i + 1:])
    return src[i:i + 1 + m.start()] if m else src[i:]


def strip_comments(src):
    return re.sub(r'//[^\n]*', '', src)


def did_fields(did, typename):
    m = re.search(r'type ' + typename + r' =\s*record \{(.*?)\};', did, re.S)
    return sorted(f.strip().split(':')[0] for f in m.group(1).split(';') if f.strip())


def main():
    print('the hiring hall holds the money and keeps its word')
    src = MO.read_text(encoding='utf-8')
    did = DID.read_text(encoding='utf-8')

    # ── compile ───────────────────────────────────────────────────────────
    pinned = (ROOT / '.dfx-version')
    version = pinned.read_text(encoding='utf-8').strip() if pinned.exists() else os.environ.get('DFX_VERSION', '')
    has_dfx = bool(shutil.which('dfx'))
    check('dfx is on PATH (needed to genuinely compile main.mo with moc)', has_dfx, 'skipping the compile check')
    if has_dfx:
        env = dict(os.environ)
        if version:
            env['DFX_VERSION'] = version
        r = subprocess.run(['dfx', 'build', 'cafresohq_market', '--check'],
                           cwd=ROOT, capture_output=True, text=True, timeout=240, env=env)
        out = (r.stdout or '') + (r.stderr or '')
        check('moc compiles the hiring hall with no errors (the Nat-floor "may trap" warnings are fine)',
              r.returncode == 0 and 'error' not in out.lower(), out[-1500:])
    moc = Path.home() / '.cache' / 'dfinity' / 'versions' / version / 'moc' if version else None
    base = Path.home() / '.cache' / 'dfinity' / 'versions' / version / 'base' if version else None
    if moc and moc.is_file() and base and base.is_dir():
        with tempfile.TemporaryDirectory() as d:
            outp = Path(d) / 'm.did'
            r = subprocess.run([str(moc), '--idl', '--package', 'base', str(base), str(MO), '-o', str(outp)],
                               capture_output=True, text=True, timeout=240)
            fresh = outp.read_text(encoding='utf-8') if outp.exists() else ''
            norm = lambda t: re.sub(r'\s+', ' ', t).strip()   # noqa: E731
            check('the in-repo .did is exactly what moc emits for main.mo (no drift)',
                  fresh and norm(fresh) == norm(did), (r.stderr or '')[-400:] or 'differs')
    else:
        check('moc for the pinned dfx is cached (needed for the .did drift check)', False, 'skipping')

    # ── exactly-once money ───────────────────────────────────────────────
    mo = body_of(src, 'func moveOut(')
    check('moveOut writes the job and the pending payout BEFORE the ledger await',
          mo.index('storeJob(') < mo.index('recordPayout(') < mo.index('await ledger.icrc1_transfer'))
    check('moveOut re-reads the row and refuses when it moved during a prior await',
          'the job changed while this was in flight' in mo and mo.index('natMap.get(jobs, j.id)') < mo.index('storeJob('))
    check('moveOut answers a replayed move with #duplicate, not a second transfer', '#Err(#Duplicate' in mo)
    check('moveOut never issues an in-flight or unknown payout key again',
          'already in flight' in mo and 'use retryPayout' in mo)
    catch_arm = mo[mo.index('} catch (e) {'):]
    check('the unknown-outcome catch does NOT restore escrow (funds may have moved)',
          'escrowed = held' not in catch_arm and 'failed:unknown' in catch_arm)
    known = mo[mo.index('case (#Err(e))'):mo.index('} catch (e) {')]
    check('a KNOWN refusal restores the escrow for a retry', 'escrowed = held' in known)
    fj = body_of(src, 'func fundJob(')
    check('fundJob pins created_at_time in fundAttempt BEFORE the transfer_from await',
          fj.index('fundAttempt := natMap.put') < fj.index('await ledger.icrc2_transfer_from'))
    check('fundJob re-reads the job after the await',
          fj.find('natMap.get(jobs, id)', fj.index('await ledger.icrc2_transfer_from')) > 0)
    check('fundJob treats #Duplicate as funded and #TooOld as a fresh attempt',
          '#Err(#Duplicate' in fj and '#Err(#TooOld)' in fj and 'natMap.delete(fundAttempt' in fj)
    check('fundJob pulls price + fee so the worker receives exactly price', 'amount = j.price + fee' in fj)
    rp = body_of(src, 'func retryPayout(')
    check('retryPayout reuses the payout\'s own created_at_time', 'Nat64.fromIntWrap(p.scheduledAt)' in rp)
    check('retryPayout refuses a payout already paid', '"already paid"' in rp)

    # ── caller keying ─────────────────────────────────────────────────────
    sigs = re.findall(r'public (?:shared|query)[^\n]*?func (\w+)\(([^)]*)\)', src)
    with_principal = sorted(n for n, args in sigs if re.search(r':\s*Principal\b', args))
    check('only linkWorker and market_admin_add_ledger take a principal argument',
          with_principal == ['linkWorker', 'market_admin_add_ledger'], with_principal)
    for name in ('postJob', 'fundJob', 'cancelJob', 'acceptDelivery', 'rejectDelivery', 'retryPayout',
                 'putListing', 'linkWorker', 'unlinkWorker'):
        b = body_of(src, f'func {name}(')
        check(f'{name} refuses the anonymous caller', 'Principal.isAnonymous(msg.caller)' in b[:600])
    for name in ('myJobs', 'getJob', 'jobPayouts', 'jobProgress', 'myListings', 'operatorJobs'):
        b = body_of(src, f'func {name}(')
        check(f'{name} answers the anonymous caller with nothing', 'Principal.isAnonymous(msg.caller)' in b)
    for name in ('market_admin_pause', 'market_admin_add_ledger', 'resolveDispute', 'market_admin_claim'):
        b = body_of(src, f'func {name}(')
        check(f'{name} is behind the plan-admin gate', 'adminGate(msg.caller)' in b)
    check('the plan admin is claim-or-match (a controller claims once, then only that principal)',
          'Principal.isController(caller)' in body_of(src, 'func adminGate('))

    # ── the worker's authority ────────────────────────────────────────────
    # A worker-key method is gated either by the key's listing (poll, heartbeat,
    # claim) or by the claim the key holds (progress, deliver, fail).
    worker_methods = sorted(n for n, _ in sigs
                            if 'listingOfWorker(msg.caller)' in func_text(src, n) or 'j.worker != ?msg.caller' in func_text(src, n))
    check('worker-key methods are exactly heartbeat/poll/claim/progress/deliver/fail',
          worker_methods == sorted(['workerHeartbeat', 'workerPoll', 'claimJob', 'progressJob', 'deliverJob', 'failJob']), worker_methods)
    for name in ('progressJob', 'deliverJob', 'failJob'):
        check(f'{name} only acts on the caller\'s own claim', 'j.worker != ?msg.caller' in body_of(src, f'func {name}('))
    check('a claim is only for a funded job addressed to (or open to) this listing',
          'j.status != #funded' in body_of(src, 'func claimJob(') and 'covers(l.tags, j.tags)' in body_of(src, 'func claimJob('))
    code = strip_comments(src)
    check('the vault is unreachable: nothing here imports or addresses cafresohq_state',
          'cafresohq_state' not in code and 'ydacz' not in code and 'vhw7q' not in code
          and re.findall(r'actor\s*\(', code) == ['actor ('] and 'actor (Principal.toText(p)) : Ledger' in code)

    # ── schema evolution ──────────────────────────────────────────────────
    check('Job fields are pinned (remove only; never add — use a side table)',
          did_fields(did, 'Job') == sorted(['attempts', 'body', 'bodySha256', 'boss', 'brief', 'claimedAt', 'createdAt',
                                            'deadlineSecs', 'deliveredAt', 'escrowed', 'fee', 'id', 'kind', 'ledger', 'listing',
                                            'note', 'price', 'rating', 'status', 'summary', 'tags', 'title', 'updatedAt',
                                            'worker', 'workerListing']), did_fields(did, 'Job'))
    check('Listing fields are pinned',
          did_fields(did, 'Listing') == sorted(['active', 'brain', 'createdAt', 'id', 'lastSeen', 'ledger', 'name', 'operator',
                                                'payoutSub', 'pitch', 'price', 'role', 'tags', 'updatedAt', 'worker']), did_fields(did, 'Listing'))
    check('Payout fields are pinned',
          did_fields(did, 'Payout') == sorted(['amount', 'blockIndex', 'jobId', 'key', 'scheduledAt', 'status', 'to', 'toSub', 'ts']))
    check('ResumeEntry fields are pinned',
          did_fields(did, 'ResumeEntry') == sorted(['at', 'boss', 'earned', 'jobId', 'kind', 'ledger', 'outcome', 'rating']))
    check('the side tables exist for what comes later (progress, payouts, resumes, fundAttempt)',
          all(f'stable var {t} ' in src for t in ('progress', 'payouts', 'resumes', 'fundAttempt')))

    # ── limits, ledgers, timer, dfx.json ──────────────────────────────────
    check('the ICP ledger is in the allowlist', '"ryjl3-tyaaa-aaaaa-aaaba-cai"' in src)
    check('the deliverable body is capped at 64 KiB', 'let BODY_MAX : Nat = 65_536;' in src)
    check('a job needs at least three snags to fail', 'let MAX_ATTEMPTS : Nat = 3;' in src)
    tail = src.rstrip().rsplit('\n', 3)[-3:]
    check('the timer is the last declaration in the actor', any('Timer.recurringTimer<system>' in l for l in tail), tail)
    dfx = json.loads((ROOT / 'dfx.json').read_text(encoding='utf-8'))
    check('dfx.json declares cafresohq_market from src/cafresohq_market/main.mo',
          dfx.get('canisters', {}).get('cafresohq_market', {}).get('main') == 'src/cafresohq_market/main.mo')
    check('jobStatus is the only public read that exposes a job, and it carries no brief or body',
          'brief' not in body_of(src, 'func jobStatus(') and 'body' not in body_of(src, 'func jobStatus(').replace('bodySha', ''))

    print()
    if FAILS:
        print(f'hiring hall: {len(FAILS)} FAILED — ' + ', '.join(FAILS[:6]))
        return 1
    print('hiring hall: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
