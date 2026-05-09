---
title: Internet Identity
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/identity
source:
  - https://internetcomputer.org/docs/building-apps/authentication/overview
  - https://github.com/dfinity/internet-identity
related:
  - "[[principals]]"
  - "[[canisters]]"
  - "[[sns]]"
difficulty: beginner
open_questions:
  - Current list of supported authentication methods (passkeys / WebAuthn authenticators / recovery mechanisms) — evolves with II releases.
---

# Internet Identity

> Internet Identity (II) is ICP's native authentication system: a canister + frontend that lets users sign in to any dapp with a WebAuthn passkey and receive a per-dapp [[principals|principal]].

## Why it exists

Dapps need a way to authenticate users without wallets, seed phrases, or a centralized OAuth provider. II uses the browser's WebAuthn stack (Touch ID, Face ID, security keys, platform passkeys) to produce signatures that the replica can verify, and wraps them in a per-origin derivation so the same user is pseudonymous *across* dapps but stable *within* one dapp.

## How it works

- **Anchor** — a user registers an *anchor* (a numeric ID) tied to one or more WebAuthn authenticators (passkeys). Losing all authenticators for an anchor means losing the identity unless recovery is set up.
- **Delegation** — when the user signs into `dapp.example`, II issues a *delegation*: a signed certificate authorizing a session keypair to act as the user's principal for that origin for a limited time. The dapp holds the session key locally; II is not contacted per-call.
- **Per-origin principals** — the principal is derived from (anchor, origin); the same anchor yields a different principal at a different dapp origin. This is the pseudonymity boundary.
- **Frontend integration** — the `@dfinity/auth-client` library handles the popup flow, stores the session key in browser storage, and provides an `Identity` object the agent uses to sign outgoing calls.
- **Backend integration** — the canister just checks `caller` (a [[principals|principal]]); it does not need to know the call came via II. II is a frontend/UX concern.
- **Governance UIs** — the NNS dapp and typical [[sns|SNS]] frontends (including SNS-aggregator UIs used to manage neurons and vote on proposals) authenticate users via II, so the voting principal is the per-origin principal II derives for that governance frontend.

## Example

```ts
import { AuthClient } from "@dfinity/auth-client";

const authClient = await AuthClient.create();
await authClient.login({
  identityProvider: "https://identity.ic0.app",
  onSuccess: () => {
    const identity = authClient.getIdentity();      // use with an Agent
    const principal = identity.getPrincipal();      // per-origin principal
    console.log(principal.toText());
  },
});
```

## Gotchas

- The per-origin derivation means switching your dapp's domain (e.g., from a canister-URL to a custom domain) **changes every user's principal**. Plan domain strategy before launch.
- Session delegations expire; your frontend must handle re-authentication gracefully.
- II is a canister running on a system subnet — outages there affect every dapp using II. Some dapps ship a fallback (e.g., NFID, plug, or direct key-based identities).
- "One anchor, many dapps" means recovery of the anchor is critical UX; losing it is equivalent to losing every dapp account at once.

## See also

- [[principals]]
- [[canisters]]
- [[sns]]
