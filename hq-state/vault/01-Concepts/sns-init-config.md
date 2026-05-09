---
title: SNS Init Config (sns_init.yaml)
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21 # Session 5: cross-linked sns-tokenomics (knobs), sns-launch-readiness (pre-flight), sns-testflight (rehearsal), sns-launch-benchmarks (reference), sns-end-to-end-launch (tutorial). Pointed the Initial Token Distribution section at sns-tokenomics as the rationale note.
tags:
  - icp
  - icp/concept
  - icp/concept/sns-init-config
  - icp/governance/sns
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://github.com/dfinity/ic/blob/master/rs/sns/cli/README.md
  - https://github.com/dfinity/ic/tree/master/rs/sns/init
related:
  - "[[sns]]"
  - "[[sns-canisters]]"
  - "[[sns-launch]]"
  - "[[sns-neurons-and-voting]]"
  - "[[sns-tokenomics]]"
  - "[[sns-launch-readiness]]"
  - "[[sns-testflight]]"
  - "[[sns-launch-benchmarks]]"
  - "[[sns-end-to-end-launch]]"
  - "[[dfx]]"
  - "[[principals]]"
difficulty: intermediate
open_questions:
  - Exact current YAML field names and their types — intentionally not transcribed here; verify against `sns init-config-file new` output on the current release.
  - Current set of validation rules enforced by `sns init-config-file validate` (versus rules only enforced by SNS-W at deploy time).
  - Whether the single-proposal launch fully supplants older multi-proposal / pre-1-proposal config formats in tooling.
---

# SNS Init Config (`sns_init.yaml`)

> `sns_init.yaml` is the single declarative file that parameterises an entire Service Nervous System — tokenomics, governance rules, the decentralization swap, and developer/treasury allocations — read by the SNS CLI to produce the payload of the `CreateServiceNervousSystem` NNS proposal.

## Why it exists

An SNS launch wires together several canisters, a token supply, a neuron basket, a one-shot swap, and a bundle of governance thresholds. Doing that interactively would be error-prone; once the NNS adopts the create-proposal, most of these values cannot be changed without another proposal. The YAML collapses the whole launch into one reviewable artefact that the CLI can validate locally *before* anyone spends voting-reward-denominated ICP submitting a proposal.

## How it works

- **Scaffold** — `sns init-config-file new` emits a template `sns_init.yaml` containing the parameters with comments; some have sensible defaults, others must be filled in.
- **Validate** — `sns init-config-file validate <path>` runs the local validator, catching obvious mistakes (missing required fields, out-of-range values, inconsistent swap bounds) before submission.
- **Deploy** — `sns deploy --network <ic|local> --init-config-file <path>` deploys the SNS using the config. On mainnet the actual creation path goes through the NNS `CreateServiceNervousSystem` proposal; test-flight and local-replica deployments use `deploy-test-flight` or `--network local`.
- **Main sections** — qualitatively, the config groups its parameters into the following areas (exact field names intentionally not transcribed; they drift and the template itself is the source of truth):

  1. **Institutional / Dapp identity.** Names, descriptions, URLs, logos, and the *fallback controllers* (the principals that regain sole control of the dapp if the swap fails).
  2. **Token.** SNS token name, symbol, ledger transaction fee, decimal places.
  3. **Initial Token Distribution.** The three canonical buckets — **developer** (vested as neurons with varying dissolve delays), **treasury** (held by SNS Governance for community spending), **swap** (offered in exchange for ICP during decentralization). Plus, optionally, named airdrop neurons allocated to specific principals. See [[sns-tokenomics]] for the knob-by-knob governance effect, and [[sns-launch-benchmarks]] for how this has sized across historical launches.
  4. **Governance / Nervous-System Parameters.** Minimum neuron stake, rejection-fee (cost to submit a losing proposal), voting reward schedule, and other thresholds that Governance will enforce and that can be updated post-launch via SNS proposals. See [[sns-neurons-and-voting]].
  5. **Neurons.** The shape of the initial *basket of neurons* each participant receives from the swap — how many, with what dissolve delays.
  6. **Swap.** Minimum and maximum ICP the swap will accept, per-participant minimum/maximum, participation conditions, geographic restrictions, start/end timing. If the minimum is not reached, the swap aborts.
  7. **NeuronsFund participation.** Whether — and how — the NNS-governed Neurons' Fund contributes ICP to the swap on behalf of NNS neurons that opted in. NF is an *ICP co-contributor* to the swap, not a separate share of SNS-token supply; see [[sns-tokenomics]].

- **Single-proposal model** — the current launch path bundles everything above into *one* NNS proposal; the older multi-step flow (create / configure / open-swap as separate proposals) is no longer the recommended model. See [[sns-launch]].

## Example

```bash
# 1. Scaffold the template into the current directory.
sns init-config-file new

# 2. Edit sns_init.yaml — set token name/symbol, fill in
#    distribution buckets, swap bounds, fallback controllers, etc.

# 3. Validate locally before wasting a proposal on a bad config.
sns init-config-file validate sns_init.yaml

# 4. (Mainnet) the validated config becomes the payload of the
#    NNS CreateServiceNervousSystem proposal.
```

## Gotchas

- **Some fields are irreversible in practice.** Token symbol and initial distribution cannot be changed by a post-launch SNS proposal the way governance thresholds can. Review these especially carefully.
- **Local validation ≠ NNS acceptance.** `sns init-config-file validate` catches schema-level mistakes, but the NNS proposal can still be rejected on tokenomic or policy grounds. Community review on the forum before submission is standard practice.
- **Do not assume field names from memory.** The YAML schema evolves; regenerate the template with `sns init-config-file new` on the current CLI release rather than copying an old one.
- **Fallback controllers are a safety net.** If they are misconfigured (e.g., set to principals you don't control), a failed swap can leave the dapp in an unreachable state.
- **Testflight it first.** The YAML validates locally but the end-to-end flow (deploy → swap → handoff) is easier to debug against a non-mainnet target. See [[sns-testflight]].

## See also

- [[sns]]
- [[sns-canisters]]
- [[sns-launch]]
- [[sns-neurons-and-voting]]
- [[sns-tokenomics]]
- [[sns-launch-readiness]]
- [[sns-testflight]]
- [[sns-launch-benchmarks]]
- [[sns-end-to-end-launch]]
- [[dfx]]
- [[principals]]
