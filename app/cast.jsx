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

/* The brain's NAME. §6 is binding: raw model IDs may appear in desktop-mode
   surfaces and settings, "never on the floor, the cards, or onboarding" —
   and the card was printing `openrouter:google/gemma-3-27b-it` under a label
   reading "Model", which is the console leaking into the office.

   This is FORMATTING ONLY. We never substitute a different name than the one
   the id already carries, so the card can never claim a brain the coworker
   isn't running — it drops the routing prefix and org path (plumbing, not
   identity) and the tuning suffixes, then title-cases what's left. An agent
   with no model set says so rather than inventing a default. */
function brainName(agent) {
  const core = _modelCore(agent && agent.model);
  if (!core) return 'not set yet';
  const bare = core.split('/').pop()
    .replace(/[:@](free|latest|preview|beta)$/i, '')
    .replace(/-(instruct|it|chat|latest|preview)$/i, '')
    .replace(/-\d{8}$/, '');                       // trailing date stamp
  const words = bare.split(/[-_]/).filter(Boolean).map(w => {
    if (/^\d+[bm]$/i.test(w)) return w.toUpperCase();          // 70b → 70B
    if (/^gpt$/i.test(w)) return 'GPT';
    if (/^(ai|llm|hq)$/i.test(w)) return w.toUpperCase();
    if (/^\d/.test(w)) return w;                               // version parts
    return w.charAt(0).toUpperCase() + w.slice(1);
  });
  return words.join(' ') || 'not set yet';
}

/* The four bars + the class tagline. Bars are 1..4 by construction. */
function statBars(agent) {
  const core = _modelCore(agent && agent.model);
  const row = CAST_CLASSES.find(c => c.re.test(core)) || CAST_DEFAULT;
  return { speed: row.speed, depth: row.depth, code: row.code, cost: row.cost, tag: row.tag };
}

/* What this coworker can actually DO, in the boss's words.
   Section 6: "tool call -> shown as the action itself: reading files,
   searching". A card that says "4 tools" has told the boss a NUMBER about
   a machine concept -- it is not wrong, it is just not about anything they
   care about. The catalog's own labels are no better ("Code Exec", "File
   Access"): those are switch names for the hiring form, where a checkbox
   list is the right shape. On a card, say the verb.

   Capped at three because a card is a glance, not a spec sheet; the full
   list stays in the title attribute for anyone who wants it. */
const CAN_DO = {
  web:    'search the web',
  vault:  'read your notes',
  files:  'work with your files',
  code:   'run code',
  img:    'make images',
  email:  'send email',
  cal:    'manage your calendar',
  db:     'query your database',
  slack:  'post to Slack',
  wallet: 'spend from your wallet',
};

function canDoPhrase(tools) {
  const list = (tools || []).map(t => CAN_DO[t]).filter(Boolean);
  if (!list.length) return 'talk things through';
  const shown = list.slice(0, 3);
  const rest = list.length - shown.length;
  let out = shown.length === 1 ? shown[0]
          : shown.slice(0, -1).join(', ') + ' and ' + shown[shown.length - 1];
  if (rest > 0) out += ` +${rest} more`;
  return out;
}

/* The one-line specialty tag: an EARNED affinity beats the class default —
   "12 research briefs" is a résumé line, "cheap and tireless" is a hunch. */
function specialtyTag(agent, xpAffinityText) {
  return (xpAffinityText && String(xpAffinityText)) || statBars(agent).tag;
}


/* ── The coworker's notebook (§2, and §3.6's cabinet) ─────────────────────
   Where a coworker's private notes live. The path was built by hand in two
   places in hq-runtime and nowhere else knew the rule, which is why the
   boss had no way to see what their own employee had written down — the
   notes existed only as a folder in the vault.

   One definition now: the runtime writes there, the roster reads from it. */
function memoryRoot(agent) {
  const safe = String((agent && agent.name) || 'agent').replace(/[^A-Za-z0-9_-]+/g, '_');
  return `Agents/${safe}`;
}

/* Which of the vault's paths belong to this coworker, as their own
   relative names ("prefs/boss.md", not "Agents/Llama/prefs/boss.md").
   Takes already-normalised path strings — see vaultPaths in hq-runtime;
   `/vault/list` hands back records, and reading those as strings is what
   killed this feature in the first place. */
function memoryNotes(agent, paths) {
  const root = memoryRoot(agent) + '/';
  return (paths || [])
    .filter(p => typeof p === 'string' && p.startsWith(root))
    .map(p => p.slice(root.length))
    .filter(Boolean)
    .sort();
}

/* What the card says. `paths` null means we could not read the cabinet —
   and "0 notes" would then be a lie of exactly the kind §4 exists to stop:
   it claims the coworker has saved nothing when the truth is that nobody
   looked. Returns null so the row renders nothing at all. */
function memoryLabel(agent, paths) {
  if (!paths) return null;
  const n = memoryNotes(agent, paths).length;
  return n === 1 ? '1 note' : `${n} notes`;
}


/* ── Payroll (§6: "Payroll shows real numbers") ───────────────────────────
   It didn't. FIVE surfaces multiplied the agent's token count by one
   hardcoded rate — 0.0000015 — regardless of which brain it ran on. On the
   live floor that produced **$0.0533 of payroll for a local Ollama that
   costs nothing at all**, and a dollar figure for a Claude Code hire whose
   billing is a flat monthly subscription with no per-word component.

   The rate is also wrong even where the shape is right: models this office
   routes to differ by roughly two orders of magnitude per token, so one
   constant is not an estimate, it is a number with a currency symbol.

   Three honest answers, and no invented fourth:

     local        — runs on the boss's own hardware; the marginal cost is
                    zero, and that IS a real number.
     subscription — a CLI hire billed by a flat plan; per-job payroll is
                    not a thing that exists, so we say so.
     metered      — genuinely costs per word, and we do not carry a rate
                    table. `—` with a tooltip beats a confident wrong
                    figure; the token count next to it is still true.

   Deliberately keyed on the ROUTING PREFIX, which is how the agent's brain
   is actually dispatched, not on the display name. */
const PAYROLL_LOCAL = /^(ollama|lmstudio):/i;
const PAYROLL_PLAN  = /^(claudecode|codex|cafresohq|hermes):/i;

function payrollLabel(agent) {
  const model = String((agent && agent.model) || '');
  if (!model) return { text: '—', title: 'No brain assigned yet, so nothing to bill.' };
  if (PAYROLL_LOCAL.test(model)) {
    return { text: 'in-house', title: 'Runs on your own hardware — no per-word charge.' };
  }
  if (PAYROLL_PLAN.test(model)) {
    return { text: 'on your plan', title: 'Covered by a subscription, not billed per word.' };
  }
  return { text: '—', title: 'Billed per word by the provider. No rate is configured here, and a made-up one would be worse than none — see the work-done count beside this.' };
}

/* §6, binding. Three surfaces show the same token count — the roster card,
   the coworker detail panel and the office total on the Situation Wall — so
   the sentence explaining it lives once, here, next to payrollLabel.
   It has to do two jobs: say what the number IS in office words, and say
   what it ISN'T. On the card it sits inches from "Jobs" (work delivered)
   and "Payroll" (what it costs), and it is neither of those. */
/* "this session" was false, and measurably so: the count lives in the
   file-backed roster record, so a full page reload returned it byte for
   byte (7,824 before and after). It has only ever been reset at hire, and
   — until that was removed — by a coffee break. Say the real span. */
const EFFORT_TIP = "Effort: how much reading and writing this coworker has done since you hired them. It is not a count of jobs — Jobs is that — and it is not a cost; Payroll is.";

/* The office-wide total wears the same word. Two surfaces show it — the
   Situation Wall and the topbar HUD — and when I renamed the per-coworker
   ones to "Effort" I updated the wall and missed the HUD, which sat there
   still saying "Work done across the office". Third copy, so it lives here
   now. */
const OFFICE_EFFORT_TIP = "Effort across the whole office — every coworker since you hired them, plus your own time with the CEO. Reading and writing, not jobs finished. Payroll stays per coworker: one total across brains that bill differently (or not at all) isn't a real number.";

/* ── Can this office actually work? ───────────────────────────────────────
   `hasUsableKey()` with no argument answers one narrow question: is the
   DEFAULT provider configured. That is the right question for the CEO's own
   chat and the wrong one for the office as a whole, because a hired coworker
   pins their own brain in their model id (`ollama:llama3.1:latest`) and the
   global setting has nothing to do with whether it runs.

   Asking the narrow question and printing the broad answer put "⚠ ADD AI KEY
   — your agents can't run until you add one" in the pinned alarm cluster of
   an office whose coworkers had just finished six jobs and filed six
   deliveries. The alarm is pinned precisely so it can never scroll away; one
   that cries wolf is worse than none.

   Same probe as the hire form's brain warning (modals/hire.jsx) — that
   surface got this right and these two didn't, which is why the shared
   version now lives here instead of a third copy.

   The client is injected so this file stays import-free for
   scripts/test_cast.py. */
function agentBrainReady(agent, C) {
  if (!agent || !C || !C.parseModelId || !C.hasUsableKey || !C.getSettings) return false;
  const parsed = C.parseModelId(agent.model) || {};
  const provider = parsed.provider, pinned = parsed.model;
  if (!provider) return false;
  const probe = Object.assign({}, C.getSettings(), { provider });
  if (pinned && provider === 'ollama')   probe.ollamaModel   = pinned;
  if (pinned && provider === 'lmstudio') probe.lmstudioModel = pinned;
  return !!C.hasUsableKey(probe);
}

/* True when SOMETHING in this office can think: the default provider, or any
   hired coworker's own brain. Unknowable → true, because an alarm you cannot
   justify must not fire. */
function officeHasBrain(agents, C) {
  if (!C || !C.hasUsableKey) return true;
  try { if (C.hasUsableKey()) return true; } catch (_e) { return true; }
  return (agents || []).some(a => agentBrainReady(a, C));
}

/* §7's third route — "pick another coworker". A failure that only offers
   "try again" is a dead end when the thing that failed is the CEO's brain:
   the CEO runs on the DEFAULT provider and a hired coworker pins their own,
   so the chief of staff being unreachable says nothing about the floor.
   Measured on a live office: the boss got "couldn't reach that brain — it
   looks offline from here" and a RETRY that could only fail again, while two
   coworkers sat at their desks on working local brains.

   Returns '' when there is nobody to hand to, so callers can append blindly.
   Lives here, beside agentBrainReady, because THREE surfaces need it and the
   first two copies of this idea had already drifted apart. */
const nameList = (names) => (
  names.length <= 1 ? (names[0] || '')
  : names.length === 2 ? `${names[0]} and ${names[1]}`
  : `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
);

/* Append the route-out to a diagnosis, closing the clause first. The
   diagnosis ends mid-thought ("…it looks offline from here"), so butting the
   hint straight on produced a run-on the first time this shipped:
   "…offline from here Llama and Mika are still working". chatErrorText had
   punctuation handling and the CEO path did not — centralising the SENTENCE
   but not the JOIN just moved the bug to whichever caller I wrote second.
   Callers get one function and cannot get it wrong. */
function withHandoff(text, agents, C) {
  const hint = handoffHint(agents, C);
  if (!hint) return text;
  let out = String(text || '');
  if (out && !/[.!?…]$/.test(out)) out += '.';
  return out + hint;
}

function handoffHint(agents, C) {
  const ready = (Array.isArray(agents) ? agents : []).filter(a => agentBrainReady(a, C));
  if (!ready.length) return '';
  /* Three names max — a route out the boss has to read twice is not a route. */
  const names = nameList(ready.slice(0, 3).map(a => a.name));
  return ready.length === 1
    ? ` ${names} is still working, though — @mention them and they can pick this up.`
    : ` ${names} are still working, though — @mention one of them and they can pick this up.`;
}

export { agentBrainReady, brainName, canDoPhrase, CAST_CLASSES, CAST_DEFAULT, EFFORT_TIP, handoffHint, memoryLabel, memoryNotes, memoryRoot, nameList, officeHasBrain, OFFICE_EFFORT_TIP, payrollLabel, poweredBy, specialtyTag, statBars, withHandoff };
