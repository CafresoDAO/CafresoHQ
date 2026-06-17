/**
 * stripe.js — thin client for the Cafreso Stripe Cloudflare Worker.
 *
 * The Worker holds the STRIPE_SECRET_KEY and creates Stripe Checkout Sessions
 * server-side so the secret never touches the browser. After the user pays on
 * Stripe's hosted page, they are redirected back to /success where we record
 * the order on-chain using their live Internet Identity.
 *
 * The oracle is self-hosted on the gateway VM (oci-fleet/stripe-oracle),
 * fronted by Caddy at https://hq.cafreso.com/stripe/*. Set
 *   PUBLIC_STRIPE_WORKER_URL=https://hq.cafreso.com/stripe/session
 * (a Cloudflare Worker twin lives in docs/stripe-worker.js as a fallback).
 */

const WORKER_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.PUBLIC_STRIPE_WORKER_URL) ||
  'https://hq.cafreso.com/stripe/session';

/**
 * Ask the Worker to create a Stripe Checkout Session. The Worker prices the
 * session server-side from the plan in `metadata` (never a client price) and
 * stamps `metadata` onto the session + payment_intent so its /webhook can
 * confirm the on-chain order. See docs/stripe-worker.js.
 *
 * @param {{
 *   metadata: { icOrderId: string, principal: string, plan: string },
 *   successUrl: string,
 *   cancelUrl: string
 * }} payload
 * @returns {Promise<{url: string} | {error: string}>}
 */
export async function createStripeSession(payload) {
  try {
    const res = await fetch(WORKER_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!res.ok) {
      const text = await res.text();
      return { error: `Worker error ${res.status}: ${text}` };
    }
    return res.json();
  } catch (err) {
    return { error: `Could not reach payment server: ${err.message}` };
  }
}

/** Key used to stash the pending Stripe order in sessionStorage. */
export const STRIPE_PENDING_KEY = 'cafreso_stripe_pending';

/**
 * Save the pending order to sessionStorage before redirecting to Stripe.
 * The success page reads this back once Stripe redirects the user home.
 */
export function savePendingStripeOrder({ orderId, items, shipping }) {
  try {
    sessionStorage.setItem(
      STRIPE_PENDING_KEY,
      JSON.stringify({ orderId, items, shipping, ts: Date.now() })
    );
  } catch (_) {
    // sessionStorage unavailable (private-mode edge case) — success page
    // falls back to showing a generic card-payment confirmation.
  }
}

/** Read and remove the pending order from sessionStorage. */
export function consumePendingStripeOrder() {
  try {
    const raw = sessionStorage.getItem(STRIPE_PENDING_KEY);
    if (!raw) return null;
    sessionStorage.removeItem(STRIPE_PENDING_KEY);
    return JSON.parse(raw);
  } catch (_) {
    return null;
  }
}
