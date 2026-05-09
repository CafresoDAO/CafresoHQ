---
title: SNS Supply Dynamics
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-supply-dynamics
  - icp/governance/sns
  - icp/sns/tokenomics
  - icp/sns/supply-dynamics
source:
  - https://github.com/dfinity/ICRC-1/blob/main/standards/ICRC-1/README.md
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://github.com/dfinity/ic/tree/master/rs/sns/governance
related:
  - "[[sns-tokenomics]]"
  - "[[sns-voting-rewards]]"
  - "[[sns-treasury-burns]]"
  - "[[sns-fee-burn-patterns]]"
  - "[[sns-canisters]]"
difficulty: intermediate
open_questions:
  - Whether SNS voting rewards are strictly minted (newly created tokens) in all current Governance releases, or whether any configuration draws rewards from a pre-funded pool. Code inspection of `rs/sns/governance` showed a `RewardEvent` record with `distributed_e8s_equivalent` but did not explicitly document mint-vs-treasury origin; the NNS precedent and SNS documentation strongly imply mint, but this should be verified against a live SNS ledger before citation.
  - Whether SNS Governance exposes a reliable API for querying *circulating* supply (total minus locked-in-neurons minus treasury) separately from total_supply, or whether circulating must be derived by the caller.
  - Whether there are any protocol-level burns (e.g. a portion of the rejection fee for lost proposals) beyond ledger transaction fees and governance-initiated burns.
---

# SNS Supply Dynamics

> How the total supply of an SNS token changes over time — through minting (voting rewards, swap-finalisation mints), burning (ledger fees, explicit governance-driven burns), and treasury movements (which are *not* supply changes, only custody changes).

## Why it exists

The initial allocation in `sns_init.yaml` (see [[sns-tokenomics]]) fixes the token distribution at genesis; it does *not* fix the token supply forever. Voting rewards, if configured, mint new tokens every reward round. Ledger fees and any explicit treasury-burn proposals reduce supply. Treasury disbursements and grants *move* tokens between accounts but do not change supply at all — a frequent point of confusion when modelling "deflationary" or "inflationary" schedules. A proposal to "burn 5M tokens per year and pay 8% staking APY" cannot be evaluated without separating those three flows, because the apparent net is dominated by whichever flow is largest.

## How it works

### Three flows that change (or don't change) supply

1. **Minting — increases total supply.**
   - **Genesis mint.** At launch, the SNS Ledger mints total-supply-worth of tokens into the initial distribution accounts (dev neurons, treasury subaccount, swap-basket neurons). The `sns_init.yaml` total-supply figure is the pre-minted ceiling; the Ledger's `icrc1_total_supply` begins at this value immediately post-launch.
   - **Voting rewards mint (if configured).** See [[sns-voting-rewards]]. If the SNS is configured with non-zero reward rates, SNS Governance mints new tokens at each reward round and distributes them to neurons that voted. These new tokens add to total supply. Open question: verify minting (vs. treasury-funded) is the actual mechanism in the current Governance release.
   - **Any other protocol-level mint.** None are standard. An SNS proposal could *theoretically* instruct the Ledger to mint (via a privileged Ledger method if exposed), but this is not a normal operation and would itself be a major proposal.

2. **Burning — decreases total supply.**
   - **Ledger transaction fees.** The ICRC-1 ledger charges a per-transfer fee; see [[sns-fee-burn-patterns]]. Whether that fee is *burned* (sent to the minting account) or *accumulated* (sent to a fee-collection account) is a ledger-configuration choice. The canonical SNS Ledger configuration should be verified per project.
   - **Explicit treasury burns.** See [[sns-treasury-burns]]. The DAO proposes a treasury transfer to the minting account (or to a burn address whose controller cannot spend from it). On adoption, SNS Root / Governance executes the transfer; the tokens are removed from circulation and total_supply decreases.
   - **Any ad-hoc burn.** A neuron holder can unilaterally send their own tokens to the minting account — this is a voluntary burn by that holder. It is not a DAO action and is uncommon.

3. **Treasury movements — do NOT change total supply.**
   - Treasury-to-grant, treasury-to-LP, treasury-to-cycle-conversion, treasury-to-dev — all of these move tokens from SNS Governance's subaccount to another account. Total supply is unchanged. *Circulating* supply (as commonly defined: supply not held by the DAO itself) does increase, because tokens moving out of the DAO's hands become tradeable.

### ICRC-1 accounting primitives

- **`icrc1_total_supply`** returns the total number of tokens across all accounts *except* the minting account. Tokens sitting in the minting account do not count toward supply. (Verified from the ICRC-1 README.)
- **The minting account is a unique account** that can create new tokens and acts as the receiver of burnt tokens. Transfers *from* the minting account are mints (no fee); transfers *to* the minting account are burns (no fee, subject to a minimum burn amount).
- **Fees** on regular transfers are collected by the minting account (per the ICRC-1 spec). Whether a specific ledger's collected fees end up *burned* vs. held somewhere else depends on the ledger implementation's fee-handling; verify for the SNS Ledger release the project is on.

### Circulating vs. total supply

- **Total supply** = output of `icrc1_total_supply`. Changes only via mint/burn.
- **Circulating supply** is not a ledger primitive — it is a derived quantity. Common definitions:
  - *Total* minus *treasury-held* minus *locked-in-neurons* (not-yet-dissolved).
  - *Total* minus *treasury-held* (looser — counts staked tokens as circulating since the neuron owner eventually controls them).
  - The exchange-facing / CoinGecko-style definition typically excludes treasury and may or may not exclude staked tokens; projects should state which they use.
- A "deflationary" narrative usually implies *total* supply falling; a "supply squeeze" narrative usually implies *circulating* supply tightening. These are not the same and should not be conflated.

### Net supply equation

For any window of time:

```
Δ total_supply = (voting rewards minted)
                + (any other mint)
                − (fees burned, if the ledger burns fees)
                − (explicit treasury burns)
                − (voluntary user burns)
```

Whether the net is positive (inflationary) or negative (deflationary) depends entirely on which term is largest. A fixed-schedule burn (e.g. 10M tokens/year) is bounded above by the treasury balance and runs out; voting rewards scale with (total_supply × reward_rate × stake_ratio) and do *not* run out until the reward rate hits zero. Small, late-stage projects often find the inflation side dominates long after launch even with an aggressive burn schedule — see the worksheet in [[tokenomics-100m-v2-burn-and-staking]].

## Example

```text
Hypothetical one-year window, SNS with 100M total supply at t=0:

  Voting rewards (minted):
    assume stake_ratio = 30%, reward_rate = 8% year-1
    minted ≈ 100M × 0.30 × 0.08 = 2.4M tokens/year

  Treasury burns (scheduled):
    10M tokens/year (5M every 6 months) — BOUNDED by treasury balance

  Fee burns:
    depends on ledger volume × per-tx fee × whether fees are burned

  Net year-1 Δ supply:
    + 2.4M  (minted rewards)
    − 10M   (scheduled burn, assuming treasury still has ≥10M)
    = −7.6M (net deflationary in year 1)

  But: treasury drains 10M/year → depletes in N years.
  After depletion, the burn leg stops; only mint leg continues.
  System is net-inflationary for every year after depletion,
  unless a fee-burn mechanism picks up the slack.
```

## Gotchas

- **Treasury movement is not a supply event.** Counting a treasury-to-grant transfer as "deflationary" is a common mis-read. The tokens are still out there — they just changed hands.
- **"Burn" is an ICRC-1 operation, not a concept you can hand-wave.** If there is no transfer to the minting account (or to a provably unspendable address), no supply has been burned. A "treasury burn" proposal must execute an actual on-ledger burn transaction.
- **`icrc1_total_supply` updates in real time.** Any consumer that caches it needs to re-read after every mint/burn round. Dashboards that show a stale number are common.
- **Reward minting compounds.** Rewards are minted against *current* total supply, not against the original-at-genesis supply. A 2% rate on a 100M supply that grew 20% over the last decade is a larger mint than a 2% rate on the same headline number at t=0.
- **Fee-burn is a ledger choice.** Not every ICRC-1 ledger burns its fees; some retain them in a fee-collection account. If a tokenomic model assumes fee-burns, the ledger config must actually burn fees — confirm against the specific SNS Ledger release.
- **Voluntary burns are possible but not countable.** Any holder can send tokens to the minting account; this reduces supply but is not something the DAO can schedule or rely on.

## See also

- [[sns-tokenomics]]
- [[sns-voting-rewards]]
- [[sns-treasury-burns]]
- [[sns-fee-burn-patterns]]
- [[sns-canisters]]
- [[sns-operations]]
- [[tokenomics-100m-v2-burn-and-staking]]
