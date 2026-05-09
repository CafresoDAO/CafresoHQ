/* ==========================================================================
   CafresoAI — mock data + small utilities
   Integration points for real API calls are marked with   // INTEGRATE:
   ========================================================================== */

const AGENT_COLORS = ['rose','teal','sun','leaf','sky'];

const ROLES = [
  'Head of Inbox Wrangling',
  'Chief Research Goblin',
  'Calendar Sommelier',
  'Docs Archivist',
  'Numbers Whisperer',
  'Creative Director',
  'Code Gremlin',
  'Growth Hunter',
];

const TOOLS_CATALOG = [
  { id: 'web',   label: 'Web Search' },
  { id: 'vault', label: 'Vault Notes'},
  { id: 'code',  label: 'Code Exec'  },
  { id: 'files', label: 'File Access'},
  { id: 'email', label: 'Email Send' },
  { id: 'cal',   label: 'Calendar'   },
  { id: 'db',    label: 'Database'   },
  { id: 'slack', label: 'Slack'      },
  { id: 'img',   label: 'Image Gen'  },
];

/* Legacy unprefixed IDs — kept for any callers still reading MOCK.MODELS.
   The live ModelPicker (window.OpenclawClient.localModelOptions) is the
   source of truth for new code; agents store provider-prefixed ids. */
const MODELS = [
  'anthropic:claude-opus-4-7',
  'anthropic:claude-sonnet-4-6',
  'anthropic:claude-haiku-4-5-20251001',
];

const INITIAL_AGENTS = [
  {
    id: 'a_mira',
    name: 'Mira',
    role: 'Head of Inbox Wrangling',
    color: 'rose',
    status: 'busy',
    task: 'triaging 23 emails',
    tools: ['web','email','cal'],
    model: 'openclaw:sonnet',
    elevated: true,
    temperature: 0.4,
    hiredAt: Date.now() - 1000 * 60 * 60 * 18,
    lastRun: '2m ago',
    nextRun: 'continuous',
  },
  {
    id: 'a_kip',
    name: 'Kip',
    role: 'Chief Research Goblin',
    color: 'teal',
    status: 'active',
    task: 'scanning Q3 reports',
    tools: ['web','files','db'],
    model: 'openclaw:sonnet',
    elevated: true,
    temperature: 0.6,
    hiredAt: Date.now() - 1000 * 60 * 60 * 56,
    lastRun: '14m ago',
    nextRun: 'in 4h',
  },
  {
    id: 'a_bop',
    name: 'Bop',
    role: 'Calendar Sommelier',
    color: 'sun',
    status: 'idle',
    task: 'standing by',
    tools: ['cal','email'],
    model: 'openclaw:sonnet',
    elevated: true,
    temperature: 0.2,
    hiredAt: Date.now() - 1000 * 60 * 60 * 120,
    lastRun: '1h ago',
    nextRun: 'on demand',
  },
];

const INITIAL_CHAT = [
  { id: 1, from: 'ceo', name: 'CafresoAI', text: "Morning, boss! What's on the agenda? I brewed the mock coffee." },
  { id: 2, from: 'user', name: 'You', text: 'Pull the competitor landscape notes together and prep a 1-pager.' },
  { id: 3, from: 'ceo', name: 'CafresoAI', text: "On it. I'll hand the research to Kip and keep the drafting here." },
  { id: 4, from: 'agent', name: 'Kip · Research', text: 'Scanning 12 sources. First pass in ~6 minutes.' },
];

const ACTIVITY_SEED = [
  { agent: 'Mira', msg: 'archived 8 newsletters' },
  { agent: 'Kip',  msg: 'found 3 relevant papers on GPU pricing' },
  { agent: 'Bop',  msg: 'proposed 2 slots for Thursday review' },
  { agent: 'Mira', msg: 'drafted reply to vendor@foundry' },
  { agent: 'Kip',  msg: 'summarized TechCrunch piece on retention' },
];

// Utility
function uid(prefix='id') { return prefix + '_' + Math.random().toString(36).slice(2, 8); }

/* Token throttle: streamed tokens arrive 30–100x/sec. If we call setChat
   per token, every update re-traverses the entire chat array and React
   diffs the whole list — fine with 10 messages, lethal at 200. This
   helper buffers tokens and flushes once per animation frame.
   It also runs cleanHarmony() over the accumulated raw text on every
   flush, so harmony-format models (gpt-oss, qwen, etc.) never display
   their channel/commentary scaffolding to the user.
   Notes (diagnostic hints emitted by agentStream) go through the .note()
   channel which is APPENDED post-cleanHarmony so they aren't eaten by the
   regex when a commentary block runs to end-of-buffer. */
function throttleTokens(setChat, msgId) {
  let raw = '';                    // full accumulated stream (cleaned for display)
  let suffix = '';                 // out-of-band notes; bypass cleanHarmony
  let scheduled = false;
  let cancelled = false;
  const schedule = () => {
    if (scheduled || cancelled) return;
    scheduled = true;
    if (typeof requestAnimationFrame !== 'undefined') requestAnimationFrame(flush);
    else setTimeout(flush, 16);
  };
  const flush = () => {
    if (cancelled) return;
    scheduled = false;
    const display = cleanHarmony(raw) + suffix;
    setChat(prev => prev.map(m => m.id === msgId ? { ...m, text: display } : m));
  };
  const ontok = (tok) => { raw += tok; schedule(); };
  ontok.note = (text) => { suffix += (suffix ? '\n\n' : '\n\n') + text; schedule(); };
  ontok.flushNow = () => { flush(); };
  ontok.cancel = () => { cancelled = true; };
  ontok.raw = () => raw;
  return ontok;
}

/* Find a [NEEDS_APPROVAL: ...] marker in agent/CEO output. Returns the
   description string (without the wrapping), or null. Tolerant of
   bracket/case/whitespace variations. */
function extractApproval(text) {
  if (!text) return null;
  const m = String(text).match(/\[\s*NEEDS[_ ]APPROVAL\s*:\s*([^\]\n]+)\]/i);
  return m ? m[1].trim() : null;
}

/* Find ALL [ACK: <state>: <note>] markers in `text`. Returns
   [{state, note}, ...] in document order.

   ACK is a lightweight "I'm still alive, here's where I am" signal an agent
   can emit at any point in their reply — unlike DM_TO it does not halt the
   stream or trigger a round-trip. The host strips the markers from the
   displayed text and routes them to MessageRegistry.transition() so the
   inbox / graph reflect live progress without the boss having to ask
   "what's happening?".

   Allowed states (agent-side):
     in_progress, blocked, awaiting_reply, completed
   The host ignores agent-emitted `failed`/`cancelled`/`delivered`/`queued`
   — those are system-set transitions and an agent shouldn't be able to
   spoof them. */
function extractAcks(text) {
  const re = /\[\s*ACK\s*:\s*([a-z_]+)\s*(?::\s*([^\]]*))?\]/gi;
  const out = [];
  let m;
  const ALLOWED = new Set(['in_progress','blocked','awaiting_reply','completed']);
  while ((m = re.exec(String(text || ''))) !== null) {
    const state = String(m[1] || '').trim().toLowerCase();
    if (!ALLOWED.has(state)) continue;
    out.push({ state, note: String(m[2] || '').trim() });
  }
  return out;
}
/* Strip every [ACK: …] marker from `text` (used to clean the agent's
   visible output before it lands in chat / journal). Idempotent. */
function stripAcks(text) {
  return String(text || '').replace(/\[\s*ACK\s*:\s*[a-z_]+\s*(?::\s*[^\]]*)?\]\s*/gi, '');
}

/* Find an [DM_TO: name]\n<body>\n[/DM_TO] block. Returns {to, body} or null. */
function extractDM(text) {
  if (!text) return null;
  const m = String(text).match(/\[\s*DM_TO\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*DM_TO\s*\]/i);
  return m ? { to: m[1].trim(), body: (m[2] || '').trim() } : null;
}

/* Find ALL [DM_TO: name] blocks in `text`. Returns [{to, body}, ...] in
   order of appearance. Used by the team-chatter loop so that an agent
   sending DMs to multiple coworkers in one reply actually triggers
   dispatch for all of them, not just the first. */
function extractAllDMs(text) {
  if (!text) return [];
  const out = [];
  const re = /\[\s*DM_TO\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*DM_TO\s*\]/gi;
  let m;
  while ((m = re.exec(text)) !== null) {
    out.push({ to: m[1].trim(), body: (m[2] || '').trim() });
  }
  return out;
}

/* Parse a leading @mention from a user message — "@kip pull the report"
   returns {targetName: 'kip', body: 'pull the report'}. Multi-word names
   not yet supported (would need quoting); first whitespace ends the name. */
function extractMention(text) {
  if (!text) return null;
  const m = String(text).match(/^\s*@([A-Za-z][A-Za-z0-9_-]*)\s+(.+)$/s);
  return m ? { targetName: m[1].trim(), body: m[2].trim() } : null;
}

/* Parse ALL leading @mentions from a user message. Supports:
     "@plato @selvin discuss the migration"
     "@plato discuss the migration"           (single mention, same as extractMention)
     "  @plato  @selvin  @gpt  what's up"     (whitespace tolerant)
   Returns { targetNames: [...], body: "..." } where body is the message
   minus the leading mention block. Returns null if no mention found. */
function extractAllMentions(text) {
  if (!text) return null;
  // Match a contiguous block of @names at the start: one or more @name tokens
  // separated by whitespace, then the rest of the message as the body.
  const m = String(text).match(/^\s*((?:@[A-Za-z][A-Za-z0-9_-]*\s+)+)(.+)$/s);
  if (!m) return null;
  const namesBlob = m[1];
  const body = m[2].trim();
  if (!body) return null;
  const targetNames = [];
  const nameRe = /@([A-Za-z][A-Za-z0-9_-]*)/g;
  let nm;
  while ((nm = nameRe.exec(namesBlob)) !== null) {
    const n = nm[1].trim();
    if (n && !targetNames.includes(n.toLowerCase())) targetNames.push(n);
  }
  return targetNames.length ? { targetNames, body } : null;
}

/* ===========================================================================
   Tool registry — a small, marker-based protocol that works on every backend
   (Anthropic, LM Studio, Ollama). Agents emit a single bracketed call on its
   own line and stop. The runner executes the tool, appends the result as a
   user turn ("[TOOL_RESULT: …] …"), and re-streams up to MAX_TOOL_HOPS times.
   =========================================================================== */
const MAX_TOOL_HOPS = 4;

/* Each tool: name, regex (single-line or multi-line block), executor, prompt
   doc lines for the system prompt. The first capture group is the argument;
   the second (optional) is the body for block-style tools. */
let _vaultConfiguredCache = { at: 0, ok: false };
async function isVaultReady() {
  const now = Date.now();
  if (now - _vaultConfiguredCache.at < 5000) return _vaultConfiguredCache.ok;
  try {
    const s = await window.OpenclawClient.vaultStatus();
    _vaultConfiguredCache = { at: now, ok: !!(s.configured && s.exists) };
  } catch (_e) { _vaultConfiguredCache = { at: now, ok: false }; }
  return _vaultConfiguredCache.ok;
}
function clearVaultReadyCache() { _vaultConfiguredCache = { at: 0, ok: false }; }

const TOOL_REGISTRY = {
  search: {
    name: 'SEARCH',
    re: /\[\s*SEARCH\s*:\s*([^\]\n]+)\]/i,
    requires: () => window.OpenclawClient.getSettings().braveEnabled && window.OpenclawClient.getSettings().braveKey,
    doc: '- [SEARCH: <query>] — Brave web search. Use for facts, news, current state. Stop after the line; results will be appended.',
    docShort: 'Web search via Brave. Use for facts, news, current state.',
    run: async (query, { signal }) => {
      const results = await window.OpenclawClient.braveSearch(query.trim(), { count: 6, signal });
      if (!results.length) return 'No results.';
      return results.map((r, i) =>
        `${i+1}. ${r.title}\n   ${r.url}\n   ${r.description}`
      ).join('\n');
    },
  },
  vault_search: {
    name: 'VAULT_SEARCH',
    re: /\[\s*VAULT_SEARCH\s*:\s*([^\]\n]+)\]/i,
    requires: isVaultReady,
    doc: '- [VAULT_SEARCH: <query>] — search the boss\'s Obsidian vault for notes mentioning the query. Returns top matches with snippets.',
    docShort: 'Search the Obsidian vault for notes matching a query. Returns paths and snippets.',
    run: async (query) => {
      const hits = await window.OpenclawClient.vaultSearch(query.trim(), { limit: 8 });
      if (!hits.length) return 'No matches in vault.';
      return hits.map(h => `• ${h.path}\n  ${h.snippet}`).join('\n\n');
    },
  },
  vault_read: {
    name: 'VAULT_READ',
    re: /\[\s*VAULT_READ\s*:\s*([^\]\n]+)\]/i,
    requires: isVaultReady,
    doc: '- [VAULT_READ: <path>] — read full contents of a vault note (e.g. "Daily/2026-04-25.md"). Use after VAULT_SEARCH narrows the right file.',
    docShort: 'Read the full contents of a vault note by path. Use after VAULT_SEARCH.',
    run: async (path) => {
      const text = await window.OpenclawClient.vaultRead(path.trim());
      // Cap to keep context costs sane.
      return text.length > 4000 ? text.slice(0, 4000) + '\n\n…(truncated)' : text;
    },
  },
  vault_append: {
    name: 'VAULT_APPEND',
    /* Multiline block: [VAULT_APPEND: path]\n<body>\n[/VAULT_APPEND] */
    re: /\[\s*VAULT_APPEND\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*VAULT_APPEND\s*\]/i,
    requires: isVaultReady,
    doc: '- [VAULT_APPEND: <path>]\n<content>\n[/VAULT_APPEND] — append content to an existing note (creates if missing). Body can be multi-line markdown.',
    docShort: 'Append multi-line markdown content to an existing vault note (creates if missing).',
    run: async (path, _ctx, body) => {
      const r = await window.OpenclawClient.vaultWrite(path.trim(), body || '', 'append');
      return `Appended ${(body||'').length} chars → ${r.path} (now ${r.size} bytes)`;
    },
  },
  vault_new: {
    name: 'VAULT_NEW',
    re: /\[\s*VAULT_NEW\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*VAULT_NEW\s*\]/i,
    requires: isVaultReady,
    doc: '- [VAULT_NEW: <path>]\n<content>\n[/VAULT_NEW] — create a new note (overwrites if exists). Use for new findings, summaries, drafts.',
    docShort: 'Create or overwrite a vault note at the given path with provided content.',
    run: async (path, _ctx, body) => {
      const r = await window.OpenclawClient.vaultWrite(path.trim(), body || '', 'write');
      return `Wrote ${(body||'').length} chars → ${r.path}`;
    },
  },
  /* File / shell tools — only enabled for elevated agents regardless of LLM
     provider. Execution is handled by serve.py /tools/exec, which validates
     paths against OPENCLAW_ALLOWED_DIRS server-side. */
  file_read: {
    name: 'FILE_READ',
    re: /\[\s*FILE_READ\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [FILE_READ: <path>] — read a local file. Path must be within the configured allowed directories.',
    docShort: 'Read a local file by absolute path within the allowed directories.',
    run: async (path, { signal, cwd }) => window.OpenclawClient.toolExec('FILE_READ', path.trim(), { signal, cwd }),
  },
  dir_list: {
    name: 'DIR_LIST',
    re: /\[\s*DIR_LIST\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [DIR_LIST: <path>] — list files and subdirectories at a path. Use to explore project structure before reading files.',
    docShort: 'List files and subdirectories at a path. Use to explore structure before reading.',
    run: async (path, { signal, cwd }) => window.OpenclawClient.toolExec('DIR_LIST', path.trim(), { signal, cwd }),
  },
  file_write: {
    name: 'FILE_WRITE',
    re: /\[\s*FILE_WRITE\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*FILE_WRITE\s*\]/i,
    requires: () => true,
    doc: '- [FILE_WRITE: <path>]\n<content>\n[/FILE_WRITE] — write (create or overwrite) a local file. Path must be within allowed directories.',
    docShort: 'Write (create or overwrite) a local file; body goes in the "body" field.',
    run: async (path, { cwd }, body) => window.OpenclawClient.toolExec('FILE_WRITE', path.trim(), { body: body || '', cwd }),
  },
  bash: {
    name: 'BASH',
    re: /\[\s*BASH\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [BASH: <command>] — run a shell command on the proxy machine (cwd = project dir or first allowed dir). Requires Bash in OPENCLAW_ALLOWED_TOOLS.',
    docShort: 'Run a shell command on the proxy machine. Requires Bash in OPENCLAW_ALLOWED_TOOLS.',
    run: async (cmd, { signal, cwd }) => window.OpenclawClient.toolExec('BASH', cmd.trim(), { signal, cwd }),
  },
  /* Per-agent memory — each agent gets a private vault folder at
     `Agents/<Name>/`. Provides persistent notes that survive across
     sessions (the in-memory `journal` only keeps 30 entries). The
     agent's prompt header auto-lists their existing memory files so
     they don't need to call MEMORY_LIST first.
     Path argument is RELATIVE to the agent's folder — we sandbox
     server-side by prepending `Agents/<Name>/`. */
  memory_list: {
    name: 'MEMORY_LIST',
    re: /\[\s*MEMORY_LIST\s*\]/i,
    requires: isVaultReady,
    doc: '- [MEMORY_LIST] — list every note in your private memory folder (Agents/<your name>/). Use to see what you\'ve saved before.',
    docShort: 'List every note in your private memory folder.',
    run: async () => 'MEMORY_LIST is bound at agent-build time — see toolsForAgent.',
  },
  memory_read: {
    name: 'MEMORY_READ',
    re: /\[\s*MEMORY_READ\s*:\s*([^\]\n]+)\]/i,
    requires: isVaultReady,
    doc: '- [MEMORY_READ: <relative-path>] — read a note from your private memory folder. Path is RELATIVE — e.g. "decisions/auth.md" reads Agents/<you>/decisions/auth.md.',
    docShort: 'Read a note from your memory by relative path (e.g. "notes/foo.md").',
    run: async () => 'MEMORY_READ is bound at agent-build time — see toolsForAgent.',
  },
  memory_write: {
    name: 'MEMORY_WRITE',
    re: /\[\s*MEMORY_WRITE\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*MEMORY_WRITE\s*\]/i,
    requires: isVaultReady,
    doc: '- [MEMORY_WRITE: <relative-path>]\n<content>\n[/MEMORY_WRITE] — create or overwrite a note in your memory. Use markdown freely. Examples of good memory: "decisions/<topic>.md", "preferences.md", "people/<name>.md", "projects/<slug>.md".',
    docShort: 'Create or overwrite a note in your memory (markdown body).',
    run: async () => 'MEMORY_WRITE is bound at agent-build time — see toolsForAgent.',
  },
  memory_append: {
    name: 'MEMORY_APPEND',
    re: /\[\s*MEMORY_APPEND\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*MEMORY_APPEND\s*\]/i,
    requires: isVaultReady,
    doc: '- [MEMORY_APPEND: <relative-path>]\n<content>\n[/MEMORY_APPEND] — append to an existing memory note (creates if missing). Use for log-style entries (journal, decisions log).',
    docShort: 'Append content to an existing memory note (creates if missing).',
    run: async () => 'MEMORY_APPEND is bound at agent-build time — see toolsForAgent.',
  },
  /* Browser tools — fetch + screenshot via the serve.py /browser/* shim.
     FETCH always works (urllib + readable-text extraction). SCREENSHOT
     drives a Brave/Chrome instance via Chrome DevTools Protocol; the
     user must launch the browser with --remote-debugging-port=9222. We
     fail gracefully with the install hint when CDP isn't reachable. */
  browser_fetch: {
    name: 'BROWSER_FETCH',
    re: /\[\s*BROWSER_FETCH\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [BROWSER_FETCH: <url>] — fetch a URL and return its readable text content (HTML stripped, scripts/styles removed). For static pages, news, docs.',
    docShort: 'Fetch a URL and return readable text. Works for static pages, news, docs.',
    run: async (url, { signal }) => {
      const u = `/browser/fetch?url=${encodeURIComponent(url.trim())}&max_chars=8000`;
      const r = await fetch(u, { signal });
      const j = await r.json();
      if (j.error) return `Browser fetch error: ${j.error}`;
      const head = `URL: ${j.url}\nStatus: ${j.status}\nTitle: ${j.title || '(none)'}\n${'─'.repeat(40)}\n`;
      return head + (j.text || '(no body)');
    },
  },
  browser_screenshot: {
    name: 'BROWSER_SCREENSHOT',
    re: /\[\s*BROWSER_SCREENSHOT\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [BROWSER_SCREENSHOT: <url>] — capture a PNG screenshot of a URL via the user\'s Chromium browser (must be running with --remote-debugging-port=9222). Returns a markdown image embed.',
    docShort: 'Capture a PNG screenshot of a URL. Requires Brave/Chrome with --remote-debugging-port=9222.',
    run: async (url, { signal }) => {
      const u = `/browser/screenshot?url=${encodeURIComponent(url.trim())}`;
      const r = await fetch(u, { signal });
      const j = await r.json();
      if (j.error) return `Screenshot unavailable: ${j.error}\n${j.hint || ''}`;
      // Embed as markdown — chat renders the data: URL inline
      return `Screenshot of ${j.url} (${j.width}×${j.height}):\n\n![screenshot](${j.png})`;
    },
  },
  /* PEER_JOURNAL — read another agent's last N journal entries so the agent
     can see what their coworker has been working on before deciding to DM
     them or to take the task on themselves. Resolved against the live peers
     list captured in toolsForAgent (see below — the run is rebound there). */
  peer_journal: {
    name: 'PEER_JOURNAL',
    re: /\[\s*PEER_JOURNAL\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [PEER_JOURNAL: <coworker name>] — read your coworker\'s last 5 journal entries to understand what they\'ve been working on. Use BEFORE [DM_TO: name] when you want to brief them with context.',
    docShort: 'Read another agent\'s last 5 journal entries.',
    run: async (_name) => '(no peer roster bound)',
  },
  /* ACK is a lightweight status-update marker — it doesn't run anything,
     it just tells the host (via post-stream extraction) what state to put
     the message in. Multiple ACKs in one reply are fine; the LAST allowed
     state wins for the resulting transition. The block is stripped from
     visible output so the user sees clean text + a state badge in the
     inbox/graph instead of brackets. Use this to keep boss informed
     without spawning a full DM_TO reply. */
  ack: {
    name: 'ACK',
    re: /\[\s*ACK\s*:\s*[a-z_]+\s*(?::\s*[^\]]*)?\]/i,
    requires: () => true,
    doc:
      '- [ACK: <state>: <one-line note>] — post a status update on the message you\'re currently handling, without breaking your reply.\n' +
      '  Allowed states: in_progress, blocked, awaiting_reply, completed.\n' +
      '  Examples:\n' +
      '    [ACK: in_progress: skimming the file now]\n' +
      '    [ACK: blocked: need vault access — please grant]\n' +
      '    [ACK: completed: 3 bullets of summary go here]\n' +
      '  ALWAYS end completed handoffs with a [ACK: completed: …] containing a 3-bullet result + risks + next-action so the boss can move fast.',
    docShort: 'Post a state update on the current message (in_progress / blocked / awaiting_reply / completed).',
    run: async () => '(ACK is captured by the host; this run is a no-op)',
  },
  /* SPAWN_SUBAGENT — create a TRANSIENT sub-agent for a single focused task.
     Host catches this marker, hires a temporary agent (depth-1, no elevation,
     no further spawning), dispatches the task, then auto-dismisses on
     completion. Use this when no current teammate fits the task and a
     specialised one-shot worker is the right tool. The sub-agent's reply is
     delivered back to YOU as a DM. Stop after emitting the block. */
  spawn_subagent: {
    name: 'SPAWN_SUBAGENT',
    re: /\[\s*SPAWN_SUBAGENT\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*SPAWN_SUBAGENT\s*\]/i,
    requires: () => true,
    doc:
      '- [SPAWN_SUBAGENT: <role / specialty>]\n<task description>\n[/SPAWN_SUBAGENT] — spin up a transient one-shot sub-agent for a focused task.\n' +
      '  The role tells the host what kind of agent to create (e.g. "code reviewer", "summarizer", "fact-checker", "JSON wrangler").\n' +
      '  The task is what they should do. Write it like you\'d brief a fresh coworker — clear scope, expected output.\n' +
      '  Sub-agents are sandboxed: NEVER elevated, can\'t fan out further, auto-dismissed when done. Use sparingly (budget caps apply).\n' +
      '  Optional per-spawn model override: `[SPAWN_SUBAGENT: code-reviewer | model:claudecode:sonnet]` — pin a specific model id for this one sub-agent (overrides the global "Sub-agent model" setting). Useful when a particular task warrants a stronger or cheaper model than the spawner uses.',
    docShort: 'Spawn a transient one-shot sub-agent for a focused task.',
    run: async () => '(SPAWN_SUBAGENT is dispatched by the host)',
  },
  /* REQUEST_ELEVATION — assistants and sub-agents are non-elevated by
     default for safety. If they hit a task that genuinely needs shell /
     file access (rare — most work doesn't), they can ask the boss for
     elevation. The marker creates an approval entry; on stamp the agent's
     `elevated` flag flips on and the file/shell tools become available
     to them on their NEXT dispatch (current dispatch already running has
     no way to retroactively grow tools mid-stream). */
  request_elevation: {
    name: 'REQUEST_ELEVATION',
    re: /\[\s*REQUEST_ELEVATION\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*REQUEST_ELEVATION\s*\]/i,
    requires: () => true,
    doc:
      '- [REQUEST_ELEVATION: <one-line reason>]\n<details: which tools you need (file/shell), what specifically you\'ll do with them, why your current toolset isn\'t enough>\n[/REQUEST_ELEVATION] — request elevated capabilities (file/shell access).\n' +
      '  Requires boss APPROVAL. Use ONLY when ordinary tools (vault, web) genuinely cannot complete the task. Most work doesn\'t need this.\n' +
      '  Approval applies to FUTURE dispatches — your current reply ends with whatever non-elevated tools you already have. Tell the boss what you\'d do once approved so they can decide.',
    docShort: 'Ask the boss to grant you elevated (file/shell) access.',
    run: async () => '(REQUEST_ELEVATION is dispatched by the host after boss approval)',
  },
  /* HIRE_ASSISTANT — propose hiring a PERMANENT assistant (secretary or
     apprentice) who reports directly to YOU. Like HIRE_AGENT this needs
     boss approval, but the resulting agent is bound to you in three ways:
     reports_to edge in the graph, dismiss-cascade if you're let go, and
     never gets more privilege than you have. Use this when the same kind
     of routine work keeps landing in your queue and a dedicated subordinate
     would absorb it (vs. spawning a fresh sub-agent each time). Cap: max
     3 active assistants per senior. */
  hire_assistant: {
    name: 'HIRE_ASSISTANT',
    re: /\[\s*HIRE_ASSISTANT\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*HIRE_ASSISTANT\s*\]/i,
    requires: () => true,
    doc:
      '- [HIRE_ASSISTANT: <name> · <role>]\n<rationale: what routine work they\'ll absorb, suggested model/tools>\n[/HIRE_ASSISTANT] — propose hiring a PERMANENT assistant who reports to YOU.\n' +
      '  REQUIRED: name AND role in the marker header (e.g. `[HIRE_ASSISTANT: Quill · Senior Editor]`). Without a name, the request is dropped with a warning.\n' +
      '  If using JSON tool format, include both fields explicitly: `{"tool":"HIRE_ASSISTANT","name":"Quill","role":"Senior Editor","rationale":"..."}`.\n' +
      '  Requires boss APPROVAL. Cap of 2 active assistants per senior. They CAN message peers and spawn one-shot sub-agents, but CANNOT propose further hires of their own (depth=1 hierarchy).\n' +
      '  Difference vs. HIRE_AGENT: assistants are subordinates (you brief them, they report findings to you). HIRE_AGENT proposes a peer for the team.\n' +
      '  Difference vs. SPAWN_SUBAGENT: assistants are permanent and remember your work between turns; sub-agents are one-shot.',
    docShort: 'Propose hiring a permanent assistant/apprentice who reports to YOU (boss approval required).',
    run: async () => '(HIRE_ASSISTANT is dispatched by the host after boss approval)',
  },
  /* HIRE_AGENT — request permission to permanently add a new agent to the
     team. Unlike SPAWN_SUBAGENT, this requires explicit boss approval (it
     persists across sessions and counts toward token costs forever). The
     marker creates an approval entry in the boss's tray; on stamp, the
     agent is hired and you'll get notified. */
  hire_agent: {
    name: 'HIRE_AGENT',
    re: /\[\s*HIRE_AGENT\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*HIRE_AGENT\s*\]/i,
    requires: () => true,
    doc:
      '- [HIRE_AGENT: <name> · <role>]\n<one-paragraph rationale + suggested model/tools>\n[/HIRE_AGENT] — propose hiring a new permanent teammate.\n' +
      '  REQUIRED: name AND role in the marker header. Without a name, the request is dropped with a warning.\n' +
      '  If using JSON tool format, include both: `{"tool":"HIRE_AGENT","name":"Quill","role":"Senior Editor","rationale":"..."}`.\n' +
      '  This requires the boss to APPROVE in their approval tray. Format the body as: rationale (why we need them), suggested model, suggested tools (web/vault/browser).\n' +
      '  Cannot grant elevation — only the boss can promote an agent to elevated status manually.\n' +
      '  Use only when the team is genuinely missing a capability. One outstanding hire request at a time.',
    docShort: 'Propose hiring a new permanent teammate (requires boss approval).',
    run: async () => '(HIRE_AGENT is dispatched by the host after boss approval)',
  },
  /* DM_TO is special — its `run` is a no-op because the DM is dispatched by
     the host app (which knows the agent roster). Keeping it in the registry
     just lets the tool-loop detect and stop on it; the host handles the
     actual hand-off. */
  dm_to: {
    name: 'DM_TO',
    re: /\[\s*DM_TO\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*DM_TO\s*\]/i,
    requires: () => true,
    doc: '- [DM_TO: <coworker name>]\n<message>\n[/DM_TO] — direct-message another sub-agent on the team. Use this when you need their expertise or to hand off a sub-task. Stop after the block; the host will deliver it and continue the chain.',
    docShort: 'Send a direct message to another sub-agent on the team to hand off a task.',
    run: async (_to, _ctx, _body) => {
      // The host catches DM_TO before this runs; this is a sentinel that
      // also handles the case where it slips through (no-op summary).
      return 'Message queued for delivery to coworker.';
    },
  },
};

/* Build the tools section of the agent system prompt, restricted to tools
   the agent has claimed AND that are configured/enabled. Returns a Promise
   since some `requires` checks (vault status) are async. */
async function toolsForAgent(agent, { peers = [] } = {}) {
  const claimed = new Set(agent.tools || []);
  const out = [];
  if (claimed.has('web') && TOOL_REGISTRY.search.requires())
    out.push(TOOL_REGISTRY.search);
  if (claimed.has('vault')) {
    const ready = await TOOL_REGISTRY.vault_search.requires();
    if (ready) {
      out.push(TOOL_REGISTRY.vault_search, TOOL_REGISTRY.vault_read,
               TOOL_REGISTRY.vault_append, TOOL_REGISTRY.vault_new);
    }
  }
  // File/shell tools for elevated agents — available regardless of LLM provider.
  if (agent.elevated) {
    out.push(TOOL_REGISTRY.file_read, TOOL_REGISTRY.dir_list, TOOL_REGISTRY.file_write, TOOL_REGISTRY.bash);
  }
  // Browser tools — available to any agent that opted into 'web' OR is
  // elevated. FETCH works everywhere (urllib); SCREENSHOT requires Brave/
  // Chrome to be running with --remote-debugging-port=9222 (we surface
  // the hint if it isn't).
  if (agent.elevated || claimed.has('web') || claimed.has('browser')) {
    out.push(TOOL_REGISTRY.browser_fetch, TOOL_REGISTRY.browser_screenshot);
  }

  // Per-agent memory — every agent gets a private vault folder regardless
  // of capability flags. Folder root is `Agents/<safe-name>/`. Bind run()
  // to the live agent so paths are scoped server-side and the agent
  // can't read another agent's notes by accident.
  const memReady = await TOOL_REGISTRY.memory_list.requires();
  if (memReady) {
    const safeName = String(agent.name || 'agent').replace(/[^A-Za-z0-9_-]+/g, '_');
    const root = `Agents/${safeName}`;
    const scope = (rel) => {
      const p = String(rel || '').replace(/^[./\\]+/, '').replace(/\\/g, '/');
      // Refuse path-traversal attempts.
      if (p.includes('..')) throw new Error('Path traversal not allowed in memory paths.');
      return root + '/' + p;
    };
    out.push({
      ...TOOL_REGISTRY.memory_list,
      run: async () => {
        const all = await window.OpenclawClient.vaultList();
        const mine = (all || []).filter(p => p.startsWith(root + '/'));
        if (!mine.length) return `(your memory is empty — write your first note with [MEMORY_WRITE: notes/foo.md]…[/MEMORY_WRITE])`;
        return mine.map(p => '• ' + p.slice(root.length + 1)).join('\n');
      },
    });
    out.push({
      ...TOOL_REGISTRY.memory_read,
      run: async (rel) => {
        try {
          const text = await window.OpenclawClient.vaultRead(scope(rel));
          return text.length > 4000 ? text.slice(0, 4000) + '\n\n…(truncated)' : text;
        } catch (e) {
          if (String(e.message || '').includes('404') || String(e.message || '').toLowerCase().includes('not found')) {
            return `(no memory at "${rel}" — use [MEMORY_LIST] to see what you've saved)`;
          }
          throw e;
        }
      },
    });
    out.push({
      ...TOOL_REGISTRY.memory_write,
      run: async (rel, _ctx, body) => {
        const target = scope(rel);
        const r = await window.OpenclawClient.vaultWrite(target, body || '', 'write');
        return `Wrote ${(body||'').length} chars → ${r.path}`;
      },
    });
    out.push({
      ...TOOL_REGISTRY.memory_append,
      run: async (rel, _ctx, body) => {
        const target = scope(rel);
        const stamped = `\n\n## ${new Date().toISOString().slice(0, 19).replace('T', ' ')}\n${body || ''}\n`;
        const r = await window.OpenclawClient.vaultWrite(target, stamped, 'append');
        return `Appended ${(body||'').length} chars → ${r.path} (now ${r.size} bytes)`;
      },
    });
  }
  // ACK is always available — every agent should be able to status-update
  // the message they're currently handling. No peer roster needed; this is
  // a self-status marker, not an outgoing send.
  out.push(TOOL_REGISTRY.ack);
  // SPAWN_SUBAGENT is always available to non-transient agents (including
  // assistants — they can spawn one-shots when they need them).
  // HIRE_AGENT and HIRE_ASSISTANT are restricted to senior agents only —
  // assistants cannot propose further hires (depth=1 hierarchy cap).
  // REQUEST_ELEVATION is available to ANY non-elevated agent (assistants,
  // sub-agents, even regular peers) so they can ask for shell/file access
  // when their task genuinely needs it. Boss decides via approval tray.
  // All four are dispatched host-side so their `run` is a no-op like dm_to.
  if (!agent.transient) {
    out.push(TOOL_REGISTRY.spawn_subagent);
    if (!agent.assistant) {
      out.push(TOOL_REGISTRY.hire_agent);
      out.push(TOOL_REGISTRY.hire_assistant);
    }
  }
  if (!agent.elevated) {
    out.push(TOOL_REGISTRY.request_elevation);
  }
  // DM_TO is always available when there's at least one coworker to talk to.
  // The roster is appended to the doc so the model knows valid recipients.
  if (peers && peers.length) {
    const namesLine = '  Coworkers you can DM: ' + peers.map(p => `${p.name} (${p.role})`).join(', ');
    out.push({ ...TOOL_REGISTRY.dm_to, doc: TOOL_REGISTRY.dm_to.doc + '\n' + namesLine });

    // Bind peer_journal to the live peers so it can return real entries.
    out.push({
      ...TOOL_REGISTRY.peer_journal,
      doc: TOOL_REGISTRY.peer_journal.doc + '\n' + namesLine,
      run: async (name) => {
        const target = peers.find(p => (p.name || '').toLowerCase() === String(name || '').trim().toLowerCase());
        if (!target) return `No coworker named "${name}".`;
        const entries = (target.journal || []).slice(0, 5);
        if (!entries.length) return `${target.name} has no journal entries yet.`;
        return entries.map((e, i) => {
          const when = e.at ? new Date(e.at).toLocaleString() : '(no time)';
          const title = e.title || '';
          const text = (e.summary || e.text || '').slice(0, 400);
          return `${i + 1}. ${when}${title ? ' — ' + title : ''}\n   ${text}`;
        }).join('\n\n');
      },
    });
  }
  return out;
}

function toolsPromptSnippet(tools) {
  if (!tools.length) return '';
  return [
    'TOOL CALLS — you have these real tools available. To invoke one, output the bracketed call on its own line and STOP. The boss will execute it and append the result; then you continue.',
    ...tools.map(t => t.doc),
    'Rules: only one tool call per turn; only invoke tools listed above; if a question needs no tool, just answer.',
  ].join('\n');
}

function toolsPromptSnippetJson(tools) {
  if (!tools.length) return '';
  return [
    'TOOL CALLS — use this exact JSON format to invoke a tool:',
    '<<<TOOL>>>',
    '{"tool": "<NAME>", "arg": "<argument>", "body": "<optional multi-line body>"}',
    '<<<END_TOOL>>>',
    'Available tools:',
    ...tools.map(t => `  ${t.name}: ${t.docShort || t.doc.replace(/^- /, '').split('\n')[0]}`),
    'Rules: emit exactly one <<<TOOL>>>…<<<END_TOOL>>> block per turn, on its own lines, then stop and wait for the result.',
  ].join('\n');
}

/* Find a JSON-format tool call emitted by capable models.
   Format: <<<TOOL>>>\n{…}\n<<<END_TOOL>>>
   Returns {tool, arg, body, raw} or null. */
function detectJsonToolCall(text, tools) {
  const m = text.match(/<<<TOOL>>>\s*\n(\{[\s\S]*?\})\s*\n<<<END_TOOL>>>/);
  if (!m) return null;
  try {
    const parsed = JSON.parse(m[1]);
    const toolName = String(parsed.tool || '').toUpperCase();
    const tool = tools.find(t => t.name === toolName);
    if (!tool) return null;
    // Per-tool field aliasing: some tools (HIRE_*, SPAWN_*, DM_TO) have
    // semantic fields that aren't called `arg`/`body`. We accept several
    // common field names so models can pick whatever feels natural in JSON
    // (`name`, `to`, `recipient`, `rationale`, `task`, etc.) without the
    // host silently dropping the request when the keys don't match.
    const get = (...keys) => {
      for (const k of keys) {
        if (parsed[k] != null && String(parsed[k]).trim()) return String(parsed[k]);
      }
      return '';
    };
    let arg, body;
    switch (toolName) {
      case 'DM_TO':
        arg  = get('arg', 'to', 'name', 'agent', 'recipient');
        body = get('body', 'message', 'text', 'content');
        break;
      case 'SPAWN_SUBAGENT':
        arg  = get('arg', 'role', 'specialty', 'kind');
        body = get('body', 'task', 'description', 'brief', 'message');
        break;
      case 'HIRE_AGENT':
      case 'HIRE_ASSISTANT': {
        // Compose "Name · Role" from whatever fields the model used.
        const name = get('name', 'agent_name', 'agentName', 'title');
        const role = get('role', 'title', 'specialty', 'position');
        if (name && role) arg = name + ' · ' + role;
        else if (name) arg = name;
        else arg = get('arg', 'nameAndRole', 'name_and_role') || '';
        body = get('body', 'rationale', 'reason', 'details', 'message');
        break;
      }
      case 'ACK':
        // ACK shouldn't actually reach here (it's filtered from detector),
        // but be defensive: support both nested and flat forms.
        arg  = get('arg', 'state', 'status');
        body = get('body', 'note', 'message');
        break;
      case 'REQUEST_ELEVATION':
        arg  = get('arg', 'reason', 'why', 'summary');
        body = get('body', 'details', 'rationale', 'message');
        break;
      default:
        arg  = String(parsed.arg || '');
        body = String(parsed.body || '');
    }
    return { tool, arg, body, raw: m[0] };
  } catch (_e) { return null; }
}

/* Find the first tool call in `text`. Returns {tool, arg, body, raw} or null.
   Tries JSON format first (capable models), then bracket regex, then harmony. */
function detectToolCall(text, tools) {
  const jsonCall = detectJsonToolCall(text, tools);
  if (jsonCall) return jsonCall;
  for (const t of tools) {
    const m = String(text).match(t.re);
    if (m) return { tool: t, arg: m[1], body: m[2] || '', raw: m[0] };
  }
  // Fall back to harmony format: gpt-oss-20b, qwen-3, and other OSS models
  // emit tool calls as <|channel|>commentary to=NAME<|message|>{…json…}
  // We map the harmony name to one of our registered tools and extract
  // the arg from common JSON keys.
  const h = extractHarmonyToolCalls(text);
  if (h.length) {
    for (const call of h) {
      const tool = tools.find(t => t.name === call.tool);
      if (!tool) continue;
      const { arg, body } = harmonyArgsFor(tool, call.payload);
      if (arg) return { tool, arg, body: body || '', raw: call.raw };
    }
  }
  return null;
}

/* Returns true if the given model is likely capable of the JSON tool call
   format (<<<TOOL>>>…<<<END_TOOL>>>). Anthropic, Google, and select local
   models get JSON; everything else falls back to bracket format. */
function supportsJsonToolFormat(model) {
  if (!model) return false;
  const { provider } = window.OpenclawClient.parseModelId(model);
  if (['anthropic', 'openclaw', 'claudecode', 'codex', 'google'].includes(provider)) return true;
  const capableLocal = ['qwen3', 'mistral-nemo', 'llama-3.3', 'deepseek'];
  return capableLocal.some(n => (model || '').toLowerCase().includes(n));
}

/* Strip harmony channel/message/end tags from a block of text, keeping only
   the "final" channel content (what the user is meant to see). Non-harmony
   text passes through unchanged. */
function cleanHarmony(text) {
  if (!text || text.indexOf('<|') < 0) return text;
  let out = String(text);
  // Remove analysis + commentary blocks entirely (CoT + tool calls aren't
  // for the user). Match up to the next channel/end/call/return marker.
  out = out.replace(
    /<\|channel\|>\s*(?:analysis|commentary)\b[\s\S]*?(?=<\|channel\||<\|end\|>|<\|call\|>|<\|return\|>|$)/g,
    ''
  );
  // Strip any remaining harmony framing tags.
  out = out.replace(/<\|channel\|>\s*final\b\s*(?:to=[^\s<]+\s*)?(?:<\|constrain\|>\w+\s*)?<\|message\|>/g, '');
  out = out.replace(/<\|(?:end|call|return|start|message|constrain)\|>/g, '');
  out = out.replace(/<\|[^|]*\|>/g, '');  // belt-and-suspenders: any leftover
  return out.trim();
}

/* Extract harmony commentary tool calls from a buffered response. Returns
   [{tool, payload, raw}] in order of appearance. */
function extractHarmonyToolCalls(text) {
  if (!text || text.indexOf('<|channel|>commentary') < 0) return [];
  const out = [];
  const re = /<\|channel\|>\s*commentary\s+to=([A-Za-z0-9_.]+)\s*(?:<\|constrain\|>\w+\s*)?<\|message\|>([\s\S]*?)(?=<\|channel\||<\|end\|>|<\|call\|>|<\|return\|>|$)/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    let name = m[1].replace(/^functions\./, '').toUpperCase();
    out.push({ tool: name, payload: m[2].trim(), raw: m[0] });
  }
  return out;
}

/* Map a harmony JSON payload to the {arg, body} our tool runners expect.
   Different tools take different arg keys; we check JSON first, fall back
   to the raw payload string. */
function harmonyArgsFor(tool, payload) {
  let parsed = null;
  try { parsed = JSON.parse(payload); } catch (_e) {}
  const get = (...keys) => {
    if (!parsed || typeof parsed !== 'object') return null;
    for (const k of keys) if (parsed[k] != null) return String(parsed[k]);
    return null;
  };
  switch (tool.name) {
    case 'SEARCH':         return { arg: get('query', 'q', 'search') || payload };
    case 'VAULT_SEARCH':   return { arg: get('query', 'q') || payload };
    case 'VAULT_READ':     return { arg: get('path', 'file') || payload };
    case 'VAULT_APPEND':
    case 'VAULT_NEW':      return { arg: get('path', 'file') || '', body: get('content', 'body', 'text') || '' };
    case 'DM_TO':          return { arg: get('to', 'name', 'agent', 'recipient') || '', body: get('message', 'body', 'text', 'content') || '' };
    case 'SPAWN_SUBAGENT': return { arg: get('role', 'specialty', 'kind') || '', body: get('task', 'description', 'brief', 'body', 'message') || '' };
    case 'REQUEST_ELEVATION': return { arg: get('reason', 'why', 'summary', 'arg') || '', body: get('details', 'rationale', 'body', 'message') || '' };
    case 'HIRE_AGENT':
    case 'HIRE_ASSISTANT': {
      const name = get('name', 'agent_name', 'agentName', 'title');
      const role = get('role', 'specialty', 'position');
      let arg = '';
      if (name && role) arg = name + ' · ' + role;
      else if (name) arg = name;
      else arg = get('nameAndRole', 'name_and_role') || '';
      return { arg, body: get('rationale', 'reason', 'details', 'body', 'message') || '' };
    }
    default:               return { arg: payload };
  }
}

const CEO_SYSTEM = `You are CafresoAI, the CEO of CafresoAI — a warm, decisive chief of staff running a small team of AI sub-agents. Speak like a trusted right hand: direct, concise, with light personality. Keep replies tight (2-4 sentences). When a task would be better done by a sub-agent, name who you're handing off to (from the HIRED roster) and say so. Never invent sub-agents that aren't on the roster.

APPROVAL PROTOCOL: For any action that sends an email, posts publicly, schedules a commitment, or spends money over $100, do NOT execute. Instead end your reply with a single line in this exact format on its own line:
  [NEEDS_APPROVAL: <one-line description of the action and any cost>]
The boss will stamp it. Once stamped you'll be told to proceed.`;

function chatToMessages(chat, { omitLastCeo = false } = {}) {
  const src = (omitLastCeo && chat.length && chat[chat.length - 1].from === 'ceo')
    ? chat.slice(0, -1) : chat;
  const out = [];
  for (const m of src) {
    if (!m.text || !String(m.text).trim()) continue;
    if (m.from === 'user') out.push({ role: 'user', content: m.text });
    else if (m.from === 'ceo') out.push({ role: 'assistant', content: m.text });
    else out.push({ role: 'user', content: `[${m.name}]: ${m.text}` });
  }
  return out;
}

function rosterSummary(agents) {
  if (!agents || !agents.length) return 'No sub-agents hired yet.';
  return 'Hired sub-agents:\n' + agents.map(a =>
    `- ${a.name} (${a.role}) — status: ${a.status}, tools: ${(a.tools||[]).join(', ') || 'none'}`
  ).join('\n');
}

function memorySummary(memory) {
  if (!memory || !memory.length) return '';
  return 'Long-term memory (notes CafresoAI has saved about the boss & ongoing work):\n' +
    memory.slice(0, 24).map(m => `  [${m.tag}] ${m.text}`).join('\n');
}

/* Most recent N journal entries surfaced to the agent so they can build on
   past work instead of starting cold every run. Cheap continuity. */
function journalSummary(agent) {
  const j = (agent && agent.journal) || [];
  if (!j.length) return '';
  /* Tight journal: 3 most recent × 120 chars each. More than that and small
     models start anchoring on prior tasks instead of focusing on the
     current request. The Inspect panel still shows the full journal. */
  const recent = j.slice(0, 3);
  const lines = ['Your recent work log (for memory only — do NOT re-litigate past tasks):'];
  for (const e of recent) {
    const when = e.date || (e.at ? new Date(e.at).toISOString().slice(0, 10) : '');
    lines.push(`  [${when}] ${(e.summary || '').slice(0, 120)}`);
  }
  return lines.join('\n');
}

function buildCeoSystem(agents, extra) {
  const parts = [CEO_SYSTEM, rosterSummary(agents)];
  const mem = memorySummary(window.MOCK && window.MOCK._memory);
  if (mem) parts.push(mem);
  if (extra) parts.push(extra);
  return parts.join('\n\n');
}

/* Cache the registry snippet for a short window — sub-agents in a meeting all
   stream within seconds of each other, so refetching per call is wasteful.
   Invalidated whenever settings change (provider/URL swaps, etc.). */
const REGISTRY_TTL_MS = 10_000;
let _registryCache = { at: 0, value: '', inflight: null };
if (window.OpenclawClient && window.OpenclawClient.onSettingsChange) {
  window.OpenclawClient.onSettingsChange(() => {
    _registryCache = { at: 0, value: '', inflight: null };
  });
}
async function registrySnippet() {
  const now = Date.now();
  if (now - _registryCache.at < REGISTRY_TTL_MS) return _registryCache.value;
  if (_registryCache.inflight) return _registryCache.inflight;
  _registryCache.inflight = (async () => {
    try {
      const reg = await window.OpenclawClient.localRegistry();
      const value = window.OpenclawClient.formatRegistry(reg);
      _registryCache = { at: Date.now(), value, inflight: null };
      return value;
    } catch (_e) {
      _registryCache.inflight = null;
      return '';
    }
  })();
  return _registryCache.inflight;
}

async function ceoStream(prompt, onToken, { chat, agents, system, model, temperature, signal, onUsage, onTool, onHint, maxTokens } = {}) {
  const messages = chat
    ? chatToMessages(chat, { omitLastCeo: true })
    : [{ role: 'user', content: prompt }];
  const reg = await registrySnippet();
  // CEO has implicit web + vault — those are top-of-house concerns.
  const ceoTools = [];
  if (TOOL_REGISTRY.search.requires()) ceoTools.push(TOOL_REGISTRY.search);
  if (await TOOL_REGISTRY.vault_search.requires()) {
    ceoTools.push(TOOL_REGISTRY.vault_search, TOOL_REGISTRY.vault_read,
                  TOOL_REGISTRY.vault_append, TOOL_REGISTRY.vault_new);
  }
  const useJsonCeo = supportsJsonToolFormat(model);
  const ceoToolSnippet = ceoTools.length ? (useJsonCeo ? toolsPromptSnippetJson(ceoTools) : toolsPromptSnippet(ceoTools)) : '';
  const sys = system || (buildCeoSystem(agents || [], reg) + (ceoToolSnippet ? '\n\n' + ceoToolSnippet : ''));

  for (let hop = 0; hop < MAX_TOOL_HOPS; hop++) {
    let buf = '';
    await window.OpenclawClient.stream({
      system: sys,
      messages,
      model: resolveModel(model),
      temperature,
      onToken: tok => { buf += tok; onToken(tok); },
      onUsage,
      signal,
      maxTokens,
    });
    const call = ceoTools.length ? detectToolCall(buf, ceoTools) : null;
    if (!call) {
      const cleaned = cleanHarmony(buf);
      const emit = (msg) => { if (onHint) onHint(msg); else onToken(msg); };
      if (!cleaned.trim()) {
        const orphans = extractHarmonyToolCalls(buf);
        if (orphans.length) {
          emit(`_(model attempted ${orphans.map(o=>o.tool).join(', ')} but those aren't wired up — check Settings → API)_`);
        } else {
          const peek = buf.slice(0, 240).replace(/\n+/g,' ').trim();
          emit(peek ? `_(empty after cleaning. Raw: "${peek}…")_` : '_(empty response from CEO model)_');
        }
      }
      return;
    }

    if (onTool) onTool({ phase: 'start', name: call.tool.name, arg: call.arg });
    let result;
    try { result = await call.tool.run(call.arg, { signal }, call.body); }
    catch (err) { result = `Error: ${err.message}`; }
    if (onTool) onTool({ phase: 'done', name: call.tool.name, arg: call.arg, result });

    const banner = `\n\n📡 ${call.tool.name}("${call.arg.trim().slice(0, 60)}") →\n${result}\n\n`;
    onToken(banner);

    messages.push({ role: 'assistant', content: buf });
    messages.push({ role: 'user', content: `[TOOL_RESULT: ${call.tool.name}]\n${result}\n\nContinue from where you stopped. Do NOT repeat the tool call.` });
  }
  if (onHint) onHint(`_(per-turn tool budget exhausted (${MAX_TOOL_HOPS} hops); ask again to continue)_`);
}

async function agentStream(agent, prompt, onToken, { chat, signal, onUsage, onTool, onHint, maxTokens, peers = [], maxToolHops = MAX_TOOL_HOPS, cwd } = {}) {
  const reg = await registrySnippet();
  const claimedRaw = (agent.tools || []).join(', ') || 'none';
  const enabledTools = await toolsForAgent(agent, { peers });
  const enabledNames = enabledTools.map(t => t.name).join(', ') || 'none';

  const base = agent.systemPrompt || `You are ${agent.name}, a sub-agent at CafresoAI. Role: ${agent.role}. Be concise (2-4 sentences), report progress honestly, and flag anything that needs the CEO's decision.`;
  const toolsNote = enabledTools.length
    ? `\n\nClaimed capabilities: ${claimedRaw}. Of these, the following are wired up for real execution: ${enabledNames}. ONLY invoke these exact tools using the bracketed format described in the TOOL CALLS section. Do NOT invent functions, do NOT use OpenAI/harmony \`commentary to=\` syntax, do NOT call any tool not in this list. If a request needs a tool you don't have, say so plainly in plain text and suggest the user @-mention a coworker who does.`
    : (agent.elevated
      ? ''
      : `\n\nClaimed capabilities: ${claimedRaw}. NONE are wired up for real execution this session. Do NOT emit tool calls of any form (no bracketed markers, no harmony commentary, no JSON function calls). If a request needs a tool, say so plainly in plain text. You may discuss your capabilities conceptually but cannot actually invoke them.`);
  const elevatedNote = agent.elevated
    ? `\n\nELEVATED SESSION: You have native computer access through Claude Code on the proxy machine. Use your built-in agentic capabilities to work with files and run commands directly — do not claim you lack access.`
    : '';
  const journalNote = journalSummary(agent);
  const mem = memorySummary(window.MOCK && window.MOCK._memory);
  /* Per-agent persistent memory listing — head-of-prompt so the agent
     knows what's in their private notes folder before they start. We
     fetch the actual file list from the vault (best effort; non-fatal
     if vault isn't configured). Limited to 12 entries to keep prompt
     size reasonable. */
  let agentMemoryNote = '';
  try {
    const safeName = String(agent.name || 'agent').replace(/[^A-Za-z0-9_-]+/g, '_');
    const root = `Agents/${safeName}/`;
    const all = await window.OpenclawClient.vaultList();
    const mine = (all || []).filter(p => p.startsWith(root)).map(p => p.slice(root.length));
    if (mine.length) {
      const shown = mine.slice(0, 12).map(p => '• ' + p).join('\n');
      const more = mine.length > 12 ? `\n…and ${mine.length - 12} more (use [MEMORY_LIST] to see all)` : '';
      agentMemoryNote =
        `YOUR MEMORY (private notes folder Agents/${safeName}/) — ${mine.length} note${mine.length === 1 ? '' : 's'}:\n${shown}${more}\n\n` +
        `Read with [MEMORY_READ: <path>], save with [MEMORY_WRITE: <path>]…[/MEMORY_WRITE], append with [MEMORY_APPEND: <path>]…[/MEMORY_APPEND]. ` +
        `Use this for things you'll need across sessions: decisions, preferences, references, working drafts. The in-context journal only holds your last 30 entries.`;
    } else {
      agentMemoryNote =
        `YOUR MEMORY (private notes folder Agents/${safeName}/) — empty.\n` +
        `Save the first note with [MEMORY_WRITE: <path>]…[/MEMORY_WRITE]. Suggested layout: decisions/<topic>.md, references/<thing>.md, preferences.md, projects/<slug>.md. Persists across sessions.`;
    }
  } catch (_e) { /* vault not configured — skip the memory note */ }
  const useJson = agent.toolFormat === 'json' || (agent.toolFormat !== 'bracket' && supportsJsonToolFormat(agent.model));
  const toolSnippet = enabledTools.length ? (useJson ? toolsPromptSnippetJson(enabledTools) : toolsPromptSnippet(enabledTools)) : '';
  const sys = [base + toolsNote + elevatedNote, toolSnippet, agentMemoryNote, journalNote, mem, reg].filter(Boolean).join('\n\n');

  const messages = chat
    ? chatToMessages(chat).concat([{ role: 'user', content: prompt }])
    : [{ role: 'user', content: prompt }];

  let toolsExecuted = 0;
  for (let hop = 0; hop < maxToolHops; hop++) {
    let buf = '';
    await window.OpenclawClient.stream({
      system: sys,
      messages,
      model: resolveModel(agent.model),
      temperature: typeof agent.temperature === 'number' ? agent.temperature : 0.5,
      onToken: tok => { buf += tok; onToken(tok); },
      onUsage,
      signal,
      maxTokens,
      // Forwarded only by the openclaw provider — others ignore it.
      agentName: agent.name,
      elevated: !!agent.elevated,
      cwd,
    });
    // ACK markers are status-update only — they should NOT halt the stream
    // for a tool round-trip. The host extracts them from `buf` after the
    // stream completes and routes to MessageRegistry.transition().
    const detectable = enabledTools.filter(t => t.name !== 'ACK');
    const call = detectable.length ? detectToolCall(buf, detectable) : null;
    if (!call) {
      /* No matching tool fired. Surface a useful hint based on what the
         model actually produced so the chat doesn't look frozen. Routed
         through onHint (out-of-band) so cleanHarmony can't eat it when a
         dangling commentary block runs to end-of-buffer. */
      const cleaned = cleanHarmony(buf);
      const emit = (msg) => { if (onHint) onHint(msg); else onToken(msg); };
      if (!cleaned.trim()) {
        const orphans = extractHarmonyToolCalls(buf);
        const enabledSet = new Set(enabledTools.map(t => t.name));
        const missing = [...new Set(orphans.map(o => o.tool).filter(n => !enabledSet.has(n)))];
        if (toolsExecuted > 0) {
          const peek = (orphans[0] && orphans[0].payload || buf).slice(0, 200).replace(/\n+/g,' ').trim();
          emit(`_(tool results came back but ${agent.name}'s model didn't write a final answer. Last attempt: "${peek}…". Try a stronger model — sonnet/opus or claudecode:sonnet — for the synthesis step, or lower temperature.)_`);
        } else if (missing.length) {
          emit(`_(${agent.name} tried to call ${missing.join(', ')} but doesn't have that capability. Edit their tools in Settings, or @-mention a coworker who does.)_`);
        } else if (orphans.length) {
          emit('_(model produced only commentary — try a different model or raise max_tokens)_');
        } else {
          const peek = buf.slice(0, 240).replace(/\n+/g,' ').trim();
          emit(peek
            ? `_(empty after cleaning. Raw: "${peek}…")_`
            : '_(no output from model — check the backend is reachable and not rate-limited)_');
        }
      }
      return;
    }
    // DM_TO is dispatched by the host (it knows the live agent state). An
    // agent can address several coworkers in one reply, so we surface
    // EVERY DM block, not just the first one detectToolCall matched. The
    // host queues them all and dispatches each.
    if (call.tool.name === 'DM_TO') {
      const dms = extractAllDMs(buf);
      const list = dms.length ? dms : [{ to: call.arg, body: call.body }];
      if (onTool) {
        for (const dm of list) onTool({ phase: 'dm', name: 'DM_TO', arg: dm.to, body: dm.body });
      }
      return;
    }
    // SPAWN_SUBAGENT — host-dispatched. We surface ONE event per matched
    // marker (only the first one in this turn — multiple in one reply is
    // intentional spam-prevention; if the agent really needs N sub-agents
    // they should chain them across turns).
    if (call.tool.name === 'SPAWN_SUBAGENT') {
      if (onTool) onTool({ phase: 'spawn-subagent', name: 'SPAWN_SUBAGENT',
                            arg: call.arg, body: call.body });
      return;
    }
    // HIRE_AGENT — host-dispatched, requires boss approval. arg = "name · role"
    if (call.tool.name === 'HIRE_AGENT') {
      if (onTool) onTool({ phase: 'hire-agent', name: 'HIRE_AGENT',
                            arg: call.arg, body: call.body });
      return;
    }
    // HIRE_ASSISTANT — host-dispatched, requires boss approval, becomes
    // subordinate of the spawning agent (reports_to in graph, dismiss-cascade).
    if (call.tool.name === 'HIRE_ASSISTANT') {
      if (onTool) onTool({ phase: 'hire-assistant', name: 'HIRE_ASSISTANT',
                            arg: call.arg, body: call.body });
      return;
    }
    // REQUEST_ELEVATION — host-dispatched, requires boss approval; on
    // approve sets agent.elevated=true for FUTURE dispatches.
    if (call.tool.name === 'REQUEST_ELEVATION') {
      if (onTool) onTool({ phase: 'request-elevation', name: 'REQUEST_ELEVATION',
                            arg: call.arg, body: call.body });
      return;
    }

    if (onTool) onTool({ phase: 'start', name: call.tool.name, arg: call.arg });
    let result;
    try {
      result = await call.tool.run(call.arg, { signal, cwd }, call.body);
    } catch (err) {
      result = `Error: ${err.message}`;
    }
    toolsExecuted++;
    if (onTool) onTool({ phase: 'done', name: call.tool.name, arg: call.arg, result });

    // Stream the result inline so the user sees what the agent is reading.
    const banner = `\n\n📡 ${call.tool.name}("${call.arg.trim().slice(0, 60)}") →\n${result}\n\n`;
    onToken(banner);

    messages.push({ role: 'assistant', content: buf });
    messages.push({ role: 'user', content: `[TOOL_RESULT: ${call.tool.name}]\n${result}\n\nContinue from where you stopped. Now write a concise answer for the user using these results. Do NOT repeat the tool call. Do NOT emit any more bracketed markers or harmony commentary unless you genuinely need another search/lookup.` });
  }
  /* Hop budget exhausted. Out-of-band hint so it doesn't end up in the
     agent's journal or in user-visible chat as if it were the model speaking. */
  if (onHint) onHint(`_(per-turn tool budget exhausted (${maxToolHops} hops). If you're inside a research mission this iteration is done — the next iteration will pick up.)_`);
}

function resolveModel(m) {
  if (!m) return undefined;
  if (m === 'lmstudio') return undefined;
  return m;
}

window.MOCK = {
  AGENT_COLORS, ROLES, TOOLS_CATALOG, MODELS,
  INITIAL_AGENTS, INITIAL_CHAT, ACTIVITY_SEED,
  uid, extractApproval, extractDM, extractAllDMs, extractMention, extractAllMentions, extractAcks, stripAcks, clearVaultReadyCache, throttleTokens, cleanHarmony,
  ceoStream, agentStream, chatToMessages, buildCeoSystem, supportsJsonToolFormat,
};
// Back-compat alias so older call sites keep working; routes to the real CEO stream.
window.MOCK.mockStream = (prompt, onToken, opts) => ceoStream(prompt, onToken, opts);
