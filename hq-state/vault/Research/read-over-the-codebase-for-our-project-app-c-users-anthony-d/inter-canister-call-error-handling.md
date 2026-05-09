---
tags: [research]
---

# Inter-canister call error handling and cleanup

## Angle

ICP inter-canister calls can fail in several ways: clean rejects, transient system failures, callback traps, and ambiguous failures where the caller cannot know whether the callee made progress. For a DeFi app, this matters anywhere the code calls ledgers, indexers, swap canisters, or internal canisters after mutating local state.

## What the ICP docs emphasize

- Inter-canister responses are handled in callbacks.
- If a reply/reject callback traps, cleanup logic may run, but app-level state can still be left inconsistent if the code relies on the callback finishing successfully.
- Rust CDK exposes helpers such as `is_clean_reject` and `is_immediately_retryable` for interpreting reject codes.
- Motoko supports `try/finally`, which should be used for releasing locks or resetting in-flight flags.
- Public update methods should be checked for state changes followed by throws/traps, since commit points can make some changes durable while later logic rolls back or fails.

## Codebase review checklist

Look for patterns like:

```motoko
state := #Pending;
let result = await ledger.icrc1_transfer(args);
state := #Complete;
```

or Rust equivalents where state is updated before an `await` and failure paths do not mark the operation as failed/retryable.

Specific risks:

- **Stuck locks / stuck pending operations**
  - Example: user withdrawal marked `pending`, ledger call rejects, code never clears pending flag.
  - Related to [[icp-async-reentrancy]], but this note focuses on failure cleanup rather than re-entry.

- **Double retry / duplicate side effects**
  - If a call times out or returns an ambiguous system error, blindly retrying can duplicate downstream effects unless the callee operation is idempotent.
  - For ledger calls, tie this back to [[icrc-ledger-idempotent-retries]].

- **State committed before external call**
  - ICP await boundaries create commit points. Any pre-await state mutation may persist even if post-await logic traps.
  - Review any DeFi accounting flow where balances, shares, rewards, deposits, or withdrawals are changed before an external call completes.

- **Callback trap after successful external action**
  - The callee may have completed successfully, but the caller’s callback traps while decoding or updating local state.
  - This can create “funds moved but app state not updated” incidents.

## Safer implementation pattern

For each outbound call:

1. Create a durable operation record with a unique operation id.
2. Mark it `Pending`.
3. Perform the external call.
4. On success, mark `Succeeded` and store the returned block/index/receipt.
5. On clean reject, mark `Failed` with reason.
6. On transient or ambiguous error, mark `Unknown` or `Retryable`, not simply `Failed`.
7. Ensure locks/in-flight flags are released in `finally` / cleanup paths.
8. Make retries idempotent using memo, created-at time, nonce, or operation id where supported.

## Suggested audit target

Search the project for:

- `await`
- `call`
- `transfer`
- `icrc1_transfer`
- `icrc2_transfer_from`
- `try`
- `catch`
- `finally`
- `trap`
- `unwrap`
- `expect`
- pending/in-flight flags

Then inspect each function for:

- local state mutation before `await`
- missing `catch` / reject handling
- cleanup not guaranteed
- retry behavior that lacks idempotency
- user-visible operation state missing for ambiguous failures

## Severity

High for withdrawals, deposits, swaps, mint/burn flows, reward claims, and any operation touching user balances.

Medium for non-financial background sync jobs or analytics calls.

## Practical patch direction

Add a small operation journal abstraction for financial inter-canister calls:

```text
Operation {
  id,
  caller,
  kind,
  amount,
  status: Pending | Succeeded | Failed | Unknown,
  external_receipt,
  error,
  created_at,
  updated_at
}
```

Use this journal to make retries explicit, observable, and idempotent instead of relying on one-shot call success.
