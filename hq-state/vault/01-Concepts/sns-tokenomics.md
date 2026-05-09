---
title: SNS Tokenomics
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-tokenomics
  - icp/governance/sns
  - icp/sns/tokenomics
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://internetcomputer.org/sns
related:
  - "[[sns]]"
  - "[[sns-init-config]]"
  - "[[sns-neurons-and-voting]]"
  - "[[sns-launch-readiness]]"
  - "[[sns-launch-benchmarks]]"
  - "[[nns]]"
difficulty: intermediate
open_questions:
  - Current Neurons' Fund matching rules and maximum match — the policy has been revised by NNS proposal more than once; verify per launch date.
  - Whether there is a minimum-decentralization floor enforced by SNS-W (i.e., a minimum % of initial supply that must go through the swap), or whether this is purely convention.
  - Current rules around airdrops as a distribution bucket — `sns_init.yaml` expresses them as pre-configured principals receiving neurons, but the canonical mechanism evolves.
---

# SNS Tokenomics

> The set of "knobs" in `sns_init.yaml` that, together, decide who owns how much of the SNS token at genesis, how locked up each holder is, and therefore how governance weight is distributed on day one of the DAO.

## Why it exists

Every knob here compounds: a generous dev allocation isn't a problem if it's vested for four years with long dissolve delays, and a 30% swap share isn't dilutive if the minimum raise is sized to keep the swap meaningful. Launching without a model of how these parameters interact is the single most common cause of SNSs that technically succeed their swap but functionally fail their decentralization — a whale-dominated day-one voting distribution, a dev team with dump-ready tokens, or a treasury with no stated spending plan. This note enumerates the knobs qualitatively; the exact YAML field names evolve and live in the template (see [[sns-init-config]]).

## How it works

### The knobs

- **Total supply.** Fixed at launch; minted into the three buckets below plus (optionally) airdrops. Cannot be inflated post-launch without an SNS proposal changing the ledger — not a normal operation.
- **Initial Token Distribution — the three canonical buckets:**
  1. **Swap share.** Tokens offered to the public during the decentralization swap in exchange for ICP. This is the primary decentralization lever: a larger swap share spreads day-one voting power wider.
  2. **Developer / team share.** Minted as a set of *neurons* owned by named principals (founders, core contributors, early employees), with per-neuron vesting and dissolve-delay schedules. Without vesting this is a dump-risk allocation; with long vesting and long dissolve delays it is a long-term alignment instrument.
  3. **Treasury share.** Held by SNS Governance itself, spendable only by successful treasury-transfer proposals. Funds ongoing operations (cycles, grants, liquidity, marketing, bounties) after launch.
- **Neurons' Fund participation.** The NNS-governed Neurons' Fund can contribute ICP to the swap on behalf of NNS neurons that opted in, and receive SNS tokens proportionally. This adds to the raise without inflating the swap *share* — the swap's SNS-token allocation is fixed; NF participation changes who holds it and the ICP pot size, not the SNS-token split.
- **Airdrops / pre-allocated neurons.** Some teams pre-allocate neurons to named community members, early users, or partner projects at genesis. In `sns_init.yaml` these appear as specific principals receiving neurons outside the swap basket; economically they come out of one of the three buckets, depending on how the team accounts for them.
- **Vesting & dissolve delays.** Per-neuron schedules on the developer and airdrop neurons. Two related but distinct concepts: **vesting** is when tokens become transferable; **dissolve delay** is how long between "start dissolving" and "tokens become liquid" (also the primary input to voting power — see [[sns-neurons-and-voting]]). Long dissolve delays both constrain dumps *and* give the holder more voting weight — a legitimate trade-off.
- **Swap parameters.** Minimum ICP (`min_icp_e8s`-style — abort below this), maximum ICP (close swap on hit), per-participant minimum and maximum, swap duration, geographic restrictions. These don't change the *share* split but they change who can buy, how much each buyer gets, and whether the swap finalises at all.
- **Initial voting power.** Not a separate knob — falls out of the above. Day-one voting power = (each bucket × each bucket's dissolve-delay schedule). A dev bucket with 8-year dissolve delays carries far more voting weight per token than swap-basket neurons with staggered short delays.

### Governance effect of each knob

- **Higher swap share** → wider day-one holder distribution → less founder/treasury dominance → slower but more legitimate governance.
- **Higher treasury share** → more runway for DAO-led operations → also more ability to fund activities without returning to investors → also more concentration of voting power in the Governance canister's own subaccounts (which do not vote, but whose spending is a single focal point of political capture).
- **Higher dev share** → stronger founder incentives → but also dump risk and founder-dominance risk unless vested and dissolve-delayed.
- **Short dissolve delays on the swap basket** → participants can exit quickly → healthier price discovery → but thinner voting quorums.
- **Long dissolve delays on the dev basket** → founders have to govern the thing they built, not flip it → but they also concentrate voting power for years.
- **Neurons' Fund** participation → larger ICP pot raised → also introduces *NNS neurons* as a proxy stakeholder in the SNS → NF holders tend to be long-horizon but are not necessarily end-users of the dapp.
- **Airdrops** → community alignment, targeted distribution → but each airdropped neuron is a voting-power unit that didn't pay ICP for its stake; abused, this skews governance without economic cost.

## Example

```text
Illustrative three-way split (not a recommendation — just naming the shape):

  Total supply := T

  Developer bucket      ──> D%  of T, minted into N_dev neurons
                              vested v years, dissolve delay d_dev
  Swap bucket           ──> S%  of T, minted at swap finalisation
                              into basket of k neurons per participant,
                              dissolve delays (d_1, ..., d_k)
  Treasury bucket       ──> R%  of T, held by SNS Governance subaccount
  (Airdrop, optional)   ──> A%  of T, minted into named-principal neurons

  D + S + R + A == 100

  Neurons' Fund match (optional) adds ICP to the raise pot, receives
  tokens out of the S% bucket proportional to its contribution.
```

## Gotchas

- **The three-way split is a simplification.** `sns_init.yaml` separately expresses dev neurons (often multiple principals), airdrop neurons, and Neurons' Fund participation; a "55% treasury / 30% swap / 15% dev" headline usually hides several smaller buckets.
- **"Swap share" is not "float at launch."** Swap-basket neurons are all staked — none of the swap tokens are liquid at finalisation. Float appears as individual participants dissolve their baskets.
- **Neurons' Fund is not a separate *share* — it's a co-buyer of the swap share.** Confusing these produces models that over- or under-count decentralization.
- **Vesting ≠ dissolve delay.** A dev neuron can be vested (transferable to the dev) but still have a long dissolve delay (non-spendable). Both matter; neither substitutes for the other.
- **Treasury is not a slush fund** — every outflow requires a treasury proposal that can be voted down. A large treasury share is a large *governable* pool, not a large *founder-accessible* pool.
- **Historical benchmarks drift.** Early SNS launches, mid-era launches, and recent launches cluster at very different split points. See [[sns-launch-benchmarks]] and always verify the specific project's published numbers on dashboard.internetcomputer.org rather than quoting from memory.

## See also

- [[sns]]
- [[sns-init-config]]
- [[sns-neurons-and-voting]]
- [[sns-launch]]
- [[sns-launch-readiness]]
- [[sns-launch-benchmarks]]
- [[nns]]
