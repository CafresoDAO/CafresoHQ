---
title: SNS Neurons and Voting
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-neurons-and-voting
  - icp/governance/sns
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://github.com/dfinity/ic/tree/master/rs/sns/governance
related:
  - "[[sns]]"
  - "[[sns-canisters]]"
  - "[[sns-init-config]]"
  - "[[sns-launch]]"
  - "[[nns]]"
  - "[[principals]]"
difficulty: intermediate
open_questions:
  - Exact voting-power formula (stake × dissolve-delay bonus × age bonus) per current SNS Governance release.
  - Current enumerated list of SNS proposal types and their default permission/following rules.
  - Minimum-dissolve-delay threshold below which an SNS neuron gains no voting power.
---

# SNS Neurons and Voting

> An SNS neuron is a staked lock-up of an SNS's own token, owned by a [[principals|principal]], that carries voting power over proposals in that SNS — the same neuron-and-delegation pattern the [[nns|NNS]] uses, scoped to one DAO.

## Why it exists

Holding a token is a thin commitment; a DAO that weighs votes purely by balance is trivially manipulable by flash loans and short-term holders. Neurons force voters to **lock** their tokens for a chosen dissolve delay in exchange for voting power and rewards — aligning governance weight with time-skin-in-the-game rather than momentary balance.

## How it works

- **Creation** — neurons originate two ways:
  1. **Swap basket.** At swap finalisation, every participant is issued a *basket* of neurons (not a single one) with staggered dissolve delays. The shape of the basket is defined in `sns_init.yaml`.
  2. **Post-launch staking.** A holder transfers SNS tokens into an SNS-Governance-owned ledger account and calls the governance canister to claim the resulting neuron.
- **Stake** — the neuron's balance of the SNS token; locked so it cannot be spent until the neuron is *dissolved*. A minimum stake is enforced by nervous-system parameters.
- **Dissolve delay** — a timer controlling how long after the user asks to dissolve until the stake becomes spendable. Higher dissolve delay → more voting power. A neuron in *non-dissolving* state holds its delay fixed; when *dissolving*, the timer counts down.
- **Voting power** — a function of stake, dissolve delay, and (typically) neuron age; neurons below a minimum dissolve delay carry no voting power. Exact formula is set by the SNS's nervous-system parameters and can be changed by SNS proposal.
- **Following** — a neuron can *follow* other neurons on specific proposal topics, delegating its vote to them. This is how SNSs achieve practical participation rates without requiring every holder to vote on every proposal.
- **Proposals** — common proposal categories an SNS uses include:
  - Upgrading SNS canisters (wasm upgrades, routed through Root).
  - Upgrading the governed dapp canister(s).
  - Changing nervous-system parameters (reward schedule, minimum stake, thresholds).
  - Treasury actions (transferring SNS tokens or ICP out of treasury).
  - Motion proposals (non-binding on-chain statements).
  - Adding/removing generic (custom) proposal types defined by the SNS itself.
  Every proposal has a cost (the rejection fee, burned if the proposal loses) to deter spam.
- **Rewards** — adopted proposals distribute voting rewards to neurons that voted on them, paid in the SNS token. Not voting (or not following someone who votes) forgoes that reward.

## Example

```text
Holder wants governance weight:

  1. transfer(sns_ledger,
              from = user_account,
              to   = sns_governance_subaccount(user_principal, nonce))
  2. sns_governance.claim_or_refresh_neuron(nonce)
     -> neuron created, owned by user_principal
  3. sns_governance.configure_neuron(neuron_id,
         IncreaseDissolveDelay { additional_seconds: Δ })
     -> neuron now has voting power
  4. sns_governance.follow(neuron_id,
         on_topic = UpgradeCanister,
         followees = [expert_neuron_id])
     -> future UpgradeCanister votes are delegated
```

## Gotchas

- **Dissolve delay is not the lock time.** You can set the dissolve delay high and *not* be dissolving; the stake is indefinitely locked until you explicitly start dissolution. Starting dissolution is a user action.
- **A neuron with too-low dissolve delay has zero voting power**, even if heavily staked. Increasing delay is free; decreasing is impossible (only the natural countdown after starting dissolution reduces it).
- **Following is topic-scoped.** Setting a followee on "UpgradeCanister" does not delegate treasury votes. Audit your following list after the SNS adds new proposal types.
- **Rejection fees are real.** Submitting a frivolous proposal that fails burns the fee; cheap-spam is intentionally expensive.
- **SNS neurons are not NNS neurons.** A principal may hold neurons in many SNSs and in the NNS independently; each set only votes in its own nervous-system.

## See also

- [[sns]]
- [[sns-canisters]]
- [[sns-init-config]]
- [[sns-launch]]
- [[nns]]
- [[principals]]
