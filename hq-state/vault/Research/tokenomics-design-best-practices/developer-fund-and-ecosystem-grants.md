---
tags: [research, sns, tokenomics, treasury, grants]
---

# Developer Fund and Ecosystem Grants Allocation

## Treasury Allocation Categories

Successful DAOs segment treasury spending into distinct buckets with different approval processes:

- **Operational costs** - Core infrastructure, tooling, security audits
- **Ecosystem grants** - Funding builders, integrations, partnerships  
- **Public goods** - Core developer funding, research, open-source tools
- **Strategic reserves** - Emergency funds, market-making, long-term stability

Each category requires different governance thresholds and transparency requirements.

## Grant Program Structures

**Milestone-Based Funding** (Harmony model):
- $10K on testnet launch with feature-complete product
- $10K after forming DAO with community
- $10K after mainnet + audit
- $10K after 1K users
- $10K after 10K users

This derisks capital deployment and aligns incentives with delivery.

**Standing Grant Committees** (Balancer, MakerDAO, ENS, Gitcoin):
- Dedicated "Growth Core Unit" or grant program
- Delegated authority up to threshold (e.g., <$50K auto-approved)
- Quarterly budget reviews by full DAO
- Focus on integrations, partnerships, deepening protocol dependencies

## Best Practices

1. **Diversify grant types**: one-time bounties, recurring contributor rewards, retroactive public goods funding
2. **Use quadratic funding** for community signal on which projects to support
3. **Require milestone deliverables** - never full upfront payment
4. **Track ROI metrics** - integrations launched, TVL growth, user acquisition cost
5. **Reserve 10-20% of treasury** for ecosystem growth (too little = stagnation, too much = misalignment with token holders)

## Risk Mitigation

- **Grant clawback clauses** if milestones unmet
- **Multi-sig disbursement** with rotating committee members
- **Public transparency dashboards** showing all allocations
- **Conflict-of-interest disclosures** for grant reviewers

## Connection to SNS Design

The SNS init file should allocate developer fund neurons with:
- Long dissolve delays (2-4 years) to align long-term incentives
- Transparent on-chain proposal requirements for fund disbursement
- Clear spending caps per proposal type ([[treasury-management-strategies]])
- Voting rewards structure that doesn't drain ecosystem budget ([[voting-rewards-and-incentive-design]])

## Anti-Patterns

❌ Single wallet control of dev fund  
❌ No spending framework = ad-hoc political battles  
❌ Grants to anon teams with no delivery track record  
❌ No clawback mechanism when projects fail to deliver  

See also: [[treasury-management-strategies]], [[governance-voting-parameters]], [[token-utility-and-value-capture]]