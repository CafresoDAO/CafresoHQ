---
title: Hello Canister (Motoko)
type: tutorial
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/tutorial
  - lang/motoko
  - icp/tool/dfx
prerequisites:
  - "[[dfx]]"
  - "[[motoko]]"
  - "[[canisters]]"
difficulty: beginner
estimated_minutes: 15
source:
  - https://internetcomputer.org/docs/building-apps/getting-started/hello-world
  - https://internetcomputer.org/docs/motoko/home
---

# Hello Canister (Motoko)

## Goal

By the end of this tutorial you will have a Motoko [[canisters|canister]] running on a [[local-replica]], and you will be able to call its `greet` method from the CLI and see a response.

## Prerequisites

- `dfx` installed — see [[dfx]]. Verify with `dfx --version`.
- Basic terminal familiarity.
- Nothing else — `dfx` ships with the Motoko compiler, so you do not need to install Motoko separately.

## Steps

### 1. Scaffold a new project

```bash
dfx new hello_world
cd hello_world
```

When prompted, pick the **Motoko** backend. `dfx` generates a project with:

- `dfx.json` — build/deploy manifest.
- `src/hello_world_backend/main.mo` — the Motoko canister source.
- `src/hello_world_frontend/` — an asset canister (you can ignore it for this walkthrough).

### 2. Inspect the generated canister

Open `src/hello_world_backend/main.mo`. It should look roughly like:

```motoko
actor {
  public query func greet(name : Text) : async Text {
    return "Hello, " # name # "!";
  };
};
```

A `query` method is read-only and fast — a single replica answers. An `update` method goes through consensus. See [[canisters]] for the distinction.

### 3. Start the local replica

In a separate terminal (or the same one with `--background`):

```bash
dfx start --background --clean
```

`--clean` wipes any previous local state under `.dfx/`, which is useful when starting fresh. See [[local-replica]].

### 4. Deploy

From the project root:

```bash
dfx deploy
```

This compiles `main.mo` to Wasm, creates the canister, installs the Wasm, and prints the canister IDs. The first deploy also funds the canister with a small pool of [[cycles]] from your local wallet.

### 5. Call the greet method

```bash
dfx canister call hello_world_backend greet '("world")'
```

Expected output:

```
("Hello, world!")
```

Try a different argument:

```bash
dfx canister call hello_world_backend greet '("ICP")'
# ("Hello, ICP!")
```

## Verify

```bash
# Confirm the canister is running and has cycles.
dfx canister status hello_world_backend
```

You should see `Status: Running`, a controller [[principals|principal]] (your dev identity), and a non-zero cycles balance.

## What just happened

1. `dfx new` generated a Motoko actor and a `dfx.json` telling `dfx` how to build it.
2. `dfx start` spun up a single-node replica on your machine.
3. `dfx deploy` compiled Motoko → Wasm, created a canister on the local replica, installed the Wasm, and registered its Candid interface.
4. `dfx canister call` sent a signed Candid-encoded request as your dev identity's [[principals|principal]]; the replica routed it to the canister; the canister returned a Candid-encoded reply; `dfx` decoded it.

## Next

- Convert `greet` to an `update` call and observe the latency difference.
- Follow [[counter-with-upgrade-hooks]] — a counter that survives upgrades via `stable var` and (optionally) [[upgrade-hooks]].
- Try the same exercise in Rust — see [[rust-cdk]].
