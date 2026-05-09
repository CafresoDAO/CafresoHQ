---
tags: [research, architecture, backend]
---
# 17. Synchronizing the BFF and Data Canisters

Following our plan to introduce a Backend-for-Frontend (BFF) canister in [[16-real-time-frontend-updates-with-canDB]], we need a robust way for it to communicate with our core `canDB` data canisters. All inter-canister communication on the Internet Computer is fundamentally asynchronous message passing.

### The Asynchronous `await` Pattern

The primary mechanism for inter-canister communication is the `async/await` pattern. When our BFF canister needs data, it doesn't make a blocking call; instead, it sends a message to a `canDB` canister and awaits its response. 

**Example Flow:**
1.  The frontend calls a query method on the BFF canister (e.g., `getDashboardData`).
2.  The BFF canister, in turn, makes one or more `await`-ed calls to different `canDB` canisters (e.g., `await userCanister.getProfile(userId)` and `await postsCanister.getRecentPosts()`).
3.  The IC runtime handles the message passing and scheduling. The BFF canister effectively pauses its execution until the responses come back.
4.  Once all awaited calls return, the BFF aggregates the data into a single, UI-friendly object and returns it to the frontend.

This pattern is powerful because it allows a single canister to efficiently orchestrate calls to many others without blocking the entire system.

### One-Way Data Pushes for Caching

We can also use one-way calls, or "fire-and-forget" messages, for proactive updates. 

For example, when a new post is created in the `postsCanister`, it could make a quick, non-awaited call to the BFF canister's `invalidateDashboardCache` method. The `postsCanister` doesn't need to wait for a response; its job is just to notify the BFF that data has changed. This keeps the BFF's cache fresh and ensures users see new data quickly.

### Considerations for Data Consistency

This asynchronous model requires careful thought about data consistency, as we explored in [[07-data-consistency-and-transactions]]. If the BFF needs to perform an operation that involves writing to two different canisters, we must handle potential failure cases where one write succeeds and the other fails. This often involves implementing two-phase commit logic or designing for eventual consistency.