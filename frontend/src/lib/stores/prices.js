// Live USD price store for the wallet.
//
// Two public APIs, each whitelisted in `.ic-assets.json5`:
//
//   CoinGecko         — ICP and Uniswap (UNI, proxied for ckUNI)
//   GeckoTerminal     — per-token price lookup on the ICP network, used for
//                       sGLDT (ICPSwap pool) and $nanas (whichever DEX lists it)
//
// Fetches every 60s with a `Promise.allSettled` so a single endpoint outage
// doesn't take down the whole wallet. Falls back to localStorage cache (24h
// TTL) and finally to zero-priced rows so the UI never crashes.

import { browser } from '$app/environment';
import { writable, derived } from 'svelte/store';

const COINGECKO_URL =
  'https://api.coingecko.com/api/v3/simple/price?ids=internet-computer%2Cuniswap&vs_currencies=usd';
const GT_ICP_TOKEN = (canisterId) =>
  `https://api.geckoterminal.com/api/v2/networks/icp/tokens/${canisterId}`;

// Canister IDs (mirrored in lib/api/icrc1.js — keep them in sync).
const TOKEN_CANISTERS = {
  sGLDT: 'i2s4q-syaaa-aaaan-qz4sq-cai',
  nanas: 'mwen2-oqaaa-aaaam-adaca-cai'
};

const CACHE_KEY = 'cafreso:prices';
const CACHE_MAX_AGE_MS = 24 * 60 * 60 * 1000;
const REFRESH_MS = 60_000;

// Shape: `{ ICP, ckUNI, sGLDT, nanas }` — USD price per whole unit.
// `source` is 'live' | 'cache' | 'cache-stale' | 'default' so the UI can
// badge stale data. `updatedAt` is an epoch ms for display.
const DEFAULTS = { ICP: 0, ckUNI: 0, sGLDT: 0, nanas: 0 };

export const prices = writable({ ...DEFAULTS, source: 'default', updatedAt: null });

function loadCache() {
  if (!browser) return null;
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed?.ICP && !parsed?.nanas && !parsed?.sGLDT) return null;
    const stale = Date.now() - parsed.timestamp > CACHE_MAX_AGE_MS;
    return { ...parsed, stale };
  } catch {
    return null;
  }
}

function saveCache(snap) {
  if (!browser) return;
  try {
    localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({ ...snap, timestamp: Date.now() })
    );
  } catch {}
}

async function fetchGtToken(canisterId) {
  try {
    const res = await fetch(GT_ICP_TOKEN(canisterId));
    if (!res.ok) return null;
    const data = await res.json();
    const raw = data?.data?.attributes?.price_usd;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : null;
  } catch {
    return null;
  }
}

async function fetchLive() {
  const [cgRes, sgldtRes, nanasRes] = await Promise.allSettled([
    fetch(COINGECKO_URL),
    fetchGtToken(TOKEN_CANISTERS.sGLDT),
    fetchGtToken(TOKEN_CANISTERS.nanas)
  ]);

  let icp = null;
  let uni = null;
  if (cgRes.status === 'fulfilled' && cgRes.value.ok) {
    try {
      const d = await cgRes.value.json();
      if (d?.['internet-computer']?.usd) icp = Number(d['internet-computer'].usd);
      if (d?.uniswap?.usd) uni = Number(d.uniswap.usd);
    } catch {}
  }

  const sgldt = sgldtRes.status === 'fulfilled' ? sgldtRes.value : null;
  const nanas = nanasRes.status === 'fulfilled' ? nanasRes.value : null;

  const anyLive =
    (icp && icp > 0) || (uni && uni > 0) || (sgldt && sgldt > 0) || (nanas && nanas > 0);

  if (anyLive) {
    const snap = {
      ICP: icp ?? 0,
      ckUNI: uni ?? 0, // ckUNI tracks UNI 1:1 by design
      sGLDT: sgldt ?? 0,
      nanas: nanas ?? 0
    };
    saveCache(snap);
    return { ...snap, source: 'live' };
  }

  const cached = loadCache();
  if (cached) {
    return {
      ICP: cached.ICP ?? 0,
      ckUNI: cached.ckUNI ?? 0,
      sGLDT: cached.sGLDT ?? 0,
      nanas: cached.nanas ?? 0,
      source: cached.stale ? 'cache-stale' : 'cache'
    };
  }

  return { ...DEFAULTS, source: 'default' };
}

async function refresh() {
  try {
    const next = await fetchLive();
    prices.set({ ...next, updatedAt: Date.now() });
  } catch (err) {
    console.warn('[prices] refresh failed', err);
  }
}

let interval = null;
let started = false;

export function startPrices() {
  if (!browser || started) return;
  started = true;
  refresh();
  interval = setInterval(refresh, REFRESH_MS);
}

export function stopPrices() {
  if (interval) {
    clearInterval(interval);
    interval = null;
    started = false;
  }
}

// Helpers used by the wallet UI.

export function formatUsd(v) {
  if (!Number.isFinite(v) || v <= 0) return '—';
  // Sub-cent prices get more precision so $nanas at $0.0001 doesn't collapse
  // to "$0.00". Large values stick to 2 decimals.
  if (v < 0.01) return `$${v.toPrecision(2)}`;
  return v.toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}

export function rawToWhole(raw, decimals) {
  if (raw === null || raw === undefined) return 0;
  const n = typeof raw === 'bigint' ? Number(raw) / 10 ** decimals : Number(raw) / 10 ** decimals;
  return Number.isFinite(n) ? n : 0;
}

// Derived store: wallet-ready `[{ key, price, ... }]` rows — consumer
// pairs with balances to compute per-row + total USD value.
export const priceFor = derived(prices, ($p) => (key) => {
  const v = Number($p?.[key]);
  return Number.isFinite(v) ? v : 0;
});
