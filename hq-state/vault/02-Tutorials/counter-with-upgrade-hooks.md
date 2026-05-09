---
title: Counter With Upgrade Hooks (Motoko)
type: tutorial
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/tutorial
  - icp/pattern/upgrade-hooks
  - lang/motoko
prerequisites:
  - "[[dfx]]"
  - "[[motoko]]"
  - "[[canisters]]"
  - "[[stable-memory]]"
  - "[[upgrade-hooks]]"
  - "[[hello-canister-motoko]]"
difficulty: beginner
estimated_minutes: 25
source:
  - https://internetcomputer.org/docs/motoko/fundamentals/actors/data-persistence
  - https://internetcomputer.org/docs/motoko/icp-features/system-functions
  - https://internetcomputer.org/docs/motoko/fundamentals/actors/orthogonal-persistence/enhanced
---

# Counter With Upgrade Hooks (Motoko)

## Goal

Build a minimal Motoko [[canisters|canister]] that holds an integer counter, then upgrade the canister twice — once to demonstrate that a **stable variable survives an upgrade**, and once to demonstrate that **`transient` state is wiped unless carried through `preupgrade` / `postupgrade`**. At the end you will understand, by direct observation, why `persistent actor` is the recommended shape for new Motoko canisters.

## Prerequisites

- `dfx` installed and working — verify with `dfx --version`. See [[dfx]].
- You have completed [[hello-canister-motoko]] and can scaffold/deploy a Motoko canister.
- Conceptual background: [[stable-memory]] and [[upgrade-hooks]].

## Steps

### 1. Scaffold a project

```bash
dfx new counter_upgrade --type motoko
cd counter_upgrade
```

### 2. Write the v1 counter (stable variable, no hooks)

Replace `src/counter_upgrade_backend/main.mo` with:

```motoko
// v1 — persistent actor: every `let`/`var` is implicitly stable.
persistent actor Counter {
  var count : Nat = 0;

  public func inc() : async Nat {
    count += 1;
    count
  };

  public query func get() : async Nat { count };
};
```

Notes:

- `persistent actor` (Motoko ≥ 0.13.5) makes `count` implicitly `stable` — equivalent to writing `stable var count : Nat = 0` in a classical actor.
- No `preupgrade` / `postupgrade` is needed. With Enhanced Orthogonal Persistence the entire heap is retained across upgrades, and the compiler additionally checks stable-signature compatibility.

### 3. Deploy and drive it up

```bash
dfx start --background --clean
dfx deploy

dfx canister call counter_upgrade_backend inc    # (1 : nat)
dfx canister call counter_upgrade_backend inc    # (2 : nat)
dfx canister call counter_upgrade_backend inc    # (3 : nat)
dfx canister call counter_upgrade_backend get    # (3 : nat)
```

### 4. Upgrade in place — verify state survives

Edit the canister: change `count += 1` to `count += 2` (or add a new method — anything that is a **compatible** change). Then:

```bash
dfx deploy
```

`dfx` detects an existing canister and issues an upgrade (equivalent to `dfx canister install --mode upgrade`). Re-check the counter:

```bash
dfx canister call counter_upgrade_backend get    # still (3 : nat)
dfx canister call counter_upgrade_backend inc    # (5 : nat) — bumped by 2
```

The counter did not reset — the stable variable was carried across the new Wasm install.

### 5. Demonstrate the hook pattern (classical, for understanding)

Now replace `main.mo` with a classical actor that uses a **`transient`** in-memory map and bridges it with `preupgrade` / `postupgrade`:

```motoko
import HashMap "mo:base/HashMap";
import Iter    "mo:base/Iter";
import Text    "mo:base/Text";

actor Counter {
  // In-memory index of per-user counters.
  transient var counts =
    HashMap.HashMap<Text, Nat>(16, Text.equal, Text.hash);

  // Serialization target — must be `stable` (implicit here would also work
  // under a `persistent` actor; we are deliberately *not* using that).
  stable var saved : [(Text, Nat)] = [];

  public func inc(user : Text) : async Nat {
    let n = switch (counts.get(user)) { case null 0; case (?x) x };
    counts.put(user, n + 1);
    n + 1
  };

  public query func get(user : Text) : async Nat {
    switch (counts.get(user)) { case null 0; case (?x) x }
  };

  system func preupgrade() {
    saved := Iter.toArray(counts.entries());
  };

  system func postupgrade() {
    counts := HashMap.fromIter(saved.vals(), 16, Text.equal, Text.hash);
    saved := [];   // don't keep a second copy
  };
};
```

Deploy, populate, upgrade with a trivial edit, and confirm:

```bash
dfx deploy
dfx canister call counter_upgrade_backend inc '("alice")'   # (1 : nat)
dfx canister call counter_upgrade_backend inc '("alice")'   # (2 : nat)
dfx canister call counter_upgrade_backend inc '("bob")'     # (1 : nat)

# Make a trivial edit (e.g. change the initial HashMap capacity) and redeploy.
dfx deploy

dfx canister call counter_upgrade_backend get '("alice")'   # (2 : nat)
dfx canister call counter_upgrade_backend get '("bob")'     # (1 : nat)
```

Both users' counters survived the upgrade — but only because `preupgrade` copied `counts` into `saved` and `postupgrade` restored it.

### 6. Break it on purpose (optional, instructive)

Delete the `preupgrade` function, add a trivial edit, and `dfx deploy` again. The transient `HashMap` is wiped:

```bash
dfx canister call counter_upgrade_backend get '("alice")'   # (0 : nat)
```

This is the classical-persistence footgun that [[upgrade-hooks]] warns about: forgetting the hook is a silent data-loss event discovered only after the upgrade.

## Verify

```bash
dfx canister status counter_upgrade_backend
```

Confirm `Status: Running`, a non-zero cycles balance, and a module-hash that changed across each upgrade step.

## What you learned

1. Under `persistent actor` (EOP), a plain `var` behaves as a stable variable and survives upgrades with **no hooks**.
2. Under a classical actor, only `stable` fields survive. `transient` state must be serialised in `preupgrade` and rehydrated in `postupgrade`.
3. Hooks run inside the canister's regular instruction / cycle budget; a trapping `preupgrade` aborts the upgrade. Scale-test before trusting them in production.
4. The modern recommendation: **use `persistent actor`** and let EOP handle persistence; reach for hooks only when you must, e.g. reshaping data across a non-backward-compatible type change.

## Next

- Replace the `HashMap` with a `Region` from `mo:core/Region` and manage offsets by hand — exercises the [[stable-memory]] low-level API.
- Rebuild the same counter in Rust using `ic-stable-structures::StableCell` — no hooks required there either. See [[rust-cdk]].
- Read the [[upgrade-hooks]] note for the "when do I absolutely need a hook?" decision tree.
