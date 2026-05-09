---
title: SNS Launch Lifecycle
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21 # Session 5: cross-linked sns-launch-readiness, sns-tokenomics, sns-testflight, sns-operations, sns-launch-benchmarks, sns-end-to-end-launch. Added swap-minimum-vs-NF nuance to gotchas.
tags:
  - icp
  - icp/concept
  - icp/concept/sns-launch
  - icp/governance/sns
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://internetcomputer.org/sns
related:
  - "[[sns]]"
  - "[[sns-canisters]]"
  - "[[sns-init-config]]"
  - "[[sns-neurons-and-voting]]"
  - "[[sns-launch-readiness]]"
  - "[[sns-tokenomics]]"
  - "[[sns-testflight]]"
  - "[[sns-operations]]"
  - "[[sns-launch-benchmarks]]"
  - "[[sns-end-to-end-launch]]"
  - "[[nns]]"
  - "[[principals]]"
  - "[[cycles]]"
difficulty: intermediate
open_questions:
  - Current minimum waiting period between NNS proposal execution and swap open (the docs state "at least 24 hours" for the 1-proposal model; verify this has not changed).
  - How failed swaps interact with Neurons' Fund matching contributions on refund.
---

# SNS Launch Lifecycle

> An SNS is launched by a single `CreateServiceNervousSystem` NNS proposal; adoption automatically deploys the SNS canister cluster, hands off dapp control, runs the decentralization swap, and — on success — flips the SNS into normal DAO-governed operation.

## Why it exists

Launching a DAO for a live dapp is a sequencing problem. You need the dapp's controllership to move atomically from devs to the DAO, the token supply to be minted in lockstep with that hand-off, the public fundraise to run under known rules, and the whole thing to be reversible if the swap fails. The SNS launch lifecycle is the protocol-level encoding of that sequence so it runs deterministically from one NNS vote.

## How it works

### Preconditions (dev-side, before the NNS vote)

- The dapp is deployed as one or more [[canisters]] controlled by the dev team.
- An `sns_init.yaml` has been authored and locally validated (see [[sns-init-config]]).
- **NNS Root is added as a co-controller of every dapp canister** that will be handed to the SNS. Without this, the automated transfer in later stages cannot execute.
- The config names **fallback controllers** — the principals that reclaim sole control if the swap fails.
- Community review on forum.dfinity.org is the conventional (not protocol-enforced) step before submission.

### The proposal

- The single NNS proposal type is **`CreateServiceNervousSystem`**, carrying the validated config as its payload.
- If the NNS **rejects** it, nothing moves — the dapp remains dev-controlled and the team can iterate on the config and re-submit.
- If the NNS **adopts** it, the automated phases below execute in order without further intervention.

### Automated deployment

- The NNS's SNS-wasm-modules canister (**SNS-W**) deploys the SNS canister cluster on the SNS subnet: Swap, Governance, Ledger, Root, Index. See [[sns-canisters]].
- Ownership of every dapp canister transitions from `{dev, nns_root}` to `{sns_root}` alone.
- The SNS enters **pre-decentralization-swap mode**, a restricted state where only a limited set of governance actions are permitted — neurons can't transact freely yet.

### Decentralization swap

- A timing gate ensures a waiting period between proposal execution and swap open so participants have time to prepare (the docs state *at least 24 hours* for the 1-proposal model).
- The **Swap** canister opens at the scheduled start time and collects ICP from participants until its end time or its maximum-ICP cap, whichever comes first.
- On success — minimum-ICP threshold reached — the swap **finalises**: ICP is distributed per the tokenomics (developer / treasury / swap buckets); participants receive their purchased tokens as a *basket of neurons* with varying dissolve delays (see [[sns-neurons-and-voting]]); SNS Governance flips to **Normal mode**.
- On failure — minimum not met — ICP is refunded to participants and sole control of the dapp returns to the fallback controllers the config named.

## Example

```text
Proposal: CreateServiceNervousSystem
Adopt?  ── NO ──> dapp stays with dev team (no SNS created)
        ── YES ─┐
                ▼
         SNS-W deploys SNS cluster on SNS subnet
                │
                ▼
         dapp controllers := { sns_root }
         SNS governance mode := pre-decentralization-swap
                │
                ▼ (wait ≥ scheduled pre-open window)
         Swap opens ──> participants send ICP
                │
                ▼ (end time OR max ICP reached)
         min ICP met? ── NO ──> refund, dapp returns to fallback controllers
                         YES ─> distribute tokens as neuron baskets,
                                SNS governance := Normal
```

## Gotchas

- **The NNS proposal is not free.** Submitting it costs the NNS proposal rejection fee if it fails to pass, so local `sns init-config-file validate` and a forum review round are the cheap pre-checks.
- **The co-controller step is easy to forget.** If NNS Root is not a co-controller of the dapp canister when the proposal executes, the handoff fails — you do not want to discover this between `adopt` and `execute`.
- **Post-launch you can't redeploy the dapp from dfx.** Every upgrade to the dapp canister is now an SNS proposal routed through Root.
- **A failed swap is recoverable**, a succeeded-and-regretted swap is not. Tokenomics and fallback controllers deserve more review than any other config section. See [[sns-tokenomics]] and [[sns-launch-readiness]].
- **Cycles still matter.** SNS canisters consume [[cycles]]; top-ups post-launch are normally funded from the SNS treasury via SNS proposal (see [[sns-operations]]).
- **"Minimum raise" ≠ "minimum decentralization".** `min_icp_e8s`-style is a financial floor (the swap aborts below it), not a participant-count floor. A small minimum can be met by a small number of large participants and still technically "succeed" — the Neurons' Fund match, per-participant caps, and swap duration are what actually spread the swap bucket across a wide holder base. See [[sns-tokenomics]].
- **Rehearse before submitting.** The 1-proposal flow is atomic; the cheapest way to discover misconfigurations is [[sns-testflight]], *before* an NNS proposal fee is spent.

## See also

- [[sns]]
- [[sns-canisters]]
- [[sns-init-config]]
- [[sns-neurons-and-voting]]
- [[sns-launch-readiness]]
- [[sns-tokenomics]]
- [[sns-testflight]]
- [[sns-operations]]
- [[sns-launch-benchmarks]]
- [[sns-end-to-end-launch]]
- [[nns]]
- [[principals]]
- [[cycles]]
