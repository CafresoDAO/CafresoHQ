---
tags: [research, sns, tokenomics, treasury, governance]
created: 2026-04-29
---

# Treasury Spending Approval Thresholds and Limits

## Critical Proposal Categories

SNS governance classifies treasury-related proposals as **critical**, requiring stricter controls:
- Treasury fund transfers
- SNS token minting
- De-registering dapp canisters (transferring control to another entity)

## Proposed Spending Limits

DFINITY community discussions (2023-2024) identified the need for **per-proposal spending caps** to prevent single-vote treasury drainage. Key design considerations:

- **Amount-based thresholds**: Limit tokens movable in a single proposal
- **Time-based rate limits**: Restrict total treasury outflows per time window
- **Percentage caps**: Limit withdrawals to X% of total treasury per proposal

This builds on [[emergency-governance-safeguards]] and complements [[proposal-submission-costs-and-anti-spam]].

## Empirical Participation Data

Study of 14 ICP SNS DAOs (2024-2025):
- **Average participation rate**: 64%
- **Approval rates**: >96.8%

High approval rates suggest either strong community alignment OR insufficient critical evaluation—important to distinguish via [[voter-participation-and-quorum-design]].

## Multi-Signature Patterns (Cross-Chain Reference)

While SNS uses neuron-based governance, traditional DAO best practices recommend:
- **3-of-5 or 4-of-7 multisigs** for major treasury operations
- Clear role separation
- Time-locks for large transfers

SNS equivalent: combine high quorum requirements with [[dissolve-delay-parameter-design]] minimums for treasury voters.

## Anti-Pattern: No Treasury Governance

DeepSnitch case study (2024): $1.5M raised with:
- ❌ No DAO voting contract
- ❌ No proposal system
- ❌ No on-chain transparency
- ❌ Unilateral team spending decisions

Reinforces need for **on-chain treasury controls** and public spending reports in SNS design.

## Best Practices for SNS Init File

1. **Set conservative spending limits** in initial governance parameters
2. **Require supermajority** (>66%) for critical treasury proposals
3. **Mandate minimum dissolve delay** for treasury voters (e.g., 6+ months)
4. **Enable treasury reporting**: Periodic on-chain summaries via automated proposals
5. **Escalating thresholds**: Small spends = simple majority; large spends = higher quorum + dissolve delay requirements

Links to [[canister-upgrade-governance-mechanisms]] for coordinating treasury + code upgrade governance.

## Open Questions

- Optimal spending cap as % of total treasury?
- Should treasury limits decrease over time as DAO matures?
- How to handle emergency treasury access vs. security?