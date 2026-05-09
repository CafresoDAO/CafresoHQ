---
tags: [research, tokenomics, sns, governance, rewards]
created: 2026-04-29
---

# Voting Rewards and Incentive Design

## Overview
SNS voting rewards are a critical mechanism for sustaining governance participation and aligning stakeholder incentives with long-term DAO success. Each SNS can configure reward parameters independently to match their community needs.

## Core Reward Mechanics

**Reward Pool Distribution**
- Rewards paid from a time-based pool (e.g., daily or weekly)
- Each neuron receives pro-rata share based on voting power used
- Voting power = staked tokens × dissolve delay multiplier × age bonus
- Creates natural incentive: lower participation → higher per-voter rewards

**Participation Incentives**
- Rewards distributed only to neurons that actively vote
- Encourages consistent engagement rather than passive holding
- Long-term commitment rewarded through dissolve delay bonuses (up to 2x)
- Age bonuses reward neurons that have been staked longer (up to 1.25x)

## Design Considerations

**Balancing Reward Rates**
- Too high: inflationary pressure, token devaluation
- Too low: insufficient participation, governance attacks more feasible
- Sweet spot varies by DAO stage and treasury size

**Maturity Modulation**
- Some SNS implementations use maturity instead of direct token rewards
- Maturity can be converted to tokens or used to increase voting power
- Reduces immediate sell pressure from rewards

**Strategic Implications**
- Rewards align voters with ecosystem growth (paid in native tokens)
- Higher rewards for longer lock-ups create stability
- Consistent participation patterns emerge from predictable incentives
- Resistant to short-term governance attacks

## Links to Related Concepts
- [[neuron-staking-voting-power-mechanics]] - how voting power multipliers work
- [[governance-voting-parameters]] - configurable parameters for voting rules
- [[token-supply-inflation-deflation-mechanisms]] - reward impact on token supply

## Key Takeaway
Well-designed voting rewards create a flywheel: participation → rewards → long-term commitment → aligned governance → DAO success → token value → more participation. The SNS init file reward parameters should balance immediate participation incentives with long-term tokenomics sustainability.