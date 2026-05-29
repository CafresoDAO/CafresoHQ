// Notification store — client-side, localStorage-backed per principal.
// Notification shape:
//   { id, type, read, createdAt, title, body, url, from?, commentId?, proposalId? }
//
// Types: 'mention' | 'reply' | 'tip' | 'proposal_open' | 'proposal_update'

import { writable, derived, get } from 'svelte/store';
import { principalText } from '$lib/stores/auth.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function storageKey(principal) {
  return `cafreso:notifications:${principal || 'anon'}`;
}

function load(principal) {
  if (typeof localStorage === 'undefined') return [];
  try {
    return JSON.parse(localStorage.getItem(storageKey(principal)) || '[]');
  } catch {
    return [];
  }
}

function save(principal, items) {
  if (typeof localStorage === 'undefined') return;
  try {
    localStorage.setItem(storageKey(principal), JSON.stringify(items));
  } catch {
    // quota exceeded — silently drop
  }
}

function makeId() {
  return `n-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

// ---------------------------------------------------------------------------
// Core store
// ---------------------------------------------------------------------------

// Start with anon notifications; re-hydrate on principal change.
const _notifications = writable(load(null));

// Re-hydrate when principal changes.
let _currentPrincipal = null;
if (typeof window !== 'undefined') {
  principalText.subscribe((p) => {
    _currentPrincipal = p;
    _notifications.set(load(p));
  });
}

// Persist on every write.
_notifications.subscribe((items) => {
  save(_currentPrincipal, items);
});

// ---------------------------------------------------------------------------
// Derived / public API
// ---------------------------------------------------------------------------

/** Full sorted notification list (newest first). */
export const notifications = derived(_notifications, (n) =>
  [...n].sort((a, b) => b.createdAt - a.createdAt)
);

/** Count of unread notifications (capped at 99 for display). */
export const unreadCount = derived(_notifications, (n) =>
  Math.min(n.filter((x) => !x.read).length, 99)
);

/**
 * Add a notification. Deduplicates by `id` — if the id already exists the
 * call is a no-op (safe to call on every comment load).
 */
export function addNotification({ id, type, title, body, url, from, commentId, proposalId } = {}) {
  const notifId = id ?? makeId();
  _notifications.update((items) => {
    if (items.some((n) => n.id === notifId)) return items; // dedup
    return [
      ...items,
      {
        id: notifId,
        type: type ?? 'mention',
        read: false,
        createdAt: Date.now(),
        title: title ?? 'New notification',
        body: body ?? '',
        url: url ?? '#',
        from: from ?? null,
        commentId: commentId ?? null,
        proposalId: proposalId ?? null,
      },
    ];
  });
}

/** Mark a single notification as read by id. */
export function markRead(id) {
  _notifications.update((items) =>
    items.map((n) => (n.id === id ? { ...n, read: true } : n))
  );
}

/** Mark all notifications as read. */
export function markAllRead() {
  _notifications.update((items) => items.map((n) => ({ ...n, read: true })));
}

/** Remove a notification by id. */
export function removeNotification(id) {
  _notifications.update((items) => items.filter((n) => n.id !== id));
}

/** Clear all notifications. */
export function clearAll() {
  _notifications.set([]);
}

// ---------------------------------------------------------------------------
// Convenience: scan a comment list for @mentions addressed to the current user.
// Call after loading comments on any post/thread.
// ---------------------------------------------------------------------------

/**
 * @param {Array} comments  - array of comment objects with { id, text, author }
 * @param {string} myName   - display name to look for (e.g. "Alice")
 * @param {string} postUrl  - URL of the post so the notification links there
 */
export function detectMentions(comments, myName, postUrl) {
  if (!myName) return;
  const pattern = new RegExp(`@${myName}\\b`, 'i');
  for (const c of comments) {
    if (pattern.test(c.text)) {
      addNotification({
        id: `mention-${c.id}`,
        type: 'mention',
        title: `${c.author?.name ?? 'Someone'} mentioned you`,
        body: c.text.slice(0, 80),
        url: `${postUrl}#comment-${c.id}`,
        from: c.author?.name ?? null,
        commentId: c.id,
      });
    }
  }
}

// ---------------------------------------------------------------------------
// Icon + colour helpers consumed by NotificationBell dropdown.
// ---------------------------------------------------------------------------

export const NOTIF_META = {
  mention:         { icon: 'at',              color: 'hsl(43 74% 54%)' },
  reply:           { icon: 'arrow-bend-up-left', color: 'hsl(210 80% 58%)' },
  tip:             { icon: 'fire',            color: 'hsl(32 72% 50%)' },
  proposal_open:   { icon: 'gavel',           color: 'hsl(260 70% 62%)' },
  proposal_update: { icon: 'bell-ringing',    color: 'hsl(260 70% 62%)' },
};

export function notifMeta(type) {
  return NOTIF_META[type] ?? { icon: 'bell', color: 'hsl(215 16% 47%)' };
}
