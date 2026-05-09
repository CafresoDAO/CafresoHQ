---
tags: [research]
---

# Cycles balance and freezing-threshold DoS

## Angle

A canister with insufficient cycles can become **frozen**: the IC stops accepting new requests so the remaining balance can cover the configured freezing threshold. For `minegold.defi`, this is an operational availability risk and can become a denial-of-service vector if attackers can trigger expensive calls or force costly inter-canister work.

Related notes: [[icp-async-reentrancy]], [[caller-authorization-checks]], [[icrc-ledger-idempotent-retries]]

## Why this matters

The IC docs describe the freezing threshold as a safety reserve: if the canister balance becomes too low, the system freezes the canister so it can survive for the configured duration. A frozen canister will stop processing new requests, which is effectively downtime for app users.

The IC DoS guidance specifically recommends:

- Monitor cycle consumption and balance automatically.
- Alert on sudden cycle consumption spikes.
- Use early authentication and rate limiting to avoid paying for expensive unauthenticated work.

## Code review checks for `minegold.defi`

Look for public update methods that:

- Do significant computation before checking `caller`.
- Accept large payloads, arrays, text blobs, or unbounded loops.
- Trigger inter-canister calls, ledger calls, timers, retries, or background jobs.
- Perform storage writes for unauthenticated or low-value requests.
- Retry failed ledger / canister calls without caps or idempotency guards.
- Expose “admin-like” maintenance endpoints without strict authorization.

Also check deployment/config files for:

- Explicit `freezing_threshold` configuration.
- Cycles monitoring scripts or dashboard references.
- Alerting on:
  - low cycle balance,
  - high cycles burned per interval,
  - unexpected update-call volume,
  - repeated failed inter-canister calls.

## Suggested patch pattern

- Put authorization and cheap validation at the very start of update methods.
- Add per-principal and/or global rate limits for public costly methods.
- Bound input sizes and loop counts.
- Cap retries and backoff for outbound calls.
- Make maintenance/admin endpoints controller- or allowlist-only.
- Add an ops runbook for topping up cycles before the freezing threshold is approached.
- Expose a lightweight health/status method that reports cycle balance and warns before danger zones.

## Example implementation idea

For Motoko canisters, add a shared helper around public update entrypoints:

```motoko
func requireAuthorized(caller : Principal) {
  if (Principal.isAnonymous(caller)) {
    throw Error.reject("anonymous caller not allowed");
  };
};

func assertSmallBatch<T>(items : [T], max : Nat) {
  if (items.size() > max) {
    throw Error.reject("batch too large");
  };
};
```

Then call these before any expensive compute, storage mutation, or inter-canister call.

## Severity

Medium to high depending on which public methods exist. If attackers can repeatedly trigger expensive updates or ledger interactions, this can become a practical availability attack by driving the canister toward its freezing threshold.