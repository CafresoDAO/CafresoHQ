// ── CafresoAI OCI client ────────────────────────────────────────────────────
// Thin fetch wrapper that prepends the user's container endpoint URL and
// attaches their ecosystem-derived principal as `X-User-Principal`.
//
// serve.py reads X-User-Principal to scope all vault/state operations
// (when running in OCI Fleet mode behind the API Gateway, the gateway sets
// this header from the validated ICP token; in dev/self-deploy mode the
// frontend sets it directly).
import { get } from 'svelte/store';
import { endpointUrl } from '$lib/stores/endpoint.js';
import { currentPrincipal } from '$lib/stores/auth.js';

class EndpointError extends Error {
  constructor(message, { status = 0, body = null } = {}) {
    super(message);
    this.name   = 'EndpointError';
    this.status = status;
    this.body   = body;
  }
}

function _baseHeaders() {
  const h = { 'Accept': 'application/json' };
  const principal = currentPrincipal();
  if (principal) h['X-User-Principal'] = principal;
  return h;
}

function _baseUrl() {
  const url = get(endpointUrl);
  if (!url) throw new EndpointError('no endpoint configured');
  return url;
}

/** GET /<path>. Returns parsed JSON. */
export async function ociGet(path, { timeoutMs = 15000 } = {}) {
  const ctrl  = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(_baseUrl() + path, {
      method:  'GET',
      headers: _baseHeaders(),
      signal:  ctrl.signal
    });
    const text = await r.text();
    if (!r.ok) throw new EndpointError(`HTTP ${r.status}`,
      { status: r.status, body: text });
    return text ? JSON.parse(text) : null;
  } finally {
    clearTimeout(timer);
  }
}

/** POST /<path> with a JSON body. */
export async function ociPost(path, body, { timeoutMs = 60000 } = {}) {
  const ctrl  = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(_baseUrl() + path, {
      method: 'POST',
      headers: { ..._baseHeaders(), 'Content-Type': 'application/json' },
      body:    JSON.stringify(body ?? {}),
      signal:  ctrl.signal
    });
    const text = await r.text();
    if (!r.ok) throw new EndpointError(`HTTP ${r.status}`,
      { status: r.status, body: text });
    return text ? JSON.parse(text) : null;
  } finally {
    clearTimeout(timer);
  }
}

// ── Convenience wrappers (match serve.py routes) ────────────────────────────

/** GET /vault/list → array of {path,title,mtime,size}. */
export async function listVault() {
  return ociGet('/vault/list');
}

/** GET /vault/note?path=... → {content, path, title, mtime}. */
export async function readVaultNote(path) {
  return ociGet('/vault/note?path=' + encodeURIComponent(path));
}

/** Health probe convenience (the endpoint store also has one). */
export async function getHealth() {
  return ociGet('/health', { timeoutMs: 8000 });
}

export { EndpointError };
