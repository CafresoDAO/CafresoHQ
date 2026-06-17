/**
 * ============================================================================
 *  CafresoHQ Stripe Oracle — card-payment confirmer (self-hosted Node service)
 * ============================================================================
 *
 *  This is the OCI-hosted twin of docs/stripe-worker.js. Instead of a
 *  Cloudflare Worker it runs as a tiny Node service on the gateway VM behind
 *  Caddy (no new vendor / login). The money logic is IDENTICAL and was
 *  adversarially reviewed — only the runtime shell changed:
 *
 *    - The Cloudflare `export default { fetch(request, env) }` handler is kept
 *      VERBATIM as `handleRequest(request, env)`. Node 20 provides global
 *      `fetch`, `Request`, `Response`, `Headers`, `crypto.subtle`, `TextEncoder`,
 *      so the Fetch-API handler code runs unchanged.
 *    - A small `http.createServer` adapter (bottom of file) turns each Node
 *      request into a Fetch `Request`, calls `handleRequest`, and writes the
 *      `Response` back. The raw body bytes are preserved so Stripe's HMAC
 *      signature check verifies exactly as on Cloudflare.
 *    - `env` is `process.env` (loaded by systemd from
 *      /etc/cafresoai/stripe-oracle.env).
 *
 *  Caddy routes  https://hq.cafreso.com/stripe/*  →  127.0.0.1:8788  (prefix
 *  stripped), so this service still sees  POST /session  and  POST /webhook.
 *
 *  Flow:
 *    POST /session  (browser)  → create a Stripe Checkout Session priced from
 *        PLAN_PRICES (never the client) with {icOrderId, principal, plan} in
 *        the session metadata.
 *    POST /webhook  (Stripe)   → verify Stripe's signature, and on a paid
 *        checkout.session.completed call bek5d.confirmCardOrder as the ORACLE
 *        identity. The canister independently re-checks amount >= the plan's
 *        on-chain USD price, so a tampered session can't buy a tier cheaply.
 *
 *  The flow only confirms; it never moves crypto. Worst case if the oracle key
 *  leaks is free plans (not theft) — keep ORACLE_SEED_HEX in the env file 600.
 *
 *  See ./README.md for the full deploy + go-live checklist.
 * ============================================================================
 */

import http from 'node:http';
import { Actor, HttpAgent } from '@dfinity/agent';
import { Ed25519KeyIdentity } from '@dfinity/identity';
import { IDL } from '@dfinity/candid';

// Plan prices in USD cents — MUST match the canister's planPriceUsdCents. The
// service prices the Stripe session from THIS map (never the client), and the
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

// Max accepted request body. Stripe events + the tiny /session JSON are well
// under this; anything larger is an abuse/DoS attempt and is rejected early
// (the adapter enforces it BEFORE buffering, so a huge body can't balloon RSS).
const MAX_BODY = 256 * 1024; // 256 KB

// Lightweight per-IP rate limit for /session (the one unauthenticated path that
// makes an outbound Stripe call). Fixed window; bounded map so spraying many
// IPs can't grow it without limit.
const RL_MAX = 30, RL_WINDOW_MS = 60_000;
const rlBuckets = new Map(); // ip -> { count, resetAt }
function sessionRateLimited(ip) {
  const now = Date.now();
  if (rlBuckets.size > 10_000) rlBuckets.clear(); // crude prune; ample for real traffic
  let b = rlBuckets.get(ip);
  if (!b || now > b.resetAt) { b = { count: 0, resetAt: now + RL_WINDOW_MS }; rlBuckets.set(ip, b); }
  b.count += 1;
  return b.count > RL_MAX;
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
// @dfinity/agent v3: HttpAgent.create() is async (it syncs time). Mainnet →
// never fetchRootKey. The identity is derived deterministically from the seed,
// so the principal is stable across restarts (that's what we register on-chain).
async function oracleActor(env) {
  const hex = (env.ORACLE_SEED_HEX || '').trim();
  const m = hex.match(/.{1,2}/g);
  if (!m || m.length !== 32) throw new Error('ORACLE_SEED_HEX must be 32 bytes (64 hex chars)');
  const seed = Uint8Array.from(m.map((h) => parseInt(h, 16)));
  const identity = Ed25519KeyIdentity.generate(seed);
  const agent = await HttpAgent.create({
    host: env.IC_HOST || 'https://icp0.io',
    identity,
    shouldFetchRootKey: false, // mainnet — do NOT fetch the root key
  });
  return Actor.createActor(idlFactory, { agent, canisterId: env.INDEX_CANISTER_ID });
}

// ── POST /session — create a Stripe Checkout Session ───────────────────────
async function handleSession(request, env, origin) {
  const ip = (request.headers.get('x-forwarded-for') || '').split(',')[0].trim() || 'unknown';
  if (sessionRateLimited(ip)) return json({ error: 'rate limited' }, 429, corsHeaders(origin));
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

  // Bound the outbound Stripe call so a slow/hung Stripe response can't pile up
  // awaited handlers.
  const ctrl = new AbortController();
  const to = setTimeout(() => ctrl.abort(), 10_000);
  let r;
  try {
    r = await fetch('https://api.stripe.com/v1/checkout/sessions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`, 'Content-Type': 'application/x-www-form-urlencoded' },
      body: p,
      signal: ctrl.signal,
    });
  } catch (e) {
    return json({ error: 'stripe unreachable' }, 504, corsHeaders(origin));
  } finally {
    clearTimeout(to);
  }
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
    const actor = await oracleActor(env);
    const res = await actor.confirmCardOrder(BigInt(icOrderId), BigInt(Math.round(amountCents)), session.id || '');
    if ('ok' in res) return new Response('confirmed', { status: 200 });
    // Business rejection (e.g. amount < price, wrong status) → do NOT retry.
    console.log('confirmCardOrder rejected:', res.err);
    return new Response('rejected: ' + res.err, { status: 200 });
  } catch (e) {
    // Transient IC failure (or oracle not yet configured) → 500 so Stripe
    // retries (its retry window ~3 days is the outage-recovery path).
    console.log('confirmCardOrder error:', String(e));
    return new Response('ic error', { status: 500 });
  }
}

// ── Router (was the Cloudflare `export default { fetch }`) ──────────────────
async function handleRequest(request, env) {
  const url = new URL(request.url);
  const origin = request.headers.get('Origin') || ALLOWED_ORIGINS[0];
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: corsHeaders(origin) });
  if (request.method === 'GET' && url.pathname === '/health') return new Response('ok', { status: 200 });
  if (request.method === 'POST' && url.pathname === '/webhook') return handleWebhook(request, env);
  if (request.method === 'POST') return handleSession(request, env, origin); // / or /session
  return new Response('CafresoHQ Stripe Oracle', { status: 200 });
}

// ── Node HTTP adapter ──────────────────────────────────────────────────────
// Buffer the raw body (Stripe's signature is over the exact bytes), build a
// Fetch Request, run the unchanged handler, stream the Response back.
const PORT = Number(process.env.STRIPE_ORACLE_PORT || 8788);
const HOST = process.env.STRIPE_ORACLE_BIND || '127.0.0.1';

const server = http.createServer((nodeReq, nodeRes) => {
  // Reject an oversized DECLARED body up front…
  const declared = Number(nodeReq.headers['content-length']);
  if (Number.isFinite(declared) && declared > MAX_BODY) {
    try { nodeRes.writeHead(413, { 'Content-Type': 'text/plain' }); nodeRes.end('payload too large'); } catch (_) {}
    nodeReq.destroy();
    return;
  }
  const chunks = [];
  let total = 0;
  let aborted = false;
  nodeReq.on('data', (c) => {
    if (aborted) return;
    total += c.length;
    // …and cap the ACTUAL bytes during streaming (defeats chunked/undeclared
    // bodies). This runs BEFORE any buffering completes, so a huge body can't
    // balloon RSS and pressure the co-hosted gateway.
    if (total > MAX_BODY) {
      aborted = true;
      try { nodeRes.writeHead(413, { 'Content-Type': 'text/plain' }); nodeRes.end('payload too large'); } catch (_) {}
      nodeReq.destroy();
      return;
    }
    chunks.push(c);
  });
  nodeReq.on('end', async () => {
    if (aborted) return;
    try {
      const bodyBuf = Buffer.concat(chunks);
      const hasBody = nodeReq.method !== 'GET' && nodeReq.method !== 'HEAD' && bodyBuf.length > 0;
      const request = new Request(`http://localhost${nodeReq.url}`, {
        method: nodeReq.method,
        headers: nodeReq.headers,
        body: hasBody ? bodyBuf : undefined,
      });
      const response = await handleRequest(request, process.env);
      const headers = {};
      response.headers.forEach((v, k) => { headers[k] = v; });
      const out = Buffer.from(await response.arrayBuffer());
      nodeRes.writeHead(response.status, headers);
      nodeRes.end(out);
    } catch (e) {
      console.log('handler error:', String(e && e.stack || e));
      // Only write a status if headers aren't already committed (avoids
      // ERR_HTTP_HEADERS_SENT throwing out of the catch).
      if (!nodeRes.headersSent) {
        try { nodeRes.writeHead(500, { 'Content-Type': 'text/plain' }); nodeRes.end('internal error'); } catch (_) {}
      } else {
        try { nodeRes.end(); } catch (_) {}
      }
    }
  });
  nodeReq.on('error', (e) => {
    console.log('request stream error:', String(e));
    try { if (!nodeRes.headersSent) { nodeRes.writeHead(400); nodeRes.end('bad request'); } } catch (_) {}
  });
});

// Bound slow-header / slow-body holds. Caddy fronts us (so these are defense in
// depth), but cheap to set at the origin too.
server.requestTimeout = 20_000;   // full request must complete in 20s
server.headersTimeout = 10_000;   // headers must arrive in 10s
server.keepAliveTimeout = 5_000;

server.listen(PORT, HOST, () => {
  console.log(`CafresoHQ Stripe Oracle listening on ${HOST}:${PORT} (max body ${MAX_BODY}B)`);
});

// A long-lived money relay must not die on a stray async fault — log loudly and
// keep serving. The per-request work is already wrapped in try/catch above.
process.on('unhandledRejection', (e) => console.log('unhandledRejection:', String((e && e.stack) || e)));
process.on('uncaughtException', (e) => console.log('uncaughtException:', String((e && e.stack) || e)));
