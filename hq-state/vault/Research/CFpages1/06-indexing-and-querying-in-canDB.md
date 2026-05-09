---
tags: [research, canDB, ICP]
---

# Indexing and Querying in canDB

As we've seen in [[04-canDB-data-storage-model]] and [[05-data-sharding-and-routing-strategies]], `canDB` distributes data across multiple canisters. While this is great for scalability, it introduces a challenge: how do you efficiently query for specific data without scanning every single canister?

This is a classic database problem. Without a proper index (like a library's card catalog), finding all records that match a specific criteria would require a full-system scan, which is slow and computationally expensive.

## Automated Indexing

`canDB` addresses this with what appears to be a layer of **automated indexing**. The system is designed to create and maintain indices on behalf of the developer, which dramatically simplifies the process of building performant dApps. This allows for more complex, real-time data processing and analytics directly on the blockchain.

## The Index Canister Pattern

A concrete example of this pattern on the Internet Computer is the **Index Canister**. As described by DFINITY for ledger applications, an index canister acts as a specialized search endpoint. Instead of forcing a user to fetch all transaction blocks to find those related to a specific account, the index canister maintains a direct mapping (e.g., `account -> [transaction_ids]`).

This pattern likely forms the foundation of `canDB`'s querying capabilities. By creating and managing these specialized index canisters, `canDB` can:

-   Route queries directly to the canisters holding the relevant index data.
-   Avoid broadcasting queries to every data-holding canister (`data shard`).
-   Enable complex, multi-field queries that would otherwise be impractical in a decentralized environment.

This strategic use of indexing is crucial for optimizing query performance and ensuring that applications built on `canDB` can access data quickly and efficiently.