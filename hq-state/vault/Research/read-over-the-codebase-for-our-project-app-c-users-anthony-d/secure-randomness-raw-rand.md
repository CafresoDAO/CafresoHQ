---
tags: [research]
---

# Secure randomness with `raw_rand`

## Angle

If `minegold.defi` has lotteries, randomized rewards, NFT/loot assignment, security codes, randomized mining outcomes, or any game/DeFi mechanic that depends on unpredictability, randomness must come from ICP’s secure randomness API rather than local pseudo-random sources.

## What the ICP docs say

- ICP exposes `raw_rand` through the management canister.
- `raw_rand` returns 32 bytes of cryptographically secure randomness.
- It is specifically recommended for canister randomness.
- Docs warn against low-entropy sources such as:
  - current time,
  - block/round timing,
  - counters,
  - caller principal,
  - deterministic hashes of public state.

## Why this matters

A canister is deterministic except where it explicitly calls IC-provided randomness. If project logic derives “randomness” from public or predictable inputs, users may be able to:

- predict reward outcomes,
- time calls to influence results,
- grind multiple identities/accounts for favorable values,
- front-run or selectively abandon bad outcomes,
- exploit modulo bias if random bytes are converted poorly into ranges.

This overlaps with [[icp-async-reentrancy]] because `raw_rand` is asynchronous: state transitions around the randomness request must be carefully staged so users cannot manipulate pending outcomes or trigger duplicate settlement.

## Code review checklist

Search the codebase for:

- `raw_rand`
- `Random`
- `rand`
- `random`
- `Time.now`
- `ic_cdk::api::time`
- `Principal`
- `hash`
- `%`
- `mod`

Flag any reward/selection/security-sensitive path that uses pseudo-randomness instead of `raw_rand`.

## Safer implementation pattern

- Commit the user action before requesting randomness.
- Store a pending request/state marker.
- Call `raw_rand`.
- On callback, consume the pending state exactly once.
- Convert bytes to bounded ranges using rejection sampling, not naive modulo, where fairness matters.
- Make retry/failure behavior explicit and idempotent, similar to [[icrc-ledger-idempotent-retries]].

## Potential vulnerability

If `minegold.defi` uses timestamps, caller IDs, counters, hashes of visible state, or modulo-reduced random bytes for mining/reward outcomes, the result may be predictable or biased. This could let sophisticated users extract more rewards than intended.

## Recommended improvement

Centralize randomness behind a small backend helper/module:

- only exposes secure `raw_rand`-backed APIs,
- documents when pseudo-randomness is acceptable,
- uses unbiased range conversion,
- logs pending/completed random operations,
- prevents duplicate settlement across retries/upgrades, tying into [[upgrade-state-persistence]].
