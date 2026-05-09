---
tags: [research, dapp-ux, payments]
---

# Transaction Confirmation UX in DApps

## Current Patterns in Cafreso

The app implements **two distinct confirmation flows** depending on context:

### 1. Modal-Form Pattern (SendTokenModal, checkout)
- Standard form submission with clear input → validate → submit → await → done
- **Phases**: idle → transferring/recording → done or error
- User confirms by clicking button (low friction)
- Success state shows immutable proof (block index for ICRC-1, order ID for records)
- Gas/network fees displayed upfront before submission

### 2. Hold-to-Confirm Pattern (BurnTipModal)
- 1.5-second hold-down gesture required to submit
- Progress ring visual feedback during hold
- Higher friction = intentional affordance for lossy actions (burning tokens)
- Prevents accidental clicks; psychological pause reinforces consequence

## Key UX Strengths

**Transparency**: Both flows show what will happen before submission—amounts, recipients, fees. No hidden costs.

**Progressive disclosure**: Form validation errors appear inline; treasury principal errors surface only when needed.

**State clarity**: Spinner icons + text ("Sending…", "Recording…", "Transferring…") signal what's happening during the wait.

**Proof of completion**: Ledger block index or order ID gives users something concrete to verify and reference—critical for blockchains where finality isn't instantaneous.

**Payment method context**: Checkout distinguishes on-chain vs off-chain (Stripe) with separate UI sections and trust signals (Stripe logo).

## Common DApp Pitfalls to Avoid

**1. Ambiguous state transitions**  
Users shouldn't wonder if "Confirming..." means waiting for user's wallet or waiting for blockchain. Cafreso avoids this by being specific ("Sending" vs "Recording").

**2. No fallback for network failure**  
If the transfer goes through but the follow-up order recording fails (as in checkout's two-phase flow), the user needs a clear recovery path. Cafreso surfaces this explicitly: "Payment confirmed (block #X) but order logging failed—contact support with this block number."

**3. Insufficient time for reading**  
Auto-dismissing success modals before the user reads the block index wastes the valuable proof. Hold states briefly (1-1.5s after completion) to ensure comprehension.

**4. Missing fee context**  
Users often don't realize they'll pay network fees. Cafreso shows "Network fee: X (auto-deducted)" before submitting, making the math transparent.

## Opportunities for Improvement

### Real-time gas/fee estimation
Currently fees are fetched async and shown as "…" while loading. On-chain dapps could pre-compute and show fees alongside amount input for instant clarity.

### Multi-step recovery hints
For complex flows (like checkout's transfer + order recording), show a progress indicator ("Step 1 of 2") so users understand the wait is normal and how many stages remain.

### Accessibility of confirmation
Hold-to-confirm is elegant but inaccessible to some motor-ability users. Consider a toggle: "Require hold" vs "Enable high-friction mode" for users who want extra safety.

### Wallet-level confirmation integration
When delegating signing to Internet Identity or other wallet providers, the user sees *two* confirmations: dapp modal + wallet UI. This can cause confusion ("Why two screens?"). Clear callouts help: "You'll also see a confirmation from your wallet."

### Post-transaction guidance
After success, users might want to:
- View the transaction on an explorer (ICP Dashboard, ICRC-1 ledger viewer)
- Share proof of payment
- Set up recurring transactions (rare in Cafreso, but useful for subscriptions)

These aren't currently offered post-success.

## Principles for Iteration

1. **Clarity > brevity**: A 2-second extra explanation beats a fast-but-confusing flow.
2. **Fail gracefully**: Network errors, timeout, insufficient balance—each should explain what went wrong and how to fix it.
3. **Proof is valuable**: Keep block indices, order IDs, and timestamps visible long enough to screenshot.
4. **Match friction to stakes**: Burning 500 tokens warrants a hold-to-confirm. Sending 5 does not.

---

See also: [[wallet_onboarding_patterns]]
