---
tags: [project-study, minegold-brave, architecture, api]
---

# Canister Architecture and API Surface

Minegold.brave is structured as a three-canister Internet Computer application with a Motoko backend, asset frontend, and Internet Identity integration.

## Canister Topology

**Defined in `dfx.json`:**

### 1. Backend Canister (`backend`)
- **Type:** Custom (Motoko)
- **Source:** `src/backend/main.mo` (50,000+ lines)
- **Build:** `mops install && mops build` → produces `backend.wasm` and `backend.did`
- **Role:** Core business logic, token operations, Ethereum verification, treasury management

### 2. Frontend Canister (`frontend`)
- **Type:** Assets
- **Source:** `src/frontend/dist` (pre-built React application)
- **Build:** `pnpm install && pnpm build`
- **Dependencies:** Depends on `backend` canister
- **Role:** Serves static UI assets, React SPA with hooks for price fetching and canister interaction

### 3. Internet Identity Canister (`internet_identity`)
- **Type:** Custom (remote reference)
- **Source:** DFINITY official release artifacts
- **Mainnet ID:** `rdmx6-jaaaa-aaaaa-aaadq-cai`
- **Role:** Decentralized authentication provider

## Backend Actor Architecture

**Entry point:** `src/backend/main.mo`

```motoko
actor Self {
  // Constants
  let BB_TOKEN_DECIMALS = 8;
  let SGLDT_DECIMALS = 8;
  let PRICE_CACHE_DURATION = 300_000_000_000; // 5 min
  
  // Hardcoded admin
  let ADMIN_PRINCIPAL : Principal = Principal.fromText(
    "rc62u-qypnw-bbkkp-d56wk-tnzaq-vwhi2-cqqay-q56hw-gsqbp-6wegl-jae"
  );
  
  // Transfer caps (audit fix FIX-1)
  let MAX_TRANSFER_AMOUNT_SGLDT : Nat = 50_000_000_000_000;
  let MAX_TRANSFER_AMOUNT_CKUNI : Nat = 50_000_000_000_000_000_000;
  
  // Persistent state
  let accessControlState = AccessControl.initState();
  var nextBridgeRequestId = 1;
  var nextExchangeRequestId = 1;
  var nextUNIDepositId = 1;
  // ... 20+ state variables
}
```

### State Management

The canister manages persistent state across upgrades using:

**Core Balances:**
- `sGLDTTreasuryBalance` — legacy, kept for upgrade compatibility
- `batPoolBalance` — BAT token pool balance
- `cachedSgldtTreasuryBalance` — on-chain sGLDT balance snapshot
- `cachedCkUNITreasuryBalance` — on-chain ckUNI balance snapshot

**Exchange Rates:**
- `uniExchangeRate` — sGLDT per UNI in 1e8 precision (default: 2.38)
- `cachedBatPrice` / `cachedSGldtPrice` — price cache with 5-minute TTL

**Request Queues:**
- `bridgeRequests` — ETH address → BAT bridge requests
- `sgldtRequests` — BAT → sGLDT exchange requests  
- `uniDepositRequests` — UNI deposit → sGLDT payout requests

**Ethereum Integration:**
- `cachedMinterDepositAddress` — fixed ERC-20 deposit address from ICP minter
- `ethAddressBindings` — ETH address ↔ ICP Principal bindings (cryptographically verified)

### External Canister References

**ICRC-1 Token Ledgers:**
```motoko
let sgldtLedger = actor("i2s4q-syaaa-aaaan-qz4sq-cai");
let ckUNILedger = actor("ilzky-ayaaa-aaaar-qahha-cai");
```

**Chain-Key Bridge:**
```motoko
let ckErc20Minter = actor("sv3dd-oaaaa-aaaar-qacoa-cai");
```

The minter canister provides `get_minter_info()` to retrieve the Ethereum helper contract address that users deposit UNI to.

## API Surface (50+ Public Methods)

### Admin Operations
- `adminGrantAdmin(newAdmin)` — Grant admin role to principal
- `adminTransferSGLDT(to, amount)` — Transfer sGLDT from treasury (capped)
- `adminTransferCkUNI(to, amount)` — Transfer ckUNI from treasury (capped)
- `adminMintCkUNI(ethTxHash, uniAmount)` — Mint ckUNI after verifying ETH deposit
- `adminDissolveCkUNI(amount, ethAddress)` — Dissolve ckUNI back to UNI on Ethereum
- `adminSetEtherscanApiKey(key)` — Configure Etherscan API key
- `adminSetUniContract(address)` — Set UNI ERC-20 contract address
- `adminSetCkerc20Helper(address)` — Set chain-key helper contract address
- `adminGetRuntimeConfig()` — Retrieve current configuration snapshot

### Treasury & Balance Queries
- `getSGLDTTreasuryBalance()` — Query cached sGLDT balance
- `getCkUNITreasuryBalance()` — Query cached ckUNI balance
- `getTreasuryICRC1Balances()` — Query both cached balances
- `refreshTreasuryBalances()` — Fetch latest balances from ledgers (update call)
- `getCanisterSGLDTBalance()` — Live ICRC-1 balance query
- `getUserSGLDTBalance(principal)` — Get user's sGLDT balance
- `getPayoutReadiness()` — Check treasury readiness for payouts
- `getPayoutDiagnostic()` — Detailed diagnostic info
- `diagnosePayoutAbility(depositId)` — Diagnose specific deposit payout readiness

### Bridge Requests (BAT ↔ ETH)
- `submitBridgeRequest(ethAddress, batAmount)` — User submits BAT → ETH bridge request
- `approveBridgeRequest(id)` — Admin approves bridge request
- `rejectBridgeRequest(id)` — Admin rejects bridge request
- `getBridgeRequests()` — List all bridge requests

### sGLDT Exchange (BAT → sGLDT)
- `submitSGLDTExchangeRequest(batAmount)` — User requests BAT → sGLDT exchange
- `approveSGLDTExchangeRequest(id)` — Admin approves exchange
- `rejectSGLDTExchangeRequest(id)` — Admin rejects exchange

### UNI Deposits & Payouts
**Primary Flow:**
1. User binds ETH address to ICP principal via `bindEthAddressEip191(signature)` or `bindEthAddressViaTx(txHash)`
2. User deposits UNI to minter's helper contract on Ethereum
3. User calls `submitUNIDeposit(ethAddress, amount, txHash, rateHint)`
4. System verifies via `autoFinalizeUNIDeposit()` or `verifyAndPayUNIDeposit()`
5. sGLDT payout triggered via `triggerSGLDTPayout(requestId)`

**Methods:**
- `bindEthAddressEip191(signature, message, ethAddress)` — Bind ETH address using EIP-191 signature
- `bindEthAddressViaTx(txHash)` — Bind ETH address by verifying an Ethereum transaction
- `isCallerBoundToEth(ethAddress)` — Query binding status
- `submitUNIDeposit(ethAddress, amount, txHash, rateHint)` — Submit deposit claim
- `autoFinalizeUNIDeposit(depositId, txHash, fromAddress, destAddress)` — Auto-verify and finalize
- `verifyAndPayUNIDeposit(requestId)` — Manual verify & pay flow
- `retryUNIDepositPayout(requestId)` — Retry failed payout
- `triggerSGLDTPayout(requestId)` — Trigger sGLDT payout for confirmed deposit
- `resetMiningPhase(requestId)` — Admin: reset deposit to pending (error recovery)

### Ethereum Verification
- `getEthBalanceOnchain(ethAddress)` — Query ETH balance via Etherscan HTTP outcall
- `getUniBalanceOnchain(ethAddress)` — Query UNI balance via Etherscan
- `getWalletBalances(ethAddress)` — Get both ETH and UNI balances
- `verifyEthTransaction(requestId)` — Verify Ethereum transaction for a deposit request

### Exchange Rate Management
- `setUNIExchangeRate(rate)` — Admin: set UNI → sGLDT rate (1e8 precision)
- `setLiveExchangeRate(rate)` — Update live exchange rate
- `syncLiveExchangeRate(rate)` — Sync rate with error handling
- `getBatPrice()` — Get BAT price (cached, 5-min TTL)
- `getSGLDTPrice()` — Get sGLDT price (cached, 5-min TTL)

### Minter Integration
- `getCkUNIMinterDepositAddress(userPrincipal)` — Get user's deposit address from minter
- `initializeMinterDepositAddress()` — Initialize cached minter address (admin)
- `selfInitializeMinterAddress()` — Self-call to initialize minter address

### Misc
- `saveCallerUserProfile(profile)` — Save user profile metadata
- `addTransaction(user, record)` — Add transaction record (internal)

## Type System

**ICRC-1 Types:**
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

**Request Types:**
```motoko
type BridgeRequest = {
  id : Nat;
  submitter : Principal;
  ethAddress : Text;
  batAmount : Nat;
  status : { #pending | #approved | #rejected };
  timestamp : Time.Time;
};

type UniDepositRequest = {
  id : Nat;
  submitter : Principal;
  ethAddress : Text;
  uniAmount : Nat;
  sgldtAmountCalculated : Nat;
  status : { #pending | #confirmed | #processing | #paid | #failed };
  txHash : Text;
  timestamp : Time.Time;
  // ... additional fields
};
```

**State Machine:** UNI deposits follow a strict state machine to prevent double-payout:
```
#pending → #confirmed → #processing → #paid
           ↓
         #failed (terminal)
```

The `#processing` state is set atomically before the async ICRC-1 transfer call. Concurrent payout attempts see `#processing` and reject, preventing race conditions.

## Network Configuration

**Local Development:**
```json
{
  "bind": "127.0.0.1:4943",
  "type": "ephemeral",
  "replica": { "subnet_type": "application" }
}
```

**Mainnet (IC):**
```json
{
  "providers": ["https://icp-api.io"],
  "type": "persistent"
}
```

## Dependencies & Imports

**Core Libraries:**
- `mo:core/*` — Motoko standard library (Array, Map, Set, Time, Timer, etc.)
- `mo:caffeineai-authorization` — Access control and role-based authorization
- `mo:caffeineai-http-outcalls` — HTTP outcalls for Ethereum verification
- `mo:sha3` — SHA-3 hashing for EIP-191 signature verification
- `mo:ecdsa` — ECDSA signature verification for Ethereum addresses

**Package Manager:** `.mops` directory contains versioned dependencies (core@1.0.0, core@2.2.0, base@0.14.14, base@0.16.0)

## Security Highlights

1. **Admin Transfer Caps** (FIX-1 from audit):
   - sGLDT: 500,000 max per call
   - ckUNI: 50 max per call
   - Prevents single-call treasury drain

2. **EIP-191 Cryptographic Binding:**
   - ETH addresses bound to ICP principals via signed messages
   - Prevents front-running attacks
   - Verifies user controls the private key

3. **State Machine Payout Protection:**
   - `#processing` state prevents concurrent double-payouts
   - Atomic state transitions before async calls

4. **Hardcoded Admin Principal:**
   - Single admin principal set at compile time
   - `adminGrantAdmin()` can delegate admin role

## Related Notes
- [[backend-core-implementation]] — Detailed backend implementation patterns
- [[identity-and-access-control]] — Access control system details
- [[http-outcalls-and-ethereum-verification]] — Ethereum integration specifics
- [[token-economics-and-exchange-rates]] — Exchange rate calculation logic
- [[data-flow-and-transaction-lifecycle]] — End-to-end transaction flows
- [[security-audit-findings]] — Audit findings and mitigations