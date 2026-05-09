---
tags: [project-study, minegold-brave, api, endpoints]
---
# API and Endpoints

The `Minegold.brave` backend, implemented in `src/backend/main.mo`, exposes several shared functions that act as its public API endpoints. These functions facilitate interactions with the Minegold protocol, including token bridging, exchanges, and treasury operations.

## Key Canister Endpoints

The `actor Self` in `main.mo` defines the primary canister and its public interface. While the file is large, I've identified several key areas that imply specific API endpoints:

### 1. Treasury and Balance Management

Functions related to checking and updating treasury balances for `sGLDT` and `ckUNI` are critical. These are often `query` calls for public readability and `update` calls for administrative actions.

```motoko
// Cached on-chain balances — updated by refreshTreasuryBalances() (an update call).
// Exposed via public shared query funcs so anonymous/unauthenticated callers can read them.
var cachedSgldtTreasuryBalance : Nat = 0;
var cachedCkUNITreasuryBalance : Nat = 0;
```

This indicates there are likely `shared query` functions to retrieve `cachedSgldtTreasuryBalance` and `cachedCkUNITreasuryBalance`.

### 2. Token Transfers (ICRC-1 Standard)

The canister interacts with ICRC-1 compliant ledgers for `sGLDT` and `ckUNI`. This implies internal calls to these ledgers, but also potentially exposed functions for users to initiate transfers or check their balances.

```motoko
let sgldtLedger : actor {
  icrc1_balance_of : (ICRC1Account) -> async Nat;
  icrc1_transfer : (ICRC1TransferArgs) -> async ICRC1TransferResult;
  icrc1_fee : () -> async Nat;
} = actor ("i2s4q-syaaa-aaaan-qz4sq-cai");

let ckUNILedger : actor {
  icrc1_balance_of : (ICRC1Account) -> async Nat;
  icrc1_transfer : (ICRC1TransferArgs) -> async ICRC1TransferResult;
  icrc1_fee : () -> async Nat;
} = actor ("ilzky-ayaaa-aaaar-qahha-cai");
```

While these are internal ledger actors, the main canister would likely wrap them with its own `shared` functions for user interaction, such as `transferSGLDT` or `transferCkUNI`.

### 3. Bridging Requests

The `BridgeRequest` type suggests an API for users to submit requests to bridge tokens (e.g., BAT) to the ICP network.

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

There would be `shared update` functions like `submitBridgeRequest` and potentially `getBridgeRequestStatus`.

### 4. sGLDT Exchange Requests

Similar to bridging, the `sGLDTRequest` type indicates an exchange mechanism, likely for converting some other token into `sGLDT`.

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

This would involve `shared update` functions such as `submitSGLDTExchange` and `getSGLDTExchangeStatus`.

### 5. UNI Deposit and Payout

The `UniDepositRequest` type and associated statuses (`#pending`, `#confirmed`, `#processing`, `#paid`, `#failed`) point to a detailed process for users to deposit UNI and receive `sGLDT` payouts.

```motoko
type UNIDepositStatus = {
  #pending;
  #confirmed;
  #processing;
  #paid;
  #failed;
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

Expected API calls include `submitUniDeposit`, `confirmUniDeposit`, and `getUniDepositStatus`.

### 6. Admin Functions

The presence of `ADMIN_PRINCIPAL` and `MixinAuthorization` strongly suggests administrative endpoints for managing the protocol, such as setting exchange rates, approving/rejecting requests, or initializing minter addresses.

```motoko
let ADMIN_PRINCIPAL : Principal = Principal.fromText("rc62u-qypnw-bbkkp-d56wk-tnzaq-vwhi2-cqqay-q56hw-gsqbp-6wegl-jae");
// ...
include MixinAuthorization(accessControlState);
```

These would be `shared update` functions restricted to the `ADMIN_PRINCIPAL`.

## Data Flow Implications

User interactions typically follow a pattern:
1.  **Submission**: A user calls a `shared update` function (e.g., `submitBridgeRequest`) to initiate an action.
2.  **State Update**: The canister's internal state variables (e.g., `nextBridgeRequestId`, `bridgeRequests` map) are updated.
3.  **Query**: Users can call `shared query` functions (e.g., `getBridgeRequestStatus`) to check the status of their requests.
4.  **Admin Action**: For certain requests, an admin might call a `shared update` function to approve or reject them, triggering further internal logic (e.g., token transfers).

This structure ensures that the canister maintains a consistent state and provides clear interfaces for both users and administrators.
