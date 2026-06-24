// One-time migration of legacy browser-storage keys to the cafresohq.* namespace.
// Copies (never deletes) any value under an old cafresoai.* / openclaw* key to its
// new cafresohq.* key on first load, so the rename doesn't strand a user's cached
// vault key / session / preferences. Idempotent.
export function migrateStorageKeys() {
  if (typeof window === 'undefined') return;
  for (const store of [window.localStorage, window.sessionStorage]) {
    try {
      for (const k of Object.keys(store)) {
        let nk = null;
        if (k.startsWith('cafresoai.')) nk = 'cafresohq.' + k.slice('cafresoai.'.length);
        else if (k.startsWith('openclaw')) nk = 'cafresohq' + k.slice('openclaw'.length);
        if (nk && store.getItem(nk) === null) store.setItem(nk, store.getItem(k));
      }
    } catch (_) { /* private mode */ }
  }
}
