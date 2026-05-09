---
title: Local Replica
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/local-replica
  - icp/deployment/local-replica
source:
  - https://internetcomputer.org/docs/building-apps/developer-tools/dfx/
  - https://github.com/dfinity/sdk
related:
  - "[[dfx]]"
  - "[[canisters]]"
  - "[[mainnet-deploy]]"
  - "[[cycles]]"
  - "[[principals]]"
  - "[[subnets]]"
difficulty: beginner
open_questions:
  - Which system-level features currently require `dfx start` flags (e.g. Bitcoin integration, threshold-ECDSA/Schnorr, canister HTTP outcalls) and which are on by default in the latest dfx.
  - Exact differences in the randomness / time sources exposed by a single-node replica vs. a real [[subnets|subnet]].
---

# Local Replica

> The local replica is a single-node, in-process version of the Internet Computer that `dfx start` boots on your machine — enough to build, install, upgrade, and call [[canisters]] exactly the way you will on mainnet, but without consensus, fees settled on-chain, or the full subnet-level feature set.

## Why it exists

Round-tripping to mainnet for every code change would be slow, expensive, and publicly visible. The local replica is the develop/test loop: iterate on a [[canisters|canister]] locally, throw state away freely, and only pay real [[cycles]] once the canister behaves. It runs the same replica binaries and presents the same system API, so a working local build is a realistic signal that the Wasm will install on mainnet.

## How it works

- **Boot** — `dfx start` launches the replica plus supporting services (the HTTP gateway, the local state dir under `.dfx/`). `dfx start --background` returns control to the shell; `dfx start --clean` wipes `.dfx/` first. `dfx stop` shuts it all down. See [[dfx]].
- **Single node** — the local network is one replica, so there is no consensus round-trip on `update` calls. Messages still go through the scheduler and the same execution layer, but latency is local-loopback rather than finality-bound.
- **Local canister IDs** — the first `dfx deploy` allocates canister IDs from a local range and writes them to `.dfx/local/canister_ids.json`. These IDs are specific to the local state directory; they do not match (and cannot be transferred to) the canister IDs a mainnet deploy will produce. Mainnet IDs live in `canister_ids.json` at the project root.
- **Local identities / principals** — `dfx identity` still manages keypairs, and every call is signed as a [[principals|principal]], exactly as on mainnet. The practical difference is that local identities have no real-world stake — the "default" dev identity is unencrypted and fine for local work, but should not be used for mainnet.
- **Cycles on local** — local deploys are funded from a local cycles faucet (the replica mints freely on the local network). `dfx canister status` still reports a balance; it is just not denominated in anything that costs money. See [[cycles]].
- **Assets** — frontend/asset canisters work the same locally and are reachable via the local HTTP gateway (`http://<canister-id>.localhost:<port>` or the legacy `?canisterId=` query style). See [[asset-canister]].

## What differs from mainnet

Local is a faithful-but-reduced model of the IC. Known asymmetries to plan around:

- **Determinism and consensus** — a single-node replica is trivially "deterministic" across its one replica. Mainnet determinism is a multi-replica invariant; code that is accidentally non-deterministic (unbounded iteration over a `HashMap` in insertion-order-dependent ways, time-based branches, etc.) can pass locally and diverge between replicas on mainnet. See [[subnets]].
- **Subnet features** — mainnet canisters live on a specific subnet type (application, system, fiduciary). Per-subnet capabilities — chain-key signing (threshold ECDSA / Schnorr), Bitcoin integration, canister HTTP outcalls, per-subnet storage ceilings — are gated behind subnet features and may not be enabled in a default `dfx start`. Some require explicit flags or local mocks to exercise.
- **HTTP outcalls** — on mainnet, canister-originated HTTPS requests are replicated across every node in the subnet and consensus-combined. A single-node local replica cannot reproduce the replication semantics; even when `dfx start` enables outcalls, the failure modes (non-idempotent endpoints, response-size limits) behave differently.
- **Randomness** — `ic0.raw_rand` on mainnet is sourced from the subnet's chain-key randomness beacon. Locally the source is a replica-local RNG; it is random enough to smoke-test code paths but is not the same adversary model.
- **Time and clocks** — mainnet time is the consensus clock of the subnet (block time rounded to the nearest checkpoint); locally it is simply wall-clock on your box. Code that expects monotonicity or round-level time granularity should be re-tested on mainnet.
- **Cost** — local is free, mainnet is not. Cycle balances, freezing thresholds, and storage ceilings are trivially satisfied locally; mainnet economics are a separate concern. See [[cycles-wallet]] and [[mainnet-deploy]].

## Example

```bash
# Start a clean local replica in the background.
dfx start --background --clean

# Deploy the project to the local network (the default target).
dfx deploy

# Inspect the local canister IDs allocated for this project.
cat .dfx/local/canister_ids.json

# Call an update method as the current dfx identity's principal.
dfx canister call my_backend increment

# Tear it all down.
dfx stop
```

## Gotchas

- `.dfx/` is local-only state, not source. Do not check it in; `dfx start --clean` deletes it, and anything you stored in a local canister goes with it.
- Local canister IDs are **not** mainnet canister IDs. Hardcoding an ID from `.dfx/local/` into frontend code will break the first time you deploy to `--network ic`.
- The default dev identity is unencrypted. If you reuse it for mainnet you are one lost laptop away from losing control of the canister — create and use a separate identity for mainnet. See [[mainnet-deploy]].
- "It worked locally" is necessary but not sufficient — subnet-level features and cost behave differently. Plan a dedicated mainnet smoke-test before relying on them.
- Upgrading between `dfx` versions can require `dfx start --clean` because the local state schema changes between releases.

## See also

- [[dfx]]
- [[canisters]]
- [[mainnet-deploy]]
- [[cycles]]
- [[principals]]
- [[subnets]]
- [[asset-canister]]
