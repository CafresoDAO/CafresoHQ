---
title: Subnets
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/subnet
source:
  - https://internetcomputer.org/docs/building-apps/essentials/network-overview
  - https://internetcomputer.org/docs/references/subnets/subnet-types
related:
  - "[[canisters]]"
  - "[[consensus]]"
  - "[[replica]]"
difficulty: intermediate
open_questions:
  - Current count and node sizes for fiduciary vs. application subnets — these change as NNS governance adds capacity.
  - Exact replication factors in use today.
---

# Subnets

> A subnet is an independent blockchain of replicated nodes that jointly host and execute a partition of ICP's [[canisters]].

## Why it exists

A single global blockchain cannot host millions of canisters without collapsing under state size and consensus overhead. ICP shards: each **subnet** is its own BLS-signed chain running a subset of canisters, and the collection of subnets is the "Internet Computer." Subnets let the network scale horizontally while each individual subnet remains a tamper-evident replicated state machine.

## How it works

- **Replication** — every node in a subnet holds the full state of every canister on that subnet and executes every message. Subnet size (e.g., 13-, 34-, or larger node counts) trades throughput for security.
- **Consensus** — the subnet runs a BLS threshold-signed consensus protocol; the chain-key signature produced each round is what clients verify. See [[consensus]].
- **Subnet types** — common distinctions: *system* subnets (NNS, II, cycles-minting — run NNS-critical canisters), *application* subnets (general dapps), *fiduciary* subnets (higher replication for financial workloads), *European* subnets (geo-restricted for data-residency).
- **Inter-subnet calls** — a canister on subnet A can call a canister on subnet B; the call is routed and the response carries a chain-key signature the caller's subnet can verify without trusting the other subnet's nodes.
- **Canister placement** — when you create a canister, it is assigned to a subnet (either chosen by the NNS or specified via subnet type). Migration between subnets is a governance operation, not something dapp developers do routinely.

## Example

```bash
# Ask dfx to show which subnet a canister lives on.
dfx canister --network ic id my_canister
# The canister ID (principal) encodes its subnet routing; the dashboard
# https://dashboard.internetcomputer.org resolves it to a subnet page.
```

## Gotchas

- **Cross-subnet latency** is meaningfully higher than intra-subnet calls. Co-locate tightly coupled canisters.
- Subnet state size is bounded by the slowest node's storage; a runaway canister can pressure its neighbors.
- Not every feature is available on every subnet — e.g., threshold ECDSA, HTTPS outcalls, and Bitcoin integration are only enabled on subnets that have been wired up for them.
- The security assumption is "fewer than 1/3 of nodes Byzantine **per subnet**," not globally. Picking a larger subnet raises that bar.

## See also

- [[canisters]]
- [[consensus]]
- [[replica]]
- [[cycles]]
