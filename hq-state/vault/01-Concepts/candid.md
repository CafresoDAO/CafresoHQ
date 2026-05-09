---
title: Candid
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/candid
  - icp/tool/candid
source:
  - https://internetcomputer.org/docs/building-apps/interact-with-canisters/candid/candid-concepts
  - https://internetcomputer.org/docs/building-apps/interact-with-canisters/candid/using-candid
  - https://internetcomputer.org/docs/references/candid-ref
  - https://internetcomputer.org/docs/motoko/icp-features/candid-serialization
  - https://github.com/dfinity/candid
related:
  - "[[canisters]]"
  - "[[motoko]]"
  - "[[rust-cdk]]"
  - "[[inter-canister-calls]]"
  - "[[dfx]]"
difficulty: beginner
---

# Candid

> Candid is ICP's **interface description language (IDL)** and wire format: a `.did` file describes a [[canisters|canister]]'s public methods and their argument/return types, and a binary encoding transports those values between caller and callee regardless of source language.

## Why it exists

A canister written in Motoko needs to be callable from a frontend written in TypeScript, a backend written in Rust, or another canister written in whatever CDK. Without a common type-and-wire language, every pair would need its own serializer. Candid fills that slot: one IDL, one encoding, one set of subtyping rules for upgrade compatibility. It is ICP's equivalent of Protobuf + gRPC rolled into one, but designed around the particulars of canister execution (async methods, `query` annotations, actor references, cycles).

## How it works

- **`.did` file** — a textual service description. Example:

  ```candid
  service counter : {
    inc   : () -> ();
    read  : () -> (nat) query;
    write : (nat) -> ();
  }
  ```

  Each method has a parameter tuple, a return tuple, and optional annotations (`query`, `oneway`, `composite_query`).
- **Type system** — primitives (`nat`, `int`, `text`, `bool`, `blob`, `principal`), composites (`record`, `variant`, `opt`, `vec`), service/function references, and `null`/`reserved`/`empty` edge cases. Records use **named fields** with a hash-based ordering, which is what allows fields to be added without breaking old clients.
- **Wire format** — a self-describing binary encoding: type table + value table. Canisters include it as the `candid:service` section of the Wasm metadata so tooling can discover the interface:
  ```bash
  dfx canister metadata <canister-id> candid:service --network ic
  ```
- **Language mapping** — every supported CDK provides a Candid ↔ native-type bridge:
  - **Motoko** — actor signatures *are* the Candid interface; `moc` auto-generates the `.did`. Runtime conversion is implicit at call boundaries, plus explicit `to_candid(...)` / `from_candid(...)` operators for dynamic cases.
  - **Rust** — the `candid` crate provides `CandidType` + `Deserialize` derives; `ic_cdk::export_candid!()` emits the interface from the compiled Wasm. For consumers, `candid_parser` plus `ic-agent` generates typed bindings from a `.did`.
- **Subtyping and upgrades** — Candid's rules define when a new interface is a **subtype** of an old one (roughly: you can add optional fields, variant cases, and new methods; you cannot rename or remove required fields). `dfx deploy` runs this check and blocks breaking upgrades unless overridden. The standalone `didc check file1.did file2.did` tool performs the same check.
- **Tooling** — `didc` (compiler + checker), `@dfinity/candid` (JS), `candid-extractor` (recover `.did` from a Wasm), Candid UI (the auto-generated web form at `<canister-id>.ic0.app/_/candid` / Candid Playground).

## Example

```did
// counter.did — Candid interface for a simple counter canister.
type Count = nat;

service : {
  inc   : () -> (Count);
  read  : () -> (Count) query;
  write : (Count) -> ();
}
```

```bash
# Call a method from the CLI; dfx parses Candid args + prints Candid reply.
dfx canister call counter write '(42 : nat)'
dfx canister call counter read
# -> (42 : nat)
```

```motoko
// Dynamic Candid encoding in Motoko.
import { call } "mo:core/InternetComputer";

let args : Blob = to_candid(["a", "b", "c"]);
let reply : Blob = await call(target, "concat", args);
let ?out : ?Text = from_candid(reply);
```

## Gotchas

- **`to_candid` is not canonical.** The same Motoko value can produce different `Blob` encodings; never use `to_candid` output as a hash key or for equality comparison.
- **Field names are hashed.** Candid records are identified by a 32-bit hash of the field name, so `{ id = 1; name = "a" }` and `{ name = "a"; id = 1 }` are the same record — but collisions, while astronomically rare, exist. Stick to descriptive ASCII names.
- **`opt` composes awkwardly with subtyping.** Adding a `variant` case or changing an `opt T` to `T` is a breaking change in subtle ways; run `didc check` before every production upgrade.
- **Tuple vs single-argument.** CDKs generally expect a *tuple* of arguments. `dfx canister call c m '(1)'` passes one `nat`; `'(1, 2)'` passes two. A method declared `(record { a : nat; b : nat })` takes one *record* argument, not two positionals.
- **Raw binary is allowed.** ICP does not enforce Candid — two canisters can agree on any byte format — but tooling and third-party integrations assume Candid. Rolling your own wire format makes the canister nearly unusable from Candid UI, agents, and block explorers.
- **Query annotations leak.** A method declared `query` in Candid but `update` in source (or vice-versa) surfaces as a mismatch at call time. Regenerate the `.did` after interface changes; don't hand-patch it.

## See also

- [[canisters]]
- [[inter-canister-calls]]
- [[motoko]]
- [[rust-cdk]]
- [[dfx]]
