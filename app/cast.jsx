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
  // `nano` earned its place off a real shelf: LM Studio was serving
  // nemotron-3-nano and nemotron-3-nano-4b, and both fell through to the
  // generic row and advertised themselves as steady generalists. A model
  // whose name says nano is the small-and-quick class by definition.
  { re: /haiku|mini|flash|small|nano/,
                                    speed: 4, depth: 2, code: 2, cost: 3, tag: 'quick with the small stuff' },
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

/* ── Which brain a role-shaped candidate actually runs on ─────────────────
   Every OPENSWARM_ROSTER template pins `cafresohq:sonnet`, and the shelf
   rendered that verbatim. Measured 2026-08-15 on an office started with
   CAFRESOHQ_CLAUDE_BIN pointed at a path that does not exist: /agent/drivers
   reported claude-code installed:false, the front desk correctly DROPPED the
   Claude card — and one row below it, seven candidate cards still read
   POWERED BY CLAUDE. Same screen, same detection result, one row apart.

   The templates describe a ROLE — docs, slides, research, data — not a
   vendor. Pinning them to one brain is what made the shelf decorative on
   every office that does not have that brain: hire the Docs Agent on an
   Ollama-only box and it goes to a desk it can never work from.

   So the brain is chosen from what was DETECTED, and the chip reports that
   choice. `ready` is the set of driver ids the caller established are ready
   to take work — the caller must pass the same readiness it used to draw
   the front-desk cards, or the two rows go back to disagreeing, which was
   the whole defect.

   Order is free-and-local first, then subscriptions already paid for, then
   metered cloud. A boss who has both LM Studio running and a Claude
   subscription is not billed for a first hire they made by clicking a
   template — and they can change the brain on the card afterwards, which
   is the point of naming it there.

   Returns null when nothing is ready. Null is a real answer and callers
   must render it as one: a card with no brain is not a card that quietly
   picks Claude. */
const CANDIDATE_BRAINS = [
  { id: 'cafresohq',   model: 'cafresohq:sonnet' },
  { id: 'lmstudio',    model: 'lmstudio:local-model' },
  { id: 'ollama',      model: 'ollama:llama3.1' },
  { id: 'claude-code', model: 'claudecode:sonnet' },
  { id: 'codex',       model: 'codex:gpt-4.1' },
  { id: 'gemini',      model: 'gemini:gemini-2.5-pro' },
  { id: 'hermes',      model: 'hermes:hermes-agent' },
  { id: 'openrouter',  model: 'openrouter:openai/gpt-oss-120b:free' },
  { id: 'groq',        model: 'groq:llama-3.3-70b-versatile' },
  { id: 'gemini-api',  model: 'gemini-api:gemini-2.5-flash' },
];

function candidateBrain(ready) {
  const have = new Set(ready || []);
  for (const b of CANDIDATE_BRAINS) {
    if (have.has(b.id)) return b.model;
  }
  return null;
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
/* Four ids are missing from this map on purpose: 'email', 'cal', 'db' and
   'slack'. There is no EMAIL_SEND, CALENDAR, DATABASE or SLACK tool anywhere
   in the app — not ungated, absent — and an audit already established that
   and hid them from the hiring and roster checkboxes. It did not reach here,
   so the front desk kept selling them. Measured on a fresh office: Vera's
   candidate card read "CAN SEARCH THE WEB, SEND EMAIL AND MANAGE YOUR
   CALENDAR +1 MORE" and Dax's read "…AND QUERY YOUR DATABASE". This is the
   first screen a new boss sees. A capability with nothing behind it is worse
   said out loud than left off a list — the checkbox was merely inert, this
   is a sales pitch. An id with no entry here contributes no words at all. */
const CAN_DO = {
  web:    'search the web',
  /* Was "read your notes" until the room was renamed. The old words were
     wrong twice over: they named a room the boss can no longer find in the
     chrome, and they described it as notes when the Library is where decks,
     documents, images and research land too. */
  vault:  'read your Library',
  files:  'work with your files',
  code:   'run code',
  img:    'make images',
  wallet: 'spend from your wallet',
};

/* The rest are real, but conditionally, and a card that ignores the
   condition is making the same promise the never-wired four were making.
   Each value names the fact the CALLER has to establish; this file is
   import-free by design (scripts/test_cast.py runs it verbatim under node),
   so it cannot go and look any of them up, and that is the right shape
   anyway — the card asserts what it was told, not what it assumed. */
const CAN_DO_NEEDS = {
  web:    'canSearch',        // TOOL_REGISTRY.search.requires() — a Brave key
  vault:  'vaultOn',          // isVaultReady() — /vault/status says configured
  files:  'elevated',         // toolsForAgent gates FILE_* and BASH on this
  code:   'elevated',         // …the tools claim grants neither on its own
  img:    'canMakeImages',    // settings.imageProvider
  wallet: 'moneyOn',          // the Wallet ICP-Service, off by default
};

/* When the headline is not available, say the smaller true thing rather
   than nothing. A 'web' coworker always gets BROWSER_FETCH, key or no key —
   that is a real capability and worth naming, and naming it is also what
   stops "search the web" from being the only way to describe this
   coworker. The other five have no smaller version: without elevation
   there is no file access at all, not a lesser one, and an unreachable
   vault is not a read-only vault — `toolsForAgent` hands over none of
   VAULT_SEARCH/READ/APPEND/NEW, nor EXPORT_PPTX/DOCX/PDF, which ride the
   same claim. */
const CAN_DO_INSTEAD = {
  web: 'read a web page you name',
};

/* And when there is no smaller true thing to say, say what switching it on
   would buy. Measured on a fresh office, after the previous tick correctly
   stopped the card promising what it could not deliver:

     Pixel  IMAGE GENERATION  CAN READ YOUR NOTES

   Every word of that is true and it is still a bad first screen. A
   coworker whose entire role is image generation, introducing itself by
   the one incidental thing it can do, reads as a broken hire rather than
   an unconfigured one — and the boss is given nothing to act on. §7 asks
   for a way forward, and the fix the last tick declined to guess at is
   this one: name the switch, in the future tense, so the sentence is a
   route rather than a claim.

   Only for conditions the boss can actually flip from where they are
   standing.

   `elevated` was excluded here on the grounds that it is "a property of
   the candidate, decided by which template you hire, not a setting anyone
   can turn on — 'run code once you elevate them' would point at a control
   that does not exist." That was wrong when it was written. The control
   does exist and always has: a 🛡 File & shell access switch on the
   coworker's own card in Settings → Roster (modals/settings.jsx), behind
   a danger-styled confirm, which sets exactly this flag. Declining to
   name it did not protect anyone — it left the one capability with a real
   door as the only one the card refused to give a route to, which is the
   §7 miss inverted: not a false way forward, a true one withheld.

   Worded as the switch is printed, not as the flag is named, so the
   sentence can be followed to a control the boss can see. */
const CAN_DO_UNLOCK = {
  img:    'make images once you pick an image provider',
  wallet: 'spend from your wallet once you switch the Wallet service on',
  files:  'work with your files once you switch on their file & shell access',
  code:   'run code once you switch on their file & shell access',
  /* Named for the panel as it is printed — Settings → Connections →
     LIBRARY — because unlike the other four this door is nowhere near the
     coworker, and the tooltip these chips already carry sends the boss to
     Settings → Roster, where there is nothing to fix. */
  vault:  'read your Library once you connect one in Settings → Connections',
};

/* `ctx` absent means the caller does not know, and unknowable → do not
   promise. Same rule as officeCanSearch and officeHasBrain: the mirror of
   "do not alarm on unknown" is "do not sell on unknown". */
function canDoPhrase(tools, ctx) {
  ctx = ctx || {};
  /* Absent is not false. A caller that could not read the settings store
     leaves the flag off the object entirely, and "we do not know" must not
     become "we know it is off" — that would put "once you pick an image
     provider" on a card belonging to a boss who already picked one. Same
     rule as the promise above, pointed the other way. */
  const established = (k) => Object.prototype.hasOwnProperty.call(ctx, k);
  const list = [];
  /* Kept separate so a future-tense line can never push a present-tense one
     out of the three the card shows. What the coworker can do today always
     outranks what it could do after a trip to Settings. */
  const pending = [];
  for (const t of (tools || [])) {
    const say = CAN_DO[t];
    if (!say) continue;
    const need = CAN_DO_NEEDS[t];
    if (!need || ctx[need]) { if (list.indexOf(say) < 0) list.push(say); continue; }
    const instead = CAN_DO_INSTEAD[t];
    if (instead) { if (list.indexOf(instead) < 0) list.push(instead); continue; }
    const unlock = CAN_DO_UNLOCK[t];
    if (unlock && established(need) && pending.indexOf(unlock) < 0) pending.push(unlock);
  }
  const all = list.concat(pending);
  if (!all.length) return 'talk things through';
  const shown = all.slice(0, 3);
  const rest = all.length - shown.length;
  let out = shown.length === 1 ? shown[0]
          : shown.slice(0, -1).join(', ') + ' and ' + shown[shown.length - 1];
  if (rest > 0) out += ` +${rest} more`;
  return out;
}

/* The same four tables, answered as a LIST instead of a sentence.

   `canDoPhrase` is the shelf's voice: one line of prose under a candidate's
   name. Two other surfaces ask the same question in chips — the coworker
   card's "Can use" row (views/core.jsx) and the inspect panel's (ui/panels.jsx)
   — and both of them answered it by printing `agent.tools` raw, which is the
   stored CLAIM, not the grant.

   Measured live on office 9261, 2026-08-16, hiring Dax off the candidate
   shelf. His shelf card read "Can work with your files and read your notes",
   which is this file being careful: `db` has no CAN_DO entry so it
   contributed no words, and `files` was promoted off the template's
   `elevated` flag. One click later the hire form dropped elevation (see
   `loadCandidate`) — and his coworker card read

       CAN USE   FILES   VAULT   DB

   with a tooltip promising these are "what this coworker is allowed to
   reach". `files` needs elevation `toolsForAgent` was never given; `db`
   reaches nothing anywhere and has since the 2026-08-13 audit. Neither can
   be unticked at the door the same tooltip names, because
   `visibleToolsCatalog` hides both. The product told the truth on the shelf
   and reverted to the sales pitch the moment the boss said yes.

   So: an id with no CAN_DO entry is dropped, exactly as it contributes no
   words to the phrase. An id whose condition is MET is granted. An id whose
   condition is unmet but which has a smaller true version — 'web' without a
   Brave key still gets BROWSER_FETCH — is granted, carrying the smaller
   claim as its own words. Anything else is LOCKED, not dropped: the
   capability is real, the switch is nameable, and §7 wants the route shown
   rather than the row quietly shrinking.

   `established` is `canDoPhrase`'s rule and is load-bearing here for the
   same reason: a settings store that could not be read leaves the fact
   ABSENT, and absent must not become "off" — a card that cannot see the
   image provider says nothing about images rather than telling a boss who
   already picked one to go and pick one. */
function grantedTools(tools, ctx) {
  ctx = ctx || {};
  const established = (k) => Object.prototype.hasOwnProperty.call(ctx, k);
  const granted = [];
  const locked = [];
  const seen = {};
  for (const t of (tools || [])) {
    const say = CAN_DO[t];
    if (!say || seen[t]) continue;
    seen[t] = 1;
    const need = CAN_DO_NEEDS[t];
    if (!need || ctx[need]) { granted.push({ id: t, say }); continue; }
    const instead = CAN_DO_INSTEAD[t];
    if (instead) { granted.push({ id: t, say: instead }); continue; }
    if (established(need)) locked.push({ id: t, unlock: CAN_DO_UNLOCK[t] || '' });
  }
  return { granted, locked };
}

/* One tooltip, two surfaces. The coworker card and the inspect panel print
   the same list and have twice been fixed one at a time — "the twin of the
   inspect panel's row, missed when that one was renamed" is the comment on
   the card today. Same words from one place, so the next rewording is one
   edit and cannot land on only half of them. */
const CAN_USE_TIP = 'What this coworker is allowed to reach — their permissions, not a record of what they have done. Change these in Settings → Roster.';
/* Appended only when something is actually dimmed, because a legend for a
   thing that is not on screen is just more words to read. */
const CAN_USE_OFF_TIP = '\n\nDimmed and marked "off" means the capability is real but a switch it needs is not on — hover one to see which switch.';

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

/* §7 wants every failure to end in a way FORWARD, and "pick another
   coworker" is only one of them — it is the one that stops existing exactly
   when the office is emptiest.

   Driven on a genuine first run: brand-new office, nobody hired, no key.
   The boss's very first message came back

     ⚠ hit a snag — couldn't reach that brain — it looks offline from here

   and stopped there. No route, no next step, and a diagnosis that reads as
   "it will be back shortly" when nothing was configured to come back. Two
   bubbles above it, the same office had already said "We don't have a
   shared brain here" — so it contradicted itself inside one screen, on the
   first thing a new user ever types.

   It stopped there because withHandoff returns the text untouched when
   nobody can help, and the only fallback that existed lived privately
   inside chatErrorText. That split is old: ui/chat.jsx's own comment says
   "agent dispatches and the CEO stream have always been two different
   error-copy paths", written the last time something was fixed in one and
   not the other. So the ladder moves here, beside handoffHint, and both
   paths climb the same one:

     1. somebody's brain is ready      → name them
     2. nobody hired at all            → hire, or bring a brain
     3. hired, but no usable key       → bring a brain

   Rung 2 offers BOTH routes in one sentence rather than guessing between
   them, because the client cannot answer "is there a brain on this
   machine" without an async probe, and a route-out that turns out to be a
   dead end is worse than two honest ones. "Hire someone on the Team tab"
   is the office's existing words for it (features.jsx, modals/collab.jsx).

   Unknowable → say nothing: if the client can't be asked about keys, the
   diagnosis stands alone rather than gaining a guess.

   `candidates` is who may be OFFERED and `roster` is who has been HIRED,
   and they are two different lists on purpose. Callers hand over a
   filtered set — chatErrorText drops the coworker who just fell over, and
   the hand-off surfaces drop the one who refused — so in a one-coworker
   office `candidates` is empty while the floor is not. Reading rung 2 off
   that list would tell a boss who has hired somebody that nobody is
   hired, which is the same class of untruth this whole function exists to
   stop. Defaults to `candidates` so a caller with nothing to filter can
   pass one list. */
function routeOut(candidates, C, roster) {
  const hint = handoffHint(candidates, C);
  if (hint) return hint;
  /* "Settings → Keys" named a tab that does not exist. `keys` survives only
     as a deep-link alias (modals/settings.jsx SETTINGS_TAB_ALIAS, "old/removed
     id → canonical id"); the nav a boss actually sees is ACCOUNT ·
     CONNECTIONS · ROSTER · MODULES · MEDIA · APPEARANCE. This is the copy
     that fires on the emptiest office there is — first run, nobody hired, no
     brain — and it sent that boss looking for a door that was removed. Every
     other key/brain sentence in the product already says Connections,
     including line 245 of this same file. */
  const BRAIN = 'add your own AI key in Settings → Connections';
  const hired = Array.isArray(roster) ? roster : (Array.isArray(candidates) ? candidates : []);
  if (!hired.length) {
    return ` Nobody's hired yet — hire someone on the Team tab, or ${BRAIN}.`;
  }
  /* Rung 3 used to say "You’re on the shared Cafreso brain" flat out. For
     the DEFAULT provider that is not merely unverified, it is inverted:
     hasUsableKey's default branch IS `openrouterKey || _managedBrain`, and
     `_managedBrain` is the answer to "is there a shared Cafreso brain". So
     the one condition that reaches this line is the condition that has just
     established there isn't one — and the sentence fired on the emptiest
     office there is, telling a self-hosted first-run boss they were on a
     brain the CEO had told them two bubbles earlier does not exist here.

     Exactly the lesson rung 2's comment above already records, one rung
     down. So ask the client the question directly instead of inferring it
     backwards: the original sentence stands where a managed brain really is
     present (a keyless provider selected while the fleet brain is wired up),
     and where it is not, the way out is the same and the claim is dropped. */
  try {
    if (C && C.hasUsableKey && !C.hasUsableKey()) {
      let shared = false;
      try { shared = !!(C.managedBrain && C.managedBrain()); } catch (_e) {}
      return shared
        ? ` You’re on the shared Cafreso brain — you can ${BRAIN} to run independently of it.`
        : ` No brain is set up yet — ${BRAIN}.`;
    }
  } catch (_) {}
  return '';
}

/* The same join withHandoff does, over the full ladder. Kept as one
   function for the reason withHandoff's own comment gives: centralising
   the sentence but not the JOIN just moves the run-on to whichever caller
   gets written second. */
function withRouteOut(text, candidates, C, roster) {
  const tail = routeOut(candidates, C, roster);
  if (!tail) return String(text || '');
  let out = String(text || '');
  if (out && !/[.!?…]$/.test(out)) out += '.';
  return out + tail;
}

export { agentBrainReady, brainName, candidateBrain, CANDIDATE_BRAINS, canDoPhrase, CAN_DO, CAN_DO_NEEDS, CAN_DO_UNLOCK, CAN_USE_OFF_TIP, CAN_USE_TIP, CAST_CLASSES, CAST_DEFAULT, EFFORT_TIP, grantedTools, handoffHint, memoryLabel, memoryNotes, memoryRoot, nameList, officeHasBrain, OFFICE_EFFORT_TIP, payrollLabel, poweredBy, specialtyTag, routeOut, statBars, withHandoff, withRouteOut };
