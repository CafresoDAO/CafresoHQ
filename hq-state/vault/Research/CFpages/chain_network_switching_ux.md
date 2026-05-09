---
tags: [research]
---

# Chain/Network Switching UX

## Core User Expectation
Users expect **instant adaptation to wallet-initiated chain changes** (e.g., Ethereum → Polygon) without manual app refresh. This is now table-stakes; visible lag or broken state is immediate friction. The wallet triggers the switch; the dApp must respond.

## Chain-Specific Data Complexity
Each chain introduces separate parameters that affect display and function:
- Gas costs and block times (directly impact [[gas_fee_transparency_ux|gas fee disclosure]])
- Native token symbols (ETH vs MATIC vs different L2s)
- **Token address variance** — the same token has different contract addresses per chain, breaking naive lookups
- Token availability — tokens supported on Ethereum may not be bridged to L2s, limiting [[token_selection_asset_picker_ux|picker options]]
- [[slippage_price_impact_ux|Price data]] freshness and routing differences per chain

## Hidden Bottlenecks

### Wallet-Sync Friction
When users interact with the dApp during or after chain switching, **signing requests don't inherit chain context cleanly**. Popup appears, user loses thread of what they're approving on which chain. Solution: display dApp domain + **chain name + human-friendly action summary** in every approval context — but requires wallet-dApp metadata coordination.

### Bridge UX Boundary
Two patterns:
1. **Separate interface** — user leaves dApp to bridge via third-party, returns with different wallet state (friction, context loss)
2. **Integrated** — bridge built into flow, but adds complexity: idempotent receipts, recovery paths, and cross-chain proofs are non-trivial

Integrated bridges are becoming standard; expect integration for core liquidity flows.

### Inconsistent Asset Availability
A DEX may support 100+ tokens on Ethereum but only 20 on Arbitrum. This breaks: token selection UX (suddenly greyed-out options), [[pending_transaction_status_ux|confirmation flows]] (user expects asset to be swappable), and trust ("why did my token disappear?").

## Emerging Pattern: Chain Abstraction
Abstraction layers hide chain selection from users — they interact with assets/functions, and the backend routes to optimal liquidity/execution. Reduces friction by removing explicit switching but introduces new complexity: hidden cost discovery, routing transparency, and custody implications.

## Integration Implications for Cafreso
- **Dynamic token list**: Fetch supported assets per chain; grey out/hide unavailable tokens in picker
- **Approval context**: Inject chain name into signing requests (via wallet integration or metadata)
- **Gas estimation**: Re-calculate and refresh when chain changes or user switches manually
- **Bridge intercept**: Detect missing liquidity on current chain; offer integrated bridge before [[error_handling_recovery_patterns|error state]]
- **State recovery**: If user switches chains mid-flow, preserve intent ("you were swapping X to Y") and re-quote for destination chain