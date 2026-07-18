// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — actor for the cafresohq_keys vetKeys canister
//
// Builds an authenticated actor (using the user's II identity) that can call:
//   • vault_public_key()        — query, returns canister BLS pubkey
//   • vault_encrypted_key(pk)   — update, ~26B cycles, returns user's enc key
//   • cycle_balance()           — query, diagnostics
//
// dfx-generated declarations live at $lib/declarations/cafresohq_keys/ —
// regenerated on every `dfx deploy` via `node_compatibility: true` in dfx.json.
// ─────────────────────────────────────────────────────────────────────────────

import { Actor, HttpAgent } from '@dfinity/agent';
import { writable, get } from 'svelte/store';
import { authIdentity, isAuthenticated } from '$lib/stores/auth.js';
import { idlFactory as keysIdl } from '$lib/declarations/cafresohq_keys/cafresohq_keys.did.js';

// Mainnet canister id is injected by dfx into frontend/.env at build time
// as VITE_CAFRESOHQ_KEYS_CANISTER_ID. Falls back to canister_ids.json.
const MAINNET_CANISTER_ID =
  import.meta.env?.VITE_CAFRESOHQ_KEYS_CANISTER_ID ||
  import.meta.env?.VITE_CANISTER_ID_CAFRESOHQ_KEYS ||
  // Pinned mainnet id (deploy: 2026-05-08, controllers: tzw3r-vl... + xip3r-mh...)
  'vhw7q-lqaaa-aaaab-agthq-cai';

const isLocalDev = typeof window !== 'undefined'
  && /localhost|127\.0\.0\.1/.test(window.location?.hostname);

const HOST = isLocalDev ? 'http://127.0.0.1:4943' : 'https://icp0.io';

export const keysCanisterId = writable(MAINNET_CANISTER_ID);

let _actor = null;
let _actorPrincipal = '';

/**
 * Build (or reuse) an authenticated keys-canister actor for the current user.
 * Throws if not signed in. The actor is rebuilt when the principal changes.
 */
export async function getKeysActor() {
  if (!get(isAuthenticated)) {
    throw new Error('Sign in with Internet Identity to access vault keys');
  }
  const identity = get(authIdentity);
  // See stateActor.js's getStateActor for why this check exists: isAuthenticated
  // can desync from the actual identity object, and calling the canister with
  // an anonymous identity anyway fails as a raw candid dump, not a clean error.
  // This is the vetKeys path — worth being just as defensive here as there.
  if (!identity || identity.getPrincipal().isAnonymous()) {
    throw new Error('Your sign-in session looks stale — please sign out and sign in again.');
  }
  const principal = identity.getPrincipal().toText();
  if (_actor && _actorPrincipal === principal) return _actor;

  const canisterId = get(keysCanisterId);
  if (!canisterId) {
    throw new Error('cafresohq_keys canister id is not configured');
  }

  const agent = new HttpAgent({ identity, host: HOST });

  // Local replica needs root key fetched. NEVER fetch on mainnet (security).
  if (isLocalDev) {
    try { await agent.fetchRootKey(); }
    catch (e) { console.warn('[keysActor] fetchRootKey failed:', e); }
  }

  _actor = Actor.createActor(keysIdl, { agent, canisterId });
  _actorPrincipal = principal;
  return _actor;
}

/** Forget the cached actor (call on logout / principal change). */
export function resetKeysActor() {
  _actor = null;
  _actorPrincipal = '';
}
