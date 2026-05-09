---
title: SNS Voting Rewards
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-voting-rewards
  - icp/governance/sns
  - icp/sns/tokenomics
  - icp/sns/supply-dynamics
source:
  - https://github.com/dfinity/ic/blob/master/rs/sns/init/src/lib.rs
  - https://github.com/dfinity/ic/tree/master/rs/sns/governance
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
related:
  - "[[sns-tokenomics]]"
  - "[[sns-init-config]]"
  - "[[sns-neurons-and-voting]]"
  - "[[sns-supply-dynamics]]"
difficulty: intermediate
open_questions:
  - Whether rewards are minted (new tokens added to supply) or drawn from a pre-funded pool, across all current SNS Governance releases. Strongly implied to be minted (matching the NNS design), but not explicitly confirmed in the code review for this note. Verify against a live SNS's `icrc1_total_supply` growth vs. a `RewardEvent`-distributed amount before citation.
  - Whether the reward-rate curve is strictly linear in time between `initial_reward_rate_basis_points` and `final_reward_rate_basis_points` over `reward_rate_transition_duration_seconds`, or whether it follows a different (e.g. quadratic) interpolation. Worksheets in this vault assume linear interpolation; verify before treating any resulting number as precise.
  - Current distribution formula within a reward round — whether strictly proportional to voting power of neurons that voted on each proposal, or whether there is any smoothing / minimum-participation gate.
---

# SNS Voting Rewards

> The periodic (per-round) distribution of tokens to SNS neurons as compensation for voting, parameterised by a decaying reward-rate curve configured in `sns_init.yaml`.

## Why it exists

Neurons only have voting power if they are locked (dissolve delay set); locked tokens have an opportunity cost (the holder cannot sell). Voting rewards are the offsetting economic incentive — they pay neuron holders to stay locked and to vote, preserving governance quorum and voting participation. The rate curve — high early, low later — front-loads alignment during the period when the DAO is most fragile (post-swap, no track record, high attacker opportunity) and tapers off as the DAO matures. Without voting rewards, a newly launched SNS tends to hit quorum failures as participants dissolve to sell; with voting rewards, neurons have a direct reason to keep their dissolve delay up and to vote actively.

## How it works

### Configuration fields (verified from `rs/sns/init` in dfinity/ic)

The three canonical fields that configure the curve, as accepted by `SnsInitPayload` and assembled into a `VotingRewardsParameters` struct:

- **`initial_reward_rate_basis_points`** — the reward rate at t = launch, in basis points (1 bp = 0.01%). E.g. 800 bp = 8.00%.
- **`final_reward_rate_basis_points`** — the reward rate after the transition period, in basis points. E.g. 200 bp = 2.00%.
- **`reward_rate_transition_duration_seconds`** — the length of the transition from initial to final, in seconds. E.g. 4 years ≈ 126 230 400 s (4 × 365.25 × 86 400).

Between t=0 and t=`reward_rate_transition_duration_seconds`, the rate interpolates from initial to final; after the transition duration, the rate holds at `final_reward_rate_basis_points` indefinitely. **The exact interpolation shape (linear vs. quadratic vs. other) is an open question** — the `VotingRewardsParameters` struct is the authoritative source and its interpolation is defined there; treat as linear for back-of-envelope work and flag any sensitive result.

Related parameters that interact with the reward calculation (qualitative; verify field names per release):

- **Reward round length** — how often rewards are calculated and distributed. Typically a fixed cadence (e.g. daily).
- **Voting-power computation** — a function of stake, dissolve delay, and age bonus (see [[sns-neurons-and-voting]]). Rewards are proportional to voting power of *neurons that voted in the round*.

### The inflation effect (what rewards do to total supply)

Under the mint-rewards model (strongly implied but not confirmed here — see open_questions):

- At each reward round, SNS Governance computes the total reward to distribute for that round. A first-order approximation is:
  ```
  round_reward ≈ current_total_supply × reward_rate_at_now × (round_length / year_length)
  ```
  — scaled by whatever the exact formula uses (the spec may apply this to *total staked* rather than *total supply*; verify).
- The reward is minted and distributed to neurons that voted, proportional to their voting power in the round.
- Neurons that did not vote receive nothing for that round — this is what gives the system its "vote or lose rewards" incentive.
- Because rewards only mint *when distributed*, the effective annual inflation depends on **stake ratio** (fraction of supply locked in neurons), **voting-participation rate** (fraction of those neurons that actually vote in a given round), and the **reward rate** at that time. A low-participation DAO inflates less than a high-participation one at the same rate, because undistributed rewards for that round are simply not minted.

### Configuring an 8% → 2% over 4-year curve (the user's proposal)

Given the three fields above, the configuration is:

```yaml
# illustrative — verify exact field path in the current sns_init.yaml schema against
# https://github.com/dfinity/ic/tree/master/rs/sns/cli and the current schema release
initial_reward_rate_basis_points: 800      # 8.00%
final_reward_rate_basis_points:   200      # 2.00%
reward_rate_transition_duration_seconds: 126230400  # ≈ 4 × 365.25 days
```

Under an assumed linear interpolation:

```
r(t) = 8% + (2% − 8%) × min(t, 4y) / 4y
     = 8% − 1.5% × min(t, 4y) / 1y

  t=0     → 8.0%
  t=1y    → 6.5%
  t=2y    → 5.0%
  t=3y    → 3.5%
  t=4y    → 2.0%
  t>4y    → 2.0% flat
```

**Caveat.** This curve is qualitative until the interpolation is confirmed. If the implementation interpolates quadratically or by some other shape, the mid-curve numbers move; the endpoints (8% at t=0, 2% at t ≥ 4y) are stable regardless.

### Benchmarks

- **NNS voting rewards** (the precedent SNS inherits from) started at ~10% and decay to ~5% over 8 years, with rewards strictly minted and distributed to NNS neurons that voted, proportional to voting power. Numbers are from NNS documentation; verify against the current NNS parameter set on dashboard.internetcomputer.org for any quantitative citation.
- **Individual SNS launches** — the initial/final rate and transition duration vary per project. Populate the "Reward rate curve" column in [[sns-launch-benchmarks]] from each project's `sns_init.yaml` or proposal payload before citing.

## Example

```text
Rough annual inflation under the 8%→2% curve, 100M supply, 30% stake ratio, 100% participation:

  Year 1:   r ≈ 8.0% → mint ≈ 100M × 30% × 8.0%  = 2.40M tokens
  Year 2:   r ≈ 6.5% → mint ≈ 100M × 30% × 6.5%  = 1.95M tokens
  Year 3:   r ≈ 5.0% → mint ≈ 100M × 30% × 5.0%  = 1.50M tokens
  Year 4:   r ≈ 3.5% → mint ≈ 100M × 30% × 3.5%  = 1.05M tokens
  Year 5+:  r = 2.0% → mint ≈ 100M × 30% × 2.0%  ≈ 0.60M tokens/year

  (These approximations ignore compounding on the growing supply and assume
   reward_rate applies to total supply rather than to total staked — the
   latter would reduce these figures by up to ~3x depending on stake ratio.
   Treat as order-of-magnitude only.)
```

## Gotchas

- **"8% staking APY" is ambiguous.** In the SNS model, rewards are funded by minting, not by a yield-generating asset. A neuron's realised APY depends on its voting power relative to the pool, its participation rate, and the dilution of its unstaked value by the same minting that pays the reward. It is not the same as a CeFi "8% savings rate".
- **Rewards require voting.** A locked neuron that does not vote for a round earns nothing that round. The 8% headline assumes the neuron is voting (directly or via a followee).
- **Rate applies to what exactly — supply or stake?** The scaling basis (total supply vs. total staked) is an implementation detail that changes the inflation number materially. Verify before modelling.
- **`final_reward_rate_basis_points` can be 0.** A project can elect for voting rewards to end entirely after the transition duration. Many projects keep a small non-zero floor to maintain baseline participation incentive.
- **Rewards are per-round, not continuous.** Rounds have a discrete cadence; a neuron that dissolves mid-round may forfeit the current-round reward depending on timing. This is usually negligible but is a real bookkeeping detail.
- **Rewards decay the neuron holder's effective share over time if they do not keep up.** A neuron with a fixed stake loses voting share each round to neurons whose rewards compound into their own stake. The 8% rate at launch rewards early, compounding stakers disproportionately.
- **`initial_reward_rate_basis_points: 800` is aggressive.** 8% starting is at the high end of the historical SNS range; it is not wrong, but it invites community scrutiny ("why so high?"). Teams have landed in the 2–6% initial range as well; see [[sns-launch-benchmarks]].

## See also

- [[sns-tokenomics]]
- [[sns-init-config]]
- [[sns-neurons-and-voting]]
- [[sns-supply-dynamics]]
- [[sns-launch-benchmarks]]
- [[tokenomics-100m-v2-burn-and-staking]]
