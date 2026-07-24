// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — actor for the cafresohq_state on-chain per-user state canister
//
// Phase 2 (see docs/PHASE2_STATE_CANISTER.md). The BROWSER is the only caller of
// this canister: it holds the II delegation, so every call is authed by msg.caller
// and no method takes a principal argument. The OCI container never calls it.
//
// Methods (all caller-keyed):
//   putHqDoc / getHqDoc / listHqDocs / deleteHqDoc / hqVersion
//   putVaultMeta / putVaultChunk / sealVault / getVaultMeta / getVaultChunk / deleteVault
//   myUsage / setPlan / planConfigured
//
// Cloned from keysActor.js. The canister id is pinned after the first
// `dfx deploy cafresohq_state --network ic` (then add VITE_CANISTER_ID_CAFRESOHQ_STATE
// to the build env / canister_ids.json and the fallback below).
// ─────────────────────────────────────────────────────────────────────────────

import { Actor, HttpAgent } from '@dfinity/agent';
import { writable, get } from 'svelte/store';
import { authIdentity, isAuthenticated } from '$lib/stores/auth.js';
import { idlFactory as stateIdl } from '$lib/declarations/cafresohq_state/cafresohq_state.did.js';

// Deployed to mainnet 2026-06-24. Pinned so the canister id is available in the
// built bundle without relying on a build-time env var (Vite's default env prefix
// is VITE_, so a bare PUBLIC_/dfx-injected var isn't guaranteed to reach the build).
const MAINNET_CANISTER_ID =
  import.meta.env?.VITE_CANISTER_ID_CAFRESOHQ_STATE ||
  import.meta.env?.VITE_CAFRESOHQ_STATE_CANISTER_ID ||
  'ydacz-riaaa-aaaal-qxeja-cai';

const isLocalDev = typeof window !== 'undefined'
  && /localhost|127\.0\.0\.1/.test(window.location?.hostname);

const HOST = isLocalDev ? 'http://127.0.0.1:4943' : 'https://icp0.io';

export const stateCanisterId = writable(MAINNET_CANISTER_ID);

let _actor = null;
let _actorPrincipal = '';

/**
 * Build (or reuse) an authenticated cafresohq_state actor for the current user.
 * Throws if not signed in or the canister id is unset. Rebuilt on principal change.
 */
export async function getStateActor() {
  if (!get(isAuthenticated)) {
    throw new Error('Sign in with Internet Identity to access on-chain state');
  }
  const canisterId = get(stateCanisterId);
  if (!canisterId) {
    throw new Error('cafresohq_state canister id is not configured yet (deploy it first)');
  }
  const identity = get(authIdentity);
  // Belt-and-suspenders: `isAuthenticated` is derived from authStatus, which
  // can occasionally desync from the actual identity object (an II session
  // that expired between page loads, or a delegation-refresh race in
  // AuthClient). Calling the canister with an anonymous identity anyway
  // doesn't fail cleanly — the replica rejects it with a raw candid dump
  // (`sender: {"__principal__":"2vxsx-fae"}`) that looks like a crash. Catch
  // it here with an actionable message instead.
  if (!identity || identity.getPrincipal().isAnonymous()) {
    throw new Error('Your sign-in session looks stale — please sign out and sign in again.');
  }
  const principal = identity.getPrincipal().toText();
  if (_actor && _actorPrincipal === principal) return _actor;

  const agent = new HttpAgent({ identity, host: HOST });
  if (isLocalDev) {
    try { await agent.fetchRootKey(); }
    catch (e) { console.warn('[stateActor] fetchRootKey failed:', e); }
  }

  _actor = Actor.createActor(stateIdl, { agent, canisterId });
  _actorPrincipal = principal;
  return _actor;
}

/** Forget the cached actor (call on logout / principal change, alongside resetKeysActor). */
export function resetStateActor() {
  _actor = null;
  _actorPrincipal = '';
}

/** Whether a state-canister id is configured (i.e. the canister has been deployed). */
export function stateCanisterConfigured() {
  return !!get(stateCanisterId);
}
