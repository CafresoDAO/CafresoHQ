---
tags: [project-study, minegold-brave]
---

# Core Data Structures and State

The primary data structures for the Minegold project are defined as Motoko `type` aliases within the main backend actor in `src/backend/main.mo`. These types model the core business logic, including token exchanges, deposits, and cross-chain bridging.

## ICRC-1 Token Types

The canister interacts with ICRC-1 compliant token ledgers for sGLDT and ckUNI. It uses a standard set of types for these interactions, which are fundamental to its operation.

```motoko
type ICRC1Account = { owner : Principal; subaccount : ?Blob };

type ICRC1TransferArgs = {
  from_subaccount : ?Blob;
  to : ICRC1Account;
  amount : Nat;
  fee : ?Nat;
  memo : ?Blob;
  created_at_time : ?Nat64;
};

type ICRC1TransferResult = { #Ok : Nat; #Err : ICRC1TransferError };
```

These types are used when calling the `icrc1_transfer` and `icrc1_balance_of` methods on the `sgldtLedger` and `ckUNILedger` actor references, forming the basis of the project's [[token-economics-and-exchange-rates]].

## Bridge Request

A `BridgeRequest` represents a user's request to bridge BAT tokens. It captures all necessary information to process and track the bridge.

```motoko
type BridgeStatus = {
  #pending;
  #approved;
  #rejected;
};

type BridgeRequest = {
  id : Nat;
  submitter : Principal;
  ethAddress : Text;
  batAmount : Nat;
  status : BridgeStatus;
  timestamp : Time.Time;
};
```
-   `id`: A unique identifier for the request.
-   `submitter`: The ICP `Principal` of the user initiating the request.
-   `ethAddress`: The user's Ethereum address for verification.
-   `batAmount`: The quantity of BAT to be bridged.
-   `status`: The current state of the request, managed by admins.

## sGLDT Exchange Request

This type models a request to exchange the project's internal `bbToken` for `sGLDT`.

```motoko
type ExchangeStatus = {
  #pending;
  #approved;
  #rejected;
};

type sGLDTRequest = {
  id : Nat;
  submitter : Principal;
  bbTokenAmount : Nat;
  sgldAmountCalculated : Nat;
  status : ExchangeStatus;
  timestamp : Time.Time;
};
```

## UNI Deposit Request

The `UniDepositRequest` is the most complex data structure, designed to handle cross-chain deposits from Ethereum. It includes a multi-step status to prevent race conditions and ensure transactional integrity during the asynchronous process.

```motoko
type UNIDepositStatus = {
  #pending;    // Initial state
  #confirmed;  // ETH transaction confirmed
  #processing; // Payout initiated, locked to prevent double-spend
  #paid;        // sGLDT payout successful
  #failed;      // Terminal state for invalid deposits
};

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
-   `status`: A state machine that tracks the deposit from submission to payout, crucial for [[http-outcalls-and-ethereum-verification]].
-   `lockedExchangeRate`: Captures the exchange rate at the time of deposit to guarantee the user receives the expected amount of sGLDT, protecting against price volatility.