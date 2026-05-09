---
title: Cycles Wallet & Cycles Ledger
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/cycles-wallet
  - icp/deployment/cycles-wallet
source:
  - https://internetcomputer.org/docs/building-apps/canister-management/topping-up
  - https://internetcomputer.org/docs/building-apps/essentials/gas-cost
  - https://github.com/dfinity/cycles-ledger
related:
  - "[[cycles]]"
  - "[[principals]]"
  - "[[canisters]]"
  - "[[mainnet-deploy]]"
  - "[[dfx]]"
  - "[[nns]]"
difficulty: intermediate
open_questions:
  - Current `dfx cycles` subcommand surface (convert / top-up / balance / transfer flags) — drifts with dfx releases.
  - Current exact transfer / deposit fees on the cycles ledger (ICRC-1/2 fees are NNS-governable).
  - Current exact XDR-to-cycles conversion rate and the per-op cycle prices — both NNS-set.
---

# Cycles Wallet & Cycles Ledger

> The cycles wallet (legacy) and the cycles ledger (current) are the two ways a developer principal can hold [[cycles]] off-canister and use them to create or top up [[canisters]]: the wallet is a per-developer canister that custodies cycles on your behalf; the cycles ledger is a single global canister that credits cycles to a principal directly.

## Why it exists

Creating a new canister or topping one up requires cycles, and [[principals|principals]] cannot natively hold cycles — cycles are a canister-resident resource. Historically this was solved by giving each developer their own **wallet canister** that held cycles and forwarded them to other canisters on the developer's behalf. More recently, DFINITY shipped the **cycles ledger**: an ICRC-1/ICRC-2-compliant system canister that lets any principal hold a cycles balance as easily as any other token, without running a personal wallet canister. For new projects, DFINITY's current guidance is to use the cycles ledger and reserve the wallet pattern for legacy continuity.

## How it works

### ICP → cycles conversion

- Cycles are minted by the **Cycles Minting Canister (CMC)**, an [[nns|NNS]]-controlled canister. A developer converts ICP to cycles by transferring ICP to the CMC's account with a typed memo; the CMC burns the ICP and credits cycles to a target (a canister balance, a wallet canister, or a cycles-ledger account).
- The conversion rate is pegged to **XDR** (IMF Special Drawing Rights), not to the ICP spot price: one trillion cycles equals one XDR by definition. The ICP/XDR rate is set by the NNS from an oracle feed. Exact current values are NNS-governable and drift; do not hardcode them.

### Cycles ledger (current pattern)

- A single mainnet canister maintained by DFINITY that implements **ICRC-1** (balances, transfer) and **ICRC-2** (approve / transfer_from) for a cycles-denominated token. Balances are keyed by principal, just like any ICRC-1 token.
- `dfx` integrates with it via `dfx cycles <subcommand>` (balance, convert from ICP, transfer to another principal, top up a canister). The `dfx` identity's principal is the cycles-ledger account holder; no separate wallet canister is required.
- Because it is a standard ICRC ledger, third-party agents, front-ends, and ops tooling can interact with it without bespoke integrations — the same agent code that reads ICP balances reads cycles balances.
- Transfers and deposits incur a small per-operation fee in cycles (like any ICRC ledger); the current fee value is NNS-governable.

### Cycles wallet (legacy pattern)

- A per-developer canister (the `wallet.wasm` historically distributed with `dfx`) whose sole job is to custody cycles and relay requests. `dfx wallet` talks to it; `dfx canister create` historically routed cycles through it by default.
- The wallet has its **own [[principals|principal]]**, distinct from the dev's. When the wallet calls another canister (e.g. as the proxy for creating a new canister), `caller` inside that canister is the wallet's principal, not the developer's. This surprises authorisation code that compares `caller` to a hardcoded dev principal.
- Still supported for existing projects; `dfx identity set-wallet <id>` registers a wallet for an identity. Not recommended for new projects now that the cycles ledger exists.

### Topping up an existing canister

Three practical routes:

1. **From the cycles ledger** — `dfx cycles top-up <canister>` transfers cycles from the dev principal's cycles-ledger balance into the target canister. Standard path for modern projects.
2. **From a wallet canister** — `dfx wallet send` / `dfx canister deposit-cycles` forward cycles from the wallet. Standard path for legacy projects.
3. **Directly from ICP via the CMC** — send ICP to the CMC with a `TOP_UP_CANISTER` memo and the target canister ID; the CMC burns the ICP and deposits cycles. Useful for automation that already holds ICP rather than cycles.

## Example

```bash
# --- Modern flow: cycles ledger ---

# Check your principal's cycles-ledger balance.
dfx cycles balance --network ic

# Convert ICP to cycles and credit your principal on the cycles ledger.
# (Exact flag surface varies by dfx release; consult `dfx cycles convert --help`.)
dfx cycles convert --amount 1.0 --network ic

# Top up a specific canister from your cycles-ledger balance.
dfx cycles top-up <canister-id> 2_000_000_000_000 --network ic
```

```bash
# --- Legacy flow: wallet canister ---

# Look up the wallet associated with the current identity.
dfx identity get-wallet --network ic

# Send cycles from the wallet to a target canister.
dfx wallet send <canister-id> 2_000_000_000_000 --network ic
```

## Gotchas

- **`caller` surprise with wallets.** Under the wallet pattern, your canister sees the *wallet's* principal as `caller` for management-canister-style operations, not your dev principal. Authorisation logic (`assert caller == owner`) that expects the dev principal will reject calls routed through the wallet.
- **Running out is silent.** A canister that hits its freezing threshold stops accepting update calls; one that hits zero is eventually deleted. Neither the wallet nor the cycles ledger will refill anything on your behalf — monitoring and top-ups are the operator's job. See [[cycles]].
- **Prices are not constants.** XDR/cycles conversion and per-operation costs are [[nns|NNS]]-set and do change. Never hardcode cycle amounts in billing / budgeting code without a way to re-read current prices.
- **Wallet vs. cycles-ledger coexist.** An identity can have *both* a registered wallet and a cycles-ledger balance; `dfx` commands differ in which one they consume. Read the command's docs before running it in a hurry.
- **Mainnet-only for real money.** `dfx cycles` and `dfx wallet` operate against the target network; on [[local-replica|local]] they hit a local faucet/wallet and the balances are not real. Always pass `--network ic` when you mean mainnet.

## See also

- [[cycles]]
- [[mainnet-deploy]]
- [[canisters]]
- [[principals]]
- [[dfx]]
- [[nns]]
