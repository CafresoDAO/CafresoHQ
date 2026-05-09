---
tags: [research, tokenomics, sns, icp]
---

# SNS Treasury and Initial Token Distribution

## Token Allocation Buckets

SNS init files define three primary token distribution buckets:

1. **Treasury tokens** — owned by SNS governance canister, spendable by community vote
2. **Swap tokens** — exchanged for ICP during decentralization swap
3. **Developer/airdrop tokens** — distributed to neurons (vested to team/early supporters)

## Treasury Management Model

The SNS places collected ICP into an **SNS-controlled treasury**. Post-swap, spending requires governance proposals passed by neuron holders.

Key consideration: Treasury is governed by staked neurons, creating alignment between token holders who lock liquidity and those controlling capital deployment.

## Swap Mechanics & Fallback

- Swap requires minimum ICP commitment threshold
- **Fallback controllers** defined in init file receive dapp control if swap fails
- Typically set to original developers pre-decentralization
- Protects against failed launch while maintaining credible decentralization path

## Neurons' Fund Integration

The **Neurons' Fund** (NNS-level mechanism) can participate in SNS swaps, providing:
- Base liquidity/credibility signal
- Adjusted via 30-day ICP/XDR conversion rate
- Simulated via SNS Tokenomics Analyzer before launch

## Open Questions for Future Research

- What treasury % leads to sustainable DAO operations?
- How do developer token vesting schedules correlate with project success?
- What swap participation thresholds indicate healthy community interest?
