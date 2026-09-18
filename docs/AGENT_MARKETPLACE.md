# The Hiring Hall — the agent marketplace on ICP

> **Status:** built 2026-09-11 (North Star §6 Phase C, DRIVER_CONTRACT §6),
> verified on a local replica 2026-09-12 (#429), **live on mainnet since
> 2026-09-15** as `cafresohq_market` = **`rliqj-gqaaa-aaaal-qxjuq-cai`**
> (next to `cafresohq_state`, plan admin = the `default` identity). The
> shell, UI and fleet follow-ups are §7 steps 2–4; the first job is §7b.
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
(ICP, ckUSDT, ckUSDC, ckBTC, ckUNI, **ckBAT**, sGLDT, $nanas; the plan admin
can add one without an upgrade, which is the only way to reach a hall that
is already deployed — `extraLedgers` is stable, so it survives upgrades).

**ckBAT (2026-09-17).** A Brave creator is paid in BAT and should be able to
spend it on a coworker without selling it first: minegold.brave bridges
BAT → ckBAT, a listing is priced in ckBAT, and the operator who earns it can
refine it into sGLDT rather than pay Ethereum gas to bridge back out. Its
shape is unlike ICP's — 18 decimals, and a 0.1 ckBAT fee (1e17) that is
thirteen orders of magnitude larger — so the replica run below is
parameterised by ledger shape and the whole job is proven at both
(`CAFRESOHQ_LEDGER_SHAPE=ckbat`).

**The ckUSDT row was wrong from #427 until 2026-09-17.** It held
`cngnf-gddge-…-3ae`, which is not a canister at all, so every ckUSDT job was
refused as an unknown ledger; the same bad value sat in `cafresohq_state`'s
payroll allowlist. The real ledger is `cngnf-vqaaa-aaaar-qag4q-cai`, which is
what the shell's `TOKENS` table always used. Both are corrected in source;
the deployed hall is corrected by `market_admin_add_ledger`.

```
fund     boss ──(icrc2_transfer_from, price + fee)──▶ hall / jobSub(id)
release  hall / jobSub(id) ──(icrc1_transfer, price, fee)──▶ operator
refund   hall / jobSub(id) ──(icrc1_transfer, price, fee)──▶ boss
```

- The boss signs **one** allowance for `price + 2·fee` with the hall as
  spender (the shell shows the approval sheet first, never auto-signed off
  an iframe request), then the hall pulls `price + fee` into a subaccount
  that is the job's alone (`"mkt" ‖ zeros ‖ id`). Why two fees: an ICRC-2
  ledger takes `amount + fee` **out of the allowance**, so an allowance of
  `price + fee` is refused with `InsufficientAllowance` — the shell shipped
  that way and the replica run (§8) caught it. What leaves the boss's
  account is `price + 3·fee`: the approve's fee, the deposit's fee, and
  the release fee that rides in the deposit.
- The release fee rides in the deposit, so **the coworker receives exactly
  the price**. A refund returns the price; the boss has spent two fees.
- **A price is at least a hundred of its ledger's fees** (2026-09-17), checked
  in `postJob` and `putListing` against a live `icrc1_fee`. The number is not
  taste. A dispute may be ruled 1–99%, the escrow holds price + fee, and
  paying the coworker `pct` while returning the rest costs two moves, so a
  ruling is payable only while `price + fee >= price*pct/100 + 2*fee` — which
  at the worst legal case, 99%, is exactly `price >= 100*fee`. Under the floor
  `resolveDispute` answers "escrow short": nothing traps and no money is lost,
  but the middle ruling quietly stops existing on the one job where somebody
  asked for a middle. On ICP the floor is 0.01, which is already what §7b
  spends, so this was unreachable until ckBAT — whose fee is thirteen orders
  of magnitude larger — made `0.15 ckBAT` a thing a person would type. The
  floors today: **0.01 ICP · 10 ckBAT · 1 ckUSDT**. Cost of the rule: `postJob`
  and `putListing` each make one inter-canister call now, and both fail closed
  if the ledger will not answer.
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

> **Done 2026-09-15.** Step 1 (the canister), step 2 (the shell — both
> domains, parity verified; the id is also pinned as the fallback in
> `marketActor.js`) and the `cafresohq_ui` deploy are live. Step 3 (the
> fleet roll) is optional. On the way: paying from the cycles ledger needs
> `NEXT_TO`; the shell repo's dfx 0.29.1 needs
> `DFX_WARNING=-mainnet_plaintext_identity` for the `default` identity; and
> `cafreso_pages` (dqcmv) refused its upgrade at 0.33 T until a 0.1 T top-up
> — an asset canister needs headroom above that to take an install. What is
> not done: §7b, the first job on mainnet.

1. Deploy the canister with the pinned toolchain and the default deploy
   identity. One guarded command does the compile check, asks, deploys,
   claims plan admin, and prints the id and the follow-ups:
   ```
   scripts/deploy_market.sh --dry-run     # shows the plan, deploys nothing
   scripts/deploy_market.sh               # asks, then deploys on ic as `default`
   ```
   It refuses a dfx other than the pinned 0.24.3 and refuses `ic_admin`.
   A new mainnet canister needs cycles. Measured 2026-09-15: the `default`
   identity held 0.0098 ICP, 0.085 T cycles on its cycles ledger and
   0.034 T in its wallet — none of which creates a canister (the create
   fee alone is 0.1 T). Fund it first, then pay from the cycles ledger:
   ```
   dfx ledger account-id --identity default          # send ICP to this account
   dfx cycles convert --amount 2.75 --network ic --identity default   # ≈ 5 T at 1 ICP = 1.83 XDR
   NO_WALLET=1 WITH_CYCLES=4800000000000 NEXT_TO=ydacz-riaaa-aaaal-qxeja-cai scripts/deploy_market.sh
   ```
   `NO_WALLET=1` pays from the cycles ledger instead of the wallet;
   `WITH_CYCLES` is the starting balance, fee included; `NEXT_TO` puts the
   hall on `cafresohq_state`'s subnet — paying from the cycles ledger, dfx
   cannot choose a subnet on its own ("Cannot automatically decide which
   subnet to target"), and `SUBNET=<id>` names one outright. Five trillion
   is a year of an idle Motoko canister and then some; two is the floor.
   **Done 2026-09-15:** 5.107 T landed, 4.8 T sent, the canister was born
   with 4.30 T (that subnet's create fee is ~0.5 T, not 0.1 T), id
   `rliqj-gqaaa-aaaal-qxjuq-cai`, `market_admin_claim` → `true`.
   Put it on the cycles monitor next to `cafresohq_state` — held escrow
   must never share the fate of 2026-08-05.
2. Pin the id in the shell: `VITE_CANISTER_ID_CAFRESOHQ_MARKET` in the
   cafreso-pages build env (or the fallback in `lib/api/marketActor.js`),
   then deploy both frontend canisters from that repo's `scripts/deploy.sh`.
   The shell side is committed there on `main` (not pushed): `1e887b9` the
   bridge, `8692de4` the allowance fix from the replica run (§3) — the
   alpha's *Post and fund* fails with *insufficient allowance* without it.
3. Ship the Hiring Hall room to the HQ UI canister. Fleet offices reached
   through the gateway load the UI from `cafresohq_ui`
   (`vhoil-eyaaa-aaaal-qxc7q-cai`), not from the container, so the room
   is not on any fleet office until:
   ```
   DFX_VERSION=0.24.3 dfx deploy cafresohq_ui --network ic --identity default
   ```
   (its dfx.json build step runs `scripts/build_hq_ui.py`, which bundles
   the UI and assembles `hq-ui/`). Self-hosted and local offices serve
   the container's own baked-in `/hq.html` and need only step 4.
4. Roll the fleet to an image that carries `ic_agent.py` and
   `market_worker.py`: CI's `sha-<short>` / `latest` from trunk head #429
   or later — #427/#428's image (`sha-30a5c79`) did **not** copy them
   (the Offer tab answered 500). Optional: set `CAFRESOHQ_MARKET_CANISTER`
   in the container env so an operator's office is pre-pointed at the
   hall (the Hiring Hall view also sets it through the Offer tab).
5. Seed the market with Cafreso's own managed coworkers (North Star §6:
   "dogfood escrow/reviews"): list them from an operator office, link each
   office's worker key, put it on duty.

### 7b. The alpha test — one job, 0.01 ICP, two offices

The local-replica walk is a test now — `python3
scripts/test_the_hall_runs_a_whole_job_on_a_real_replica.py` (~3 min,
starts and stops its own replica on port 4977, mock ledger with the ICP
ledger's rules) — run it once before deploying. On mainnet, with a small
amount:

1. **Operator office** (any HQ opened at ai.cafreso.com, signed in as
   identity B, with one coworker hired on a brain that machine runs —
   Ollama, LM Studio, or a CLI subscription): Network → *Offer a coworker*
   → pick the coworker, set the asking price to `0.01` ICP → *List them
   and put this office on duty*. The worker card should turn **ON DUTY**
   within a poll (default 20 s) and the listing show **Key: this office**.
   If the card says **NOT ANSWERING**, the office's serve.py is not the
   #427 build — check `/marketplace/worker/status` on it.
2. **Boss office** (a second HQ, identity A, with ≥ 0.01 ICP plus three
   ledger fees — 0.0103 ICP — in A's main account): Network → the
   coworker's card should read **AT THEIR DESK** → *Hire for a job* → a
   real brief → *Post and fund*. The shell's approval sheet shows price
   0.01 ICP, the three fees (0.0003), what leaves the account (0.0103),
   the allowance being signed (0.0102), and the hall's canister id as the
   holder. Sign it. *Your jobs* shows **WAITING FOR THE COWORKER**. If it
   instead says *insufficient allowance*, the shell on ai.cafreso.com is
   older than cafreso-pages' allowance fix (§3) — redeploy the frontend.
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

### 7c. Cycles: the hall does not tick on a clock any more

Measured on the live hall on 2026-09-17, by sampling `cycle_balance` every
few seconds (the trace is reproducible with a query loop; queries are free):

| charge | size | cadence | per day |
|---|---|---|---|
| one timer tick, empty job map | ~28.6 M cycles | every 60 s | ~41 B |
| storage (3.8 MB) | ~0.24 M | every ~20 s | ~0.95 B |
| one HTTP request answered through `http_request_update` | ~7.7 M | per request | — |

The tick is the message itself plus the collector's pass over the heap; it
costs the same with nothing to do. So the 60-second `recurringTimer` was
~97% of the hall's burn — 4.2 T in about a hundred days — while the hall
stood empty, and `cafresohq_state` died of the same thing in August (its
wake timer every 120 s and payroll scan every 300 s came to ~29 B/day of its
33 B/day).

Since this change the hall sets ONE `setTimer` for the next moment a job can
change on its own — a lease expiring, a delivery a week old, a funded post a
month old, an unfunded post a week old, a failed job owed a refund — runs
`tend` then, and re-aims from what is left. No such job, no timer. Every
transition into one of those states re-arms it; an upgrade re-aims from the
jobs on record. Pinned by
`scripts/test_the_hall_ticks_only_while_a_job_can_change_on_its_own.py`.
Expected idle burn after the upgrade: ~1 B/day (storage), i.e. the 4.2 T
lasts years instead of a season.

The same two changes are owed to `cafresohq_state` (its `main.mo` is edited
by hand, not by the office): arm the wake timer only while wake is enabled,
arm the payroll scan only while a salary or a worker payout is pending (or
scan hourly at most), and answer public GETs (`/operator/config.json`,
`/health`, 404s) from the query `http_request` instead of upgrading every
request to a paid update — machine clients then read via
`…raw.icp0.io`, which skips certification, or via an agent query.

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

- `test_the_hall_runs_a_whole_job_on_a_real_replica.py` (#429) — **the
  first real-replica run**: dfx 0.24.3's local replica on a port of its own
  (`scripts/replica_harness/`, project-scoped), the hall as deployed, and a
  mock ICRC-1/ICRC-2 ledger with the real ledger's arithmetic (fees,
  allowance deduction, dedup window). Three fresh keys and a stranger walk
  the whole loop through `ic_agent.py` and the real `MarketWorker.tick`:
  refused allowance → funded → claimed → delivered → paid on the stamp, a
  rejected delivery ruled a 40/60 split, a cancel refund, a brain that
  throws, unlink. Every balance is asserted to the base unit. It found two
  launch-blockers on its first run: replicas answer with indefinite-length
  CBOR (ic_agent refused it — every container call would have died) and
  the shell's allowance was one fee short (§3). ~3 minutes cold; skipped
  under GitHub Actions unless `CAFRESOHQ_REPLICA=1`.

Not verified, and named so nobody mistakes silence for coverage:

- **No mainnet run yet.** The replica run uses a mock ledger with the ICP
  ledger's rules, not the ICP ledger itself. The alpha in §7b is the first
  real-token job.
- **Certificate signatures are not verified** by `ic_agent.py` (no BLS in
  pure Python yet). The client trusts TLS to the boundary node; every
  money decision is the canister's from `msg.caller`, so a spoofed reply
  can mislead a worker's log, never the escrow. Follow-up listed in §9.
- The shell changes are type-checked, not driven — the real ApprovalSheet
  and ICRC-2 approve run only in the deployed shell.

## 9. What is next (in order)

1. ~~Local-replica run of the whole loop~~ (done, #429), then a mainnet dry run with 0.01 ICP (§7b).
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
7. BANK as the hall's default token, with a discount against paying in any
   other ledger, and ckBAT as the native alternative. (Supersedes "$CF once
   the SNS token exists" from `strategy/04 §3`: the separate CafresoHQ token
   is retired in favour of one platform token — see the reserve/BANK notes.)
8. Quote a listing once and settle in any allowlisted ledger at an oracle
   rate, rather than a price per ledger. minegold's backend already runs a
   ckBAT/USD feed with a freshness gate; reuse it rather than a second
   oracle. This is what makes a BANK discount expressible.
9. A hall fee, kept in the job's own ledger, so jobs paid in ckBAT leave
   ckBAT in the treasury in proportion to real usage. Today the hall keeps
   nothing: the coworker receives exactly the price.
