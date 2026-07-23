// ─────────────────────────────────────────────────────────────────────────────
// Return-visit state for /news — localStorage-backed, same pattern as
// upnext.js, because there's no account system to hang this off of. Two
// independent pieces:
//
//   - markVisit(): stamps "now" as the last-seen time and returns the
//     PREVIOUS stamp, so the caller can show "N new since you were last
//     here" using the old value before it's overwritten.
//   - followedTopics: a plain array of section-rubric words (see
//     sectionTag() in digest.js) the reader has starred, so a return visit
//     can surface "N new in topics you follow" instead of just the raw feed.
// ─────────────────────────────────────────────────────────────────────────────
import { writable } from 'svelte/store';

const VISIT_KEY = 'cafreso:news:lastVisit';
const FOLLOW_KEY = 'cafreso:news:followedTopics';
const MAX_FOLLOWED = 20;

export const followedTopics = writable([]);

function readFollowed() {
  try {
    const raw = JSON.parse(localStorage.getItem(FOLLOW_KEY) || '[]');
    return Array.isArray(raw) ? raw : [];
  } catch (_e) { return []; }
}
function persistFollowed(list) {
  try { localStorage.setItem(FOLLOW_KEY, JSON.stringify(list.slice(0, MAX_FOLLOWED))); } catch (_e) {}
}

/** Hydrate followedTopics from localStorage — call once on mount (client only). */
export function loadFollowedTopics() {
  followedTopics.set(readFollowed());
}

export function toggleFollow(word) {
  followedTopics.update((list) => {
    const next = list.includes(word) ? list.filter((w) => w !== word) : [...list, word];
    persistFollowed(next);
    return next;
  });
}

/**
 * Stamp this visit, return the PREVIOUS one (ms epoch, or null on a
 * brand-new browser). Read-then-write in that order on purpose — the
 * read has to happen before the overwrite, since the whole point of the
 * write is marking THIS visit for the comparison on the NEXT one.
 */
export function markVisit() {
  let prev = null;
  try {
    const raw = localStorage.getItem(VISIT_KEY);
    prev = raw ? Number(raw) : null;
    if (!Number.isFinite(prev)) prev = null;
  } catch (_e) { /* localStorage unavailable — treat as first-ever visit */ }
  try { localStorage.setItem(VISIT_KEY, String(Date.now())); } catch (_e) {}
  return prev;
}
