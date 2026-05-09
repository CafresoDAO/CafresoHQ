---
tags: [project-study, minegold-brave, security, authentication, authorization]
---

# Identity and Access Control

The minegold.defi platform implements a multi-layered identity and access control system that handles **Internet Computer principals**, **Ethereum addresses**, and **role-based authorization**. This architecture bridges Web3 identity standards across two blockchain ecosystems while maintaining strict security boundaries.

## Authentication Layers

### 1. Internet Identity Authentication

The platform uses **Internet Identity** (ICP's native authentication system) as the primary authentication mechanism:

```motoko
func isAuthenticatedUser(caller : Principal) : Bool {
  not caller.isAnonymous();
}
```

Every canister function receives a `caller` principal via the `shared ({ caller })` pattern. The system distinguishes between:

- **Authenticated users**: Logged in via Internet Identity, have a non-anonymous principal
- **Anonymous callers**: Unauthenticated queries, principal is `2vxsx-fae` (the anonymous principal)

**Why this matters**: Internet Identity provides cryptographically secure, privacy-preserving authentication without passwords. Users authenticate once and interact with all ICP canisters using the same identity.

### 2. Anonymous Query Access

Certain read-only operations are **deliberately exposed to anonymous callers** for transparency:

```motoko
// Cached on-chain balances — updated by refreshTreasuryBalances() (an update call).
// Exposed via public shared query funcs so anonymous/unauthenticated callers can read them.
var cachedSgldtTreasuryBalance : Nat = 0;
var cachedCkUNITreasuryBalance : Nat = 0;
```

Public query functions like `getTreasuryBalances()`, `getExchangeRate()`, and `getMinterDepositAddress()` can be called without authentication—anyone can verify treasury reserves and pricing without logging in.

## Authorization Model

### Role-Based Access Control (RBAC)

The system uses the **caffeineai-authorization** library to manage roles:

```motoko
import MixinAuthorization from "mo:caffeineai-authorization/MixinAuthorization";
import AccessControl from "mo:caffeineai-authorization/access-control";

let accessControlState = AccessControl.initState();

do {
  accessControlState.userRoles.add(ADMIN_PRINCIPAL, #admin);
  accessControlState.adminAssigned := true;
};

include MixinAuthorization(accessControlState);
```

**Three permission tiers**:

| Tier | Principal Type | Capabilities |
|------|----------------|-------------|
| **Admin** | Hardcoded `ADMIN_PRINCIPAL` + granted admins | Treasury transfers, minter initialization, admin grants, all write operations |
| **Authenticated User** | Any non-anonymous principal | Submit deposits, bind ETH addresses, view own transaction history, refine ckUNI → sGLDT |
| **Anonymous** | `2vxsx-fae` anonymous principal | Query treasury balances, exchange rates, minter address (read-only) |

### Admin Authorization Pattern

Every admin-protected function follows this pattern:

```motoko
public shared ({ caller }) func adminTransferSGLDT(to : Principal, amount : Nat) : async Text {
  if (not isAdmin(caller)) {
    return "error: Unauthorized — admin access required";
  }
  
  // Admin transfer caps prevent single-call treasury drain (FIX-1)
  if (amount > MAX_TRANSFER_AMOUNT_SGLDT) {
    return "error: Amount exceeds safety cap of 500,000 sGLDT per transaction";
  }
  
  // ... transfer logic
}
```

The `isAdmin()` check accepts:
1. The hardcoded `ADMIN_PRINCIPAL` (set to `rc62u-qypnw-bbkkp-d56wk-tnzaq-vwhi2-cqqay-q56hw-gsqbp-6wegl-jae`)
2. Any principal granted admin via `adminGrantAdmin()` (stored in `accessControlState.userRoles`)

**Security pattern**: Admin functions include **transfer caps** (see [[security-audit-findings]]) to prevent accidental or malicious treasury drainage:
- sGLDT cap: 500,000 sGLDT per transaction
- ckUNI cap: 50 ckUNI per transaction

### User-Scoped Access Control

Regular users can only access their own data:

```motoko
public query ({ caller }) func getUserTransactions(user : Principal) : async [TxRecord] {
  if (caller != user and not isAdmin(caller)) {
    Runtime.trap("Unauthorized: Can only view your own transactions");
  }
  switch (userTransactions.get(user)) {
    case (?txs) txs;
    case null [];
  };
}
```

Users can read their own transaction history, but **admins can read any principal's history** for support and auditing purposes.

## Ethereum Address Binding

The platform binds **Ethereum addresses to ICP principals** to:
1. Prevent front-running attacks (attacker can't claim another user's ETH deposits)
2. Enable cross-chain identity verification
3. Support wallet balance queries for authenticated users

### Method 1: EIP-191 Personal Sign (Primary)

The **cryptographically secure** binding method using Ethereum's `personal_sign` standard:

```motoko
public shared ({ caller }) func bindEthAddressEip191(
  ethAddress : Text,
  publicKeyHex : Text,
  signatureHex : Text
) : async Text {
  if (not isAuthenticatedUser(caller)) {
    return "error: must be logged in via Internet Identity";
  }
  
  // Reconstruct canonical message — prevents signature forgery
  let message = "minegold.defi: bind 0x" # ethLower # " -> " # caller.toText();
  
  let verifyResult = _verifyEip191Bind(message, signatureHex, publicKeyHex, ethLower);
  if (verifyResult != "ok") {
    return "error: " # verifyResult;
  }
  
  // Signature verified — overwrite any existing binding
  ethAddressBinding.add(ethLower, caller);
  "ok: 0x" # ethLower # " is cryptographically bound to " # caller.toText();
}
```

**How it works**:
1. User signs the exact message: `"minegold.defi: bind 0x<address> -> <principal>"`
2. Frontend submits signature + public key to the canister
3. Canister verifies the signature using `Sha3` (Keccak256) and `Ecdsa` libraries
4. Verified binding is stored in `ethAddressBinding` map (persistent state)

**Why this is secure**: An attacker cannot forge an EIP-191 signature for an address they don't control. The message includes the caller's principal, so signatures can't be replayed across principals.

### Method 2: On-Chain Transaction Verification (Fallback)

Workaround for **mobile Brave Wallet** where `personal_sign` is broken:

```motoko
public shared ({ caller }) func bindEthAddressViaTx(txHash : Text) : async Text {
  // 1. Fetch tx by hash via Etherscan API
  // 2. Verify tx.from == tx.to (must be self-transaction)
  // 3. Verify tx.value == 0 (no ETH should move)
  // 4. Compute expected commitment = keccak256(caller.toText())
  // 5. Verify tx.input == commitment (calldata proves principal ownership)
  // 6. Bind ethAddress -> caller
}
```

**Frontend protocol**:
1. Compute `commitment = keccak256(callerPrincipalText)`
2. Send self-transaction: `{to: ethAddress, value: 0, data: commitment}`
3. Wait for mining, submit `txHash` to canister
4. Canister verifies the on-chain transaction

**Why this works**: Sending an Ethereum transaction requires the user's private key—same security guarantee as `personal_sign`. The on-chain transaction is unforgeable and publicly verifiable.

### Cross-Device Binding Sync

Bindings are **principal-scoped**, not device-scoped:

```motoko
public shared query ({ caller }) func isCallerBoundToEth(ethAddress : Text) : async Bool {
  if (not isAuthenticatedUser(caller)) return false;
  switch (ethAddressBinding.get(ethLower)) {
    case (?p) Principal.equal(p, caller);
    case null false;
  };
}
```

If a user binds on desktop, the frontend can query `isCallerBoundToEth()` on mobile and skip the signature step—the binding is stored in the canister, not localStorage.

## Principal-Based State Management

All user-scoped state uses `Principal` as the key:

```motoko
let userTransactions = Map.empty<Principal, [TxRecord]>();
let ethAddressBinding = Map.empty<Text, Principal>();  // ETH -> Principal
let accessControlState.userRoles: Map<Principal, Role>;  // Principal -> Role
```

**Pattern**: The canister stores:
- **User transaction history**: keyed by principal
- **ETH address bindings**: maps lowercase ETH address → principal
- **Admin roles**: maps principal → `#admin` variant

This design means:
- All user data is tied to their Internet Identity
- Cross-device consistency (state lives in the canister, not browser)
- Admin actions are auditable by principal

## Security Patterns

### 1. Hardcoded Admin Principal

```motoko
let ADMIN_PRINCIPAL : Principal = Principal.fromText(
  "rc62u-qypnw-bbkkp-d56wk-tnzaq-vwhi2-cqqay-q56hw-gsqbp-6wegl-jae"
);
```

**Why hardcoded?** Prevents privilege escalation attacks. Even if the `accessControlState` is compromised, the hardcoded principal retains admin access and can recover the system.

### 2. Admin Transfer Caps (Post-Audit Fix)

See [[security-audit-findings]] for context—these caps were added to prevent single-call treasury drainage:

```motoko
let MAX_TRANSFER_AMOUNT_SGLDT : Nat = 50_000_000_000_000;  // 500,000 sGLDT
let MAX_TRANSFER_AMOUNT_CKUNI : Nat = 50_000_000_000_000_000_000;  // 50 ckUNI
```

### 3. ETH Address Normalization

All ETH addresses are normalized before storage:
- Strip `0x` prefix
- Convert to lowercase
- Validate length (42 characters including `0x`)

Prevents binding collisions from case variations (`0xABC...` vs `0xabc...`).

### 4. Authenticated vs. Anonymous Context

Functions explicitly check authentication where needed:

```motoko
public shared ({ caller }) func submitUNIDeposit(...) : async Nat {
  if (not isAuthenticatedUser(caller)) {
    Runtime.trap("error: must be logged in via Internet Identity");
  }
  // ... deposit logic
}
```

**Pattern**: State-modifying operations require authentication; public queries allow anonymous access for transparency.

## Diagnostic Tools

The system includes admin diagnostics:

```motoko
public query func checkMyAdminStatus(caller : Principal) : async {
  caller : Text;
  isHardcodedAdmin : Bool;
  hasAdminRole : Bool;
  isAdmin : Bool;
}
```

Helps debug "not admin" errors from the UI by showing all permission checks.

## Related Patterns

- [[api-and-endpoints]] — How caller authentication affects API access
- [[security-audit-findings]] — Transfer caps and binding race conditions
- [[data-flow-and-transaction-lifecycle]] — How principals flow through deposit/refine operations
- [[frontend-architecture-and-ui]] — Internet Identity integration in React

## Key Takeaways

- **Three-tier access model**: admin, authenticated user, anonymous query
- **Cross-chain identity**: ETH addresses cryptographically bound to ICP principals
- **Dual binding methods**: EIP-191 signatures (primary) + on-chain tx verification (fallback)
- **Principal-scoped state**: All user data keyed by Internet Identity principal
- **Security hardening**: Hardcoded admin, transfer caps, address normalization