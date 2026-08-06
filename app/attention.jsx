/* ── The attention queue ──────────────────────────────────────────────────
   Pure helpers behind "N need you". Import-free so
   scripts/test_attention.py runs this file verbatim under node.

   The queue answers ONE question: how many things need the boss? It was
   answering a different one — how many times has something been reported —
   and the gap between those is not cosmetic.

   Measured on a real session: 21 unread attention rows, every one of them
   the same root cause ("that brain isn't signed in yet"), re-raised across
   seven coworkers and several runs each. One decision to make; the office
   pill said twenty-one. A chief of staff who hands you the same note
   twenty-one times is not being thorough, they are burying the one thing
   you have to do.

   So: identical text from the same coworker is ONE item that happened N
   times. Nothing is hidden — the row carries its own count, and every
   underlying entry stays in the list for the Activity tab. What changes is
   that the number on the wall means what it says. */

/* Same coworker + same sentence = the same problem recurring. Deliberately
   strict: it keys on the WHOLE text, so "failed 'Draft the brief'" and
   "failed 'Ship the page'" stay separate items — those are two pieces of
   work stuck, not one thing repeated. Only genuinely identical reports
   collapse. */
function attentionKey(entry) {
  if (!entry) return '';
  /* '::' is safe as a separator here — agent ids are short slugs (`a1`,
     `a_tir7pj`), so it cannot collide with a real id and merge two
     coworkers' items. */
  return String(entry.agentId || entry.agentName || '') + '::' + String(entry.text || '');
}

/* Collapse a newest-first list into newest-first groups.

   Each group carries `entry` (the most recent occurrence — the one a Retry
   should act on), `count`, and `ids` (every entry it stands for, so marking
   the group read can mark all of them and the count can't drift). */
function groupAttention(entries) {
  const list = Array.isArray(entries) ? entries : [];
  const byKey = new Map();
  const order = [];
  for (const e of list) {
    if (!e) continue;
    const k = attentionKey(e);
    if (!byKey.has(k)) {
      byKey.set(k, { key: k, entry: e, count: 0, ids: [] });
      order.push(k);
    }
    const g = byKey.get(k);
    g.count += 1;
    if (e.id) g.ids.push(e.id);
  }
  return order.map(k => byKey.get(k));
}

/* How many things need the boss, counting each distinct problem once.
   Pending approvals are always their own item — two stamps waiting are two
   decisions even when they read alike. */
function attentionCount(activity, approvals) {
  const unread = (Array.isArray(activity) ? activity : [])
    .filter(e => e && e.priority === 'attention' && e.unread);
  const pending = Array.isArray(approvals) ? approvals.length : 0;
  return groupAttention(unread).length + pending;
}

export { attentionCount, attentionKey, groupAttention };
