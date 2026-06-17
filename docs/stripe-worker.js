/**
 * ============================================================================
 *  CafresoHQ Stripe Worker — card payments oracle (Cloudflare Worker)
 * ============================================================================
 *
 *  Card money lives off-chain in Stripe, so the order canister (bek5d) can't
 *  observe a card payment directly. This Worker is the trusted ORACLE:
 *
 *    POST /session  (from the browser)
 *        → creates a Stripe Checkout Session priced from PLAN_PRICES (NOT the
 *          client) and stamps {icOrderId, principal, plan} into its metadata.
 *
 *    POST /webhook  (from Stripe)
 *        → verifies Stripe's signature, and on `checkout.session.completed`
 *          (payment_status=paid) calls bek5d.confirmCardOrder(icOrderId,
 *          amount_total_cents) as the ORACLE identity. The canister still
 *          enforces amount >= the plan's on-chain USD price, so a tampered
 *          session can't buy a tier cheaply — the oracle is only trusted to
 *          relay the true, Stripe-signed amount.
 *
 *  The flow only confirms; it never moves crypto. Worst case if the oracle key
 *  leaks is free plans (not theft) — keep ORACLE_SEED_HEX in Cloudflare secrets.
 *
 * ----------------------------------------------------------------------------
 *  DEPLOY (wrangler)
 * ----------------------------------------------------------------------------
 *  1. npm i -g wrangler && wrangler login
 *  2. Project deps:  npm i @dfinity/agent @dfinity/identity @dfinity/candid @dfinity/principal
 *  3. wrangler.toml:
 *         name = "cafreso-stripe"
 *         main = "stripe-worker.js"
 *         compatibility_date = "2024-09-23"
 *         compatibility_flags = ["nodejs_compat"]
 *         [vars]
 *         IC_HOST = "https://icp0.io"
 *         INDEX_CANISTER_ID = "bek5d-2qaaa-aaaab-agqrq-cai"
 *  4. Generate the ORACLE identity + its principal (run once, locally):
 *         node -e "const{Ed25519KeyIdentity}=require('@dfinity/identity');const s=require('crypto').randomBytes(32);const id=Ed25519KeyIdentity.generate(s);console.log('SEED_HEX=',s.toString('hex'));console.log('PRINCIPAL=',id.getPrincipal().toText())"
 *  5. Secrets:
 *         wrangler secret put STRIPE_SECRET_KEY        # sk_test_… then sk_live_…
 *         wrangler secret put STRIPE_WEBHOOK_SECRET    # whsec_… (from step 7)
 *         wrangler secret put ORACLE_SEED_HEX          # the SEED_HEX from step 4
 *  6. wrangler deploy   →  note the workers.dev URL.
 *  7. Stripe dashboard → Developers → Webhooks → Add endpoint:
 *         URL: <worker-url>/webhook   Events: checkout.session.completed
 *         Copy the signing secret into STRIPE_WEBHOOK_SECRET (step 5), redeploy.
 *  8. ON-CHAIN: an admin authorises this Worker's PRINCIPAL (step 4) on bek5d:
 *         dfx canister --network ic call index setOraclePrincipal '(principal "<PRINCIPAL>")' --identity <admin>
 *  9. Frontend: set PUBLIC_STRIPE_WORKER_URL=<worker-url>, redeploy.
 * 10. Test in Stripe TEST mode (card 4242 4242 4242 4242), confirm the order
 *     flips to "paid" on-chain and the plan applies. THEN flip
 *     PUBLIC_CARD_PAYMENTS=on and switch STRIPE_SECRET_KEY to sk_live_.
 * ============================================================================
 */

import { Actor, HttpAgent } from '@dfinity/agent';
import { Ed25519KeyIdentity } from '@dfinity/identity';
import { IDL } from '@dfinity/candid';

// Plan prices in USD cents — MUST match the canister's planPriceUsdCents. The
// Worker prices the Stripe session from THIS map (never the client), and the
// canister independently re-checks amount_total >= its own price.
const PLAN_PRICES = {
  'cafresohq-pro': 900,
  'cafresohq-always-on': 2900,
};

// Origins allowed to create sessions (the browser shell). Tighten as needed.
const ALLOWED_ORIGINS = ['https://ai.cafreso.com', 'https://cafreso.com'];

// Minimal candid for the one method we call. `ok` is decoded loosely (record
// subtyping ignores the GlobalOrder fields we don't need).
const idlFactory = ({ IDL }) =>
  IDL.Service({
    // (orderId, amountPaidCents, stripeRef) — stripeRef is the session id, which
    // the canister binds the confirmation to (reconciliation + replay bound).
    confirmCardOrder: IDL.Func(
      [IDL.Int, IDL.Nat, IDL.Text],
      [IDL.Variant({ ok: IDL.Record({}), err: IDL.Text })],
      []
    ),
  });

function corsHeaders(origin) {
  const allow = ALLOWED_ORIGINS.includes(origin) ? origin : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': allow,
    'Access-Control-Allow-Methods': 'POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Vary': 'Origin',
  };
}

function json(body, status, extra) {
  return new Response(JSON.stringify(body), {
    status: status || 200,
    headers: { 'Content-Type': 'application/json', ...(extra || {}) },
  });
}

// ── Stripe webhook signature (manual HMAC-SHA256 via Web Crypto) ───────────
function timingSafeEqualHex(a, b) {
  if (typeof a !== 'string' || typeof b !== 'string' || a.length !== b.length) return false;
  let out = 0;
  for (let i = 0; i < a.length; i++) out |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return out === 0;
}

async function verifyStripeSignature(rawBody, sigHeader, secret) {
  if (!sigHeader || !secret) return false;
  const parts = Object.fromEntries(
    sigHeader.split(',').map((kv) => {
      const i = kv.indexOf('=');
      return [kv.slice(0, i).trim(), kv.slice(i + 1).trim()];
    })
  );
  const t = parts.t;
  const v1 = parts.v1;
  if (!t || !v1) return false;
  // Reject events older/newer than 5 minutes (replay protection).
  if (Math.abs(Date.now() / 1000 - Number(t)) > 300) return false;
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const sig = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(`${t}.${rawBody}`));
  const expected = [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, '0')).join('');
  return timingSafeEqualHex(expected, v1);
}

// ── Oracle actor (calls bek5d.confirmCardOrder) ────────────────────────────
function oracleActor(env) {
  const seed = Uint8Array.from((env.ORACLE_SEED_HEX || '').match(/.{1,2}/g).map((h) => parseInt(h, 16)));
  const identity = Ed25519KeyIdentity.generate(seed);
  const agent = new HttpAgent({ host: env.IC_HOST || 'https://icp0.io', identity });
  // Mainnet only — do NOT fetchRootKey in production.
  return Actor.createActor(idlFactory, { agent, canisterId: env.INDEX_CANISTER_ID });
}

// ── POST /session — create a Stripe Checkout Session ───────────────────────
async function handleSession(request, env, origin) {
  let body;
  try { body = await request.json(); } catch (_) { return json({ error: 'bad json' }, 400, corsHeaders(origin)); }
  const meta = body.metadata || {};
  const plan = meta.plan;
  const icOrderId = meta.icOrderId;
  const principal = meta.principal || '';
  const priceCents = PLAN_PRICES[plan];
  if (!plan || priceCents == null) return json({ error: 'unknown plan' }, 400, corsHeaders(origin));
  if (!icOrderId || !/^\d+$/.test(String(icOrderId))) return json({ error: 'bad order id' }, 400, corsHeaders(origin));
  if (!env.STRIPE_SECRET_KEY) return json({ error: 'worker not configured' }, 503, corsHeaders(origin));

  const p = new URLSearchParams();
  p.append('mode', 'payment');
  p.append('success_url', body.successUrl || `${origin}/hq/plans?paid=${plan}&order=${icOrderId}`);
  p.append('cancel_url', body.cancelUrl || `${origin}/hq/plans`);
  p.append('client_reference_id', String(icOrderId));
  p.append('line_items[0][quantity]', '1');
  p.append('line_items[0][price_data][currency]', 'usd');
  p.append('line_items[0][price_data][unit_amount]', String(priceCents)); // server-set price
  p.append('line_items[0][price_data][product_data][name]', `CafresoHQ ${plan} (monthly)`);
  // metadata on BOTH the session and the payment_intent so the webhook can read it
  p.append('metadata[icOrderId]', String(icOrderId));
  p.append('metadata[principal]', principal);
  p.append('metadata[plan]', plan);
  p.append('payment_intent_data[metadata][icOrderId]', String(icOrderId));
  p.append('payment_intent_data[metadata][plan]', plan);

  const r = await fetch('https://api.stripe.com/v1/checkout/sessions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`, 'Content-Type': 'application/x-www-form-urlencoded' },
    body: p,
  });
  const session = await r.json();
  if (!r.ok) return json({ error: session?.error?.message || 'stripe error' }, 502, corsHeaders(origin));
  return json({ url: session.url }, 200, corsHeaders(origin));
}

// ── POST /webhook — Stripe → confirm the order on-chain ────────────────────
async function handleWebhook(request, env) {
  const raw = await request.text();
  const ok = await verifyStripeSignature(raw, request.headers.get('stripe-signature'), env.STRIPE_WEBHOOK_SECRET);
  if (!ok) return new Response('bad signature', { status: 400 });

  let event;
  try { event = JSON.parse(raw); } catch (_) { return new Response('bad json', { status: 400 }); }

  // Only act on a completed, paid checkout that carries our order id. Shop/store
  // sessions (no icOrderId) are ignored → the Pages store flow is untouched.
  if (event.type !== 'checkout.session.completed') return new Response('ignored', { status: 200 });
  const session = event.data?.object || {};
  const icOrderId = session.metadata?.icOrderId;
  if (!icOrderId) return new Response('not a plan order', { status: 200 });
  if (session.payment_status !== 'paid') return new Response('not paid', { status: 200 });

  const amountCents = Number(session.amount_total); // already in cents, USD
  if (!Number.isFinite(amountCents) || amountCents <= 0) return new Response('bad amount', { status: 200 });

  try {
    const actor = oracleActor(env);
    const res = await actor.confirmCardOrder(BigInt(icOrderId), BigInt(Math.round(amountCents)), session.id || '');
    if ('ok' in res) return new Response('confirmed', { status: 200 });
    // Business rejection (e.g. amount < price, wrong status) → do NOT retry.
    console.log('confirmCardOrder rejected:', res.err);
    return new Response('rejected: ' + res.err, { status: 200 });
  } catch (e) {
    // Transient IC failure → 500 so Stripe retries (its retry window ~3 days
    // is the outage-recovery path).
    console.log('confirmCardOrder error:', String(e));
    return new Response('ic error', { status: 500 });
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = request.headers.get('Origin') || ALLOWED_ORIGINS[0];
    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(origin) });
    if (request.method === 'POST' && url.pathname === '/webhook') return handleWebhook(request, env);
    if (request.method === 'POST') return handleSession(request, env, origin); // / or /session
    return new Response('CafresoHQ Stripe Worker', { status: 200 });
  },
};
