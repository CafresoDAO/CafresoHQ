---
title: Network Nervous System (NNS)
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/nns
  - icp/governance/nns
source:
  - https://internetcomputer.org/nns
  - https://internetcomputer.org/docs/building-apps/governing-apps/nns/overview
  - https://github.com/dfinity/ic/tree/master/rs/nns
related:
  - "[[sns]]"
  - "[[subnets]]"
  - "[[principals]]"
  - "[[cycles]]"
  - "[[cycles-wallet]]"
  - "[[canisters]]"
difficulty: intermediate
open_questions:
  - Current exact list of NNS canisters (the "Lifeline" and "Genesis Token" canisters in particular — their present-day roles and whether any have been deprecated).
  - Current enumerated list of NNS proposal topics and the per-topic default following / voting-power parameters.
  - Current exact voting-rewards schedule (daily rewards maturity formula and the long-term reward decay).
---

# Network Nervous System (NNS)

> The NNS is the Internet Computer's **root DAO** — the on-chain governance system that runs the protocol itself: admitting and decommissioning subnets, upgrading replica software, pricing [[cycles]], controlling the [[sns|SNS]] factory, and holding the ICP ledger. It is the same pattern an SNS instantiates for a single dapp, applied at the scale of the whole network.

## Why it exists

Every blockchain needs a way to evolve its protocol — price curves, new consensus features, node rotations. Most chains do this with off-chain rough-consensus + hard forks. ICP does it on-chain: a permanent DAO composed of ICP-staked neurons votes on proposals that are executed directly by the protocol's own canisters. The NNS is that DAO. It is what makes statements like "the IC can upgrade its own replica software autonomously" true — there is no foundation-controlled multisig flipping switches; there is a proposal, a vote, and a canister-executed effect.

## How it works

- **Neurons and voting** — ICP token holders lock ICP in a **neuron** (a staking position with a chosen dissolve delay). Voting power is a function of stake × dissolve-delay × age bonus; neurons vote on proposals and earn **maturity** (convertible to ICP) as rewards. Long-lived neurons with long dissolve delays carry disproportionately more weight — the design goal is to privilege people with skin in the long-term outcome.
- **Proposals** — any neuron above a minimum stake can submit a proposal. Proposals are **topic-scoped** (governance motions, replica upgrades, subnet management, node admission, SNS launches, network-economics parameters, etc.). Each topic has its own default following graph and rejection-fee behavior.
- **Following** — neurons can *follow* other neurons on a per-topic basis. A neuron that does not vote directly on a topic inherits the vote of whoever it follows. This is how casual holders delegate specialised judgment (e.g. follow a "node ops" neuron for subnet-management topics) without giving up sovereignty on other topics.
- **Governance runs the protocol** — the NNS Governance canister does not just hold opinions; the other NNS canisters are *its controlees*, and adopted proposals execute as concrete canister calls: the Registry is rewritten, the replica is upgraded, an SNS is created, a subnet is admitted, a node is decommissioned.

## The NNS canisters

The NNS is a cluster of specialized canisters living on the NNS [[subnets|subnet]] (a system subnet). Each has a well-defined job; together they form the governance and ledger backbone of the IC.

- **Governance** — the proposal / voting engine. Stores neurons, tallies votes, executes adopted proposals. The neuron-and-follow pattern originates here; the [[sns]] Governance canister is a parameterised fork of this one.
- **Registry** — the canonical registry of the IC's topology: the list of subnets, which nodes belong to each subnet, which replica versions they run, which canister IDs are allocated to which subnet. Adopted proposals on subnet management, node admission, or replica upgrades are applied by mutating the Registry, which replicas then read.
- **ICP Ledger** — the ICP token ledger. Holds balances, processes transfers, and is the canister every exchange, wallet, and on-chain ICP user ultimately hits. It is a standard ledger canister (historically its own ABI, with ICRC-1/2 support layered on).
- **Cycles Minting Canister (CMC)** — the canister that burns ICP and mints [[cycles]]. It is how a developer principal goes from "holding ICP" to "funded canister": send ICP here with a typed memo, and cycles are credited to the target. Price is pegged to XDR and the rate is set by NNS-approved parameters. See [[cycles-wallet]].
- **Root** — the controller of the other NNS canisters. Upgrades to any NNS canister go through Root, which in turn executes the Governance-adopted upgrade proposal. This is the exact same pattern SNS Root plays for an individual SNS — the NNS is, in that sense, its own SNS.
- **Lifeline** — the "last-resort" controller of Root. It exists so that if Governance or Root ever gets bricked by a bad upgrade, there is still a minimal, audited canister with authority to recover them. It is intentionally tiny and rarely touched.
- **Genesis Token (GTC)** — the launch-era canister that allowed initial token-holders to claim their genesis ICP into neurons. Largely historical now; kept for archival claims and auditability.

Other canisters commonly grouped with the NNS (Neurons' Fund, SNS-W / SNS-Wasm-Modules, Node Rewards, etc.) are adjacencies that Governance invokes for specific workflows rather than the governance backbone itself.

## Relationship to the SNS

The [[sns|SNS]] is the NNS's governance pattern **parameterised for a single dapp**:

- The **shape** is identical — a Root canister controlling a Governance canister that holds neurons and executes adopted proposals, with a Ledger canister for the governance token.
- The **scope** differs. NNS governs the Internet Computer as a whole: subnets, replica versions, [[cycles]] pricing, the ICP ledger, which SNSes get launched. An SNS governs a single dapp: that dapp's canister upgrades, its own token parameters, its own treasury.
- The **creation path** is asymmetric. The NNS pre-exists; it launched with the network at genesis. An SNS is *created by an NNS proposal* (`CreateServiceNervousSystem`) — the NNS is the mint for SNSes. See [[sns-launch]].
- **Neurons do not cross over.** NNS neurons vote on NNS proposals and hold ICP; SNS neurons vote on their SNS's proposals and hold that SNS's token. The two are separate governance stacks even though they share a codebase.

## Example

```text
Layer              Role                               Controller of
-----              ----                               -------------
Lifeline           recover Root                       NNS Root
NNS Root           upgrade NNS canisters              Governance, Registry, Ledger, CMC, ...
Governance         hold neurons, run proposals        (executed by Root on adoption)
Registry           network topology                   (mutated by adopted proposals)
ICP Ledger         ICP balances                       (fees/params via proposal)
CMC                ICP → cycles mint                  (rate/params via proposal)

An adopted replica-upgrade proposal flows like:
  neurons vote -> Governance tallies -> proposal adopted ->
  Governance calls Root -> Root writes new replica version into Registry ->
  subnets read Registry and upgrade replicas on the next restart boundary.
```

## Gotchas

- **The NNS is not a product you deploy.** It exists on the NNS subnet, pre-existing. Building on ICP means building *into* the world the NNS governs, not standing up your own copy. The SNS is the packaged-up pattern for teams that want their *own* DAO.
- **Proposal topics matter.** Voting power, rejection fees, and following graphs are *per-topic*. A neuron that follows a respected governance neuron on "governance motions" does not automatically follow them on "node admission". Casual voters should think about delegation topic-by-topic.
- **Dissolve delay is the commitment signal.** Neurons with short dissolve delays vote with less weight, period. The point is that liquidity and governance influence are trade-offs.
- **NNS / SNS token flows are independent.** ICP → cycles via the CMC is an NNS-level flow. SNS treasuries hold their own token and cannot mint cycles directly; post-launch SNS cycle top-ups typically come from the SNS's ICP holdings via the CMC.
- **Don't infer specifics from memory.** Exact reward curves, minimum stakes, rejection fees, and topic enumerations are all NNS-governable and have changed over time. If a decision hinges on an exact number, re-check it from a live source.

## See also

- [[sns]]
- [[sns-launch]]
- [[sns-neurons-and-voting]]
- [[subnets]]
- [[principals]]
- [[cycles]]
- [[cycles-wallet]]
- [[canisters]]
