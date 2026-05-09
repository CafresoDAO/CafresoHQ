---
tags: [research, sns, tokenomics, neurons-fund]
---

# Neurons' Fund Matched Funding Mechanics

The Neurons' Fund (NF) is a critical bootstrapping mechanism for SNS DAOs on the Internet Computer, providing matched funding to decentralization swaps.

## How Matched Funding Works

The NF uses a matching function **f(x)** where:
- **x** = direct participation amount from community
- **f(x)** = corresponding NF contribution

The function has **three distinct phases** designed to be continuous, ensuring smooth scaling between participation levels.

**Key constraint**: In the matched funding framework, minimum and maximum funding targets refer **only to direct participation**, not including the NF contribution.

## Best Practices

### Genesis Voting Power Distribution

**Critical principle**: Swap participants should have the **majority of voting power at genesis**.

If developers + seed investors hold the majority together:
- Must clearly articulate why these parties are **independent**
- Otherwise creates centralization risk that undermines DAO credibility

### Strategic Implications

The matched funding mechanism:
- **Amplifies community participation** without diluting it
- Provides credibility signal (NNS governance backing the project)
- Reduces capital requirements for project teams
- Aligns NNS stakeholders with SNS success

Related to [[initial-token-allocation-and-swap-parameters]] and [[sns-dao-launch-case-studies-success-metrics]].

## Treasury Impact

NF participation affects:
- Total treasury size at genesis
- Initial liquidity depth (see [[liquidity-provision-and-dex-strategies]])
- Runway for [[developer-fund-and-ecosystem-grants]]