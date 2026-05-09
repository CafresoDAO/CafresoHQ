---
tags: [research, canDB, backend]
---

# What is canDB?

Based on the official documentation, **canDB** is a flexible, high-performance, and horizontally scalable non-relational (NoSQL) database framework built for the Internet Computer. It is developed by ORIGYN-SA / CanScale.

Its primary purpose is to abstract away the complexities of managing data across multiple canisters. This is a significant advantage for developers building on the IC.

### Key Features & Benefits:

*   **Horizontal Scaling:** Automatically manages data partitioning and distribution across multiple canisters as the dataset grows.
*   **Simplified API:** Provides a familiar NoSQL API, hiding the underlying multi-canister complexity.
*   **Automation:** Handles canister spin-up, auto-scaling, data persistence, and stability.
*   **Performance:** Benchmarks are available for review, indicating a focus on performance.

This technology seems to directly address some of the major challenges of building scalable applications on the IC, which is a great fit for our [[01-project-overview-and-tech-stack|project]].

### Primary Resources:

*   **GitHub:** [ORIGYN-SA/CanDB](https://github.com/ORIGYN-SA/CanDB)
*   **API Docs:** [candb.canscale.dev](https://candb.canscale.dev)
*   **Project Site:** [canscale.dev](https://www.canscale.dev/)
