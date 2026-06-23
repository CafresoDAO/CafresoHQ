// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — Phase 2 browser sync layer (cafresohq_state)
//
// The browser (which holds the II delegation) couriers durable state to/from the
// on-chain state canister. See docs/PHASE2_STATE_CANISTER.md §4.
//
// EVERYTHING here is gated behind PUBLIC_STATE_CANISTER:
//   'off'     (default) → all functions are no-ops; ZERO behavior change.
//   'mirror'  → dual-write to the canister after the container write (non-fatal).
//   'primary' → canister is authoritative; container cache hydrates from it.
// It is also a no-op until the canister id is configured (post-deploy).
//
// Vault objects (base64 ciphertext blobs, never decrypted here) are chunked into
// ≤1.9 MiB slices: putVaultMeta → putVaultChunk×N → sealVault. HQ docs (small
// JSON) are written with optimistic concurrency + an LWW-by-id merge on conflict.
// ─────────────────────────────────────────────────────────────────────────────

import { getStateActor, stateCanisterConfigured } from '$lib/api/stateActor.js';

const MODE = (import.meta.env?.PUBLIC_STATE_CANISTER || 'off').toLowerCase();
const CHUNK = 1_900_000; // bytes; must stay ≤ canister MAX_CHUNK_BYTES

export function stateMode() { return MODE; }
/** True only when sync is switched on AND the canister has been deployed. */
export function stateEnabled() { return MODE !== 'off' && stateCanisterConfigured(); }
export function statePrimary() { return MODE === 'primary' && stateCanisterConfigured(); }

// ── byte helpers ─────────────────────────────────────────────────────────────
function b64ToBytes(b64) {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
function bytesToB64(bytes) {
  let bin = '';
  const STEP = 0x8000; // avoid arg-length limits on String.fromCharCode
  for (let i = 0; i < bytes.length; i += STEP) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + STEP));
  }
  return btoa(bin);
}
async function sha256(bytes) {
  return new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
}
const utf8 = (s) => new TextEncoder().encode(s);
const fromUtf8 = (b) => new TextDecoder().decode(b instanceof Uint8Array ? b : new Uint8Array(b));

// ── Vault object transport ───────────────────────────────────────────────────
/**
 * Mirror one vault object (base64 ciphertext) on-chain: chunk → meta → chunks → seal.
 * Non-fatal: returns {ok:true,version} or {ok:false,error}. Safe to call fire-and-forget.
 */
export async function mirrorVaultObject(objId, ciphertextB64) {
  if (!stateEnabled()) return { ok: false, skipped: true };
  try {
    const actor = await getStateActor();
    const bytes = b64ToBytes(ciphertextB64);
    const count = Math.max(1, Math.ceil(bytes.length / CHUNK));
    const digest = await sha256(bytes);
    // expectVersion = current sealed version (0 if new).
    const curMeta = await actor.getVaultMeta(objId);
    const expect = curMeta.length ? Number(curMeta[0].version) : 0;
    const metaRes = await actor.putVaultMeta(objId, BigInt(bytes.length), BigInt(count), digest, BigInt(expect));
    if (!('ok' in metaRes)) return { ok: false, error: JSON.stringify(metaRes) };
    const version = metaRes.ok.version;
    for (let ix = 0; ix < count; ix++) {
      const slice = bytes.subarray(ix * CHUNK, Math.min((ix + 1) * CHUNK, bytes.length));
      const cRes = await actor.putVaultChunk(objId, version, BigInt(ix), slice);
      if (!('ok' in cRes)) return { ok: false, error: `chunk ${ix}: ${JSON.stringify(cRes)}` };
    }
    const sealRes = await actor.sealVault(objId, version);
    if (!('ok' in sealRes)) return { ok: false, error: JSON.stringify(sealRes) };
    return { ok: true, version: Number(version) };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  }
}

/** Read a vault object from the canister, reassembled to base64 ciphertext, or null. */
export async function fetchVaultObject(objId) {
  if (!stateEnabled()) return null;
  try {
    const actor = await getStateActor();
    const metaOpt = await actor.getVaultMeta(objId);
    if (!metaOpt.length) return null;
    const count = Number(metaOpt[0].chunkCount);
    const parts = [];
    let total = 0;
    for (let ix = 0; ix < count; ix++) {
      const cOpt = await actor.getVaultChunk(objId, BigInt(ix));
      if (!cOpt.length) return null; // incomplete
      const u = cOpt[0] instanceof Uint8Array ? cOpt[0] : new Uint8Array(cOpt[0]);
      parts.push(u); total += u.length;
    }
    const all = new Uint8Array(total);
    let off = 0;
    for (const p of parts) { all.set(p, off); off += p.length; }
    return bytesToB64(all);
  } catch (e) {
    console.warn('[stateSync] fetchVaultObject failed', objId, e);
    return null;
  }
}

export async function deleteVaultObject(objId) {
  if (!stateEnabled()) return { ok: false, skipped: true };
  try {
    const actor = await getStateActor();
    await actor.deleteVault(objId);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  }
}

// ── HQ doc transport (small JSON; optimistic concurrency + merge) ─────────────
/**
 * Push one HQ doc (JSON text) on-chain. On version conflict, merges arrays by id
 * (LWW on updatedAt, honoring tombstones) and retries once. Non-fatal.
 */
export async function pushHqDoc(name, jsonText) {
  if (!stateEnabled()) return { ok: false, skipped: true };
  try {
    const actor = await getStateActor();
    const writeOnce = async (text, expect) => {
      const bytes = utf8(text);
      return actor.putHqDoc(name, bytes, await sha256(bytes), BigInt(expect));
    };
    const cur = await actor.getHqDoc(name);
    let expect = cur.length ? Number(cur[0].version) : 0;
    let res = await writeOnce(jsonText, expect);
    if ('conflict' in res) {
      const remote = await actor.getHqDoc(name);
      const remoteText = remote.length ? fromUtf8(remote[0].body) : '[]';
      const merged = mergeJsonById(jsonText, remoteText);
      res = await writeOnce(merged, remote.length ? Number(remote[0].version) : 0);
      if ('ok' in res) return { ok: true, version: Number(res.ok.version), merged: true, mergedText: merged };
    }
    if ('ok' in res) return { ok: true, version: Number(res.ok.version) };
    return { ok: false, error: JSON.stringify(res) };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  }
}

/** Pull one HQ doc's JSON text from the canister (or null). */
export async function pullHqDoc(name) {
  if (!stateEnabled()) return null;
  try {
    const actor = await getStateActor();
    const d = await actor.getHqDoc(name);
    return d.length ? fromUtf8(d[0].body) : null;
  } catch (e) {
    console.warn('[stateSync] pullHqDoc failed', name, e);
    return null;
  }
}

/** List on-chain HQ doc summaries (for boot hydrate). */
export async function listHqDocs() {
  if (!stateEnabled()) return [];
  try { return await (await getStateActor()).listHqDocs(); }
  catch (e) { console.warn('[stateSync] listHqDocs failed', e); return []; }
}

// ── merge ────────────────────────────────────────────────────────────────────
/**
 * 3-way-ish merge of two JSON arrays of records keyed by `id`:
 *  - union by id; per id keep the higher `updatedAt` (last-writer-wins)
 *  - a record with `deleted:true` / `tombstone:true` is a tombstone and wins ties
 * Non-array or unparseable inputs fall back to remote (canister authoritative).
 */
export function mergeJsonById(localText, remoteText) {
  let local, remote;
  try { local = JSON.parse(localText); } catch { return remoteText; }
  try { remote = JSON.parse(remoteText); } catch { return localText; }
  if (!Array.isArray(local) || !Array.isArray(remote)) return remoteText; // canister wins
  const byId = new Map();
  const consider = (rec) => {
    if (!rec || rec.id == null) return;
    const prev = byId.get(rec.id);
    if (!prev) { byId.set(rec.id, rec); return; }
    const a = Number(prev.updatedAt || 0), b = Number(rec.updatedAt || 0);
    if (b > a) byId.set(rec.id, rec);
    else if (b === a && (rec.deleted || rec.tombstone)) byId.set(rec.id, rec); // tombstone wins ties
  };
  for (const r of remote) consider(r);
  for (const r of local) consider(r);
  return JSON.stringify([...byId.values()]);
}

// Exposed for tests.
export const _internals = { b64ToBytes, bytesToB64, CHUNK };
