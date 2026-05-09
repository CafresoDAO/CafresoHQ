---
tags: [project-study, minegold-brave]
---
# Patterns & Conventions

The Minegold.brave codebase follows consistent patterns across Motoko backend code, deployment scripts, and configuration. This note captures recurring conventions, architectural decisions, and code style patterns.

## Motoko Backend Patterns

### Import Organization

Imports are grouped by source:

```motoko
// Core library imports (mo:core/*)
import Array "mo:core/Array";
import Time "mo:core/Time";
import Map "mo:core/Map";

// External dependencies
import MixinAuthorization "mo:caffeineai-authorization/MixinAuthorization";
import Ecdsa "mo:ecdsa";

// IC system canister
import IC "ic:aaaaa-aa";
```

All imports use the `"mo:core/*"` pattern for standard library modules (not the older `mo:base` convention).

### Constants and Configuration

Constants follow an **ALL_CAPS** naming convention:

```motoko
let BB_TOKEN_DECIMALS = 8;
let SGLDT_DECIMALS = 8;
let PRICE_CACHE_DURATION = 300_000_000_000; // 5 minutes in nanoseconds
let ADMIN_PRINCIPAL : Principal = Principal.fromText("rc62u-...");
```

**Placement convention**: Runtime-configurable vars are declared at the END of the actor's variable declaration block to avoid upgrade incompatibilities (EOP — End of Program — ensures new variables append as stable slots rather than shifting existing ones):

```motoko
// Placed at the END of the actor's var/let declaration
// sequence so EOP appends them as new stable slots without shifting any
// existing ones (mid-block insertions cause "Memory-incompatible program
// upgrade" trap on install).
var etherscanApiKey : Text = "";
var uniContractLower : Text = "1f9840a85d5af5bf1d1762f925bdaddc4201f984";
```

### State Management

**Persistent state** uses mutable variables (`var`) for scalars and immutable bindings (`let`) for collections:

```motoko
// Counters: var
var nextBridgeRequestId = 1;
var nextExchangeRequestId = 1;

// Collections: let (the Map/Set/List is mutable, the binding is not)
let bridgeRequests = Map.empty<Nat, BridgeRequest>();
let userProfiles = Map.empty<Principal, UserProfile>();
let seenTxHashes = Set.empty<Text>();
```

This pattern leverages Motoko's stable variable semantics — both `var` and `let` declarations at actor scope are stable across upgrades.

### Type Definitions

**Variant types** (sum types) are used for status enums:

```motoko
type BridgeStatus = {
  #pending;
  #approved;
  #rejected;
};

type UNIDepositStatus = {
  #pending;
  #confirmed;
  #processing;
  #paid;
  #failed;
};
```

**Record types** use PascalCase for type names, camelCase for field names:

```motoko
type BridgeRequest = {
  id : Nat;
  submitter : Principal;
  ethAddress : Text;
  batAmount : Nat;
  status : BridgeStatus;
  timestamp : Time.Time;
};
```

**Public types** are explicitly marked for export:

```motoko
public type TxType = {
  #Bridge;
  #Mint;
  #Refine;
  #Transfer;
};
```

### Error Handling Patterns

**Result types** using variants for functions that can fail:

```motoko
func _fetchMinterDepositAddress(_owner : Principal) : async { #ok : Text; #err : Text } {
  try {
    let info = await ckErc20Minter.get_minter_info();
    switch (info.erc20_helper_contract_address) {
      case (?addr) {
        if (addr.size() > 0) #ok(addr) 
        else #err("ckERC-20 minter returned an empty helper contract address.");
      };
      case null {
        #err("ckERC-20 minter has no ERC-20 helper contract address configured yet.");
      };
    };
  } catch (e) {
    #err("ckERC-20 minter (sv3dd-oaaaa-aaaar-qacoa-cai) returned an error: " # e.message());
  };
};
```

**Pattern matching** for exhaustive error handling:

```motoko
switch (result) {
  case (#Ok(blockIndex)) {
    ignore await refreshTreasuryBalances();
    "ok: Transfer successful. Block index: " # blockIndex.toText();
  };
  case (#Err(#InsufficientFunds { balance })) {
    "error: Insufficient sGLDT in treasury. Balance: " # balance.toText();
  };
  case (#Err(#BadFee { expected_fee })) {
    "error: BadFee — ledger expected " # expected_fee.toText();
  };
  // ... all other ICRC1TransferError variants
};
```

**Text result convention**: Public API functions return `Text` with prefixes `"ok:"` or `"error:"` so frontends can parse status without needing to handle traps:

```motoko
public shared ({ caller }) func adminTransferSGLDT(to : Principal, amount : Nat) : async Text {
  if (not isAdmin(caller)) {
    return "error: Unauthorized — admin only";
  }
  // ... validation
  switch (result) {
    case (#Ok(blockIndex)) {
      "ok: Transfer successful. Block index: " # blockIndex.toText();
    };
    case (#Err(_)) { "error: ..." };
  };
}
```

**Trap for auth failures in query calls**:

```motoko
public query ({ caller }) func getUserTransactions(user : Principal) : async [TxRecord] {
  if (caller != user and not isAdmin(caller)) {
    Runtime.trap("Unauthorized: Can only view your own transactions");
  };
  // ...
};
```

### Authorization Patterns

**Dual admin check**: hardcoded principal OR role-based:

```motoko
func isAdmin(caller : Principal) : Bool {
  if (caller == ADMIN_PRINCIPAL) return true;
  switch (accessControlState.userRoles.get(caller)) {
    case (? #admin) true;
    case (_) false;
  };
};
```

**Caller context extraction**:

```motoko
public shared ({ caller }) func adminGrantAdmin(newAdmin : Principal) : async Text {
  if (not isAdmin(caller)) {
    return "error: Unauthorized — only existing admins may grant admin rights";
  };
  // ...
}
```

**Anonymous user check**:

```motoko
func isAuthenticatedUser(caller : Principal) : Bool {
  not caller.isAnonymous();
};
```

### Security Patterns

**Per-principal rate limiting**:

```motoko
let submissionTimestamps = Map.empty<Principal, List.List<Time.Time>>();
let MAX_SUBMISSIONS_PER_HOUR : Nat = 5;
let SUBMISSION_WINDOW_NS = 60 * 60 * 1_000_000_000;
```

**ETH address binding** (first-principal-wins to prevent front-running):

```motoko
// Maps a (lowercased) ETH address to the FIRST principal that submitted a
// deposit from that address. Subsequent submissions from a different
// principal claiming the same address are rejected.
let ethAddressBinding = Map.empty<Text, Principal>();
```

**Cache-based DoS prevention**:

```motoko
// Each verifyEthTransaction call burns ~15 B cycles on HTTP outcalls.
// Cache the last response per requestId for VERIFY_CACHE_TTL_NS to
// short-circuit duplicate calls within the window.
let verifyCache = Map.empty<Nat, { result : Text; at : Time.Time }>();
let VERIFY_CACHE_TTL_NS = 3 * 1_000_000_000; // 3 seconds
```

**Transfer caps** to prevent treasury drainage:

```motoko
let MAX_TRANSFER_AMOUNT_SGLDT : Nat = 50_000_000_000_000;
let MAX_TRANSFER_AMOUNT_CKUNI : Nat = 50_000_000_000_000_000_000;

if (amount > MAX_TRANSFER_AMOUNT_SGLDT) {
  return "error: Transfer amount exceeds the per-tx cap";
}
```

### Actor References and Canister Interaction

**Hardcoded actor references** for mainnet canisters:

```motoko
let sgldtLedger : actor {
  icrc1_balance_of : (ICRC1Account) -> async Nat;
  icrc1_transfer : (ICRC1TransferArgs) -> async ICRC1TransferResult;
  icrc1_fee : () -> async Nat;
} = actor ("i2s4q-syaaa-aaaan-qz4sq-cai");
```

**Transient actor references** (not stable, re-initialized on upgrade):

```motoko
transient let ckErc20Minter : actor {
  get_minter_info : () -> async MinterInfo;
} = actor ("sv3dd-oaaaa-aaaar-qacoa-cai");
```

**Partial type definitions** (Candid subtyping — only decode fields you need):

```motoko
type MinterInfo = {
  erc20_helper_contract_address : ?Text;
};
// The actual minter response has more fields; we ignore them
```

### Utility Modules

Internal modules for shared logic:

```motoko
module Utils {
  public func compareBridgeRequestsByTimestamp(a : BridgeRequest, b : BridgeRequest) : Order.Order {
    Nat.compare(a.timestamp.toNat(), b.timestamp.toNat());
  };
};
```

### Transaction ID Generation

```motoko
var txCounter : Nat = 0;

func _nextTxId() : Text {
  txCounter += 1;
  Time.now().toText() # "-" # txCounter.toText();
};
```

Combines timestamp + counter to ensure uniqueness and sortability.

## Shell Script Patterns

### Header Comments

All deployment scripts use ASCII art banner comments:

```bash
#!/usr/bin/env bash
# ============================================================================
# minegold.defi — LOCAL LAUNCH SCRIPT
# ============================================================================
# One-command local deploy using the canonical DFINITY SDK (dfx).
# ...
# ============================================================================
```

### Strict Error Handling

```bash
set -euo pipefail
```

- `-e`: exit on any command failure
- `-u`: error on undefined variables
- `-o pipefail`: fail if any command in a pipe fails

### Script Directory Navigation

```bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
```

Ensures the script runs from its own directory regardless of where it's invoked from.

### Flag Parsing Pattern

```bash
CLEAN=0
REINSTALL=0
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --clean)     CLEAN=1 ;;
    --reinstall) REINSTALL=1 ;;
    --rebuild)   REBUILD=1 ;;
    -h|--help)
      sed -n '2,14p' "$0"; exit 0 ;;  # extract header comment as help
    *)
      echo "Unknown flag: $arg"; exit 1 ;;
  esac
done
```

### Colored Output Helpers

```bash
b() { printf '\033[1m%s\033[0m\n' "$*"; }    # bold
g() { printf '\033[32m%s\033[0m\n' "$*"; }  # green
y() { printf '\033[33m%s\033[0m\n' "$*"; }  # yellow
r() { printf '\033[31m%s\033[0m\n' "$*" >&2; }  # red to stderr
step() { echo; b "▸ $*"; }
```

Usage:
```bash
step "Checking prerequisites"
g "  ✓ backend.wasm (123.4 KiB)"
r "Missing: dfx"
```

### Prerequisite Checks

```bash
missing=()
command -v dfx  >/dev/null 2>&1 || missing+=("dfx")
command -v node >/dev/null 2>&1 || missing+=("node")
if (( ${#missing[@]} )); then
  r "Missing: ${missing[*]}"
  exit 1
fi
```

### File Existence Validation

```bash
[[ -f src/backend/dist/backend.wasm ]] || { 
  r "Missing src/backend/dist/backend.wasm — run: ./launch.sh --rebuild"; 
  exit 1; 
}
```

### Conditional Deployment Flags

```bash
DEPLOY_FLAGS=()
(( REINSTALL )) && DEPLOY_FLAGS+=(--mode reinstall -y)
dfx deploy "${DEPLOY_FLAGS[@]}" backend
```

### Error Suppression for Optional Commands

```bash
set +e  # temporarily disable exit-on-error
dfx canister call backend assignCallerUserRole "(...)" >/dev/null 2>&1
RC=$?
set -e  # re-enable
if (( RC == 0 )); then
  g "  ✓ success"
else
  y "  ⚠ failed — non-critical"
fi
```

## Configuration Patterns

### Build Verification Commands

From [[project-configuration]], `dfx.json` uses inline `bash -c` build checks:

```json
"build": "bash -c 'test -f src/backend/dist/backend.wasm && test -f src/backend/dist/backend.did || { echo \"[dfx.json] Pre-built backend artifacts missing.\"; echo \"         Run:  cd src/backend && mops install && mops build\"; exit 1; }'"
```

This pattern validates pre-built artifacts and provides actionable error messages.

### Mops Configuration

From `mops.toml`:

```toml
[canisters.backend]
main = "src/backend/main.mo"

[moc]
args = [
  "--default-persistent-actors",
  "--actor-idl=src/backend/system-idl",
  "-E=M0236,M0235,M0223,M0237",  # suppress specific warnings
  "-A=M0198"                     # promote M0198 to error
]
```

Explicit compiler flags are documented inline.

## Naming Conventions Summary

| Element | Convention | Example |
|---------|------------|----------|
| Type names | PascalCase | `BridgeRequest`, `TxType` |
| Function names | camelCase | `isAdmin`, `getUserTransactions` |
| Public functions | `public shared` or `public query` | `public shared ({ caller }) func adminTransferSGLDT` |
| Constants | ALL_CAPS | `MAX_TRANSFER_AMOUNT_SGLDT` |
| State variables | camelCase | `nextBridgeRequestId`, `cachedSgldtTreasuryBalance` |
| Private helpers | `_prefixedCamelCase` | `_nextTxId()`, `_fetchMinterDepositAddress()` |
| Variant tags | `#lowercase` or `#PascalCase` | `#pending`, `#Bridge` |
| Canister actors | camelCase + "Ledger" / "Minter" | `sgldtLedger`, `ckErc20Minter` |

## Documentation Patterns

**Inline comments for "why" and security context**:

```motoko
// FIX-1: Admin transfer caps — prevent a single call from draining the entire treasury.
let MAX_TRANSFER_AMOUNT_SGLDT : Nat = 50_000_000_000_000;

// ── Front-running defense: ethAddress ↔ ICP principal binding ─────────
// Maps a (lowercased) ETH address to the FIRST principal that submitted a
// deposit from that address. Subsequent submissions from a different
// principal claiming the same address are rejected.
```

**Triple-slash doc comments** for public APIs (not shown in excerpts, but standard in Motoko).

**Code comments include decimal conversion hints**:

```motoko
let PRICE_CACHE_DURATION = 300_000_000_000; // 5 minutes in nanoseconds
let uniExchangeRate : Nat = 238_000_000; // 1e8 precision (2.38 sGLDT per UNI)
```

## Linked Notes

- [[key-components]] — canister structure
- [[state-management]] — how persistent state is organized
- [[security-audit-findings]] — security issues that drove some of these patterns
- [[build-and-deploy-process]] — how these patterns manifest in deployment
- [[api-and-endpoints]] — public API surface shaped by these conventions