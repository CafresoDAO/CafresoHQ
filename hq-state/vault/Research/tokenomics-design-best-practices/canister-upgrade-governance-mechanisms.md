---
tags: [research, sns, governance, upgrades, risk-management]
---

# Canister Upgrade Governance Mechanisms

## Overview
SNS canister upgrades represent critical governance decisions that can fundamentally alter DAO behavior. Proper upgrade governance is essential for security and continuity.

## Key Mechanisms

### Proposal-Driven Upgrades
- SNS canisters (governance, ledger, swap, root, index) can only be upgraded via governance proposals
- NNS team publishes new versions to SNS-WASM, but each SNS DAO must vote to adopt them
- Creates two-tier system: NNS approval → individual SNS adoption

### Launch Phase Restrictions
- Certain proposals **cannot be submitted during SNS launch** before decentralization completes
- Prevents founders/early controllers from making fundamental changes before community can participate
- Ensures critical governance decisions happen only after decentralization swap completes

### Emergency Upgrade Patterns
- Critical bug fixes (e.g., 2025-08 example) sometimes require fast-track voting
- DFINITY votes quickly on critical security/stability issues
- Creates tension between urgency and decentralized deliberation
- Related to [[emergency-governance-safeguards]] mechanisms

### SNS-Driven Upgrades Feature
- Recent enhancement allows SNS governance to drive its own upgrades more autonomously
- Reduces dependency on manual intervention
- Enables programmatic upgrade schedules if configured

## Risk Considerations

### Upgrade Attack Surface
- Malicious upgrade could drain treasury, manipulate voting power, or lock governance
- Requires high quorum thresholds for upgrade proposals
- Should be classified as critical proposal type requiring extended voting periods

### Version Skew Risks
- SNS DAOs may lag behind published versions if governance is inactive
- Creates security exposure if critical patches aren't adopted
- Links to [[voter-participation-and-quorum-design]] challenges

### Coordination Dependencies
- Multi-canister upgrades must be coordinated (governance + ledger + swap together)
- Partial upgrades can create incompatibilities
- Proposal text should clearly specify all affected canisters

## Best Practices for SNS Init Config

**Upgrade Proposal Parameters:**
- Set higher `minimum_yes_proportion_of_total` (e.g., 20-30%) for upgrade proposals
- Require extended `initial_voting_period` (7-14 days) for upgrades vs standard proposals
- Consider separate quorum thresholds by proposal type

**Emergency Override Mechanisms:**
- Define what constitutes "emergency" clearly in documentation
- Establish pre-approved fast-track process for critical security patches
- Requires balance with [[governance-attack-vectors-and-defenses]]

**Transparency Requirements:**
- Mandate detailed technical review period before upgrade votes
- Require changelog, security audit summaries, and rollback procedures in proposal text
- Consider requiring developer signatures or reproducible builds

## Anti-Patterns

❌ Allowing unrestricted upgrade proposals before swap completion  
❌ Same voting parameters for upgrades as routine governance  
❌ No rollback mechanism if upgrade causes issues  
❌ Automatic adoption of NNS-published versions without DAO vote  

## Treasury Impact

Upgrade governance intersects with [[treasury-management-strategies]]:
- Buggy upgrades could expose treasury to exploits
- Upgrade proposals may include treasury disbursement logic changes
- Version lag creates technical debt that eventually requires expensive remediation
