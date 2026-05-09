---
title: Principals
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/principal
source:
  - https://internetcomputer.org/docs/building-apps/essentials/identity
  - https://internetcomputer.org/docs/references/ic-interface-spec
related:
  - "[[canisters]]"
  - "[[internet-identity]]"
  - "[[inter-canister-calls]]"
  - "[[sns]]"
difficulty: beginner
open_questions:
  - Exact byte layout and version tagging for self-authenticating vs. derived principals (check the interface spec before relying on it).
---

# Principals

> A principal is ICP's universal identity: a self-describing byte string that names a user, a [[canisters|canister]], or a role, and is attached to every message the replica sees.

## Why it exists

ICP needs one identity type that covers both *humans/services calling canisters* and *canisters calling canisters*, without the chain caring which is which. Principals give every sender a verifiable name the receiver can authorize against — no separate "account address vs. contract address" split.

## How it works

- **Kinds** — common categories include: *self-authenticating* (derived from a public key, used by end users and dev identities), *canister* (assigned when a canister is created; encodes subnet routing info), *anonymous* (the null principal, for unauthenticated queries), and *opaque* (system-reserved).
- **Textual form** — groups of lowercase base32 separated by dashes with a CRC check, e.g. `rrkah-fqaaa-aaaaa-aaaaq-cai`. The form is designed to be copy-pasteable and typo-resistant.
- **Authentication** — for user principals, the agent signs each request with the matching private key; the replica verifies the signature and sets the `caller` to the derived principal. A canister receiving a call uses `msg.caller` / `ic_cdk::caller()` for authorization.
- **Derivation for dapps** — services like [[internet-identity]] derive a **per-origin** principal from the user's II anchor, so the same human appears as a different principal to different dapps (pseudonymity across apps, consistent identity within one app).
- **Controllers** — a canister's controllers are a set of principals authorized for management calls; they can be users, other canisters, or NNS-managed roles. In an [[sns|SNS]], the SNS **Root** canister's principal is the sole controller of every other SNS canister and of the dapp canister(s) handed off to the DAO; neuron ownership is likewise attributed to a principal.

## Example

```motoko
import Principal "mo:base/Principal";

actor {
  public shared ({ caller }) func whoami() : async Principal {
    caller
  };

  public shared ({ caller }) func onlyOwner() : async () {
    assert (not Principal.isAnonymous(caller));
    // ... authorized logic
  };
};
```

## Gotchas

- **Anonymous calls** are the default for unauthenticated queries; always check `isAnonymous(caller)` before gating sensitive logic.
- Principals from [[internet-identity]] are **per-dapp**; don't assume a user's principal is stable across apps.
- A canister's own principal (`Principal.fromActor(this)` / `ic_cdk::id()`) is different from a user-principal of the developer who deployed it.
- Storing principals as strings is fine for display; for authorization compare the binary/typed form to avoid canonicalization bugs.

## See also

- [[canisters]]
- [[internet-identity]]
- [[dfx]]
- [[sns]]
