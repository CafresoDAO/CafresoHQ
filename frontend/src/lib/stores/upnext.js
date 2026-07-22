// ─────────────────────────────────────────────────────────────────────────────
// "Up Next" — a personal research shortlist for the library.
//
// The honest v1 of "vote on what the network researches next." There is no
// on-chain vote tally yet (the state canister has no vote method) and the
// network's own gap questions are answered autonomously, so a GLOBAL queue
// isn't buildable today without faking numbers. Instead this is truthful and
// personal-first: questions YOU add, boosts YOU cast to reorder them, all in
// localStorage — plus a one-tap send into the real submitJob pipeline. When a
// shared on-chain tally ships, only this module changes (same component API).
//
//   shape: { q, boosts, addedAt }   (q is the display text; keyed by norm(q))
// ─────────────────────────────────────────────────────────────────────────────
import { writable } from 'svelte/store';

const KEY = 'cafreso:upnext';
const MAX = 40;

/** Loose client-side normalization for de-duping. The canister does the real
    normalization server-side; this only needs to stop obvious dupes in the UI. */
export function normQ(q) {
  return String(q || '')
    .toLowerCase()
    .replace(/[‘’‛]/g, "'")   // curly/‘ ’ apostrophes → straight
    .replace(/[“”]/g, '"')          // curly double quotes → straight
    .replace(/[^a-z0-9]+/g, ' ')              // fold all punctuation/spacing to one space
    .trim();
}

function read() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '[]');
    return Array.isArray(raw) ? raw : [];
  } catch (_e) {
    return [];
  }
}

function persist(list) {
  try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))); } catch (_e) {}
}

// SSR-safe: localStorage doesn't exist during prerender, so start empty and
// hydrate on the client via load().
export const upNext = writable([]);

/** Hydrate from localStorage — call once on mount (client only). */
export function loadUpNext() {
  upNext.set(sortQueue(read()));
}

/** Newest-intent first: highest boosts, then most recently added. */
function sortQueue(list) {
  return [...list].sort((a, b) => (b.boosts - a.boosts) || (b.addedAt - a.addedAt));
}

function mutate(fn) {
  upNext.update((list) => {
    const next = sortQueue(fn([...list]) || list);
    persist(next);
    return next;
  });
}

/** Add a question if not already queued. Returns false if it was a dupe. */
export function addQuestion(q, addedAt) {
  const text = String(q || '').trim();
  if (!text) return false;
  const key = normQ(text);
  let added = false;
  mutate((list) => {
    if (list.some((it) => normQ(it.q) === key)) return list;   // dupe → no-op
    added = true;
    // A freshly-added question starts with one boost — you added it, you want it.
    list.push({ q: text.slice(0, 240), boosts: 1, addedAt: addedAt || Date.now() });
    return list;
  });
  return added;
}

/** +1 boost — nudges the question up your shortlist. */
export function boost(q) {
  const key = normQ(q);
  mutate((list) => { const it = list.find((x) => normQ(x.q) === key); if (it) it.boosts += 1; return list; });
}

export function removeQuestion(q) {
  const key = normQ(q);
  mutate((list) => list.filter((x) => normQ(x.q) !== key));
}

export function hasQuestion(list, q) {
  const key = normQ(q);
  return list.some((x) => normQ(x.q) === key);
}
