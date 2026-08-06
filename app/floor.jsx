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

/* Which props stand in a coworker's room. Driven by `agent.tools` — the
   capability the boss ACTUALLY granted at hire — so a room furnishes to
   what its occupant can really do, and the §4 walk destinations exist in
   the room the walk happens in.

   Honesty note: this is capability, never achievement. A cabinet means
   "may open the vault", not "has filed a lot" — the papers pile and the
   out-tray are the earned counters, and they already read real numbers.
   An agent with no declared tools still gets a shelf: a bare office would
   read as broken, and a shelf claims nothing. Capped at two so the room
   stays legible at ×2 scale. */
const KIT_RULES = [
  [/^(vault|files?|fs|disk|memory)$/i, 'cabinet'],
  [/^(web|email|mail|http|browse|slack)$/i, 'phone'],
  [/^(search|library|research|db|index)$/i, 'bookshelf'],
];

function deskKit(tools) {
  const list = Array.isArray(tools) ? tools : [];
  const out = [];
  for (const t of list) {
    for (const [re, prop] of KIT_RULES) {
      if (re.test(String(t)) && out.indexOf(prop) === -1) out.push(prop);
    }
  }
  if (!out.length) out.push('bookshelf');
  return out.slice(0, 2);
}

export { deskKit, PROP_PLACARD, snagSentence, toolProp };
