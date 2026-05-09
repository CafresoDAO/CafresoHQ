---
tags: [research]
---

# ICRC ledger idempotent retries

## Angle

For a DeFi app, ledger transfers are high-risk because canister-to-ledger calls may end in an **unknown state**: the caller may not know whether the ledger accepted the transfer before the response was lost, trapped, timed out, or rejected at the system boundary.

This is distinct from [[icp-async-reentrancy]]: even without reentrancy, retry logic can accidentally create duplicate financial effects if it is not idempotent.

## Key finding

The Internet Computer docs recommend making ledger transfers idempotent by retrying with **identical transfer arguments**, including:

- `created_at_time`
- `memo`
- sender/subaccount
- recipient
- amount
- fee

ICRC ledgers can deduplicate transactions with the same parameters inside their transaction window. If a call returns an unknown result, the app should retry the exact same transaction rather than creating a fresh transfer request.

## Bug/vulnerability pattern to look for in `minegold.defi`

Search the codebase for ICRC/ledger transfer paths and check whether retries regenerate any of these fields:

- `created_at_time = now()` inside each retry attempt
- random or incrementing `memo` per retry
- recalculated `fee` without preserving the original transfer args
- rebuilt transfer object after a timeout
- frontend retry button that submits a brand-new withdrawal/deposit request
- backend job processor that replays failed jobs by constructing a new ledger transaction

If any of these happen, the app may double-send funds during transient failures.

## Safer implementation pattern

For each financial operation:

1. Create a durable internal operation record before calling the ledger.
2. Store the exact ledger transfer args on that record.
3. Include `created_at_time`.
4. Use a deterministic or persisted `memo`.
5. On retry, reuse the stored args byte-for-byte/logically exactly.
6. Treat `Duplicate` / duplicate transaction responses as success if they match the pending operation.
7. Reconcile final status by querying transaction history or account balances where appropriate.

## Extra caution

ICRC transaction deduplication is not infinite. It depends on the ledger’s configured transaction window and permitted drift. A retry after the deduplication window may no longer be deduplicated, so the app should avoid blindly retrying old pending transfers.

Recommended policy:

- retry aggressively only while inside the ledger deduplication window;
- after the window expires, switch to manual/operator reconciliation or ledger-history verification;
- expose pending/unknown states in admin tooling rather than silently creating a new transaction.

## Code review checklist

- [ ] Are all ledger calls wrapped with explicit unknown-state handling?
- [ ] Are transfer args persisted before the first call?
- [ ] Does retry logic reuse the original `created_at_time` and `memo`?
- [ ] Are duplicate-transaction responses mapped to success/idempotent completion?
- [ ] Is there a cutoff after which automatic retries stop?
- [ ] Are withdrawal/deposit operation IDs separate from ledger transaction IDs?
- [ ] Is there logging for unknown, duplicate, success, and fatal ledger outcomes?

## Why this matters

In DeFi, retry bugs become money bugs. A transient network or subnet issue should not be able to turn one user withdrawal, purchase, mint, burn, or settlement into multiple ledger transfers.