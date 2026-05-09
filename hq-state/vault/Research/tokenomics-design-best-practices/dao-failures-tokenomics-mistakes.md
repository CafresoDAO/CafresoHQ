---
tags: [research, tokenomics, dao-governance]
created: 2026-04-29
---

# DAO Failures and Tokenomics Mistakes

## Common Failure Patterns

**Rigid Tokenomics**
- Token-based systems struggle to adapt when tokenomics are too rigid (RapidInnovation DAO study)
- Fixed parameters in initial distribution can't accommodate changing community needs
- Lesson: Build flexibility into governance token mechanics, allow parameter updates via proposal

**Voting Power Concentration**
- Poor initial token distribution creates plutocracy, not democracy
- Early investors/team holding too much supply = captured governance
- Links to [[neuron-staking-voting-power-mechanics]] - dissolve delay and age bonuses can compound concentration issues

**The DAO (2016) Case Study**
- Trustless governance requires solving trust challenges, not ignoring them
- Technical vulnerabilities in smart contracts can destroy entire treasuries
- Governance design must account for adversarial scenarios and edge cases
- The failure highlighted need for expanded governance theories beyond traditional corporate models

## Key Design Decisions

Per arXiv research on Open Problems in DAOs:
- How to allocate voting power (linear tokens vs. quadratic vs. reputation-weighted)
- How voting choices translate to outcomes (simple majority vs. quorum requirements vs. conviction voting)
- Social choice theory intersects with tokenomics design

## Treasury Management Implications

Failures often stem from:
- No clear treasury spend governance framework
- Inability to adapt treasury allocation as project evolves
- See [[sns-treasury-and-initial-token-distribution]] for allocation best practices

## Reputation vs. Pure Token Systems

- Reputation tokenomics (SSRN paper) argues reputation-weighted governance more nimble and market-responsive
- Pure token systems can be gamed via accumulation
- Hybrid approaches (like ICP neurons with dissolve delay) attempt to reward long-term alignment

## For SNS Init File Design

Critical parameters to avoid common pitfalls:
- Ensure governance can update its own parameters (meta-governance)
- Prevent early whale concentration through vesting, lockups, caps
- Build in treasury spending limits/budgets at governance layer
- Consider reputation/commitment signals (dissolve delay) alongside raw token holdings