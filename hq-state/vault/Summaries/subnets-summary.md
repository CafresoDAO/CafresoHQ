---
source: "[[01-Concepts/subnets.md]]"
generated: 2026-05-02 02:07
agent: auto
---

# Summary of subnets

- A subnet is an independent blockchain of replicated nodes that jointly host and execute a partition of ICP’s [[Canisters]]; the [[ICP Map of Content]] places [[Subnets]] in Core Architecture alongside [[Cycles]], [[Principals]], [[Replica]], and [[Consensus]].
- ICP shards into subnets because one global blockchain cannot host millions of canisters without state-size and consensus overhead; each subnet is a BLS-signed chain and tamper-evident replicated state machine.
- Every node in a subnet holds the full state of every canister on that subnet and executes every message; subnet size trades throughput for security, with the assumption “fewer than 1/3 Byzantine nodes per subnet.”
- Subnets run threshold-signed [[Consensus]], and clients verify chain-key signatures rather than trusting individual nodes; [[Replica]] is the ICP node software that participates in this execution model.
- Cross-subnet calls extend [[Inter-Canister Calls]] across subnet boundaries: requests and responses are routed with chain-key signatures, but latency is higher than intra-subnet calls, so tightly coupled canisters should be co-located.
- Canister placement is assigned by the NNS or by subnet type, not routinely migrated by developers; [[Local Replica]] is useful for development but lacks real subnet consensus, while [[Cycles]] pay for the compute, memory, messages, and storage consumed by canisters on subnets.

## Source
[[01-Concepts/subnets.md]]

## Linked context
- [[00-Index/icp-moc.md]]
- [[00-Index/learning-log.md]]
- [[01-Concepts/canisters.md]]
- [[01-Concepts/cycles.md]]
- [[01-Concepts/inter-canister-calls.md]]
- [[01-Concepts/local-replica.md]]
