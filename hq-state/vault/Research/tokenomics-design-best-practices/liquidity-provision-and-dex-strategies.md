---
tags: [research, tokenomics, liquidity, dex]
---

# Liquidity Provision and DEX Strategies

## Overview
Post-launch token liquidity is critical for price discovery, trading efficiency, and avoiding manipulation. DAOs need strategies to bootstrap and maintain healthy secondary markets.

## Liquidity Bootstrapping Methods

### Liquidity Mining Programs
- **Mechanism**: Reward liquidity providers (LPs) with native tokens for depositing into AMM pools
- **Early-phase incentives**: Higher rewards during launch to attract initial capital
- **Proportional distribution**: Rewards scale with LP's share of total pool liquidity
- **Objective**: Bootstrap deep liquidity quickly, reduce slippage for early traders

### Automated Market Maker (AMM) Pool Design
- **Reserve ratios**: Pools maintain token pairs (e.g., SNS_token/ICP) with algorithmic pricing
- **Impermanent loss consideration**: LPs face risk if token price moves significantly vs. paired asset
- **Multiple pool strategy**: Diversify across different pairs (stablecoin, native ecosystem token, ETH/BTC equivalents)

### Liquidity Bootstrapping Pools (LBPs)
- **Dynamic weight adjustment**: Pool weights shift over time to create controlled price discovery
- **Front-running resistance**: Discourages bots, favors genuine price-finding
- **Use case**: Fair initial token distribution with built-in market-making

## Treasury Liquidity Management

### Protocol-Owned Liquidity (POL)
- **Treasury as LP**: DAO treasury deposits into its own AMM pools
- **Benefits**: 
  - Permanent liquidity base (no mercenary capital flight)
  - Earns trading fees for treasury
  - Greater price stability
- **Tradeoffs**: Locks capital that could fund development

### Incentive Program Design
- **Time-bound campaigns**: Avoid perpetual inflation from liquidity rewards
- **Tiered rewards**: Higher APY for longer lockup commitments
- **Pool targeting**: Direct incentives to most strategic pairs (e.g., SNS/ICP over SNS/meme_token)

## Common Pitfalls
1. **Insufficient initial liquidity**: Leads to high slippage, poor user experience, whale manipulation
2. **Over-reliance on mercenary capital**: LPs farm-and-dump when incentives dry up
3. **Single DEX concentration**: Platform risk if that DEX is compromised or loses market share
4. **Ignoring impermanent loss**: LPs exit if IL exceeds rewards, draining pools

## SNS-Specific Considerations
- **ICP ecosystem**: Primary liquidity should pair with ICP (native ecosystem token)
- **DEX options**: ICPSwap, Sonic, other ICP-native AMMs
- **Timing**: Coordinate liquidity deployment with decentralization swap completion
- **Treasury allocation**: [[sns-treasury-and-initial-token-distribution]] should reserve 5-15% for initial LP seeding

## Links
- Related: [[token-utility-and-value-capture]] (utility drives organic trading volume)
- Related: [[treasury-management-strategies]] (POL as treasury diversification)
- Related: [[dao-failures-tokenomics-mistakes]] (liquidity crises case studies)