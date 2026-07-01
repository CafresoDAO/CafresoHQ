// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — actor + client for the cafresohq_sites public asset canister
//
// ONE HQ-owned, DAO-funded canister that hosts every user's published sites.
// The authenticated shell (which holds II) is the only caller: putSiteFile is
// keyed by msg.caller, so a user can only write their own namespace. The site
// is then reachable PUBLICLY at
//   https://<sites-canister>.icp0.io/<principalText>/<project>/
//
// Gated on a configured canister id (dfx injects it after the founder deploys +
// funds the canister once). Until then sitesConfigured() is false and callers
// fall back to the container /fs/site preview link.
// ─────────────────────────────────────────────────────────────────────────────

import { Actor, HttpAgent } from '@dfinity/agent';
import { get } from 'svelte/store';
import { authIdentity, isAuthenticated } from '$lib/stores/auth.js';
import { idlFactory as sitesIdl } from '$lib/declarations/cafresohq_sites/cafresohq_sites.did.js';

// Pin here after `dfx deploy cafresohq_sites --network ic` (dfx also injects
// VITE_CANISTER_ID_CAFRESOHQ_SITES into the build env).
const SITES_CANISTER_ID =
  import.meta.env?.VITE_CANISTER_ID_CAFRESOHQ_SITES ||
  import.meta.env?.VITE_CAFRESOHQ_SITES_CANISTER_ID ||
  null;

const isLocalDev =
  typeof window !== 'undefined' && /localhost|127\.0\.0\.1/.test(window.location?.hostname);
const HOST = isLocalDev ? 'http://127.0.0.1:4943' : 'https://icp0.io';

export function sitesConfigured() { return !!SITES_CANISTER_ID; }
export function sitesCanisterId() { return SITES_CANISTER_ID; }

let _actor = null;
let _actorPrincipal = '';
export async function getSitesActor() {
  if (!SITES_CANISTER_ID) throw new Error('cafresohq_sites not deployed yet');
  if (!get(isAuthenticated)) throw new Error('Sign in with Internet Identity');
  const identity = get(authIdentity);
  const principal = identity.getPrincipal().toText();
  if (_actor && _actorPrincipal === principal) return _actor;
  const agent = new HttpAgent({ identity, host: HOST });
  if (isLocalDev) { try { await agent.fetchRootKey(); } catch (e) { console.warn('[sitesActor] rootKey', e); } }
  _actor = Actor.createActor(sitesIdl, { agent, canisterId: SITES_CANISTER_ID });
  _actorPrincipal = principal;
  return _actor;
}
export function resetSitesActor() { _actor = null; _actorPrincipal = ''; }

/** Public URL for a published project (raw disabled → served via boundary node). */
export function sitesPublicUrl(principalText, project) {
  return `https://${SITES_CANISTER_ID}.icp0.io/${principalText}/${encodeURIComponent(project)}/`;
}

function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/**
 * Publish a collected site to the canister under the signed-in user's namespace.
 * `files` = [{ path, contentType, b64 }]. Drops the old project first, uploads
 * each file, returns { url, files: n }. Files > ~2 MiB are skipped (reported).
 */
export async function publishSiteToCanister({ project, files }) {
  const actor = await getSitesActor();
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
