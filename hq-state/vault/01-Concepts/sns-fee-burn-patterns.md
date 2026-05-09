---
title: SNS Fee-Burn Patterns
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-fee-burn-patterns
  - icp/governance/sns
  - icp/sns/tokenomics
  - icp/sns/supply-dynamics
source:
  - https://github.com/dfinity/ICRC-1/blob/main/standards/ICRC-1/README.md
  - https://github.com/dfinity/ic/tree/master/rs/sns/governance
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
related:
  - "[[sns-treasury-burns]]"
  - "[[sns-supply-dynamics]]"
  - "[[sns-tokenomics]]"
  - "[[sns-operations]]"
difficulty: intermediate
open_questions:
  - Whether the canonical SNS Ledger release burns its transaction fees (i.e. routes `fee` to the minting account) or accumulates them in a fee-collection account. The ICRC-1 spec says regular transfer fees are collected by the minting account, which would imply burn; verify this for the specific SNS Ledger wasm the project is deploying.
  - Whether any deployed SNS dapp canisters route application-level protocol fees (e.g. DEX swap fees, marketplace fees, transaction fees in an application canister) to a token burn, and if so what share — treat any specific claim as project-specific and verify against the project's source and public tokenomics post.
  - Whether DFINITY publishes canonical patterns/templates for fee-burn implementations at the application-canister level.
---

# SNS Fee-Burn Patterns

> An alternative to scheduled treasury burns: route a percentage of every fee (ledger transaction fee, protocol fee, revenue event) directly to the ICRC-1 minting account, so supply reduction tracks *usage* instead of tracking a calendar.

## Why it exists

Scheduled treasury burns (see [[sns-treasury-burns]]) have two problems: they deplete treasury runway on a fixed clock regardless of whether the DAO can afford it, and each burn requires a governance proposal that can fail. Fee-burns solve both: the supply reduction comes from usage revenue (not from treasury), and the burn happens at the ledger / canister level with no per-event proposal. A high-volume dapp burns more; a low-volume dapp burns less; a zero-volume dapp burns nothing and conserves treasury. The trade-off is that fee-burns only work if there is a fee-generating activity, and they couple tokenomics to usage in a way that is harder to reason about than "we burn 5M every H1".

## How it works

### Two layers where fees can be burned

1. **ICRC-1 ledger transaction fee.** Every transfer on the SNS Ledger charges a per-transfer fee (`icrc1_fee()`). Per the ICRC-1 spec, regular-transfer fees are collected by the minting account — which means, in the canonical ICRC-1 reading, *every ledger transaction is a partial burn*. Whether the deployed SNS Ledger wasm actually enforces this (vs. routing fees to a non-minting collection account) is a per-release implementation detail — verify.
   - Implications: higher token velocity → more burn. A token that sits in wallets does not burn; a token that trades actively does.
   - The per-tx fee is small (SNS Ledger fees are typically fractions of a token); the cumulative burn depends on transaction volume.
2. **Application-canister protocol fee.** A dapp that charges its users a fee for protocol actions (DEX swaps, NFT mints, marketplace listings, subscription payments, bridge operations) can direct some fraction of that fee to a burn. Mechanisms:
   - The dapp canister itself transfers X% of incoming fees to the SNS Ledger minting account on each billable event.
   - The dapp canister accumulates fees, then transfers a batch to the minting account on a cadence (daily, weekly).
   - The dapp canister holds fees in a dedicated subaccount; the DAO periodically proposes a burn from that subaccount (hybrid between fee-burn and scheduled burn).

### Comparison with scheduled treasury burns

| Axis                          | Scheduled treasury burn                           | Fee-burn                                          |
|-------------------------------|---------------------------------------------------|---------------------------------------------------|
| Burn source                   | Treasury balance                                  | Usage / protocol revenue                          |
| Tracks usage?                 | No — fixed calendar                               | Yes — bursts of activity → bursts of burn        |
| Depletes treasury?            | Yes — bounded above by treasury balance           | No — does not touch treasury                      |
| Requires per-burn proposal?   | Yes (see [[sns-treasury-burns]])                  | No (for ledger-level or canister-level patterns) |
| DAO can cancel?               | Yes — vote the next proposal down                 | Only by upgrading the dapp canister or changing ledger config |
| Predictability                | High (calendar)                                   | Low (depends on usage)                            |
| Narrative                     | "We burn N tokens every period"                   | "We burn with every transaction"                  |
| Common failure mode           | Treasury exhausts; schedule ends                  | Zero usage → zero burn → no deflation             |

The two are not exclusive. A hybrid ("scheduled burn funded from fee accumulator") preserves predictability while insulating treasury.

### External benchmarks

- **BNB quarterly burns.** Binance historically burned BNB quarterly, initially funded from exchange profits; later transitioned to an on-chain auto-burn formula tied to price and usage. Analogous to the treasury-burn → fee-burn evolution teams sometimes follow. Cite specific numbers from Binance's published burn history, not memory.
- **ETH EIP-1559.** Introduced a `base fee` on every transaction that is burned (sent to an unspendable address). Makes ETH supply respond directly to transaction volume; under sufficient load, ETH net-burns. A useful mental model for fee-burn-at-the-ledger-level, though the ICRC-1 and EVM fee mechanics differ.
- **Canister-fee burns (ICP-native).** Some ICP ecosystem projects route protocol fees at the canister level to the SNS Ledger minting account; specific percentages and mechanisms are project-by-project. **Do not cite a specific project's percentage from memory** — verify against the project's source code or tokenomics post.

## Example

```text
Sketch: SNS-token-denominated marketplace dapp, 2.5% marketplace fee,
50% of fee burned, 50% to treasury.

  User pays 100 TOK to seller on a marketplace transaction.
  Marketplace canister deducts 2.5 TOK fee.

    Burn leg:      1.25 TOK → transfer to SNS Ledger minting account
                              (reduces icrc1_total_supply by 1.25 TOK)

    Treasury leg:  1.25 TOK → transfer to SNS Governance treasury subaccount
                              (supply unchanged; treasury grows)

  Seller receives: 97.5 TOK.

  Over a week with 10,000 transactions averaging 100 TOK:
    Total fee:     25,000 TOK
    Burned:        12,500 TOK / week
    Annualised:    ≈ 650,000 TOK / year

  Compared to a 10M/year scheduled treasury burn:
    Scheduled burn is ~15x larger under this usage profile — fee-burn
    only catches up at ~15x higher volume, or at ~15x higher fee %.
    A hybrid (scheduled burn while usage ramps, phase out as fee-burn
    grows) is a plausible design.
```

## Gotchas

- **Zero usage → zero burn.** A fee-burn model for a dapp with low or zero real usage is a tokenomic no-op. Before committing to fee-burn as the primary deflationary mechanism, model the expected annual burn at realistic and at pessimistic volumes.
- **Fee-burn depends on the ledger/canister actually implementing it.** "We'll burn fees" is a narrative; the mechanism must live in code (ledger config for ledger fees, canister code for protocol fees) and must route to the minting account. Verify.
- **ICRC-1 ledger fees are small.** The default SNS Ledger per-transfer fee is fractions of a token; it takes very high tx volumes for ledger-fee-burns alone to move the needle on total supply.
- **DEX / LP / mint fees are usually denominated in the traded asset, not always in the SNS token.** A DEX that charges fees in ICP and converts to SNS token to burn introduces a pricing step; a DEX that charges fees directly in SNS token burns straightforwardly. Model the conversion path.
- **Removing fee-burn later requires governance.** If fee-burn is implemented in the dapp canister, reversing it requires an upgrade proposal. If at the ledger level, it requires changing the ledger. Either way, it is a sticky design choice — easier to add than to remove cleanly.
- **Fee-burns concentrate benefit on holders proportional to stake.** The holders who benefit most from deflation are those who hold the most. A fee-burn narrative that emphasises "community reward through deflation" is really describing a holder reward; worth naming that directly.
- **Do not claim a specific burn percentage without code.** "We burn 50% of fees" is a statement about the dapp canister's code. Publish the function that does it. A forum-post claim with no code is rumor.

## See also

- [[sns-treasury-burns]]
- [[sns-supply-dynamics]]
- [[sns-tokenomics]]
- [[sns-operations]]
- [[sns-canisters]]
- [[tokenomics-100m-v2-burn-and-staking]]
