# The Hiring Hall, Phase 4: a fee, and hiring across offices

Written 2026-11-21 by Claude (Opus 5.5), for `docs/AGENT_ECONOMY_ON_ICP.md` Phase 4.
Status: **design.** `cafresohq_market` (`rliqj-…`) is live on mainnet, so every change here is a
reviewed PR, a replica run, and an upgrade Anthony approves.

## 1. A hall fee that funds the economy

Today the hall keeps nothing: the coworker receives exactly the price. A small fee, kept in the
job's own ledger and sent to the CF treasury, lets the economy pay for its own canisters in
proportion to real use (AGENT_MARKETPLACE.md §9.9).

**Rules**
- `feeBps` (basis points), set by the plan admin, **capped at 1,000 (10%)** in code, default 0.
  Once the CF DAO controls the hall, it changes only through a passed proposal.
- **The fee is fixed when a job is posted** (`job.hallFeeBps`), so a change never touches jobs
  already funded, and the boss sees the split before signing.
- **Taken only from what the worker earns:** on acceptance, and on the worker's share of a split
  ruling. Refunds and cancellations carry no fee.
- **The fee pays its own ledger fee.** Escrow today holds `price + ledgerFee` for one move. A fee
  needs a second move, so the treasury receives `hallFee − ledgerFee`. If `hallFee ≤ 2 × ledgerFee`,
  the fee is waived for that job and the worker is paid as today. Nobody pays an extra fee, and the
  escrow arithmetic and the 100-fee price floor still hold.
- **Exactly once, as today:** two payout rows with their own keys (`pay:<id>` and `fee:<id>`),
  state written before each await, the same `created_at_time` on retry. The worker is paid first;
  a failed fee move never blocks the worker's money.
- `treasury` (an ICRC-1 account), set by the plan admin. On mainnet it is `cf_treasury`.
- The résumé and `marketStats` show earned and fee separately.

## 2. Hiring across offices

Any principal can already be a boss: `postJob` and `fundJob` are keyed by caller. What's missing is
that an outside agent can't *find* the hall, and an agent spending its owner's money can't fund a job.

- **Discovery.** The hall answers `getApiDoc()` in plain text, and the hall, `cf_agents`,
  `cafresohq_mandates` and `cf_factory` are listed in `/.well-known/ic-architecture` once they are
  deployed, so ICP MCP finds them.
- **Listings ↔ directory.** A listing may name its worker's `cf_agents` principal. The agent's card
  then shows `"hire": { "hall": "<canister>", "listing": <id> }`, and the hall checks
  `cf_agents.verify(worker)` before taking a job for it.
- **Funding from a mandate.** A job can be funded by a plain transfer into its escrow subaccount
  (which is what `cafresohq_mandates.spend(purpose = "hall-job")` does), followed by
  `confirmDeposit(id)`. The hall checks the escrow subaccount's balance covers `price + fee` and
  moves the job to funded. Only the boss can call it, and only once, so an agent can hire another
  agent inside the limits its owner signed.
- **Track records.** When a job is accepted, the hall writes a confirmed record for the worker in
  `cf_agents`, with the boss as counterparty, so a hall job builds the same two-sided track record.

## 3. A hardening item found while reading the hall

`fundJob` and `retryPayout` treat a ledger `#TooOld` as "the earlier attempt never landed" and try
again with a fresh `created_at_time`. `#TooOld` only says the stamp is outside the 24-hour dedup
window; it doesn't say whether the first attempt landed.

- **Payouts are bounded.** They come from the job's own escrow subaccount, which holds only
  `price + fee`. If the first payout landed, a fresh one fails with insufficient funds, so nobody is
  paid twice. The status then reads "failed: insufficient funds" for a payout that succeeded.
- **Deposits** could be taken twice from a boss, but only if the first one landed and the job
  wasn't marked funded, which needs a trap after the await.

**Fix:** on `#TooOld`, read the escrow subaccount's balance before trying again. If a payout's money
is already gone, the payout landed: mark it paid, with the block unknown. If a deposit's money is
already there, the deposit landed: mark the job funded. `cafresohq_mandates` already treats
`#TooOld` as unknown for this reason.

## 4. Build order
1. The hardening fix (§3), with a replica test that ages a stamp past the window on the mock ledger.
2. The fee (§1), with replica tests for acceptance, split rulings, waiver, and a failed fee move.
3. `confirmDeposit` and the listing ↔ directory link (§2), with a mandate funding a job end to end.
4. The `ic-architecture` entries, once Anthony has deployed the new canisters.
