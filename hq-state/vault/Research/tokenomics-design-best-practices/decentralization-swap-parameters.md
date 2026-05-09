---
tags: [research, sns, tokenomics, decentralization-swap]
---

# Decentralization Swap Parameters & Pricing Mechanics

## How SNS Decentralization Swaps Work

The decentralization swap is the initial token distribution mechanism for SNS DAOs on ICP. Key mechanics:

**Dynamic Pricing Formula:**
- `Token Price = Total ICP Raised / SNS Tokens Sold`
- Price is **not known upfront** — determined only when swap closes
- More participation → higher price per token → fewer tokens per participant

**Pro-Rata Distribution:**
- All participants pay the same final price
- SNS tokens distributed as **neurons** (not liquid tokens)
- Contribution share determines allocation: `Your Tokens = (Your ICP / Total ICP) × Total SNS Tokens`

## Critical Init File Parameters

**Min/Max ICP Thresholds:**
- `min_participants` — minimum number of unique participants required
- `min_icp_e8s` — swap fails if not reached; protects against under-capitalization
- `max_icp_e8s` — caps raise; excess ICP refunded; controls dilution

**Token Allocation:**
- `sns_token_e8s` — total tokens available in swap (from treasury)
- Balance between community distribution vs. treasury reserves

## Best Practices for Setting Swap Parameters

**Minimum ICP Target:**
- Set high enough to fund roadmap for 18–24 months
- Too low → treasury runs dry, DAO forced to raise again (dilutive, governance overhead)
- Reference [[sns-treasury-and-initial-token-distribution]]

**Maximum ICP Cap:**
- Prevents whale dominance and excessive concentration
- Higher cap = lower token allocation per participant = better decentralization
- But: too high dilutes early contributors

**Participant Minimums:**
- Higher `min_participants` forces broader distribution
- Reduces risk of governance capture by small cartel
- Ties to [[neuron-staking-voting-power-mechanics]] — need diverse voting power

## Common Pitfalls

**Price Discovery Uncertainty:**
- Participants commit blind — don't know final price
- Can cause FOMO rushing or participation collapse if poorly marketed
- Transparency on roadmap/use-of-funds critical to justify valuation

**Over-Optimization for Raise Amount:**
- Maximizing ICP raised ≠ maximizing DAO health
- High valuation from successful swap can create sell pressure post-unlock
- Better: moderate raise, sustainable treasury management

**Insufficient Treasury Reserves:**
- Swap sells tokens from treasury → reduces DAO's future flexibility
- Need balance: distribute enough for decentralization, retain enough for grants/development
- See [[dao-failures-tokenomics-mistakes]] for under-funded DAO examples

## Monitoring & Iteration

- Track swap participation velocity during live swap
- Post-swap: analyze distribution (Gini coefficient, top-10 holder %)
- Future SNS versions may need parameter adjustments based on DAO's maturity