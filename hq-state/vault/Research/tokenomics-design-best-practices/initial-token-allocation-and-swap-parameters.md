---
tags: [research, sns, tokenomics, initial-distribution]
---

# Initial Token Allocation and Swap Parameters

## Core Allocation Blocks

SNS DAOs should structure initial token allocation across four main blocks:

1. **DAO Treasury** — tokens controlled by governance for community bounties, user rewards, ecosystem development
2. **Decentralization Swap** — public distribution via initial swap (ICP → governance tokens)
3. **Seed Funders** — early investors who funded development pre-launch
4. **Development Team** — founding/core team allocation with vesting

## SNS Fairness Requirement

The Internet Computer **enforces at protocol level** that:
> Decentralization swap allocation ≥ (Seed funders + Development team)

This prevents scenarios where insiders hold majority control before the DAO launches. The swap must distribute *at least* as many tokens to the public as are granted to all private parties combined.

## Fair Launch vs Pre-Sale Models

**Fair launch** (no insider pre-allocation):
- All tokens distributed via swap, liquidity mining, or airdrops
- Maximum decentralization from day one
- Examples: Yearn, SushiSwap (early DeFi)
- Trade-off: no early funding for development

**Balanced hybrid** (SNS model):
- Treasury + swap ≥ 50% of supply goes to DAO/community
- Seed + team ≤ 50%, with [[token-vesting-schedules-design|vesting]] to prevent dumps
- Enforced fairness ratio ensures no "VC capture"
- Funds development while maintaining decentralization

## Swap Parameter Design

Key levers in the SNS decentralization swap:

**Participation caps:**
- Max ICP per participant (anti-whale)
- Min ICP threshold (exclude dust)
- Total swap target range (min/max raise)

**Token price discovery:**
- Fixed price vs Dutch auction vs bonding curve
- SNS uses neuron-based allocation (participants receive staked neurons, not liquid tokens)
- Immediate [[governance-voting-parameters|voting power]] for swap participants

**Post-swap liquidity:**
- Reserve treasury allocation for [[liquidity-provision-and-dex-strategies|DEX liquidity]]
- Coordinate with swap timing to prevent immediate price crash
- Governance-controlled liquidity deployment

## Distribution Strategy Best Practices

1. **Gradual treasury deployment** — don't dump full treasury allocation immediately; release via governance proposals over time
2. **Multisig → DAO transition** — start with multisig control of critical functions, migrate to full DAO governance after community stabilizes
3. **Transparent allocation** — publish full distribution breakdown before swap (builds trust)
4. **Anti-sybil for airdrops** — if using airdrops alongside swap, implement proof-of-humanity or reputation gates
5. **Liquidity mining alignment** — if rewarding LPs, ensure rewards vest or require minimum lock periods

## Common Pitfalls

- **Insufficient swap allocation** → insider dominance, governance attacks
- **No vesting for team/seed** → immediate sell pressure, price collapse
- **Oversize treasury** → lazy governance, no urgency for revenue
- **Undersize treasury** → DAO can't fund development, stagnates
- **Fixed swap price too high** → fails to reach minimum, launch aborted
- **Fixed swap price too low** → immediate pump-and-dump

## Integration Points

- Link swap allocation to [[voting-rewards-and-incentive-design|reward budget]]
- Coordinate treasury size with [[treasury-management-strategies|spending policies]]
- Ensure team vesting aligns with [[dissolve-delay-parameter-design|neuron lock periods]]
- Plan [[token-supply-inflation-deflation-mechanisms|inflation schedule]] relative to initial supply
