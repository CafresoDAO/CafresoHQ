---
tags: [project-study, minegold-brave, http-outcalls, ethereum, security]
---

# HTTP Outcalls and Ethereum Verification

The Minegold.defi bridge uses **ICP's HTTP outcall feature** to verify Ethereum transactions on-chain via Etherscan API. This enables trustless cross-chain verification without centralized oracles.

## HTTP Outcall Library: caffeineai-http-outcalls

**Source**: `.mops/caffeineai-http-outcalls@0.1.0/src/outcall.mo`

### Core Wrapper Functions

```motoko
public func httpGetRequest(
  url : Text,
  extraHeaders : [Header],
  transform : Transform
) : async Text

public func httpPostRequest(
  url : Text,
  extraHeaders : [Header],
  body : Text,
  transform : Transform
) : async Text
```

### Cycles Cost

```motoko
let httpRequestCycles = 231_000_000_000; // ~231B cycles per call
```

**Why 231B cycles**: The library sets a fixed cycles budget per HTTP outcall. The actual Etherscan API calls in practice consume **~15B cycles** (comment from `main.mo:281`), but the library over-provisions to avoid running out mid-request.

**Cost optimization note** (from `main.mo:3013`): The default ICP HTTP outcall max response size is 2MB, which would cost ~270B cycles. By constraining response sizes, the actual cost is much lower.

### Transform Function

The transform function strips headers from responses to ensure **consensus across replicas**:

```motoko
public func transform(input : TransformationInput) : TransformationOutput {
  let response = input.response;
  {
    response with headers = [];
  };
};
```

**Why strip headers**: Different replicas may receive slightly different HTTP headers (timestamps, rate-limit counters, server IDs). By removing headers, only the response body is used for consensus, preventing non-deterministic failures.

**Critical setting** (`main.mo:3030`):

```motoko
is_replicated = ?false; // IMPORTANT: must be unreplicated
```

**Why unreplicated**: Etherscan returns slightly different responses per replica (e.g., dynamic timestamp fields). Running the call unreplicated and then using the transform function to normalize the response prevents consensus mismatches.

### User-Agent

All requests include a custom User-Agent:

```motoko
{ name = "User-Agent"; value = "caffeine.ai" }
```

This identifies the requests as coming from Caffeine.ai platform canisters.

## Etherscan V2 API Integration

**Base API**: `https://api.etherscan.io/v2/api?chainid=1&...`

**Why V2**: Etherscan V1 API was deprecated in April 2026 (comment from `main.mo:2918`). All endpoints now use V2.

**API Key**: Stored in mutable state variable:

```motoko
var etherscanApiKey : Text = ""; // Admin sets this via setEtherscanApiKey()
```

### Key Endpoints Used

#### 1. eth_getTransactionByHash (JSON-RPC Proxy)

**Purpose**: Fetch detailed transaction data for verification

**URL pattern**:

```text
https://api.etherscan.io/v2/api?chainid=1&module=proxy&action=eth_getTransactionByHash&txhash=<TX_HASH>&apikey=<KEY>
```

**Used in**:

- `verifyEthTransaction()` — main verification path (line 1543)
- `_getEthTxByHash()` — helper for fetching tx details (line 2854)
- `_checkIfAlreadySubmitted()` — duplicate detection (line 2920)

**Response shape** (parsed):

```json
{
  "result": {
    "from": "0x...",
    "to": "0x...",
    "input": "0x...",
    "blockNumber": "0x..."
  }
}
```

#### 2. eth_blockNumber (JSON-RPC Proxy)

**Purpose**: Get current Ethereum block height to verify confirmations

**URL pattern**:

```text
https://api.etherscan.io/v2/api?chainid=1&module=proxy&action=eth_blockNumber&apikey=<KEY>
```

**Used in**: `verifyEthTransaction()` to calculate `confirmations = currentBlock - txBlock`

#### 3. account/txlist (Account API)

**Purpose**: Fetch recent transactions for a user's Ethereum address

**URL pattern**:

```text
https://api.etherscan.io/v2/api?chainid=1&module=account&action=txlist&address=<ETH_ADDRESS>&sort=desc&apikey=<KEY>
```

**Used in**: `_getUserRecentTxs()` to find user's recent deposits without requiring exact txHash (line 1803)

**Returns**: Array of transactions sorted by block number descending (newest first)

**Parsing note** (line 1818): The JSON parsing is "imperfect but stable" — relies on Etherscan's consistent response structure rather than full JSON schema validation.

## Verification Flow: submitUNIDeposit → verifyEthTransaction

### Step 1: User Submits Deposit

```motoko
public shared ({ caller }) func submitUNIDeposit(
  ethAddress : Text,
  uniAmount : Nat,
  txHash : Text,
  rateHint : ?Nat
) : async Nat
```

**No HTTP outcall at this stage**. The function just records the deposit request and returns a `requestId`.

### Step 2: Verify Ethereum Transaction

```motoko
public shared ({ caller }) func verifyEthTransaction(requestId : Nat) : async Text
```

**Verification steps**:

1. **Fetch tx by hash** (HTTP outcall #1):

   ```motoko
   let txDataUrl = "https://api.etherscan.io/v2/api?chainid=1&module=proxy&action=eth_getTransactionByHash&txhash=" # txHash # "&apikey=" # etherscanApiKey;
   let rawResponse = await OutCall.httpGetRequest(txDataUrl, [], OutCall.transform);
   ```

2. **Verify `tx.to` matches helper contract**:

   ```motoko
   if (txTo != helperContractAddress) {
     return "ERROR: Transaction sent to wrong contract";
   }
   ```

3. **Verify `tx.from` matches user's declared ETH address**:

   ```motoko
   if (txFrom != request.ethAddress) {
     return "ERROR: Transaction from address mismatch";
   }
   ```

4. **Decode calldata** to verify:
   - Function selector matches `deposit(address,uint256,bytes32)`
   - UNI amount matches user's claim
   - Principal bytes match caller's ICP principal

5. **Check confirmations** (HTTP outcall #2):

   ```motoko
   let blockNumUrl = "https://api.etherscan.io/v2/api?chainid=1&module=proxy&action=eth_blockNumber&apikey=" # etherscanApiKey;
   let currentBlock = await OutCall.httpGetRequest(blockNumUrl, [], OutCall.transform);
   let confirmations = currentBlock - txBlock;
   ```

6. **If confirmations ≥ MIN_CONFIRMATIONS_FOR_PAYOUT (5)**:
   - Mark deposit as `#confirmed`
   - Trigger sGLDT payout

### Caching to Reduce Outcalls

**Verify cache** (line 2447):

```motoko
let verifyCache = Map.empty<Nat, { result : Text; at : Time.Time }>();
let VERIFY_CACHE_TTL_NS = 3 * 1_000_000_000; // 3 seconds
```

**Why cache**: If a user (or an attacker) calls `verifyEthTransaction()` repeatedly for the same `requestId` within 3 seconds, the cached result is returned instead of making fresh HTTP outcalls.

**When cache is invalidated**:

- After 3 seconds
- When admin calls `retryPayout()` to force re-verification

## Error Handling

### Error Variants

```motoko
type VerificationError = {
  #apiError : Text;      // Etherscan unreachable — user should retry
  #rpcError : Text;      // Malformed Etherscan response
  #txNotFound;           // Transaction hash not found on Ethereum
  #wrongContract;        // tx.to != helper contract
  #addressMismatch;      // tx.from != user's declared ETH address
  #amountMismatch;       // Decoded amount != user's claim
  #insufficientConfirmations; // Not enough blocks yet
};
```

### Retry Strategy

**For `#apiError`** (Etherscan unreachable or rate-limited):

```text
"Etherscan unreachable — retry in a moment"
```

**User action**: Wait 10-30 seconds and call `verifyEthTransaction(requestId)` again.

**For `#insufficientConfirmations`**:

```text
"Transaction found but only X/5 confirmations. Wait ~Y minutes."
```

**User action**: Wait for more Ethereum blocks (each block ~12 seconds).

**For `#txNotFound`** (line 1945):

```text
"No matching deposit found for <ethAddress> with amount <amount> e8s. Did you sign and broadcast the deposit? If just now, wait ~30s for Etherscan to index and retry."
```

**Why 30s delay**: Etherscan's indexer has a lag between when a tx is broadcasted and when it appears in their API.

## Client-Side vs On-Chain Verification

The codebase has **two verification modes**:

### Mode 1: On-Chain Verification (Original)

**Used in**: `submitUNIDeposit()` + `verifyEthTransaction()`

**Flow**:

1. User submits deposit with `txHash`
2. Canister fetches tx from Etherscan (HTTP outcall)
3. Canister verifies on-chain

**Pros**: Fully trustless — user can't lie about tx details  
**Cons**: Costs 15B cycles per verification; ~30s Etherscan indexing delay

### Mode 2: Client-Side Verification (New)

**Used in**: `submitUNIDepositWithSignature()`

**Flow** (line 1952):

1. User submits deposit with **cryptographic signature** proving they control the ETH address
2. Canister verifies signature (no HTTP outcall)
3. If signature valid → deposit marked `#confirmed` immediately

**Pros**: Instant confirmation; no cycles cost for HTTP outcalls  
**Cons**: Requires wallet signature support (MetaMask, WalletConnect)

**Comment from code** (line 1953):

> "No Etherscan HTTP outcall is needed — ETH verification happens client-side."

**Security note**: The signature binds the ETH address to the ICP principal (see [[identity-and-access-control#address-binding-eip-191-signatures]]), preventing front-running attacks without needing on-chain verification.

## Admin Functions for HTTP Outcalls

### Set Etherscan API Key

```motoko
public shared ({ caller }) func setEtherscanApiKey(key : Text) : async Text {
  _adminOnly(caller);
  etherscanApiKey := key;
  "API key updated";
};
```

**Why needed**: Etherscan API requires an API key for higher rate limits. Without it, the canister would be limited to ~1 call/5 seconds (public tier).

### Force Retry Payout

```motoko
public shared ({ caller }) func retryPayout(requestId : Nat) : async Text {
  _adminOnly(caller);
  // Bypasses Etherscan re-check and directly attempts sGLDT payout
};
```

**When to use** (line 2331):

> "You want to force a payout retry without waiting for the next Etherscan poll cycle."

**Use case**: If a deposit was verified on-chain but the `icrc1_transfer` to pay out sGLDT failed (e.g., insufficient canister balance), admin can retry just the payout step without re-verifying via HTTP outcall.

## Potential Failure Modes

### 1. Etherscan API Down

**Symptom**: All `verifyEthTransaction()` calls return `#apiError`  
**Impact**: New deposits can't be verified on-chain  
**Mitigation**: Users can switch to client-side verification via `submitUNIDepositWithSignature()`

### 2. Etherscan Rate Limiting

**Symptom**: HTTP responses return `{"status":"0","message":"NOTOK"}` (line 1812)  
**Impact**: Verification calls fail temporarily  
**Mitigation**: 

- Admin sets a higher-tier API key via `setEtherscanApiKey()`
- Users retry after backoff period

### 3. Consensus Mismatch (Replicated Call)

**Symptom**: Canister traps with "replica disagreement" error  
**Root cause**: If `is_replicated = true`, different replicas might receive different Etherscan responses (e.g., dynamic timestamp fields)  
**Fix**: Already mitigated by setting `is_replicated = ?false` (line 3030)

### 4. Cycles Exhaustion

**Symptom**: HTTP outcall fails with "out of cycles"  
**Impact**: All verifications stop  
**Prevention**: Each call budgets 231B cycles; monitor canister cycles balance

## Comparison: HTTP Outcalls vs Oracles

| Aspect | ICP HTTP Outcalls | Traditional Oracles (e.g., Chainlink) |
|--------|------------------|----------------------------------------|
| **Trust model** | Trustless (consensus across ICP replicas) | Trust oracle network |
| **Cost** | ~15B cycles (~$0.000015 at $5/XDR) | Gas fees on source chain + oracle fees |
| **Latency** | ~2-5 seconds | Varies (minutes for some networks) |
| **Dependency** | Etherscan API | Oracle contract + off-chain nodes |
| **Failure mode** | Retry on API error | Oracle network liveness |
| **Censorship resistance** | Can switch API provider | Can switch oracle network |

**Why Minegold chose HTTP outcalls**: For a bridge that only needs to verify Ethereum transactions (not post data back to Ethereum), HTTP outcalls provide a simpler, cheaper, and sufficiently decentralized solution compared to running an oracle network.

## Related Documentation

- [[backend-core-implementation#ethereum-transaction-verification]] — full verification flow
- [[identity-and-access-control#address-binding-eip-191-signatures]] — client-side signature verification
- [[token-economics-and-exchange-rates#exchange-rate-locking]] — why rate hints matter for verification timing
- [[security-audit-findings#front-running-protection]] — why signature-based flow was added

## Code References

- `src/backend/main.mo:1505-1750` — `verifyEthTransaction()` implementation
- `src/backend/main.mo:2826-2950` — `_getEthTxByHash()` helper
- `src/backend/main.mo:1762-1850` — `_getUserRecentTxs()` for fuzzy tx lookup
- `.mops/caffeineai-http-outcalls@0.1.0/src/outcall.mo` — HTTP wrapper library