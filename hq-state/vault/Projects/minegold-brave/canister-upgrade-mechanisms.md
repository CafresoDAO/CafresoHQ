---
tags: [project-study, minegold-brave, icp, upgrades, devops]
---

# Canister Upgrade Mechanisms

## Overview

The minegold.defi project uses **Enhanced Orthogonal Persistence (EOP)** for canister upgrades, eliminating the need for explicit `preupgrade`/`postupgrade` lifecycle hooks. State persistence is automatic, but requires careful adherence to memory layout constraints to avoid "Memory-incompatible program upgrade" traps.

## Core Upgrade Strategy

### Enhanced Orthogonal Persistence (EOP)

Unlike traditional Motoko canisters that use `stable var` declarations, this project leverages EOP where regular `var` declarations and non-stable data structures are automatically serialized/deserialized across upgrades:

```motoko
// State automatically persists across upgrades
let bridgeRequests = Map.empty<Nat, BridgeRequest>();
let sGLDTRequests = Map.empty<Nat, sGLDTRequest>();
let userProfiles = Map.empty<Principal, UserProfile>();
let uniDeposits = Map.empty<Nat, UniDepositRequest>();
let userTransactions = Map.empty<Principal, List.List<TxRecord>>();
let seenTxHashes = Set.empty<Text>();
```

**No explicit upgrade hooks** — no `system func preupgrade()` or `system func postupgrade()` required.

### Critical Memory Layout Constraint

From `src/backend/main.mo:290-298`:

> "Placed at the END of the actor's var/let declaration sequence so EOP appends them as new stable slots without shifting any existing ones (mid-block insertions cause 'Memory-incompatible program upgrade' trap on install)."

**Rule**: New state variables MUST be added at the END of the actor's declaration block. Inserting variables in the middle shifts memory offsets and breaks upgrade compatibility.

```motoko
// ✅ CORRECT: New vars at the end
var nextBridgeRequestId = 1;
var nextExchangeRequestId = 1;
// ... existing vars ...
var etherscanApiKey : Text = "";        // Added in upgrade v2
var uniContractLower : Text = "...";     // Added in upgrade v2
var ckerc20HelperLower : Text = "...";   // Added in upgrade v2

// ❌ WRONG: Inserting in middle breaks upgrades
var nextBridgeRequestId = 1;
var newFeatureFlag = false;  // ← BREAKS UPGRADE!
var nextExchangeRequestId = 1;
```

## Backward Compatibility Patterns

The codebase includes several patterns for maintaining upgrade compatibility:

### 1. **Deprecated vars kept for compatibility**

```motoko
var sGLDTTreasuryBalance : Nat = 0; // kept for upgrade compatibility
var _minterInitAttempts : Nat = 0;  // Kept for upgrade compatibility — not used

// ckUNIMinter: kept for upgrade compatibility. The previous version stored
// an actor reference here as a stable variable.
var ckUNIMinter : actor { ... } = actor ("nbsys-saaaa-aaaar-qaaga-cai");
```

Old variables are retained even if no longer used to prevent memory layout shifts.

### 2. **Optional fields for backward compatibility**

```motoko
public type SomeRecord = {
  field1 : Text;
  field2 : ?Text;  // Optional for backward compatibility with records
                   // that predate this field
};
```

### 3. **Aliased functions for API stability**

```motoko
/// Alias kept for backward compatibility. Prefer getPayoutReadiness().
public shared query func oldFunctionName() : async Result { ... }
```

## Deployment Modes

The `launch-mainnet.sh` script supports two modes:

### Upgrade Mode (Preserves State)

```bash
./launch-mainnet.sh --upgrade
```

- Uses `dfx deploy backend --network ic --mode upgrade`
- Preserves all canister state (maps, balances, user data)
- **Use when**: deploying code changes or bug fixes to existing production canister
- **Requires**: caller must be a controller of the existing canister

### Fresh Mode (New Canister)

```bash
./launch-mainnet.sh --fresh [--rebuild]
```

- Creates NEW canister IDs
- State starts empty
- **Requires editing** `TREASURY_PRINCIPAL` and `ADMIN_PRINCIPAL` in `main.mo` before deployment
- **Use when**: initial deployment or intentional clean slate

## Treasury Principal Constraint

From `launch-mainnet.sh:7-16`:

> "main.mo hardcodes TREASURY_PRINCIPAL = 72fnc-ziaaa-aaaai-axk4q-cai. That value MUST equal Principal.fromActor(Self) on mainnet, otherwise every treasury ICRC-1 call will target the wrong account."

The canister **IS** the treasury — all payout transfers use `Principal.fromActor(Self)` as sender. If deploying fresh:

1. Deploy once to get the new canister ID
2. Update `TREASURY_PRINCIPAL` in `main.mo` to match
3. Redeploy with `--mode upgrade`

Or use `--upgrade` to maintain the existing principal.

## Local Testing of Upgrades

The `launch.sh` script includes a `--reinstall` flag for local testing:

```bash
./launch.sh --reinstall  # Force reinstall (LOSE STATE)
```

- Uses `dfx deploy --mode reinstall`
- **Destroys all state** — equivalent to fresh install
- Use for testing initial deployment scenarios locally

**Default local deploy preserves state** (upgrade mode):

```bash
./launch.sh  # Upgrades existing local canisters
```

## Upgrade Process

### 1. Pre-Deploy Checks

```bash
# Prerequisites from launch-mainnet.sh
- dfx installed and logged in
- Cycles wallet configured OR identity has cycles (dfx 0.16+)
- At least ~4 TC for fresh deploy, ~0.5 TC for upgrade
```

### 2. Build

```bash
# Optional: rebuild from source
./launch-mainnet.sh --upgrade --rebuild

# Or use pre-built wasm
./launch-mainnet.sh --upgrade
```

### 3. Deploy

```bash
step "Deploying backend to mainnet"
DEPLOY_FLAGS=(--network ic --mode upgrade)
dfx deploy backend "${DEPLOY_FLAGS[@]}"
BACKEND_ID="$(dfx canister id backend --network ic)"
```

### 4. Frontend Update

Frontend deployment happens immediately after backend:

```bash
step "Injecting canister IDs into frontend env.json"
cat > src/frontend/dist/env.json <<JSON
{
  "backend_host": "https://icp-api.io",
  "backend_canister_id": "${BACKEND_ID}",
  "project_id": "minegold-defi-ic"
}
JSON

step "Deploying frontend to mainnet"
dfx deploy frontend "${DEPLOY_FLAGS[@]}"
```

## Risks & Safeguards

### Memory Layout Incompatibility

**Risk**: Inserting variables mid-actor or reordering declarations causes "Memory-incompatible program upgrade" trap.

**Safeguard**:
- Document new vars at END of declaration block
- Code review upgrade PRs specifically for memory layout changes
- Test upgrades locally before mainnet

### State Migration Without Hooks

**Risk**: Cannot run custom logic during upgrade (no `postupgrade` hook).

**Workaround**: Use admin migration functions:

```motoko
// Migration Logic (lines 3799-3814)
public shared ({ caller }) func migration_updateBalance(_balance : Nat) : async () {
  assert caller == ADMIN_PRINCIPAL;
  sGLDTTreasuryBalance := _balance;
};
```

Admin calls migration function AFTER upgrade completes to fix state if needed.

### No Rollback Mechanism

There is **no automated rollback** in the scripts. If an upgrade fails:

1. If the canister is bricked, controllers can reinstall (loses state)
2. For bad logic (not upgrade trap), deploy a fix with `--mode upgrade`
3. **Best practice**: Test upgrades on testnet replica first

## Testing Upgrade Compatibility

### Local Upgrade Test

```bash
# 1. Deploy baseline version
./launch.sh

# 2. Make state-changing calls (create deposits, etc.)
dfx canister call backend submitUNIDeposit '...'

# 3. Make code changes (ensure new vars at END)

# 4. Upgrade
./launch.sh  # Default is upgrade mode

# 5. Verify state persisted
dfx canister call backend listMyDeposits '()'
```

### Intentional State Reset Test

```bash
./launch.sh --reinstall
# Verifies canister works from clean state
```

## Migration from Traditional Stable Vars

Previous versions may have used `stable var` — EOP is backward compatible:

```motoko
// Old pattern (still works)
stable var oldCounter : Nat = 0;

// New pattern (EOP)
var newCounter : Nat = 0;
let dataMap = Map.empty<Nat, Record>();  // Non-stable collections
```

Both persist across upgrades. EOP removes the need for manual serialization of complex types in `preupgrade`/`postupgrade`.

## Related Documentation

- [[mainnet-launch-procedures]] — full mainnet deployment walkthrough
- [[state-management]] — how state is structured in the canister
- [[build-and-deploy-process]] — build artifacts and deployment flow
- [[local-deployment-with-dfx]] — local testing procedures

## Key Takeaways

- **EOP eliminates manual upgrade hooks** but requires strict variable ordering
- **Add new state at END** of actor declaration block
- **Keep deprecated vars** to maintain memory layout compatibility
- **Test upgrades locally** before mainnet (`./launch.sh` default behavior)
- **No automated rollback** — upgrades are one-way (fix-forward only)
- **Treasury principal must match** `Principal.fromActor(Self)` for ICRC-1 calls to work