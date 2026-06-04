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

import { transfer as icrcTransfer, TOKENS } from '$lib/api/icrc1.js';
import { recordOrder, getTreasury, listMyOrders } from '$lib/api/store.js';
import { createStripeSession, savePendingStripeOrder } from '$lib/api/stripe.js';
import { fleetApiUrl } from '$lib/api/fleetClient.js';
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

/** Subscribe by paying in ICP. Transfers the ICP-equivalent of the plan's USD
 *  price to the treasury, then records the order on-chain. Returns
 *  { ok, plan, block } or { err }. After this, the success path should call the
 *  fleet bridge (set-plan) — see notifyFleet(). */
export async function subscribeWithIcp(planId) {
  const plan = PLANS[planId];
  if (!plan || plan.usd <= 0) return { err: 'Pick a paid plan.' };

  // HQ revenue → admin principal (falls back to the Pages store treasury).
  const treasury = HQ_TREASURY || await getTreasury();
  if (!treasury) return { err: 'Treasury not configured — contact support.' };

  const icpAmount = usdToIcp(plan.usd);
  if (icpAmount == null) return { err: 'ICP price unavailable — try again in a moment.' };

  // 1. Pay: ICRC-1 transfer user → treasury (authed II identity).
  const pay = await icrcTransfer({
    tokenKey: 'ICP',
    toPrincipalText: treasury,
    amount: icpAmount,
    memoText: `cafresohq:${planId}`,
  });
  if (pay.err) return { err: `Payment failed: ${pay.err}` };

  // 2. Record on-chain: order ledger, buyer = caller principal (unforgeable).
  const rec = await recordOrder({
    items: [{ slug: plan.slug, qty: 1, priceNanas: 0, price: plan.usd }],
    shipping: {},
    paidBlock: pay.ok,            // ledger block index = receipt
    paymentMethod: 'icp',
  });
  if (rec.err) {
    // Payment went through but recording failed — surface block for support.
    return { err: `Paid (block ${pay.ok}) but order record failed: ${rec.err}. Save this block #.`, block: pay.ok };
  }
  return { ok: true, plan: planId, block: pay.ok, order: rec.ok };
}

/** Subscribe by card via the existing Stripe Worker. Redirects the browser to
 *  Stripe Checkout; the /success page records the order + notifies the fleet. */
export async function subscribeWithCard(planId, { successUrl, cancelUrl }) {
  const plan = PLANS[planId];
  if (!plan || plan.usd <= 0) return { err: 'Pick a paid plan.' };
  const orderId = `hq-${planId}-${Date.now()}`;
  savePendingStripeOrder({
    orderId,
    items: [{ name: `CafresoHQ ${plan.label}`, price: plan.usd, qty: 1 }],
    shipping: {},
  });
  const session = await createStripeSession({
    items: [{ name: `CafresoHQ ${plan.label} (monthly)`, price: plan.usd, qty: 1 }],
    shipping: {},
    orderId,
    successUrl,
    cancelUrl,
  });
  if (session.error) return { err: session.error };
  if (session.url) { window.location.href = session.url; return { ok: true, redirecting: true }; }
  return { err: 'No checkout URL returned.' };
}

/** Tell the fleet to apply the user's plan to their container (idle policy +
 *  capability) — proven by an ON-CHAIN plan token.
 *
 *  We mint the token from the cafresoai_keys canister, which reads the paid
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
