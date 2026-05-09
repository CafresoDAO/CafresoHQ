---
title: Motoko
type: concept
status: stable
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/language
  - lang/motoko
source:
  - https://internetcomputer.org/docs/motoko/home
  - https://internetcomputer.org/docs/motoko/fundamentals/actors/data-persistence
  - https://internetcomputer.org/docs/motoko/fundamentals/actors/orthogonal-persistence/enhanced
  - https://github.com/dfinity/motoko
related:
  - "[[canisters]]"
  - "[[rust-cdk]]"
  - "[[dfx]]"
  - "[[stable-memory]]"
  - "[[upgrade-hooks]]"
  - "[[candid]]"
  - "[[inter-canister-calls]]"
difficulty: beginner
---

# Motoko

> Motoko is DFINITY's purpose-built language for writing ICP [[canisters]] — an actor-based, strongly-typed language whose compiler and runtime are designed around the constraints of canister execution.

## Why it exists

General-purpose languages make you bolt on canister semantics (async boundaries, orthogonal persistence, stable variables) via a CDK and discipline. Motoko bakes those semantics into the *language*: an actor is a canister, every public method is an async message, and the type system enforces the rules. The goal is to make correct canister code the default and to let the toolchain safety-check upgrades.

## How it works

- **Actors** — the top-level unit is an `actor` (or `actor class`), which compiles to a Wasm canister. Public methods become the canister's [[candid|Candid]] interface.
- **Async messages** — calls between actors return `async T` and are awaited. The compiler prevents smuggling non-shareable values across message boundaries. Query functions are *not* async contexts and cannot `await`. See [[inter-canister-calls]].
- **Orthogonal persistence** — by default, the actor's entire state is persisted automatically between messages. Across *upgrades*, you mark survivors with `stable var`; non-stable state (`transient`) is re-initialized.
- **`persistent actor` (v0.13.5+)** — prefixing `actor` / `actor class` with `persistent` makes every `let`/`var` implicitly `stable`. Only `transient` fields need explicit annotation. This is the recommended style.
- **Enhanced Orthogonal Persistence (EOP)** — since Motoko v0.13.x, EOP is the **default** compilation mode: the canister's entire main memory is retained across upgrades (via the IC install option `wasm_memory_persistence = opt keep`). Upgrade hooks are now discouraged; the runtime instead performs a stable-signature compatibility check and rolls back incompatible upgrades. See [[upgrade-hooks]].
- **Type system** — structural types, generics, pattern matching, variant types, `Result<Ok, Err>`; nulls are opt-in via `?T`. The compiler checks upgrade compatibility against the previous interface using stable-subtyping rules.
- **Core library** — the modern library lives under `mo:core/*` (`mo:core/Nat`, `mo:core/Region`, `mo:core/Principal`, `mo:core/InternetComputer`, etc.); the legacy `mo:base/*` library is still supported but being superseded.
- **Tooling** — compiled by `moc` (shipped with [[dfx]]); the `.did` file is generated automatically from actor signatures. `moc --stable-types` and `--stable-compatible` emit and check `.most` stable-signature files.

## Example

```motoko
import Nat "mo:core/Nat";

persistent actor Counter {
  // Under `persistent`, `n` is implicitly stable — no annotation needed.
  var n : Nat = 0;

  public func inc() : async Nat {
    n += 1;
    n
  };

  public query func get() : async Nat { n };
};
```

## Gotchas

- In non-`persistent` actors, only `stable`-flagged state (or state reachable from it) survives an upgrade. Forgetting `stable` on a big data structure silently wipes it. `persistent actor` eliminates this footgun. See [[upgrade-hooks]].
- Upgrade compatibility is checked at install time against the previous stable signature; a breaking change blocks the upgrade. Under EOP the runtime additionally rolls back incompatible type changes; under classical persistence a trapping `pre_upgrade` can brick the canister.
- The core/base libraries evolve — pin the Motoko toolchain version in `dfx.json` so CI builds are reproducible.
- Legacy classical persistence (`--legacy-persistence`) serialises the heap on upgrade and hits IC instruction limits on large state. EOP avoids that; prefer the default.
- Motoko's GC runs **inside** the canister's cycle budget; for truly large data, bypass the heap and use [[stable-memory]] `Region`s directly.

## See also

- [[canisters]]
- [[rust-cdk]]
- [[dfx]]
- [[stable-memory]]
- [[upgrade-hooks]]
- [[candid]]
- [[inter-canister-calls]]
