// ── CafresoAI workspace + session store ─────────────────────────────────────
// Manages workspace template catalog, active sessions, and launch state.
// Reuses fleet API client patterns from fleetClient.js.

import { writable, derived, get } from 'svelte/store';
import { fleetApiUrl, fleetApiAuthToken, FleetApiError } from '$lib/api/fleetClient.js';

// ── Stores ──────────────────────────────────────────────────────────────────

export const templates      = writable([]);
export const sessions       = writable([]);
export const activeCategory = writable('all');
export const searchQuery    = writable('');
export const launchingId    = writable(null);   // template id currently launching

const browser = () => typeof window !== 'undefined';

// Persist sessions to localStorage for fast dock rendering on reload
const SESSIONS_KEY = 'cafresoai.active_sessions';
if (browser()) {
  try {
    const cached = localStorage.getItem(SESSIONS_KEY);
    if (cached) sessions.set(JSON.parse(cached));
  } catch (_) { /* ignore */ }
  sessions.subscribe((s) => {
    try { localStorage.setItem(SESSIONS_KEY, JSON.stringify(s)); }
    catch (_) { /* private mode */ }
  });
}

// ── Categories ──────────────────────────────────────────────────────────────

export const categories = [
  { id: 'all',          label: 'All' },
  { id: 'ai',           label: 'AI' },
  { id: 'desktops',     label: 'Desktops' },
  { id: 'productivity', label: 'Productivity' },
  { id: 'apps',         label: 'Apps' },
  { id: 'servers',      label: 'Servers & Apps' },
  { id: 'custom',       label: 'Custom' },
];

// ── Derived stores ──────────────────────────────────────────────────────────

export const filteredTemplates = derived(
  [templates, activeCategory, searchQuery],
  ([$templates, $cat, $q]) => {
    let list = $templates;
    if ($cat !== 'all') {
      list = list.filter((t) => t.category === $cat);
    }
    if ($q.trim()) {
      const q = $q.toLowerCase().trim();
      list = list.filter((t) =>
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        (t.tags || []).some((tag) => tag.toLowerCase().includes(q))
      );
    }
    // enabled first, then by sort_order
    return list.sort((a, b) => {
      if (a.enabled !== b.enabled) return a.enabled ? -1 : 1;
      return (a.sort_order ?? 99) - (b.sort_order ?? 99);
    });
  }
);

export const activeSessions = derived(sessions, ($s) =>
  $s.filter((s) => s.status === 'running' || s.status === 'starting')
);

// ── Internal fetch (mirrors fleetClient.js pattern) ─────────────────────────

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

/** Fetch workspace template catalog from fleet API.
 *  Passes the caller's ICP principal so the server filters allowed_principals.
 *  Falls back to bundled workspaces.json if the API is unreachable (dev mode). */
export async function fetchTemplates(principal = '') {
  try {
    const qs   = principal ? `?principal=${encodeURIComponent(principal)}` : '';
    const data = await _fetch(`/workspaces/templates${qs}`, { timeoutMs: 10_000 });
    if (data?.templates) {
      templates.set(data.templates);
    }
    return data;
  } catch (_) {
    // Dev fallback: load from static JSON so the gallery is usable offline
    if (get(templates).length === 0) {
      try {
        const r = await fetch('/workspaces-catalog.json');
        const list = await r.json();
        if (Array.isArray(list) && list.length > 0) {
          templates.set(list);
          return { templates: list, categories: {}, total: list.length };
        }
      } catch (__) { /* no fallback available */ }
    }
    return null;
  }
}

/** Fetch sessions for a principal. */
export async function fetchSessions(principal) {
  if (!principal) return;
  const data = await _fetch(
    '/sessions?principal=' + encodeURIComponent(principal),
    { timeoutMs: 10_000 }
  );
  if (data?.sessions) {
    sessions.set(data.sessions);
  }
  return data;
}

/** Get a single session by ID. */
export async function getSession(sessionId) {
  return _fetch('/sessions/' + encodeURIComponent(sessionId), { timeoutMs: 8_000 });
}

/**
 * Launch a workspace. For canister type, returns immediately.
 * For OCI/Hyper-V, polls until session is running.
 * @param {string} principal
 * @param {string} templateId
 * @param {object} [opts]
 * @param {(session: any) => void} [opts.onUpdate]
 * @param {number} [opts.pollMs]
 * @param {number} [opts.maxWaitMs]
 */
export async function launchWorkspace(principal, templateId, {
  onUpdate, pollMs = 4_000, maxWaitMs = 600_000
} = {}) {
  launchingId.set(templateId);
  try {
    const start = await _fetch('/sessions/launch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ principal, template_id: templateId }),
      timeoutMs: 15_000,
    });

    onUpdate?.(start);

    // Canister or already-running sessions return immediately
    if (start.status === 'running') {
      _upsertSession(start);
      return start;
    }

    // Poll until running or error
    const sessionId = start.session_id;
    const deadline = Date.now() + maxWaitMs;

    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, pollMs));
      const session = await getSession(sessionId);
      onUpdate?.(session);

      if (session.status === 'running') {
        _upsertSession(session);
        return session;
      }
      if (session.status === 'error') {
        throw new FleetApiError(session.error || 'launch failed',
          { status: 500, body: session });
      }
    }

    throw new FleetApiError('launch timed out', { status: 504, body: { sessionId } });
  } finally {
    launchingId.set(null);
  }
}

/** Stop a running session. */
export async function stopSession(sessionId) {
  const result = await _fetch('/sessions/' + encodeURIComponent(sessionId) + '/stop', {
    method: 'POST',
    timeoutMs: 15_000,
  });
  _upsertSession({ session_id: sessionId, status: 'stopping' });
  return result;
}

/** Delete/terminate a session. */
export async function deleteSession(sessionId) {
  const result = await _fetch('/sessions/' + encodeURIComponent(sessionId), {
    method: 'DELETE',
    timeoutMs: 15_000,
  });
  sessions.update((s) => s.filter((x) => x.session_id !== sessionId));
  return result;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function _upsertSession(session) {
  sessions.update((list) => {
    const idx = list.findIndex((s) => s.session_id === session.session_id);
    if (idx >= 0) {
      list = [...list];
      list[idx] = { ...list[idx], ...session };
    } else {
      list = [...list, session];
    }
    return list;
  });
}

/**
 * Find a running session for a given template (for "Connect" vs "Launch").
 * @param {string} templateId
 * @returns {object|null}
 */
export function runningSessionForTemplate(templateId) {
  const all = get(sessions);
  return all.find(
    (s) => s.template_id === templateId &&
           (s.status === 'running' || s.status === 'starting')
  ) || null;
}

// ── Custom template CRUD (Bring Your Own VM) ──────────────────────────────

/**
 * Register a user-onboarded VM/endpoint as a custom workspace template.
 * @param {{ name: string, host: string, port: number, protocol?: string, icon?: string, description?: string, principal?: string }} opts
 */
export async function createCustomTemplate(opts) {
  const data = await _fetch('/workspaces/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
    timeoutMs: 10_000,
  });
  // Append the new template to the store
  if (data?.id) {
    templates.update((list) => [...list, data]);
  }
  return data;
}

/**
 * Delete a custom (user-onboarded) template.
 * @param {string} templateId — must start with "custom-"
 */
export async function deleteCustomTemplate(templateId) {
  const result = await _fetch('/workspaces/templates/' + encodeURIComponent(templateId), {
    method: 'DELETE',
    timeoutMs: 10_000,
  });
  templates.update((list) => list.filter((t) => t.id !== templateId));
  return result;
}
