---
tags: [research, governance, security]
---

# Governance Attack Vectors and Defense Mechanisms

## Major Attack Vectors

**Token Concentration (Whale Problem)**
- Large token holders can dominate voting outcomes
- Flash loan attacks: temporary token acquisition to pass malicious proposals
- Soft capture: whales coordinating behind multisigs to control decisions
- Vote delegation layering: concentration of power through opaque intermediaries

**Low Participation Vulnerabilities**
- Weak voter turnout allows small coordinated groups to pass critical changes
- Apathy attacks: malicious proposals submitted when engagement is historically low
- Quorum manipulation: timing proposals around predictable low-activity periods

**Delegation Abuse**
- Delegation systems can concentrate influence in bad-faith intermediaries
- Delegated voters acting against delegators' interests
- Opaque decision-making by delegate cartels

**Backdoor Mechanisms**
- Hidden admin roles or emergency functions exploitable by insiders
- Privileged upgrade paths bypassing normal governance
- Parameter changes that effectively override prior governance decisions

## Defense Strategies

**Voting Power Constraints**
- Quadratic voting: reduces whale influence by making additional votes increasingly expensive (cost = votes²)
- Vote-escrowed tokens (veTokens): longer lock periods earn more voting power, aligning with long-term health
- Conviction voting: voting power grows over time proposal stays active, favoring patient consensus
- Maximum individual voting power caps (e.g., no single neuron >5% of total voting power)

**Participation Requirements**
- Minimum quorum thresholds (e.g., 3-10% of total voting power must participate)
- Super-majority requirements for critical changes (e.g., 67% for treasury withdrawals, smart contract upgrades)
- Time delays between proposal passage and execution (timelock periods allow emergency response)
- Minimum proposal voting periods (e.g., 4-7 days minimum to allow community review)

**Delegation Safeguards**
- Transparent delegation: on-chain records of who delegated to whom
- Instant revocation: delegators can reclaim voting power at any time
- Liquid democracy: delegators can override their delegate's vote on specific proposals
- Delegate accountability: track records publicly visible

**Detection and Monitoring**
- Anomaly detection for sudden voting power concentrations
- Alert systems for unusual proposal activity or voting patterns
- Public dashboards showing token distribution, voting participation, delegation networks
- Post-execution review periods with emergency pause mechanisms

## SNS-Specific Considerations

**Initial Distribution Design**
- [[decentralization-swap-parameters]]: Avoid concentration in swap by setting max participant limits
- [[token-vesting-schedules-design]]: Stagger vesting to prevent sudden voting power shifts
- Developer/founding team voting power should decline over time as community grows

**Neuron Mechanics as Defense**
- [[neuron-staking-voting-power-mechanics]]: Dissolve delays create skin-in-the-game
- Longer dissolve delays = higher voting rewards = alignment with long-term health
- Age bonuses encourage sustained participation rather than one-time purchases

**Proposal Cost Mechanisms**
- [[proposal-submission-costs-and-anti-spam]]: Rejection fees deter spam but shouldn't block legitimate minority voices
- Tiered costs: higher fees for treasury/critical proposals, lower for governance parameter tweaks

**Following/Delegation Design**
- [[vote-delegation-and-following-mechanisms]]: Make following transparent and revocable
- Prevent circular following chains
- Display follower counts and voting records publicly

## Common Failure Patterns

**Indistinguishability Problem** (a16z)
- Mechanisms that enable broad participation also enable attackers
- Cannot distinguish "legitimate" token accumulation from "malicious" accumulation
- Solution: Focus on economic alignment (time locks, skin-in-the-game) rather than trying to identify "good" vs "bad" actors

**False Sense of Decentralization**
- Token distribution appears decentralized but votes are coordinated off-chain
- Multisig holders effectively control outcomes despite appearing as separate wallets
- Mitigation: Sybil-resistance through economic cost (staking, time locks) not identity

**Irreversibility**
- Once malicious proposals execute, reversal requires hard fork or extraordinary measures
- Prevention through early detection >> post-execution remediation
- Build in execution delays for all high-impact proposals

## Recommended SNS Init Parameters

- **Minimum dissolve delay for voting**: 6 months minimum
- **Proposal rejection fee**: 1-10 tokens (enough to deter spam, not block participation)
- **Voting period**: 4-7 days minimum for standard proposals, 7-14 days for critical changes
- **Quorum**: 3-10% of total voting power depending on DAO maturity
- **Super-majority threshold**: 67% for treasury, upgrade, and critical parameter changes
- **Max neuron age bonus**: Cap at 4x to prevent excessive concentration from oldest neurons
- **Voting rewards**: Higher for longer dissolve delays (see [[voting-rewards-and-incentive-design]])

## References
- a16z Crypto: "DAO governance attacks, and how to avoid them"
- Olympix: "Governance Attack Vectors in DAOs"
- Cantina: "Governance as an Attack Vector in Web3 Protocols"
- Frontiers in Blockchain: "DAO voting mechanism resistant to whale and collusion problems"