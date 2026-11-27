# Paying the factory in ICP and ckUSDT

Status: **design note, first draft, 2026-11-27. Nothing here is built or deployed.**
It is step 3 of the three-year plan (`obsidian-computer/docs/THREE_YEAR_PLAN.md`).

## The problem

`cf_factory` takes only cycles: an owner calls `deposit()` with cycles attached. To get cycles
today a person needs a cycles wallet and the command line. That stops almost everyone outside ICP.

**Goal:** an owner sends ICP or ckUSDT from any wallet, and a minute later their factory balance
shows cycles. They never see the word "cycles wallet".

## What is true on chain today

Read with query calls on 2026-11-27.

| Fact | Value |
|---|---|
| ICP ledger | `ryjl3-tyaaa-aaaaa-aaaba-cai`, fee 0.0001 ICP, supports ICRC-2 |
| ckUSDT ledger | `cngnf-vqaaa-aaaar-qag4q-cai`, 6 decimals, fee 0.01 ckUSDT, supports ICRC-2 |
| ICP to cycles | 1 ICP mints about 1.52 T cycles (rate 15,197 from the cycles minting canister) |
| Factory | `deposit()` credits the caller. There is no way to deposit for someone else |

One trillion cycles is priced at one XDR, about $1.35 to $1.37.

## Design in one paragraph

A new small canister, the **pay desk**, sits in front of the factory. Each owner has their own
deposit address on it. The owner sends ICP or ckUSDT there and calls `settle`. For ICP, the pay
desk burns it into cycles through the network's own minting canister. For ckUSDT, it keeps the
token and hands over cycles from a float it holds. Either way it then deposits the cycles into the
factory in the owner's name. The factory gains one small method, `depositFor`.

## Why a separate canister

- The factory stays simple: it holds cycles and nothing else.
- A bug in token handling cannot touch owners' cycles or their apps.
- The pay desk can be replaced or paused without upgrading the factory.

## The one change to the factory

```
depositFor : (owner : principal) -> (nat)   // cycles attached are credited to `owner`
```

It adds no stored field, so the upgrade is memory-compatible. Anyone may call it: the only thing
a caller can do is give cycles to someone. It refuses the anonymous principal as owner.

## Paying with ICP

1. The owner asks the pay desk for their deposit address: `depositAddress()`. It returns an
   ICRC-1 account (the pay desk, with a subaccount made from the owner's principal) and the older
   account-id form that exchanges use.
2. The owner sends ICP there from any wallet or exchange.
3. The owner, or anyone, calls `settle(owner, #ICP)`. The pay desk then:
   1. reads the balance of that subaccount and stops if it is under the minimum;
   2. writes a journal row, before any call out;
   3. sends the ICP to the cycles minting canister, marked as a top-up of the pay desk;
   4. tells the minting canister, which mints the cycles into the pay desk and says how many;
   5. keeps its fee, and calls `factory.depositFor(owner)` with the rest attached;
   6. marks the journal row done.

The ICP is burned by the network when it becomes cycles. Nobody at Cafreso holds it at any point.

**If a step fails:** every step is safe to repeat. The minting canister remembers a transfer by
its block number, so asking twice mints once. If the factory refuses the deposit, the cycles stay
in the pay desk, recorded as owed to that owner, and `settle` tries again.

Owners with a wallet that supports ICRC-2 can skip the deposit address: approve the pay desk, then
call `payIcp(amount)`. It is the same flow from step 3.2 on.

## Paying with ckUSDT

ckUSDT cannot be turned into cycles directly. There are two ways to handle it.

| | A. Float (recommended first) | B. Swap inside the canister |
|---|---|---|
| How | The pay desk keeps the ckUSDT and gives cycles from a float it holds | The pay desk swaps ckUSDT to ICP on a DEX, then mints cycles |
| Depends on | Someone refilling the float | A DEX working, and its price |
| Risk | The float runs out, and payments pause | Slippage, a thin pool, a DEX outage |
| Work | Small | Larger, and harder to test |

With A, the flow matches ICP up to step 3.2. Then the pay desk:

1. works out the price: dollars per trillion cycles, from the ICP price (the network's exchange
   rate canister) and the ICP-to-cycles rate. The rate is cached for ten minutes;
2. checks the float can cover the cycles. If not, it stops **before** taking any money;
3. moves the ckUSDT from the owner's subaccount to the pay desk's revenue account;
4. calls `factory.depositFor(owner)` with the cycles;
5. marks the journal row done.

The float is cycles the operator puts in. Refilling it means turning ICP into cycles, which today
needs Anthony's yes each time. The collected ckUSDT is revenue.

## Price

The strategy proposes cycles at cost plus 20%. So an owner who pays for 1.2 T receives 1.0 T. The
pay desk keeps the rest: as cycles for ICP payments, and inside the ckUSDT price for ckUSDT.

Example at today's rate: 1 ICP mints about 1.52 T, and the owner is credited about 1.27 T.

`quote(token, amount)` shows the cycles an owner would receive before they send anything.

## Limits

| Limit | Value to start |
|---|---|
| Smallest payment | 0.1 ICP, or 1 ckUSDT |
| Largest single payment | 50 ICP, or 100 ckUSDT |
| Largest total a day, all owners | 500 ICP, or 1,000 ckUSDT |
| Rate older than | 30 minutes: ckUSDT payments pause |

The caps bound the damage of a bug in the first months. They are install settings.

## Refunds

- **Before `settle`:** `refund(token)` sends the owner's deposit back to the principal that owns
  the subaccount, less the ledger fee.
- **After `settle`:** the money is cycles. The factory's `withdraw` can send an owner's unused
  cycles to a canister they name. There is no way back to ICP or ckUSDT, and the page must say so.

## Who can do what

- **Any owner:** `depositAddress`, `quote`, `settle`, `refund`, `myPayments`.
- **Anyone:** `settle` for someone else (it can only help them), `stats`, `getApiDoc`.
- **Operator:** add cycles to the float; pause new payments. No method lets the operator take an
  owner's unsettled deposit.
- **Revenue:** `sweep` sends collected ckUSDT to one account fixed at install. It takes no
  argument, so it cannot be pointed anywhere else.

Agents never move an owner's tokens. An agent can read the deposit address to its owner and call
`settle` after the owner has paid. The transfer itself is the owner's own act, in their wallet.

## Interface sketch

```
type Token = variant { ICP; ckUSDT };
type Payment = record {
  id : nat; owner : principal; token : Token; amount : nat;
  cycles : nat; fee : nat; at : int;
  state : variant { started; minted; credited; refunded; failed : text };
};

depositAddress : () -> (record { account : Account; legacyAccountId : text }) query;
quote          : (Token, nat) -> (record { cycles : nat; fee : nat; rateAt : int }) query;
settle         : (principal, Token) -> (variant { ok : Payment; err : text });
payIcp         : (nat) -> (variant { ok : Payment; err : text });   // ICRC-2 route
refund         : (Token) -> (variant { ok : nat; err : text });
myPayments     : () -> (vec Payment) query;
stats          : () -> (record { float : nat; owedCycles : nat; paused : bool;
                                 icpBurned : nat; ckusdtTaken : nat; payments : nat }) query;
sweep          : () -> (variant { ok : nat; err : text });
getApiDoc      : () -> (text) query;
```

## What the owner sees

An "Add funds" panel on Obsidian.Computer, later also in the Cafreso skill's output:

- their deposit address, with a copy button and a QR code;
- "You will receive about 1.27 T cycles for 1 ICP", from `quote`;
- after paying: the balance in cycles, and in plain terms how long that runs one small app;
- a clear line that payments cannot be turned back into ICP or ckUSDT.

## Tests before anything goes near mainnet

On a local replica, with the harness in `scripts/replica_harness` (it already has a mock ledger):

1. ICP happy path: deposit, settle, owner's factory balance rises by the quoted amount.
2. `settle` twice: one payment.
3. The minting step fails, then works on retry: one payment, no lost ICP.
4. The factory refuses the deposit: cycles are owed, and the next `settle` delivers them.
5. ckUSDT with an empty float: refused, and no token moves.
6. A stale rate: ckUSDT pauses, ICP still works.
7. Refund before settle returns the deposit less the fee. Refund after settle is refused.
8. Each cap is enforced.
9. The factory upgrade with `depositFor` passes `moc --stable-compatible` against the live build.

## Build order

1. `depositFor` in the factory, with tests. Upgrade on Anthony's yes.
2. The pay desk with ICP only. Replica tests. Deploy on Anthony's yes, with low caps.
3. One real payment of 0.1 ICP by Anthony, end to end.
4. The "Add funds" panel.
5. ckUSDT by the float route.
6. Opt the pay desk in to DFINITY's connector, so an assistant can quote and settle.

Rough cost: about 1.5 T cycles to create and fund the pay desk, plus the float.

## Risks

- **A stuck payment.** The journal and repeatable steps are there for this. `myPayments` shows
  the state, so support can see where one stopped.
- **The rate.** A wrong ckUSDT rate gives away cycles or overcharges. The freshness limit
  and the caps bound it.
- **The float runs dry.** ckUSDT pauses cleanly, and ICP is unaffected.
- **Taking payment in a stablecoin.** This is selling hosting credit, and it is not refundable in
  kind. It belongs on the list for the lawyer's review in the plan.
- **Card payment** is not covered. It needs a partner and comes later.

## Decisions for Anthony

1. A separate pay desk canister, with `depositFor` added to the factory?
2. The fee: cost plus 20%?
3. ckUSDT by the float route first?
4. The starting caps in the table above?
5. Where collected ckUSDT goes: the reserve account today, the treasury canister once it is live?
6. Should ckUSDC be accepted too? It works the same way as ckUSDT.
