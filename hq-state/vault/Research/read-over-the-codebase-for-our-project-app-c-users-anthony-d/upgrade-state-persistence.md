---
tags: [research]
---

# Upgrade state persistence risks

## Angle

IC canister upgrades can silently lose or corrupt application state when runtime-only collections (e.g. `HashMap`, `Buffer`, class instances, closures, non-shared objects) are not correctly serialized into stable variables before upgrade and reconstructed afterward.

This is especially relevant for a DeFi app because balances, positions, pool accounting, allowances, reward checkpoints, admin settings, and pending withdrawal/deposit state must survive upgrades exactly.

## What the sources say

- Motoko persists `stable` variables across upgrades, but ordinary actor fields are flexible/runtime-only and can be lost unless explicitly made stable.
- Upgrade hooks exist:
  - `system func preupgrade()`
  - `system func postupgrade()`
- Official docs note that relying heavily on upgrade hooks should be avoided when possible.
- A common risky pattern is:
  - keep fast runtime structures such as `HashMap`
  - convert them to stable arrays in `preupgrade`
  - rebuild them in `postupgrade`
- Joachim Breitner’s IC audit guidance highlights this exact idiom as an audit target because the conversion logic can be incomplete or inconsistent.

## Bugs/vulnerabilities to look for in `minegold.defi`

Search the codebase for:

- `system func preupgrade`
- `system func postupgrade`
- `stable var`
- `HashMap`
- `Buffer`
- `Trie`
- `Array`
- custom migration/version fields

Then check:

- **Missing fields in serialization**
  - Example: stable snapshot saves user balances but forgets accrued rewards, lock timestamps, referral state, pending claims, or fee debt.

- **Post-upgrade reinitialization bugs**
  - Runtime maps rebuilt empty or partially rebuilt.
  - Admin/owner/default config reset to deployer defaults.
  - Fee parameters or token canister IDs reset.

- **Schema migration hazards**
  - Stable data layout changed without a versioned migration path.
  - Old deployments unable to upgrade to new code.
  - Optional fields added but not defaulted safely.

- **Trap risk in upgrade hooks**
  - `preupgrade` or `postupgrade` can trap if converting large maps, unwrapping nulls, or exceeding instruction limits.
  - A trapped upgrade can leave the app unable to deploy fixes cleanly.

- **Accounting invariant drift**
  - After reconstruction, total user balances should still equal ledger/internal totals.
  - Pool reserves, share supply, reward indexes, and debt accounting should match pre-upgrade snapshots.

## Suggested hardening

- Prefer stable-native structures where practical.
- Maintain explicit stable schema versions:
  - `stable var stateVersion : Nat = 1`
  - migration functions from each old version to current.
- Add upgrade tests that:
  - create users/positions/rewards
  - simulate upgrade
  - verify all balances and invariants survive
- Add an invariant checker callable by admin/query:
  - total balances
  - pool reserve consistency
  - reward index sanity
  - no negative/overflowed accounting
- Keep `preupgrade` simple and deterministic.
- Avoid clearing stable snapshots in `postupgrade` until reconstruction succeeds.

## Link to prior note

Related to [[icp-async-reentrancy]] because both issues can break DeFi accounting, but upgrade persistence bugs are operational/state-layout failures rather than call-flow failures.