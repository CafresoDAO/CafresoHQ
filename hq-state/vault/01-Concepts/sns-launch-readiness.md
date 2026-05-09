---
title: SNS Launch Readiness
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-launch-readiness
  - icp/governance/sns
  - icp/sns/operations
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://docs.internetcomputer.org/building-apps/governing-apps/tokenomics/preparation
  - https://forum.dfinity.org
related:
  - "[[sns]]"
  - "[[sns-launch]]"
  - "[[sns-init-config]]"
  - "[[sns-tokenomics]]"
  - "[[sns-testflight]]"
  - "[[canisters]]"
  - "[[upgrade-hooks]]"
  - "[[principals]]"
difficulty: intermediate
open_questions:
  - Exact current set of "must-pass" checks DFINITY recommends in the public launch-review thread before an NNS submission (the list evolves).
  - Whether any formal audit programme is gated into the launch flow, or audits are purely community-norm.
  - Current recommended minimum community-review window on forum.dfinity.org between first proposal draft and NNS submission.
---

# SNS Launch Readiness

> A pre-flight checklist — dapp maturity, canister control, tokenomics, and community review — that a team works through before submitting the `CreateServiceNervousSystem` NNS proposal; the launch itself is atomic and irreversible, so every weakness must be caught here.

## Why it exists

The [[sns-launch]] proposal is a single atomic event: if the NNS adopts it, control of the dapp transfers and the decentralization swap is scheduled without further human intervention. There is no "fix it up after launch" window between adoption and swap-open other than the mandatory pre-open waiting period. Readiness is therefore a discipline of catching every class of mistake — technical, governance, legal, tokenomic — *before* the proposal is submitted. Most historical SNS launch rejections on the forum trace to gaps in this list rather than to tokenomic disagreement.

## How it works

### 1. Dapp maturity

- **The dapp actually runs on mainnet.** Users are using it; cycles cost is known; upgrade paths have been exercised. An SNS that inherits a prototype inherits its bugs *and* its governance tax.
- **Upgrade-hook hygiene.** Every dapp canister handed to the SNS must survive an upgrade round-trip without data loss. See [[upgrade-hooks]] and [[stable-memory]] — post-launch, every upgrade becomes an SNS proposal, so a canister that can't upgrade cleanly blocks every future release.
- **Observability.** Metrics / logs / alerting in place before handoff; once the SNS owns the canister, a silent-failure mode is much harder to debug because you cannot just redeploy.

### 2. Canister controller hand-off

- **NNS Root as co-controller.** Every dapp canister that will be transferred must have NNS Root added to its controllers *before* the proposal executes. The automated handoff in the launch flow depends on this.
- **No lingering dev-only controllers.** After handoff, SNS Root must be the *sole* controller. Any still-attached dev principal is a governance bypass.
- **Fallback controllers chosen deliberately.** Named in `sns_init.yaml`; receive sole control if the swap fails. Set to principals the team actually controls and can re-launch from. See [[sns-init-config]].
- **Cycles runway.** The dapp canister must have enough cycles to survive the swap window and the first post-launch proposal cycle. Post-launch top-ups go through SNS proposals.

### 3. Security and audits

- **Third-party audit** of the dapp canister's public surface, especially any privileged methods, inter-canister calls, and upgrade paths. The audit report is typically linked in the forum pre-launch thread.
- **Authentication surface** reviewed: which principals can call which methods, and whether any of those become SNS-governance-only post-launch.
- **Dependency audit.** CDK version, Candid interface stability, any ic-* crates pinned; a canister handed off to the DAO cannot silently follow an unpinned dependency.

### 4. Tokenomics review

- **Allocations set deliberately**, not by template defaults. Dev / treasury / swap shares, vesting, dissolve-delay schedule, Neurons' Fund match. See [[sns-tokenomics]].
- **Minimum raise (`min_icp_e8s`-style)** sized so that falling short is genuinely acceptable — a successful swap at the minimum must still produce a viable DAO.
- **Max raise and per-participant caps** chosen to avoid whale concentration while still being practical to hit.
- **Vesting & dissolve-delay schedule** for the developer neuron basket documented publicly; a 15%-dev allocation with no vesting reads very differently from one with a multi-year schedule.

### 5. Governance configuration

- **Initial voting power distribution** modeled: who controls what % of voting power at launch, under realistic swap-basket assumptions. If the dev team's neurons dominate voting power on day one, the SNS is not yet decentralized in practice.
- **Nervous-system parameters** (minimum stake, rejection fee, reward schedule) set per the team's philosophy, not left as template defaults they didn't read.
- **Follow graph seeded.** Community expectations (or the dev team's own recommendation) around which neurons to follow on which topics — without this, participation rates crater in week one.

### 6. Community readiness

- **Forum thread** on forum.dfinity.org: the `sns_init.yaml`, tokenomics rationale, audit links, swap schedule, public. Multiple revision rounds before submission are the norm.
- **Written decentralization roadmap.** What the dev team will still do after launch, what the DAO will do, and how the transition will be visible to holders.
- **Communication channels** in place (forum, Discord/X, announcement blog) so participants can reach the team during the swap window.

### 7. Dissolve-delay & follow-graph planning

- **Neuron basket shape** (how many neurons, what dissolve delays) set in `sns_init.yaml` is what every swap participant will receive; this is a governance-shape decision as much as a tokenomic one.
- **Expected voting participation** estimated from the basket: very long dissolve delays with no follow-graph guidance typically produce high-quorum but low-turnout votes.

## Example

```text
Readiness gate (illustrative — not a protocol-enforced checklist):

  [ ] dapp live on mainnet ≥ N weeks, upgrade round-trip tested
  [ ] NNS Root added as co-controller of every dapp canister
  [ ] fallback controllers set to principals team controls
  [ ] third-party audit published, open issues triaged
  [ ] sns_init.yaml locally validated (see [[sns-init-config]])
  [ ] tokenomics published with rationale (see [[sns-tokenomics]])
  [ ] minimum raise sized so success-at-minimum is viable
  [ ] dev neuron vesting + dissolve-delay schedule published
  [ ] forum thread open, ≥ 1 revision round completed
  [ ] decentralization roadmap written, published
  [ ] cycles runway for dapp + SNS cluster for 90 days
  [ ] observability in place before handoff
  → submit CreateServiceNervousSystem proposal
```

## Gotchas

- **"We'll fix it in the first SNS proposal" is a trap.** Post-launch fixes require adoption by a DAO that doesn't exist yet at launch-time and whose voting power is concentrated among people who just bought in. If a launch-blocking issue reaches the swap, you cannot assume governance will gracefully repair it.
- **Legal readiness is out of scope of this note but not of the launch.** Jurisdictional review of the token, the swap, and any geographic restrictions (a configurable field in `sns_init.yaml`) typically happens in parallel with the technical review.
- **Community review timing is not protocol-enforced**, but an NNS proposal that appears without prior forum discussion is usually rejected for process reasons alone.
- **The readiness list lengthens over time.** DFINITY and the ecosystem add expectations as prior launches surface new failure modes — treat this note as a floor, not a ceiling; check the forum's most recent launch-review threads for the current bar.

## See also

- [[sns]]
- [[sns-launch]]
- [[sns-init-config]]
- [[sns-tokenomics]]
- [[sns-testflight]]
- [[sns-operations]]
- [[upgrade-hooks]]
- [[canisters]]
- [[principals]]
