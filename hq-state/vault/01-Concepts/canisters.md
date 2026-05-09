---
title: Canisters
type: concept
status: stable
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/canister
source:
  - https://internetcomputer.org/docs/building-apps/essentials/canisters
  - https://internetcomputer.org/docs/building-apps/canister-management/storage
  - https://internetcomputer.org/docs/references/ic-interface-spec
related:
  - "[[subnets]]"
  - "[[cycles]]"
  - "[[principals]]"
  - "[[motoko]]"
  - "[[rust-cdk]]"
  - "[[stable-memory]]"
  - "[[upgrade-hooks]]"
  - "[[candid]]"
difficulty: beginner
open_questions:
  - Exact per-message instruction limit (update vs query vs composite-query) — subnet-dependent and adjusted via replica releases.
---

# Canisters

> A canister is ICP's smart-contract unit: a WebAssembly module bundled with its own persistent memory, addressable by a [[principals|principal]] and executed by a [[subnets|subnet]].

## Why it exists

Ethereum-style contracts are small, stateless-ish functions that read/write a shared KV. ICP wanted contracts that could also serve full web applications — HTTPS endpoints, large state, long-running compute — without relying on a frontend hosted off-chain. A canister bundles **code + state + identity + billing account** into one addressable object so a full dapp can live entirely on-chain.

## How it works

- **Wasm module** — compiled from Motoko, Rust, TypeScript (Azle), Python (Kybra), or any language with a Wasm target plus a CDK.
- **State** — two tiers: the Wasm heap (up to 4 GiB in 32-bit mode, ~6 GiB in 64-bit mode — reset on upgrade in the classical model) and **stable memory** (up to 500 GiB, preserved across upgrades). Motoko's Enhanced Orthogonal Persistence additionally retains the entire main memory across upgrades. See [[stable-memory]].
- **Messages** — canisters expose `update` (state-changing, goes through consensus) and `query` (read-only, answered by a single replica, much faster). See [[inter-canister-calls]].
- **Interface** — every canister's public interface is described in [[candid|Candid]]; CDKs auto-generate the `.did` file.
- **Billing** — each canister holds a balance of [[cycles]]; every instruction, message, and byte of storage is metered against that balance. An empty-balance canister is eventually frozen and then deleted.
- **Controllers** — principals authorized to install code, upgrade, start/stop, or delete the canister. Controllers are distinct from the canister's *own* principal.
- **Lifecycle** — `create → install → running → (upgrade | stop | start) → delete`. Upgrades invoke `pre_upgrade`/`post_upgrade` hooks (now optional under Motoko EOP); see [[upgrade-hooks]].

## Example

```motoko
// Minimal canister actor in Motoko.
actor {
  stable var count : Nat = 0;

  public func increment() : async Nat {
    count += 1;
    count
  };

  public query func get() : async Nat { count };
};
```

## Gotchas

- The Wasm heap is **wiped on upgrade**. Anything you need to keep must live in stable memory or be serialized in `pre_upgrade`.
- `query` calls are fast but **not trusted** individually — a single replica answers. For security-critical reads, use an `update` call or a certified query.
- A canister can run out of cycles silently; monitor balance and set a freezing threshold.
- Canister IDs are principals, but not all principals are canisters (users are principals too).

## See also

- [[subnets]]
- [[cycles]]
- [[principals]]
- [[motoko]]
- [[rust-cdk]]
- [[dfx]]
