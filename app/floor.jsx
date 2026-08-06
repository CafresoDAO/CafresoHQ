/* ── Floor language (OFFICE_AS_INTERFACE §4) ──────────────────────────────
   Pure helpers that translate runtime events into the office's physical
   vocabulary. The mapping is the ANIMATION API: one table, every backend.
   Kept import-free so scripts/test_floor.py can run this file verbatim.

   §4's binding rules apply to everything here:
   - honest   — a prop visit only plays while that tool is REALLY running;
                the snag line never claims anything but what happened.
   - cheap    — these return strings/classnames for CSS the floor already
                has (away placards, bubbles); no new animation tech.       */

/* Which prop a tool call walks the coworker to. Search wins over storage
   (VAULT_SEARCH is a bookshelf trip, not a cabinet one); anything we can't
   place honestly stays at the desk with the tool chip. */
function toolProp(name) {
  const n = String(name || '').toUpperCase();
  if (!n) return null;
  if (/SEARCH|LIBRARY|RESEARCH/.test(n)) return 'bookshelf';
  if (/WEB|HTTP|FETCH|URL|BROWSE/.test(n)) return 'phone';
  if (/VAULT|FILE|DIR|MEMORY|NOTE/.test(n)) return 'cabinet';
  return null;
}

/* What the placard says while they're away from the desk. Office words
   only (§6): the action, never the tool. */
const PROP_PLACARD = {
  cabinet:   'at the filing cabinet',
  bookshelf: 'at the bookshelf',
  phone:     'on the phone',
};

/* One honest sentence for the "hit a snag" bubble (§4 error row, §7 "no
   raw error dumps"). First line only — stack traces and JSON bodies are
   for the inspect panel, not the floor — collapsed and capped so it reads
   as speech, not a log. */
function snagSentence(raw) {
  const first = String(raw || '').split('\n')[0]
    .replace(/https?:\/\/\S+/g, '')            // URLs are noise in a bubble
    .replace(/[{}[\]"\\]/g, ' ')               // JSON shrapnel
    .replace(/\s+/g, ' ')
    .trim();
  const line = first || 'something went wrong on the last run';
  return 'hit a snag — ' + (line.length > 90 ? line.slice(0, 89).trimEnd() + '…' : line);
}

export { PROP_PLACARD, snagSentence, toolProp };
