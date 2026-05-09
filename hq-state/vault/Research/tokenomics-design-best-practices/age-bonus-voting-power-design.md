---
tags: [research, sns, tokenomics, governance]
---

# Age Bonus Voting Power Design

Age bonus is a critical but often overlooked voting power multiplier in SNS governance that rewards long-term commitment beyond just dissolve delay.

## Core Mechanics

**Voting power formula:**
```
voting_power = neuron_stake × dissolve_delay_bonus × age_bonus
```

**Age vs. Dissolve Delay:**
- **Dissolve delay**: commitment to *future* lock-up (6mo = 1.06x, 8yr = 2x, linear scaling)
- **Age bonus**: reward for *past* lock-up duration without dissolving
- Both multiply together, creating powerful incentives for long-term holders

## Design Rationale

**Why age bonus matters:**
1. **Prevents gaming**: Without it, participants could repeatedly lock/unlock to maximize dissolve delay bonus without true commitment
2. **Rewards consistency**: Values holders who maintain position through market cycles
3. **Governance stability**: Long-term participants have proven alignment and context
4. **Sybil resistance**: Age accumulation can't be easily split across multiple neurons

## Implementation Considerations

**Age accumulation rules:**
- Age only accumulates while neuron is non-dissolving
- Dissolving state pauses age accumulation
- Age resets if neuron fully dissolves
- Age may cap at maximum (typically matches max dissolve delay)

**Balancing parameters:**
- Too aggressive: locks governance power with old holders, prevents fresh participation
- Too weak: undermines long-term commitment incentives
- Sweet spot: meaningful reward (10-25% boost over time) without entrenchment

## Common Pitfalls

1. **No age bonus**: Encourages lock/unlock cycling to game rewards
2. **Age bonus too high**: Creates permanent governance oligarchy
3. **Complex age curves**: Confuses participants, reduces predictability
4. **Age without dissolve delay**: Allows gaming through temporary locks

## SNS Best Practices

- Mirror NNS age bonus parameters unless specific reasons justify deviation
- Document age bonus clearly in tokenomics materials (often overlooked)
- Consider reduced age bonus cap for smaller DAOs to prevent entrenchment
- Ensure age bonus + dissolve delay don't create >4x total multiplier gaps
- Test scenarios where early adopters accumulate maximum age before broader participation

## Related Mechanisms

See also: [[dissolve-delay-parameter-design]], [[neuron-staking-voting-power-mechanics]], [[voting-rewards-and-incentive-design]]