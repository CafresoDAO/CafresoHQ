/* ── The cast (OFFICE_AS_INTERFACE §2) ────────────────────────────────────
   Pure helpers behind the coworker card. Import-free so
   scripts/test_cast.py runs this file verbatim under node.

   §2's rules, encoded:
   - The VENDOR is a chip, never the coworker's identity ("powered by …").
   - Four stat bars, no more: Speed · Depth · Code · Cost. "Derived from the
     driver manifest's costHint + model class; honest and RELATIVE, not
     benchmark cosplay" — these are coarse 1..4 class judgements a colleague
     would make ("she's fast", "he's thorough"), not leaderboard numbers.
   - Cost reads as VALUE: 4 bars = costs you nothing extra, 1 bar = the
     expensive specialist. (Payroll shows real numbers; the bar is a vibe.) */

/* Model-class table. Order matters: first match wins, and prefixes like
   'openrouter:' only decide the vendor — the class comes from the model id
   AFTER the prefix when we recognise it, else the driver's default row. */
const CAST_CLASSES = [
  // key-test (on the prefix-stripped, lowercased model id), bars, tagline
  { re: /fable|mythos|opus/,        speed: 2, depth: 4, code: 4, cost: 1, tag: 'the deep-work specialist' },
  { re: /sonnet/,                   speed: 3, depth: 3, code: 3, cost: 2, tag: 'strong all-rounder' },
  { re: /haiku|mini|flash|small/,   speed: 4, depth: 2, code: 2, cost: 3, tag: 'quick with the small stuff' },
  { re: /gpt-5|o[13]|codex/,        speed: 2, depth: 4, code: 4, cost: 2, tag: 'ships serious code' },
  { re: /claude-code/,              speed: 2, depth: 4, code: 4, cost: 2, tag: 'ships serious code' },
  { re: /gemini/,                   speed: 3, depth: 3, code: 3, cost: 2, tag: 'strong all-rounder' },
  { re: /llama|mistral|qwen|gemma|phi|deepseek|hermes/,
                                    speed: 3, depth: 2, code: 2, cost: 4, tag: 'cheap and tireless' },
];
const CAST_DEFAULT = { speed: 3, depth: 3, code: 2, cost: 3, tag: 'steady generalist' };

/* Vendor chip from the model id's shape. Honest and boring — when we don't
   recognise the vendor we say what we do know ('your hardware' for local
   daemons) rather than guessing a brand. */
const CAST_VENDORS = [
  { re: /^(ollama|lmstudio):/,          name: 'your hardware' },
  { re: /^openrouter:/,                 name: 'OpenRouter' },
  { re: /^groq:/,                       name: 'Groq' },
  { re: /^gemini(-api)?:|gemini/,       name: 'Google' },
  { re: /^codex|gpt|^o[13]/,            name: 'OpenAI' },
  { re: /hermes/,                       name: 'Nous Research' },
  { re: /claude|sonnet|haiku|opus|fable/, name: 'Claude' },
];

function _modelCore(model) {
  const m = String(model || '').toLowerCase().trim();
  return m.replace(/^[a-z][a-z0-9_-]*:/, '');   // strip one driver prefix
}

function poweredBy(agent) {
  const m = String((agent && agent.model) || '').toLowerCase().trim();
  if (!m) return null;
  for (const v of CAST_VENDORS) {
    if (v.re.test(m)) return v.name;
  }
  return null;   // unknown vendor → no chip, never a wrong brand
}

/* The four bars + the class tagline. Bars are 1..4 by construction. */
function statBars(agent) {
  const core = _modelCore(agent && agent.model);
  const row = CAST_CLASSES.find(c => c.re.test(core)) || CAST_DEFAULT;
  return { speed: row.speed, depth: row.depth, code: row.code, cost: row.cost, tag: row.tag };
}

/* The one-line specialty tag: an EARNED affinity beats the class default —
   "12 research briefs" is a résumé line, "cheap and tireless" is a hunch. */
function specialtyTag(agent, xpAffinityText) {
  return (xpAffinityText && String(xpAffinityText)) || statBars(agent).tag;
}

export { CAST_CLASSES, CAST_DEFAULT, poweredBy, specialtyTag, statBars };
