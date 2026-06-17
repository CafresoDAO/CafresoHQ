/**
 * stripe.js — thin client for the Cafreso Stripe Cloudflare Worker.
 *
 * The Worker holds the STRIPE_SECRET_KEY and creates Stripe Checkout Sessions
 * server-side so the secret never touches the browser. After the user pays on
 * Stripe's hosted page, they are redirected back to /success where we record
 * the order on-chain using their live Internet Identity.
 *
 * To set up your Worker:
 *   1. Go to workers.cloudflare.com → Create Worker
 *   2. Paste the worker code from docs/stripe-worker.js
 *   3. Add secret: STRIPE_SECRET_KEY = sk_live_...
 *   4. Set WORKER_URL below (or in .env as PUBLIC_STRIPE_WORKER_URL)
 */

const WORKER_URL =
  (typeof import.meta !== 'undefined' && import.meta.env?.PUBLIC_STRIPE_WORKER_URL) ||
  'https://cafreso-stripe.YOUR-SUBDOMAIN.workers.dev';

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
