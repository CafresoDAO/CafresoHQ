---
tags: [research, sns, governance, delegation]
---

# Vote Delegation and Following Mechanisms

## Overview
SNS neurons can delegate voting power through "following" - allowing token holders to transfer voting rights to trusted neurons rather than voting directly on every proposal. This is critical for participation rates and governance health.

## Core Mechanism
- Neuron holders choose to follow other neurons on specific topics/proposal types
- Followers automatically inherit the vote of the neurons they follow
- Enables governance participation without requiring constant attention or domain expertise
- Configured via NNS dapp for each SNS DAO

## Research Findings

### Participation Patterns (Okutan et al., 2025)
Empirical analysis of 14 IC SNS DAOs found:
- Following mechanisms significantly impact participation rates
- Users lack time/knowledge to vote on all decisions
- Delegation enables sustained governance activity
- Rewards are proportional to activity and commitment, incentivizing delegation participation

### Fairness and Concentration Risks
Recent research on token delegation highlights key concerns:
- **Voting power concentration**: Delegation can centralize power in popular delegates
- **Trust dependencies**: Followers must trust delegates' decision-making alignment
- **Transparency requirements**: Delegation patterns should be visible to community

## Design Considerations for SNS Init

### Enable Flexible Following
- Support topic-based following (not just blanket delegation)
- Allow neuron holders to follow different experts for different proposal categories
- Ensure following relationships are easily modifiable

### Monitor Concentration
- Track delegation concentration metrics
- Consider governance alerts if too much power concentrates in few neurons
- Balance between efficiency (delegation) and decentralization

### Incentive Alignment
- Voting rewards should encourage informed delegation choices
- Consider reputation/track record visibility for potential delegates
- Reward both direct voters AND followers to maintain participation

## Common Pitfalls
- **Over-centralization**: Too much delegation to small set of neurons undermines DAO goals
- **Unclear delegation UX**: Complex following mechanisms reduce participation
- **No delegation accountability**: Delegates should be monitorable and replaceable

## Links to Other Tokenomics Elements
- Relates to [[neuron-staking-voting-power-mechanics]] - staking determines votable power
- Impacts [[governance-voting-parameters]] - delegation affects quorum and participation thresholds
- Connected to [[voting-rewards-and-incentive-design]] - rewards must incentivize healthy delegation patterns

## Recommendations
1. Design SNS init to encourage topic-specific following, not blanket delegation
2. Make delegation transparent and easily reversible
3. Monitor concentration metrics post-launch
4. Consider voting reward structures that incentivize informed following choices
5. Document trusted neurons/delegates for community reference
