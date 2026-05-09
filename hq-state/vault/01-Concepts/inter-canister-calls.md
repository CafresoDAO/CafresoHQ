---
title: Inter-Canister Calls
type: concept
status: draft
created: 2026-04-21
updated: 2026-04-21
tags:
  - icp
  - icp/concept
  - icp/concept/inter-canister-calls
  - icp/pattern/inter-canister-calls
source:
  - https://internetcomputer.org/docs/references/async-code
  - https://internetcomputer.org/docs/motoko/fundamentals/actors/messaging
  - https://internetcomputer.org/docs/references/ic-interface-spec
  - https://github.com/dfinity/cdk-rs
related:
  - "[[canisters]]"
  - "[[motoko]]"
  - "[[rust-cdk]]"
  - "[[candid]]"
  - "[[cycles]]"
difficulty: intermediate
open_questions:
  - Current maximum bounded-wait timeout ceiling (documented as "around 5 minutes" but the exact value is subject to change via replica releases).
  - Whether the best-effort-response API is GA or still behind a feature flag on all subnet types.
---

# Inter-Canister Calls

> An inter-canister call is a [[canisters|canister]]-to-canister RPC: canister `A` invokes a method on canister `B`, the ICP delivers the request, `B` executes it, and a response (or error) is routed back. Calls are **asynchronous**, bounded by the subnet's scheduling rules, and encoded in [[candid|Candid]] by default.

## Why it exists

A dapp on ICP is almost always more than one canister: a frontend asset canister talks to a backend; the backend talks to the ledger; maybe to Internet Identity, maybe to a Bitcoin canister. Unlike Ethereum, where contract→contract calls are synchronous inside a single transaction, ICP canisters live on different subnets and run on their own message scheduler. Inter-canister calls give them a well-typed, async-friendly way to interact across those boundaries.

## How it works

- **Async + callback based** — at the Wasm system API level, a call is made with `ic0.call_new` / `ic0.call_perform` and the reply is delivered to a named callback. CDKs hide this behind `async`/`await`:
  - Motoko: `await canister.method(args)` where `canister` is imported as `import X "canister:x"` or built via `actor(canisterId) : actor { ... }`.
  - Rust: `ic_cdk::call(target, "method", (args,)).await`, or the `candid::Principal`-based wrappers generated from a `.did` binding.
- **Each `await` is a message boundary.** Control yields back to the scheduler; other messages on the same canister can run before the reply arrives. This is the source of ICP's **reentrancy** hazard — your canister's state can be mutated between `await` points.
- **Cycles can ride along.** A caller may attach [[cycles]] to a call; the callee must explicitly accept them with `ic_cdk::api::call::msg_cycles_accept` (Rust) / `ExperimentalCycles.accept` (Motoko). Unaccepted cycles are refunded. Some management-canister methods (threshold ECDSA, HTTPS outcalls) *require* attached cycles.
- **Bounded-wait vs unbounded-wait** — two delivery modes:
  - **Unbounded-wait (a.k.a. guaranteed-response)** — the system waits until the callee either replies or the request provably fails. The caller always learns the outcome but may block indefinitely if the callee stalls.
  - **Bounded-wait (a.k.a. best-effort-response)** — the caller sets a timeout (capped by the system, documented as on the order of five minutes). After the timeout the system may deliver an "unknown" error even if the request was processed. Scales better under load; safer for upgrades (since unbounded calls block `stop` and therefore block safe upgrades).
- **Error classes** — transport-level reject codes (canister trapped, canister not found, out of cycles, timed out), plus whatever application error the callee returned. Both Motoko and Rust surface these via `try`/`catch` (Motoko) or `CallResult<T>` (Rust).
- **Candid at the boundary** — arguments and returns are serialised as [[candid|Candid]]. The CDK does the encoding; dynamic calls (`IC.call` in Motoko, `ic_cdk::api::call::call_raw` in Rust) take raw bytes if you need to bypass the type system.
- **Query vs update targets** — you can inter-canister-call an `update` method (goes through consensus on the callee's subnet) or a `query` method. Note: a Motoko `query` function cannot itself issue inter-canister calls — only `update` contexts are async contexts.

## Example

```motoko
// Motoko: typed import + await.
import Ledger "canister:ledger";

actor Wallet {
  public func balanceOf(who : Principal) : async Nat {
    // Each `await` is a message boundary; other messages may run between.
    await Ledger.icrc1_balance_of({ owner = who; subaccount = null });
  };
};
```

```rust
// Rust: call via ic_cdk::call with a (tuple,) args.
use candid::Principal;
use ic_cdk::call;

#[ic_cdk::update]
async fn balance_of(ledger: Principal, who: Principal) -> u128 {
    let (balance,): (u128,) = call(ledger, "icrc1_balance_of", (who,))
        .await
        .expect("ledger call failed");
    balance
}
```

## Gotchas

- **Reentrancy is real.** Between `await` and the reply, other messages can run and mutate your state. Don't read-modify-write across an `await`; either snapshot what you need before the call or lock/guard the critical section.
- **Unbounded-wait calls can block upgrades.** A stopped canister must drain its outstanding calls before it can upgrade safely. A caller that issued an unbounded-wait call to a misbehaving callee may be un-upgradeable until the call resolves.
- **Best-effort does not guarantee "did it happen?"** A timed-out bounded-wait call may or may not have executed on the callee. Design idempotent endpoints (see dfinity's idempotency best-practice doc) so retries are safe.
- **Cycles are spent on failed calls too.** Even rejected requests cost cycles for the message and for serialising the args.
- **Cross-subnet calls are slower.** Requests that cross subnet boundaries carry a chain-key signature handshake; co-locate tightly coupled canisters on the same [[subnets|subnet]] when latency matters.
- **A self-call is still a real message.** `await self.foo()` goes through the scheduler, yields the canister, and costs cycles — it is not a function call.

## See also

- [[canisters]]
- [[candid]]
- [[cycles]]
- [[motoko]]
- [[rust-cdk]]
- [[subnets]]
