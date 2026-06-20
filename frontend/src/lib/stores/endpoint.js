// ── CafresoAI cloud endpoint store ───────────────────────────────────────────
// Tracks the URL of the user's OCI Container Instance (their personal
// CafresoAI serve.py instance) and probes /health to confirm it's alive.
//
// Three deployment modes detected automatically:
//   1. Local Companion  → http://localhost:8787
//   2. OCI self-deploy  → user-pasted https URL of their own VM
//   3. OCI Fleet        → URL provisioned by fleet-manager
//
// The endpoint is persisted in localStorage so it survives reloads.
import { writable, derived, get } from 'svelte/store';

const STORAGE_KEY = 'cafresoai.endpoint';

// ── Stores ───────────────────────────────────────────────────────────────────

/** Configured endpoint URL (string) or '' if unset. */
export const endpointUrl = writable('');

/**
 * Health probe state:
 *   { state: 'idle' | 'probing' | 'ok' | 'error',
 *     data:  <last successful /health response> | null,
 *     error: <string|null>, lastChecked: <Date|null> }
 */
export const endpointHealth = writable({
  state: 'idle',
  data:  null,
  error: null,
  lastChecked: null
});

export const endpointReady = derived(
  endpointHealth, ($h) => $h.state === 'ok'
);

// ── Hydration ────────────────────────────────────────────────────────────────
const browser = () => typeof window !== 'undefined';

function _hydrate() {
  if (!browser()) return;
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) endpointUrl.set(saved);
  } catch (_) { /* ignore */ }
}
_hydrate();

endpointUrl.subscribe((url) => {
  if (!browser()) return;
  try {
    if (url) localStorage.setItem(STORAGE_KEY, url);
    else     localStorage.removeItem(STORAGE_KEY);
  } catch (_) { /* ignore */ }
});

// ── Helpers ──────────────────────────────────────────────────────────────────
export function normalizeUrl(raw) {
  if (!raw) return '';
  let s = raw.trim();
  // Auto-prepend http:// if missing scheme
  if (!/^https?:\/\//i.test(s)) s = 'http://' + s;
  // Strip trailing slash
  return s.replace(/\/+$/, '');
}

/** Set + persist the endpoint URL. Returns the normalized form.
 *  Automatically kicks off a /health probe so the rest of the app doesn't
 *  have to remember to call probeHealth() after every setEndpoint() —
 *  this previously caused the "Connecting to your container…" spinner
 *  to hang indefinitely after a successful provision.
 */
export function setEndpoint(raw) {
  const n = normalizeUrl(raw);
  endpointUrl.set(n);
  // New endpoint → reset health state, then immediately probe.
  endpointHealth.set({ state: 'idle', data: null, error: null, lastChecked: null });
  if (n) {
    // Fire-and-forget — probeHealth() updates endpointHealth reactively.
    probeHealth().catch(() => { /* error surfaces via endpointHealth */ });
  }
  return n;
}

export function clearEndpoint() {
  endpointUrl.set('');
  endpointHealth.set({ state: 'idle', data: null, error: null, lastChecked: null });
}

/**
 * Chrome 138+ gates public-site → localhost requests behind a user-granted
 * "local network access" permission (Edge follows Chromium). Report its state
 * so callers can (a) guide the user through the one-time Allow click and
 * (b) stretch fetch timeouts while the prompt is on screen — an AbortSignal
 * firing mid-prompt cancels the request before the user can answer.
 * Returns 'granted' | 'prompt' | 'denied' | 'unsupported'.
 */
export async function localNetworkPermission() {
  try {
    if (!browser() || !navigator.permissions?.query) return 'unsupported';
    const s = await navigator.permissions.query({ name: 'local-network-access' });
    return s.state || 'unsupported';
  } catch (_) {
    return 'unsupported';   // browser doesn't know the permission = no gating
  }
}

/** Effective probe timeout: while the browser is showing (or about to show)
 *  the local-network permission prompt, give the user time to answer. */
async function _lnaAwareTimeout(base, url) {
  if (!/^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(url || '')) return base;
  return (await localNetworkPermission()) === 'prompt' ? Math.max(base, 45_000) : base;
}

/**
 * GET /health on the current endpoint, update endpointHealth.
 * Returns the parsed body on success, throws on failure.
 */
export async function probeHealth({ timeoutMs = 8000 } = {}) {
  const url = get(endpointUrl);
  if (!url) {
    endpointHealth.set({ state: 'error', data: null,
      error: 'no endpoint configured', lastChecked: new Date() });
    throw new Error('no endpoint configured');
  }
  endpointHealth.update((h) => ({ ...h, state: 'probing', error: null }));
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), await _lnaAwareTimeout(timeoutMs, url));
  try {
    const r = await fetch(url + '/health', {
      method: 'GET',
      signal: ctrl.signal,
      headers: { 'Accept': 'application/json' }
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    endpointHealth.set({
      state: 'ok',
      data,
      error: null,
      lastChecked: new Date()
    });
    return data;
  } catch (err) {
    const msg = err.name === 'AbortError' ? `timeout after ${timeoutMs}ms` : String(err.message || err);
    endpointHealth.set({
      state: 'error',
      data: null,
      error: msg,
      lastChecked: new Date()
    });
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Detect a Local Companion running on this machine.
 *
 * Tries HTTPS first, then HTTP. The local app now auto-provisions a localhost
 * TLS cert, so when ai.cafreso.com (HTTPS) is the shell, only the HTTPS probe
 * can succeed (an HTTP probe is mixed-content-blocked, and an https→https fetch
 * only resolves if the cert is browser-trusted, i.e. mkcert) — which is exactly
 * the condition under which the local app can also be embedded in an iframe.
 * The HTTP fallback keeps working when the shell itself is served over HTTP.
 */
// Ports auto-probed when looking for a Local Companion. 8787 is the default in
// the docker one-liner; 8788 is the most common alt when 8787 is taken. Users
// on any other port connect explicitly via the "custom port" field (which
// persists, so subsequent loads find it without scanning).
export const DEFAULT_LOCAL_PORTS = [8787, 8788];

export async function detectLocalCompanion({ timeoutMs = 1500, allowPrompt = false, ports = DEFAULT_LOCAL_PORTS } = {}) {
  // https before http, lower ports before higher — candidate[i] order = preference.
  const candidates = [];
  for (const p of ports) candidates.push(`https://localhost:${p}`, `http://localhost:${p}`);
  // While Chrome's local-network permission prompt is pending, only a probe
  // initiated from a user gesture should wait on it (allowPrompt) — the quiet
  // background re-poll must not stack 45s requests.
  let effective = timeoutMs;
  if (allowPrompt) effective = await _lnaAwareTimeout(timeoutMs, `http://localhost:${ports[0]}`);
  // Probe concurrently so adding ports doesn't multiply the wall-clock wait;
  // worst case stays ~one timeout regardless of how many ports we check.
  const probe = (candidate) => new Promise((resolve) => {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), effective);
    fetch(candidate + '/health', { signal: ctrl.signal })
      .then((r) => resolve(r.ok ? candidate : null))
      .catch(() => resolve(null))          // not running / blocked / untrusted cert
      .finally(() => clearTimeout(timer));
  });
  const results = await Promise.all(candidates.map(probe));
  return results.find(Boolean) || null;    // earliest (most-preferred) responder
}

/**
 * Turn whatever the user typed in the "custom port / URL" field into a probe-able
 * URL: a bare port ("8788") -> http://localhost:8788; a host or full URL -> normalized.
 */
export function localUrlFromInput(raw) {
  const s = (raw || '').trim();
  if (!s) return '';
  if (/^\d{2,5}$/.test(s)) return `http://localhost:${s}`;   // bare port number
  return normalizeUrl(s);                                     // host or full URL
}
