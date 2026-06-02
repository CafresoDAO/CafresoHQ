# CafresoHQ Billing — Reuse the CafresoPages Rails (don't rebuild)

> We already own a production payment system in **CafresoPages** that charges in
> **Stripe (fiat) OR ICRC-1 tokens (ICP, ckUNI, sGLDT, $nanas)** and records every
> payment on-chain against the buyer's **verified Internet Identity principal**.
> CafresoHQ provisions containers against that *same principal*. So billing for
> the SaaS is mostly **wiring, not building.** This supersedes the "build Stripe
> from scratch" step in SAAS_MVP_PLAN.md.

---

## 1. What CafresoPages already gives us (verified in code)

| Capability | Where | What it does |
|---|---|---|
| **Stripe Checkout** | `src/lib/api/stripe.js` → Cloudflare Worker | Worker holds `STRIPE_SECRET_KEY`, creates a hosted Checkout Session, redirects to `/success`. Secret never touches the browser. |
| **ICRC-1 token pay** | `src/lib/api/icrc1.js` `transfer()` | Authed `icrc1_transfer` from the signed-in II identity to a treasury principal. Supports **ICP, ckUNI, sGLDT, $nanas**. Returns the ledger **block index** as receipt. |
| **On-chain order ledger** | `src/lib/api/store.js` `recordOrder()` → `GlobalOrder.mo` | Records `{buyer=principal (unforgeable), itemsJson, totalNanas, status, paidBlock, paymentMethod}`. **Starts "pending"; admin `confirmOrder(id, blockIndex)` flips to "paid" after verifying the transfer.** |
| **Treasury** | `store.js` getTreasury/setTreasury | The principal that receives ICRC-1 payments. |
| **Audit trail** | `AuditTrail.svelte`, `BurnReceipt.mo` | Existing UI + on-chain receipts. |

**The crucial property:** a payment is already tied to a **verified ICP principal**
(`GlobalOrder.buyer = Principal.toText(caller)` — server-set, unforgeable). That
principal is the *exact same key* CafresoHQ uses to provision/look up a container
(`slug = sha256(principal)`). **Payment identity == container identity, for free.**

---

## 2. The integration (subscription on top of the order ledger)

We don't need a new payment system — we need a **subscription/plan concept** keyed
to the principal, fed by the existing payment flows. Two clean options:

### Option A (fastest, on-chain native) — "subscription order" + plan field
1. Add a tiny **`Subscription` record** to the appservice canister (mirror
   `GlobalOrder`): `{ principal, plan, status, paidBlock, paymentMethod,
   currentPeriodEnd, timestamp }`. SK `sub#<principal>`.
2. **Checkout reuses existing rails:**
   - **Token pay:** user clicks "Subscribe — 250 $nanas/mo" → `icrc1.transfer()` to
     treasury → `recordSubscription(plan, block, 'nanas')` (mirror `recordOrder`).
     Canister verifies the block on the ledger (it already has the pattern) →
     `status='active', currentPeriodEnd=now+30d`.
   - **Stripe pay:** existing `createStripeSession()` with the plan as the line item
     → `/success` → `recordSubscription(plan, 0, 'stripe')` → admin/worker
     `confirmSubscription` (same pattern as `confirmOrder`).
3. **CafresoHQ reads the plan from the canister**, not its own DB. The shell already
   talks to ICP — one query `getSubscription(principal)` → `{plan, active}`.
4. **Provision/enforce on that plan** — which we already wired:
   `fleet-manager set-plan <principal> <plan>` (the webhook/worker calls it, or the
   fleet-api polls the canister). reap-idle already enforces free=20m / pro=60m /
   always-on=exempt.

### Option B (even less new code) — treat a subscription as a recurring "order"
- Reuse `recordOrder` verbatim with `items=[{slug:'cafresohq-pro', priceNanas:250}]`.
  A subscription = the most recent **paid** order with a `cafresohq-*` slug whose
  `timestampUpdated` is within 30 days. `getPlan(principal)` = scan that user's
  orders. Zero new canister types; ship today. (Downgrade to Option A's dedicated
  record once volume justifies it.)

**Recommendation:** ship **Option B** for the MVP (reuses `recordOrder`/`confirmOrder`
as-is, no Motoko changes), migrate to **Option A** when you want clean renewals.

---

## 3. End-to-end flow (token OR fiat → working HQ)

```
User in ai.cafreso.com shell, signed in with II (principal P)
   │
   ├─ picks plan (Pro $9 / 250 $nanas)  ─ pay with:
   │     • $nanas/ICP →  icrc1.transfer(P → treasury)  → block #
   │     • card       →  createStripeSession()  → Stripe → /success
   │
   ├─ recordOrder({items:[cafresohq-pro], paidBlock:#, paymentMethod})  (existing)
   │     → GlobalOrder {buyer:P, status:pending→paid}   (admin/worker confirmOrder)
   │
   ├─ fleet hook: set-plan P pro     (already built)
   │     → registry plan=pro · pushes capability=full to container
   │
   └─ provision/start P's container (reuses existing flow)
         → reap-idle keeps free users cheap, pro warm 60m, always-on exempt
```

Everything left of "fleet hook" **already exists in CafresoPages**. Everything right
of it **we already built this session.** The integration is the arrow between them.

---

## 4. Why this is a strong position (the entrepreneur read)

- **Two payment rails, one of them crypto-native.** Stripe for normies, **$nanas/ICP
  for the on-chain audience** — and paying in **your own $nanas token creates token
  demand/utility** (subscriptions become a $nanas sink → supports tokenomics in
  `docs/strategy/04-sns-tokenomics-decisions.md`).
- **No new PCI/secret surface.** Stripe secret stays in the existing Worker; we never
  touch cards. Token payments are non-custodial (user→treasury direct).
- **Identity = payment = compute**, all the same II principal. No account-linking,
  no email/password, no Stripe-customer-↔-user mapping table. This is the part most
  SaaS spend weeks on; ICP gives it to us free.
- **Profitable model intact:** plan gates the container behavior we built (idle-stop,
  capability). $9 Pro on ~$1.40 COGS = ~84% margin; $nanas payments cost us ~$0 to
  accept (just a ledger fee).

---

## 5. Concrete steps (replaces the "Stripe from scratch" days in SAAS_MVP_PLAN)

1. **Add `cafresohq-free/pro/always-on` as products** in the existing store catalog
   (priceNanas + a Stripe price). ~30 min — it's the existing product system.
2. **Subscribe UI** in the HQ shell: reuse `icrc1.transfer` + `createStripeSession`
   + `recordOrder`. A "Plans" page, not a new payment stack. ~1 day.
3. **`getPlan(principal)`** helper (Option B: scan paid `cafresohq-*` orders < 30d).
   ~half day.
4. **Bridge plan → fleet:** the success/confirm path calls
   `fleet-manager set-plan <principal> <plan>` (via fleet-api endpoint). We already
   built `set-plan`. ~half day.
5. **Gate provision + capability on plan** (free until paid). ~half day.
6. **Renewal/expiry:** cron checks `currentPeriodEnd`; lapsed → `set-plan free`
   (auto-downgrades to idle-20m/lite). Reuses reap-idle. ~half day.

**~3 days instead of the ~1 week** estimated for greenfield Stripe — because the
payment rails, on-chain receipts, treasury, and identity are already production code
in CafresoPages. **This is exactly why owning CafresoPages matters.**

---

## 6. Open items to confirm with you
- **Treasury principal** for CafresoHQ subscription revenue — same as Pages treasury, or a dedicated one?
- **$nanas price per plan** (e.g. Pro = 250 $nanas ≈ $9?) — sets the token sink rate.
- **Stripe Worker** — reuse the same Worker with a CafresoHQ price, or a second Worker? (Reuse is simplest.)
