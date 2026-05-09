---
tags: [research]
---

# ICP async/await reentrancy review angle

## Angle

Internet Computer canisters can hit reentrancy-style bugs around `async` / `await` and inter-canister calls. This is especially relevant for DeFi code because state transitions often involve balances, deposits, swaps, mints, withdrawals, or ledger calls.

## What the search surfaced

ICP guidance warns about patterns where a canister:

- changes global state,
- makes an inter-canister call,
- then assumes the state is unchanged when execution resumes.

On ICP, an `await` yields control. Other messages can execute before the original function resumes, so state may be modified “in between.” This can break assumptions in Motoko and Rust canisters.

The official high-traffic dapp guidance specifically calls out:

- changing global state before an inter-canister call,
- changing it again in the callback/continuation,
- assuming no other message changed state meanwhile,
- not handling failed inter-canister calls correctly after partial state updates.

Security writeups also recommend locking critical flows, either globally or per caller/resource, when concurrent mutation would be unsafe.

## Codebase review checklist for `minegold.defi`

Look for functions that:

- call external canisters such as ICRC/ledger, swap, index, oracle, or governance canisters;
- contain `await`, `await*`, `.await`, or callback-like continuations;
- mutate balances, ownership, pool reserves, rewards, deposits, claims, or order state before the await;
- resume after the await and write state again;
- do not use a pending/locked/in-flight status;
- do not roll back or compensate on error;
- catch errors but leave state partially updated.

High-risk examples to hunt for:

```motoko
balances.put(user, balance - amount);
let result = await ledger.icrc1_transfer(...);
if (result is #Err) {
  balances.put(user, balance); // stale balance may overwrite later changes
}
```

```rust
state.withdrawals.insert(id, Pending);
let transfer = ledger.transfer(args).await;
// assumes withdrawal state has not changed here
state.withdrawals.remove(&id);
```

## Safer patterns to consider

- Use explicit state machines: `Created -> PendingTransfer -> Completed/Failed`.
- Store operation IDs/nonces and verify the operation is still current after `await`.
- Prefer checks-effects-interactions, but remember ICP’s failure handling still needs compensation logic.
- Use per-account or per-resource locks for withdraw/deposit/claim paths.
- Avoid restoring stale snapshots after failed calls; recompute or apply targeted compensation.
- Make post-await code revalidate all assumptions.
- Add tests that trigger two concurrent calls from the same principal or same asset/pool.

## Why this matters for DeFi

If `minegold.defi` has mining rewards, token claims, deposits, swaps, or treasury transfers, a reentrancy window could cause:

- double-claiming rewards,
- stale balance overwrite,
- locked funds,
- inconsistent pool accounting,
- duplicate withdrawals,
- bypassed limits/cooldowns.

Future iterations should inspect the actual source for `await` boundaries and map each one to the state touched before and after.