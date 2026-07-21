// ── CafresoAI admin store ────────────────────────────────────────────────────
// Dashboard metrics, session management, infrastructure health.
// Gated on isAdmin — checks principal against FLEET_ADMIN_PRINCIPALS.

import { writable, derived, get } from 'svelte/store';
import { principalText } from '$lib/stores/auth.js';
import { fleetApiUrl, fleetApiAuthToken, FleetApiError } from '$lib/api/fleetClient.js';

// ── Admin auth ──────────────────────────────────────────────────────────────

/** List of admin principals (set from env or hardcoded for now). */
const ADMIN_PRINCIPALS = [
  // Anthony's ecosystem principal (shared across Banking.Brave / Cafreso / CafresoAI)
  // Add more principals here as needed
];

const browser = () => typeof window !== 'undefined';
const ADMIN_OVERRIDE_KEY = 'cafresoai.admin_override';

/** True if the current user has been verified as admin by the API. */
export const isAdminVerified = writable(false);

/**
 * Derived: true if current principal is in local admin list OR the API
 * has confirmed admin status. For production, always verify via API.
 */
export const isAdmin = derived(
  [principalText, isAdminVerified],
  ([$p, $verified]) => {
    if ($verified) return true;
    if (ADMIN_PRINCIPALS.includes($p)) return true;
    // Dev override: localStorage flag for testing
    if (browser()) {
      try { return localStorage.getItem(ADMIN_OVERRIDE_KEY) === 'true'; }
      catch (_) { /* private mode */ }
    }
    return false;
  }
);

// ── Stores ──────────────────────────────────────────────────────────────────

export const dashboardMetrics   = writable(null);
export const allSessions        = writable([]);
export const infrastructure     = writable(null);
export const adminLoading       = writable(false);
export const adminError         = writable('');
export const adminTab           = writable('dashboard');

// ── Internal fetch ──────────────────────────────────────────────────────────

async function _fetch(path, opts = {}) {
  const url = get(fleetApiUrl).replace(/\/+$/, '') + path;
  const tok = get(fleetApiAuthToken);
  const headers = { 'Accept': 'application/json', ...(opts.headers || {}) };
  if (tok) headers['X-Fleet-Auth'] = tok;
  headers['X-User-Principal'] = get(principalText) || '';
  const ctrl  = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 15_000);
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

/** Fetch aggregate dashboard metrics. */
export async function fetchDashboard() {
  adminLoading.set(true);
  adminError.set('');
  try {
    const data = await _fetch('/admin/dashboard', { timeoutMs: 10_000 });
    dashboardMetrics.set(data);
    return data;
  } catch (e) {
    adminError.set(e.message || 'Failed to load dashboard');
    return null;
  } finally {
    adminLoading.set(false);
  }
}

/** Fetch all sessions across all users. */
export async function fetchAllSessions() {
  try {
    const data = await _fetch('/admin/sessions', { timeoutMs: 10_000 });
    if (data?.sessions) {
      allSessions.set(data.sessions);
    }
    return data;
  } catch (e) {
    adminError.set(e.message || 'Failed to load sessions');
    return null;
  }
}

/** Fetch infrastructure health (Hyper-V, OCI, ICP status). */
export async function fetchInfrastructure() {
  try {
    const data = await _fetch('/admin/infrastructure', { timeoutMs: 10_000 });
    infrastructure.set(data);
    return data;
  } catch (e) {
    adminError.set(e.message || 'Failed to load infrastructure');
    return null;
  }
}

/** Force-kill a session (admin only). */
export async function killSession(sessionId) {
  const result = await _fetch(`/admin/sessions/${encodeURIComponent(sessionId)}/kill`, {
    method: 'POST',
    timeoutMs: 15_000,
  });
  // Remove from local store
  allSessions.update((list) => list.filter((s) => s.session_id !== sessionId));
  return result;
}

/** Verify admin status via API. */
export async function verifyAdmin() {
  try {
    const data = await _fetch('/admin/verify', { timeoutMs: 5_000 });
    isAdminVerified.set(data?.is_admin === true);
    return data?.is_admin === true;
  } catch (_) {
    isAdminVerified.set(false);
    return false;
  }
}
