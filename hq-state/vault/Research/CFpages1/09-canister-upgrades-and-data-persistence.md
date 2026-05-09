---
tags: [research, canDB, ICP]
---

# Canister Upgrades and Data Persistence

One of the most critical operational aspects of developing on the Internet Computer is managing canister upgrades. Unlike traditional systems, a canister's heap memory (where application state is typically held during execution) is wiped clean when its Wasm code is upgraded. This presents a significant challenge: how to preserve data across deployments.

The solution lies in ICP's **stable memory**.

### Heap vs. Stable Memory

- **Heap Memory:** Fast, managed by the Wasm module, but transient. It is discarded during an upgrade.
- **Stable Memory:** A separate, persistent memory space that survives upgrades. Data must be explicitly moved from the heap to stable memory before an upgrade and then reloaded afterward.

### The Upgrade Lifecycle Hooks

To manage this data transfer, the IC provides two special system functions that developers can implement in their canisters:

1.  `pre_upgrade`: This function is automatically executed *before* the canister's Wasm is replaced. Its job is to serialize the necessary data from the heap and write it into stable memory.
2.  `post_upgrade`: This function is executed *after* the new Wasm has been installed. Its purpose is to read the data from stable memory, deserialize it, and repopulate the new heap, effectively restoring the canister's state.

### How `canDB` Simplifies This

Manually managing serialization and stable memory can be complex and error-prone, especially as data models evolve. This is a core value proposition of `canDB`.

- It abstracts away the low-level details of stable memory management.
- It provides stable data structures (like `StableBTreeMap`) that inherently live in stable memory, reducing or eliminating the need for manual `pre_upgrade` and `post_upgrade` logic for application data.
- This directly addresses the challenge of refactoring and partitioning data models, as mentioned in the research, making the entire [[04-canDB-data-storage-model|data storage model]] more robust and scalable across updates.

By handling data persistence automatically, `canDB` allows developers to focus on application logic rather than the mechanics of data survival, which is a major roadblock for wider IC adoption.