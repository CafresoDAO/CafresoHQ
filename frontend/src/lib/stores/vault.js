// ─────────────────────────────────────────────────────────────────────────────
// CafresoHQ — encrypted vault store
//
// Zero-knowledge vault. The container's serve.py only sees:
//   • An "index.bin" blob (the encrypted directory listing)
//   • A set of "f-<random_hex>.bin" blobs (the per-file ciphertexts)
//
// The container has no idea what the files are named or how they're organised.
// All metadata lives inside the encrypted index, decrypted only in the user's
// browser using the vetKeys-derived master key.
//
// Storage path
// ────────────
//   Browser  ←──── ai.cafreso.com (this dapp)
//      │
//      │  fetch(  https://hq.cafreso.com/u/<slug>/vault/blob/<id>  )
//      ▼
//   Caddy gateway  ───→  user's container's serve.py /vault/blob/<id>
//                                   │
//                                   ▼
//                        OCI Object Storage (per-user prefix)
//
// Index schema (post-decryption)
// ─────────────────────────────
//   {
//     "version": 1,
//     "files": [
//       { "id": "<16-hex>", "name": "Notes/today.md",
//         "encName": "<base64>", "size": 1234,
//         "createdAt": <ms>, "updatedAt": <ms> }
//     ],
//     "tombstones": [<id>, ...]   // for sync conflict resolution
//   }
// ─────────────────────────────────────────────────────────────────────────────

import { writable, derived, get } from 'svelte/store';
import { endpointUrl } from '$lib/stores/endpoint.js';
import { isAuthenticated, principalText } from '$lib/stores/auth.js';
import { getKeysActor } from '$lib/api/keysActor.js';
import {
  getMasterKey, forgetMasterKey,
  encryptFile, decryptFile,
  encryptBytes, decryptBytes,
  encryptName, decryptName,
  encryptIndex, decryptIndex,
  newFileId, INDEX_FILE_ID,
} from '$lib/crypto/vaultKey.js';

// ── Stores ──────────────────────────────────────────────────────────────────

/** Vault initialization state.
 *  'idle' | 'unlocking' | 'unlocked' | 'locked' | 'error'
 *  - idle:      not signed in or vault not yet attempted
 *  - unlocking: deriving master key + loading index
 *  - unlocked:  master key in memory, index loaded — ready for read/write
 *  - locked:    explicit lock requested (master key forgotten)
 *  - error:     last operation failed (see vaultError for details)
 */
export const vaultState = writable('idle');
export const vaultError = writable(null);

/** The decrypted index — null until unlocked. */
export const vaultIndex = writable(null);

/** Sorted list of file metadata (decrypted names). */
export const vaultFiles = derived(vaultIndex, ($idx) =>
  $idx ? [...$idx.files].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0)) : []
);

export const vaultUnlocked = derived(vaultState, ($s) => $s === 'unlocked');

// ── Internal state ──────────────────────────────────────────────────────────

let _master = null;     // Uint8Array — never leaves this module after derive
let _saveLock = Promise.resolve();

// ── Network helpers ─────────────────────────────────────────────────────────

function _vaultBaseUrl() {
  const ep = get(endpointUrl);
  if (!ep) throw new Error('Endpoint not configured. Provision your HQ first.');
  return ep.replace(/\/+$/, '') + '/vault';
}

async function _putBlob(id, ciphertextB64) {
  const r = await fetch(_vaultBaseUrl() + '/blob/' + encodeURIComponent(id), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: ciphertextB64,
  });
  if (!r.ok) throw new Error(`PUT blob ${id} → HTTP ${r.status}`);
  // Phase 2: best-effort dual-write of the ciphertext on-chain. No-op unless
  // PUBLIC_STATE_CANISTER is enabled AND cafresohq_state is deployed.
  import('$lib/api/stateSync.js')
    .then((m) => { if (m.stateEnabled()) m.mirrorVaultObject(id, ciphertextB64).catch(() => {}); })
    .catch(() => {});
  return r.json().catch(() => ({}));
}

async function _getBlob(id) {
  const r = await fetch(_vaultBaseUrl() + '/blob/' + encodeURIComponent(id), {
    method: 'GET',
    headers: { 'Accept': 'application/octet-stream' },
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`GET blob ${id} → HTTP ${r.status}`);
  return r.text();   // base64 string
}

async function _deleteBlob(id) {
  const r = await fetch(_vaultBaseUrl() + '/blob/' + encodeURIComponent(id), {
    method: 'DELETE',
  });
  if (!r.ok && r.status !== 404) throw new Error(`DELETE blob ${id} → HTTP ${r.status}`);
  import('$lib/api/stateSync.js')
    .then((m) => { if (m.stateEnabled()) m.deleteVaultObject(id).catch(() => {}); })
    .catch(() => {});
}

// Phase 2 backfill: the live _putBlob mirror only catches NEW writes, so vault
// objects written before mirror was enabled never reach the canister. This couriers
// the existing index + every file blob up once per principal. Sequential, best-effort,
// non-fatal — never blocks unlock, never throws into the UI. The flag is only set on a
// fully-clean pass, so a transient failure simply retries on the next unlock.
const _BACKFILL_KEY = 'cafresohq.vault_backfilled_v1';
async function _backfillToCanister(idx) {
  if (typeof window === 'undefined') return;
  let m;
  try { m = await import('$lib/api/stateSync.js'); } catch { return; }
  if (!m.stateEnabled || !m.stateEnabled()) return;
  const flag = `${_BACKFILL_KEY}:${get(principalText) || ''}`;
  try { if (localStorage.getItem(flag)) return; } catch { /* private mode → just run */ }
  const ids = [INDEX_FILE_ID, ...((idx && idx.files) || []).map((f) => f.id)];
  let ok = 0, fail = 0;
  for (const id of ids) {
    try {
      const ct = await _getBlob(id);
      if (!ct) continue;                         // already deleted / missing — skip
      const r = await m.mirrorVaultObject(id, ct);
      if (r && r.ok) ok++; else fail++;
    } catch { fail++; }
  }
  if (fail === 0) { try { localStorage.setItem(flag, String(ok)); } catch {} }
  console.info(`[vault] on-chain backfill: ${ok} mirrored, ${fail} failed of ${ids.length}`);
}

// ── Index lifecycle ─────────────────────────────────────────────────────────

const _INDEX_CACHE_KEY = 'cafresohq.vault_index_cache';
const _INDEX_ETAG_KEY  = 'cafresohq.vault_index_etag';

function _emptyIndex() {
  return { version: 1, files: [], tombstones: [] };
}

function _getCachedIndex() {
  try {
    const raw = sessionStorage.getItem(_INDEX_CACHE_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) {}
  return null;
}

function _setCachedIndex(idx) {
  try {
    sessionStorage.setItem(_INDEX_CACHE_KEY, JSON.stringify(idx));
  } catch (_) {}
}

async function _loadIndex() {
  const cached = _getCachedIndex();
  const ct = await _getBlob(INDEX_FILE_ID);
  if (!ct) return _emptyIndex();

  const etag = ct.length + ':' + ct.slice(0, 64);
  const prevEtag = sessionStorage.getItem(_INDEX_ETAG_KEY);
  if (cached && prevEtag === etag) return cached;

  const idx = await decryptIndex(_master, ct);
  _setCachedIndex(idx);
  try { sessionStorage.setItem(_INDEX_ETAG_KEY, etag); } catch (_) {}
  return idx;
}

async function _saveIndex(idx) {
  // Mutex so concurrent writes don't lose updates
  _saveLock = _saveLock.then(async () => {
    const ct = await encryptIndex(_master, idx);
    await _putBlob(INDEX_FILE_ID, ct);
    _setCachedIndex(idx);
    try {
      const etag = ct.length + ':' + ct.slice(0, 64);
      sessionStorage.setItem(_INDEX_ETAG_KEY, etag);
    } catch (_) {}
  });
  return _saveLock;
}

// ── Public API ──────────────────────────────────────────────────────────────

/**
 * Derive the master key (vetKeys round-trip) and load the encrypted index.
 * Idempotent — does nothing if already unlocked.
 */
export async function unlockVault() {
  if (get(vaultState) === 'unlocked' && _master) return;
  if (!get(isAuthenticated)) {
    vaultState.set('idle');
    vaultError.set('Sign in with Internet Identity to unlock the vault.');
    return;
  }
  vaultState.set('unlocking');
  vaultError.set(null);
  try {
    const actor = await getKeysActor();
    _master = await getMasterKey(actor);
    const idx = await _loadIndex();
    vaultIndex.set(idx);
    vaultState.set('unlocked');
    // Phase 2: one-time best-effort backfill of pre-existing vault objects. Not
    // awaited — runs in the background after unlock so it never delays the UI.
    _backfillToCanister(idx);
  } catch (err) {
    console.error('[vault] unlock failed:', err);
    vaultError.set(String(err?.message || err));
    vaultState.set('error');
    _master = null;
  }
}

/** Forget the master key + index. Files remain encrypted on the container. */
export function lockVault() {
  _master = null;
  vaultIndex.set(null);
  vaultState.set('locked');
  vaultError.set(null);
  forgetMasterKey();
  try {
    sessionStorage.removeItem(_INDEX_CACHE_KEY);
    sessionStorage.removeItem(_INDEX_ETAG_KEY);
  } catch (_) {}
}

function _ensureUnlocked() {
  if (!_master || get(vaultState) !== 'unlocked') {
    throw new Error('Vault is locked. Call unlockVault() first.');
  }
}

/** Look up a file metadata entry by name (returns null if not found). */
export function findByName(name) {
  const idx = get(vaultIndex);
  if (!idx) return null;
  return idx.files.find((f) => f.name === name) || null;
}

/** Create a new file. Returns the metadata entry. */
export async function createFile(name, content = '') {
  _ensureUnlocked();
  const now = Date.now();
  const id = newFileId();
  const ct = await encryptFile(_master, id, content);
  await _putBlob(id, ct);

  const encName = await encryptName(_master, name);
  const meta = {
    id, name, encName,
    size: content.length,
    createdAt: now,
    updatedAt: now,
  };
  vaultIndex.update((idx) => {
    idx = idx || _emptyIndex();
    return { ...idx, files: [...idx.files, meta] };
  });
  await _saveIndex(get(vaultIndex));
  return meta;
}

/** Read decrypted content for a file id. */
export async function readFile(id) {
  _ensureUnlocked();
  const ct = await _getBlob(id);
  if (!ct) throw new Error('File not found on container: ' + id);
  return decryptFile(_master, id, ct);
}

/** Update a file's content (preserves id, bumps updatedAt + size). */
export async function updateFile(id, newContent) {
  _ensureUnlocked();
  const ct = await encryptFile(_master, id, newContent);
  await _putBlob(id, ct);
  vaultIndex.update((idx) => ({
    ...idx,
    files: idx.files.map((f) =>
      f.id === id ? { ...f, size: newContent.length, updatedAt: Date.now() } : f
    ),
  }));
  await _saveIndex(get(vaultIndex));
}

/** Rename a file (re-encrypts the deterministic name field, content untouched). */
export async function renameFile(id, newName) {
  _ensureUnlocked();
  const encName = await encryptName(_master, newName);
  vaultIndex.update((idx) => ({
    ...idx,
    files: idx.files.map((f) =>
      f.id === id ? { ...f, name: newName, encName, updatedAt: Date.now() } : f
    ),
  }));
  await _saveIndex(get(vaultIndex));
}

/** Delete a file. Tombstones the id so sync clients know to drop it. */
export async function deleteFile(id) {
  _ensureUnlocked();
  await _deleteBlob(id);
  vaultIndex.update((idx) => ({
    ...idx,
    files: idx.files.filter((f) => f.id !== id),
    tombstones: [...(idx.tombstones || []), id],
  }));
  await _saveIndex(get(vaultIndex));
}

// ── Binary file upload / download ───────────────────────────────────────────
//
// Files are encrypted on the user's device with a per-file key (HKDF-derived
// from the vetKeys master), then uploaded as opaque blobs. Filenames live in
// the encrypted index — the container only ever sees random-id ciphertext.
//
// MIME type is recorded in the index so the UI can render previews and
// downloads with the right Content-Type.

/**
 * Upload one File (from <input type="file"> or drag-drop event.dataTransfer.files).
 * Encrypts client-side then PUTs the ciphertext blob.
 *
 * Pass `skipIndexSave: true` when calling from uploadFiles() — the batch
 * wrapper saves the index once at the end instead of once per file, cutting
 * N index PUTs down to 1 for bulk uploads (latency + cost improvement).
 *
 * @param {File} file
 * @param {{ onProgress?: (event: any) => void, skipIndexSave?: boolean }} [options]
 * Returns the new metadata entry.
 */
export async function uploadFile(file, { onProgress, skipIndexSave = false } = {}) {
  _ensureUnlocked();
  if (!file) throw new Error('no file given');
  // 200 MB plaintext cap — AES-GCM base64-encodes to ~133% of source size,
  // so 200 MB plaintext → ~267 MB body; serve.py accepts up to 300 MB.
  const MAX = 200 * 1024 * 1024;
  if (file.size > MAX) {
    throw new Error(`file too large (${(file.size / 1024 / 1024).toFixed(1)} MB; cap is 200 MB)`);
  }

  onProgress?.({ phase: 'reading', file: file.name });
  const bytes = new Uint8Array(await file.arrayBuffer());

  onProgress?.({ phase: 'encrypting', file: file.name });
  const id = newFileId();
  const ct = await encryptBytes(_master, id, bytes);

  onProgress?.({ phase: 'uploading', file: file.name });
  await _putBlob(id, ct);

  const encName = await encryptName(_master, file.name);
  const now = Date.now();
  const meta = {
    id, name: file.name, encName,
    size: file.size,
    mimeType: file.type || 'application/octet-stream',
    isBinary: true,                // distinguishes from text notes in the UI
    createdAt: now,
    updatedAt: now,
  };
  vaultIndex.update((idx) => {
    idx = idx || _emptyIndex();
    return { ...idx, files: [...idx.files, meta] };
  });
  // Single-file path: save index immediately so the file is findable right away.
  // Batch path: caller (uploadFiles) saves once after all files are done.
  if (!skipIndexSave) {
    await _saveIndex(get(vaultIndex));
  }
  onProgress?.({ phase: 'done', file: file.name, id });
  return meta;
}

/**
 * Upload multiple files in parallel. Yields a meta entry per success and
 * an error entry per failure. Use Promise.allSettled + per-item try/catch so
 * one bad file doesn't kill the whole batch.
 *
 * Optimization: all files share a single final index save (1 PUT) instead of
 * one per file (N PUTs). A 100-file drop goes from 200 PUTs to 101 PUTs and
 * saves ~10–20 s of round-trips through Caddy → container → OCI.
 *
 * @param {FileList|File[]} files
 * @param {{ onProgress?: (event: any) => void }} [options]
 */
export async function uploadFiles(files, { onProgress } = {}) {
  _ensureUnlocked();
  const list = Array.from(files || []);
  if (!list.length) return { uploaded: [], failed: [] };

  const results = await Promise.allSettled(
    list.map((f) => uploadFile(f, { onProgress, skipIndexSave: true }))
  );
  const uploaded = [];
  const failed   = [];
  results.forEach((r, i) => {
    if (r.status === 'fulfilled') uploaded.push(r.value);
    else failed.push({ name: list[i].name, error: String(r.reason?.message || r.reason) });
  });

  // Single index save for the entire batch — covers all successfully uploaded files.
  if (uploaded.length > 0) {
    await _saveIndex(get(vaultIndex));
  }
  return { uploaded, failed };
}

/**
 * Decrypt + return a Blob suitable for browser download.
 * The caller can pass it to URL.createObjectURL() and trigger a click on
 * an <a download> element.
 */
export async function downloadFileBlob(id) {
  _ensureUnlocked();
  const ct = await _getBlob(id);
  if (!ct) throw new Error('File not found on container: ' + id);
  const meta = get(vaultIndex)?.files.find((f) => f.id === id);
  const bytes = await decryptBytes(_master, id, ct);
  return new Blob([bytes], { type: meta?.mimeType || 'application/octet-stream' });
}

/** Trigger a browser download of a vault file by id. */
export async function triggerDownload(id) {
  const meta  = get(vaultIndex)?.files.find((f) => f.id === id);
  const blob  = await downloadFileBlob(id);
  const url   = URL.createObjectURL(blob);
  const a     = document.createElement('a');
  a.href      = url;
  a.download  = meta?.name || ('file-' + id);
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(url);
    a.remove();
  }, 1000);
}

/** Diagnostics — does the vault round-trip with this principal? */
export async function diagnoseVault() {
  await unlockVault();
  const id = await createFile('__diagnostic__.tmp', '# diagnostic\n\nok @ ' + new Date().toISOString());
  const content = await readFile(id.id);
  await deleteFile(id.id);
  return { ok: content.startsWith('# diagnostic'), fileId: id.id };
}
