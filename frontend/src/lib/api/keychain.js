// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — on-chain BYOK keychain
//
// The user's model/API keys, encrypted in the SHELL with the vetKeys-derived
// master key (same derivation as the vault: an attacker needs the user's II,
// not just canister or localStorage contents), stored as one HqDoc named
// 'keychain' in cafresohq_state. Sign in on any device → keys follow.
//
// Ciphertext layout: HqDoc body = utf8(base64(AES-GCM(master, 'hq-keychain-v1',
// JSON{provider: plaintextKey})))  — vaultKey.encryptBytes handles IV/HKDF.
// putKeychain does its own optimistic-versioning with ONE conflict retry that
// merges by provider (stateSync.pushHqDoc's array merge doesn't fit this doc).
// ─────────────────────────────────────────────────────────────────────────────

import { get } from 'svelte/store';
import { getStateActor, stateCanisterConfigured } from '$lib/api/stateActor.js';
import { getKeysActor } from '$lib/api/keysActor.js';
import { getMasterKey, encryptBytes, decryptBytes } from '$lib/crypto/vaultKey.js';
import { isAuthenticated } from '$lib/stores/auth.js';

const DOC_NAME = 'keychain';
const FILE_ID = 'hq-keychain-v1';

const utf8 = (s) => new TextEncoder().encode(s);
const fromUtf8 = (b) => new TextDecoder().decode(b instanceof Uint8Array ? b : new Uint8Array(b));
async function sha256(bytes) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
}

export function keychainAvailable() {
  return stateCanisterConfigured() && get(isAuthenticated);
}

async function master() {
  return getMasterKey(await getKeysActor());
}

async function decryptDoc(masterBytes, doc) {
  if (!doc) return {};
  try {
    const json = await decryptBytes(masterBytes, FILE_ID, fromUtf8(doc.body));
    const map = JSON.parse(new TextDecoder().decode(json));
    return map && typeof map === 'object' ? map : {};
  } catch (e) {
    console.warn('[keychain] decrypt failed (wrong identity or corrupt doc)', e);
    return {};
  }
}

/** → { keys: {provider: plaintext}, version } — {} / 0 when unset. */
export async function getKeychain() {
  if (!keychainAvailable()) return { keys: {}, version: 0 };
  const actor = await getStateActor();
  const d = await actor.getHqDoc(DOC_NAME);
  if (!d.length) return { keys: {}, version: 0 };
  const m = await master();
  return { keys: await decryptDoc(m, d[0]), version: Number(d[0].version) };
}

async function writeDoc(actor, m, keysMap, expectVersion) {
  const cipherB64 = await encryptBytes(m, FILE_ID, utf8(JSON.stringify(keysMap)));
  const body = utf8(cipherB64);
  return actor.putHqDoc(DOC_NAME, body, await sha256(body), BigInt(expectVersion));
}

/**
 * Upsert keys ({provider: plaintext}; empty-string value deletes the provider).
 * Merges over the current on-chain map; one conflict retry.
 * → { ok, version } | { ok:false, error }
 */
export async function putKeychain(updates) {
  if (!keychainAvailable()) return { ok: false, error: 'keychain unavailable (sign in required)' };
  try {
    const actor = await getStateActor();
    const m = await master();

    const applyUpdates = (base) => {
      const next = { ...base };
      for (const [provider, key] of Object.entries(updates || {})) {
        if (key) next[provider] = key;
        else delete next[provider];
      }
      return next;
    };

    const cur = await actor.getHqDoc(DOC_NAME);
    const curKeys = cur.length ? await decryptDoc(m, cur[0]) : {};
    let expect = cur.length ? Number(cur[0].version) : 0;
    let res = await writeDoc(actor, m, applyUpdates(curKeys), expect);

    if ('conflict' in res) {
      const remote = await actor.getHqDoc(DOC_NAME);
      const remoteKeys = remote.length ? await decryptDoc(m, remote[0]) : {};
      expect = remote.length ? Number(remote[0].version) : 0;
      res = await writeDoc(actor, m, applyUpdates(remoteKeys), expect);
    }
    if ('ok' in res) return { ok: true, version: Number(res.ok.version) };
    return { ok: false, error: JSON.stringify(Object.keys(res)) };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  }
}
