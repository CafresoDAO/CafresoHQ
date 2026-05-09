---
title: SNS Canister Set
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-canisters
  - icp/governance/sns
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://github.com/dfinity/ic/tree/master/rs/sns
related:
  - "[[sns]]"
  - "[[sns-launch]]"
  - "[[sns-neurons-and-voting]]"
  - "[[canisters]]"
  - "[[principals]]"
  - "[[cycles]]"
difficulty: intermediate
open_questions:
  - Exact inter-canister call patterns between Root ↔ Governance ↔ Ledger (useful for building SNS-integrated tooling).
  - Current ICRC standards implemented by the SNS Ledger beyond ICRC-1/2 (e.g. ICRC-3 block log) — verify per release.
---

# SNS Canister Set

> An SNS is not a single canister but a fixed cluster — **Root**, **Governance**, **Ledger**, **Index**, **Swap**, and **Archive** — each with a narrow responsibility, all governed together.

## Why it exists

Splitting the nervous-system across dedicated canisters keeps concerns (upgrade authority, proposal state, token supply, transaction history, one-off swap logic) isolated so they can be upgraded, audited, and scaled independently — the same separation-of-concerns pattern the NNS itself uses.

## How it works

Each canister is deployed on the SNS subnet by the SNS wasm-modules canister (SNS-W) as part of the launch flow (see [[sns-launch]]). After launch, the cluster is collectively controlled by SNS **Root**, which is in turn controlled by SNS **Governance** — so every management action traces back to a successful SNS proposal.

### Root

- The *controller of controllers* for the SNS cluster.
- Holds controller rights over every other SNS canister **and** over the dapp canister(s) that were handed off to the SNS.
- Executes upgrades on behalf of adopted SNS proposals (e.g. "upgrade SNS Governance to wasm X", "upgrade dapp canister to wasm Y").
- Controlled by SNS Governance.

### Governance

- Holds the nervous-system state: neurons, proposals, votes, following relationships.
- Defines proposal types (e.g. upgrade proposals, nervous-system-parameter changes, motion proposals, treasury transfers) and the logic that executes an adopted proposal by instructing Root.
- Authorises reward distribution to voting neurons from the token supply.
- This is where [[sns-neurons-and-voting]] lives.

### Ledger (ICRC-1 / ICRC-2)

- The token ledger for the SNS's own token: implements the ICRC-1 transfer standard, and typically ICRC-2 approval/allowance.
- Mints the initial token supply per the `sns_init.yaml` distribution (developer / treasury / swap buckets).
- Used by Governance to hold neuron stakes and by Swap to distribute tokens to participants.

### Index

- Provides transaction-history queries over the Ledger (the Ledger itself serves only recent blocks directly).
- Account-keyed indexing so a frontend can fetch an account's history without scanning the whole chain.

### Swap

- Runs the **decentralization swap** exactly once per SNS: collects ICP from participants, closes at the scheduled end time or when the maximum is reached, and on success mints/distributes SNS tokens to participants as a *basket of neurons* (see [[sns-neurons-and-voting]]).
- On failure it refunds collected ICP and triggers return of dapp control to the fallback controllers in the config.
- After the swap finalises, Swap is effectively dormant — the lifecycle event it exists to run has already happened.

### Archive (one or more)

- Ledger *block-archive* canisters. The Ledger spawns Archives as its block log grows so that its own state stays bounded; old blocks live in the Archive canisters and are stitched back into chain-of-blocks queries.
- Transparent to clients; controlled by the Ledger, which is in turn controlled by Root.

## Example

```text
Control graph after launch:

  SNS Governance ──controls──> SNS Root
       ▲
       │ (proposals → adopt → execute)
       │
       └── voted by neurons (holders of SNS token)

  SNS Root ──controls──> { SNS Governance, SNS Ledger, SNS Index,
                           SNS Swap, Archive(s), dapp_canister(s) }
```

## Gotchas

- **Root's controller list is the root of trust.** If Root is misconfigured so that something other than SNS Governance controls it, the DAO property is broken. The launch flow wires this automatically; custom tampering post-launch requires an SNS proposal.
- **Ledger and Index are usually pulled from the shared DFINITY ICRC canister implementations**, not custom-written per SNS — the `ic` repo keeps them separate from `rs/sns/`.
- **Swap is fire-once.** Additional fund-raises (e.g. top-ups after launch) are not "another swap"; they are normal SNS proposals against treasury.
- SNS canister principals (like any [[canisters|canister]]) are [[principals]]. Proposals that refer to SNS canisters refer to them by principal.

## See also

- [[sns]]
- [[sns-launch]]
- [[sns-neurons-and-voting]]
- [[sns-init-config]]
- [[canisters]]
- [[principals]]
