---
tags: [research, tokenomics, sns, voting-rewards]
---

# Maturity Modulation and Reward Conversion Mechanics

## Core Mechanism

Maturity modulation is a dynamic mechanism that controls how voting rewards (earned as "maturity") convert into actual tokens. This introduces uncertainty and supply control into the reward distribution process.

## How It Works

**Voting Reward Distribution:**
- Rewards distributed on regular basis (NNS: daily)
- Pro-rata allocation based on:
  - Voting power when proposals were made
  - Number of proposals voted on
  - Neuron participation rate

**Voting Power Calculation:**
- Base stake (ICP locked in neuron)
- Staked maturity (previously earned, not yet converted)
- Dissolve delay bonus (up to 2x for 8 years)
- Age bonus (rewards long-term holding)

Example: 60 ICP stake + 40 staked maturity = 100 combined stake. With 8-year dissolve delay (2x bonus) and 2-year age, voting power is significantly amplified.

## Maturity Modulation Function

**Purpose:** Introduces controlled uncertainty in token creation from maturity, preventing predictable inflation.

**Key Benefits:**
1. Dynamic supply control based on network conditions
2. Prevents gaming of reward timing
3. Allows network to respond to economic conditions
4. Reduces predictable sell pressure from reward claims

## Incentive Schedule Design

**Early Adoption Incentives:**
- NNS started with 10% of total supply distributed annually at genesis
- Front-loaded rewards encourage early participation and security
- Declining reward schedule over time as network matures

**SNS Considerations:**
- Can customize reward pools in SNS init file
- Must balance early incentives vs. long-term sustainability
- Related to [[token-supply-inflation-deflation-mechanisms]] and [[voting-rewards-and-incentive-design]]

## Best Practices for SNS Configuration

**Reward Pool Sizing:**
- Consider total supply allocation for voting rewards
- Model inflation impact over 5-10 year horizon
- Balance governance participation incentives with token value preservation

**Maturity Options:**
- Staking maturity: compounds voting power without inflating supply
- Spawning neurons: converts to liquid tokens, realizes inflation
- Modulation factor: adds uncertainty layer to prevent predictable extraction

**Participation Thresholds:**
- Reward only active voters to encourage governance engagement
- Pro-rata distribution ensures large and small holders are proportionally rewarded
- See [[neuron-staking-voting-power-mechanics]] for voting power calculation details

## Treasury Impact

Voting reward pools come from either:
1. Pre-allocated treasury tokens (see [[sns-treasury-and-initial-token-distribution]])
2. Inflationary emission (see [[token-supply-inflation-deflation-mechanisms]])

DAO must decide: front-load rewards (faster distribution, earlier dilution) vs. conservative schedule (slower growth, longer runway).

## Common Pitfalls

- Over-generous early rewards → rapid dilution → price collapse
- Under-rewarding governance → low participation → security risks
- Fixed/predictable rewards → timing games and mercenary capital
- No modulation → predictable sell pressure at reward claim times
