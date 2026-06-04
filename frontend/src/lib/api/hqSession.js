// ── CafresoAI HQ container session ───────────────────────────────────────────
// Mints a short-lived, principal-bound session token ON-CHAIN (the cafresoai_keys
// canister verifies II ownership natively, then HMAC-signs principal+exp) and
// installs it as a cookie on the OCI gateway. The gateway's Caddy forward_auth →
// verifier.py then gates every /u/<slug>/* request with it, so only the signed-in
// owner can reach their container. /health stays open, so liveness probing works
// without a session.
//
// Flow:
//   1. actor.mintHqSession()                → { token, exp }   (on-chain, authed)
//   2. POST <gateway>/fleet/session {token} → Set-Cookie hq_session  (credentials)
//   3. schedule a refresh shortly before exp while the II delegation is valid
//
// Only needed when the container is reached THROUGH the gateway (hq.cafreso.com).
// Local/self-hosted endpoints have no verifier and skip this entirely.
import { writable, get } from 'svelte/store';
import { getKeysActor } from '$lib/api/keysActor.js';
import { isAuthenticated } from '$lib/stores/auth.js';
import { fleetApiUrl } from '$lib/api/fleetClient.js';

export const hqSessionReady = writable(false);
export const hqSessionError = writable(null);

let _refreshTimer = null;
let _inflight = null;

function gatewayBase() {
  // The cookie must be set on the host that serves /u/<slug>/* — the same host
  // the fleet API lives behind (the Caddy gateway).
  return (get(fleetApiUrl) || '').replace(/\/+$/, '');
}

/** Host that owns the gateway (where the session cookie lives). */
export function gatewayHost() {
  try { return new URL(get(fleetApiUrl)).host; } catch { return ''; }
}

/** Whether a given endpoint URL is served through the auth gateway (and thus
 *  needs a session cookie). Local/self-hosted endpoints return false. */
export function endpointNeedsSession(endpointUrl) {
  if (!endpointUrl) return false;
  let host = '';
  try { host = new URL(endpointUrl).host; } catch { return false; }
  const gw = gatewayHost();
  return !!gw && host === gw;
}

/** Mint a token on-chain and install it as a cookie on the gateway, then
 *  schedule a refresh. Returns true on success. De-duplicated: concurrent
 *  callers share one in-flight mint. */
export async function ensureHqSession() {
  if (!get(isAuthenticated)) { hqSessionReady.set(false); return false; }
  if (_inflight) return _inflight;
  _inflight = (async () => {
    try {
      const actor = await getKeysActor();
      let minted;
      try {
        minted = await actor.mintHqSession();
      } catch (e) {
        // Most likely the canister secret isn't configured yet (setHqSessionSecret).
        hqSessionError.set(_reason(e));
        hqSessionReady.set(false);
        return false;
      }
      const token = String(minted.token);
      const exp = Number(minted.exp); // seconds since epoch
      const base = gatewayBase();
      if (!base) { hqSessionReady.set(false); return false; }

      const r = await fetch(base + '/fleet/session', {
        method: 'POST',
        credentials: 'include',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      if (!r.ok) {
        hqSessionError.set(`session install failed (HTTP ${r.status})`);
        hqSessionReady.set(false);
        return false;
      }
      hqSessionError.set(null);
      hqSessionReady.set(true);
      _scheduleRefresh(exp);
      return true;
    } catch (e) {
      hqSessionError.set(_reason(e));
      hqSessionReady.set(false);
      return false;
    } finally {
      _inflight = null;
    }
  })();
  return _inflight;
}

function _scheduleRefresh(expSeconds) {
  if (_refreshTimer) clearTimeout(_refreshTimer);
  if (!Number.isFinite(expSeconds)) return;
  const nowSec = Date.now() / 1000;
  // Refresh 2 minutes before expiry; never sooner than 30s from now.
  const delayMs = Math.max(30_000, (expSeconds - nowSec - 120) * 1000);
  _refreshTimer = setTimeout(() => { ensureHqSession().catch(() => {}); }, delayMs);
}

export function stopHqSession() {
  if (_refreshTimer) { clearTimeout(_refreshTimer); _refreshTimer = null; }
  hqSessionReady.set(false);
}

function _reason(e) {
  const m = String(e?.message || e || 'unknown error');
  if (/not configured/i.test(m)) return 'HQ sessions are not enabled yet.';
  return m;
}
