---
title: 100M SNS Tokenomics v2 — Burn Schedule + Staking APY Analysis
type: project
status: planning
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/project
  - icp/project/tokenomics-100m-v2-burn-and-staking
  - icp/governance/sns
  - icp/sns/tokenomics
  - icp/sns/supply-dynamics
stack:
  - sns tokenomics
  - sns supply dynamics
repo: ""
supersedes: "[[tokenomics-100m-analysis]]"
---

# 100M SNS Tokenomics v2 — Burn Schedule + Staking APY Analysis

> Extends [[tokenomics-100m-analysis]] with a session-6 user proposal: on top of the 100M / 15 dev / 30 swap / 55 treasury split, add a scheduled burn of 5M tokens every 6 months (10M / year) from treasury and a staking APY curve of 8% decaying to 2% over 4 years. This worksheet evaluates whether the combined proposal is net-deflationary, how fast the treasury drains, and what the system looks like a decade in. **All figures below are first-order approximations with explicit assumptions; treat as order-of-magnitude.**

## Proposal summary

> **User proposal (evaluated literally):** SNS token, total supply 100,000,000. Initial distribution 15% developer (15M) / 30% decentralization swap (30M) / 55% treasury (55M). A scheduled burn of 5,000,000 tokens every 6 months (10,000,000 / year) is executed from the treasury. A staking APY of 8% initially, decaying to 2% after 4 years, is paid to stakers. Stated goal: net-deflationary supply.

## Key assumption — flagged prominently

**The 8% → 2% APY is interpreted as the SNS voting reward rate curve** (see [[sns-voting-rewards]]), configured via `initial_reward_rate_basis_points: 800` / `final_reward_rate_basis_points: 200` / `reward_rate_transition_duration_seconds ≈ 4 years`. Under this interpretation, **rewards are minted by SNS Governance** (newly-created tokens, inflationary — see [[sns-supply-dynamics]]) and **do not draw from treasury**. If the user instead intends "APY paid out of treasury", the math changes dramatically — see the secondary scenario below.

This note models the primary (mint) interpretation as the likely intent because:
1. The SNS Governance canister has a built-in reward minting mechanism parameterised by exactly these kinds of rates.
2. Funding rewards from treasury would require a new per-round treasury-transfer proposal or a dedicated disbursement canister — neither is a standard SNS pattern.
3. The "8% APY" language is common in CeFi where the counterparty funds yield; in SNS voting rewards the "APY" is really a mint rate and realised yield is diluted by the same mint.

## Scenario math — assumptions

The worksheet is a back-of-envelope forecast, not a simulation. Explicit assumptions:

- **Reward rate curve is linear** in time between 8% (t=0) and 2% (t=4y), then flat at 2% thereafter. The SNS `VotingRewardsParameters` struct is the authoritative source; the actual interpolation shape (linear vs. other) is an [[sns-voting-rewards]] open question. Under a non-linear curve the mid-curve numbers move by up to ~10-15% but the endpoints and qualitative shape are unchanged.
- **Reward is applied to *total supply*** (`annual_mint = stake_ratio × current_total_supply × reward_rate`). If the live implementation instead applies the rate to *total staked* rather than total supply, the mint is unchanged for the fraction of supply that is staked and the effective inflation rises by 1/stake_ratio — flag, but inflation in absolute terms is identical. If the rate is applied to total supply (as modelled), under-participation reduces realised mint; the model is the "full participation" upper bound.
- **Annual rate for year N** is taken as the midpoint of the year: r(N) = 8% − 1.5% × (N − 0.5) for N ∈ {1,2,3,4}, and r(N) = 2% for N ≥ 5. Values used below: **Y1 7.25%, Y2 5.75%, Y3 4.25%, Y4 2.75%, Y5+ 2.00%**.
- **Scheduled burn is 10M / year** (two 5M tranches), **bounded above by treasury balance**. Each burn requires a successful SNS proposal — the worksheet assumes every burn proposal is adopted. In practice this is aspirational (see [[sns-treasury-burns]]).
- **Stake ratio** is modelled at three flat levels for the whole window: **low 15%, base 30%, high 50%**. In practice stake ratio rises in early years (swap basket is locked) then evolves as dissolve delays mature; the flat model is a simplification.
- **No fee burns** are modelled. If the ledger or dapp-level fee-burns (see [[sns-fee-burn-patterns]]) are active, they add a small deflationary term proportional to usage; the worksheet ignores this conservatively.
- **No grants, disbursements, or ICP movements** are modelled. Treasury is assumed to fund *only* the scheduled burn in the primary scenario. This is unrealistic — in reality treasury must also fund cycles, grants, audits, operations — but it is the most-favourable accounting for the user's proposal. Real treasury runway is *shorter* than what is computed here.
- **Supply compounds at yearly granularity.** End-of-year supply becomes start-of-next-year supply. Rounds in practice are more frequent (daily), which slightly changes the number; immaterial at this resolution.

## Primary scenario — rewards minted (standard SNS)

**Formula per year N:**

```
supply_end(N)   = supply_start(N) + minted(N) − burn(N)
minted(N)       = stake_ratio × supply_start(N) × rate(N)
burn(N)         = min(10M, treasury_start(N))
treasury_end(N) = treasury_start(N) − burn(N)
```

### Base case — stake ratio = 30%

| Year | Supply start | Rate | Minted | Burn | Supply end | Treasury end | Net Δ supply |
|-----:|-------------:|-----:|-------:|-----:|-----------:|-------------:|-------------:|
| 1    | 100.000M     | 7.25% | 2.175M | 10M  | 92.175M    | 45M          | −7.825M      |
| 2    | 92.175M      | 5.75% | 1.590M | 10M  | 83.765M    | 35M          | −8.410M      |
| 3    | 83.765M      | 4.25% | 1.068M | 10M  | 74.833M    | 25M          | −8.932M      |
| 4    | 74.833M      | 2.75% | 0.617M | 10M  | 65.450M    | 15M          | −9.383M      |
| 5    | 65.450M      | 2.00% | 0.393M | 10M  | 55.843M    | 5M           | −9.607M      |
| 6    | 55.843M      | 2.00% | 0.335M | **5M (partial — treasury exhausts)** | 51.178M    | **0**        | −4.665M      |
| 7    | 51.178M      | 2.00% | 0.307M | 0    | 51.485M    | 0            | +0.307M      |
| 8    | 51.485M      | 2.00% | 0.309M | 0    | 51.794M    | 0            | +0.309M      |
| 9    | 51.794M      | 2.00% | 0.311M | 0    | 52.105M    | 0            | +0.311M      |
| 10   | 52.105M      | 2.00% | 0.313M | 0    | 52.418M    | 0            | +0.313M      |

**Base case — treasury exhausted mid-year 6** (full 55M burned by then). Net-deflationary years 1–6; mildly net-inflationary every year after (≈0.3M/y ≈ 0.6% of ~52M supply). Supply roughly stabilises around **52M** by year 10 under this scenario.

### Low case — stake ratio = 15%

| Year | Supply start | Rate | Minted | Burn | Supply end | Treasury end |
|-----:|-------------:|-----:|-------:|-----:|-----------:|-------------:|
| 1    | 100.000M     | 7.25% | 1.088M | 10M  | 91.088M    | 45M          |
| 2    | 91.088M      | 5.75% | 0.786M | 10M  | 81.873M    | 35M          |
| 3    | 81.873M      | 4.25% | 0.522M | 10M  | 72.395M    | 25M          |
| 4    | 72.395M      | 2.75% | 0.299M | 10M  | 62.694M    | 15M          |
| 5    | 62.694M      | 2.00% | 0.188M | 10M  | 52.882M    | 5M           |
| 6    | 52.882M      | 2.00% | 0.159M | **5M (partial — treasury exhausts)** | 48.041M    | **0**        |
| 7    | 48.041M      | 2.00% | 0.144M | 0    | 48.185M    | 0            |
| 8    | 48.185M      | 2.00% | 0.145M | 0    | 48.330M    | 0            |
| 9    | 48.330M      | 2.00% | 0.145M | 0    | 48.475M    | 0            |
| 10   | 48.475M      | 2.00% | 0.145M | 0    | 48.620M    | 0            |

**Low case — treasury exhausted mid-year 6.** Very similar exhaustion timing to base (the burn is rate-independent), slightly lower supply because less was minted. Stabilises around **49M** by year 10.

### High case — stake ratio = 50%

| Year | Supply start | Rate | Minted | Burn | Supply end | Treasury end |
|-----:|-------------:|-----:|-------:|-----:|-----------:|-------------:|
| 1    | 100.000M     | 7.25% | 3.625M | 10M  | 93.625M    | 45M          |
| 2    | 93.625M      | 5.75% | 2.692M | 10M  | 86.317M    | 35M          |
| 3    | 86.317M      | 4.25% | 1.834M | 10M  | 78.151M    | 25M          |
| 4    | 78.151M      | 2.75% | 1.074M | 10M  | 69.225M    | 15M          |
| 5    | 69.225M      | 2.00% | 0.692M | 10M  | 59.917M    | 5M           |
| 6    | 59.917M      | 2.00% | 0.599M | **5M (partial — treasury exhausts)** | 55.516M    | **0**        |
| 7    | 55.516M      | 2.00% | 0.555M | 0    | 56.071M    | 0            |
| 8    | 56.071M      | 2.00% | 0.561M | 0    | 56.632M    | 0            |
| 9    | 56.632M      | 2.00% | 0.566M | 0    | 57.198M    | 0            |
| 10   | 57.198M      | 2.00% | 0.572M | 0    | 57.770M    | 0            |

**High case — treasury exhausted mid-year 6.** Post-exhaustion mint term is larger (~0.55M/y ≈ 1% of supply), so supply grows more visibly after year 6. Stabilises-in-growth around **58M and climbing ≈1% / year** by year 10.

### Primary scenario — headline observations

- **Treasury exhausts in year 6 across all three stake ratios.** The burn schedule (10M/y) is much larger than the mint rate (0.1–3.6M/y depending on stake and year), so the burn leg is the dominant treasury drain and the exhaustion year is nearly independent of stake ratio.
- **The proposal is net-deflationary for years 1–5.** Every year in this window supply falls by roughly 7–10M (the burn dwarfs the minted rewards).
- **After year 6, the system is net-inflationary** — slowly (≈0.3–0.6M/y depending on stake), but with no deflation leg to offset it. The "deflationary" narrative is true for the first ~5 years and false thereafter.
- **Final-year-10 supply ranges ~49M (low) / ~52M (base) / ~58M (high)** — about half of genesis supply, with the treasury already empty for five years.

## Secondary scenario — rewards paid from treasury (non-standard)

**Formula per year N:**

```
rewards_paid(N)  = stake_ratio × supply_start(N) × rate(N)
burn(N)          = min(10M, treasury_start(N) − rewards_paid(N))   # rewards have priority
treasury_end(N)  = treasury_start(N) − rewards_paid(N) − burn(N)
supply_end(N)    = supply_start(N) − burn(N)                         # no mint → only burn affects supply
```

This assumes rewards are paid from treasury in SNS tokens (no ICP conversion), with reward-payment prioritised over scheduled burn if treasury cannot cover both. Rewards *do not* change total supply (they transfer from treasury to stakers); only the burn affects total supply.

### Base case — stake ratio = 30%

| Year | Supply start | Rate | Rewards paid | Burn | Supply end | Treasury end |
|-----:|-------------:|-----:|-------------:|-----:|-----------:|-------------:|
| 1    | 100.000M     | 7.25% | 2.175M      | 10M  | 90.000M    | 42.825M      |
| 2    | 90.000M      | 5.75% | 1.553M      | 10M  | 80.000M    | 31.272M      |
| 3    | 80.000M      | 4.25% | 1.020M      | 10M  | 70.000M    | 20.252M      |
| 4    | 70.000M      | 2.75% | 0.578M      | 10M  | 60.000M    | 9.674M       |
| 5    | 60.000M      | 2.00% | 0.360M      | **9.314M (partial)** | 50.686M | **0** |
| 6    | 50.686M      | 2.00% | 0 (no treasury) | 0 | 50.686M    | 0            |
| 7    | 50.686M      | 2.00% | 0            | 0    | 50.686M    | 0            |

**Base case treasury-funded — exhausted late in year 5.** Supply floor ~50.7M. After exhaustion, no rewards *and* no burn — the staking incentive collapses entirely, which is a much worse failure mode than the primary scenario because low participation can cascade into voting-quorum failures (see [[sns-operations]]).

### Low case — stake ratio = 15%

| Year | Supply start | Rate | Rewards paid | Burn | Supply end | Treasury end |
|-----:|-------------:|-----:|-------------:|-----:|-----------:|-------------:|
| 1    | 100.000M     | 7.25% | 1.088M      | 10M  | 90.000M    | 43.912M      |
| 2    | 90.000M      | 5.75% | 0.776M      | 10M  | 80.000M    | 33.136M      |
| 3    | 80.000M      | 4.25% | 0.510M      | 10M  | 70.000M    | 22.626M      |
| 4    | 70.000M      | 2.75% | 0.289M      | 10M  | 60.000M    | 12.338M      |
| 5    | 60.000M      | 2.00% | 0.180M      | 10M  | 50.000M    | 2.158M       |
| 6    | 50.000M      | 2.00% | 0.150M      | **2.008M (partial)** | 47.992M | **0** |

**Low case treasury-funded — exhausted early-to-mid year 6.** Supply floor ~48M.

### High case — stake ratio = 50%

| Year | Supply start | Rate | Rewards paid | Burn | Supply end | Treasury end |
|-----:|-------------:|-----:|-------------:|-----:|-----------:|-------------:|
| 1    | 100.000M     | 7.25% | 3.625M      | 10M  | 90.000M    | 41.375M      |
| 2    | 90.000M      | 5.75% | 2.588M      | 10M  | 80.000M    | 28.788M      |
| 3    | 80.000M      | 4.25% | 1.700M      | 10M  | 70.000M    | 17.088M      |
| 4    | 70.000M      | 2.75% | 0.963M      | 10M  | 60.000M    | 6.125M       |
| 5    | 60.000M      | 2.00% | 0.600M      | **5.525M (partial)** | 54.475M | **0** |
| 6    | 54.475M      | 2.00% | 0 (no treasury) | 0 | 54.475M    | 0            |

**High case treasury-funded — exhausted mid-year 5.** Supply floor ~54.5M.

### Secondary scenario — headline observations

- **Treasury exhausts 6–12 months earlier across the board** because it funds both the burn and the reward payments from the same pool.
- **Supply reduction is smaller** (no mint → only burn reduces supply → supply falls ~50M across the window rather than ~45M), but that is cold comfort: the treasury is gone, and with it both the reward incentive and any further burns.
- **Post-exhaustion failure is harsher.** Rewards stop entirely (unlike the minted scenario where rewards continue at 2%), so neurons lose their staking incentive, voting participation likely collapses, and the DAO faces quorum risk on the next contested vote.
- **Higher stake ratios drain treasury faster** (they draw more per year in rewards), so in this model "good news (high participation)" is actually "bad news (faster depletion)". This is an inverted incentive structure and a red flag for the treasury-funded interpretation.

## Key findings (ranked)

1. **Primary risk — treasury exhaustion at ~year 5.5 under the burn plan alone.** The 10M/y scheduled burn drains the 55M treasury in about 5.5 years regardless of stake ratio. This exhaustion is the dominant feature of the proposal's economics — every downstream concern (grants, audits, ops, incident response, liquidity provision) loses its funding source at the same time.
2. **Post-exhaustion the system is net-inflationary** (primary scenario: +0.3 to +0.6M/y) unless a fee-burn mechanism or some other revenue-linked burn picks up where the scheduled burn leaves off. The "deflationary" narrative is accurate for years 1–5 and false thereafter; teams should not market it as a permanent property.
3. **The DAO has limited runway for grants, audits, incident response after ~year 4.** By end of year 4 treasury holds 15M in the primary scenario — roughly 27% of what it started with, and enough for one more year of the scheduled burn and effectively nothing else. Before that point, any non-burn treasury spending (real grants, real audits, real ops) accelerates exhaustion well beyond the 5.5-year mark. **The worksheet's 5.5 years is an upper bound**; the realistic runway is shorter.
4. **Each scheduled burn requires an SNS proposal — the schedule is aspirational, not enforced.** Every 5M tranche is a governance act that can be voted down or delayed. A committed deflationary schedule is not achievable through scheduled-proposal flow alone; it requires either a dedicated scheduled-burn canister (see [[sns-treasury-burns]]) or a protocol-level burn like ledger-fee burn or dapp-revenue burn (see [[sns-fee-burn-patterns]]).
5. **8% starting reward rate is aggressive** relative to qualitative benchmarks. The NNS historical rate was ~10% decaying to ~5%; several SNSs have launched in the 2–6% initial range. An 8% starting rate will invite forum scrutiny ("why so high?"); the justification should be modelled in terms of alignment-incentive value vs. inflation cost and published, not asserted (reference [[sns-launch-benchmarks]]).
6. **Stake ratio has surprisingly little effect on the primary scenario's exhaustion year** because the burn schedule dominates. It has a much larger effect on *long-run inflation* (year 7+) and on *secondary scenario runway*. If the user's intent is treasury-funded rewards, stake-ratio sensitivity flips sign and becomes a runway-killing factor.
7. **Circulating supply dynamics are more complex than total supply.** As tokens leave treasury (via burns or disbursements) and swap-basket neurons dissolve, circulating supply rises even while total supply falls. The narrative of a "shrinking token" can mask a growing-float-available-for-sale reality. See [[sns-supply-dynamics]].

## Alternative proposals to compare

- **Fee-burn / revenue-burn instead of fixed schedule.** Burns track usage rather than calendar (see [[sns-fee-burn-patterns]]). Treasury is preserved indefinitely as a war chest. Deflationary pressure scales with adoption — which is also a risk if adoption is low, but for a productive dapp it is the design most aligned with its own success. Binance BNB's shift from quarterly burns to an on-chain auto-burn formula is a precedent.
- **Lower initial APY (e.g. 4–5%) to reduce inflation pressure.** Cuts the mint term by 30–50% in year 1 with minimal governance downside if the dissolve-delay voting-power incentive is strong. The community-review conversation shifts from "why 8%?" to "why not higher?", which is an easier one to answer.
- **Preserve treasury as a war chest; explicit treasury-use policy** splitting treasury intake and outflow into named purposes (grants %, ops %, burn %, reserve %). Replaces an ambient "we'll spend it on stuff" posture with a published policy the DAO commits to. Example: 40% grants / 30% ops and cycles / 20% burn / 10% strategic reserve.
- **Hybrid: scheduled burn while usage ramps, then fade to fee-burn.** Use scheduled burns in years 1–2 to establish the deflationary narrative while fee revenue is too small to burn meaningfully; publish a sunset criterion (e.g. once annual fee-burn exceeds 5M, scheduled burns taper). Gives marketing story without 10-year treasury commitment.
- **Reduce burn-tranche size to preserve runway.** 2M / 6 months (4M/y) gives 55M / 4M ≈ 13.75 years of runway for the burn schedule alone — still a meaningful narrative, dramatically longer horizon. Combined with modest fee-burns this could produce a sustainable net-deflation.
- **Burn address alternative to minting-account burn.** Not recommended — see [[sns-treasury-burns]] gotcha on total_supply accounting. Noted here only to flag why the canonical minting-account burn is the right implementation.

## Recommendations — what to decide before committing

1. **Confirm rewards funding source.** Is the 8%→2% curve the SNS voting reward rate (minted, inflationary — primary scenario) or an out-of-treasury staking payout (non-standard — secondary scenario)? This single answer changes the math fundamentally; everything downstream depends on it.
2. **Re-plan the treasury envelope to survive 10+ years**, not 5.5. Either reduce burn-tranche size (2–3M / 6 months rather than 5M), or introduce a fee-burn mechanism that replaces the scheduled burn as the dominant deflation driver, or both. A DAO whose treasury is empty at year 6 is a DAO with no ability to respond to incidents, fund audits, or adapt to changing conditions.
3. **Commit to vesting and dissolve-delay for the dev 15%** — carried forward from [[tokenomics-100m-analysis]] and still unresolved. A new burn/staking layer does nothing for the dev-bucket concentration risk; it is still the single largest governance red flag in the allocation.
4. **Decide between programmatic burns, fee-burns, and hybrid.** Programmatic (scheduled) burns are marketing-friendly but governance-fragile and treasury-draining. Fee-burns are economically aligned but require usage to produce deflation. A hybrid is often the right answer; pick one and publish the decision rule.
5. **Publish explicit treasury policy.** Name the percentages: X% grants, Y% ops and cycles, Z% burn, W% strategic reserve. Revisit annually via proposal. Without a policy, the 55M share is either "too large" (if nothing happens) or "depleted by opportunism" (if proposals drip it out unstructured). A policy converts the community review from "is 55% too much?" to "is this policy sensible?".
6. **Define what triggers the APY step-down.** Calendar (the implicit assumption — linear over 4 years per the SNS config) is easy but decoupled from maturity milestones. Alternative: step-down on TVL, participation-rate, or time-since-launch milestones, configurable by SNS proposal later. Calendar is the conservative default; the decision should be made explicitly.
7. **Model the minting-basis assumption.** Whether rewards are applied to *total supply* or to *total staked* is a material variable not yet confirmed against the Governance source. The worksheet uses supply; verify before using the numbers for any public commitment.
8. **Plan for the post-exhaustion scenario.** Year-7-onwards is net-inflationary in the primary scenario with no alternative burn source. Either accept that the deflation narrative has a 5–6-year shelf life, or build the fee-burn / alternative burn source now so it can ramp as the scheduled burn sunsets.

## Open questions

- **SNS `VotingRewardsParameters` interpolation shape** — linear vs. alternative. Verify against `rs/sns/governance` source before treating the mid-curve worksheet numbers as precise. → [[sns-voting-rewards]]
- **Reward rate basis** — applied to total supply vs. total staked. Changes the inflation in absolute terms. → [[sns-voting-rewards]]
- **Confirmation that SNS rewards are minted (not treasury-funded) in the current Governance release.** The design strongly implies mint; a direct confirmation from a live SNS's ledger history would close the loop. → [[sns-voting-rewards]], [[sns-supply-dynamics]]
- **Canonical proposal type name for treasury burns** — historically `TransferSnsTreasuryFunds`, verify current. → [[sns-treasury-burns]]
- **Whether the SNS Ledger configuration burns transaction fees** (routes to minting account) or accumulates them. Changes whether the worksheet's "no fee burns" assumption is truly conservative. → [[sns-fee-burn-patterns]]
- **Minimum burn threshold** on the SNS Ledger — `BadBurn` error below a certain amount; verify that 5M-scale tranches are well above the floor. → [[sns-treasury-burns]]
- **Any project-specific benchmark numbers for 8%→2% reward curves** — no SNS has been verified to use this exact schedule in this vault; add to the benchmarks table if a peer can be found. → [[sns-launch-benchmarks]]
- **Realistic stake-ratio trajectory** over 10 years (not flat) — initial swap baskets are fully staked at launch but dissolve over their dissolve-delay schedule; steady-state is lower than year-1. A dynamic stake-ratio model would refine the mint term materially.
- **ICP-side treasury** (swap-raised ICP) not modelled here — treasury holds both SNS tokens and ICP, and the cycle-conversion / grant programme typically denominates in ICP. A full model would track both.

## See also

- [[tokenomics-100m-analysis]]
- [[sns-supply-dynamics]]
- [[sns-voting-rewards]]
- [[sns-treasury-burns]]
- [[sns-fee-burn-patterns]]
- [[sns-tokenomics]]
- [[sns-launch-benchmarks]]
- [[sns-operations]]
- [[sns-neurons-and-voting]]
