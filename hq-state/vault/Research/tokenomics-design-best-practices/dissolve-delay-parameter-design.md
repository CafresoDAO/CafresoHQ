---
tags: [research, sns, tokenomics, governance]
---

# Dissolve Delay Parameter Design

Dissolve delay (neuron lock-up period) is a critical SNS init parameter that directly impacts governance stability, voting power distribution, and token liquidity.

## Mechanics

**Voting power formula** on Internet Computer SNS:
```
voting_power = stake × dissolve_delay_bonus × age_bonus
```

- Dissolve delay bonus: proportional to lock-up duration (longer = more power)
- Age bonus: rewards long-term holding without dissolving
- When timer reaches zero, neuron can disburse tokens

## Basket-of-Neurons Approach

**Best practice from ICP/SNS**: Initial contributors and swap participants receive **multiple neurons with staggered dissolve delays**, not a single locked position.

### Advantages:
- **Gradual liquidity**: participants can access portions over time
- **Sustained governance**: some neurons remain long-locked even as others dissolve
- **Flexibility**: different neurons for different purposes (voting, liquidity, speculation)
- **Reduced sell pressure**: avoids cliff unlocks where everyone exits simultaneously

### Common basket configurations:
- Short (1-3 months): immediate liquidity needs, speculative positions
- Medium (6-12 months): balanced governance participation
- Long (1-2+ years): founding team alignment, maximum voting power

See also: [[token-vesting-schedules-design]] for team allocations, [[neuron-staking-voting-power-mechanics]] for detailed mechanics, [[governance-voting-parameters]] for related governance config.

## Parameter Design Considerations

**Minimum dissolve delay**: Set too low → governance instability (voters with no skin in the game). Common range: 1-6 months minimum for any voting power.

**Maximum dissolve delay**: Determines maximum voting power multiplier. NNS uses 8 years max; SNS projects often use 1-2 years to balance commitment vs accessibility.

**Dissolve delay for founding team**: Should match or exceed project maturity timeline. 2+ years signals long-term commitment. Combined with basket approach to avoid total lockout.

## Anti-Patterns

- **Single long lock without baskets**: Creates liquidity crisis and resentment
- **No dissolve delay incentive**: Voting power = stake only → plutocracy without long-term alignment
- **Excessive max delays (>3-5 years for SNS)**: Deters participation in early-stage DAOs
- **Uniform dissolve across all participants**: Increases correlated exit risk

## Operational Notes

Once set in SNS init file, dissolve delay parameters are **difficult to change** without governance vote. Model different scenarios (bear market, team departures, treasury needs) before finalizing.

Reference [[treasury-management-strategies]] for coordinating treasury neuron dissolve delays with operational needs.