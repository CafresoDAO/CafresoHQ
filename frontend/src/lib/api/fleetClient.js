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
 */
export async function provision(principal) {
  return _fetch('/fleet/provision', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ principal }),
    timeoutMs: 15_000,
  });
}

/** Single status fetch for an in-flight job. */
export async function getJob(jobId) {
  return _fetch('/fleet/job/' + encodeURIComponent(jobId), { timeoutMs: 8_000 });
}

/**
 * @typedef {Object} ProvisionWaitOptions
 * @property {(job: any) => void} [onUpdate]
 * @property {number} [pollMs]
 * @property {number} [maxWaitMs]
 */

/**
 * Provision and poll until 'ready' or 'error'. Calls onUpdate(job) on each tick.
 * Throws on error or timeout.
 *
 * @param {string} principal
 * @param {ProvisionWaitOptions} [options]
 */
export async function provisionAndWait(principal, {
  onUpdate, pollMs = 5_000, maxWaitMs = 600_000
} = {}) {
  const start = await provision(principal);
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

export { FleetApiError };
