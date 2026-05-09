---
title: Stable Memory
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/stable-memory
  - icp/pattern/stable-memory
source:
  - https://internetcomputer.org/docs/motoko/icp-features/stable-memory
  - https://internetcomputer.org/docs/motoko/fundamentals/actors/data-persistence
  - https://internetcomputer.org/docs/building-apps/canister-management/storage
  - https://github.com/dfinity/motoko
  - https://github.com/dfinity/stable-structures
related:
  - "[[canisters]]"
  - "[[upgrade-hooks]]"
  - "[[motoko]]"
  - "[[rust-cdk]]"
difficulty: intermediate
open_questions:
  - Whether the 500 GiB stable-memory ceiling applies uniformly across all subnet types or is effectively capped lower by per-canister storage cost / freezing thresholds.
---

# Stable Memory

> Stable memory is a second, larger memory area a [[canisters|canister]] can use for data that must survive a Wasm upgrade — separate from the Wasm heap, accessed through a byte-addressable system API, and automatically preserved by the replica across `install --mode upgrade`.

## Why it exists

The Wasm heap is reset when a canister is upgraded to a new Wasm module (unless Motoko's Enhanced Orthogonal Persistence is in effect — see below). Dapps that hold more state than fits in the 32-/64-bit heap, or that simply want upgrades to be cheap and reliable, need a storage tier that is *decoupled from the Wasm module's lifetime*. Stable memory is that tier.

## How it works

- **Tiers** — every canister has (1) Wasm / heap memory (cleared on upgrade in the classical model) and (2) stable memory, which the system preserves across upgrades.
- **Size** — stable memory has a documented ceiling of **500 GiB** per canister (much larger than the heap; the heap itself is 4 GiB in 32-bit mode, ~6 GiB in 64-bit mode without enhanced persistence). Actual usable size is bounded by subnet storage and the canister's [[cycles]] balance.
- **Pages and blocks** — the allocation unit is a **page** (fixed at 64 KiB, i.e. `65_536` bytes, zero-initialised). The runtime allocates in **blocks** of 128 pages internally, but the caller addresses individual bytes via offsets.
- **System API** — low-level `ic0.stable64_grow`, `ic0.stable64_read`, `ic0.stable64_write` calls expose the area directly; CDKs wrap them.
- **Motoko — stable variables** — annotate actor fields with `stable var` (or declare `persistent actor` so every `let`/`var` is implicitly stable). The runtime serialises stable fields into stable memory on upgrade and rehydrates them on install.
- **Motoko — `Region`** — for raw byte-addressable stable storage, the `mo:core/Region` module exposes `Region.new()`, `Region.grow(r, pages)`, `Region.size(r)`, and typed `storeNat8` / `loadNat8` / `storeNat64` / `loadNat64` / `storeBlob` / `loadBlob` accessors. `Region.grow` returns the previous size on success, or `0xFFFF_FFFF_FFFF_FFFF` on failure.
- **Rust — `ic-stable-structures`** — the DFINITY-maintained `ic-stable-structures` crate provides `StableBTreeMap`, `StableLog`, `StableCell`, `StableVec`, each backed directly by stable memory and therefore upgrade-safe without custom `pre_upgrade`/`post_upgrade`. See [[upgrade-hooks]] and [[rust-cdk]].
- **Enhanced Orthogonal Persistence (Motoko)** — Motoko's default persistence mode keeps the *entire Wasm main memory* across upgrades (the IC's `wasm_memory_persistence = opt keep` install option). With EOP, you rarely need to touch stable memory at all; Motoko programmers use stable variables mostly as an *intent marker* rather than a serialization mechanism. Stable memory (via `Region`) is still useful for truly large or legacy data.

## Example

```motoko
// Motoko: stable variable + explicit Region.
import Region "mo:core/Region";

persistent actor Store {
  stable var counter : Nat = 0;                  // implicit-stable under `persistent`
  var log : Region = Region.new();               // also stable under `persistent`

  public func bump() : async Nat {
    counter += 1;
    counter
  };
}
```

```rust
// Rust: ic-stable-structures BTreeMap that survives upgrades with no hooks.
use ic_stable_structures::{DefaultMemoryImpl, StableBTreeMap, memory_manager::{MemoryId, MemoryManager}};
use std::cell::RefCell;

thread_local! {
  static MM: RefCell<MemoryManager<DefaultMemoryImpl>> =
    RefCell::new(MemoryManager::init(DefaultMemoryImpl::default()));

  static MAP: RefCell<StableBTreeMap<u64, String, _>> =
    RefCell::new(StableBTreeMap::init(MM.with(|m| m.borrow().get(MemoryId::new(0)))));
}
```

## Gotchas

- **Heap vs stable is still your choice** — even with EOP, very large or append-only datasets belong in stable memory / `Region` / `ic-stable-structures` to keep upgrade compatibility checks fast and avoid hitting instruction limits in `pre_upgrade`.
- **Manual layout in `Region`** — Motoko's `Region` API is byte-addressed. You track offsets yourself; overlapping writes corrupt data silently.
- **`Region` only grows** — there is no shrink. Budget pages carefully; a failed `grow` returns `0xFFFF_FFFF_FFFF_FFFF`, not a trap.
- **Access cost** — reading/writing stable memory is meaningfully more expensive (in [[cycles]] and instructions) than touching the Wasm heap. Use it for persistence, not as a hot cache.
- **Classical persistence still exists** — projects compiled with `--legacy-persistence` in `moc` still use the serialize-on-upgrade path, and hit IC instruction limits on large heaps. Don't opt into it unless you have a reason. See [[upgrade-hooks]].
- **Rust requires discipline** — in Rust there is no orthogonal persistence at all; anything not in `ic-stable-structures` (or explicitly copied in `#[pre_upgrade]`) is lost on upgrade.

## See also

- [[upgrade-hooks]]
- [[canisters]]
- [[motoko]]
- [[rust-cdk]]
- [[cycles]]
