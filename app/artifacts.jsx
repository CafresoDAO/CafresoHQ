import { CafresoHQClient, VaultBridge } from '../claude-client.jsx';

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
  return String(s || '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 56) || 'delivery';
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

/* Build the note that lands in the cabinet. Markdown gets a small header so
   the file stands on its own months later in Obsidian; html is written raw
   so it renders when opened. */
function buildDelivery(task, agent, text) {
  const body = stripToolMarkers(text);
  if (!body) return null;
  const home = STARTER_HOME[task && task.starter] || DEFAULT_HOME;
  const slug = slugify(task && task.title);
  const who = (agent && agent.name) || 'your team';
  const when = new Date().toISOString().slice(0, 10);

  const html = (task && task.starter === 'page') ? extractHtml(body) : null;
  if (html) return { path: `${home}/${slug}.html`, content: html, kind: 'page' };

  const content = [
    `# ${(task && task.title) || 'Delivery'}`,
    '',
    `*Delivered by ${who} · ${when}*`,
    '',
    '---',
    '',
    body,
    '',
  ].join('\n');
  return { path: `${home}/${slug}.md`, content, kind: 'note' };
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
async function fileDelivery(task, agent, text) {
  try {
    const built = buildDelivery(task, agent, text);
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

export { buildDelivery, cabinetIsEncrypted, extractHtml, fileDelivery, slugify, stripToolMarkers };
