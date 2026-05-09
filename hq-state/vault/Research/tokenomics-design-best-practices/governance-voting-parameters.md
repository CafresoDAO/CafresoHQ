---
tags: [research, tokenomics, governance]
---

# DAO Governance Voting Parameters

Critical parameters that determine proposal success/failure and protect against attacks.

## Quorum Requirements

**Minimum participation threshold for valid votes.**

- **Industry standard: 4%+** for most DAOs
- Lower thresholds create whale attack vectors (e.g., 15% holder + 3% quorum = only needs 5% additional support)
- Active multisig DAOs often use 50%+ quorum
- Example: Threshold network requires **1.5% of total T supply** for proposals to pass

## Approval Thresholds

**Percentage of participating votes needed to pass.**

- **66%+ for major changes** (constitutional amendments, treasury allocation)
- Simple majority (50%+) for routine operations
- Acts as buffer against coordinated attacks when combined with quorum

## Voting Period Duration

**Vote-time synchronizes with voter activity patterns.**

- **1-3 days**: Active communities, frequent communication, multisig wallets
- **7-10 days**: Broader DAOs with global participation
- Example: Threshold runs **10-day voting periods**
- Too short → excludes timezone/schedule diversity
- Too long → slows decision velocity

## Anti-Gaming Mechanisms

1. **High quorum + high threshold** creates double defense
2. **Snapshot voting** (record holdings at proposal creation) prevents vote-buying during active proposal
3. **Proposal bond/threshold** prevents spam (must hold X% to submit)

## SNS Considerations

Related to [[neuron-staking-voting-power-mechanics]] — dissolve delay affects who can participate in votes within the voting period window.

Key question for SNS init: balance accessibility (low barriers) vs security (high thresholds). Early-stage DAOs often start permissive and tighten as token distribution broadens.