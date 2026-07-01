// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — Publish-to-Canister client
//
// Sites are hosted IN the cafresohq_state canister (no separate canister — same
// per-caller isolation, already deployed + funded). This module just wraps the
// site methods on the state actor and builds the public URL. Served at
//   https://<cafresohq_state>.icp0.io/<principalText>/<project>/
// ─────────────────────────────────────────────────────────────────────────────

import { get } from 'svelte/store';
import { authIdentity } from '$lib/stores/auth.js';
import { getStateActor, stateCanisterConfigured, stateCanisterId } from '$lib/api/stateActor.js';

/** Publish is available whenever the (already-deployed) state canister is configured. */
export function sitesConfigured() { return stateCanisterConfigured(); }

/** Public URL for a published project on the state canister's http_request host. */
export function sitesPublicUrl(principalText, project) {
  return `https://${get(stateCanisterId)}.icp0.io/${principalText}/${encodeURIComponent(project)}/`;
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/**
 * Publish a collected site under the signed-in user's namespace.
 * `files` = [{ path, contentType, b64 }]. Drops the old project first, uploads
 * each file, returns { url, files: n, skipped: [...] }. Files > ~2 MiB skipped.
 */
export async function publishSiteToCanister({ project, files }) {
  const actor = await getStateActor();
  const principalText = get(authIdentity).getPrincipal().toText();
  await actor.deleteSite(project); // clear stale files so removed ones don't linger
  let ok = 0;
  const skipped = [];
  for (const f of files || []) {
    const bytes = b64ToBytes(f.b64 || '');
    if (bytes.length > 2_000_000) { skipped.push(f.path); continue; }
    const res = await actor.putSiteFile(project, f.path, f.contentType || 'application/octet-stream', bytes);
    if ('ok' in res) ok += 1; else skipped.push(`${f.path} (${res.err})`);
  }
  return { url: sitesPublicUrl(principalText, project), files: ok, skipped };
}
