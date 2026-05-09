---
tags: [research]
---

# Pending Transaction Status & Management UX

## The Core Problem

After [[transaction_confirmation_ux|confirming a transaction]], users enter a limbo state—waiting for blockchain inclusion. This is **where trust erodes fastest**:

- Users accustomed to Web2 instant feedback interpret delays as "the app is broken"
- No visibility into what's happening creates anxiety ("Did it go through?")
- Stuck or orphaned transactions confuse users who can't interpret confirmation counts
- Silent failures (tx pending forever, never landing) feel like data loss

## Current Best Practices

### 1. **Visual Status Progression**
- Show clear states: **Pending → Confirming → Confirmed → Failed**
- Use progress indicators (animated bars, percentage blocks) to fight the perception of "nothing happening"
- Each state needs a distinct visual treatment; users scan quickly

### 2. **Estimated Completion Times**
- Display countdown or ETA based on network conditions
- Dramatically reduces user anxiety ("5 mins remaining" beats "waiting")
- Must be honest: better to show ±range than falsely precise times
- Update estimates in real-time as network conditions change

### 3. **Confirmation Transparency**
- Show confirmation count (e.g., "2/12 confirmations") NOT cryptic "pending" labels
- Explain what "confirmed" means in your context (how many blocks = final?)
- Surface this without jargon—users don't need to know "nonce" or "mempool"

### 4. **Optimistic UI (Carefully)**
- Show the result immediately (e.g., balance update, token swap completed visually)
- BUT clearly mark it as "pending confirmation" in a subtle, non-alarming way
- If it fails, rollback visually and explain why (failed to submit, insufficient funds, etc.)
- This feels responsive without deceiving users

### 5. **Actionable Exit Routes**
- **If stuck**: Provide "speed up" or "cancel" buttons (if the chain supports it)
- **If failed**: Show the actual error + suggest recovery (retry, adjust gas, check balance)
- **If slow**: Offer option to monitor in a block explorer or get notifications
- Don't trap users in a waiting state with no escape hatch

### 6. **Real-Time Updates**
- Poll status or use WebSocket subscriptions, don't make users refresh
- Surface state changes immediately ("Confirmed!" notification)
- Show tx hash early so users can independently verify on a block explorer

## Common Pitfalls

- **Orphaned tx display bug**: App says "pending" but blockchain shows 76 confirmations (confirmation sync mismatch)
- **No error boundaries**: Transactions fail silently, no explanation of why
- **False progress**: Showing progress bars that don't correlate to actual block progress
- **Stuck queue**: Showing multiple transactions stuck indefinitely with no "speed up" option

## Next Steps for Cafreso

1. Map current tx status flow: when/where does status get polled?
2. What states can a tx reach? (pending, confirmed, failed, dropped, replaced)
3. Can you show confirmation counts or only "pending/confirmed"?
4. Are there "speed up" or "cancel" primitives available on the target chains?
5. How do you handle orphaned/stuck transactions in your recovery flow?

## Related

- [[transaction_confirmation_ux]] — the confirmation modal that precedes this
- [[error_handling_recovery_patterns]] — what to do when the tx fails
- [[gas_fee_transparency_ux]] — gas context for "speed up" and stuck tx scenarios