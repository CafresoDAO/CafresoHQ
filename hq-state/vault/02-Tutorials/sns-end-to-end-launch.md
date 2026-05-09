---
title: SNS End-to-End Launch Walkthrough
type: tutorial
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/tutorial
  - icp/governance/sns
  - icp/sns/operations
prerequisites:
  - "[[dfx]]"
  - "[[sns]]"
  - "[[sns-init-config]]"
  - "[[sns-launch]]"
  - "[[sns-launch-readiness]]"
  - "[[sns-tokenomics]]"
  - "[[sns-testflight]]"
difficulty: advanced
estimated_minutes: 120
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://github.com/dfinity/ic/tree/master/rs/sns/cli
  - https://forum.dfinity.org
---

# SNS End-to-End Launch Walkthrough

> An operational walkthrough of the full SNS launch path: register-with-NNS → draft `sns_init.yaml` → validate → testflight → NNS proposal → decentralization swap → handoff. **Kept qualitative on CLI specifics** — the SNS CLI surface evolves between releases; always confirm subcommands and flags against the current release's `--help` and against the live docs.

## Goal

At the end of this walkthrough, the reader will know the full path an SNS launch takes from a mainnet-deployed dapp to a DAO-controlled dapp, will know where each step can fail, and will know which artefacts must be published at each gate for community review.

## Prerequisites

- `dfx` installed and configured — see [[dfx]]
- A dapp already deployed to mainnet under the dev team's control — see [[mainnet-deploy]]
- Conceptual understanding of the SNS canister set, launch lifecycle, tokenomics, and init config — see [[sns]], [[sns-canisters]], [[sns-launch]], [[sns-tokenomics]], [[sns-init-config]]
- A testflight rehearsal completed — see [[sns-testflight]]
- Pre-flight checklist worked through — see [[sns-launch-readiness]]

## Source-of-truth caveat

Exact SNS CLI subcommand names, flag spellings, required identity setup, and NNS proposal payload format have changed across releases. This tutorial gives the *shape* of each step and the artefacts produced; for the exact commands, run the current CLI's `--help` and cross-reference the live DFINITY docs linked in `source:`.

## Steps

### 1. Pre-launch: prepare the dapp and community

Before any CLI action:

- The dapp has been running on mainnet long enough that the team has real upgrade / incident-response experience with it.
- A third-party audit has been completed and published.
- A forum thread on forum.dfinity.org has been opened describing: the dapp, the motivation for decentralization, the `sns_init.yaml` plan, the tokenomics rationale (see [[sns-tokenomics]]), the audit, the timeline. Revision rounds in response to community feedback are the norm, not the exception.

**Verify:** the checklist in [[sns-launch-readiness]] is clean.

### 2. Add NNS Root as co-controller of the dapp canister(s)

Every dapp canister that will be handed off to the SNS must have **NNS Root** added as a *co-controller* before the `CreateServiceNervousSystem` proposal executes. Without this, the automated handoff in the launch flow cannot transfer control — the proposal adopts, but the handoff step fails.

```bash
# Qualitative — verify against current dfx / NNS docs.
dfx canister --network ic update-settings <dapp_canister> \
    --add-controller <nns_root_principal>
```

The NNS Root principal is a well-known identity on mainnet; fetch it from the live docs rather than hardcoding it from memory.

**Verify:**

```bash
dfx canister --network ic info <dapp_canister>
# Should list dev_principal AND nns_root_principal as controllers.
```

### 3. Draft `sns_init.yaml`

Scaffold from the current SNS CLI so the field shape matches the version that will be validated:

```bash
sns init-config-file new
```

Edit the resulting `sns_init.yaml` to fill in:

- Dapp identity (name, description, URLs, logo references).
- Token (name, symbol, ledger transaction fee, decimals).
- Initial Token Distribution (dev / treasury / swap buckets; airdrop neurons if any) — see [[sns-tokenomics]].
- Nervous-system parameters (minimum neuron stake, rejection fee, voting reward schedule, minimum dissolve delay for voting power) — see [[sns-neurons-and-voting]].
- Swap bounds (min ICP, max ICP, per-participant min/max, start/end timing, geographic restrictions, Neurons' Fund participation).
- Fallback controllers (principals that regain sole control if the swap fails — typically the dev team).

**Publish the draft YAML on the forum thread** for community review. Revision rounds expected.

### 4. Validate locally

```bash
sns init-config-file validate sns_init.yaml
```

Catches schema-level errors (missing required fields, out-of-range values, inconsistent swap bounds). Does **not** catch tokenomic or policy problems — those have to come from the forum review. See [[sns-init-config]].

### 5. Testflight rehearsal

Run the end-to-end flow against a non-mainnet target (local replica or staging). See [[sns-testflight]] for the full testflight path. Minimum things to exercise in the rehearsal:

- The cluster deploys from the YAML without errors.
- The swap opens, accepts test ICP, and finalises to the expected neuron basket distribution.
- A post-launch upgrade proposal (an SNS proposal that installs a new wasm on the dapp canister) votes and executes cleanly against the testflight cluster.

**Verify:** resulting voting-power distribution matches the team's model (it almost never does exactly on the first try — adjust dissolve-delay configuration, iterate).

### 6. Submit the `CreateServiceNervousSystem` NNS proposal

The validated `sns_init.yaml` becomes the payload of a single NNS proposal of type `CreateServiceNervousSystem`. Submission is an NNS action, not an SNS action — it is submitted by an NNS neuron, costs the NNS proposal rejection fee if rejected, and is voted on by NNS neurons (not SNS neurons, which don't exist yet).

Qualitatively:

```bash
# Verify current NNS CLI / quill / ic-admin command against live docs.
<nns-proposal-tool> propose create-service-nervous-system \
    --init-config-file sns_init.yaml \
    --title "Launch SNS for <dapp>" \
    --url <forum-thread-url> \
    --summary <summary-markdown>
```

**What happens on adoption:**

1. SNS-W (the NNS-governed SNS wasm-modules canister) deploys the SNS canister cluster on the SNS subnet: Swap, Governance, Ledger, Root, Index. See [[sns-canisters]].
2. Controllership of every dapp canister listed in the config transfers from `{dev, nns_root}` to `{sns_root}` alone.
3. The SNS enters **pre-decentralization-swap mode**.
4. A waiting period begins (the docs state *at least 24 hours* for the 1-proposal model — verify against current docs).

**Verify:**

- The NNS proposal status on dashboard.internetcomputer.org.
- Post-adoption: the new SNS canister IDs appear on dashboard.internetcomputer.org/sns.
- Post-adoption: `dfx canister --network ic info <dapp_canister>` shows *only* the SNS Root principal as controller.

### 7. Decentralization swap

At the scheduled start time, the Swap canister opens and accepts ICP contributions from participants. It closes at the scheduled end time or when the maximum ICP is reached, whichever comes first.

During the swap window:

- Monitor participation on dashboard.internetcomputer.org/sns/<id>.
- Answer questions on the forum thread and in the team's existing community channels.
- Do *not* add or remove anything to the SNS — the cluster is in pre-decentralization-swap mode for exactly this reason.

### 8. Finalisation

**Success path (minimum ICP reached):**

- Swap finalises.
- ICP is distributed per the tokenomics (split between dev, treasury, and the raise pot that funds ongoing SNS operations).
- Participants receive their purchased SNS tokens as a *basket of neurons* with varying dissolve delays (see [[sns-neurons-and-voting]]).
- SNS Governance flips to **Normal mode** — proposals and votes now function the way [[sns-neurons-and-voting]] describes.

**Failure path (minimum ICP not reached):**

- ICP is refunded to participants by the Swap canister.
- Sole control of the dapp canister(s) returns to the fallback controllers named in the config.
- The SNS cluster is in an aborted state; re-launching requires another `CreateServiceNervousSystem` proposal with a revised config. **Tokenomics, timing, or outreach likely need rethinking before re-submitting** — the same config is unlikely to reach the minimum on a second try.

### 9. Post-launch operations

See [[sns-operations]] for the full operating manual. First-week priorities:

- Confirm every SNS canister has enough cycles for the foreseeable window; schedule a top-up proposal if not.
- Confirm the dapp canister has enough cycles.
- Draft the first "routine" SNS proposal (even a motion proposal) early, to exercise the flow while the team still has operational continuity from launch.
- Publish a post-launch retrospective on the forum: what the final neuron distribution looks like, what the treasury holds, what the first planned proposals are.

## Verify

Key confirmation points once the swap has finalised successfully:

```bash
# SNS cluster canister IDs are published on the dashboard:
# https://dashboard.internetcomputer.org/sns/<sns-root-principal>

# dapp canister is solely controlled by SNS Root:
dfx canister --network ic info <dapp_canister>

# SNS token supply is minted and matches sns_init.yaml:
# (use the ledger canister ID from the dashboard, not a memory citation)
dfx canister --network ic call <sns_ledger> icrc1_total_supply

# Governance mode is Normal (not pre-decentralization-swap):
dfx canister --network ic call <sns_governance> get_mode
```

## Failure modes

- **NNS rejects the proposal.** No state changes; dapp remains dev-controlled. Treat the rejection reasons (public on the forum/dashboard) as the design feedback they are; iterate the config.
- **Proposal adopts but handoff fails** (usually: NNS Root was not added as co-controller of every dapp canister listed in the config). Recovery is non-trivial and requires coordination with DFINITY — this is why step 2 is a hard pre-check.
- **Swap does not meet minimum.** Auto-refund; dapp returns to fallback controllers. Re-launch requires a revised config.
- **Swap over-subscribes almost instantly.** Not a technical failure, but a signal that the swap bounds and per-participant caps may have been set too narrow; the resulting voting-power distribution may be more concentrated than planned.
- **Post-launch dapp upgrade fails** (usually: pre/post-upgrade hooks not exercised properly — see [[upgrade-hooks]]). No automatic rollback; a fix-forward SNS proposal is required.
- **SNS cluster canister runs out of cycles.** Freezes; if unresolved, eventually deleted. Top-up-via-treasury-proposal cadence must be planned from day one — see [[sns-operations]].

## Next

- [[sns-operations]] — post-launch operating manual
- [[sns-init-yaml-walkthrough]] — deeper CLI-focused walkthrough of `sns_init.yaml`
- [[tokenomics-100m-analysis]] — worked example of evaluating a specific proposed split
