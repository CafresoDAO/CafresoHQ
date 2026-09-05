import { CafresoHQClient, VaultBridge } from '../claude-client.jsx';
import { visitLine, visitPlace } from './floor.jsx';

/* ── Artifact landing (OFFICE_AS_INTERFACE §1 "out-tray → filing cabinet",
   §3 step 6) ──────────────────────────────────────────────────────────────
   When a task finishes, its deliverable is filed to the vault BY THE HOST.

   Why host-side and not a [VAULT_NEW:…] the agent emits: filing can't depend
   on the coworker cooperating. None of the front-desk hires claim `vault` in
   their tools, so they physically cannot call that marker — and the small
   local models that a zero-config user is most likely to hire are exactly
   the ones that would forget it. The office files the out-tray; the coworker
   just has to finish the work.

   Only TASK completions land here. A chat reply or a DM is not an artifact,
   and filing every conversational turn would bury the real deliverables. */

/* Starter cards already declared where their output belongs; everything else
   goes to one obvious shelf. Kept in step with modals/starter.jsx. */
const STARTER_HOME = { brief: 'Research', draft: 'Drafts', page: 'Sites' };
const DEFAULT_HOME = 'Deliveries';

function slugify(s) {
  /* Trim AFTER the cap as well as before it. The old order trimmed, then
     sliced — so a title long enough to be cut mid-word left the hyphen
     hanging: "Save a note to your memory saying the boss likes bullet
     points, then confirm" filed as
     `save-a-note-to-your-memory-saying-the-boss-likes-bullet-.md`.
     Caught by reading a real filename rather than the function.

     `[^a-z0-9]` is not "unsafe characters", it is "not the Latin alphabet":
     every letter of Japanese, Russian, Greek, Hebrew, Arabic and Korean was
     replaced with a dash, the trim ate the dashes, and what was left fell
     through to the `|| 'delivery'` fallback — so a boss who does not type in
     English got `Deliveries/delivery.md`, `delivery-2.md`, `delivery-3.md`
     for every task they ever finished, with the title thrown away. This is
     `#279`'s bug ("every japanese starter task was filed as note.md",
     modals/starter.jsx `filePath`) in its twin: the header above this file
     says the two are "kept in step with" each other, and only one of them
     was fixed. `\p{L}\p{N}` under /u still turns `.` and `/` into `-`, which
     is what the old class was really protecting, and the cap now counts code
     points so an astral character is never cut into a lone surrogate. */
  const cleaned = String(s || '').toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '');
  return Array.from(cleaned).slice(0, 56).join('')
    .replace(/^-+|-+$/g, '') || 'delivery';
}

/* A page deliverable is only worth saving as .html if it actually IS html.
   Models wrap it in a fence more often than not, so prefer the first fenced
   block that looks like markup, then fall back to the whole reply. Returns
   null when there's no markup — the caller then files plain markdown rather
   than writing a .html file that would open blank. */
function extractHtml(text) {
  const s = String(text || '');
  const looksHtml = (t) => /<(?:!doctype\s+html|html|body|main|section|article|div|h1)\b/i.test(t);
  const fence = /```[a-zA-Z]*\s*\n([\s\S]*?)```/g;
  let m;
  while ((m = fence.exec(s)) !== null) {
    if (looksHtml(m[1])) return m[1].trim();
  }
  return looksHtml(s) ? s.trim() : null;
}

/* Drop stray tool markers before filing. A model that emits
   "[MEMORY_WRITE: decisions/welcome.md]" the runtime didn't act on leaves the
   marker sitting in the reply, and a delivered file that opens on a line of
   machine syntax isn't a deliverable.

   Deliberately narrow on two axes: the line must be ENTIRELY one bracketed
   marker (prose that merely mentions one survives, as do markdown links like
   [Text](url) and reference definitions like [1]: http://…), and the name
   must look like OUR tool vocabulary — underscored, or fully capitalised.
   Case is not assumed: models write "Vault_APPEND" as happily as
   "VAULT_APPEND". A bare "[x]" checkbox or "[draft]" aside is left alone. */
const MARKER_LINE = /^\s*\[\s*\/?\s*([A-Za-z][A-Za-z0-9_]*)\s*(?::[^\]]*)?\]\s*$/;

function stripToolMarkers(text) {
  return String(text || '')
    .split('\n')
    .filter(line => {
      const m = MARKER_LINE.exec(line);
      if (!m) return true;
      const name = m[1];
      return !(name.includes('_') || name === name.toUpperCase());
    })
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/* Is there anything here, or only the announcement of it?

   `!!text.trim()` is the question the office used to ask, in three places,
   and it gets the all-markers case right: a reply that is nothing but
   [VAULT_NEW: …] lines strips to empty, and the run is correctly recorded as
   "came back with nothing" — SNAG, no XP, card not certified.

   One surviving line flips all of it. Measured 2026-08-15 against a canned
   brain answering with exactly this:

       Here is what I did:

       [VAULT_NEW: Research/colours.md]
       [MEMORY_WRITE: decisions/colours.md]

   cleanBuf came out as the string "Here is what I did:" — non-empty, so the
   task went green in DONE, XP was booked as a success, the floor announced
   "Nova completed …", and the cabinet got a sheet whose entire body was that
   sentence, eight lines above the office's own "Nothing opened, saved or
   looked up for this one."

   A lead-in is a promise about content, so a body of nothing but lead-ins is
   materially the empty run the office already knows how to report. Narrow on
   purpose: one line that is not a lead-in is enough to count, so a real
   answer, a heading with a body under it, or a sentence containing a colon
   anywhere but the end all pass untouched.

   Deliberately NOT swept in: a body of bulleted markers ("- [VAULT_NEW: x]")
   survives the strip by #53's decision and reads as substance here. Changing
   that is a change to what gets stripped, not to what counts as content. */
function hasSubstance(text) {
  return String(text || '')
    .split('\n')
    .map(l => l.trim())
    .filter(Boolean)
    .some(l => !/:$/.test(l) && !/^#{1,6}\s/.test(l));
}

/* ── The transcript is not the deliverable ────────────────────────────────
   While a coworker works, the floor streams every tool visit inline — the
   fetched page, the search hits, the file it opened. That is right for the
   screen: the boss is watching them work.

   It is wrong for the cabinet. A real "Three primary colours" delivery came
   back 8,833 bytes: one sentence of Llama's own answer wrapped around a
   URL, `Status: 200`, `Title: …`, a rule, Wikipedia's body text, and
   `[…truncated, 79626 more chars]`. Every one of those is §6-banned jargon,
   sitting in a file the boss keeps.

   `echoes` are the exact strings the runtime appended (handed over on the
   tool `done` event, so the format is defined once and undone by literal
   match — no regex hunting for a block whose end is genuinely ambiguous,
   since a fetched page contains blank lines too). */
function stripToolEcho(text, echoes) {
  let out = String(text || '');
  for (const echo of (echoes || [])) {
    if (!echo) continue;
    out = out.split(echo).join('\n\n');   // literal removal; keeps the break
  }
  return out.replace(/\n{3,}/g, '\n\n').trim();
}

/* …but deleting the working outright would launder the sources. A memo that
   silently reports Wikipedia's answer as the coworker's own is LESS honest
   than the transcript was, not more. So the visits come back as a short
   footer in office words (§6): what they consulted, never which tool.

   The phrasing is `visitLine` from app/floor.jsx — the same table that
   writes the desk bubble, the activity row and the chat echo. This module
   had its own copy of it, which is how the office ends up describing one
   filing-cabinet trip four different ways. */
function workingNotes(visits) {
  const seen = [];
  for (const v of (visits || [])) {
    if (!v || !v.name) continue;
    /* visitPlace for the argument-less tools. MEMORY_LIST takes no argument,
       so `visitLine` returns null for it and this loop used to `continue` —
       silently dropping a real visit from the record. Caught on a clean
       first run: a delivery whose footer listed one source when the
       coworker had visited two.

       Under-reporting the working is the same failure as over-reporting it.
       The live surfaces already fell back to the floor's placard; the filed
       note is the one that outlives the session, so it least of all should
       be the surface that forgets. */
    /* Past tense only for a trip that arrived. `failed` has been on the done
       event since 2026-08-13, when the office was caught captioning a failed
       DIR_LIST "📁 Opened ./site" above its own "Not a directory: ./site" —
       and every live surface was taught to read it. This one was not, so the
       filed note went on writing "Read www.gartner.com/…" for a page that
       answered 403.

       Measured 2026-08-14: a brief asked for analyst citations fetched
       Gartner, Forrester and McKinsey, and got 403, 404, 403 — zero bytes,
       confirmed against serve.py's own log and re-run by hand. The coworker
       said so plainly in its reply. The footer beneath it listed all three
       as Read, so the office's record called its own coworker a liar for
       telling the truth. The note four lines up says the filed note least of
       all should be the surface that forgets; it was forgetting the other
       half of the same fact. */
    const tense = v.failed ? 'fail' : 'past';
    const line = visitLine(v.name, v.arg, tense) || visitPlace(v.name, tense);
    const row = `- ${line}`;
    if (seen.indexOf(row) === -1) seen.push(row);
  }
  return seen;
}

/* ── Naming a source you never visited ────────────────────────────────────
   The always-written footer puts the office's record beneath the coworker's
   claim, but it argues in silence: a real brief (2026-08-12) cited a Harvard
   Business Review article that does not appear to exist, with "Nothing
   opened, saved or looked up for this one." four lines below. An invented
   vault path is checkable in one click; an invented journal article looks
   authoritative, and a reader who trusts the bullet has no reason to scroll
   down and cross-examine a footer. Both facts — record empty, reply claims
   sources — are known at filing time, so when they contradict, the office
   can say so instead of leaving the disagreement as an exercise.

   Deliberately narrow, because flagging an honest reply is the same §7
   failure pointed the other way. The research brief itself invites
   "(Source: what I already know)", so a bare "Source:" match would fire on
   exactly the compliant behaviour the office asked for. Only two shapes
   count as pointing OUTSIDE the coworker's own head:
   - a URL — no visits means nothing was fetched, so it was not read;
   - a source attribution ("Source: …" at a line's start, or "(Source: …)")
     whose named source is NOT the coworker's own knowledge.
   A quoted title floating in prose is left alone — the placeholder-detector
   post-mortem in OFFICE_AS_INTERFACE.md shows how an "exact" prose pattern
   still cries wolf on ordinary sentences. Misses fall back to the passive
   footer, which is the standing mitigation; false alarms have no fallback. */
const OWN_HEAD = new RegExp('\\b(?:' + [
  'what (?:i|they) (?:already )?know', 'already knew',
  '(?:my|their|its) (?:own )?(?:knowledge|memory|experience|understanding|training|head)',
  '(?:general|common|prior|existing|internal|background) knowledge',
  'training data', 'from memory', 'recall(?:ed)?',
  'no (?:specific |particular |single )?(?:source|citation)',
  "(?:don'?t|do not|doesn'?t|does not) have a (?:source|citation)",
  'unsure', 'not sure', 'none', 'n/a',
].join('|') + ')\\b', 'i');

/* The third shape, added 2026-08-14 after the guard above missed the most
   ordinary citation form there is. A research brief came back with four
   attributions — `(Gartner, 2027)`, `(Forrester, 2026)`, `(McKinsey, 2026)`,
   `(Gartner, 2027)` — two of them wrapping quoted text, on an empty record.
   Not one contains the word "source", so `citesOutside` returned false and
   the extra line never printed. The footer said "Nothing opened, saved or
   looked up" 200 words below the first citation and left it at that.

   Author-year is a citation by construction: a proper name and a year in one
   parenthesis points at a document. Three things keep the name narrow, and
   they are not interchangeable — a fire arm that relaxed the wrong one
   changed no behaviour at all, which is how the first draft of this comment
   was caught crediting the wrong rule:

   - no digits in the name, which is what actually excludes "(Q3, 2026)" and
     "(FY24, 2025)";
   - not a month, which excludes "(January, 2026)" — a date, not a source;
   - at least one lowercase letter, which excludes bare acronyms.

   That last rule costs real citations: "(HBR, 2026)" and "(IEEE, 2024)" are
   missed. Deliberate, and the trade is the same one the rest of this section
   makes — a miss falls back to the passive footer, which is the standing
   mitigation, while a false alarm on an honest reply has nothing beneath
   it. */
const MONTH = /^(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)/i;
const AUTHOR_YEAR = /\(\s*([A-Z][A-Za-z&.'-]*[a-z][A-Za-z&.'\- ]{0,38}?)\s*,\s*((?:19|20)\d{2})\s*\)/g;

function citesOutside(text) {
  const s = String(text || '');
  if (/\bhttps?:\/\/[^\s)]|\bwww\.[a-z0-9-]+\.[a-z]{2}/i.test(s)) return true;
  const tag = /(?:^[ \t>*+-]*|\()sources?\s*:\s*([^)\n]*)/gim;
  let m;
  while ((m = tag.exec(s)) !== null) {
    const named = m[1].trim();
    if (named && !OWN_HEAD.test(named)) return true;
  }
  AUTHOR_YEAR.lastIndex = 0;
  while ((m = AUTHOR_YEAR.exec(s)) !== null) {
    const named = m[1].trim();
    if (named && !MONTH.test(named) && !OWN_HEAD.test(named)) return true;
  }
  return false;
}

/* A cited year that has not happened yet, which is a different and much
   harder fact than "the record is empty". Two of the four attributions above
   read `(Gartner, 2027)` and were filed on 2026-08-14. No record, empty or
   full, explains reading a document dated next year — a coworker that DID
   search still cannot have found it. So this line is not conditional on the
   visit list, and it is not a judgement: the office states the year it was
   handed and the year it is, and stops there.

   Only years already inside a citation count. A forecast in prose — "adoption
   should reach 50% by 2030" — is an ordinary sentence, and a detector that
   read every four-digit number would flag every roadmap the office ever
   writes. */
function citedFutureYears(text, now) {
  const year = (now || new Date()).getFullYear();
  const found = [];
  let m;
  AUTHOR_YEAR.lastIndex = 0;
  while ((m = AUTHOR_YEAR.exec(String(text || ''))) !== null) {
    const n = Number(m[2]);
    if (!MONTH.test(m[1].trim()) && n > year && found.indexOf(n) === -1) found.push(n);
  }
  return found.sort();
}

/* The office runs on the boss's clock. `toISOString()` stamps UTC, so a
   delivery filed at 8pm in New York was dated TOMORROW in its own header —
   caught on a real filing. Every other date on the floor is local. */
function officeDate(now) {
  const d = now || new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/* The same rule with a clock time on it, for stamps a human reads INSIDE a
   filed note — the `generated:` frontmatter, a memory append's heading. Those
   were UTC too, so a note written at 2:30 AM in California claimed 09:30 in
   its own header, right under a filename the office had already dated
   locally. Nothing parses these stamps; they exist to tell the boss when the
   note was written, which makes the boss's clock the only correct one. */
function officeStamp(now) {
  const d = now || new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${officeDate(d)} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

/* Build the note that lands in the cabinet. Markdown gets a small header so
   the file stands on its own months later in Obsidian; html is written raw
   so it renders when opened. */
function buildDelivery(task, agent, text, visits) {
  const body = stripToolMarkers(stripToolEcho(text, (visits || []).map(v => v && v.echo)));
  /* Not `if (!body)`. That guard was right about what it was for and drew the
     line one character too generously — see hasSubstance for the sheet a
     lead-in-only body produced. */
  if (!hasSubstance(body)) return null;
  const home = STARTER_HOME[task && task.starter] || DEFAULT_HOME;
  const slug = slugify(task && task.title);
  const who = (agent && agent.name) || 'your team';
  const when = officeDate();

  const html = (task && task.starter === 'page') ? extractHtml(body) : null;
  if (html) return { path: `${home}/${slug}.html`, content: html, kind: 'page' };

  const working = workingNotes(visits);
  /* An empty record under a reply that names sources is a contradiction the
     office can state, not just make available — see citesOutside above. The
     wording reports what the office observed; it does not judge the reply. */
  const record = working.length
    ? working.slice()
    : ['- Nothing opened, saved or looked up for this one.'];
  /* "Nothing was read" and "the record is empty" are different facts, and
     the gate used to be the second one. Three refused fetches fill the
     record three rows deep and still consult nothing, so a brief citing
     sources on top of them slipped past a check written for exactly that
     case. What matters is whether any trip arrived. */
  const consulted = (visits || []).some(v => v && v.name && !v.failed);
  if (!consulted && citesOutside(body)) {
    record.push(working.length
      ? '- Every source this run tried to open was refused, so nothing above was checked against one — treat the citations as recalled.'
      : '- The note above mentions sources, but nothing was opened or searched while it was written — treat those as recalled, not checked.');
  }
  /* A path named in the body with no cabinet write behind it. This is the
     one the footer below was written for and could not reach: measured on a
     fresh office, the LAN brain answered a "write it and file it" brief with
     "I will write a 400-word briefing … and save it to the vault under
     `Drafts/Sourdough_Feeding_Briefing.md`", the board went green, and this
     sheet carried that sentence as the deliverable with "Nothing opened,
     saved or looked up for this one" eight lines under it. Two true records
     of one run, disagreeing, neither pointing at the other.

     `unwrittenPaths` below owns the detection, and drops any path this run
     actually opened — see its comment for the run where these two lines of
     the record contradicted each other about one file. */
  const promised = unwrittenPaths(body, visits);
  if (promised.length) {
    record.push(`- ${promised.map(p => `\`${p}\``).join(' and ')} `
      + `${promised.length > 1 ? 'are' : 'is'} named above, but nothing was `
      + `written to the cabinet on this run — this sheet is the only file it `
      + `produced.`);
  }
  const ahead = citedFutureYears(body);
  if (ahead.length) {
    record.push(`- ${ahead.join(' and ')} ${ahead.length > 1 ? 'have' : 'has'} not happened yet`
      + `, so nothing published ${ahead.length > 1 ? 'in those years' : 'that year'} can have been read — check ${ahead.length > 1 ? 'those citations' : 'that citation'} before relying on it.`);
  }
  const content = [
    `# ${(task && task.title) || 'Delivery'}`,
    '',
    `*Delivered by ${who} · ${when}*`,
    '',
    '---',
    '',
    body,
    /* The Working footer is ALWAYS written, even empty. It used to be
       omitted when there were no visits, which made "this coworker consulted
       nothing" and "this delivery predates the footer" look identical, and
       left an absence where the honest thing is a sentence.

       That matters because of what models actually file. A real delivery came
       back "Yellow." followed by "[Vault path: Research/banana-colour.md]" —
       an invented filing, no Research folder anywhere. The office knows
       exactly what IT did, and stating that plainly puts the record directly
       beneath the claim, where a reader can see they disagree. Same
       principle as the unclosed-write guard: an absence loses against a
       confident sentence, so turn the absence into a statement.

       This comment used to end "the office cannot detect the claim: it is
       prose, it carries no marker, and guessing which sentences are claims
       would mean editing a coworker's words." Half right, and the half it
       got wrong sat here for two months. Guessing which SENTENCES are claims
       would indeed be editing; recognising a path is not guessing, and
       `claimedPaths` above does it off a shape rather than a meaning. The
       record no longer waits to be read next to the claim — it names it. */
    '', '---', '', '**Working**', '',
    ...record,
    '',
  ].join('\n');
  return { path: `${home}/${slug}.md`, content, kind: 'note' };
}


/* ── When the coworker filed it themselves ────────────────────────────────
   §3.6 files host-side because filing "can't depend on the coworker
   cooperating". True for the front-desk hires, which hold no vault tools at
   all. But the SPECIALIST roles are the opposite case: Kip is told to save a
   research note to `Research/<topic>.md`, Sloan to render a real `.pptx`,
   Quill a `.docx`. They do file, deliberately, at a path they chose and told
   the boss about.

   The host then filed a SECOND copy at `Deliveries/<slug>.md`, and pointed
   `task.artifactPath` — the out-tray's "open the latest", the delivery
   sheet — at its own duplicate rather than at the file the specialist
   actually produced. Two copies of one deliverable in the cabinet, and the
   click went to the wrong one.

   Only tools that write to the CABINET count. Deliberately excluded:
   - MEMORY_WRITE / MEMORY_APPEND — the coworker's private notes folder
     (`Agents/<name>/`), not a deliverable for the boss;
   - FILE_WRITE — the workspace on disk, not the vault.
   Getting that wrong would suppress the host's filing for a task that
   produced no cabinet artifact at all, which is worse than a duplicate. */
const CABINET_WRITE = /^(VAULT_NEW|VAULT_APPEND|EXPORT_PPTX|EXPORT_DOCX|EXPORT_PDF|GENERATE_IMAGE|GENERATE_VIDEO)$/i;

/* Paths a coworker NAMED in its prose, as opposed to paths it wrote.
   `agentFiledPath` above answers the second question off the visit log; this
   answers the first off the text, and the gap between them is the claim.

   Narrow on purpose, and all of the narrowness is in the shape. A folder, a
   slash and a document extension are all required, so "the vault" or a bare
   `Drafts` says nothing. Two features carry every URL exclusion between
   them, and both are in the pattern rather than in a test after it. A match
   may only OPEN at a boundary — start of string, whitespace, backtick,
   quote, paren, asterisk — and the folder charset `[\w-]` admits no dot. So
   `https://example.com/docs/report.md` has nowhere to begin: not at
   `example` (preceded by `/`), not at `com` (preceded by `.`), not at
   `docs` or `report` either. A coworker naming a page it read is never
   read as a coworker claiming to have filed it.

   Two further guards used to sit in the loop below — a `head.indexOf('.')`
   test and a look-behind for `/` or `@` — and the fire test found neither
   could ever fire. The first segment cannot hold a dot, and nothing
   mid-URL can open a match, so both were reassurance rather than logic:
   six probes across URL, elided and email forms produced zero hits between
   them. Deleted rather than left in, because a dead guard is exactly what
   you trust when the live one is the part that broke — and the arm that
   deleted one of them passed, which is how they were found. A miss costs a
   caveat; a false alarm calls an honest coworker a liar, and that is the
   more expensive mistake.

   No spaces inside a segment, and that rule was written by the test. A
   first cut allowed them, because real vault notes are allowed them —
   `Research/My Notes.md` is a legal path — and on "Filed to Research/a.md
   and also Reports/b.md" the segment ran straight through the prose and
   matched `Research/a.md and also Reports/b.md` as ONE file. That is worse
   than missing both: the note would have quoted the boss a filename that
   nobody, coworker or office, had ever written. Models overwhelmingly emit
   `Sourdough_Feeding_Briefing.md`, so the space costs little, and a miss
   costs only the caveat. */
const CLAIMED_PATH =
  /(?:^|[\s`("'*])([A-Za-z][\w-]*(?:\/[\w.-]+)*\/[\w.-]+\.(?:md|txt|pptx|docx|pdf|csv|png|jpe?g))/g;

function claimedPaths(text) {
  const t = String(text || '');
  const out = [];
  let m;
  CLAIMED_PATH.lastIndex = 0;
  while ((m = CLAIMED_PATH.exec(t))) {
    const p = m[1];
    if (out.indexOf(p) < 0) out.push(p);
  }
  return out;
}

function agentFiledPath(visits) {
  let last = null;
  for (const v of (visits || [])) {
    /* A VAULT_NEW that THREW still leaves a visit behind — `arg` is the path
       it was trying to write, `failed` is the server saying it never landed
       (hq-runtime.jsx's tool loop: catch sets `meta.failed = true`, the
       `arg` on the done event is unchanged). Skipping the failed check here
       meant a write that errored out still won `last`, so the host treated
       the coworker as having self-filed at a path that was never created —
       and because `ownPath` came back truthy, app.jsx's
       `ownPath || await fileDelivery(...)` never ran the host's own
       fallback filing either. The task's artifactPath — the out-tray's
       "open the latest" — pointed at a cabinet entry that plain doesn't
       exist, and the delivery that should have landed as a host-filed copy
       never landed at all. `unwrittenPaths` and `consulted` below both
       already skip `v.failed` for the same reason; this one didn't. */
    if (!v || v.failed || !CABINET_WRITE.test(String(v.name || ''))) continue;
    const p = String(v.arg || '').trim();
    if (p) last = p;          // the newest write wins — that's the deliverable
  }
  return last;
}

/* ── A file the office OPENED is a file that is there ─────────────────────
   Measured live 2026-08-15, office 9261, task "Vendor pick". The coworker
   read a vault note and said so; the sheet's own Working record said so on
   the line above; and then the next line said this:

     - Opened Research/vendors.md in the cabinet
     - `Research/vendors.md` is named above, but nothing was written to the
       cabinet on this run — this sheet is the only file it produced.

   Two consecutive lines of the office's own record, contradicting each
   other about one file. The second is the "named a path, wrote nothing"
   guard, and it was asking only half of its own question: it checked
   whether anything had been WRITTEN and never whether this path had been
   READ. On a read, the two facts it calls a contradiction are not one —
   nothing was written because nothing needed to be, and the file it says is
   not there is the file the office had open a moment earlier.

   §7's rule is no lies to the boss, and the expensive direction here has
   always been the false alarm: a miss costs a caveat, a false alarm calls an
   honest coworker a liar. This is that mistake with the office's own visit
   log sitting right there disproving it.

   Only a trip that ARRIVED suppresses. A failed read proves the opposite —
   the file could not be opened — and the note's conclusion holds, so
   `failed` visits are skipped here exactly as they are in the Working
   record's tense and in `consulted` above.

   Any tool, not just the cabinet ones. `FILE_WRITE src/index.js` followed by
   "saved to src/index.js" hit the same false alarm — the note would say a
   file the office had just written to disk was not there, because the write
   was to the workspace rather than the vault. What the office knows is
   narrower and truer than the tool taxonomy: it touched this exact path this
   run, and the trip arrived.

   One function, and both doors call it. `unfiledPath` in hq-runtime.jsx and
   `buildDelivery`'s footer above each carried their own copy of "named, and
   nothing wrote it" — the same two-implementations-of-one-rule shape #81 was
   about, and both had this same half-question in them. The wordings still
   differ, because the sheet is talking about itself and the chat note is
   not; the DETECTION is now in one place. */
function normVisitPath(s) {
  return String(s || '').trim().replace(/^(?:\.\/|\/)+/, '').toLowerCase();
}

function unwrittenPaths(text, visits) {
  if (agentFiledPath(visits)) return [];
  const touched = [];
  for (const v of (visits || [])) {
    if (!v || v.failed) continue;
    const p = normVisitPath(v.arg);
    if (p) touched.push(p);
  }
  return claimedPaths(text).filter(p => touched.indexOf(normVisitPath(p)) < 0);
}

/* True when the cabinet really is end-to-end encrypted — i.e. this HQ is
   framed by the trusted shell that holds the user's identity and does the
   vetKeys work. A plain local vault folder is NOT encrypted, and the
   delivery sheet must not claim otherwise (§4 "animations must be honest"
   applies to copy too). */
function cabinetIsEncrypted() {
  try { return !!(VaultBridge && VaultBridge.isAvailable && VaultBridge.isAvailable()); }
  catch (_e) { return false; }
}

/* ── One filename, two deliveries ─────────────────────────────────────────
   The filed path is `${home}/${slugify(task.title)}.md`, and NOTHING about
   it is unique: the folder is one of four constants and the slug is the
   boss's own words, capped at 56 characters. `mode: 'write'` on
   PUT /vault/note is a REPLACE on every backend the Library has (serve.py:
   `target.write_text(body)`; REST: PUT; OCI: put_object), so the second
   delivery to land on a name silently destroyed the first.

   Two ordinary ways to get there, neither of them exotic:
   - the same brief given to two coworkers to compare their answers — the
     starter card builds the title from the subject, so both tasks are
     "Research brief: how small teams price a new product" and both file to
     `Research/research-brief-how-small-teams-price-a-new-p.md`;
   - two different briefs whose first ~41 characters agree, since the slug
     is cut at 56 and "Research brief: " already spends 16 of them.

   In both cases the boss watched two tasks go green, saw the out-tray count
   two deliveries, and had one file — and BOTH tasks' `artifactPath` pointed
   at it, so "open the latest" on the first coworker opened the second
   coworker's work under the first one's name. Silent, and the surviving
   sheet's own header names the wrong author.

   agent_runner.jsx's child-note writer had exactly this bug and exactly
   this fix (`pathTaken` + a step loop); the deliverable filer, the writer
   the boss meets first, never got it. `pathIsFree` is conservative the same
   way: only a real 404/"not found" clears a name. Offline, 502, a binary
   415 — the answer is unknown, and unknown is not permission to replace.
   If nothing in 20 steps is free the office files NOTHING and reports no
   artifact, which is honest and reversible; overwriting is neither. */
async function pathIsFree(path) {
  try { await CafresoHQClient.vaultRead(path); return false; }   // already taken
  catch (e) { return /not found|404/i.test((e && e.message) || ''); }
}

function stepPath(path, n) {
  if (n <= 1) return path;
  const p = String(path || '');
  const dot = p.lastIndexOf('.');
  const slash = p.lastIndexOf('/');
  return dot > slash + 1 ? `${p.slice(0, dot)}-${n}${p.slice(dot)}` : `${p}-${n}`;
}

/* File a finished task's deliverable. Resolves to the vault path, or null if
   there's nothing to file / no cabinet configured. NEVER throws: a filing
   failure must not take down task completion, which already succeeded. */
async function fileDelivery(task, agent, text, visits) {
  try {
    const built = buildDelivery(task, agent, text, visits);
    if (!built) return null;
    const st = await CafresoHQClient.vaultStatus();
    if (!st || !st.configured || !st.exists) return null;   // no cabinet yet
    let target = '';
    for (let n = 1; n <= 20; n++) {
      const candidate = stepPath(built.path, n);
      /* A re-run of the SAME task refreshes its own sheet rather than
         growing -2, -3, … beside it: that file is this task's, and the
         boss asked for it again. Anyone else's sheet is stepped past. */
      if (task && task.artifactPath === candidate) { target = candidate; break; }
      if (await pathIsFree(candidate)) { target = candidate; break; }
    }
    if (!target) return null;   // no free name — file nothing rather than replace
    await CafresoHQClient.vaultWrite(target, built.content, 'write');
    return target;
  } catch (_e) {
    // Cabinet unreachable, or the deliverable defeated the builder. The
    // result still lives on the task; the caller runs inside the completion
    // try/catch, so escaping here would mark a task that SUCCEEDED as failed.
    return null;
  }
}

/* One line on purpose: scripts/test_artifacts.py lifts the pure half of this
   file by dropping lines that START with `export`, so a wrapped export list
   leaves an orphan line behind and the harness won't parse. */
export { agentFiledPath, buildDelivery, cabinetIsEncrypted, citesOutside, claimedPaths, extractHtml, fileDelivery, hasSubstance, officeDate, officeStamp, slugify, stripToolEcho, stripToolMarkers, unwrittenPaths, workingNotes };
