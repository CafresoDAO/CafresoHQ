---
tags: [research, tokenomics, vesting]
---

# Token Vesting Schedules Design

Critical component of SNS tokenomics that prevents early dumps and aligns long-term incentives. Links to [[sns-treasury-and-initial-token-distribution]] for allocation context.

## Industry Standard Cliff Periods

**Team/Founders:** 12-month cliff minimum
- No tokens unlock during cliff period
- Prevents mercenary behavior and short-term commitment
- Standard vesting duration: 36-48 months total after cliff

**Investors (Private/Strategic):** 6-12 month cliff
- Private rounds typically 6-month cliff, 42-month linear unlock
- Strategic partners sometimes shorter cliff (3-6 months) if they provide ongoing value

**Advisors/Consultants:** 6-month cliff, 18-24 month total vesting

## Vesting Models

**Linear Streaming:** Tokens unlock continuously (per-second or per-block)
- Smoothest distribution, prevents single-day dump events
- Preferred for team and investor allocations
- Example: 100K tokens over 36 months = ~92 tokens/day

**Cliff + Linear:** Industry best practice
- Initial lock period (cliff) + gradual linear release
- Balances commitment requirement with predictable liquidity

**Milestone-Based:** Tokens unlock upon achievement
- Riskier - can create uncertainty
- Better for contractors/short-term contributors than core team

## Reference Vesting Schedule Example

Typical DAO allocation schedule (100M token supply):

| Category | % | Cliff | Total Duration | Vesting After Cliff |
|----------|---|-------|----------------|---------------------|
| Team/Founders | 11% | 12mo | 48mo | 36mo linear |
| Private Sale | 11% | 6mo | 48mo | 42mo linear |
| Public Sale | 6% | 3mo | 9mo | 6mo linear |
| Treasury | 19% | 6mo | 24mo | 18mo linear |
| Marketing | 7% | 0mo | 48mo | 48mo linear |
| Liquidity | 6% | 0mo | Immediate | - |
| Incentives | 30% | 0mo | Immediate | - |

## SNS-Specific Considerations

**Neurons as Vesting Mechanism:**
- SNS tokens can be locked in neurons with dissolve delays
- Minimum dissolve delay acts as implicit vesting/cliff
- Voting power increases with lock duration, incentivizing longer holds
- Links to [[neuron-staking-voting-power-mechanics]]

**Developer/DAO Neuron:**
- Often holds team allocation in 6-8 year dissolve delay neuron
- Prevents immediate liquidity but allows governance participation
- More aligned than traditional vesting (team votes on proposals affecting their tokens)

## Red Flags to Avoid

❌ **No team cliff** = team can dump immediately after TGE
❌ **Short vesting (<24 months)** = weak long-term alignment  
❌ **Large unlocked treasury at launch** = governance capture risk
❌ **Asymmetric vesting** = team vests faster than community builds value

## Best Practices

✅ Team vesting ≥ 48 months total (12mo cliff + 36mo linear)
✅ Treasury releases controlled by governance votes, not automatic schedule
✅ All non-liquidity allocations have minimum 6-month cliff
✅ Public documentation of full vesting schedule before launch
✅ On-chain enforcement (smart contracts/neurons) not just promises
