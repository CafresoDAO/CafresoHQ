---
tags: [research, canDB, backend, api]
---

# Core canDB API Modules

A review of the official API documentation at `candb.canscale.dev` reveals the primary modules that make up the [[02-what-is-canDB|canDB]] framework. Understanding these is key to implementing it in our backend.

### Core Data & Interaction

*   **`CanDB`**: The main module and entry point for all interactions with the database.
*   **`Entity`**: Represents the base data record or item being stored. This is the fundamental unit of data.
*   **`HashTree`**: The underlying data structure for a single canister, described as a stable `HashMap` mapping a Partition Key to a `RangeTree`.
*   **`RangeTreeV2`**: A stable B-Tree structure that maps an `Entity`'s Sort Key to its actual data (Attributes).

### Canister Management & Utilities

*   **`CanDBAdmin`**: Provides utility methods for the main Index Canister to control the child data canisters.
*   **`CanisterActions`**: High-level functions for interacting with the IC's Management Canister, likely for creating or scaling canisters.
*   **`CanisterMap`**: A data structure for tracking which Partition Key lives on which canister.

This modular structure confirms that `canDB` is designed to abstract away the complexity of multi-canister architecture, letting us focus on the `Entity` and `CanDB` modules for most operations.