---
tags: [research, sns, governance, proposal-costs]
---

# Proposal Submission Costs and Anti-Spam Mechanisms

## Overview
SNS governance systems use economic barriers to prevent spam proposals while maintaining accessibility for legitimate governance participants.

## Key Parameter: reject_cost_e8s

The `reject_cost_e8s` parameter defines the cost a neuron holder must pay when submitting a proposal. This fee is:
- **Returned** if the proposal is adopted
- **Forfeited** if the proposal is rejected
- Acts as a deterrent against frivolous or malicious proposals

### NNS Benchmark
The Network Nervous System (NNS) uses **25 ICP** as the proposal submission fee. This creates significant economic accountability for proposers while remaining accessible to serious participants.

## Proposal Type Differentiation

Different proposal types should have different requirements based on their impact:

### Critical Proposals
- **Longer voting periods**: 5-10 days
- **Higher adoption thresholds**
- Examples: Treasury transfers, major parameter changes
- Rationale: High-stakes decisions need thorough deliberation

### Non-Critical Proposals  
- **Shorter voting periods**: 4-8 days (default)
- **Standard thresholds**
- Examples: Minor updates, operational decisions
- Rationale: Maintains agility for routine governance

## Related Parameters

The proposal submission system works in concert with:

- `neuron_minimum_stake_e8s` — minimum tokens to create voting neuron
- `neuron_minimum_dissolve_delay_to_vote_seconds` — time commitment required to vote
- `initial_voting_period_seconds` — default window for voting
- `max_proposals_to_keep_per_action` — historical record limits

## Design Considerations

### Setting Rejection Costs
- **Too low**: Opens door to spam, governance fatigue, and low-quality proposals
- **Too high**: Excludes legitimate community participation, centralizes power
- **Calibration**: Should be meaningful relative to minimum neuron stake (typically 1-10x minimum stake)

### Balancing Accessibility vs Quality
A well-designed system:
1. Allows dedicated community members to participate
2. Deters bad actors from flooding governance
3. Aligns economic incentives with proposal quality
4. Returns fees to encourage good-faith proposals

## Links to Other Mechanisms

- Works with [[governance-voting-parameters]] to shape proposal dynamics
- Complements [[neuron-staking-voting-power-mechanics]] for governance access control
- Part of broader [[dao-failures-tokenomics-mistakes]] prevention strategy

## Implementation Notes

When configuring SNS init parameters:
- Consider your token's price volatility when setting fixed e8s amounts
- Test the psychological barrier: is the cost meaningful but not prohibitive?
- Monitor proposal submission rates post-launch and adjust if needed
- Document the reasoning for your chosen values in DAO communications