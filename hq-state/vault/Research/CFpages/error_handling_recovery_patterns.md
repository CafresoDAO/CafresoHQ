---
tags: [research, dapp-ux, error-handling, resilience]
---

# Error Handling & Recovery Patterns in DApps

## Error Categories

DApp transactions fail across multiple layers, each requiring different UX treatment:

### 1. **Client-Side Validation Errors**
- Insufficient balance (user has fewer tokens than they're trying to spend)
- Invalid recipient/destination format
- Missing required fields (memo, treasury principal, etc.)
- Amount exceeds limits (e.g., transaction ceiling)

**Current Cafreso approach**: Form validation shows inline errors immediately—"Recipient not found" or "Amount exceeds balance"—before submission. This is the right place to fail.

**Pitfall**: Showing balance *after* the error message forces users to scroll up to verify. Better: inline balance display next to the input field.

### 2. **Wallet Rejection**
- User cancels the confirmation in their wallet (Internet Identity, Plug, etc.)
- Wallet is locked or requires re-authentication
- Wallet version mismatch or permission conflicts

**Current behavior**: Modal closes, no clear signal whether the user cancelled or the wallet failed. Users wondering "Did I click confirm?" is common.

**Better UX**: Show a transient toast: "Wallet confirmation cancelled. Try again." This confirms the user saw the prompt and chose to cancel.

### 3. **Network & Blockchain Errors**
- Transaction submission times out (user is waiting, nothing happens)
- Network congestion causes the transaction to fail mid-broadcast
- Insufficient network gas/fees (for EVM chains; less relevant on ICP but still possible for cross-chain bridges)
- Smart contract revert (Treasury principal locked, transfer not authorized, etc.)

**Current handling**: "Recording failed" in checkout, but the reason is opaque. Users don't know if it's their fault, a temporary glitch, or a permanent blocker.

### 4. **Post-Submission Ambiguity**
The hardest case: transaction was *submitted* but the app lost the result (page refresh, connection drop, browser close).

**Current pattern**: No transaction recovery shown. If the user refreshes during a transfer, they can't verify whether it went through.

## Best Practices from Industry

### Retry & Fallback Logic
- **Transient errors** (timeout, network blip) → Automatic retry with exponential backoff (1s, 2s, 4s)
- **User errors** (insufficient balance, invalid input) → Explain the problem and let user fix it
- **Service errors** (contract revert, authorization failure) → Show the revert reason if available; direct to support if not

### Proof of Submission
Even if the dApp can't immediately confirm success, capture and display:
- **Transaction hash** (if on-chain submission succeeded)
- **Timestamp** of the attempt
- **Explorer link** (ICP Dashboard, ICRC-1 ledger viewer) so users can manually check

This turns "Waiting…" into "Waiting… [View on explorer]" — the user regains control.

### Clear State Messaging
| State | Message | User Action |
|-------|---------|----------|
| Idle | Ready | Click confirm |
| Submitted | "Waiting for blockchain confirmation…" | Wait or check explorer |
| Timeout | "Transfer taking longer than usual. [Check explorer] [Retry]" | User can verify manually |
| Rejected | "Wallet confirmation cancelled" | Retry |
| Failed | "Insufficient balance (needed X, have Y)" | Deposit more |
| Success | "Transfer complete. Block #1234" | Proof provided |

## Cafreso-Specific Gaps

### 1. **Two-Phase Checkout Error**
Checkout requires:
1. Token transfer (on-chain)
2. Order recording (backend API)

If phase 1 succeeds but phase 2 fails, the current flow says only "Recording failed." Better:
- "Payment confirmed (block #X) but order logging failed."
- Show the block number so user can reference it in support ticket.
- Offer "Retry recording" in case it was a temporary API hiccup.

### 2. **No Transaction History**
Cafreso has no transaction log. If a user submits a transfer, closes the browser, and comes back later, they have no way to check if it went through (short of asking the Treasury manager directly).

**Improvement**: Store submitted transaction hashes locally (localStorage or IndexedDB) and poll the ledger periodically to show status updates.

### 3. **Wallet Mismatch Errors Not Surfaced**
Internet Identity canisters require a specific principal. If the user switches identities mid-session, subsequent transfers fail silently with "Transfer not authorized." Better:
- Detect principal change on app startup
- Show: "Your identity changed. [Log out and back in] to use the new principal."

### 4. **Balance Staleness**
Balance displayed on page load may be stale by the time user submits. If they send their last token and then make a second transfer, it may fail with "insufficient balance" even though the display showed enough.

**Mitigation**: Refresh balance on form focus and before submission.

## Principles for Recovery UX

1. **Name the error specifically** — "Insufficient balance" beats "Transfer failed."
2. **Show what the user can do** — Include at least one action: [Retry] [Deposit more] [View explorer]
3. **Preserve transaction proof** — Always show block numbers, hashes, or timestamps so users can verify offline.
4. **Distinguish user vs system errors** — "You need X more tokens" feels different (and more helpful) than "Our server had a problem. Retry in 30s."
5. **Offer async recovery** — If a transfer succeeds on-chain but the dApp loses the response, the user should still be able to verify it later.

## See Also

- [[transaction_confirmation_ux]] — errors are the sad path of confirmation flows
- [[wallet_onboarding_patterns]] — wallet connection errors bridge onboarding and transaction flows
