---
tags: [research]
---

# Certified query responses

## Angle

If the app uses `query` methods for frontend-visible balances, prices, pool state, user positions, or admin/config data, those responses are fast but are not automatically consensus-certified. A malicious replica, boundary node, or MITM can spoof or stale-serve uncertified query responses unless the canister uses certified data and the client verifies it.

This is separate from update-call correctness covered in [[icp-async-reentrancy]] and caller checks in [[caller-authorization-checks]].

## What the ICP docs emphasize

- Update calls are consensus-certified by default; query calls are not.
- For query calls that must be trusted, the canister should:
  - commit a 32-byte root hash via certified data;
  - return a witness/hash tree plus certificate with the query response;
  - ensure the witness binds the returned value and relevant query parameters;
  - allow the client to recompute the witness root and compare it with `/canister/<canister_id>/certified_data`;
  - verify certificate time freshness, with docs suggesting a default staleness window around 5 minutes, adjusted by use case.
- Asset canisters get special handling through certified assets, but custom app query methods do not get this “for free.”

## Code review checklist for minegold.defi

Look for any `query` methods that return security-sensitive data:

- token/ledger-like balances;
- deposit status;
- staking position or rewards;
- swap quotes used for signing/submitting trades;
- gold price/oracle values;
- vault totals, TVL, pool reserves;
- user-specific entitlement or KYC/allowlist state;
- admin-config values used by the frontend to decide which canister/principal to trust.

For each, classify:

1. **Display-only and low impact** — uncertified query may be acceptable if UI clearly treats it as informational.
2. **Decision-making but rechecked by update call** — acceptable only if update method independently validates all assumptions.
3. **Security/financial decision directly trusted by frontend** — should use certified variables/maps or be converted to an update call.

## Likely bug pattern

A frontend fetches a fast query result, then uses that value to decide whether to transfer, mint, redeem, or display a “confirmed” financial state. If the subsequent update call does not recompute the authoritative value, a spoofed/stale query can mislead the user or produce incorrect app behavior.

Example risks:

- stale “deposit confirmed” state;
- manipulated displayed rewards;
- fake pool price/quote;
- stale admin configuration pointing users at old or malicious flows;
- frontend showing a successful/settled state before a certified or update-confirmed result exists.

## Suggested improvement

For sensitive query data:

- use `ic-certified-map` or equivalent certified hash tree structure;
- include the queried key/parameters in the witness;
- return certificate + witness + value from the query;
- verify on the frontend before trusting the value;
- enforce a freshness check on certificate `/time`;
- if certification is too much for now, use update calls for critical confirmation paths.

## Test ideas

- Add a unit/integration test proving the certified witness changes when the returned value changes.
- Add a frontend verification test that rejects:
  - mismatched witness/value;
  - stale certificate time;
  - witness for a different key/user;
  - missing certificate.
- Add code comments marking which queries are intentionally uncertified and why.

## Priority

Medium to high if minegold.defi has query methods feeding financial UX decisions. Low if queries are purely cosmetic and all sensitive state transitions are independently validated in update calls.