---
title: Rust CDK
type: concept
status: stable
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/cdk
  - lang/rust
source:
  - https://internetcomputer.org/docs/building-apps/developer-tools/cdks/rust/intro-to-rust
  - https://github.com/dfinity/cdk-rs
  - https://github.com/dfinity/stable-structures
related:
  - "[[canisters]]"
  - "[[motoko]]"
  - "[[dfx]]"
  - "[[stable-memory]]"
  - "[[upgrade-hooks]]"
  - "[[candid]]"
  - "[[inter-canister-calls]]"
difficulty: intermediate
open_questions:
  - Exact minor versions of `ic-cdk` and `ic-stable-structures` pinned by the current `dfx` toolchain — useful for a CI pin but not needed for the concept itself.
---

# Rust CDK

> The Rust CDK (`ic-cdk`) is DFINITY's canister development kit for Rust — a set of crates and macros that turn a `#[no_std]`-friendly Rust crate into a deployable ICP [[canisters|canister]].

## Why it exists

Rust is the production workhorse for most non-trivial ICP dapps (ledger, II, NNS canisters, the ledger suite, most SNSes). The CDK hides the raw `ic0.*` system API behind ergonomic Rust: proc-macros for exported methods, async helpers for inter-canister calls, Candid serde support, and well-supported stable-memory data structures.

## How it works

- **Crates** — the toolkit is intentionally modular. Your canister is a `cdylib` crate targeting `wasm32-unknown-unknown`; you add `ic-cdk` for the canister programming model, `ic-cdk-macros` for the attribute macros (`#[update]`, `#[query]`, `#[init]`, `#[pre_upgrade]`, `#[post_upgrade]`), and pick up adjacent crates as needed: `ic0` (the raw system-API binding `ic-cdk` sits on top of), `ic-cdk-timers` (periodic / one-shot timers), `ic-cdk-bindgen` (generate typed Rust bindings from a `.did` for inter-canister clients), `ic-certified-map` / `ic-http-certification` (certified responses for asset-like workloads), `ic-ledger-types` (ICP-ledger types). The crates are separate; `ic-cdk-macros` is not re-exported by `ic-cdk`.
- **Candid** — the `candid` crate + `CandidType`/`Deserialize` derives produce the [[candid|Candid]] interface from your Rust types. `ic_cdk::export_candid!()` declares that a `.did` is extractable from the compiled Wasm; the `candid-extractor` tool (published alongside cdk-rs) reads the emitted section and writes the `.did` file at build time. `dfx build` wires this in for Rust canister types.
- **Async** — `ic_cdk::call(...)` returns a future the CDK drives between messages; you `await` it like normal Rust async. Each await point is a cross-message boundary; see [[inter-canister-calls]] for reentrancy implications.
- **State** — a common pattern is `thread_local! { static STATE: RefCell<State> = ...; }`. For upgrade-safe or large state, use `ic-stable-structures`. The crate currently provides `Cell`, `BTreeMap`, `BTreeSet`, `Vec`, `Log` (append-only variable-size entries), and `MinHeap`, each backed directly by stable memory and therefore upgrade-safe without custom `pre_upgrade`/`post_upgrade`. Hosting more than one in a single canister requires a `MemoryManager` — stable structures *cannot share a memory*, so the manager carves a single physical memory into up to 255 virtual memories keyed by `MemoryId`, one per structure. See [[stable-memory]].
- **Build** — `dfx build` invokes `cargo build --target wasm32-unknown-unknown --release` and then `ic-wasm` to shrink / post-process the module.

## Example

```rust
use ic_cdk::{query, update};

thread_local! {
    static COUNT: std::cell::Cell<u64> = std::cell::Cell::new(0);
}

#[update]
fn increment() -> u64 {
    COUNT.with(|c| { let n = c.get() + 1; c.set(n); n })
}

#[query]
fn get() -> u64 {
    COUNT.with(|c| c.get())
}

ic_cdk::export_candid!();
```

## Gotchas

- The Wasm heap is wiped on upgrade. Either serialize state in `#[pre_upgrade]`/`#[post_upgrade]` or keep it in `ic-stable-structures` from the start. See [[upgrade-hooks]].
- `panic!` aborts the message and rolls back any state change in that message — useful as a cheap assert, but expensive if you trip it in hot paths.
- `await` across an inter-canister call means the canister's state can be observed / mutated by other messages before the call returns. Design for reentrancy.
- Wasm binary size matters for install/upgrade cost — strip debug info and run `ic-wasm shrink`.

## See also

- [[canisters]]
- [[motoko]]
- [[dfx]]
- [[stable-memory]]
- [[upgrade-hooks]]
- [[candid]]
- [[inter-canister-calls]]
