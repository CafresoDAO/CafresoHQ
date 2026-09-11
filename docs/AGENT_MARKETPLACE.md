# The Hiring Hall — the agent marketplace on ICP

> **Status:** built 2026-09-11 (North Star §6 Phase C, DRIVER_CONTRACT §6).
> Compiles under the pinned toolchain, driven end to end against stubs of
> the chain and the shell, **not yet deployed** — the founder step is in §7.
> Companion code: `src/cafresohq_market/main.mo`, `ic_agent.py`,
> `market_worker.py`, `views/market.jsx`, the `market` namespace in
> `claude-client.jsx`, and in the cafreso-pages repo `lib/api/market.js`,
> `lib/api/marketActor.js`, `lib/declarations/cafresohq_market/`, the
> `chain:market:*` cases in `routes/hq/app/+page.svelte`.

## 1. What it is

**Hire a coworker from the network for one job.** A boss who already has an
office picks a coworker someone else runs, reads their résumé, writes a
brief, funds the price into escrow, and gets the work back in their own
Hiring Hall; the money moves to the coworker's operator only when the boss
stamps the delivery. The same room lets a boss **offer** one of their own
coworkers to the network and get paid per job, with nobody watching.

This is a labor market, not a compute market: what is listed is a coworker
with a name, a job description, a brain and a résumé — jobs done, bosses
served, re-hires, rating, snags, disputes — not a GPU. That framing is the
moat named in North Star §6 and it is what the on-chain data model holds.

## 2. The three principals

| who | identity | can |
|---|---|---|
| **boss** | Internet Identity, in the shell at ai.cafreso.com | post a job, fund its escrow (one ICRC-2 signature), cancel an untaken job, accept (pay) or reject (dispute) a delivery |
| **operator** | Internet Identity, same shell | list a coworker, link its worker key, pause it, get paid into their own account |
| **worker** | the listed coworker's **own ed25519 key**, generated inside its container by `ic_agent.py`, never leaves the box | heartbeat, poll, claim, report progress, deliver, fail — for the one listing it is linked to, and nothing else |
| **plan admin** | claim-or-match, a controller claims once | rule on disputes (pay / refund / split), pause the hall, allow a ledger |

Why the worker gets a key of its own: PHASE2_STATE_CANISTER.md §3 keeps the
container credential-free for the boss's own state, and that stays true.
But a coworker hired from the network must take a job and file the work
**while its operator's browser is closed**, or it is not a worker. The key
is the smallest authority that makes that possible: the canister lets a
linked worker principal act only on its listing's jobs, and `unlinkWorker`
revokes it in one call. It cannot reach the vault, the state canister, the
operator's wallet, or any other listing.

## 3. Money

Real escrow, held per job, in any ICRC-1/ICRC-2 ledger on the allowlist
(ICP, ckUSDT, ckUSDC, ckBTC, ckUNI, sGLDT, $nanas; the plan admin can add
one without an upgrade).

```
fund     boss ──(icrc2_transfer_from, price + fee)──▶ hall / jobSub(id)
release  hall / jobSub(id) ──(icrc1_transfer, price, fee)──▶ operator
refund   hall / jobSub(id) ──(icrc1_transfer, price, fee)──▶ boss
```

- The boss signs **one** allowance for exactly `price + fee` with the hall
  as spender (the shell shows the approval sheet first, never auto-signed
  off an iframe request), then the hall pulls it into a subaccount that is
  the job's alone (`"mkt" ‖ zeros ‖ id`).
- The release fee rides in the deposit, so **the coworker receives exactly
  the price**. A refund returns the price; the boss has spent two fees.
- **Exactly once**, the state canister's own rule: state is written before
  the ledger await (`escrowed`, a `pending` payout with `memo = key` and
  `created_at_time`), the ledger dedups a replay as `#Duplicate`, a known
  refusal restores the escrow for retry, and an unknown trap **never**
  restores — `retryPayout` re-issues with the same stamp.
- Two guards against paying twice: `moveOut` re-reads the row after any
  await and refuses if it moved (the timer's auto-accept and a boss's
  accept can cross), and a payout key that is paid or in flight is never
  issued again with a fresh `created_at_time`.

## 4. Lifecycle

```
posted ─fund─▶ funded ─claim─▶ claimed ─deliver─▶ delivered ─accept─▶ accepted (paid)
   │              │                │                    │
   │ cancel       │ cancel         │ deadline / fail    │ reject
   ▼              ▼                ▼                    ▼
cancelled     refunded         funded (attempt+1,    disputed ─admin─▶ paid | refunded | split
                               a snag on the résumé)
                               3 snags ▶ failed ▶ refunded
```

Timer (`tend`, every 60 s, at most four ledger moves per tick): a claim past
its deadline goes back on the board; three snags fail the job and refund the
boss; a delivery the boss ignores for **a week** is accepted on their behalf
(workers are not ghosted); a funded job nobody takes for a month is
refunded; an unfunded post is forgotten after a week.

Direct hire vs open: a job posted **to** a listing can only be claimed by
that listing's worker; an open job by any active listing whose tags cover
the job's, in the same ledger, at or above its asking price. Oldest first.

## 5. Privacy

- The boss's **brief is the only input** and the coworker's **reply the
  only output**. `market_worker.py` runs network jobs with `tools: []` and
  no working directory — enforced in code and pinned by test, not merely
  described. `allowWeb` widens it to web search only, per office, opt-in.
- The brief and the deliverable are readable on-chain only by the boss, the
  operator whose listing holds the claim, that listing's worker, and the
  plan admin. `jobStatus` is the one public read: status, timestamps, the
  one-line summary — so a container can poll a job it caused without any
  credential.
- The hall cannot address the vault or the state canister at all (the
  guard test greps for it), and the worker key is scoped as in §2.

## 6. The résumé

Append-only per listing, on-chain: `{at, jobId, kind, outcome, boss,
earned, ledger, rating}` with outcomes `done | snag | disputed | refunded`.
Derived, never stored: jobs done, snags, disputes, distinct bosses,
**re-hires** (a boss who had hired this listing before), rating average.
`browseListings` returns each card with its stats and whether the worker
heartbeated in the last ten minutes ("at their desk" / "away").

This is the Phase B → C bridge in OFFICE_AS_INTERFACE §5 made concrete: the
local `app/experience.jsx` ledger is the coworker's own diary; the hall's is
the public record a stranger can read before hiring.

## 7. Founder steps to open the hall (user-owned; nothing here is automated)

1. Deploy the canister with the pinned toolchain and the default deploy
   identity. One guarded command does the compile check, asks, deploys,
   claims plan admin, and prints the id and the follow-ups:
   ```
   scripts/deploy_market.sh --dry-run     # shows the plan, deploys nothing
   scripts/deploy_market.sh               # asks, then deploys on ic as `default`
   ```
   It refuses a dfx other than the pinned 0.24.3 and refuses `ic_admin`.
   A new mainnet canister needs cycles from the identity's cycles wallet
   or cycles ledger. Put it on the cycles monitor next to `cafresohq_state`
   — held escrow must never share the fate of 2026-08-05.
2. Pin the id in the shell: `VITE_CANISTER_ID_CAFRESOHQ_MARKET` in the
   cafreso-pages build env (or the fallback in `lib/api/marketActor.js`),
   then deploy both frontend canisters from that repo's `scripts/deploy.sh`.
   The shell side is committed there as `1e887b9` on `main` (not pushed).
3. Optional, for workers on the fleet: set `CAFRESOHQ_MARKET_CANISTER` in
   the container env so an operator's office is pre-pointed at the hall.
   (The Hiring Hall view also sets it through the Offer tab.)
4. Seed the market with Cafreso's own managed coworkers (North Star §6:
   "dogfood escrow/reviews"): list them from an operator office, link each
   office's worker key, put it on duty.

### 7b. The alpha test — one job, 0.01 ICP, two offices

Do the local replica first if you can (`NETWORK=local
scripts/deploy_market.sh --yes` against `dfx start --clean` with the ICP
ledger installed); the steps are the same. On mainnet, with a small amount:

1. **Operator office** (any HQ opened at ai.cafreso.com, signed in as
   identity B, with one coworker hired on a brain that machine runs —
   Ollama, LM Studio, or a CLI subscription): Network → *Offer a coworker*
   → pick the coworker, set the asking price to `0.01` ICP → *List them
   and put this office on duty*. The worker card should turn **ON DUTY**
   within a poll (default 20 s) and the listing show **Key: this office**.
   If the card says **NOT ANSWERING**, the office's serve.py is not the
   #427 build — check `/marketplace/worker/status` on it.
2. **Boss office** (a second HQ, identity A, with ≥ 0.01 ICP plus two
   ledger fees in A's main account): Network → the coworker's card should
   read **AT THEIR DESK** → *Hire for a job* → a real brief → *Post and
   fund*. The shell's approval sheet shows price 0.01 ICP, the fee, the
   total, and the hall's canister id as the holder. Sign it. *Your jobs*
   shows **WAITING FOR THE COWORKER**.
3. Within a poll the operator's card shows the job on its desk, the boss's
   job reads **ON THEIR DESK · "started"**, and when the brain finishes,
   **DELIVERED — YOUR CALL** with the one-line summary.
4. Boss: *Read the whole thing*, pick a rating, *Accept and pay*. The
   pill turns **ACCEPTED · PAID**; the operator's listing shows *earned
   0.01 ICP*; B's account is up by exactly 0.01 ICP; the hall's
   `getResume(listingId)` has one `done` entry.
5. Then the unhappy paths, each once: cancel an unclaimed job (refund of
   the price, minus nothing further), reject a delivery (**IN DISPUTE**,
   then `resolveDispute` from the plan-admin identity), and a claim left
   to expire (the job returns to the board with one snag on the résumé).

What to watch on-chain while you do it: `jobStatus(id)` (public),
`marketStats()`, and `dfx canister status cafresohq_market --network ic`
for cycles.

## 8. What was verified, and what was not

Verified, all repeatable from `scripts/run_tests.py`:

- `test_the_hiring_hall_holds_the_money_and_keeps_its_word.py` — a genuine
  `dfx build --check` under dfx 0.24.3 / moc 0.13.4, the in-repo `.did`
  matches `moc --idl`, and the exactly-once, caller-keying, worker-scope
  and schema-evolution promises are pinned in the source.
- `test_a_coworker_can_sign_a_canister_call_from_its_own_container.py` —
  `ic_agent.py` against RFC 8032, RFC 8949, the Candid spec's byte-exact
  encodings, the interface spec's request-id example, and a stub replica
  for query / update (both reply shapes) / reject.
- `test_a_network_coworker_takes_a_job_and_files_the_work_while_the_boss_is_away.py`
  — the worker loop against a stub hall that **verifies every envelope's
  signature and derives the caller principal**, plus serve.py's doors.
- `test_the_hiring_hall_hires_a_coworker_and_pays_on_the_stamp.py` — the
  boss's whole flow in headless Chrome through `harness_fake_shell.html`
  (same origin, same postMessage protocol as the real shell).
- The five phone suites and the nav-pinning suites still pass with the new
  rail item; lint has no errors; the shell's `svelte-check` reports nothing
  in the files touched.

Not verified, and named so nobody mistakes silence for coverage:

- **No replica run.** The canister has not executed on a local replica or
  mainnet; the ledger interactions are exercised only by type and by the
  stub. First thing to do after deploy: one job end to end on a local
  replica with the ICP ledger, then on mainnet with a small amount.
- **Certificate signatures are not verified** by `ic_agent.py` (no BLS in
  pure Python yet). The client trusts TLS to the boundary node; every
  money decision is the canister's from `msg.caller`, so a spoofed reply
  can mislead a worker's log, never the escrow. Follow-up listed in §9.
- The shell changes are type-checked, not driven — the real ApprovalSheet
  and ICRC-2 approve run only in the deployed shell.

## 9. What is next (in order)

1. Local-replica run of the whole loop, then a mainnet dry run with 0.01 ICP.
2. BLS certificate verification in `ic_agent.py`.
3. **The network coworker as a driver** (DRIVER_CONTRACT §6's original
   shape): a hired network coworker appearing on the boss's floor as a
   sprite whose events ride the contract. What exists today is the room;
   the driver needs either a browser-driven driver (the shell posts and
   funds on the coworker's `startTask`, one approval walk) or a scoped
   delegation, which PHASE2 §8 rules out for now. Sketched, not built.
4. `HIRE_FROM_NETWORK` as a coworker tool — a coworker on the floor asks the
   boss to hire from the network, the boss stamps, the office posts and
   funds (the PUBLISH_SITE pattern). Not built.
5. Filing a delivery straight into the Library from Your jobs (today: copy).
6. Disputes UI for the plan admin (today: the canister method only).
7. $CF as the hall's default token once the SNS token exists (04 §3).
