---
tags: [research, canDB, security, access-control]
---

# Security and Access Control in canDB

While specific `canDB` documentation on security is not readily available, we can infer its security model from the underlying architecture of the Internet Computer. Security on the IC is fundamentally tied to the **Principal** of the entity making a call.

Every call to a canister method is authenticated, and the canister can identify the `caller`. This allows developers to implement robust access control logic directly within their application canisters.

## Core Security Primitive: The Caller's Principal

The `ic.caller()` method within a canister returns the Principal ID of the user or canister that initiated the current request. This is the bedrock of IC security. Any access control system built in or on top of `canDB` will leverage this primitive.

## Common Access Control Patterns

Given this foundation, here are the patterns developers would likely implement when using `canDB`:

1.  **Owner/Admin Access:** The simplest model. A canister stores a list of admin Principals. Before executing a privileged action (like deleting data or changing settings), the canister code checks if `ic.caller()` is on the admin list.

2.  **Role-Based Access Control (RBAC):** A more scalable approach. The application maintains a mapping of Principals to roles (e.g., `admin`, `editor`, `viewer`). Canister methods then check if the caller's role has the necessary permissions for the requested operation. This logic would live in the application layer, calling `canDB` on behalf of the user.

3.  **Per-Record ACLs (Access Control Lists):** For fine-grained control, each document or record stored in `canDB` could contain its own ACL, specifying which Principals have read or write access. This offers maximum flexibility but adds storage and computational overhead, as permissions must be checked on every access attempt.

## Multi-Canister Implications

In a sharded system like `canDB` (see [[05-data-sharding-and-routing-strategies]]), security checks are vital at each hop. The main router canister might perform initial validation, but the final data canister holding the information *must* re-verify the `caller`'s permissions. This prevents unauthorized users from bypassing the router and calling a data canister directly.

Ultimately, `canDB` likely provides the database infrastructure, while the responsibility for implementing one of these access control patterns falls to the application developer.