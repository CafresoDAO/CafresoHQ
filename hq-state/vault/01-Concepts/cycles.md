---
title: Cycles
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/cycles
source:
  - https://internetcomputer.org/docs/building-apps/essentials/gas-cost
  - https://internetcomputer.org/docs/building-apps/canister-management/topping-up
related:
  - "[[canisters]]"
  - "[[subnets]]"
  - "[[cycles-wallet]]"
  - "[[sns]]"
difficulty: beginner
open_questions:
  - Exact current XDR-to-cycles conversion rate and per-operation cycle prices — these are set by the NNS and change over time.
  - Current freezing threshold defaults for app subnets vs. system subnets.
---

# Cycles

> Cycles are the unit of resource metering on ICP — the "gas" that pays for a [[canisters|canister]]'s compute, memory, messages, and storage.

## Why it exists

Unlike account-based chains where the *caller* pays gas, ICP uses a **reverse-gas** model: the callee (canister) pays. This lets end users interact with a dapp without holding tokens or signing gas-priced transactions — a precondition for normal web UX. Cycles are the denomination in which that metering happens.

## How it works

- **Stable price** — cycles are pegged to a fixed value in XDR (IMF Special Drawing Rights), so a unit of compute costs a predictable amount in fiat terms regardless of ICP token price volatility.
- **Minting** — ICP tokens can be converted to cycles by sending them to the cycles-minting canister; the NNS burns the ICP and credits cycles to a target canister. See [[cycles-wallet]].
- **Metering** — the replica charges cycles for: Wasm instructions executed, bytes of state stored per second, messages sent/received, and inter-canister call payloads.
- **Freezing threshold** — each canister has a reserve below which it stops accepting `update` calls (to avoid being deleted mid-operation). The controller sets this.
- **Deletion** — a canister whose balance hits zero is eventually deleted and its state lost. Top-ups are the operator's responsibility.
- **Subnet dependence** — cost scales with [[subnets|subnet]] replication factor; a 13-node app subnet is cheaper per cycle than a 34-node fiduciary subnet.
- **DAO-governed canisters still burn cycles** — [[sns|SNS]] canisters (Root, Governance, Ledger, Index, Swap, Archive) and the dapp canister(s) handed off to them consume cycles like any other; post-launch top-ups are typically funded from the SNS treasury via an SNS proposal rather than a dev-side `dfx canister deposit-cycles`.

## Example

```bash
# Check a canister's cycle balance (via dfx).
dfx canister status my_canister

# Top up a canister with cycles from your wallet.
dfx canister deposit-cycles 1_000_000_000_000 my_canister
```

## Gotchas

- Running out of cycles is a *real* failure mode. Monitor balances; consider a cycles-ops canister or external alerting.
- Cycle costs are **per-subnet**: migrating a canister between subnet types changes its burn rate.
- A `query` is cheap but still costs cycles; a hot-loop of queries from a malicious caller can drain a canister.
- Never hardcode cycle amounts in production without a way to update them — NNS can (and does) re-price operations.

## See also

- [[canisters]]
- [[cycles-wallet]]
- [[subnets]]
- [[sns]]
