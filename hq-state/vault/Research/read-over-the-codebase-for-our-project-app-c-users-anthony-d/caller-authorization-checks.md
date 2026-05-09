---
tags: [research]
---

# Caller Authorization Checks

## Angle

Review `minegold.defi` for ICP canister methods that trust caller identity, admin status, ownership, or authenticated frontend state without enforcing authorization inside the canister.

This complements [[upgrade-state-persistence]] and [[icp-async-reentrancy]]: even if state survives upgrades and async calls are safe, exposed update methods can still be abused if caller checks are incomplete or inconsistent.

## Why this matters

ICP security guidance calls out access-control bugs as a core canister risk:

- Unauthenticated access to privileged API methods.
- Anonymous callers being allowed into methods that require a real user.
- One user reading or mutating another user’s data.
- Admin/controller-only operations relying on frontend gating instead of canister-side checks.
- Small controller groups having unilateral upgrade/control power over asset-holding canisters.

The Internet Computer IAM docs specifically recommend rejecting anonymous callers in authenticated methods, ideally through a shared helper. The high-traffic dapp guidance also notes that authenticated attackers may still need per-caller defenses such as rate limits or usage accounting.

## What to inspect in this codebase

Look for all public `query` / `update` / `shared` methods and classify them:

| Method type | Required check |
|---|---|
| Public read-only metadata | May allow anonymous access |
| User account/profile/position methods | Must reject anonymous caller |
| User-specific reads | Must verify `caller == owner` or authorized delegate |
| Token/account mutation | Must verify caller owns the affected account/position |
| Admin/config/upgrade controls | Must require explicit admin/controller allowlist |
| Reward/mint/claim/liquidation flows | Must prevent caller from choosing arbitrary beneficiary/owner fields |

## Red flags to search for

- Methods that accept a `principal`, `owner`, `account`, `user`, or `beneficiary` argument and act on it without comparing it to `msg.caller` / `ic_cdk::caller()`.
- Frontend-only assumptions like “only admins can see this button.”
- Use of `Principal.anonymous()` / anonymous principals as valid account keys.
- Admin checks implemented in only some methods but not all related mutation methods.
- In Motoko, variable shadowing around `msg` or caller context. One audit writeup warns that shadowing the message context can accidentally make authorization checks refer to the wrong caller.
- Any method where an attacker can pass another user’s principal and trigger transfer, withdrawal, staking, claim, or state update.
- Controller checks confused with app-level admin checks. Controllers can upgrade the canister, but ordinary admin functions should still be explicit and auditable.

## Safer pattern

Centralize caller/auth checks instead of repeating ad hoc logic.

Rust-style concept:

```rust
fn authenticated_caller() -> Result<Principal, String> {
    let caller = ic_cdk::caller();
    if caller == Principal::anonymous() {
        return Err("anonymous caller not allowed".to_string());
    }
    Ok(caller)
}
```

Then each protected method should call this first and derive the user account from the caller, not from an arbitrary request field.

For admin operations:

```rust
fn require_admin() -> Result<Principal, String> {
    let caller = authenticated_caller()?;
    if !STATE.with(|s| s.borrow().admins.contains(&caller)) {
        return Err("admin only".to_string());
    }
    Ok(caller)
}
```

## Suggested local review checklist

- Build an API inventory of all exported canister methods.
- Mark each as `public`, `authenticated`, `owner-only`, or `admin-only`.
- For every authenticated method, verify anonymous callers are rejected.
- For every owner-only method, verify ownership is derived from caller or strictly checked.
- For every admin-only method, verify it uses one shared helper.
- Add negative tests:
  - anonymous caller rejected;
  - user A cannot mutate/read user B;
  - non-admin cannot call config/admin methods;
  - caller cannot spoof `beneficiary` / `owner` fields.

## Sources

- Internet Computer security docs: canister development security best practices.
- Internet Computer IAM security docs: reject anonymous callers for authenticated calls.
- Internet Computer high-traffic dapp launch guidance: authenticated attackers may require per-caller defenses.
- BlockApex ICP security findings: caller/message-context shadowing can break authorization.