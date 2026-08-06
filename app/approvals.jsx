/* ── Approval payloads (OFFICE_AS_INTERFACE §4 "needs approval") ──────────
   Pure helper behind the approval row. Import-free so
   scripts/test_approvals.py runs this file verbatim under node.

   An approval row is a CONSENT surface, and that makes its honesty rules
   the inverse of the rest of the app's:

   - Everywhere else, raw payloads are noise to be translated into office
     language (§6/§7). Here the raw payload IS the point — the boss is
     authorising exactly this text, and a paraphrase would defeat the gate.
   - The row's title is the requesting agent's own `summary` of what it
     wants to do. That is a CLAIM. This gate exists precisely to catch a
     claim that doesn't match the action, so the action has to be visible
     next to it or the boss is being asked to rubber-stamp a description.  */

/* Deliberately huge. The first cut capped values at 400 chars, and driving
   a real request through it showed why that was wrong: a command padded
   with 500 harmless characters and ending in `rm -rf /important` — titled
   "Harmless cleanup" by its author — rendered as a wall of padding with
   the dangerous tail cut off. The truncation was marked, but the one part
   that mattered was the part that disappeared.

   Length is not a layout problem (the row's box scrolls), so a tight cap
   bought nothing except hiding the END of long input — which is exactly
   where something buried would be. This bounds a pathological blob and
   nothing else. */
const APPROVAL_VALUE_CAP = 8000;

/* Argument order: what the decision usually turns on, first. */
const APPROVAL_LEAD_KEYS = ['command', 'file_path', 'path', 'url'];

function formatToolInput(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return '';
  const keys = Object.keys(input);
  if (!keys.length) return '';

  const clip = (s) => {
    const t = String(s);
    return t.length > APPROVAL_VALUE_CAP
      ? t.slice(0, APPROVAL_VALUE_CAP) + ' …(truncated)'
      : t;
  };

  const lead = APPROVAL_LEAD_KEYS.filter(k => keys.includes(k));
  const rest = keys.filter(k => lead.indexOf(k) === -1);
  /* A lone command or path reads better bare — "rm -rf build/" rather than
     "command: rm -rf build/". Only when it stands alone: with any second
     argument present, every line needs its label to stay unambiguous. */
  const bare = lead.length === 1 && keys.length === 1;

  return [...lead, ...rest].map(k => {
    const v = input[k];
    const flat = (v !== null && typeof v === 'object') ? JSON.stringify(v) : String(v);
    return bare ? clip(flat) : `${k}: ${clip(flat)}`;
  }).join('\n');
}

export { APPROVAL_VALUE_CAP, formatToolInput };
