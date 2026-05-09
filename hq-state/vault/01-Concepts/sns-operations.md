---
title: SNS Operations (Post-Launch)
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/sns-operations
  - icp/governance/sns
  - icp/sns/operations
source:
  - https://docs.internetcomputer.org/building-apps/governing-apps/launching/launch-summary-1proposal
  - https://internetcomputer.org/sns
  - https://github.com/dfinity/ic/tree/master/rs/sns/governance
  - https://dashboard.internetcomputer.org/sns
related:
  - "[[sns]]"
  - "[[sns-canisters]]"
  - "[[sns-neurons-and-voting]]"
  - "[[sns-launch]]"
  - "[[sns-tokenomics]]"
  - "[[upgrade-hooks]]"
  - "[[cycles]]"
difficulty: intermediate
open_questions:
  - Current default proposal-type set and per-type follow/voting-power rules in the SNS Governance release line (drifts; verify per release).
  - Whether there is a canonical "emergency halt" proposal type at the SNS level, or whether halts are achieved by a custom upgrade proposal that installs a halted wasm.
  - Recommended observability stack for SNS canisters — whether dashboard.internetcomputer.org alone suffices or teams typically run their own Prometheus-style scraping via a metrics endpoint.
---

# SNS Operations (Post-Launch)

> After the decentralization swap finalises, every operational action on the SNS cluster and on the governed dapp — upgrades, parameter changes, treasury spends, emergency responses — must pass through an SNS proposal; this note is the operating manual for that mode.

## Why it exists

At swap finalisation the dev team loses unilateral control of the dapp and of the SNS canister cluster. "Operations" is no longer SSH + `dfx deploy`; it is "draft proposal → submit → community votes → Root executes". The tooling is similar enough to the NNS's that experienced operators adapt quickly, but the cadence is radically different (proposals take at least hours to days to finalise) and every action is public. Teams that treat post-launch operations as "business as usual plus a YAML file" under-invest in the proposal flow and find themselves unable to ship security fixes on a short timeline.

## How it works

### Upgrading SNS canisters

- Every SNS canister (Root, Governance, Ledger, Index, Swap, Archive) is controlled by SNS Root, which is controlled by SNS Governance. Upgrading any of them requires an SNS proposal that Root executes against the target canister.
- **Core SNS upgrades follow DFINITY's SNS-W blessed-wasm track.** The NNS-governed SNS-W canister maintains the set of wasms the Root canister is permitted to install against SNS cluster members. Upgrade proposals reference a wasm hash that SNS-W knows about; installing a wasm outside that set is not part of the default path.
- **Proposal type.** An "upgrade SNS controlled canister" (or equivalent) proposal type exists in the default SNS proposal set. See [[sns-neurons-and-voting]] for how voting on it works.

### Upgrading the governed dapp

- The dapp canister(s) were handed off at launch; SNS Root is their controller. Upgrading them is a separate proposal type from upgrading the SNS cluster itself.
- The team (or any neuron holder) builds the new wasm, publishes the hash + source, drafts the proposal (target canister, wasm module, init/upgrade arg), and submits.
- The proposal's rejection fee is burned if it loses. Community review on the forum typically precedes submission, same as launch.

### Nervous-system parameters

- Governance thresholds (minimum neuron stake, rejection fee, reward schedule, minimum dissolve delay for voting power, etc.) are mutable post-launch via dedicated parameter-change proposals.
- Changes take effect on adoption; prior neurons and prior proposals are unaffected unless the parameter explicitly applies retroactively.

### Treasury disbursements

- Treasury tokens (the bucket minted at launch into SNS Governance's own subaccount — see [[sns-tokenomics]]) move only through treasury proposals.
- **Treasury can hold ICP as well as the SNS token.** Swap proceeds (the ICP raised from participants) end up in an SNS-controlled account; disbursing that ICP is also governed.
- **Common treasury uses:** cycle top-ups for SNS canisters and the dapp canister, grants to contributors, liquidity provision on DEXes, marketing budgets, bounty payouts.
- Every disbursement is on-chain and publicly readable via the ledger / dashboard — there is no "private treasury" path.

### Cycles and top-ups

- SNS canisters burn cycles like any other canister (see [[cycles]]). Running out of cycles freezes and eventually deletes a canister — catastrophic for any cluster member.
- Post-launch cycle top-ups typically route through a treasury proposal that converts treasury ICP (or SNS token, via swap) to cycles and tops up the target canister via the cycles ledger.
- Some teams pre-commit to a recurring top-up proposal or to a standing balance-threshold alert to the community.

### Emergency response

- **There is no off-switch.** Once the SNS owns the dapp, "halt the dapp right now" is itself an SNS proposal — it runs at the speed of governance, not the speed of incident response.
- **Mitigations teams use:**
  - A pre-built "halted" wasm ready to propose at short notice.
  - Feature flags inside the dapp canister toggleable by an SNS parameter change (the canister reads a state flag on each update call and returns an error if set).
  - A short-voting-period "critical" proposal type (available in the SNS Governance default proposal set for this reason), which has tighter quorum / faster resolution than standard proposals.
  - A follow-graph seeded by the community so that critical proposals can reach quorum on the short window.
- `manage_neuron` is a standard SNS Governance call; voting and following use it, but it is not an emergency bypass — a neuron cannot override the DAO, only vote in it.

### Metrics and observability

- **dashboard.internetcomputer.org** surfaces per-SNS information (canister IDs, token supply, neuron counts, proposal history) and is the default public read-side tool.
- The SNS canisters expose Candid methods for state queries (supply, neuron lookup, proposal list). Teams commonly scrape these into their own dashboards for alerting.
- **Alert on:** low cycles on any cluster member, low voting participation on critical proposals, unexpected treasury outflows, dapp canister error-rate spikes, large neuron-stake changes (potential governance takeover).

## Example

```text
Post-launch upgrade, end-to-end:

  1. Dev team builds new dapp canister wasm, publishes hash + source.
  2. Forum post explaining the change, diff, test coverage, risks.
  3. Any neuron submits "upgrade dapp canister" SNS proposal
     (target canister id, wasm module or hash, upgrade arg).
     - Rejection fee staked.
  4. Voting window opens; neurons vote directly or via followees.
  5. Proposal adopted → SNS Governance instructs SNS Root.
  6. SNS Root calls management canister: install_code(mode = upgrade, ...).
  7. Dapp canister runs post-upgrade hook (see [[upgrade-hooks]]).
  8. Verify via dashboard.internetcomputer.org and the dapp's own health endpoint.
```

## Gotchas

- **"Just push a hotfix" doesn't exist.** Even for a trivial fix, the fastest path is a critical proposal with its reduced voting window. Plan security incidents around that reality.
- **Treasury proposals are very public.** Every transfer is visible; opposition campaigns during the voting window are routine for large spends. Build consensus on the forum before submitting.
- **Cycle-starving any cluster member is fatal.** The SNS cluster is a set of interdependent canisters; if the Ledger freezes, so does every operation that touches token state. Top-up hygiene is not optional.
- **Proposal fee is not a deterrent once governance is contentious.** A motivated opponent can afford to lose proposal fees repeatedly to spam; the default rejection fee is tuned for baseline load.
- **SNS-W is NNS-governed.** The set of wasms SNS Root is permitted to install against core cluster members is decided by the NNS, not by each SNS. An SNS cannot unilaterally choose to upgrade its Governance canister to a non-blessed wasm via the normal path.

## See also

- [[sns]]
- [[sns-canisters]]
- [[sns-neurons-and-voting]]
- [[sns-launch]]
- [[sns-launch-readiness]]
- [[sns-tokenomics]]
- [[upgrade-hooks]]
- [[cycles]]
- [[nns]]
