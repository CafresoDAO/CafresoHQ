---
tags: [research, sns, governance, staking]
---

# Neuron Staking & Voting Power Mechanics

## Core Voting Power Formula
Voting power in SNS DAOs is **proportional to three factors**:
1. **Token quantity staked** in the neuron
2. **Dissolve delay** (lock-up period)
3. **Neuron age** (time since creation)

## Maximum Voting Power Strategy
To achieve maximum voting power:
- Lock neuron for **8 years** (max dissolve delay)
- Leave locked for **4 additional years** (age bonus accumulates)
- **Regularly vote** or set following relationships (participation multiplier)

This creates a 12-year horizon for maximum influence, aligning governance power with long-term commitment.

## Reward Eligibility & Distribution
- **Minimum dissolve delay**: 6 months to earn voting rewards
- **Daily reward pool**: `Total_Supply × R(t) / 365.25`
- **Participation incentive**: Lower overall participation → higher individual rewards

This inverse relationship naturally incentivizes staking and governance participation during periods of apathy.

## Design Implications for SNS Init File
Related to [[sns-treasury-and-initial-token-distribution]], staking parameters should:
- Set **minimum dissolve delay** high enough to prevent short-term speculation (6-12 months typical)
- Configure **age bonus multipliers** to reward patient capital
- Balance reward rates to ensure treasury sustainability while incentivizing meaningful stake

**Key risk**: If dissolve delays are too short or rewards too generous, treasury depletes before DAO achieves sustainability.

---
*Source: ICP governance docs, NNS staking mechanics*