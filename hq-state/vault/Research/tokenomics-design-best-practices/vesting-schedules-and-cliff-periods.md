---
tags: [research, tokenomics, sns, vesting]
---

# Vesting Schedules and Cliff Periods

Token vesting schedules control how allocated tokens unlock over time, critical for aligning team/investor incentives and preventing sell pressure.

## Standard Vesting Structure

**Cliff Period**: Initial lock phase before ANY tokens unlock
**Vesting Duration**: Total time for complete unlock
**Unlock Duration**: Time over which gradual release occurs

## Benchmark Allocation Schedule

Based on industry standards (100M token supply example):

| Category | % | Cliff | Vest Duration | Unlock Duration |
|----------|---|-------|---------------|-----------------|
| Team/Founders | 11% | 12mo | 48mo | 36mo |
| Private Sale | 11% | 6mo | 48mo | 42mo |
| Treasury | 19% | 6mo | 24mo | 18mo |
| Public Sale | 6% | 3mo | 9mo | 6mo |
| Marketing | 7% | 0mo | 48mo | 48mo |
| Incentives | 30% | 0mo | 1mo | 1mo |

## SNS-Specific Considerations

**Per IC Documentation**: SNS preparation checklist requires:
- Clear articulation of token distribution
- Rationale for dev and seed independence
- Analysis via SNS Tokenomics Analyzer
- Evolution of voting power over time
- Justification of DAO decentralization trajectory

## Best Practices

**Team/Founder Vesting**:
- 12-month cliff minimum (prevents quick exit)
- 3-4 year total vesting (industry standard)
- Linear monthly/quarterly unlock (predictability)

**Early Investor Vesting**:
- 6-12 month cliff
- 2-4 year unlock schedule
- Prevents immediate dump post-launch

**Treasury Allocation**:
- Moderate cliff (3-6mo) allows early DAO operations
- 18-24 month unlock balances runway with dilution control

**Public Sale**:
- Shorter cliff (0-3mo) rewards community participation
- Faster unlock (6-12mo) acceptable for smaller allocations

## Related Considerations

Links to [[initial-token-allocation-and-swap-parameters]] for genesis distribution and [[whale-concentration-anti-whale-mechanisms]] for addressing concentrated unlocks.

## Common Pitfalls

- **No cliff on team tokens**: Creates misaligned incentives
- **Too-short vesting**: Enables coordinated dumps
- **Uniform schedules**: Ignores different stakeholder needs
- **Ignoring voting power evolution**: Early concentrations persist too long

## Monitoring

Track upcoming unlock events to:
- Anticipate sell pressure
- Adjust liquidity provisions (see [[liquidity-provision-and-dex-strategies]])
- Communicate with community