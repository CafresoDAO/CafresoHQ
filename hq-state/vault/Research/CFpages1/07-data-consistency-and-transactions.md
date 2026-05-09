---
tags: [research, canDB, database]
---

# Data Consistency and Transactions in canDB

In any distributed database, and especially one like `canDB` that operates across multiple canisters, ensuring data consistency is paramount. While `canDB` abstracts away much of the complexity of [[05-data-sharding-and-routing-strategies|data sharding]], developers must understand the guarantees it provides for concurrent operations and atomic updates.

## The Challenge of Distributed Consistency

When data is spread across different canisters, a single logical operation (like transferring funds between two user accounts stored in different canisters) might involve multiple separate writes. This introduces risks:

- **Concurrent Updates:** Two processes might try to update the same piece of data simultaneously, leading to race conditions.
- **Partial Failures:** One canister write might succeed while another fails, leaving the database in an inconsistent state.

## Potential Consistency Models for canDB

The Internet Computer's underlying protocol provides a strong foundation, processing messages in rounds. However, inter-canister communication is asynchronous. This suggests `canDB` might operate with one of the following models:

1.  **Strong Consistency (within a single canister):** Operations within a single data canister are likely atomic and strongly consistent, leveraging the single-threaded execution of canisters on the IC. For any data residing in one canister, this is straightforward.

2.  **Eventual Consistency (across canisters):** For transactions that span multiple canisters, `canDB` likely relies on an eventually consistent model. This means that if no new updates are made, all replicas (or data shards) will eventually converge to the same state. This is a common and practical approach in large-scale distributed systems.

3.  **Transactional Guarantees:** Implementing true ACID-like transactions across canisters is complex. It often requires two-phase commit (2PC) protocols or Sagas, which would need to be built into the [[03-core-canDB-api-modules|core API]]. Without explicit documentation, we should assume that multi-canister operations are *not* atomic by default.

Understanding `canDB`'s specific approach is crucial for building reliable applications. If strong transactional guarantees are needed, developers might need to implement their own coordination logic on top of `canDB`'s primitives.