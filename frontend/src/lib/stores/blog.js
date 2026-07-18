import { writable, derived, get } from 'svelte/store';
import { browser } from '$app/environment';
import { authIdentity } from '$lib/stores/auth.js';
import { getBalance, TOKENS } from '$lib/api/icrc1.js';

const TWEAK_DEFAULTS = { density: 'cozy', burnModel: 'hold', pixelArt: 'on' };

function persisted(key, fallback) {
  const initial = browser ? JSON.parse(localStorage.getItem(key) || 'null') ?? fallback : fallback;
  const store = writable(initial);
  if (browser) store.subscribe((v) => localStorage.setItem(key, JSON.stringify(v)));
  return store;
}

// `$nanas` is now a real on-chain ICRC-1 token (`mwen2-…`). For signed-in
// users we hydrate this store from `icrc1_balance_of` against the ledger;
// for anonymous visitors we fall back to the seeded localStorage counter
// so the chip never renders blank on first load. `refreshNanasBalance()`
// re-polls the ledger — call after any action that changes the balance
// (checkout, tip, mint).
export const nanasBalance = persisted('cafreso-blog:nanas', 0);
export const nanasBalanceSource = writable('local'); // 'local' | 'ledger' | 'ledger-stale'

// ── Gold (sGLDT) — the real economy token ────────────────────────────────────
// Tips and shop payments moved from the $nanas test token to sGLDT: a low-fee
// wrapper of GLDT (1:1 gold-backed, sVault/Sneed DAO governed). Fractional —
// the chip shows 2dp; transfers use the exact amount. $nanas stores stay for
// legacy wallet display only.
export const goldBalance = writable(null);            // sGLDT whole units (float) | null = not loaded
export const goldBalanceSource = writable('none');    // 'none' | 'ledger' | 'ledger-stale'
export const userBurns = persisted('cafreso-blog:burns', {}); // slug -> amount
export const tweaks = persisted('cafreso-blog:tweaks', TWEAK_DEFAULTS);
export const tweaksOpen = writable(false);
export const burnTarget = writable(null); // slug or null
export const bbModalOpen = writable(false);
export const aiSearchOpen = writable(false);
// Optional query handed to AISearchModal when it opens (e.g. from the homepage
// search box). Consumed + cleared by the modal on open; empty = normal idle.
export const aiSearchPrefill = writable('');

// Burn state derived from current target
export const userBurnedOn = (slug) => derived(userBurns, ($b) => $b[slug] || 0);

// Confirm a burn locally — used for the optimistic UI flash after a tip.
// The real balance is corrected on the next `refreshNanasBalance()` call.
export function confirmBurn(slug, amount) {
  userBurns.update((b) => ({ ...b, [slug]: (b[slug] || 0) + amount }));
  nanasBalance.update((n) => Math.max(0, n - amount));
}

export async function refreshNanasBalance() {
  if (!browser) return;
  const identity = get(authIdentity);
  if (!identity) {
    nanasBalanceSource.set('local');
    return;
  }
  try {
    const principal = identity.getPrincipal().toText();
    const raw = await getBalance('nanas', principal);
    if (raw === null || raw === undefined) {
      nanasBalanceSource.set('ledger-stale');
      return;
    }
    // $nanas uses 8 decimals (e8s); the UI treats the chip as a whole-unit
    // counter, so we format back to integer nanas.
    const whole = Number(raw) / 10 ** TOKENS.nanas.decimals;
    nanasBalance.set(Math.floor(whole));
    nanasBalanceSource.set('ledger');
  } catch (err) {
    console.warn('[blog.js] refreshNanasBalance failed', err);
    nanasBalanceSource.set('ledger-stale');
  }
}

// Optimistic decrement after a gold tip — corrected by the next refresh.
export function confirmGoldTip(slug, amount) {
  userBurns.update((b) => ({ ...b, [slug]: (b[slug] || 0) + amount }));
  goldBalance.update((n) => (n === null ? null : Math.max(0, n - amount)));
}

export async function refreshGoldBalance() {
  if (!browser) return;
  const identity = get(authIdentity);
  if (!identity) {
    goldBalance.set(null);
    goldBalanceSource.set('none');
    return;
  }
  try {
    const principal = identity.getPrincipal().toText();
    const raw = await getBalance('sGLDT', principal);
    if (raw === null || raw === undefined) {
      goldBalanceSource.set('ledger-stale');
      return;
    }
    goldBalance.set(Number(raw) / 10 ** TOKENS.sGLDT.decimals);
    goldBalanceSource.set('ledger');
  } catch (err) {
    console.warn('[blog.js] refreshGoldBalance failed', err);
    goldBalanceSource.set('ledger-stale');
  }
}

// Auto-refresh whenever the signed-in principal changes.
if (browser) {
  authIdentity.subscribe((id) => {
    if (id) {
      refreshNanasBalance();
      refreshGoldBalance();
    }
  });
}
