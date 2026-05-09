---
title: 100M SNS Tokenomics — Proposed Split Analysis
type: project
status: planning
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/project
  - icp/project/tokenomics-100m-analysis
  - icp/governance/sns
  - icp/sns/tokenomics
stack:
  - sns tokenomics
repo: ""
---

# 100M SNS Tokenomics — Proposed Split Analysis

> Analysis of a user-proposed three-way SNS initial distribution (100M total supply: 15% dev / 30% swap / 55% treasury). Evaluated against the qualitative patterns in [[sns-launch-benchmarks]] and the knob model in [[sns-tokenomics]]. **All historical comparisons are qualitative** — exact per-project figures must be verified against dashboard.internetcomputer.org/sns and each project's published proposal payload before being quoted as confirmed.

## Summary

- **Total supply:** 100,000,000 tokens (fixed at launch, minted via `sns_init.yaml`).
- **Developer / team:** 15% — 15,000,000 tokens.
- **Decentralization swap:** 30% — 30,000,000 tokens.
- **Treasury (SNS Governance):** 55% — 55,000,000 tokens.
- **Airdrops:** not specified in the proposal → treat as 0% for now, but flag as a gap.
- **Neurons' Fund participation:** not specified → flag as a gap (NF is an additional ICP source to the swap, not a separate supply bucket; see [[sns-tokenomics]]).
- **Vesting / dissolve-delay schedule for the dev bucket:** not specified → flag as the single largest governance risk in the proposal.

## Benchmarking

Against the qualitative landscape in [[sns-launch-benchmarks]] (verify specific numeric rows against the dashboard before citing them as confirmed):

| Bucket     | Proposal | Observed band (qualitative, per forum/dashboard discussion) | Position                        |
|------------|---------:|:------------------------------------------------------------|:---------------------------------|
| Swap       | **30%**  | Commonly 20–50%                                              | Low end of the decentralization band |
| Dev/team   | **15%**  | Commonly 10–25%                                              | Middle-to-low; reasonable *if vested* |
| Treasury   | **55%**  | Commonly 30–50%; 55%+ uncommon                               | High end — above typical         |
| Airdrops   | 0% (unspecified) | Sometimes 1–10% as a separate bucket                | Below typical; no community-alignment bucket declared |
| NF match   | Not addressed | Usually present, often material relative to public raise | Gap — must be decided explicitly |

**Headline takeaway:** the proposal sits at the *high end* of treasury share and the *low end* of swap share, which together amount to a concentration of economic and voting weight in one place (SNS Governance's own subaccount) that the community can only govern via treasury-disbursement proposals. That concentration is not illegitimate — SNS Governance is, definitionally, the DAO — but it is unusual and needs a public defence.

Concrete anchor figures from specific historical launches have **not been transcribed** into this document because they could not be verified through the research pass. Before freezing the split, populate the table in [[sns-launch-benchmarks]] with verified numbers from `dashboard.internetcomputer.org/sns/<project>` for at least 3–4 reference launches whose shape the team wants to position against.

## Risks / flags

### 1. Treasury share at 55% is above typical

- **Why it's a risk.** Historically most SNSs landed 30–50% treasury. 55% signals either "we have a lot of planned on-chain spending" or "we under-sized the swap and overflowed into treasury". The community will want to know which.
- **What mitigates it.** A *published* treasury-use roadmap: what the 55M tokens will fund, on what cadence, for how long. Cycles for canisters, grants to contributors, liquidity provision, marketing, bounties, partner integrations — each with rough sizing.
- **What does not mitigate it.** Generic language like "long-term development and ecosystem growth". That's what every treasury says; it's not a roadmap.
- **Governance note.** Treasury tokens don't vote — they sit in SNS Governance subaccounts. But every treasury spend is itself a proposal that concentrated holders can decide. Size the treasury assuming the DAO will eventually have contentious votes over how to spend it.

### 2. Swap share at 30% is at the low end of the decentralization floor

- **Why it's a risk.** A 30% swap is at the lower edge of the commonly-seen band. Whether that is *enough* decentralization depends almost entirely on two variables this proposal does not yet specify: (a) the **minimum raise** (`min_icp_e8s`-style), and (b) the **Neurons' Fund match**.
  - If the minimum raise is large and NF participates materially, the 30% swap bucket ends up distributed across a broad set of participants and NF-backed NNS neurons — decentralization is fine.
  - If the minimum raise is small and NF doesn't participate, the 30% can close with a small number of large participants — decentralization is performative, not real.
- **What mitigates it.** Deciding `(min_raise, max_raise)` and per-participant caps together, modeled against expected public interest and an explicit NF match assumption. Making the community-readable tokenomics post include the "under what raise profile does this still count as decentralized" table.
- **What does not mitigate it.** Arguing "30% is within the band" without naming the raise parameters. The band only justifies the bucket size *when* the rest of the swap config is reasonable.

### 3. 15% dev bucket is only safe with meaningful vesting and dissolve delay

- **Why it's a risk.** 15M tokens sitting in dev-controlled principals with short or unclear dissolve delays is a textbook dump-risk allocation. Day-one voting power from the dev bucket also potentially dominates the basket distribution from the swap (which is split across many participants with relatively short initial dissolve delays), meaning the founders can outvote the rest of the DAO on launch day even if everyone else agrees against them.
- **What mitigates it.**
  - **Vesting** over multiple years — each tranche becomes transferable only after a cliff + schedule.
  - **Dissolve delays** set long (multi-year) on the dev neurons, with clear rationale for each founder's allocation.
  - **Publishing the schedule** explicitly in the forum tokenomics post — one table per named dev principal with amount, vesting schedule, initial dissolve delay, and any other conditions.
- **What does not mitigate it.** "Vesting TBD", "standard vesting", or vesting without dissolve delay. Vesting only restricts transferability; dissolve delay restricts both liquidity and voting-power concentration reduction. Both knobs matter (see [[sns-tokenomics]]).

### 4. The proposal does not mention Neurons' Fund, airdrops, or vesting

- **Neurons' Fund.** Not a supply bucket — an ICP contributor to the swap — but materially changes who holds the 30% swap bucket at finalisation. **Decide opt-in vs. opt-out and model both scenarios.** Most recent launches have had NF participation; default to assuming it will be present unless explicitly suppressed.
- **Airdrops.** No airdrop bucket is named, which is a defensible choice but an explicit one. If the team wants to reward early users, testflight participants, partner DAOs, or community members, the decision of *where* those tokens come from (dev / treasury / new named airdrop bucket) and *with what dissolve-delay* needs to be in the YAML, not added later.
- **Vesting / dissolve-delay schedules.** The single largest information gap in the proposal. Without a schedule, the 15% dev bucket cannot be reasoned about. (Repeat of risk #3, because it is the single most-important missing piece.)

### 5. Initial voting-power distribution is unmodeled

- The headline split doesn't tell you who votes with what weight on day one. Voting power falls out of the combination of bucket size *and* each bucket's dissolve-delay schedule. Before freezing the split, the team should:
  - Model day-one voting power under at least two scenarios (short swap-basket delays vs. long; short dev delays vs. long).
  - Publish the model. Community review on tokenomics is mostly about whether the *resulting voting distribution* is tolerable, not about the headline bucket percentages.

### 6. Upgrade, cycle, and treasury-spending cadence are out of scope here but load-bearing

- None of these are tokenomic risks per se, but all of them interact with the treasury size. A 55M-token treasury implies the team is planning to fund operations from that pool for a long horizon; the operations plan (see [[sns-operations]]) should exist and be publishable before the launch proposal.

## Recommendations

Concrete asks the user should answer before freezing this allocation. Each is blocking in the sense that a thoughtful forum reviewer will ask about it; better to answer proactively than reactively.

1. **Publish a treasury-use roadmap.** How the 55M tokens will be deployed over what time horizon, split across cycle top-ups, grants, liquidity, operations, etc. Without this, the 55% share reads as either "too large" or "we didn't know what else to do with them". A published plan changes the conversation from "is 55% too much?" to "is this roadmap sensible?".
2. **Specify the dev-bucket vesting + dissolve-delay schedule, per named principal.** A table with columns (principal, amount, vesting cliff + schedule, initial dissolve delay). This is the single most important artefact the dev bucket needs; without it, 15% cannot be evaluated.
3. **Decide and publish the Neurons' Fund stance.** Opt in (and what maximum match is acceptable) or opt out (and why). Model how each scenario changes day-one voting-power distribution in the swap basket.
4. **Specify the swap parameters, not just the swap share.** Minimum raise, maximum raise, per-participant min/max, swap duration, geographic restrictions. The 30% swap bucket's meaning depends on all of these.
5. **Decide airdrops explicitly.** Either "no airdrop bucket, by choice" with rationale, or a named airdrop bucket carved from one of the three — with recipient principals, amounts, and dissolve delays.
6. **Model and publish day-one voting-power distribution** under at least two dissolve-delay scenarios. Close the loop from "allocation knobs" to "governance effect" (see [[sns-tokenomics]]), because that loop is what the community ultimately votes on.

A smaller, optional recommendation:

7. **Populate [[sns-launch-benchmarks]] with at least 3–4 verified reference launches** (numbers pulled from dashboard.internetcomputer.org and each project's forum thread) before the launch thread is published, so the tokenomics post can position this split against real peers.

## Open questions

- Is there a specific application / dapp this tokenomics is intended for, or is it being designed independently? That determines how realistic the treasury roadmap needs to be.
- What is the target `(min, max)` ICP raise, in absolute terms? The 30% swap share is defensible or undefensible depending on this number.
- What vesting schedule does the dev team have in mind, and how long a dissolve delay?
- Is Neurons' Fund participation desired? If yes, at what maximum match?
- Is there an existing community (early users, testflight participants, partner DAOs) that would normally expect an airdrop at launch?
- Is the team planning on-chain cycle-management or treasury-driven spending as the canonical operations model, and how does that affect treasury sizing?
- Are there any time pressures (fundraising runway, ecosystem event timing) that should shape the launch schedule?

## TL;DR — what to decide before freezing the split

The three-way 15 / 30 / 55 headline is defensible *at the extremes* but not *on the merits*, because every knob that actually controls governance (vesting, dissolve delays, minimum raise, NF match, per-participant caps) has not been specified. In order of priority, the user should decide:

1. **Dev-bucket vesting + dissolve-delay schedule.** Single largest risk.
2. **Treasury-use roadmap.** Justifies the 55% share or doesn't.
3. **Swap parameters (min raise, max raise, per-participant caps) + NF stance.** Converts the 30% headline into real decentralization.

Everything else is downstream of these three.

## See also

- [[sns-tokenomics]]
- [[sns-init-config]]
- [[sns-launch-benchmarks]]
- [[sns-launch]]
- [[sns-launch-readiness]]
- [[sns-operations]]
- [[sns-neurons-and-voting]]
