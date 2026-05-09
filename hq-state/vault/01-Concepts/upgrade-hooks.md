---
title: Upgrade Hooks
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/upgrade-hooks
  - icp/pattern/upgrade-hooks
source:
  - https://internetcomputer.org/docs/motoko/icp-features/system-functions
  - https://internetcomputer.org/docs/motoko/fundamentals/actors/data-persistence
  - https://internetcomputer.org/docs/motoko/fundamentals/actors/orthogonal-persistence/enhanced
  - https://github.com/dfinity/motoko
  - https://github.com/dfinity/cdk-rs
related:
  - "[[canisters]]"
  - "[[stable-memory]]"
  - "[[motoko]]"
  - "[[rust-cdk]]"
difficulty: intermediate
open_questions:
  - Exact instruction / cycle budget applied to `pre_upgrade`-phase execution, which varies by subnet and dfx / replica version.
---

# Upgrade Hooks

> Upgrade hooks are the two system-defined callbacks a [[canisters|canister]] can export — `pre_upgrade` (run in the *old* Wasm, just before the new module is installed) and `post_upgrade` (run in the *new* Wasm, immediately after install) — that let developers bridge state across an upgrade when automatic persistence is insufficient.

## Why it exists

When a canister is upgraded, the replica installs a new Wasm module against the same canister ID. By default (in the classical persistence model and in Rust) the **Wasm heap is reset**; only [[stable-memory]] carries over. Any runtime state that lived in the heap — a `HashMap`, a counter, an in-memory index — would be lost. Upgrade hooks are the serialization seam: `pre_upgrade` copies that state into stable storage, and `post_upgrade` reconstitutes it after the new module is running.

Under Motoko's **Enhanced Orthogonal Persistence (EOP)**, the *entire* main memory is retained across upgrades — so upgrade hooks become optional and, per DFINITY's own docs, **discouraged**.

## How it works

- **Motoko — `preupgrade` / `postupgrade`** — declared as actor system functions: `system func preupgrade() { ... }` and `system func postupgrade() { ... }`. They run synchronously in the old / new image respectively, and **cannot send messages** (no `await`).
- **Rust CDK — `#[pre_upgrade]` / `#[post_upgrade]`** — attributes from `ic-cdk-macros` on free functions with signature `fn() -> ()`. Inside, you typically `ic_cdk::storage::stable_save((state,))` and `stable_restore`, or serialise to stable memory via `ic-stable-structures`.
- **Ordering** — `pre_upgrade` runs in the old Wasm *after* the canister is stopped for upgrade; the new Wasm is then installed; `post_upgrade` runs in the new Wasm before any regular ingress message is served.
- **Failure is fatal** — if `pre_upgrade` traps or runs out of cycles/instructions, the **upgrade is aborted** and the canister stays on the old image. If `post_upgrade` traps, the upgrade is rolled back and the *new* image is never committed; the canister remains on the old version. DFINITY explicitly warns that a trapping `pre_upgrade` on a canister whose state is too large to serialise within instruction limits can leave the canister unupgradeable — the classic "brick" scenario.
- **Motoko EOP** — with EOP enabled (default since Motoko v0.13.x), Motoko keeps the persistent heap as-is. Stable variables survive automatically; no `pre_upgrade`/`postupgrade` is required. The runtime performs a **compatibility check** on the upgraded program's stable signature and rolls back if the new types aren't stable-compatible.
- **`persistent actor` keyword** — Motoko ≥ 0.13.5: prefixing the actor declaration with `persistent` makes every `let` / `var` implicitly `stable`. Only `transient` fields need explicit annotation. This is the recommended style and eliminates most upgrade-hook uses.
- **IC upgrade option** — the install call takes `wasm_memory_persistence`: `opt keep` preserves main memory (required for EOP), `null` / `replace` drops it (classical model). `dfx` sets this based on the canister's declared persistence mode.

## Example

```motoko
// Discouraged classical pattern — only needed when NOT using EOP / persistent actor.
import HashMap "mo:base/HashMap";
import Iter    "mo:base/Iter";
import Text    "mo:base/Text";

actor Token {
  transient var balances =
    HashMap.HashMap<Text, Nat>(10, Text.equal, Text.hash);
  stable var savedBalances : [(Text, Nat)] = [];

  system func preupgrade() {
    savedBalances := Iter.toArray(balances.entries());
  };

  system func postupgrade() {
    balances :=
      HashMap.fromIter(savedBalances.vals(), 10, Text.equal, Text.hash);
    savedBalances := [];
  };
};
```

```rust
// Rust CDK: serialise to stable memory around an upgrade.
use ic_cdk_macros::{pre_upgrade, post_upgrade};
use std::cell::RefCell;

thread_local! { static STATE: RefCell<State> = RefCell::default(); }

#[pre_upgrade]
fn pre_upgrade() {
    STATE.with(|s| ic_cdk::storage::stable_save((s.borrow().clone(),)).unwrap());
}

#[post_upgrade]
fn post_upgrade() {
    let (state,): (State,) = ic_cdk::storage::stable_restore().unwrap();
    STATE.with(|s| *s.borrow_mut() = state);
}
```

## Gotchas

- **Prefer no hooks at all.** Motoko docs state: "The use of upgrade hooks is not recommended as they can fail and cause the program to enter an unrecoverable state." Use stable variables + `persistent actor` in Motoko, or `ic-stable-structures` in Rust.
- **Scale test your `pre_upgrade`.** A `pre_upgrade` that happily serialises 100 KB of state in dev will trap on 10 MB in production. Hooks run under the same instruction budget as a normal message.
- **Traps are silent-until-you-upgrade.** You only discover a broken `pre_upgrade` *at* upgrade time, which is the worst moment. Write a test that drives a canister's state to realistic size, then calls `dfx deploy --mode upgrade` and asserts it succeeds.
- **`post_upgrade` cannot `await`.** Neither hook is an async context. Any migration that *needs* an inter-canister call must happen in a normal `update` called after the upgrade completes.
- **Don't confuse hook direction.** `pre_upgrade` runs in the *old* code with access to its in-memory shape; `post_upgrade` runs in the *new* code and must cope with whatever shape `pre_upgrade` chose to write. The new code must be able to read the old code's serialisation.
- **Graph-copy stabilisation exists as an escape hatch** — Motoko ships `__motoko_stabilize_before_upgrade` / `__motoko_destabilize_after_upgrade` canister methods for migrating enormous EOP heaps across multiple messages. Controller-only, rarely needed.

## See also

- [[stable-memory]]
- [[canisters]]
- [[motoko]]
- [[rust-cdk]]
- [[counter-with-upgrade-hooks]]
