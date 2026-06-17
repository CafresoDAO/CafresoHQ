// Cafreso Store API client (Phase 2 — CanDB-backed via IndexCanister).
//
// Talks to the IndexCanister for products + orders + treasury.
// Falls back to seed data when offline so SSR/preview never blanks.

import { browser } from '$app/environment';
import { createActor } from '$lib/declarations/index';
import { currentIdentity } from '$lib/stores/auth.js';
import { PRODUCTS as SEED_PRODUCTS } from '$lib/data/products.js';

const MAINNET_INDEX = 'bek5d-2qaaa-aaaab-agqrq-cai';
const canisterId =
  import.meta.env.PUBLIC_INDEX_CANISTER_ID || MAINNET_INDEX;
// The index canister principal — the spender the buyer approves for ICRC-2
// plan purchase (it calls icrc2_transfer_from to collect the fixed plan price).
export const INDEX_CANISTER_ID = canisterId;
const network = import.meta.env.PUBLIC_DFX_NETWORK || 'ic';
const host = network === 'local' ? 'http://127.0.0.1:4943' : 'https://icp0.io';

let _anonActor = null;
let _authActor = null;
let _authPrincipal = null;

function actor({ authed = false } = {}) {
  if (!browser || !canisterId) return null;
  if (authed) {
    const identity = currentIdentity();
    if (!identity) return null;
    const principal = (() => {
      try { return identity.getPrincipal().toText(); } catch { return null; }
    })();
    if (_authActor && _authPrincipal === principal) return _authActor;
    try {
      _authActor = createActor(canisterId, { agentOptions: { host, identity } });
      _authPrincipal = principal;
      return _authActor;
    } catch (e) {
      console.warn('[store] authed actor creation failed', e);
      return null;
    }
  }
  if (_anonActor) return _anonActor;
  try {
    _anonActor = createActor(canisterId, { agentOptions: { host } });
    return _anonActor;
  } catch (e) {
    console.warn('[store] anon actor creation failed', e);
    return null;
  }
}

// ---------- Products ----------
// New CanDB Product shape: { name, slug, description, priceNanas (Text),
// fileKeys, tags, timestampListed }. The frontend's existing UI uses
// `title`/`excerpt`/`cat`/`img`/`price` etc. — we shim at the edge.
//
// Mapping conventions:
//   tags[0] = category ("Coffee" | "Merch" | "DAO" | "SNS")
//   tags[1] = "soon" if true (else absent)
//   tags[2] = stock count (numeric) or "unlimited"
//   tags[3] = priceCentsUSD as Text
//   fileKeys[0] = image key
function canisterToProduct(p) {
  const tags = p.tags || [];
  const cat = tags[0] || 'Coffee';
  const soon = tags.includes('soon');
  const stockTag = tags.find((t) => /^stock:/.test(t));
  const stock = stockTag ? (stockTag.slice(6) === 'unlimited' ? null : Number(stockTag.slice(6))) : null;
  const usdTag = tags.find((t) => /^usd:/.test(t));
  const priceCentsUSD = usdTag ? Number(usdTag.slice(4)) : 0;
  return {
    slug: p.slug,
    name: p.name,
    title: p.name,
    excerpt: p.description,
    cat,
    img: (p.fileKeys && p.fileKeys[0]) || '',
    price: Number(p.priceNanas) || 0,
    priceCentsUSD,
    soon,
    stock,
  };
}

function productToCanister(p) {
  const tags = [p.cat || 'Coffee'];
  if (p.soon) tags.push('soon');
  tags.push(`stock:${p.stock == null || p.stock === '' ? 'unlimited' : Number(p.stock)}`);
  tags.push(`usd:${Math.max(0, Math.floor(Number(p.priceCentsUSD ?? 0)))}`);
  return {
    slug: p.slug,
    name: p.title ?? p.name ?? '',
    description: p.excerpt ?? '',
    priceNanas: String(Math.max(0, Math.floor(Number(p.price ?? 0)))),
    fileKeys: p.img ? [p.img] : [],
    tags,
    timestampListed: 0n,
  };
}

export async function listProducts() {
  const a = actor();
  if (!a) return SEED_PRODUCTS;
  try {
    const out = await a.listProducts();
    if (!out || out.length === 0) return SEED_PRODUCTS;
    return out.map(canisterToProduct);
  } catch (e) {
    console.warn('[store] listProducts failed, using seed', e);
    return SEED_PRODUCTS;
  }
}

export async function getProduct(slug) {
  const a = actor();
  const fallback = () => SEED_PRODUCTS.find((p) => p.slug === slug) || null;
  if (!a) return fallback();
  try {
    const out = await a.getProduct(slug);
    if (!out || out.length === 0) return fallback();
    return canisterToProduct(out[0]);
  } catch (e) {
    console.warn('[store] getProduct failed, using seed', e);
    return fallback();
  }
}

export async function upsertProduct(product) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in to manage the catalog.' };
  try {
    const res = await a.upsertProduct(productToCanister(product));
    if ('ok' in res) return { ok: canisterToProduct(res.ok) };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

export async function deleteProduct(slug) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in to manage the catalog.' };
  try {
    const res = await a.deleteProduct(slug);
    if ('ok' in res) return { ok: true };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

// ---------- Orders ----------
// New shape: itemsJson + shippingJson are JSON-encoded text fields.
// status is Text ("pending" | "paid" | …).
function canisterToOrder(o) {
  let items = [];
  let shipping = {};
  try { items = JSON.parse(o.itemsJson || '[]'); } catch (_) {}
  try { shipping = JSON.parse(o.shippingJson || '{}'); } catch (_) {}
  return {
    id: Number(o.id),
    buyer: o.buyer,
    items,
    totalNanas: Number(o.totalNanas),
    shipping,
    status: o.status,
    paidBlock: Number(o.paidBlock) || null,
    paymentMethod: o.paymentMethod,
    note: o.note,
    createdAt: Number(o.timestampCreated) / 1_000_000,
    updatedAt: Number(o.timestampUpdated) / 1_000_000,
  };
}

export async function recordOrder({ items, shipping, paidBlock = 0, paymentMethod = 'nanas' }) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in to place an order.' };
  try {
    const itemsJson = JSON.stringify(
      (items || []).map((it) => ({
        slug: it.slug,
        qty: Number(it.qty ?? 1),
        priceNanas: Number(it.priceNanas ?? it.price ?? 0),
      }))
    );
    const shippingJson = JSON.stringify(shipping || {});
    const res = await a.recordOrder(itemsJson, shippingJson, BigInt(paidBlock || 0), paymentMethod);
    if ('ok' in res) return { ok: canisterToOrder(res.ok) };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

// Trustless self-service ICP plan purchase: the index canister pulls the fixed
// plan price (icrc2_transfer_from) from the buyer — who must have approved it
// first — and records a PAID order. Returns { ok: order } | { err }.
export async function purchasePlanIcp(slug) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in to subscribe.' };
  try {
    const res = await a.purchasePlanIcp(slug);
    if ('ok' in res) return { ok: canisterToOrder(res.ok) };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

// USD-cents price (BigInt) for a plan slug, or null if unpriced. The canister
// charges the live-rate ICP equivalent at purchase (via the XRC oracle).
export async function getPlanPriceUsdCents(slug) {
  const a = actor();
  if (!a) return null;
  try {
    const out = await a.getPlanPriceUsdCents(slug);   // opt nat → [] | [BigInt cents]
    return (out && out.length) ? out[0] : null;
  } catch (e) {
    console.warn('[store] getPlanPriceUsdCents failed', e);
    return null;
  }
}

// Legacy compat — old code calls `markOrderPaid`. Route through confirmOrder.
export async function markOrderPaid(id, blockIndex) {
  return confirmOrder(id, blockIndex);
}

export async function confirmOrder(id, blockIndex) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in as admin first.' };
  try {
    const res = await a.confirmOrder(BigInt(id), BigInt(blockIndex));
    if ('ok' in res) return { ok: canisterToOrder(res.ok) };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

export async function listMyOrders() {
  const a = actor({ authed: true });
  if (!a) return [];
  try {
    const out = await a.listMyOrders();
    return out.map(canisterToOrder);
  } catch (e) {
    console.warn('[store] listMyOrders failed', e);
    return [];
  }
}

export async function listAllOrders() {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in as admin first.' };
  try {
    const res = await a.listAllOrders();
    if ('ok' in res) return { ok: res.ok.map(canisterToOrder) };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

export async function updateOrderStatus(id, status, note = '') {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in as admin first.' };
  try {
    const res = await a.updateOrderStatus(BigInt(id), status, note);
    if ('ok' in res) return { ok: canisterToOrder(res.ok) };
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}

// ---------- Treasury ----------

let _treasuryCache = null;
export async function getTreasury() {
  const a = actor();
  if (!a) return null;
  if (_treasuryCache) return _treasuryCache;
  try {
    const out = await a.getTreasury();
    if (!out || out.length === 0) return null;
    _treasuryCache = out[0].principal;
    return _treasuryCache;
  } catch (e) {
    console.warn('[store] getTreasury failed', e);
    return null;
  }
}

export async function setTreasury(principalText) {
  const a = actor({ authed: true });
  if (!a) return { err: 'Sign in as admin first.' };
  try {
    const { Principal } = await import('@dfinity/principal');
    const res = await a.setTreasury(Principal.fromText(principalText));
    if ('ok' in res) {
      _treasuryCache = principalText;
      return { ok: true };
    }
    return { err: res.err };
  } catch (e) {
    return { err: String(e?.message || e) };
  }
}
