# Paying the factory in ICP and ckUSDT

Status: **ICP pay-in is built and tested on a local replica (2026-11-27). Nothing is deployed.**
ckUSDT, the "Add funds" panel and the connector opt-in are still design only.
It is step 3 of the three-year plan (`obsidian-computer/docs/THREE_YEAR_PLAN.md`).

Decided by Anthony on 2026-11-27: **build it into the factory**, **do not accept ckUSDC**, and
**the fee is cost plus 10%**.
The first draft proposed a separate canister; that is dropped.

## The problem

`cf_factory` takes only cycles: an owner calls `deposit()` with cycles attached. To get cycles
today a person needs a cycles wallet and the command line. That stops almost everyone outside ICP.

**Goal:** an owner sends ICP or ckUSDT from any wallet, and a minute later their factory balance
shows cycles. They never see the words "cycles wallet".

## What is true on chain today

Read with query calls on 2026-11-27.

| Fact | Value |
|---|---|
| ICP ledger | `ryjl3-tyaaa-aaaaa-aaaba-cai`, fee 0.0001 ICP, supports ICRC-2 |
| ckUSDT ledger | `cngnf-vqaaa-aaaar-qag4q-cai`, 6 decimals, fee 0.01 ckUSDT, supports ICRC-2 |
| ICP to cycles | 1 ICP mints about 1.52 T cycles (rate 15,197 from the cycles minting canister) |
| Factory | `deposit()` credits the caller with attached cycles. It holds no tokens |

One trillion cycles is priced at one XDR, about $1.35 to $1.37.

## Design in one paragraph

Each owner gets their own deposit address on the factory itself. The owner sends ICP or ckUSDT
there and calls `settle`. For ICP, the factory burns it into cycles through the network's minting
canister, and the cycles arrive in the factory's own balance. For ckUSDT, the factory keeps the
token and credits cycles it already holds above what it owes. Either way the owner's existing
balance (`myBalance`) goes up, and budgets, projects and top-ups work exactly as they do now.

## What changes in the factory

- **New methods:** `depositAddress`, `quote`, `settle`, `payIcp`, `refund`, `myPayments`,
  `payStats`, `sweep`, and `setPayPaused` for the operator.
- **New stored data:** a payments journal, the cached rate, the day's totals, a pause switch.
  All are added. No existing field changes or goes away, so the upgrade keeps its memory.
- **New install settings:** the fee, the caps, and the account that receives ckUSDT.
- **No timers.** Everything runs inside a call an owner makes, as today.
- **Unchanged:** `deposit()` with cycles, budgets, projects, installs, rollbacks, the reserve rule.

**A trade-off to know.** The factory controls every app it has made, and it now also handles
tokens. A fault in the new code sits in the same canister as that control. Three things limit it:
the pay switch turns payments off without touching apps; the caps bound any loss; and the payment
code never calls the code that manages apps.

## Paying with ICP

1. The owner asks for their deposit address: `depositAddress()`. It returns an ICRC-1 account (the
   factory, with a subaccount made from the owner's principal) and the older account-id form that
   exchanges use.
2. The owner sends ICP there from any wallet or exchange.
3. The owner, or anyone, calls `settle(owner, #ICP)`. The factory then:
   1. reads the balance of that subaccount and stops if it is under the minimum;
   2. writes a journal row, before any call out;
   3. sends the ICP to the cycles minting canister, marked as a top-up of the factory;
   4. tells the minting canister, which mints the cycles into the factory and says how many;
   5. adds those cycles, less the fee, to the owner's balance, and the fee to `feesTaken`;
   6. marks the journal row done.

The ICP is burned by the network when it becomes cycles. Nobody at Cafreso holds it at any point.

**If a step fails:** every step is safe to repeat. The minting canister remembers a transfer by
its block number, so asking twice mints once. The journal row records which step was reached, and
the next `settle` carries on from there.

Owners with a wallet that supports ICRC-2 can skip the deposit address: approve the factory, then
call `payIcp(amount)`. It is the same flow from step 3.2 on.

## Paying with ckUSDT

ckUSDT cannot be turned into cycles directly. The factory keeps the token as revenue and credits
cycles from its own surplus: the cycles it holds above what it owes owners and above its reserve.
`factoryStatus` already reports that number as `spendable`.

The flow matches ICP up to step 3.2. Then the factory:

1. works out the price: dollars per trillion cycles, from the ICP price (the network's exchange
   rate canister) and the ICP-to-cycles rate. The rate is cached for ten minutes;
2. checks that `spendable` covers the cycles. If not, it stops **before** taking any money;
3. moves the ckUSDT from the owner's subaccount to the factory's revenue subaccount;
4. adds the cycles to the owner's balance. The surplus shrinks by the same amount;
5. marks the journal row done.

The operator keeps the surplus topped up, as today, with a cycles deposit that needs Anthony's
yes. Swapping ckUSDT for ICP on a DEX inside the canister is left for later: it adds a dependency
on a DEX and its price.

## Price

Cycles are sold at cost plus 10% (Anthony, 2026-11-27; the strategy doc had proposed 20%). So an
owner who pays for 1.1 T receives 1.0 T. For ICP the factory keeps the rest as cycles. For ckUSDT
the margin is inside the price.

Example at today's rate: 1 ICP mints about 1.52 T, and the owner is credited about 1.38 T.

`quote(token, amount)` shows the cycles an owner would receive before they send anything.

## Limits

| Limit | Value to start |
|---|---|
| Smallest payment | 0.1 ICP, or 1 ckUSDT |
| Largest single payment | 50 ICP, or 100 ckUSDT |
| Largest total a day, all owners | 500 ICP, or 1,000 ckUSDT |
| Rate older than | 30 minutes: ckUSDT payments pause |

The caps bound the damage of a fault in the first months. They are install settings.

## Refunds

- **Before `settle`:** `refund(token)` sends the owner's deposit back to the principal that owns
  the subaccount, less the ledger fee.
- **After `settle`:** the money is cycles. `withdraw` already sends an owner's unused cycles to a
  canister they name. There is no way back to ICP or ckUSDT, and the page must say so.

## Who can do what

- **Any owner:** `depositAddress`, `quote`, `settle`, `payIcp`, `refund`, `myPayments`.
- **Anyone:** `settle` for someone else (it can only help them), `payStats`.
- **Operator:** `setPayPaused`. No method lets the operator take an owner's unsettled deposit.
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
  state : variant { started; sent; credited; refunded; failed : text };
};

depositAddress : () -> (record { account : Account; legacyAccountId : text }) query;
quote          : (Token, nat) -> (record { cycles : nat; fee : nat; rateAt : int }) query;
settle         : (principal, Token) -> (variant { ok : Payment; err : text });
payIcp         : (nat) -> (variant { ok : Payment; err : text });   // ICRC-2 route
refund         : (Token) -> (variant { ok : nat; err : text });
myPayments     : () -> (vec Payment) query;
payStats       : () -> (record { paused : bool; icpBurned : nat; ckusdtTaken : nat;
                                 payments : nat; spendable : nat }) query;
sweep          : () -> (variant { ok : nat; err : text });
setPayPaused   : (bool) -> ();                                       // operator only
```

`getApiDoc` gains a paragraph on paying, so an assistant can explain it and call `settle`.

## What the owner sees

An "Add funds" panel on Obsidian.Computer, later also in the Cafreso skill's output:

- their deposit address, with a copy button and a QR code;
- "You will receive about 1.38 T cycles for 1 ICP", from `quote`;
- after paying: the balance in cycles, and in plain terms how long that runs one small app;
- a clear line that payments cannot be turned back into ICP or ckUSDT.

## What is built (ICP only)

In `src/cf_factory/main.mo`, tested by `scripts/test_an_owner_pays_the_factory_in_icp.py` beside a
mock ICP ledger and minting canister (`scripts/replica_harness/mock_icp.mo`).

It differs from the sketch above in these ways:

- **Settings** are one optional install argument, `pay`: the ledger, the minting canister, the
  markup (1,000 = 10%) and the three ICP limits. They are stored. Until they are first given, every
  payment method says it is off. After that, an upgrade that leaves `pay` out keeps them, and a new
  value replaces them. Settings that make no sense make the upgrade fail.
- **`depositAddressFor(owner)`** is added, so an agent can read an owner their address.
- **`quote`** uses the last rate the factory saw. **`refreshRate()`** asks the minting canister, at
  most every ten minutes.
- **A payment's states** are started, sent, credited and failed. A refund before `settle` has no
  payment row, so there is no "refunded" state.
- **A deposit over the cap** is taken one cap at a time; the rest waits for the next `settle`.
- **`sweep`** comes with ckUSDT. There is nothing to sweep for ICP: it is burned.
- **The operator** for `setPayPaused` is any controller of the factory.
- **`retryPayment(id, block)`** and **`closePayment(id, why)`**, operator only. The first reopens a
  payment whose ICP was sent but not credited; the second closes one that can never finish, so the
  owner can pay or refund again. Neither moves anything: cycles are still credited only on the
  minting canister's own answer, and a ledger block serves one payment.
- **The credit is checked.** A reported amount that is not sane, or more than the factory holds
  above what it owes, is not credited.

## Review, 2026-11-27

An independent review found no way to be credited twice or without ICP being burned, and found
every declared type equal to the live ICP ledger and minting canister. Its findings, and what was
done:

| Finding | Done |
|---|---|
| A stuck payment locks the owner's deposit address, with no operator method | `retryPayment`, `closePayment` |
| A retry more than a day later dropped the record even if the transfer had happened | The record is kept and marked for the operator |
| A routine upgrade without `pay` switched off refunds and stranded open payments | Settings are stored |
| A repeated ledger answer was trusted on a new payment | A block serves one payment; timestamps never repeat |
| The credit trusted the minting canister's number | Sanity cap, and never more than the factory holds |
| `payIcp` took ICP before checks that could still fail | It checks the day's limit and open payments first |
| A dropped payment could lower the wrong day's total | Fixed |
| No check on the settings | Checked at install |
| Anyone can make the factory spend cycles on calls out | Anonymous callers are refused. A signed-in caller still can; this is as before for other methods |

Left as they are, and to know:

- **Anyone can settle for an owner.** That turns the deposit into cycles, which cannot be refunded
  as ICP. An owner who wants their ICP back must refund before anyone settles.
- **The ledger fee (0.0001 ICP) is fixed in the code.** If the ledger changes it, settle and refund
  fail until an upgrade.
- **ICP sent to the factory's main account**, not to a deposit address, cannot be recovered.
- **When the minting canister sends ICP back**, it keeps three ledger fees.
- **Stop the factory before every upgrade**, as the runbook says, so no payment is mid-call.

## Tests before anything goes near mainnet

On a local replica, with the harness in `scripts/replica_harness` (it already has a mock ledger):

1. ICP happy path: deposit, settle, the owner's balance rises by the quoted amount.
2. `settle` twice: one payment.
3. The minting step fails, then works on retry: one payment, no lost ICP.
4. ckUSDT with too little surplus: refused, and no token moves.
5. A stale rate: ckUSDT pauses, ICP still works.
6. Refund before settle returns the deposit less the fee. Refund after settle is refused.
7. Each cap is enforced, and the pay switch stops payments while apps keep working.
   (Not tested: the day's total starting again at midnight UTC.)
8. Every existing factory test still passes unchanged.
9. The new build passes `moc --stable-compatible` against the live build, and an upgrade from the
   live wasm keeps every balance, budget and project.

## Build order

1. ICP pay-in in the factory, with tests: **done on a local replica**. The mainnet upgrade waits
   for Anthony's yes, with low caps.
2. One real payment of 0.1 ICP by Anthony, end to end.
3. The "Add funds" panel.
4. ckUSDT, as a second upgrade.
5. Opt the factory in to DFINITY's connector, so an assistant can quote and settle.

## Risks

- **A stuck payment.** The journal and repeatable steps are there for this. `myPayments` shows
  the state, so support can see where one stopped.
- **The rate.** A wrong ckUSDT rate gives away cycles or overcharges. The freshness limit and the
  caps bound it.
- **The surplus runs low.** ckUSDT pauses cleanly, and ICP is unaffected.
- **More code in the canister that controls every app.** See the trade-off above.
- **Taking payment in a stablecoin.** This is selling hosting credit, and it is not refundable in
  kind. It belongs on the list for the lawyer's review in the plan.
- **Card payment** is not covered. It needs a partner and comes later.

## Decisions

| Decision | Answer |
|---|---|
| Separate canister, or inside the factory | Inside the factory (Anthony, 2026-11-27) |
| Accept ckUSDC | No (Anthony, 2026-11-27) |
| The fee | Cost plus 10% (Anthony, 2026-11-27) |
| ckUSDT from the factory's surplus first, a DEX swap later | Open |
| The starting caps in the table above | Open |
| Where collected ckUSDT goes: the reserve account today, the treasury canister once it is live | Open |
