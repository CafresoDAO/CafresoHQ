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

/* Unicode bidi-control characters (U+202A–U+202E, the embedding/override
   pair, and U+2066–U+2069, their "isolate" successors) don't change what a
   value IS — they change the order it's PAINTED in. A command carrying an
   RLO (U+202E) can render with its tail reshuffled in front of its head,
   the classic "trojan source" trick (real-world use: disguising `evil.exe`
   as `evil ‮exe.txt` so it reads as a harmless .txt file). Every other
   guard in this file protects the CONTENT of the approval box — the cap
   keeps both ends, the label keeps values unambiguous — on the assumption
   that painting the string verbatim is the same as showing the boss the
   truth. For these code points it isn't: the bytes the CLI executes and
   the glyphs the boss reads can differ, which is exactly the gap this gate
   exists to close. Escaped to a literal `\uXXXX`, not stripped — nothing
   about the payload disappears, only its power to reorder how it reads. */
const BIDI_CONTROL_RE = /[‪-‮⁦-⁩]/g;
const escapeBidiControls = (s) => s.replace(BIDI_CONTROL_RE,
  c => '\\u' + c.codePointAt(0).toString(16).toUpperCase().padStart(4, '0'));

function formatToolInput(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) return '';
  const keys = Object.keys(input);
  if (!keys.length) return '';

  /* Past the cap, keep BOTH ends and elide the middle. Slicing off the tail
     (the first cut's approach, and this file's own approach until this fix)
     recreates the exact bug documented above at a bigger threshold: a
     buried `rm -rf /important` living past char 8000 would still vanish
     from the approval box, unmarked as anything but "the end got cut". */
  const clip = (s) => {
    const t = String(s);
    if (t.length <= APPROVAL_VALUE_CAP) return t;
    const head = Math.ceil(APPROVAL_VALUE_CAP / 2);
    const tail = APPROVAL_VALUE_CAP - head;
    const omitted = t.length - head - tail;
    return t.slice(0, head) + ` …(${omitted} chars omitted)… ` + t.slice(t.length - tail);
  };

  const lead = APPROVAL_LEAD_KEYS.filter(k => keys.includes(k));
  const rest = keys.filter(k => lead.indexOf(k) === -1);
  /* A lone command or path reads better bare — "rm -rf build/" rather than
     "command: rm -rf build/". Only when it stands alone: with any second
     argument present, every line needs its label to stay unambiguous. */
  const bare = lead.length === 1 && keys.length === 1;

  return [...lead, ...rest].map(k => {
    const v = input[k];
    const raw = (v !== null && typeof v === 'object') ? JSON.stringify(v) : String(v);
    const flat = escapeBidiControls(raw);
    return bare ? clip(flat) : `${k}: ${clip(flat)}`;
  }).join('\n');
}

export { APPROVAL_VALUE_CAP, formatToolInput };
