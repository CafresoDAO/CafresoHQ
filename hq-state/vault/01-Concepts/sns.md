---
title: Service Nervous System (SNS)
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21 # Session 5: added cross-links to sns-launch-readiness / sns-tokenomics / sns-testflight / sns-operations / sns-launch-benchmarks; added Neurons'-Fund-vs-swap-bucket gotcha.
tags:
  - icp
  - icp/concept
  - icp/concept/sns
  - icp/governance/sns
source:
  - https://internetcomputer.org/sns
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://github.com/dfinity/ic/tree/master/rs/sns
related:
  - "[[nns]]"
  - "[[sns-canisters]]"
  - "[[sns-init-config]]"
  - "[[sns-launch]]"
  - "[[sns-neurons-and-voting]]"
  - "[[sns-launch-readiness]]"
  - "[[sns-tokenomics]]"
  - "[[sns-testflight]]"
  - "[[sns-operations]]"
  - "[[sns-launch-benchmarks]]"
  - "[[principals]]"
  - "[[canisters]]"
  - "[[cycles]]"
difficulty: intermediate
open_questions:
  - Exact nervous-system parameter defaults (min neuron stake, rejection-fee, voting reward schedule) — change over time and are set per-SNS at launch.
  - Exact current geographic-restriction mechanism in the swap config.
  - Current canonical rules for Neurons' Fund matching — verify per launch date against the NNS proposal that last adjusted NF policy.
---

# Service Nervous System (SNS)

> An SNS is a per-dapp DAO on ICP — the same governance pattern the [[nns|NNS]] uses to govern the Internet Computer itself, instantiated as a set of canisters that take over control of a specific dapp so that token-holders, rather than the original developers, decide its future. See [[nns]] for the protocol-level counterpart.

## Why it exists

Handing a dapp to a DAO normally means rewriting it as on-chain contracts plus an off-chain frontend, then bolting governance onto that via a separate token contract and a snapshot/voting service. ICP already has all of those primitives in the NNS; the SNS is the reusable, NNS-blessed packaging of that pattern so a team can move a [[canisters|canister]]-based dapp from "dev-controlled" to "DAO-controlled" without inventing the governance stack each time.

## How it works

- **Relationship to the NNS** — an SNS is *created by an NNS proposal* (the `CreateServiceNervousSystem` proposal; see [[sns-launch]]). After creation the SNS governs its own dapp independently, but the NNS retains protocol-level authority over the platform (subnets, replica versions, etc.).
- **Canister set** — every SNS is a fixed cluster of canisters: **Root**, **Governance**, **Ledger** (ICRC-1/2), **Index**, **Swap**, and one or more **Archive** canisters. See [[sns-canisters]] for the responsibilities of each.
- **Decentralization lifecycle** — three stages:
  1. **Dev-controlled.** The team builds and operates the dapp normally. Before launch, NNS Root is added as a *co-controller* of the dapp canister(s) so that the later hand-off can be automated.
  2. **NNS-controlled (transient).** The NNS adopts the `CreateServiceNervousSystem` proposal; the system deploys the SNS canisters and transfers sole control of the dapp from the dev team to SNS Root. The SNS sits in a restricted "pre-decentralization-swap mode" until the swap runs.
  3. **DAO-controlled.** The decentralization swap distributes the SNS token to participants, who receive it staked as a *basket of neurons* with varying dissolve delays. Governance transitions to "normal mode" — every subsequent decision is made by SNS proposal and neuron vote (see [[sns-neurons-and-voting]]).
- **Configuration** — the whole nervous-system is parameterised up-front via a YAML file (conventionally `sns_init.yaml`) plus the `CreateServiceNervousSystem` NNS proposal; see [[sns-init-config]].
- **Failure mode** — if the swap fails to meet its minimum, collected ICP is refunded and sole control of the dapp returns to the *fallback controllers* the config named (typically the original dev team).

## Example

```text
Phase 1 (dev)
  dapp_canister.controllers = { dev_principal }

Phase 2 (pre-launch handoff)
  dapp_canister.controllers = { dev_principal, nns_root_principal }
  -> NNS proposal CreateServiceNervousSystem is adopted
  -> SNS-W deploys { sns_root, sns_governance, sns_ledger, sns_index, sns_swap }
  dapp_canister.controllers = { sns_root_principal }

Phase 3 (post-swap)
  SNS governance mode = Normal
  token holders vote via neurons
```

## Gotchas

- **SNS is not a library you import** — it's a managed cluster launched by an NNS proposal. You cannot "deploy an SNS" unilaterally to mainnet the way you deploy a regular canister; the `CreateServiceNervousSystem` NNS vote is mandatory. Local testing (test-flight / local-replica SNS) is the unilateral path. See [[sns-launch]].
- **Irreversible** — once the swap succeeds, the dev team no longer controls the dapp. Everything operational (upgrades, cycle top-ups, parameter changes) must route through SNS proposals.
- **Cycles still apply** — SNS canisters consume [[cycles]] like any other canister; the SNS treasury / developer allocation is what ultimately funds operations.
- **Different from NNS neurons** — SNS neurons hold the SNS's own token and only vote on that SNS's proposals. They are *not* interchangeable with NNS neurons.
- **Neurons' Fund ≠ swap bucket.** The Neurons' Fund is an *ICP co-contributor* to the decentralization swap on behalf of opted-in NNS neurons; it is not a separate supply bucket in the SNS token. The swap's SNS-token allocation is fixed by `sns_init.yaml`; NF participation changes who holds it and the size of the ICP pot raised, not the supply split itself. See [[sns-tokenomics]].
- **Launch is a one-shot atomic event.** Every readiness check happens *before* the `CreateServiceNervousSystem` NNS vote — there is no "fix it up after adoption" window between adoption and swap-open. See [[sns-launch-readiness]] for the pre-flight checklist; [[sns-testflight]] for dry-running the flow first; and [[sns-operations]] for the post-launch operating model.

## See also

- [[nns]]
- [[sns-canisters]]
- [[sns-init-config]]
- [[sns-launch]]
- [[sns-neurons-and-voting]]
- [[sns-launch-readiness]]
- [[sns-tokenomics]]
- [[sns-testflight]]
- [[sns-operations]]
- [[sns-launch-benchmarks]]
- [[canisters]]
- [[principals]]
- [[cycles]]
