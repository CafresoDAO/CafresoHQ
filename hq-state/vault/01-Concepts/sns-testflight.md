---
title: SNS Testflight
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-testflight
  - icp/governance/sns
  - icp/sns/operations
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://github.com/dfinity/ic/tree/master/rs/sns/cli
  - https://forum.dfinity.org
related:
  - "[[sns]]"
  - "[[sns-launch]]"
  - "[[sns-launch-readiness]]"
  - "[[sns-init-config]]"
  - "[[local-replica]]"
  - "[[dfx]]"
difficulty: intermediate
open_questions:
  - Exact current subcommand name and flags on the SNS CLI for the testflight path (historically `sns deploy-testflight` / `sns deploy --network local`; verify against the current release rather than quoting from memory).
  - Whether a public "staging NNS" is currently maintained by DFINITY for dry-run `CreateServiceNervousSystem` proposals, or whether teams spin up their own.
  - Which validations the testflight flow skips relative to the real NNS path (e.g. Neurons' Fund matching, subnet-level SNS-W checks) — these shape what testflight can and cannot catch.
---

# SNS Testflight

> A dry-run path for an SNS launch — deploying the SNS cluster against a non-mainnet target (local replica or staging) using the same `sns_init.yaml` the team will eventually submit, so the full lifecycle (deploy → swap → handoff) can be exercised before any NNS vote is spent.

## Why it exists

The real [[sns-launch]] is atomic and irreversible, and the NNS proposal carries a rejection fee if it fails. A bad YAML field, a missing co-controller, or a misconfigured swap bound discovered *after* adoption has no graceful recovery path — the swap either runs on bad parameters or aborts, and in both cases the team has already burned reputation on the forum. Testflight closes that gap by letting the team exercise the end-to-end flow against throwaway state first: the same `sns_init.yaml`, the same CLI, the same canister graph, but without committing to a public raise. This note stays qualitative because the exact subcommand surface has changed across SNS CLI releases and the authoritative source is the current CLI's `--help` plus the live docs.

## How it works

### What testflight is *not*

- **Not a mainnet SNS.** Testflight deployments do not issue real SNS tokens on the IC's NNS subnet; the NNS is not asked to adopt a `CreateServiceNervousSystem` proposal.
- **Not a substitute for forum review.** Testflight catches technical mistakes (YAML errors, canister wiring, upgrade failures), not tokenomic or policy mistakes. Community review still needs to happen separately.
- **Not a substitute for an audit.** It runs *your* code against *your* config; it tells you the mechanics work, not that they're safe.

### What testflight typically does

- **Deploys the SNS canister cluster** (Root, Governance, Ledger, Index, Swap, Archive) in a non-mainnet context — historically via an SNS CLI subcommand along the lines of `sns deploy-testflight` against a local replica or a staging network. Verify the current subcommand name before using it.
- **Reads the same `sns_init.yaml`** the team plans to submit, so schema-level errors surface here rather than at NNS submission.
- **Exercises the swap flow** end-to-end with test ICP: swap opens, participants contribute, swap finalises, neuron baskets are minted. The team can verify that the resulting voting-power distribution matches their model.
- **Lets the team simulate post-launch operations** — submit an SNS proposal against the testflight cluster, vote on it with the minted neurons, execute it via Root, and verify the dapp canister upgrade path works end-to-end.

### Local replica vs. staging

- **Local replica** — cheapest and fastest; uses [[local-replica]] via [[dfx]]. Good for schema validation and smoke-testing deploy. Diverges from mainnet in the same places [[local-replica]] notes (consensus, time, randomness, subnet features), so timing-sensitive flows (swap end time, dissolve countdowns) run on a different clock.
- **Staging / testnet** — where available, closer to production because it runs across a multi-node subnet with something resembling mainnet consensus. Rarer and may require coordination with DFINITY or the ecosystem. Whether a public "staging NNS" is currently offered for full `CreateServiceNervousSystem` dry-runs is an open question; teams often spin up their own ephemeral network.

### What a testflight run proves

- The `sns_init.yaml` parses and validates against the CLI of the version the team will use.
- The NNS-Root-as-co-controller handoff executes correctly against the team's dapp canister code (i.e. the code is upgradeable and accepts the new controller).
- The swap math produces the neuron baskets the team modeled.
- The voting-power distribution at swap finalisation matches expectations — including how the dev bucket compares to the swap bucket once dissolve delays are applied.
- A post-launch upgrade proposal against the dapp canister, submitted through SNS Governance and executed through SNS Root, works end-to-end.

### What a testflight run does *not* prove

- The real NNS will adopt the proposal (that's a governance question, not a technical one).
- Mainnet-level cycle costs and timing (testflight clocks and cycle economics differ from mainnet).
- Neurons' Fund participation behaves identically (NF is part of the real NNS flow, not testflight).
- Nothing about legal or policy compliance of the launch.

## Example

```text
Testflight rehearsal (qualitative — verify CLI against current release):

  # 1. Spin up the local test environment
  dfx start --clean --background

  # 2. Run the testflight deploy with the real sns_init.yaml
  sns <testflight-subcommand> \
      --init-config-file sns_init.yaml \
      --network <local-or-staging>

  # 3. Inspect the resulting cluster
  dfx canister --network <net> id sns_root
  dfx canister --network <net> id sns_governance
  dfx canister --network <net> id sns_swap

  # 4. Walk the swap flow
  #    - Open swap (auto per config)
  #    - Contribute test ICP from several principals
  #    - Finalise
  #    - Verify neuron baskets and voting power

  # 5. Walk a post-launch proposal
  #    - Build a new wasm of the dapp canister
  #    - Submit an "upgrade canister" SNS proposal
  #    - Vote with the minted neurons
  #    - Execute; verify the dapp canister is upgraded
```

## Gotchas

- **The CLI surface drifts.** Past SNS CLI releases have renamed subcommands and flags; working testflight scripts from a prior launch cycle are common to break. Regenerate your reference from the current CLI's `--help`.
- **Local time is wall-clock time.** Long dissolve delays or long swap windows take *real* time to elapse even in testflight. Teams typically lower these for rehearsal and re-verify against mainnet-sized values in a second run.
- **Local IDs ≠ mainnet IDs.** Every testflight deploy produces a fresh canister ID set. Anything that hardcodes a principal (e.g. a frontend that talks to `sns_ledger`) needs to read the ID from config, not from a pinned constant.
- **Testflight does not spend an NNS proposal fee.** That's its point — but it also means a testflight "pass" does not credit anything toward the real launch; you still submit the proposal cold.

## See also

- [[sns]]
- [[sns-launch]]
- [[sns-launch-readiness]]
- [[sns-init-config]]
- [[sns-operations]]
- [[local-replica]]
- [[dfx]]
