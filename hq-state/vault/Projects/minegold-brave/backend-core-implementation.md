---
tags: [project-study, minegold-brave]
---
# Backend Core Implementation

The project's backend is a single, monolithic Motoko actor defined in `src/backend/main.mo`. This canister is stateful and serves as the central controller for all core business logic, including treasury management, token exchanges, and cross-chain asset bridging.

## Key Responsibilities

The main actor is responsible for several critical functions:

- **Treasury Management**: The canister itself acts as the treasury, holding and managing the project's `sGLDT` and `ckUNI` tokens. It defines hardcoded transfer caps to prevent accidental draining of funds.
- **Token Exchange**: It processes requests to exchange proprietary tokens (`BB_TOKEN`) for `sGLDT`, calculating the amounts and handling the state transitions for each request.
- **Asset Bridging**: It manages the process for users to deposit UNI from Ethereum and receive `sGLDT` on the IC. This involves interacting with the `ckErc20Minter` canister.
- **Identity & Security**: It uses EIP-191 signature verification to cryptographically link a user's Ethereum address to their ICP principal. Access control is managed via a simple role system with a hardcoded admin principal.

## Architecture & State

The canister is designed as a stateful actor, maintaining its state across upgrades. Key state variables track request IDs, cached token prices, treasury balances, and the current exchange rate.

```motoko
actor Self {
  // Persistent State
  let accessControlState = AccessControl.initState();

  var nextBridgeRequestId = 1;
  var nextExchangeRequestId = 1;
  var nextUNIDepositId = 1;
  var sGLDTTreasuryBalance : Nat = 0; // kept for upgrade compatibility
  var batPoolBalance : Nat = 0;
  // UNI exchange rate: sGLDT per UNI in 1e8 precision (default 238000000 = 2.38 sGLDT per UNI)
  var uniExchangeRate : Nat = 238_000_000;
  // ... more state variables
}
```

## Inter-Canister Communication

The actor communicates with several other canisters to perform its duties, primarily ICRC-1 token ledgers and the DFINITY-provided chain-key minter for ERC-20 tokens.

```motoko
  // ICRC-1 Ledger Actor References
  let sgldtLedger : actor {
    // ... ICRC-1 methods
  } = actor ("i2s4q-syaaa-aaaan-qz4sq-cai");

  let ckUNILedger : actor {
    // ... ICRC-1 methods
  } = actor ("ilzky-ayaaa-aaaar-qahha-cai");

  // ckERC-20 Minter Canister
  transient let ckErc20Minter : actor {
    get_minter_info : () -> async MinterInfo;
  } = actor ("sv3dd-oaaaa-aaaar-qacoa-cai");
```

This monolithic approach centralizes all logic, making state management straightforward but potentially creating a single point of failure and complexity. It connects directly to the project's [[canister-architecture-and-api-surface]], [[identity-and-access-control]], and [[token-economics-and-exchange-rates]].