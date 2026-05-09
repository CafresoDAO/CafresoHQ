---
tags: [project-study, minegold-brave, architecture, data-flow]
---

# Data Flow and Transaction Lifecycle

This note documents how data moves through the Minegold.brave DeFi system, from user-initiated actions on Ethereum through ICP canister state changes to final token payouts.

## System Overview

Minegold.brave is a cross-chain bridge that allows users to deposit UNI tokens on Ethereum and receive sGLDT tokens on ICP. The data flows through multiple stages:

1. **Ethereum Layer** — User deposits UNI to ckERC-20 helper contract
2. **Verification Layer** — Canister verifies transaction via Etherscan API
3. **Processing Layer** — State transitions and security checks
4. **Payout Layer** — ICRC-1 token transfers to user
5. **History Layer** — Transaction records for audit trail

## Primary Data Flow: UNI → sGLDT Bridge

### Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant Ethereum
    participant Frontend
    participant Backend as ICP Backend Canister
    participant Etherscan
    participant sGLDTLedger as sGLDT Ledger
    
    User->>Ethereum: Deposit UNI to ckERC-20 helper
    Ethereum-->>User: txHash
    User->>Frontend: Submit deposit (ethAddress, amount, txHash)
    Frontend->>Backend: submitUNIDeposit()
    
    Note over Backend: Validation:
    - Rate limiting
    - Format validation
    - ETH address binding
    - Duplicate check
    
    Backend-->>Frontend: depositId
    Frontend->>Backend: verifyEthTransaction(depositId)
    Backend->>Etherscan: HTTP outcall: gettxreceiptstatus
    Etherscan-->>Backend: confirmation status
    
    Note over Backend: If confirmed:
    - Verify calldata
    - Update status to #confirmed
    
    Backend->>Backend: verifyAndPayUNIDeposit()
    
    Note over Backend: Security checks:
    - Status transition (confirmed → processing)
    - Amount validation
    - Calculate payout
    
    Backend->>sGLDTLedger: icrc1_transfer()
    sGLDTLedger-->>Backend: blockIndex
    
    Note over Backend: Update state:
    - Status = #paid
    - Record tx history
    - Refresh balances
    
    Backend-->>Frontend: "paid: <amount> sGLDT"
    Frontend-->>User: Success notification
```

### Stage 1: Deposit Submission

**Entry Point**: `submitUNIDeposit(ethAddress, uniAmount, txHash, rateHint)`

**Data Validations**:
```motoko
// Rate limiting
if (not isAdmin(caller) and _checkAndRecordSubmission(caller)) {
  Runtime.trap("Rate limit: max 5 deposit submissions per hour per principal");
};

// Minimum deposit guard
if (uniAmount < 100_000) {  // 0.001 UNI
  Runtime.trap("Deposit too small: minimum is 0.001 UNI");
};

// txHash format: 0x + 64 hex chars
if (txHash.size() != 66) { Runtime.trap("Invalid txHash") };

// ethAddress format: 0x + 40 hex chars
if (ethAddress.size() != 42) { Runtime.trap("Invalid ethAddress") };
```

**Security Mechanisms**:

1. **ETH Address Binding** — Cryptographic proof via EIP-191 signature
   ```motoko
   // Front-running defense: require address binding before accepting deposit
   switch (_bindOrCheckEthAddress(caller, ethAddress)) {
     case (?errMsg) { Runtime.trap("Wallet ownership guard: " # errMsg) };
     case null { /* caller owns the bound ETH address */ };
   };
   ```

2. **Duplicate Transaction Prevention**
   ```motoko
   if (seenTxHashes.contains(txHash)) {
     // Return existing deposit ID instead of creating duplicate
     for ((existingId, existing) in uniDeposits.entries()) {
       if (existing.txHash == txHash and existing.submitter == caller) {
         return existingId;
       };
     };
     Runtime.trap("Duplicate txHash: submitted by another principal");
   };
   seenTxHashes.add(txHash);
   ```

3. **Exchange Rate Locking**
   ```motoko
   // Lock rate at submission time (±50% sanity band)
   let effectiveLockedRate : Nat = switch (rateHint) {
     case (?hint) {
       let upper = uniExchangeRate + (uniExchangeRate / 2);  // +50%
       let lower = uniExchangeRate - (uniExchangeRate / 2);  // -50%
       if (hint > upper or hint < lower) uniExchangeRate else hint
     };
     case null { uniExchangeRate };
   };
   ```

**State Created**:
```motoko
type UniDepositRequest = {
  id : Nat;
  submitter : Principal;
  ethAddress : Text;
  uniAmount : Nat;
  txHash : Text;
  status : UNIDepositStatus;  // #pending
  sgldtPaid : Nat;  // 0 initially
  timestamp : Time.Time;
  lockedExchangeRate : ?Nat;
};
```

### Stage 2: Ethereum Verification

**Entry Point**: `verifyEthTransaction(requestId)`

**Flow**:
1. **Cache Check** — 3-second TTL to prevent cycle drain DoS
   ```motoko
   // Each call burns ~15 B cycles on HTTP outcalls
   // Cache prevents spam at ingress rate (~100 req/s)
   if (not isAdmin(caller)) {
     switch (verifyCache.get(requestId)) {
       case (?cached) {
         if (Time.now() - cached.at < VERIFY_CACHE_TTL_NS) {
           return cached.result;  // Return cached result
         };
       };
       case null {};
     };
   };
   ```

2. **Etherscan API Call**
   ```motoko
   let etherscanUrl = "https://api.etherscan.io/v2/api?chainid=1" #
     "&module=transaction&action=gettxreceiptstatus" #
     "&txhash=" # request.txHash # "&apikey=" # etherscanApiKey;
   
   let responseBody = await _httpGetBounded(etherscanUrl, 8192);
   ```

3. **Response Parsing** — Looks for `"result":{"status":"1"}` pattern
   - `status=1` → transaction confirmed
   - `status=0` → transaction failed/reverted
   - API error → return "pending" for retry

4. **Calldata Verification** (see [[security-audit-findings]])
   - Parses full transaction details via Etherscan `eth_getTransactionByHash`
   - Validates:
     - `tx.from == ethAddress` (sender matches)
     - `tx.to == ckErc20HelperContract` (correct target)
     - Input data contains deposit function selector `0x26b3293f`
     - Decoded amount matches `uniAmount`
     - Decoded principal matches `submitter`

**State Transition**:
```motoko
// On successful verification:
let confirmedRequest = { request with status = #confirmed };
uniDeposits.add(requestId, confirmedRequest);

// On Ethereum tx failure:
let failedRequest = { request with status = #failed; uniAmount = 0 };
uniDeposits.add(requestId, failedRequest);
```

### Stage 3: Payout Processing

**Entry Point**: `verifyAndPayUNIDeposit(requestId)`

**Authorization**:
```motoko
// Allow: depositor, admin, OR this canister itself
// (Internal calls route through IC message queue with caller = canister principal)
if (caller != request.submitter and 
    not isAdmin(caller) and 
    caller != Principal.fromActor(Self)) {
  return "error: Unauthorized";
};
```

**Status State Machine**:
```motoko
type UNIDepositStatus = {
  #pending;     // Initial state after submission
  #confirmed;   // Ethereum tx verified
  #processing;  // Payout in flight (prevents double-spend)
  #paid;        // Completed successfully
  #failed;      // Terminal rejection
};

// Critical atomicity:
match (request.status) {
  case (#paid) { return "already_paid: ..." };
  case (#processing) { return "pending: Payout already in progress" };
  case (#pending) { return "pending: Awaiting ETH confirmation" };
  case (#failed) { return "rejected: cannot be retried" };
  case (#confirmed) {
    // Atomically mark #processing BEFORE async call
    let processingRequest = { request with status = #processing };
    uniDeposits.add(requestId, processingRequest);
  };
};
```

**Payout Calculation**:
```motoko
// Use locked exchange rate from deposit time
let effectiveRate = switch (request.lockedExchangeRate) {
  case (?r) r;  // User gets the rate they saw at submission
  case null uniExchangeRate;  // Fallback for old records
};

// uniAmount (e8s) * rate (1e8) / 1e8 = sgldtAmount (e8s)
let sgldtAmount = (request.uniAmount * effectiveRate) / 100_000_000;
```

**ICRC-1 Transfer**:
```motoko
let fee = await sgldtLedger.icrc1_fee();  // Dynamic fee query

let transferResult = await sgldtLedger.icrc1_transfer({
  from_subaccount = null;  // Canister's default account (treasury)
  to = { owner = request.submitter; subaccount = null };
  amount = sgldtAmount;
  fee = ?fee;
  memo = null;
  created_at_time = null;
});

match (transferResult) {
  case (#Ok(blockIndex)) {
    // Update to #paid, record transaction history
    let paidRequest = { request with status = #paid; sgldtPaid = sgldtAmount };
    uniDeposits.add(requestId, paidRequest);
  };
  case (#Err(#InsufficientFunds { balance })) {
    // Revert to #confirmed for admin retry after funding
    let revertedRequest = { request with status = #confirmed };
    uniDeposits.add(requestId, revertedRequest);
  };
  // ... other error cases revert to #confirmed
};
```

### Stage 4: Transaction History Recording

**Dual Records** — Each successful deposit creates TWO transaction records:

1. **Bridge Transaction** (Ethereum side)
   ```motoko
   _recordTx(submitter, {
     id = _nextTxId();
     txType = #Bridge;
     amount = uniAmount;
     tokenSymbol = "UNI";
     status = #Completed;
     timestamp = Time.now();
     ethTxHash = ?txHash;
     icpBlockIndex = null;
     errorMsg = null;
     description = "UNI bridged from Ethereum: <amount> e8s";
   });
   ```

2. **Refine Transaction** (ICP sGLDT payout)
   ```motoko
   _recordTx(submitter, {
     id = _nextTxId();
     txType = #Refine;
     amount = sgldtAmount;
     tokenSymbol = "sGLDT";
     status = #Completed;
     timestamp = Time.now();
     ethTxHash = ?txHash;
     icpBlockIndex = ?blockIndex;
     errorMsg = null;
     description = "sGLDT released from treasury: <amount> e8s";
   });
   ```

**Storage**:
```motoko
// Per-user transaction list (newest-first linked list)
let userTransactions = Map.empty<Principal, List.List<TxRecord>>();

func _recordTx(user : Principal, record : TxRecord) {
  let existing = switch (userTransactions.get(user)) {
    case null List.nil<TxRecord>();
    case (?list) list;
  };
  userTransactions.add(user, List.push(record, existing));
};
```

## Alternative Flow: Auto-Finalize Deposit

**Use Case**: Mobile users who can't capture txHash after MetaMask redirect

**Entry Point**: `autoFinalizeUNIDeposit(ethAddress, uniAmountE8, rateHint)`

**Flow**:
1. **Scan Ethereum history** — Fetch last 10 transactions via Etherscan V2 txlist
   ```motoko
   let url = "https://api.etherscan.io/v2/api?chainid=1" #
     "&module=account&action=txlist" #
     "&address=" # ethAddress #
     "&sort=desc&page=1&offset=10" #
     "&apikey=" # etherscanApiKey;
   ```

2. **Match deposit transaction**
   - `tx.to == ckErc20HelperContract`
   - Input data starts with deposit selector `0x26b3293f`
   - Decoded amount matches `uniAmountE8`

3. **Auto-submit** — Creates UniDepositRequest and triggers verification
   ```motoko
   let requestId = await submitUNIDeposit(ethAddress, uniAmount, foundTxHash, rateHint);
   ignore await verifyAndPayUNIDeposit(requestId);  // Fire-and-forget payout
   return #ok({ requestId; txHash = foundTxHash });
   ```

**Result Variants**:
```motoko
type AutoFinalizeResult = {
  #ok : { requestId : Nat; txHash : Text };  // Found and submitted
  #alreadyExists : { requestId : Nat; txHash : Text; status : Text };  // Already processed
  #noDepositFound : Text;  // No matching tx in recent history
  #apiError : Text;  // Etherscan unavailable — retry
};
```

## Admin Flows

### Direct sGLDT Transfer

**Entry Point**: `adminTransferSGLDT(to, amount)`

**Security**:
```motoko
if (not isAdmin(caller)) {
  return "error: Unauthorized. Only admin can transfer sGLDT.";
};

// FIX-1: Transfer cap to prevent accidental treasury drain
if (amount > MAX_TRANSFER_AMOUNT_SGLDT) {  // 500,000 sGLDT
  return "error: Amount exceeds safety cap of 500,000 sGLDT.";
};
```

**Flow**:
```motoko
let fee = await sgldtLedger.icrc1_fee();
let transferResult = await sgldtLedger.icrc1_transfer({
  from_subaccount = null;  // Canister treasury account
  to = { owner = to; subaccount = null };
  amount;
  fee = ?fee;
  memo = null;
  created_at_time = null;
});
```

### Exchange Rate Management

**Entry Point**: `setUNIExchangeRate(rate)`

```motoko
public shared ({ caller }) func setUNIExchangeRate(rate : Nat) : async () {
  if (not isAdmin(caller)) {
    Runtime.trap("Unauthorized: Only admin can update UNI exchange rate");
  };
  uniExchangeRate := rate;  // 1e8 precision (e.g., 238_000_000 = 2.38 sGLDT/UNI)
};
```

**Note**: Changing the global rate does NOT affect pending deposits — they use `lockedExchangeRate`

## Data Storage Architecture

### State Maps

```motoko
// Primary deposit storage (requestId → request)
let uniDeposits = Map.empty<Nat, UniDepositRequest>();

// Transaction history (principal → list of TxRecord)
let userTransactions = Map.empty<Principal, List.List<TxRecord>>();

// Security / anti-fraud
let ethAddressBinding = Map.empty<Text, Principal>();  // ethAddr → bound principal
let seenTxHashes = Set.empty<Text>();  // Duplicate prevention

// Rate limiting
let submissionTimestamps = Map.empty<Principal, List.List<Time.Time>>();
let verifyCache = Map.empty<Nat, { result : Text; at : Time.Time }>();
```

### Cached Balances

**Problem**: ICRC-1 balance queries are inter-canister calls (slow, cost cycles)

**Solution**: Cached balances refreshed on-demand

```motoko
var cachedSgldtTreasuryBalance : Nat = 0;
var cachedCkUNITreasuryBalance : Nat = 0;

public shared func refreshTreasuryBalances() : async () {
  let sgldtBalance = await sgldtLedger.icrc1_balance_of({
    owner = Principal.fromActor(Self);
    subaccount = null;
  });
  cachedSgldtTreasuryBalance := sgldtBalance;
  
  let ckUNIBalance = await ckUNILedger.icrc1_balance_of({
    owner = Principal.fromActor(Self);
    subaccount = null;
  });
  cachedCkUNITreasuryBalance := ckUNIBalance;
};

// Fast query endpoint (no await needed)
public shared query func getSGLDTTreasuryBalance() : async Nat {
  cachedSgldtTreasuryBalance
};
```

## Error Handling Patterns

### Revertible State Transitions

**Pattern**: Mark `#processing` before async calls, revert to `#confirmed` on failure

```motoko
// BEFORE async call
let processingRequest = { request with status = #processing };
uniDeposits.add(requestId, processingRequest);

try {
  let transferResult = await sgldtLedger.icrc1_transfer(...);
  match (transferResult) {
    case (#Ok(_)) {
      // SUCCESS: mark #paid
      uniDeposits.add(requestId, { request with status = #paid });
    };
    case (#Err(_)) {
      // FAILURE: revert to #confirmed for retry
      uniDeposits.add(requestId, { request with status = #confirmed });
    };
  };
} catch (_) {
  // EXCEPTION: revert to #confirmed
  uniDeposits.add(requestId, { request with status = #confirmed });
};
```

### Terminal Failures

**Pattern**: Mark `#failed` + zero amount → prevents retry/payout

```motoko
if (isFailed) {
  // Ethereum tx reverted — zero the amount so legacy code can't pay it
  let failedRequest = { request with status = #failed; uniAmount = 0 };
  uniDeposits.add(requestId, failedRequest);
  return "failed";
};

// Later in payout:
if (request.uniAmount == 0) {
  return "rejected: deposit was rejected and cannot be retried";
};
```

## Integration Points

### External Systems

1. **Etherscan API** (HTTP outcalls)
   - `gettxreceiptstatus` — Confirms transaction mined
   - `eth_getTransactionByHash` — Full tx details for calldata verification
   - `txlist` — Account transaction history (auto-finalize flow)
   - Rate limit: API key required, canister caches responses

2. **sGLDT Ledger** (ICRC-1 canister `i2s4q-syaaa-aaaan-qz4sq-cai`)
   - `icrc1_balance_of` — Query treasury balance
   - `icrc1_transfer` — Send sGLDT to users
   - `icrc1_fee` — Dynamic fee query

3. **ckUNI Ledger** (ICRC-1 canister `ilzky-ayaaa-aaaar-qahha-cai`)
   - Balance queries, admin transfers

4. **ckERC-20 Minter** (`sv3dd-oaaaa-aaaar-qacoa-cai`)
   - `get_minter_info()` → Returns `erc20_helper_contract_address`
   - Used to initialize deposit address

### Inter-Canister Patterns

**Self-Calls** — Internal functions calling public endpoints

```motoko
// verifyEthTransaction internally calls verifyAndPayUNIDeposit
let payResult = await verifyAndPayUNIDeposit(requestId);

// Caller in this case is Principal.fromActor(Self), not the original user
// Authorization check must allow canister self-calls:
if (caller != Principal.fromActor(Self) and ...) { trap };
```

## Performance Optimizations

### Cycle Management

1. **Verification Cache** — 3s TTL prevents HTTP outcall spam
   - Each `verifyEthTransaction` costs ~15 B cycles
   - Without cache: 100 req/s × 15 B = 1.5 T cycles/s → canister drained in seconds

2. **Bounded HTTP Responses** — `_httpGetBounded(url, maxBytes)`
   - Prevents memory exhaustion from oversized API responses
   - 8 KB limit for receipt status, 32 KB for transaction lists

3. **Lazy Balance Refresh** — Manual `refreshTreasuryBalances()` instead of per-request queries
   - Frontend can poll cached values via fast query calls
   - Updated after successful payouts

## Related Documentation

- [[security-audit-findings]] — Security mechanisms in deposit flow
- [[api-and-endpoints]] — Public function reference
- [[state-management]] — Persistent state variables
- [[key-components]] — Actor structure and imports

## Key Takeaways

1. **Defense in Depth** — Multiple validation layers (format, binding, calldata, status machine)
2. **Atomicity** — Critical state transitions happen before async calls to prevent race conditions
3. **Revertibility** — Failed async operations revert state to allow safe retry
4. **Rate Limiting** — Protects against DoS via both submission caps and response caching
5. **Locked Exchange Rates** — Users receive exactly what they saw at submission time
6. **Dual Transaction Records** — Full audit trail of both Ethereum and ICP sides