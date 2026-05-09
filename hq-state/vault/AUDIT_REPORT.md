# minegold.defi Audit Report

Date: 2026-05-02
Scope: `C:\Users\Anthony\Downloads\minegold.defi`

## Executive Summary

This audit reviewed the Motoko backend canister, React/Vite frontend wallet flow, dependency manifests, and local check results. The highest-risk issues are in the UNI deposit and sGLDT payout state machine.

Two critical findings can lead to unauthorized sGLDT payouts:

1. Failed Ethereum transactions can be converted into retryable payouts.
2. ETH address ownership is not required before deposit registration, and `autoFinalizeUNIDeposit` can claim another user's deposit.

Do not launch or fund the treasury until the critical payout paths are fixed and redeployed.

## Commands Run

- `pnpm typecheck` in `src/frontend`: passed.
- `pnpm check` in `src/frontend`: failed with 83 errors and 17 warnings, mostly formatting/import/a11y diagnostics.
- `pnpm audit --prod` at repo root: no known production dependency vulnerabilities.
- `pnpm audit` at repo root: 3 moderate dev/build-chain vulnerabilities.
- `mops check` in `src/backend`: blocked on Windows (`which` missing, toolchain not initialized, Windows unsupported).
- `wsl.exe ... mops check`: timed out after ~124 seconds.

## Critical Findings

### C-01: Failed ETH Transactions Can Still Trigger sGLDT Payout

Severity: Critical

Evidence:

- `verifyEthTransaction` marks an Ethereum receipt failure as `#failed` but keeps the claimed `uniAmount`: `src/backend/main.mo:3401-3420`.
- `verifyAndPayUNIDeposit` treats `#failed` like a payout-eligible retry state: `src/backend/main.mo:1996-2001`.
- `retryUNIDepositPayout` resets `#failed` to `#confirmed` and calls payout: `src/backend/main.mo:2290-2319`.
- `triggerSGLDTPayout` also resets `#failed` to `#confirmed` and calls payout without an Etherscan re-check: `src/backend/main.mo:2361-2381`.

Impact:

An authenticated user can submit a deposit with a positive UNI amount and a reverted Ethereum transaction hash. After `verifyEthTransaction` marks it failed, the user can call `triggerSGLDTPayout` or `retryUNIDepositPayout` and receive sGLDT from the treasury even though no valid UNI deposit occurred.

Recommended fix:

- Make failed ETH receipts terminal and unpayable.
- Do not let `verifyAndPayUNIDeposit` pay `#failed` records.
- Split payout failure from ETH verification failure, for example `#payoutFailed` versus `#rejected`.
- Require an explicit verified flag or only allow payout from `#confirmed` after `_verifyDepositCalldata` passed.
- For defense in depth, have `verifyAndPayUNIDeposit` either re-check the verified flag or run final calldata verification before transfer.

### C-02: Deposit Registration Does Not Require ETH Address Ownership Proof

Severity: Critical

Evidence:

- `_bindOrCheckEthAddress` binds an ETH address to the first caller with no signature or on-chain proof: `src/backend/main.mo:2469-2491`.
- The frontend explicitly removed the user-facing verification step and relies on automatic first-deposit binding: `src/frontend/src/App.tsx:1134-1143`.
- `autoFinalizeUNIDeposit` accepts a caller-supplied `ethAddress`, scans that address, and creates a deposit record for the caller: `src/backend/main.mo:1779-1787`, `src/backend/main.mo:1911-1922`.
- `autoFinalizeUNIDeposit` does not call `_bindOrCheckEthAddress` at all.
- `_verifyDepositCalldata` confirms `tx.from`, UNI amount, helper contract, and treasury principal, but it does not prove that the ICP caller controls `tx.from`: `src/backend/main.mo:2950-3007`.

Impact:

An attacker who sees a victim's unclaimed UNI deposit to the treasury can call `autoFinalizeUNIDeposit` with the victim's ETH address and amount. The canister records the request under the attacker's ICP principal and pays sGLDT to the attacker after calldata verification passes.

The direct `submitUNIDeposit` path is also race-prone for never-bound addresses because the first caller can bind an address without proof.

Recommended fix:

- Require `bindEthAddressEip191` or `bindEthAddressViaTx` before any deposit registration.
- Remove automatic first-use binding from `submitUNIDeposit`.
- Add the same binding enforcement to `autoFinalizeUNIDeposit`.
- In payout verification, require `ethAddressBinding[tx.from] == request.submitter`.
- Consider disabling `autoFinalizeUNIDeposit` until this is fixed.

## High Findings

### H-01: Public HTTP Outcalls Allow Cycle and API-Key DoS

Severity: High

Evidence:

- `getEthBalanceOnchain` is public, unauthenticated, and performs an Etherscan outcall: `src/backend/main.mo:3093-3104`.
- `getWalletBalances` is public and can perform two Etherscan outcalls; cache is per address and can be bypassed with new addresses: `src/backend/main.mo:3124-3161`.
- `getUniBalanceOnchain` is public, unauthenticated, and performs an Etherscan outcall: `src/backend/main.mo:3182-3195`.
- `_httpGetBounded` sends 5B cycles per HTTP request buffer: `src/backend/main.mo:3020-3045`.

Impact:

Anyone can repeatedly call these update methods with arbitrary valid-looking addresses to burn canister cycles and exhaust or rate-limit the shared Etherscan key.

Recommended fix:

- Require authenticated callers for canister-side balance outcalls.
- Add per-principal and global rate limits.
- Cache zero/error responses briefly to avoid repeated misses.
- Prefer frontend public RPC reads for anonymous users.

### H-02: Etherscan API Key Is Committed and Bundled

Severity: High

Evidence:

- Backend default value embeds the key in source/WASM: `src/backend/main.mo:298`.
- Frontend embeds the same key in browser code: `src/frontend/src/lib/eth.ts:165`.

Impact:

Anyone with the repo, deployed frontend bundle, or canister WASM can extract the key and rate-limit the service.

Recommended fix:

- Rotate the key.
- Remove committed defaults; initialize backend config post-deploy through an admin call.
- Do not ship the key in frontend code. Use public RPC fallback or a rate-limited backend proxy for key-required calls.

## Medium Findings

### M-01: Any Caller Can Read Any User's Transaction History

Severity: Medium

Evidence:

- `getUserTransactions(user)` has no auth check and returns the full transaction list for the supplied principal: `src/backend/main.mo:427-433`.

Impact:

Transaction hashes, amounts, statuses, and descriptions are exposed for any known principal.

Recommended fix:

- Remove this public method or require `caller == user || isAdmin(caller)`.
- Keep `getMyTransactions` for normal users and `adminGetUserTransactions` for admins.

### M-02: Dev/Build Dependency Advisories

Severity: Medium

`pnpm audit` found:

- `esbuild <=0.24.2` via Vite: GHSA-67mh-4wv8-2f99.
- `vite <=6.4.1`: GHSA-4w7w-66w2-5vf9.
- `postcss <8.5.10`: GHSA-qx2v-qp2m-jg93.

Production-only audit reported no known vulnerabilities.

Recommended fix:

- Upgrade Vite to a version that pulls patched esbuild, or pin/override esbuild to `>=0.25.0` if compatible.
- Upgrade PostCSS to `>=8.5.10`.
- Re-run `pnpm audit` after lockfile updates.

## Build and Quality Notes

- Frontend TypeScript typecheck passes.
- Biome currently fails with 83 errors and 17 warnings. The shown diagnostics include import ordering, Node builtin import protocol, unused variable, SVG accessibility, and dialog/progressbar accessibility issues.
- Backend check could not be completed from this Windows shell. Mops reported Windows unsupported; WSL attempt timed out.
- The git worktree was already dirty before this report, including generated canister artifacts, `node_modules`, frontend sources, backend source, and `.env`.

## Positive Controls Observed

- Duplicate transaction hashes are tracked with `seenTxHashes`.
- Successful payout path marks deposits `#processing` before awaiting the ledger transfer.
- Confirmed payout path checks minimum confirmations.
- `_verifyDepositCalldata` validates helper contract, token, amount, and treasury principal for successful receipt paths.
- Admin transfers have per-call caps.

## Priority Remediation Plan

1. Patch C-01 immediately: make ETH-failed deposits terminal and remove all payout paths from `#failed`.
2. Patch C-02 immediately: require cryptographic ETH binding before any deposit record can be created or paid.
3. Temporarily disable or admin-gate `autoFinalizeUNIDeposit`, `triggerSGLDTPayout`, and `retryUNIDepositPayout` until the state model is fixed.
4. Add regression tests for reverted tx, calldata mismatch, unbound address, bound-address mismatch, duplicate hash, and payout retry.
5. Rate-limit public HTTP outcalls and rotate/remove the exposed API key.
6. Upgrade vulnerable dev/build dependencies and clear Biome diagnostics.
