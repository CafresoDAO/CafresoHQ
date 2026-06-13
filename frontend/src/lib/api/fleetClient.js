// ── CafresoAI fleet API client ──────────────────────────────────────────────
// Talks to oci-fleet/fleet-api.py — looks up + provisions per-user OCI
// containers keyed by ICP Internet Identity principals.
//
// The fleet API URL is configurable in Settings; defaults to localhost:8080.

import { writable, get } from 'svelte/store';

const STORAGE_KEY    = 'cafresoai.fleet_api_url';
// In dev (localhost), hit local fleet-api.py; in production (ICP canister),
// hit the gateway VM where fleet-api.py is deployed behind Caddy.
// HTTPS is required when the shell is served from an HTTPS origin (mixed-content).
const DEFAULT_API    = (typeof window !== 'undefined'
    && /localhost|127\.0\.0\.1/.test(window.location?.hostname))
    ? 'http://localhost:8080'
    : 'https://hq.cafreso.com';   // Caddy TLS gateway — auto-cert via Let's Encrypt
const browser        = () => typeof window !== 'undefined';

// ── Stores ──────────────────────────────────────────────────────────────────
export const fleetApiUrl = writable(
  (browser() && localStorage.getItem(STORAGE_KEY)) || DEFAULT_API
);

if (browser()) {
  fleetApiUrl.subscribe((v) => {
    try {
      if (v) localStorage.setItem(STORAGE_KEY, v);
      else   localStorage.removeItem(STORAGE_KEY);
    } catch (_) { /* private mode */ }
  });
}

export const fleetApiAuthToken = writable(
  (browser() && localStorage.getItem('cafresoai.fleet_api_token')) || ''
);
if (browser()) {
  fleetApiAuthToken.subscribe((v) => {
    try {
      if (v) localStorage.setItem('cafresoai.fleet_api_token', v);
      else   localStorage.removeItem('cafresoai.fleet_api_token');
    } catch (_) { /* private mode */ }
  });
}

// ── Internal fetch ──────────────────────────────────────────────────────────
class FleetApiError extends Error {
  constructor(message, { status = 0, body = null } = {}) {
    super(message);
    this.name   = 'FleetApiError';
    this.status = status;
    this.body   = body;
  }
}

async function _fetch(path, opts = {}) {
  const url = get(fleetApiUrl).replace(/\/+$/, '') + path;
  const tok = get(fleetApiAuthToken);
  const headers = { 'Accept': 'application/json', ...(opts.headers || {}) };
  if (tok) headers['X-Fleet-Auth'] = tok;
  const ctrl  = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 30_000);
  try {
    const r = await fetch(url, { ...opts, headers, signal: ctrl.signal });
    const text = await r.text();
    const data = text ? JSON.parse(text) : null;
    if (!r.ok) {
      throw new FleetApiError(data?.error || `HTTP ${r.status}`,
        { status: r.status, body: data });
    }
    return data;
  } finally {
    clearTimeout(timer);
  }
}

// ── Public API ──────────────────────────────────────────────────────────────

/** Liveness check — returns the API's /health JSON. */
export async function fleetHealth() {
  return _fetch('/fleet/health', { timeoutMs: 5_000 });
}

/**
 * Look up an existing container for a principal.
 * Returns the lookup record (with `endpoint`) or `null` if 404.
 */
export async function lookup(principal) {
  try {
    return await _fetch('/fleet/lookup?principal=' + encodeURIComponent(principal),
                        { timeoutMs: 8_000 });
  } catch (err) {
    if (err instanceof FleetApiError && err.status === 404) return null;
    throw err;
  }
}

/**
 * Kick off a provision job. Returns either:
 *   { status: 'existing', endpoint } — already provisioned
 *   { job_id, status: 'queued',  poll } — running async, poll the job
 *
 * Self-service: pass `token` (an on-chain-minted session token from
 * mintSessionToken in hqSession.js) — the API takes the principal FROM the
 * token, so a caller can only provision their OWN container. Without a token
 * the server requires admin X-Fleet-Auth (refused in dev-mode), which closes
 * the hole where anyone could spin a container for an arbitrary principal.
 */
export async function provision(principal, token) {
  return _fetch('/fleet/provision', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(token ? { principal, token } : { principal }),
    timeoutMs: 15_000,
  });
}

/** Single status fetch for an in-flight job. */
export async function getJob(jobId) {
  return _fetch('/fleet/job/' + encodeURIComponent(jobId), { timeoutMs: 8_000 });
}

/**
 * Permanently delete the caller's OWN container. The credential is an
 * on-chain-minted session token (mintSessionToken in hqSession.js) — the API
 * takes the principal FROM the token, so a caller can only delete their own
 * container. Synchronous on the server (~10-30s): removes the OCI container
 * instance + its gateway route. The user's encrypted vault in Object Storage
 * is PRESERVED — re-provisioning the same principal recovers it. Idempotent:
 * deleting a non-existent container succeeds.
 * Returns { status: 'deleted', principal, note }.
 */
export async function deprovision(token) {
  return _fetch('/fleet/deprovision', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ token }),
    timeoutMs: 130_000,
  });
}

/**
 * @typedef {Object} ProvisionWaitOptions
 * @property {(job: any) => void} [onUpdate]
 * @property {number} [pollMs]
 * @property {number} [maxWaitMs]
 * @property {string} [token]  on-chain session token for self-service provision
 */

/**
 * Provision and poll until 'ready' or 'error'. Calls onUpdate(job) on each tick.
 * Throws on error or timeout.
 *
 * @param {string} principal
 * @param {ProvisionWaitOptions} [options]
 */
export async function provisionAndWait(principal, {
  onUpdate, pollMs = 5_000, maxWaitMs = 600_000, token
} = {}) {
  const start = await provision(principal, token);
  if (start.status === 'existing') {
    onUpdate?.({ ...start, phase: 'existing' });
    return start;
  }
  const jobId = start.job_id;
  onUpdate?.({ ...start, phase: 'queued' });

  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, pollMs));
    const job = await getJob(jobId);
    onUpdate?.(job);
    if (job.status === 'ready') return job;
    if (job.status === 'error') {
      throw new FleetApiError(job.error || 'provision failed',
        { status: 500, body: job });
    }
  }
  throw new FleetApiError('provision timed out',
    { status: 504, body: { jobId } });
}

/**
 * Wake (start) the caller's OWN stopped container so the browser can reach it
 * again. Same credential model as provision: pass an on-chain-minted session
 * `token` (the principal is taken FROM the token). Returns either:
 *   { status: 'ready', endpoint, gateway_url } — already healthy / woke instantly
 *   { job_id, status: 'queued', poll }         — starting async, poll the job
 * Throws FleetApiError(404) with body.code==='not_provisioned' when there is no
 * container on record — the caller should provision instead of waking.
 */
export async function wake(token) {
  return _fetch('/fleet/wake', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ token }),
    timeoutMs: 15_000,
  });
}

/**
 * Wake and poll until 'ready' or 'error'. Mirrors provisionAndWait — calls
 * onUpdate(job) each tick. Throws FleetApiError on error/timeout; for a dead
 * container the thrown error's body.phase==='gone' (the recorded instance was
 * deleted/failed), so the caller can branch to provision a fresh one — the
 * encrypted vault in Object Storage is preserved and reattaches on re-provision.
 *
 * @param {string} token  on-chain session token (principal taken FROM it)
 * @param {{onUpdate?:(job:any)=>void, pollMs?:number, maxWaitMs?:number}} [options]
 */
export async function wakeAndWait(token, {
  onUpdate, pollMs = 3_000, maxWaitMs = 180_000
} = {}) {
  const start = await wake(token);
  if (start.status === 'ready') {
    onUpdate?.({ ...start, phase: 'ready' });
    return start;
  }
  const jobId = start.job_id;
  onUpdate?.({ ...start, phase: start.phase || 'waking' });

  const deadline = Date.now() + maxWaitMs;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, pollMs));
    const job = await getJob(jobId);
    onUpdate?.(job);
    if (job.status === 'ready') return job;
    if (job.status === 'error') {
      // Preserve the full job (incl. phase:'gone') so the caller can branch.
      throw new FleetApiError(job.error || 'wake failed',
        { status: 500, body: job });
    }
  }
  throw new FleetApiError('wake timed out', { status: 504, body: { jobId } });
}

export { FleetApiError };
