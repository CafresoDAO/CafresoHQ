---
tags: [research, treasury, risk-management]
---

# Treasury Asset Diversification Strategies

DAOs face unique treasury management challenges balancing growth potential against operational stability. Asset diversification is critical for long-term survival.

## Core Diversification Principles

**Two-Year Runway Rule**: Industry best practice suggests maintaining **at least 2 years of operating expenses in stable, liquid assets** (primarily stablecoins). This provides breathing room during market downturns and ensures continued operations regardless of token price volatility.

**Asset Class Balance**:
- Stablecoins (USDC, DAI, USDT): 40-60% for operational expenses and stability
- Native governance token: 20-40% for alignment and treasury growth
- Blue-chip crypto (BTC, ETH): 10-30% for long-term value preservation
- DeFi yield positions: 5-15% for additional income generation

## Risk Management Approaches

**Volatility Mitigation**: DAOs must actively manage exposure to volatile assets. During bull markets, protocols should convert excess volatile holdings into stablecoins to lock in gains. The inverse (converting stables to volatile assets) should only occur with explicit governance approval and clear risk parameters.

**Capital Preservation vs. Growth**: Treasuries typically split into two buckets:
1. **Preservation bucket**: Stable assets covering 24+ months runway, never touched for speculation
2. **Growth bucket**: Remainder allocated for diversification, yield farming, strategic investments

## Implementation Mechanisms

**Tokenized Diversification**: Protocols like Set Protocol allow DAOs to allocate capital into managed TokenSets—algorithm-driven or professionally managed baskets. This provides instant diversification without requiring in-house trading expertise.

**Governance Guardrails**: Successful DAOs establish clear policies defining:
- Maximum allocation percentages per asset class
- Approval thresholds for rebalancing (e.g., >$100K moves require full governance vote)
- Risk limits (VaR, drawdown limits, concentration caps)
- Conversion triggers (automatic stablecoin conversion at certain profit thresholds)

## Common Pitfalls

**Over-complication**: Spreading treasury too thin across dozens of assets increases operational overhead and gas costs without meaningful risk reduction. Stick to 5-8 core positions maximum.

**Native Token Concentration**: Many DAOs fail by holding 80%+ of treasury in their own governance token. This creates death spirals—treasury value crashes exactly when the DAO needs funds most (during protocol decline).

**Inadequate Liquidity**: Allocating too much capital into locked farming positions or illiquid investments prevents rapid response to operational needs or market opportunities.

## Relationship to SNS Configuration

For SNS DAOs, treasury diversification happens post-decentralization swap. Initial treasury composition is typically 100% native SNS tokens. The init file should therefore include:

- **Developer/ecosystem fund sizing** ([[developer-fund-and-ecosystem-grants]]) to ensure sufficient stable runway
- **Voting thresholds** ([[governance-voting-parameters]]) that prevent reckless treasury reallocation
- **Treasury management proposal types** with appropriate approval quorums

The SNS init file cannot directly allocate diversified assets, but it establishes the governance framework determining how quickly and safely the DAO can diversify post-launch.

## Key Metrics to Monitor

- **Runway months**: Total stable assets / monthly burn rate
- **Volatility exposure**: % of treasury in non-stablecoin assets
- **Liquidity ratio**: % of treasury accessible within 7 days
- **Concentration risk**: Largest single asset position as % of total

Links: [[treasury-management-strategies]], [[token-supply-inflation-deflation-mechanisms]], [[revenue-sharing-fee-distribution-mechanisms]]