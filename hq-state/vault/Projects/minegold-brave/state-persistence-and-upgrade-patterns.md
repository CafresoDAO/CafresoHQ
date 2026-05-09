---
tags: [project-study, minegold-brave, icp, state-management]
---

# State Persistence and Upgrade Patterns

Minegold.brave implements sophisticated state persistence strategies to ensure data survives canister upgrades while maintaining backward compatibility. ICP canisters lose all memory on upgrade unless variables are marked stable—this codebase shows production patterns for managing that constraint.

## Stable vs Transient State

### Stable Variables (Persistent)

All actor-level `var` and `let` declarations are **stable by default** in Motoko—they persist across upgrades:

```motoko
// Counters — persist to ensure unique IDs aren't reused
var nextBridgeRequestId = 1;
var nextExchangeRequestId = 1;
var nextUNIDepositId = 1;

// Exchange rates — persist to maintain consistent pricing
var uniExchangeRate : Nat = 238_000_000;

// Caches — persist to avoid re-fetching on upgrade
var cachedSgldtTreasuryBalance : Nat = 0;
var cachedCkUNITreasuryBalance : Nat = 0;
var cachedMinterDepositAddress : Text = "";

// Data structures — persist all user/request state
let bridgeRequests = Map.empty<Nat, BridgeRequest>();
let sGLDTRequests = Map.empty<Nat, sGLDTRequest>();
let userProfiles = Map.empty<Principal, UserProfile>();
let uniDeposits = Map.empty<Nat, UniDepositRequest>();
let userTransactions = Map.empty<Principal, List.List<TxRecord>>();
```

**Why these are stable**: Request state, user profiles, transaction history, and ID counters MUST survive upgrades or users lose their data.

### Transient State (Ephemeral)

The `transient` keyword marks variables that **reset on every upgrade**:

```motoko
transient let ckErc20Minter : actor {
  get_minter_info : () -> async MinterInfo;
} = actor ("sv3dd-oaaaa-aaaar-qacoa-cai");
```

**Why transient**: Actor references can't be serialized to stable memory. They're reconstructed from hardcoded principal IDs on each upgrade, so there's no need to persist the reference itself.

## Upgrade Compatibility Patterns

### 1. Tombstone Variables

Variables kept solely for backward compatibility with previous versions:

```motoko
var sGLDTTreasuryBalance : Nat = 0; // kept for upgrade compatibility
var _minterInitAttempts : Nat = 0; // Kept for upgrade compatibility — not used.

// ckUNIMinter: kept for upgrade compatibility. The previous version stored an actor reference
// here as a stable variable. We restore it with the same type so the upgrade succeeds,
// then ignore its value — the minter is accessed via transient let ckUNIMinterV1/V2 instead.
var ckUNIMinter : actor {
  get_deposit_address : shared { owner : Principal; subaccount : ?Blob } -> async Text;
} = actor ("nbsys-saaaa-aaaar-qaaga-cai");
```

**Pattern**: When refactoring away a stable variable, **don't delete it**—set it to a placeholder and mark it unused. Deleting shifts all subsequent stable memory slots, causing "Memory-incompatible program upgrade" traps.

### 2. Stable Variable Ordering

Stable variables are assigned memory slots **in declaration order**. Reordering or inserting mid-block breaks upgrades:

```motoko
// ── Admin-settable stable runtime config ───────────────────────────────
// These were originally hardcoded constants embedded in the wasm. Storing
// them as vars keeps them OUT of the public wasm bytes (anyone could
// extract them via `dfx canister info` against the install hash) and
// lets admin rotate the API key or update contract addresses without a
// canister redeploy. Placed at the END of the actor's var/let declaration
// sequence so EOP appends them as new stable slots without shifting any
// existing ones (mid-block insertions cause "Memory-incompatible program
// upgrade" trap on install).
var etherscanApiKey : Text = "";
```

**Rule**: Always append new stable variables at the **end** of the declaration block. Never insert in the middle.

### 3. Optional Fields for Schema Evolution

Adding fields to existing record types requires optionality:

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
  // Exchange rate locked at deposit time (1e8 precision).
  // Optional for backward compatibility with records that predate this field.
  // Payout always uses this rate (or falls back to uniExchangeRate).
  lockedExchangeRate : ?Nat;
};
```

**Pattern**: New fields added after initial deployment must be `?Type` (optional). Existing records won't have the field—code must handle `null` gracefully.

## State Machine Persistence

Status enums persist mid-flight request state across upgrades:

```motoko
// UNI deposit status includes #processing to prevent double-payout race conditions.
// The state machine is: #pending → #confirmed → #processing → #paid.
// #failed is terminal for Ethereum receipt/calldata/binding rejection.
// Once #processing is set atomically before the async ICRC-1 call, a second concurrent
// call will see #processing and reject, preventing double-payout.
type UNIDepositStatus = {
  #pending;
  #confirmed;
  #processing;
  #paid;
  #failed;
};
```

**Critical**: If a canister upgrades while processing a deposit (status = `#processing`), the persisted status prevents re-processing after restart. The admin can manually transition stuck deposits.

## Persistent Caches

### Price Caches

```motoko
var cachedBatPrice : ?{
  price : Nat;
  timestamp : Time.Time;
} = null;

var cachedSGldtPrice : ?{
  price : Nat;
  timestamp : Time.Time;
} = null;

let PRICE_CACHE_DURATION = 300_000_000_000; // 5 minutes in nanoseconds
```

**Design**: Caches persist across upgrades to avoid immediately re-fetching expensive data. The timestamp-based TTL ensures stale data expires naturally.

### Balance Caches

```motoko
// Cached on-chain balances — updated by refreshTreasuryBalances() (an update call).
// Exposed via public shared query funcs so anonymous/unauthenticated callers can read them.
var cachedSgldtTreasuryBalance : Nat = 0;
var cachedCkUNITreasuryBalance : Nat = 0;
```

**Why cache balances**: Query calls can't make inter-canister calls. By caching balances in stable vars and exposing them via queries, anonymous users can read treasury state instantly without waiting for consensus (update calls).

### Verification Cache (Transient)

```motoko
// Each verifyEthTransaction call burns ~15 B cycles on HTTP outcalls.
// We cache the last response per requestId for VERIFY_CACHE_TTL_NS and short-circuit
// duplicate calls within the window. The frontend polls every 4-5 s, so a 3 s TTL still
// gives users near-real-time updates while killing the DoS.
let verifyCache = Map.empty<Nat, { result : Text; at : Time.Time }>();
let VERIFY_CACHE_TTL_NS = 3 * 1_000_000_000; // 3 seconds
```

**Note**: This cache uses `let` (stable) even though it's labeled conceptually transient. It persists across upgrades but has a 3-second TTL, so stale entries expire quickly anyway. Could be marked `transient let` to save memory on upgrade.

## Data Structure Persistence

### Maps and Sets

```motoko
let bridgeRequests = Map.empty<Nat, BridgeRequest>();
let sGLDTRequests = Map.empty<Nat, sGLDTRequest>();
let uniDeposits = Map.empty<Nat, UniDepositRequest>();
let userTransactions = Map.empty<Principal, List.List<TxRecord>>();
let seenTxHashes = Set.empty<Text>();
let ethAddressBinding = Map.empty<Text, Principal>();
let submissionTimestamps = Map.empty<Principal, List.List<Time.Time>>();
```

**Pattern**: All collections use stable `let` bindings. The `Map` and `Set` types from `mo:core` are upgrade-stable—their internal state serializes automatically.

### Lists for Transaction History

```motoko
let userTransactions = Map.empty<Principal, List.List<TxRecord>>();
```

**Design choice**: Immutable linked lists (`List.List`) are stable and efficient for prepend-heavy workloads (new transactions added at head). However, they don't support efficient random access or deletion—appropriate for append-only history.

## Security-Sensitive Persistence

### Admin Credentials Outside WASM

```motoko
// Admin-settable stable runtime config — keeps them OUT of the public wasm bytes
// (anyone could extract them via `dfx canister info` against the install hash) and
// lets admin rotate the API key or update contract addresses without a canister redeploy.
var etherscanApiKey : Text = "";
```

**Security pattern**: Storing API keys as stable variables (set via admin function) instead of hardcoded constants prevents extraction from the public WASM bytecode.

### Principal Bindings

```motoko
// Maps a (lowercased) ETH address to the FIRST principal that submitted a
// deposit from that address. Subsequent submissions from a different principal
// claiming the same address are rejected.
let ethAddressBinding = Map.empty<Text, Principal>();
```

**Critical for security**: This binding MUST persist—if it reset on upgrade, an attacker could re-bind victim addresses to their own principal.

## Common Upgrade Pitfalls

### ❌ Deleting Stable Variables

```motoko
// BEFORE:
var oldFeatureFlag : Bool = false;
var importantCounter : Nat = 0;

// AFTER (WRONG):
// Deleted oldFeatureFlag — this shifts importantCounter to slot 0!
var importantCounter : Nat = 0; // ← Now reads oldFeatureFlag's memory!
```

**Fix**: Leave tombstones:

```motoko
var _oldFeatureFlag : Bool = false; // unused, kept for upgrade compat
var importantCounter : Nat = 0;
```

### ❌ Reordering Declarations

```motoko
// BEFORE:
var configA : Text = "";
var configB : Nat = 0;

// AFTER (WRONG):
var configB : Nat = 0; // ← Swapped order!
var configA : Text = ""; // ← Reads from wrong slot, upgrade traps
```

**Fix**: Never reorder. Append new vars at the end.

### ❌ Changing Variable Types

```motoko
// BEFORE:
var featureFlags : [Bool] = [];

// AFTER (WRONG):
var featureFlags : Map<Text, Bool> = Map.empty(); // ← Type mismatch!
```

**Fix**: Add new variable, migrate data in post-upgrade hook, tombstone old:

```motoko
var _featureFlags_v1 : [Bool] = []; // tombstone
var featureFlagsV2 : Map<Text, Bool> = Map.empty();

// In system func postupgrade() { ... migrate data ... }
```

## Monitoring Upgrade Health

### Canister Logs

After upgrade, check canister logs for:
- Stable memory size before/after
- Variable count changes
- Any "incompatible upgrade" warnings

### Admin Diagnostics

The codebase exposes admin-only getters for critical state:

```motoko
public shared query ({ caller }) func getTreasuryICRC1Balances() : async Text {
  if (not isAdmin(caller)) {
    Runtime.trap("Unauthorized: admin only");
  };
  // Returns cached balances to verify they survived upgrade
}
```

## Related Notes

- [[canister-upgrade-mechanisms]] — Covers pre/post-upgrade hooks and migration scripts
- [[backend-core-implementation]] — Main canister logic that uses these persistence patterns
- [[icp-runtime-patterns-and-optimization]] — Broader ICP-specific patterns including cycles/timers

## References

- `src/backend/main.mo:60-99` — Stable variable declarations with compatibility comments
- `src/backend/main.mo:152-154` — Transient actor reference example
- `src/backend/main.mo:290-299` — Stable variable ordering rationale
- `src/backend/main.mo:200-214` — Optional field for backward compatibility