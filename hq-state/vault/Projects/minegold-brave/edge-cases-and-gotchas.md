---
tags: [project-study, minegold-brave, security, gotchas]
---

# Edge Cases & Gotchas

Critical traps, workarounds, and known issues in the minegold.defi project. These range from security vulnerabilities to platform-specific deployment quirks.

## Critical Security Edge Cases

### C-01: Failed ETH Transactions Can Trigger sGLDT Payout

**Severity:** Critical (fund-loss risk)

**The Problem:**
A reverted Ethereum transaction can still result in sGLDT being minted to the attacker.

**How It Happens:**
```motoko
// src/backend/main.mo:3401-3420
// verifyEthTransaction marks failed receipts as #failed but keeps the claimed uniAmount
if (receipt.status == "0") {
  return #failed; // ⚠️ Still has uniAmount in the record!
}

// src/backend/main.mo:1996-2001
// verifyAndPayUNIDeposit treats #failed like a retryable state
case (#failed) { /* proceeds to payout */ }

// src/backend/main.mo:2290-2319
// retryUNIDepositPayout resets #failed → #confirmed without re-checking Etherscan
status := #confirmed;
await triggerSGLDTPayout(depositId);
```

**Attack Vector:**
1. Attacker submits a deposit with a positive UNI amount
2. Provides a hash of a **reverted** transaction (or creates one deliberately)
3. `verifyEthTransaction` marks it `#failed`
4. Attacker calls `triggerSGLDTPayout` or `retryUNIDepositPayout`
5. Receives sGLDT even though no valid UNI deposit occurred

**Fix Required:**
- Make `#failed` terminal and unpayable
- Split `#payoutFailed` from `#ethVerificationFailed`
- Only allow payout from `#confirmed` after successful `_verifyDepositCalldata`

See [[security-audit-findings]] for full audit report.

### C-02: No ETH Address Ownership Proof Required

**Severity:** Critical (deposit theft)

**The Problem:**
Anyone can claim another user's Ethereum deposit by calling `autoFinalizeUNIDeposit` with the victim's address.

**Code Path:**
```motoko
// src/backend/main.mo:1779-1787, 1911-1922
// autoFinalizeUNIDeposit accepts caller-supplied ethAddress
public shared({caller}) func autoFinalizeUNIDeposit(
  ethAddress: Text,
  uniAmount: Nat
) : async Text {
  // ⚠️ Does NOT call _bindOrCheckEthAddress!
  // Creates deposit record under caller's principal
  // Pays sGLDT to caller after verification passes
}

// src/backend/main.mo:2469-2491
// _bindOrCheckEthAddress binds on first-use with NO cryptographic proof
case null {
  ethAddressBinding.put(ethAddr, caller); // ⚠️ No signature required!
}
```

**Attack Vector:**
1. Victim sends UNI to treasury from address `0xVICTIM`
2. Attacker sees the on-chain transaction
3. Attacker calls `autoFinalizeUNIDeposit("0xVICTIM", amount)`
4. Canister creates deposit under **attacker's** ICP principal
5. After verification, sGLDT is paid to **attacker**

**Why the Frontend Removed Verification:**
```typescript
// src/frontend/src/App.tsx:1134-1143
// Comment reveals the verification step was "explicitly removed"
// and relies on automatic first-deposit binding
```

**Fix Required:**
- Require `bindEthAddressEip191` or `bindEthAddressViaTx` before any deposit
- Remove automatic first-use binding from `submitUNIDeposit`
- Add binding enforcement to `autoFinalizeUNIDeposit`
- Verify `ethAddressBinding[tx.from] == request.submitter` in payout logic

---

## State Machine Gotchas

### Payout Retry Confusion

The deposit state machine has overlapping retry paths that can conflict:

```motoko
// Three functions can trigger payout:
// 1. verifyAndPayUNIDeposit (normal path)
// 2. retryUNIDepositPayout (manual admin retry)
// 3. triggerSGLDTPayout (manual user retry)

// Problem: All three reset failed states without re-verification
status := #confirmed; // ⚠️ No Etherscan re-check!
```

**Edge Case:** If the Etherscan API was temporarily down during initial verification, a legitimate `#failed` status might be retried — but the current code would also allow retry of a genuinely rejected transaction.

### ICRC-1 Transfer "Never Traps" Contract

Multiple functions have explicit `NEVER traps` contracts:

```motoko
// src/backend/main.mo:1959, 2263
/// IMPORTANT: This function NEVER traps. All errors are returned as descriptive Text.
public shared({caller}) func verifyAndPayUNIDeposit(...) : async Text
```

**Why This Matters:**
- All error paths must return `Text` instead of `throw`ing
- Careful testing needed to ensure no `Runtime.trap()` calls in these paths
- The ICRC-1 ledger transfer can still fail — must be caught with `try/catch`

**Observed Error Handling:**
```motoko
// src/backend/main.mo:2134, 2155, 2161, 2167
case (#Err(#InsufficientFunds { balance })) {
  ignore debug_show(("sGLDT transfer failed: InsufficientFunds", balance));
  status := #payoutFailed;
  return #err(#payoutFailed("Insufficient treasury balance"));
}
```

---

## Deployment & Toolchain Gotchas

### Windows Toolchain Incompatibility

**Problem:** Mops (Motoko package manager) does not support Windows.

```bash
# From audit report:
# mops check in src/backend: blocked on Windows (which missing, toolchain not initialized, Windows unsupported).
# wsl.exe ... mops check: timed out after ~124 seconds.
```

**Workaround:**
- Use prebuilt `src/backend/dist/backend.wasm` on Windows
- For development, use WSL2 or Linux/macOS
- `launch.sh --rebuild` will fail on native Windows

### Admin Principal Hardcoded Mismatch

**Problem:** Local deployments can't grant admin role to the deployer.

```bash
# src/backend/main.mo:55
# IMPORTANT: Principal.fromActor(Self) == c626g-iyaaa-aaaau-agpoa-cai.
# ⚠️ This is hardcoded and won't match your local dfx identity!

# launch.sh:136-142 tries to assign admin role, but warns:
if (( RC == 0 )); then
  g "✓ ${MY_PRINCIPAL} now has admin role on the backend canister"
else
  y "⚠ assignCallerUserRole failed — main.mo hardcodes a specific ADMIN_PRINCIPAL."
  y "   Local admin features won't be reachable unless you edit"
  y "   src/backend/main.mo → ADMIN_PRINCIPAL and rebuild (--rebuild)."
fi
```

**Fix:**
- Edit `ADMIN_PRINCIPAL` in `src/backend/main.mo` to your `dfx identity get-principal`
- Rebuild with `./launch.sh --rebuild`
- Or use `dfx canister call backend assignCallerUserRole` after deploy

### Two Different Deployment Tools

**Gotcha:** Project has **two** deployment scripts using different CLIs:

```bash
# launch.sh uses dfx (standard DFINITY SDK)
dfx deploy backend
dfx canister id backend

# deploy.sh uses icp-cli (different tool)
icp network start -d
icp canister create --environment local frontend
icp deploy --environment local frontend backend
```

**Implication:** Choose one and stick with it. Don't mix — canister IDs and network state won't be compatible.

---

## Wallet Integration Workarounds

### Mobile Brave `personal_sign` Returns Empty Array

**Problem:** Mobile Brave Wallet has a broken `personal_sign` implementation that returns `[]` instead of a signature.

**Workaround:** Use a self-transaction with calldata commitment instead.

```motoko
// src/backend/main.mo:1486-1510
/// Cryptographically bind an ETH address to the caller's ICP principal
/// by verifying an on-chain self-transaction whose calldata commits to
/// the caller's principal. This is the WORKAROUND for mobile Brave
/// Wallet's broken in-tab `personal_sign` (which returns `[]`).
///
/// Why this works: sending an Ethereum transaction requires the user's
/// private key — same security guarantee as `personal_sign`. The on-chain
/// transaction is unforgeable, publicly verifiable, and `sendTransaction`
/// works correctly on every wallet (including mobile Brave) because it's
/// already used for the UNI deposit flow.
```

**Protocol:**
1. Compute commitment = `keccak256(callerPrincipalText)` → 32 bytes
2. Send self-transaction:
   - `to`: same as `from` (self-tx)
   - `value`: 0
   - `data`: `"0x" + commitment_hex`
3. Wait for mining, capture `txHash`
4. Submit to `bindEthAddressViaTx(txHash)`

**Verification:**
- Verify `tx.from == tx.to` (proves key ownership)
- Verify `tx.value == 0` (no ETH moves)
- Verify `tx.input == keccak256(caller.toText())`

### Multiple Wallet Provider Preference

```typescript
// src/frontend/src/App.tsx:290-294
// If multiple providers are injected (MetaMask + Brave), prefer Brave since
// it's the user's active wallet on this dApp.
if (eth.providers && eth.providers.length > 0) {
  const brave = eth.providers.find((p) => p.isBraveWallet === true);
  if (brave) return brave;
}
```

**Why:** Users with multiple browser wallets need consistent provider selection to avoid confusion.

### WalletConnect Preferred for Mobile

```typescript
// src/frontend/src/App.tsx:278-282
// 1. Active WalletConnect session — preferred for any mobile flow, since
//    requests are forwarded to the real wallet app instead of the buggy
//    in-tab provider.
const wc = getActiveWalletConnectProvider();
if (wc) return wc as unknown as InjectedProvider;
```

---

## HTTP Outcall Gotchas

### Must Use Unreplicated Mode to Avoid Consensus Failures

**Problem:** Etherscan balance queries return slightly different values to different replicas when the chain tip advances between requests (millisecond-level race).

```motoko
// src/backend/main.mo:3030-3037
// IMPORTANT: must be unreplicated. Etherscan returns slightly different
// balances to different replicas when the chain tip advances between
// their requests (millisecond-level race). Replicated outcalls then
// fail with "No consensus could be reached". Unreplicated mode routes
// the call through a SINGLE replica whose response is signed — no
// cross-replica agreement needed. This is the canonical pattern for
// oracle-style outcalls on IC.
is_replicated = ?false;
```

**Why This Was Added:**
```motoko
// src/backend/main.mo:3051-3052
// (debugEtherscanRaw helper removed after outcall consensus issue diagnosed
//  and fixed via is_replicated=false — 2026-04-23.)
```

**Cost Impact:**
- Unreplicated outcalls on a 13-node app subnet: **~1/13 the cost** of replicated
- With `max_response_bytes ≤ 32 KB`, real cost is a few hundred million cycles
- Code provides 5B cycles as buffer; unused cycles are refunded

### Public HTTP Outcalls Enable Cycle DoS

**Problem:** Unauthenticated public functions perform expensive HTTP outcalls.

```motoko
// src/backend/main.mo:3093-3104, 3124-3161, 3182-3195
public func getEthBalanceOnchain(ethAddress: Text) : async Nat {
  // ⚠️ Public, unauthenticated, performs Etherscan outcall
  // 5B cycles per call!
}
```

**Attack Vector:**
- Attacker calls these methods repeatedly with arbitrary addresses
- Burns canister cycles
- Exhausts or rate-limits the shared Etherscan API key

**Mitigation Needed:**
- Require authenticated callers
- Add per-principal and global rate limits
- Cache zero/error responses briefly
- Prefer frontend public RPC reads for anonymous users

See [[security-audit-findings#H-01]] for full finding.

### Etherscan API Key Exposure

**Problem:** API key is hardcoded in both backend WASM and frontend bundle.

```motoko
// src/backend/main.mo:298
// ⚠️ Embedded in source/WASM — anyone can extract it
let ETHERSCAN_KEY = "<key>"; 
```

```typescript
// src/frontend/src/lib/eth.ts:165
// ⚠️ Shipped in browser code — visible to all users
const ETHERSCAN_API_KEY = "<key>";
```

**Impact:** Anyone with the repo, deployed frontend bundle, or canister WASM can extract the key and rate-limit the service.

---

## Frontend Gotchas

### Polyfill Import Order Matters

**Problem:** Polyfills **must** be imported before anything else or Buffer/process will be undefined.

```typescript
// src/frontend/src/main.tsx:1
// IMPORTANT: polyfills MUST be imported before anything else so Buffer/process
// are defined for dependencies that expect them in the browser.
import './polyfills';
```

**Why:** Some dependencies (like crypto libraries or ethers.js) expect Node.js globals (`Buffer`, `process.env`) to exist in the browser environment.

### Zero Balance Display Edge Case

```typescript
// src/frontend/src/App.tsx:1366
// Note: check for !== undefined (not > BigInt(0)) so a genuine zero balance displays correctly
if (balance !== undefined) {
  // Display balance, even if 0
}
```

**Gotcha:** Using `if (balance)` would hide legitimate zero balances. Always check `!== undefined` for BigInt values.

### Remote Debugging Improvements

```typescript
// src/frontend/src/App.tsx:675
// which cuts remote-debugging in half (we no longer have to ask "what was
// the error message?" — it's visible in the UI)
```

**Implication:** Error messages are intentionally shown in the UI for mobile debugging, where dev tools aren't accessible.

---

## Privacy Gotcha

### Any Caller Can Read Any User's Transaction History

**Problem:** No authorization check on `getUserTransactions(user)`.

```motoko
// src/backend/main.mo:427-433
public query func getUserTransactions(user: Principal) : async [Transaction] {
  // ⚠️ No auth check! Returns full tx list for any principal
  switch (userTransactions.get(user)) {
    case (?txs) { txs };
    case null { [] };
  };
}
```

**Impact:** Transaction hashes, amounts, statuses, and descriptions are exposed for any known principal.

**Recommended Fix:**
- Remove this public method
- Keep `getMyTransactions` for normal users
- Add `adminGetUserTransactions` for admin-only access

See [[security-audit-findings#M-01]].

---

## Keccak-256 Padding Gotcha

**Problem:** Must use the original Keccak padding, not SHA-3 standard.

```motoko
// src/backend/main.mo:2613
/// IMPORTANT: this is Keccak-256 with the original padding (0x01 delim),
/// NOT SHA3-256 (which uses 0x06). Ethereum uses the original Keccak.
```

**Why:** Ethereum's `keccak256` predates the final SHA-3 standard and uses different padding. Using SHA3-256 will produce different hashes and break signature verification.

---

## Build Quality Notes

**From Audit:**
- Frontend TypeScript typecheck: ✅ passes
- Biome linting: ❌ 83 errors + 17 warnings (import ordering, Node builtin protocol, unused vars, SVG/dialog accessibility)
- Backend Motoko check: ❌ could not complete on Windows
- Production dependencies: ✅ no known vulnerabilities
- Dev dependencies: ⚠️ 3 moderate vulnerabilities (esbuild, vite, postcss)

**Workaround:** Use prebuilt artifacts for Windows development; run quality checks in WSL2 or CI.

---

## Testing Gaps

**Missing Regression Tests:**
The audit recommends adding tests for:
- Reverted tx with claimed payout
- Calldata mismatch
- Unbound ETH address
- Bound-address mismatch (attacker != address owner)
- Duplicate transaction hash
- Payout retry after various failure states

**Current Coverage:**
- Duplicate transaction hash tracking exists (`seenTxHashes`)
- Successful payout marks `#processing` before ledger transfer
- Minimum confirmations checked on confirmed path
- Calldata validation exists but not enforced on all payout paths

---

## Cross-References

- Full security audit: [[security-audit-findings]]
- Deposit flow details: [[data-flow-and-transaction-lifecycle]]
- State management: [[state-management]]
- API endpoints: [[api-and-endpoints]]
- Build process: [[build-and-deploy-process]]
- Local deployment: [[local-deployment-with-dfx]]
