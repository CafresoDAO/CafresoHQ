// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — vault crypto module (vetKeys + AES-GCM + AES-SIV-style names)
//
// Zero-knowledge vault. The user's master key is derived via ICP vetKeys keyed
// on their Internet Identity principal. Per-file content keys and per-name
// deterministic keys are derived from the master via HKDF.
//
// Threat model
// ────────────
//   • Anthony (canister controller, OCI account holder): SHOULD NOT be able
//     to read any vault content, file names, or directory structure.
//   • OCI infrastructure compromise: SHOULD NOT yield any plaintext.
//   • ICP subnet node compromise (single node): SHOULD NOT yield any key.
//     vetKeys threshold-derives keys; no node sees plaintext.
//   • User's browser session: holds plaintext keys in memory + sessionStorage.
//     Cleared on logout.
//
// Three layers of derivation
// ──────────────────────────
//   1. Vault master key (32 bytes) — vetKeys-derived from ICP principal
//   2. Per-file content key (AES-GCM, 256-bit) — HKDF(master, salt=file_id)
//   3. Name encryption key (AES-GCM, 256-bit) — HKDF(master, salt='names-v1')
//      Used with deterministic IV derived from name → encrypted index entries
//      with stable ciphertexts (so same name → same blob, enabling lookup).
//
// File IDs are random 16-byte hex (no relation to name) — the encrypted
// `index.bin` file maps id → metadata (name, path, size, mtime). Without
// the master key, the file system on the container is just `f-<hex>.bin`
// blobs and one `index.bin` blob — no information leakage.
// ─────────────────────────────────────────────────────────────────────────────

import {
  TransportSecretKey,
  DerivedPublicKey,
  EncryptedVetKey,
} from '@dfinity/vetkeys';
import { get } from 'svelte/store';
import { authIdentity, principalText, currentPrincipal } from '$lib/stores/auth.js';

const SESSION_CACHE_KEY = 'cafresohq.vault_master_key';
const SESSION_PRINCIPAL_KEY = 'cafresohq.vault_master_principal';

let _masterKeyCache = null;     // Uint8Array — in-memory copy of the derived master
let _cachedActor = null;        // memoised cafresohq_keys actor

// ── Helpers ──────────────────────────────────────────────────────────────────

const browser = () => typeof window !== 'undefined';

function hex(bytes) {
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}
function unhex(s) {
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.substr(i * 2, 2), 16);
  return out;
}
function b64encode(bytes) {
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}
function b64decode(s) {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

// 16-byte random hex — collision probability negligible at vault scale.
export function newFileId() {
  const buf = new Uint8Array(16);
  crypto.getRandomValues(buf);
  return hex(buf);
}

// ── HKDF derivation ──────────────────────────────────────────────────────────

async function hkdfDerive(masterBytes, info, saltBytes, lengthBits = 256) {
  const masterKey = await crypto.subtle.importKey(
    'raw', masterBytes, 'HKDF', false, ['deriveBits']
  );
  return crypto.subtle.deriveBits(
    {
      name: 'HKDF',
      hash: 'SHA-256',
      salt: saltBytes,
      info: new TextEncoder().encode(info),
    },
    masterKey,
    lengthBits
  );
}

async function deriveFileContentKey(masterBytes, fileId) {
  const salt = unhex(fileId);
  const bits = await hkdfDerive(masterBytes, 'cafresohq-vault-content-v1', salt);
  return crypto.subtle.importKey('raw', bits, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
}

// Deterministic name encryption: same plaintext name → same ciphertext.
// Achieved by deriving the IV from HMAC(master, "iv:" + name) instead of
// random. Allows lookups against the encrypted index without decrypting.
async function deriveNameKey(masterBytes) {
  const bits = await hkdfDerive(
    masterBytes,
    'cafresohq-vault-names-v1',
    new TextEncoder().encode('cafresohq-vault-names-salt-v1')
  );
  return crypto.subtle.importKey('raw', bits, { name: 'AES-GCM' }, false, ['encrypt', 'decrypt']);
}

async function deriveNameMacKey(masterBytes) {
  const bits = await hkdfDerive(
    masterBytes,
    'cafresohq-vault-name-mac-v1',
    new TextEncoder().encode('cafresohq-vault-name-mac-salt-v1')
  );
  return crypto.subtle.importKey('raw', bits, { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
}

async function deterministicNameIv(masterBytes, name) {
  const macKey = await deriveNameMacKey(masterBytes);
  const sig = await crypto.subtle.sign('HMAC', macKey, new TextEncoder().encode(name));
  return new Uint8Array(sig).slice(0, 12);
}

// ── Master key lifecycle ─────────────────────────────────────────────────────

/**
 * Hydrate from sessionStorage if a master key was previously derived for the
 * current principal. Returns true if hydration succeeded.
 */
function _tryHydrate() {
  if (!browser() || _masterKeyCache) return false;
  try {
    const savedPrincipal = sessionStorage.getItem(SESSION_PRINCIPAL_KEY);
    const savedB64 = sessionStorage.getItem(SESSION_CACHE_KEY);
    if (savedPrincipal && savedB64 && savedPrincipal === get(principalText)) {
      _masterKeyCache = b64decode(savedB64);
      return true;
    }
  } catch (_) { /* ignore */ }
  return false;
}

function _persist(masterBytes) {
  if (!browser()) return;
  try {
    sessionStorage.setItem(SESSION_CACHE_KEY, b64encode(masterBytes));
    sessionStorage.setItem(SESSION_PRINCIPAL_KEY, get(principalText));
  } catch (_) { /* private mode — keep in memory only */ }
}

/**
 * Forget the cached master key — call on logout or principal change.
 * Does NOT delete vault files, just the local key copy.
 */
export function forgetMasterKey() {
  _masterKeyCache = null;
  if (!browser()) return;
  try {
    sessionStorage.removeItem(SESSION_CACHE_KEY);
    sessionStorage.removeItem(SESSION_PRINCIPAL_KEY);
  } catch (_) { /* ignore */ }
}

/**
 * Derive (or fetch from cache) the vault master key for the signed-in user.
 * One vetKeys call per session — cached in sessionStorage thereafter.
 *
 * @param {any} keysActor  The cafresohq_keys actor (built with the user's identity)
 * @returns {Promise<Uint8Array>} 32-byte master key
 */
export async function getMasterKey(keysActor) {
  if (_masterKeyCache) return _masterKeyCache;
  if (_tryHydrate()) return _masterKeyCache;
  if (!keysActor) throw new Error('cafresohq_keys actor required to derive master key');

  const principal = currentPrincipal();
  if (!principal) throw new Error('sign in with Internet Identity first');

  // 1. Generate ephemeral transport keypair (BLS12-381 G1)
  const tsk = TransportSecretKey.random();

  // 2. Ask the canister to derive + encrypt the user's master key under our transport pubkey
  const encryptedKeyBytes = await keysActor.vault_encrypted_key(tsk.publicKeyBytes());
  const canisterPubKeyBytes = await keysActor.vault_public_key();

  // 3. Wrap the canister's outputs in their typed wrappers, then decryptAndVerify.
  //    This both decrypts and verifies the BLS signature underlying the vetKey.
  //    `input` MUST match what the canister passed to `vetkd_derive_key.input` —
  //    we use the caller's principal bytes (Principal.toBlob(caller) in the
  //    canister maps to identity.getPrincipal().toUint8Array() in the client).
  const principalBytes = get(authIdentity).getPrincipal().toUint8Array();
  const dpk = DerivedPublicKey.deserialize(new Uint8Array(canisterPubKeyBytes));
  const enc = new EncryptedVetKey(new Uint8Array(encryptedKeyBytes));
  const vetKey = enc.decryptAndVerify(tsk, dpk, principalBytes);

  // 4. Derive a 32-byte symmetric master key from the vetKey via HKDF.
  //    The domain separator scopes this material to the vault subsystem so
  //    future features (BYOK, messaging) using the same vetKey produce
  //    independent keys — see vetKeys docs "Security Considerations".
  const master = vetKey.deriveSymmetricKey('cafresohq-vault-master-v1', 32);

  _masterKeyCache = master;
  _persist(master);
  return master;
}

// ── File content encryption ──────────────────────────────────────────────────
//
// Two layers:
//   • encryptBytes / decryptBytes — work on raw Uint8Array (for binary
//     uploads: images, PDFs, zips, anything)
//   • encryptFile / decryptFile  — thin wrappers that text-encode (for
//     Markdown notes via the editor)
//
// Both produce {iv (12) || AES-GCM ciphertext+tag} encoded as base64.
// AES-GCM IV is fresh random per write — same plaintext encrypts to a
// different blob each time (semantic security).

/** Encrypt arbitrary bytes for a given file ID. Returns base64 ciphertext. */
export async function encryptBytes(masterBytes, fileId, plaintext) {
  if (!(plaintext instanceof Uint8Array)) {
    throw new TypeError('encryptBytes expects Uint8Array plaintext');
  }
  const key = await deriveFileContentKey(masterBytes, fileId);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const plainBuffer = new Uint8Array(plaintext).buffer;
  const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plainBuffer);
  const combined = new Uint8Array(iv.length + ct.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(ct), iv.length);
  return b64encode(combined);
}

/** Decrypt base64 ciphertext for a given file ID. Returns Uint8Array plaintext. */
export async function decryptBytes(masterBytes, fileId, ciphertextB64) {
  const key = await deriveFileContentKey(masterBytes, fileId);
  const combined = b64decode(ciphertextB64);
  if (combined.length < 12 + 16) throw new Error('ciphertext too short');
  const iv = combined.slice(0, 12);
  const ct = combined.slice(12);
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
  return new Uint8Array(pt);
}

/** Encrypt UTF-8 string content. Wrapper around encryptBytes. */
export async function encryptFile(masterBytes, fileId, plaintext) {
  return encryptBytes(masterBytes, fileId, new TextEncoder().encode(plaintext));
}

/** Decrypt to UTF-8 string. Wrapper around decryptBytes. */
export async function decryptFile(masterBytes, fileId, ciphertextB64) {
  const bytes = await decryptBytes(masterBytes, fileId, ciphertextB64);
  return new TextDecoder().decode(bytes);
}

// ── Name (deterministic) encryption ──────────────────────────────────────────

/**
 * Encrypts a file name to a stable ciphertext (same name → same output).
 * Used inside the encrypted index so we can dedupe + look up by name without
 * leaking name plaintexts. NOT used as the file ID — that's random per file.
 */
export async function encryptName(masterBytes, name) {
  const key = await deriveNameKey(masterBytes);
  const iv = await deterministicNameIv(masterBytes, name);
  const ct = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    new TextEncoder().encode(name)
  );
  const combined = new Uint8Array(iv.length + ct.byteLength);
  combined.set(iv, 0);
  combined.set(new Uint8Array(ct), iv.length);
  return b64encode(combined);
}

export async function decryptName(masterBytes, ciphertextB64) {
  const key = await deriveNameKey(masterBytes);
  const combined = b64decode(ciphertextB64);
  if (combined.length < 12 + 16) throw new Error('name ciphertext too short');
  const iv = combined.slice(0, 12);
  const ct = combined.slice(12);
  const pt = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ct);
  return new TextDecoder().decode(pt);
}

// ── Convenience: encrypt the index ───────────────────────────────────────────
// The index is just a regular file with the reserved id 'index'.

export const INDEX_FILE_ID = 'i'.repeat(32);  // 16-byte hex constant

export async function encryptIndex(masterBytes, indexObj) {
  const json = JSON.stringify(indexObj);
  return encryptFile(masterBytes, INDEX_FILE_ID, json);
}

export async function decryptIndex(masterBytes, ciphertextB64) {
  const json = await decryptFile(masterBytes, INDEX_FILE_ID, ciphertextB64);
  return JSON.parse(json);
}

// ── Self-test (callable from devtools) ──────────────────────────────────────

export async function _selfTest() {
  // Synthesise a master and roundtrip a file + name + index.
  const master = crypto.getRandomValues(new Uint8Array(32));
  const fid = newFileId();

  const plain = '# hello\n\nthis is a test note ✨';
  const ct = await encryptFile(master, fid, plain);
  const back = await decryptFile(master, fid, ct);
  if (back !== plain) throw new Error('content roundtrip failed');

  const name = 'My Notes/2026-05-08.md';
  const ne1 = await encryptName(master, name);
  const ne2 = await encryptName(master, name);
  if (ne1 !== ne2) throw new Error('name encryption not deterministic');
  const nd = await decryptName(master, ne1);
  if (nd !== name) throw new Error('name roundtrip failed');

  const idx = { version: 1, files: [{ id: fid, name, size: plain.length, mtime: Date.now() }] };
  const idxCt = await encryptIndex(master, idx);
  const idxBack = await decryptIndex(master, idxCt);
  if (JSON.stringify(idxBack) !== JSON.stringify(idx)) throw new Error('index roundtrip failed');

  return { ok: true, fileId: fid, ciphertextLen: ct.length };
}
