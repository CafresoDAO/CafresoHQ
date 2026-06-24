// ── CafresoHQ auth store ─────────────────────────────────────────────────────
// Internet Identity authentication that produces an *ecosystem-shared* principal —
// the same principal a user gets across Banking.Brave, Cafreso combined-dapp,
// and Minegold.defi. Achieved by setting II's `derivationOrigin` to the
// canonical Banking.Brave canister URL, which hosts the
// `/.well-known/ii-alternative-origins` file listing all sister dapps.
//
// Browser-only: every export early-returns when `window` is undefined so SSR /
// build-time pre-rendering doesn't hit `localStorage` or `AuthClient.create()`.
import { writable, derived, get } from 'svelte/store';
import { AuthClient } from '@dfinity/auth-client';
import { ECOSYSTEM } from '$lib/config.js';

// ── Ecosystem constants ──────────────────────────────────────────────────────
// Banking.Brave canister — the ecosystem's canonical II derivationOrigin.
// Cafreso combined-dapp + Minegold.defi both anchor here, so when CafresoHQ
// at ai.cafreso.com sets derivationOrigin to this URL, the user gets the
// SAME principal across cafreso.com, ai.cafreso.com, minegold.defi, etc.
//
// REQUIREMENT: the canister at ECOSYSTEM.banking must publish a
// `/.well-known/ii-alternative-origins` file listing every dapp domain
// that derives from it (e.g. cafreso.com, ai.cafreso.com).
export const ECOSYSTEM_DERIVATION_ORIGIN = ECOSYSTEM.banking;
export const II_PROVIDER_URL              = 'https://identity.ic0.app';

// 30 days, in nanoseconds — matches Cafreso combined-dapp session length
const MAX_SESSION_NS = BigInt(30 * 24 * 60 * 60 * 1_000_000_000);

const ECO_FLAG_KEY = 'cafresohq.use_ecosystem_principal';
const browser_     = () => typeof window !== 'undefined';

function _initialEcoFlag() {
  if (!browser_()) return true;
  const v = localStorage.getItem(ECO_FLAG_KEY);
  // default ON — ecosystem principal is the whole point. Users can opt out
  // during testing if Banking.Brave hasn't whitelisted this URL yet.
  return v === null ? true : v === 'true';
}

// ── Stores ───────────────────────────────────────────────────────────────────
/** 'initializing' | 'idle' | 'logging-in' | 'success' | 'error' */
export const authStatus     = writable('initializing');
export const authError      = writable(null);
export const authIdentity   = writable(null);  // Identity object (not serialized)
export const principalText  = writable('');    // string form, persistable

/**
 * When true (default), II login passes derivationOrigin → ecosystem-shared
 * principal across Banking.Brave / Cafreso / Minegold / CafresoHQ.
 * Requires Banking.Brave's `/.well-known/ii-alternative-origins` to list
 * this dapp's URL. Toggle off to test on a non-whitelisted host.
 */
export const useEcosystemPrincipal = writable(_initialEcoFlag());
if (browser_()) {
  useEcosystemPrincipal.subscribe((v) => {
    try { localStorage.setItem(ECO_FLAG_KEY, String(!!v)); } catch (_) { /* private mode */ }
  });
}

export const isAuthenticated = derived(authStatus, ($s) => $s === 'success');
export const isReady         = derived(authStatus, ($s) => $s !== 'initializing');

// ── Internal ─────────────────────────────────────────────────────────────────
let _client = null;

const browser = () => typeof window !== 'undefined';

async function _ensureClient() {
  if (_client) return _client;
  _client = await AuthClient.create({
    idleOptions: {
      idleTimeout:    1000 * 60 * 60 * 24, // 24h idle disconnect
      disableDefaultIdleCallback: true
    }
  });
  return _client;
}

function _adopt(identity) {
  const prevPrincipal = get(principalText);
  authIdentity.set(identity);
  const p = identity?.getPrincipal();
  const next = p ? p.toText() : '';
  principalText.set(next);
  // If the principal changed (different user signed in), wipe any vault
  // crypto state derived for the old principal so the new user can't
  // accidentally read a stale cached master key from sessionStorage.
  if (prevPrincipal && prevPrincipal !== next && browser()) {
    Promise.all([
      import('$lib/stores/vault.js'),
      import('$lib/api/keysActor.js'),
      import('$lib/api/stateActor.js'),
    ]).then(([{ lockVault }, { resetKeysActor }, { resetStateActor }]) => {
      lockVault();
      resetKeysActor();
      resetStateActor();
    }).catch(() => { /* best effort */ });
  }
}

// ── Public API ───────────────────────────────────────────────────────────────

/** Initialize the auth client. Call from the root layout's onMount. */
export async function initAuth() {
  if (!browser()) return;
  authStatus.set('initializing');
  try {
    const c = await _ensureClient();
    if (await c.isAuthenticated()) {
      _adopt(c.getIdentity());
      authStatus.set('success');
    } else {
      authStatus.set('idle');
    }
  } catch (err) {
    console.error('[auth] init failed:', err);
    authError.set(String(err));
    authStatus.set('error');
  }
}

/** Open the II popup and log in. Resolves once the user finishes. */
export async function login() {
  if (!browser()) return;
  authStatus.set('logging-in');
  authError.set(null);
  try {
    const c    = await _ensureClient();
    const useEco = get(useEcosystemPrincipal);
    const opts = {
      identityProvider: II_PROVIDER_URL,
      maxTimeToLive:    MAX_SESSION_NS,
      windowOpenerFeatures:
        'left=' + (window.screen.width / 2 - 525 / 2) +
        ',top='  + (window.screen.height / 2 - 705 / 2) +
        ',toolbar=0,location=0,menubar=0,width=525,height=705',
    };
    // Only pass derivationOrigin when the user asked for the ecosystem-shared
    // principal AND the alt-origins file at Banking.Brave is presumed to list
    // this URL. Without it, II falls back to the canister's own origin.
    if (useEco) opts.derivationOrigin = ECOSYSTEM_DERIVATION_ORIGIN;

    await new Promise((resolve, reject) => {
      c.login({
        ...opts,
        onSuccess: () => resolve(),
        onError:   (e) => reject(e)
      });
    });
    _adopt(c.getIdentity());
    authStatus.set('success');
  } catch (err) {
    console.error('[auth] login failed:', err);
    authError.set(String(err));
    authStatus.set('error');
  }
}

export async function logout() {
  if (!browser()) return;
  try {
    const c = await _ensureClient();
    await c.logout();
  } finally {
    authIdentity.set(null);
    principalText.set('');
    authStatus.set('idle');
    // Wipe vault crypto state — master key, cached actor, decrypted index —
    // and stop the hq_session refresh timer (it used to keep firing after
    // logout, trying to mint sessions for a signed-out user).
    // Lazy-load to avoid a circular import at module init time.
    try {
      const [{ lockVault }, { resetKeysActor }, { stopHqSession }, { resetStateActor }] = await Promise.all([
        import('$lib/stores/vault.js'),
        import('$lib/api/keysActor.js'),
        import('$lib/api/hqSession.js'),
        import('$lib/api/stateActor.js'),
      ]);
      lockVault();
      resetKeysActor();
      stopHqSession();
      resetStateActor();
    } catch (_) { /* best effort */ }
  }
}

/** Synchronous identity lookup for API clients. Returns null if not signed in. */
export function currentIdentity() {
  return get(authIdentity);
}

/** Synchronous principal lookup. Returns '' if not signed in. */
export function currentPrincipal() {
  return get(principalText);
}
