---
title: Scaffolding an sns_init.yaml with the SNS CLI
type: tutorial
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/tutorial
  - icp/governance/sns
prerequisites:
  - "[[dfx]]"
  - "[[sns]]"
  - "[[sns-init-config]]"
  - "[[sns-launch]]"
difficulty: intermediate
estimated_minutes: 30
source:
  - https://github.com/dfinity/ic/blob/master/rs/sns/cli/README.md
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
open_questions:
  - Exact current installation path / release channel for the `sns` CLI on the current `dfx` — verify from the linked CLI README before running.
  - Whether `sns init-config-file validate` in the current release catches every rule also enforced by SNS-W at deploy time.
---

# Scaffolding an `sns_init.yaml` with the SNS CLI

## Goal

Walk through generating, editing, and validating a Service Nervous System initialization config file — the artefact that eventually becomes the payload of a [[sns-launch|`CreateServiceNervousSystem` NNS proposal]]. The aim is **not** to launch an SNS to mainnet; it is to produce a locally-valid config and build intuition for what each major section controls.

> **Source-of-truth caveat.** The YAML schema evolves. This tutorial describes the *shape* of the config qualitatively. When you run the steps, the template emitted by `sns init-config-file new` on your current CLI release is the authoritative field list — copy from that, not from memory.

## Prerequisites

- [[dfx]] installed and working locally.
- The `sns` CLI available on your `PATH` — shipped alongside recent releases of `dfx` / the IC SDK. If your `dfx` does not expose it, build or install the CLI from `rs/sns/cli/` in `github.com/dfinity/ic`. See that README for the current installation instructions.
- A notional dapp in mind: a name, a token symbol, a rough idea of the developer / treasury / swap split, and a reasonable minimum/maximum for the swap.

## Steps

### 1. Check the CLI is there

```bash
sns --help
sns init-config-file --help
```

You should see subcommands including `new` and `validate` under `init-config-file`. If not, your `dfx` release does not bundle the current `sns` CLI — consult the upstream README.

### 2. Scaffold a fresh `sns_init.yaml`

```bash
mkdir sns-experiment && cd sns-experiment
sns init-config-file new
```

This writes `sns_init.yaml` into the current directory. Open it. The file is annotated with comments explaining each field; read it top-to-bottom before editing.

### 3. Orient yourself — what are you editing?

The config groups its fields into roughly these sections (see [[sns-init-config]] for the concept-level summary):

1. **Institutional / dapp identity.** Names, descriptions, URLs, a logo path, and — critically — the **fallback controllers** who regain control of the dapp if the swap fails. These must be principals you actually control.
2. **Token.** Token name, symbol, decimal places, ledger transaction fee. Mostly *one-shot* decisions: changing a symbol post-launch ranges from awkward to impossible.
3. **Initial token distribution.** Three buckets:
   - **Developer** — allocated to dev-team principals, typically as neurons with long dissolve delays.
   - **Treasury** — owned by SNS Governance, spendable only via SNS proposal after launch.
   - **Swap** — the supply offered to swap participants in exchange for ICP.
4. **Governance / nervous-system parameters.** Minimum neuron stake, rejection fee, voting reward schedule, thresholds. Most of these are adjustable post-launch via an SNS proposal — treat the initial values as reasonable starting points, not forever-settings. See [[sns-neurons-and-voting]].
5. **Neurons.** The shape of the *basket* each swap participant receives — how many neurons, with what staggered dissolve delays.
6. **Swap.** Minimum and maximum ICP the swap will collect, per-participant minimum/maximum, start/end timing, participation conditions, geographic restrictions.
7. **Neurons' Fund participation.** Whether the NNS Neurons' Fund is allowed to match participation from opted-in NNS neurons, and — if so — how that matching is parameterised.

### 4. Fill in the required fields

Work top-down through the template. The comments flag which fields have defaults you can leave alone and which require your input. Pay particular attention to:

- **Fallback controllers.** Type these slowly. A failed-swap hand-off into the void is unrecoverable without NNS intervention.
- **Swap min/max ICP.** The minimum is your "this SNS is viable" threshold; below it the swap refunds and the launch unwinds.
- **Distribution buckets.** The sum must equal the initial supply; the validator will reject inconsistencies.
- **Dev neuron dissolve delays.** Optics and practicality — short dev-lockups undermine DAO credibility; pick deliberately.

### 5. Validate locally

```bash
sns init-config-file validate sns_init.yaml
```

This runs the local schema validator. Typical failures:

- Missing required fields.
- Distribution bucket totals that don't add up to the initial supply.
- Swap minimum greater than maximum, or start-time after end-time.
- Dissolve delays below the nervous-system minimum.

Fix and re-run until the validator passes.

### 6. (Optional) Dry-deploy in test-flight or local

Validation is a static check. To see SNS-W actually accept or reject the config, you can:

```bash
# Test-flight: a deploy that exercises more of the pipeline
# without going through an NNS proposal.
sns deploy-test-flight --init-config-file sns_init.yaml

# Or, if you have a local replica running:
sns deploy --network local --init-config-file sns_init.yaml
```

Both paths give faster, cheaper feedback than submitting a mainnet `CreateServiceNervousSystem` proposal. Refer to the CLI README for the current exact subcommand names and flags — they drift.

### 7. Don't submit to mainnet from a tutorial

A real SNS launch needs:

- Peer / community review on forum.dfinity.org (conventional, not protocol-enforced).
- A committed tokenomics design — not a "let's see what the tool does" draft.
- The **NNS Root co-controller** prerequisite wired into your dapp canisters (see [[sns-launch]]).
- Budget for the rejection fee of the `CreateServiceNervousSystem` proposal.

None of that is part of this walkthrough — it is a *scaffolding* exercise, full stop.

## Verify

You end this tutorial with:

```bash
ls sns_init.yaml         # the scaffolded + edited config
sns init-config-file validate sns_init.yaml   # exits 0
```

and — more importantly — a mental map of which fields the config is actually asking you about and why each of them is hard to change after launch.

## Next

- [[sns-launch]] — what happens after the validated config becomes an NNS proposal payload.
- [[sns-neurons-and-voting]] — how the neurons the config hands out actually vote.
- [[sns-canisters]] — the canister cluster that the config ultimately parameterises.
