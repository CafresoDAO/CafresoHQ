// hqPlans.js — CafresoHQ subscription billing.
//
// Reuses the existing CafresoPages payment rails instead of building new ones:
//   • ICP payment   → icrc1.transfer()  (this session: ICP only; $nanas later)
//   • Card payment  → createStripeSession()  (existing Cloudflare Worker)
//   • On-chain proof → recordOrder()  (GlobalOrder ledger; buyer = II principal)
//
// A subscription is modeled (MVP, "Option B") as the most recent PAID order with
// a `cafresohq-<plan>` slug whose updatedAt is within PLAN_PERIOD_DAYS. No new
// canister types — ships on the order ledger we already have. The verified
// buyer principal == the principal CafresoHQ provisions a container against, so
// payment identity and compute identity are the same key.
//
// Pricing: ICP-first. USD list price is converted to ICP at the live rate from
// stores/prices.js so the catalog stays in USD but users pay in ICP today.

import { approve, getFee } from '$lib/api/icrc1.js';
import { listMyOrders, purchasePlanIcp, createCardOrder, getPlanPriceUsdCents, INDEX_CANISTER_ID } from '$lib/api/store.js';
import { createStripeSession } from '$lib/api/stripe.js';
import { fleetApiUrl } from '$lib/api/fleetClient.js';
import { principalText } from '$lib/stores/auth.js';
import { get } from 'svelte/store';
import { prices } from '$lib/stores/prices.js';

export const PLAN_PERIOD_DAYS = 30;

// CafresoHQ subscription revenue goes to the admin principal (override the Pages
// store treasury). Set via PUBLIC_HQ_TREASURY for a different env if needed.
export const HQ_TREASURY =
  (typeof import.meta !== 'undefined' && import.meta.env?.PUBLIC_HQ_TREASURY) ||
  'rc62u-qypnw-bbkkp-d56wk-tnzaq-vwhi2-cqqay-q56hw-gsqbp-6wegl-jae';

// The three SaaS tiers (see docs/SAAS_MVP_PLAN.md). usd is the list price;
// slug is the catalog/order key the fleet maps to a plan. 'free' needs no
// payment — it's the default a principal gets before any paid order.
export const PLANS = {
  free:        { id: 'free',        slug: 'cafresohq-free',       label: 'Free',       usd: 0 },
  pro:         { id: 'pro',         slug: 'cafresohq-pro',        label: 'Pro',        usd: 9 },
  'always-on': { id: 'always-on',   slug: 'cafresohq-always-on',  label: 'Always-On',  usd: 29 },
};

const SLUG_TO_PLAN = Object.fromEntries(
  Object.values(PLANS).map((p) => [p.slug, p.id])
);

/** Convert a USD list price to whole-unit ICP at the live rate. Returns null if
 *  the ICP price isn't loaded yet (caller should ask the user to retry). */
export function usdToIcp(usd) {
  const icpUsd = Number(get(prices)?.ICP);
  if (!Number.isFinite(icpUsd) || icpUsd <= 0) return null;
  return usd / icpUsd;
}

/** Read the caller's current plan from the on-chain order ledger.
 *  Returns { plan, activeUntil, order } — 'free' if no active paid order. */
export async function getPlan() {
  try {
    const orders = await listMyOrders();
    const cutoff = Date.now() - PLAN_PERIOD_DAYS * 24 * 60 * 60 * 1000;
    // newest paid cafresohq-* order still within the period wins
    const active = (orders || [])
      .filter((o) => o.status === 'paid')
      .map((o) => {
        const item = (o.items || []).find((it) => SLUG_TO_PLAN[it.slug]);
        return item ? { plan: SLUG_TO_PLAN[item.slug], updatedAt: o.updatedAt, order: o } : null;
      })
      .filter(Boolean)
      .filter((x) => x.updatedAt >= cutoff)
      .sort((a, b) => b.updatedAt - a.updatedAt)[0];
    if (!active) return { plan: 'free', activeUntil: null, order: null };
    return {
      plan: active.plan,
      activeUntil: active.updatedAt + PLAN_PERIOD_DAYS * 24 * 60 * 60 * 1000,
      order: active.order,
    };
  } catch (e) {
    console.warn('[hqPlans] getPlan failed', e);
    return { plan: 'free', activeUntil: null, order: null };
  }
}

/** Subscribe by paying in ICP — trustless, fully on-chain (no admin, no oracle).
 *  The buyer APPROVES the index canister to spend the fixed plan price, then the
 *  canister pulls exactly that price (icrc2_transfer_from buyer → HQ treasury)
 *  and records a PAID order in one shot. The ledger debit is the proof, so the
 *  resulting order is immediately `paid` and mintPlanToken accepts it.
 *  Returns { ok, plan, order } or { err }. The success path calls notifyFleet(). */
export async function subscribeWithIcp(planId) {
  const plan = PLANS[planId];
  if (!plan || plan.usd <= 0) return { err: 'Pick a paid plan.' };

  // The canister prices plans in USD cents and charges the live-rate ICP at
  // purchase (via the on-chain XRC oracle). We approve a margined ICP estimate
  // from the live display rate so the canister's exact pull always fits; the
  // canister decides the real amount, and any leftover allowance auto-expires.
  const cents = await getPlanPriceUsdCents(plan.slug);
  if (cents == null) return { err: 'Plan pricing not available yet — try again shortly.' };
  const usd = Number(cents) / 100;

  const icpUsd = Number(get(prices)?.ICP);
  if (!Number.isFinite(icpUsd) || icpUsd <= 0) return { err: 'ICP price unavailable — try again in a moment.' };
  const icpEstimate = usd / icpUsd;                       // whole ICP at the live rate

  // 1. Approve estimate + 25% margin + fee (covers rate divergence/movement).
  const fee = (await getFee('ICP')) ?? 10_000n;
  const approveE8s = BigInt(Math.ceil(icpEstimate * 1.25 * 1e8)) + BigInt(fee);
  const ap = await approve({
    tokenKey: 'ICP',
    spenderPrincipalText: INDEX_CANISTER_ID,
    amount: approveE8s,
  });
  if (ap.err) return { err: `Approval failed: ${ap.err}` };

  // 2. The canister reads the live rate, pulls the EXACT matching ICP, and
  //    records the paid order. A buyer can never underpay (the canister sets the
  //    amount from XRC) or pay someone else (it pulls to the configured HQ
  //    treasury); a double-submit returns the existing paid order (idempotent).
  const res = await purchasePlanIcp(plan.slug);
  if (res.err) {
    // Best-effort: revoke the leftover allowance so no standing pull
    // authorization lingers if the purchase didn't complete.
    approve({ tokenKey: 'ICP', spenderPrincipalText: INDEX_CANISTER_ID, amount: 0n }).catch(() => {});
    return { err: res.err };
  }
  return { ok: true, plan: planId, order: res.ok };
}

/** Subscribe by card via the Stripe Worker. Records a PENDING order on-chain
 *  FIRST (so the webhook oracle has a real order id to confirm), then redirects
 *  to Stripe Checkout. On return, handleStripeReturn polls until the webhook has
 *  flipped the order to "paid", then applies the plan. */
export async function subscribeWithCard(planId, { successUrl, cancelUrl }) {
  const plan = PLANS[planId];
  if (!plan || plan.usd <= 0) return { err: 'Pick a paid plan.' };

  // 1. On-chain pending order — buyer principal is unforgeable, slug allowlisted.
  const rec = await createCardOrder(plan.slug);
  if (rec.err) return { err: rec.err };
  const icOrderId = rec.ok.id;

  // 2. Stripe Checkout session. The Worker prices it server-side from the plan
  //    (not us) and stamps the order id into metadata; the canister re-checks
  //    the paid amount on confirm. successUrl carries ?paid + &order so the
  //    return handler knows which order to poll.
  const session = await createStripeSession({
    metadata: { icOrderId: String(icOrderId), principal: get(principalText) || '', plan: plan.slug },
    successUrl: `${successUrl}${successUrl.includes('?') ? '&' : '?'}order=${icOrderId}`,
    cancelUrl,
  });
  if (session.error) return { err: session.error };
  if (session.url) { window.location.href = session.url; return { ok: true, redirecting: true }; }
  return { err: 'No checkout URL returned.' };
}

/** Poll the on-chain order ledger until `orderId` is "paid" (the Stripe webhook
 *  oracle flips it) or the timeout elapses. Returns true if paid. */
export async function waitForOrderPaid(orderId, { pollMs = 3000, timeoutMs = 90000, signal } = {}) {
  const id = Number(orderId);
  const isPaid = (orders) => (orders || []).some((o) => Number(o.id) === id && o.status === 'paid');
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (signal?.aborted) return false;
    if (isPaid(await listMyOrders())) return true;
    await new Promise((r) => setTimeout(r, pollMs));
  }
  return signal?.aborted ? false : isPaid(await listMyOrders());
}

/** Tell the fleet to apply the user's plan to their container (idle policy +
 *  capability) — proven by an ON-CHAIN plan token.
 *
 *  We mint the token from the cafresohq_keys canister, which reads the paid
 *  order (`orderId`) from the unforgeable ledger, confirms it belongs to the
 *  caller + is paid + within the period, and HMAC-signs the tier. The fleet
 *  applies the plan only on a valid token, so the client can't self-assign.
 *
 *  ICP orders are marked paid on-chain immediately → this works right away.
 *  Card orders (no ICP block) stay pending until confirmed on-chain, so the
 *  mint throws and we return { ok:false }; the plan applies once the order is
 *  paid (Stripe→confirmOrder) and the fleet reconciles.
 *
 *  @param {number|bigint} orderId  on-chain order id (from recordOrder)
 *  @returns {Promise<{ok:boolean, plan?:string, reason?:string}>}
 */
export async function notifyFleet(orderId) {
  if (orderId == null) return { ok: false, reason: 'no order id' };
  try {
    const { getKeysActor } = await import('$lib/api/keysActor.js');
    const actor = await getKeysActor();
    let proof;
    try {
      proof = await actor.mintPlanToken(BigInt(orderId));
    } catch (e) {
      return { ok: false, reason: String(e?.message || e) };
    }
    const base = (get(fleetApiUrl) || '').replace(/\/+$/, '');
    const r = await fetch(base + '/fleet/set-plan', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ token: proof.token }),
    });
    return { ok: r.ok, plan: proof.plan };
  } catch (e) {
    return { ok: false, reason: String(e?.message || e) };
  }
}
