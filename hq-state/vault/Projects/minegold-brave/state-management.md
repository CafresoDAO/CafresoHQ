---
tags: [project-study, minegold-brave]
---
# State Management in `minegold_backend`

The `minegold_backend` canister, primarily implemented in `src/backend/main.mo`, relies heavily on Motoko's stable variables (`var`) to manage and persist its state across canister upgrades. This ensures that critical data, user requests, and configuration remain intact.

## Key Stable Variables and Their Purpose

The following `var` declarations in `main.mo` represent the core persistent state of the canister:

*   `nextBridgeRequestId`, `nextExchangeRequestId`, `nextUNIDepositId`: These `Nat` variables serve as auto-incrementing counters to assign unique identifiers to new bridge, exchange, and UNI deposit requests, respectively.

*   `sGLDTTreasuryBalance`, `batPoolBalance`: `Nat` variables tracking the internal balances of sGLDT and BAT tokens held by the canister. These are essential for managing the project's liquidity and payouts.

*   `uniExchangeRate`: A `Nat` representing the current exchange rate of sGLDT per UNI, stored with 1e8 precision. This rate is used for calculating payouts.

*   `cachedSgldtTreasuryBalance`, `cachedCkUNITreasuryBalance`: `Nat` variables that store the most recently fetched on-chain balances of sGLDT and ckUNI from their respective ledgers. These are updated periodically by an update call (`refreshTreasuryBalances()`) and exposed via query functions for efficient, unauthenticated reads.

*   `cachedMinterDepositAddress`: A `Text` variable storing the fixed ERC-20 deposit address provided by the ICP ERC-20 minter. This address is initialized once by an admin call.

*   `ckUNIMinter`: An actor reference (`actor { ... }`) to the ckUNI minter canister. This variable is primarily for upgrade compatibility with previous versions and its value is ignored in favor of transient references.

*   `cachedBatPrice`, `cachedSGldtPrice`: Optional records (`?{ price : Nat; timestamp : Time.Time; }`) that cache the prices of BAT and sGLDT, along with a timestamp. This allows the canister to serve price data efficiently while managing data freshness.

## Persistent Data Structures

Beyond simple variables, the canister likely uses stable data structures (such as `Map` or `VarArray` from `mo:core`) to store collections of structured data that need to persist. While the specific declarations for these collections are not fully visible in the truncated `main.mo`, the presence of types like `BridgeRequest`, `sGLDTRequest`, and `UniDepositRequest` strongly implies their use for maintaining a history of user interactions and their current status.

Example of a request type, which would be stored in a stable collection:

```motoko
type UniDepositRequest = {
    id : Nat;
    submitter : Principal;
    ethAddress : Text;
    uniAmount : Nat;
    txHash : Text;
    status : UNIDepositStatus;
    sgldtPaid : Nat;
    timestamp : Time.Time;
    lockedExchangeRate : ?Nat;
};
```

## Access Control State

The `accessControlState` variable, initialized with `AccessControl.initState()`, is a crucial part of the canister's persistent state. It manages user roles and permissions, with the `ADMIN_PRINCIPAL` being assigned the `#admin` role during initialization. This state dictates who can call privileged functions within the canister.

```motoko
  let accessControlState = AccessControl.initState();

  do {
    accessControlState.userRoles.add(ADMIN_PRINCIPAL, #admin);
    accessControlState.adminAssigned := true;
  };

  include MixinAuthorization(accessControlState);
```

## Request Status Management

Enums are used to define the lifecycle of various requests, ensuring clear state transitions and preventing issues like double-payouts. For instance, `UNIDepositStatus` defines a specific state machine:

*   `#pending`: Initial state.
*   `#confirmed`: Deposit confirmed.
*   `#processing`: Actively processing the payout (atomically set to prevent race conditions).
*   `#paid`: Payout successfully completed.
*   `#failed`: Payout failed.

This structured approach to state management, leveraging Motoko's stability features, is fundamental to the reliability and upgradeability of the `minegold_backend` canister.