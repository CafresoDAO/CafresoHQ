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
     Caught by reading a real filename rather than the function. */
  return String(s || '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 56)
    .replace(/-+$/, '') || 'delivery';
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
    const line = visitLine(v.name, v.arg, 'past') || visitPlace(v.name, 'past');
    const row = `- ${line}`;
    if (seen.indexOf(row) === -1) seen.push(row);
  }
  return seen;
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
  if (!body) return null;
  const home = STARTER_HOME[task && task.starter] || DEFAULT_HOME;
  const slug = slugify(task && task.title);
  const who = (agent && agent.name) || 'your team';
  const when = officeDate();

  const html = (task && task.starter === 'page') ? extractHtml(body) : null;
  if (html) return { path: `${home}/${slug}.html`, content: html, kind: 'page' };

  const working = workingNotes(visits);
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
       an invented filing, no Research folder anywhere. The office cannot
       detect the claim: it is prose, it carries no marker, and guessing which
       sentences are claims would mean editing a coworker's words. But the
       office knows exactly what IT did, and stating that plainly puts the
       record directly beneath the claim, where a reader can see they
       disagree. Same principle as the unclosed-write guard: an absence loses
       against a confident sentence, so turn the absence into a statement. */
    '', '---', '', '**Working**', '',
    ...(working.length ? working : ['- Nothing opened, saved or looked up for this one.']),
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

function agentFiledPath(visits) {
  let last = null;
  for (const v of (visits || [])) {
    if (!v || !CABINET_WRITE.test(String(v.name || ''))) continue;
    const p = String(v.arg || '').trim();
    if (p) last = p;          // the newest write wins — that's the deliverable
  }
  return last;
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

/* File a finished task's deliverable. Resolves to the vault path, or null if
   there's nothing to file / no cabinet configured. NEVER throws: a filing
   failure must not take down task completion, which already succeeded. */
async function fileDelivery(task, agent, text, visits) {
  try {
    const built = buildDelivery(task, agent, text, visits);
    if (!built) return null;
    const st = await CafresoHQClient.vaultStatus();
    if (!st || !st.configured || !st.exists) return null;   // no cabinet yet
    await CafresoHQClient.vaultWrite(built.path, built.content, 'write');
    return built.path;
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
export { agentFiledPath, buildDelivery, cabinetIsEncrypted, extractHtml, fileDelivery, officeDate, officeStamp, slugify, stripToolEcho, stripToolMarkers, workingNotes };
