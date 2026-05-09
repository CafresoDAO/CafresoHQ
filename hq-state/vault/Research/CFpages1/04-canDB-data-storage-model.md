---
tags: [research, canDB, storage]
---

# CanDB's Data Storage Model: NoSQL on Stable Memory

`canDB` is fundamentally a non-relational (NoSQL) database designed for the Internet Computer. Its architecture is built to solve one of the core challenges of the IC: scalable, persistent storage.

Key characteristics of its storage model include:

- **Multi-Canister Architecture**: `canDB` achieves horizontal scalability by distributing data across multiple canisters. This allows a database to grow beyond the memory limits of a single canister, which is a significant advantage for data-intensive applications.

- **Leveraging Stable Memory**: The Internet Computer provides two types of memory for canisters: heap memory (fast, but cleared on canister upgrades) and stable memory (slower, but persistent). `canDB` is built to use **stable memory** for data persistence. This ensures that all database records survive code updates and system upgrades, making it a reliable long-term storage solution.

- **NoSQL Flexibility**: As a non-relational database, it offers flexibility in data schemas, similar to other NoSQL databases like MongoDB. This is well-suited for the evolving requirements of modern web applications.

This storage model is a core part of what makes [[02-what-is-canDB|canDB]] a powerful tool. The abstraction it provides allows developers to work with a scalable database without manually managing data distribution and persistence across multiple canisters, which would otherwise be a complex task handled via the [[03-core-canDB-api-modules|core API modules]].