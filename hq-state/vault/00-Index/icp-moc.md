---
title: ICP Map of Content
type: moc
status: active
created: 2026-04-21
updated: 2026-04-21 # Session 5: added SNS operations layer (readiness, tokenomics, testflight, operations, benchmarks); added [[tokenomics-100m-analysis]] to Projects; added [[sns-end-to-end-launch]] to Tutorials.
tags:
  - icp
  - moc
  - index
---

# ICP Map of Content

Top-level map. The sub-agent expands each branch over time by adding linked atomic notes in `01-Concepts/`.

Notes marked below with a ✓ have a drafted atomic note; unmarked links are stubs for future sessions.

## Core Architecture

- ✓ [[canisters]] — WebAssembly-based smart contracts
- ✓ [[subnets]] — groups of node machines running canisters
- ✓ [[cycles]] — the gas/fuel for computation and storage
- ✓ [[principals]] — identity primitives
- [[replica]] — the ICP node software
- [[consensus]] — threshold-based consensus protocol

## Development Stack

- ✓ [[motoko]] — ICP-native language
- ✓ [[rust-cdk]] — Rust canister development kit
- [[azle]] — TypeScript CDK
- [[kybra]] — Python CDK
- ✓ [[dfx]] — the ICP CLI
- ✓ [[candid]] — interface description language & wire format for canister calls

## Patterns

- ✓ [[inter-canister-calls]]
- ✓ [[stable-memory]]
- ✓ [[upgrade-hooks]]
- [[http-outcalls]]
- [[threshold-ecdsa]]
- [[chain-fusion]] — BTC / ETH integration
- ✓ [[internet-identity]]

## Deployment

- ✓ [[local-replica]] — `dfx start`, local canister IDs, and the ways a single-node replica diverges from mainnet
- ✓ [[mainnet-deploy]] — `dfx deploy --network ic`, controllers, identities, and the first-deploy control graph
- ✓ [[cycles-wallet]] — cycles ledger (current) vs. the legacy wallet canister, CMC top-ups, XDR pricing
- ✓ [[asset-canister]] — prebuilt asset canister, `"type": "assets"`, certified serving, SPA fallback

## Governance

- ✓ [[sns]] — per-dapp DAOs on ICP; the NNS-pattern packaged for individual services
- ✓ [[sns-canisters]] — Root / Governance / Ledger / Index / Swap / Archive
- ✓ [[sns-init-config]] — the `sns_init.yaml` configuration surface
- ✓ [[sns-launch]] — `CreateServiceNervousSystem` proposal → handoff → swap → normal mode
- ✓ [[sns-neurons-and-voting]] — staking, dissolve delay, following, proposal types
- ✓ [[nns]] — the root DAO of the protocol: Governance, Registry, ICP Ledger, CMC, Root, Lifeline, Genesis Token
- ✓ [[sns-launch-readiness]] — pre-flight checklist: dapp maturity, controllers, audits, tokenomics, community review, neuron / follow-graph planning
- ✓ [[sns-tokenomics]] — the allocation knobs (supply, swap, treasury, dev, NF, airdrops, vesting, dissolve delays) and each knob's governance effect
- ✓ [[sns-testflight]] — dry-running the full launch flow against local replica / staging before the real NNS proposal
- ✓ [[sns-operations]] — post-launch operating manual: upgrades, treasury, emergencies, metrics
- ✓ [[sns-launch-benchmarks]] — reference table of publicly-launched SNSs (rows unverified until populated from dashboard + forum payloads)

## Projects

- ✓ [[notes-dapp]] — minimal per-user notes dapp (Motoko + React + II + stable memory + asset canister); baseline spec for the deployment branch
- ✓ [[tokenomics-100m-analysis]] — analysis of the user's proposed 100M / 15 dev / 30 swap / 55 treasury SNS split against [[sns-tokenomics]] and [[sns-launch-benchmarks]]

## Tutorials

- ✓ [[hello-canister-motoko]] — scaffold, deploy, and call a Motoko canister on the local replica
- ✓ [[counter-with-upgrade-hooks]] — a Motoko counter that survives upgrades via stable vars + pre/post hooks
- ✓ [[sns-init-yaml-walkthrough]] — scaffold, validate, and understand an `sns_init.yaml` with the SNS CLI
- ✓ [[ship-to-mainnet]] — end-to-end: `dfx new` → local test → mainnet identity → cycles funding → `dfx deploy --network ic` → verify
- ✓ [[sns-end-to-end-launch]] — end-to-end SNS launch walkthrough: register with NNS → draft `sns_init.yaml` → validate → testflight → `CreateServiceNervousSystem` proposal → swap → handoff
