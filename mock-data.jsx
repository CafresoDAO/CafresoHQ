/* ==========================================================================
   CafresoHQ — mock data + small utilities
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
   The live ModelPicker (window.CafresoHQClient.localModelOptions) is the
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
    model: 'cafresohq:sonnet',
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
    model: 'cafresohq:sonnet',
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
    model: 'cafresohq:sonnet',
    elevated: true,
    temperature: 0.2,
    hiredAt: Date.now() - 1000 * 60 * 60 * 120,
    lastRun: '1h ago',
    nextRun: 'on demand',
  },
];

/* OpenSwarm-style specialist roster.
   Seven specialists modeled on github.com/VRSEN/openswarm. CafresoHQ (CEO) is
   the orchestrator; these are the workers. Each template provides a name, a
   crisp role, a tailored system prompt, and the tools they need.
   Tools currently wired in CafresoHQ: 'web' (search), 'vault' (notes), 'files'
   (read/write for elevated agents), 'email', 'cal' (calendar), 'db' (data).
   Use spawnOpenswarmRoster(setAgents, existingAgents) to hire missing ones. */
const OPENSWARM_ROSTER = [
  {
    name: 'Vera',
    role: 'Virtual Assistant',
    color: 'rose',
    tools: ['web','email','cal','vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.4,
    systemPrompt:
      "You are Vera, the Virtual Assistant on CafresoHQ's team. You handle everyday operational work: writing short-form copy, scheduling, messaging, task management, and external system queries. Be concise (2-4 sentences). For composed messages or scheduling drafts longer than ~200 words, save to the vault under Drafts/<slug>.md via [VAULT_NEW] and return just the path + a one-line summary. Flag anything that needs the boss's decision.",
  },
  {
    name: 'Kip',
    role: 'Deep Research',
    color: 'teal',
    tools: ['web','vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.5,
    systemPrompt:
      "You are Kip, the Deep Research specialist. You conduct evidence-based research with citations and balanced analysis. Use [SEARCH] to gather sources, then synthesize into a research note saved to Research/<topic>.md via [VAULT_NEW]. In chat, return ONLY a 2-4 sentence executive summary + the vault path. Always cite at least 3 distinct sources. Flag conflicting evidence rather than hiding it.",
  },
  {
    name: 'Dax',
    role: 'Data Analyst',
    color: 'sun',
    tools: ['files','vault','db'],
    model: 'cafresohq:sonnet',
    temperature: 0.2,
    elevated: true,
    systemPrompt:
      "You are Dax, the Data Analyst. You analyze structured data, compute KPIs, run statistical checks, and produce charts/tables. For analyses longer than ~200 words, save the full report (with table excerpts and any chart specs) to Reports/<topic>.md via [VAULT_NEW]. In chat, return the headline numbers + the vault path. Be precise about uncertainty; never round away meaningful precision without flagging it.",
  },
  {
    name: 'Sloan',
    role: 'Slides Agent',
    color: 'lavender',
    tools: ['vault','files'],
    model: 'cafresohq:sonnet',
    temperature: 0.5,
    elevated: true,
    systemPrompt:
      "You are Sloan, the Slides specialist. You produce REAL .pptx PowerPoint decks via [EXPORT_PPTX: Slides/<topic>.pptx]…[/EXPORT_PPTX]. The body is a markdown outline: `# Deck Title` for the title slide, then `## Slide N: Title` for each slide, then `- bullet` lines for points. The server renders the actual PowerPoint file via python-pptx and saves it to the vault. In chat, return: slide count + main theme + the .pptx vault path. Never paste the deck content into chat — the boss opens it directly from the vault. Visual design notes (layout, image suggestions) go as italicised bullets the user can ignore or have Pixel render.",
  },
  {
    name: 'Quill',
    role: 'Docs Agent',
    color: 'leaf',
    tools: ['vault','files'],
    model: 'cafresohq:sonnet',
    temperature: 0.4,
    elevated: true,
    systemPrompt:
      "You are Quill, the Documents specialist. You produce REAL deliverables: .docx via [EXPORT_DOCX: Docs/<topic>.docx]…[/EXPORT_DOCX] for editable Word documents, or .pdf via [EXPORT_PDF: Docs/<topic>.pdf]…[/EXPORT_PDF] for finalised PDFs. The body is markdown (headings, bullets, tables, numbered lists). Pick the right format: .docx if the boss will edit it, .pdf if they'll just read/send it. The server renders the actual file and saves it to the vault. In chat, return: file type + word count + the vault path. Never paste the full content into chat.",
  },
  {
    name: 'Pixel',
    role: 'Image Generation',
    color: 'rose',
    tools: ['vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.8,
    systemPrompt:
      "You are Pixel, the Image Generation specialist. You generate REAL images via [GENERATE_IMAGE: Images/<slug>.png]\\n<detailed image prompt>\\n[/GENERATE_IMAGE]. The provider+model come from Settings → Media. Cloud options: OpenAI DALL·E, Google Imagen, fal.ai Flux. Local options (free, no API cost): Automatic1111 WebUI, ComfyUI. The server calls the configured backend and saves the rendered image to the vault. Craft the prompt carefully: subject, style, composition, lighting, mood, aspect-ratio hints. In chat, return: 1-line prompt summary + the image vault path. If the boss asks for multiple variations, emit multiple GENERATE_IMAGE blocks with distinct paths. If Settings → Media isn't configured, you'll see no GENERATE_IMAGE tool — tell the boss to configure a provider.",
  },
  {
    name: 'Reel',
    role: 'Video Generation',
    color: 'lavender',
    tools: ['vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.7,
    systemPrompt:
      "You are Reel, the Video Generation specialist. You generate REAL videos via [GENERATE_VIDEO: Videos/<slug>.mp4]\\n<detailed video prompt>\\n[/GENERATE_VIDEO]. Provider+model come from Settings → Media. Cloud: fal.ai (Seedance/Veo/Kling recommended; Sora gated). Local: ComfyUI running an AnimateDiff/SVD/Mochi/Hunyuan workflow (the boss must export the workflow JSON from Comfy first — you don't author workflows yourself). Write the prompt as a single coherent scene description: subject, action, camera, style, mood. Most providers cap at ~5-10s — keep scope tight. The render takes minutes; the server saves the .mp4 to the vault. In chat, return: prompt summary + duration + the vault path. For longer pieces, emit multiple GENERATE_VIDEO blocks (separate scenes).",
  },
  {
    name: 'Atlas',
    role: 'News Mapper',
    color: 'teal',
    tools: ['web', 'vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.3,
    systemPrompt:
      "You are Atlas, the News Mapper. Run on a schedule (start a Research mission with a news beat as the topic) and turn a stream of headlines into an explorable CONCEPT MAP. Each cycle: [SEARCH:] the beat for the latest developments, pick ONE story you haven't covered, and write a tight note to News/<beat-slug>/<story-slug>.md via [VAULT_NEW]. Write in plain declarative sentences DENSE with concrete named entities — people, organizations, places, products, technologies, events — because those entities become the nodes of the concept map and their co-occurrence becomes the edges. Avoid filler and hedging; one fact per sentence. Add frontmatter '---\\ntags: [news, <beat-slug>]\\n---' and a few [[wikilinks]] to related notes. In chat return a 1-2 sentence digest + the vault path. The boss views your map in 🧠 Graph → 🧠 Concepts, scoped to your News/ folder, and can publish it as a shareable public graph.",
  },
];

/* Hire any OPENSWARM_ROSTER specialists that aren't already on the team.
   Returns the number of new agents added. Matches by name (case-insensitive)
   so users who hand-edited their roster don't get dupes. */
function spawnOpenswarmRoster(existingAgents, addAgent) {
  const have = new Set((existingAgents || []).map(a => String(a.name || '').toLowerCase()));
  let added = 0;
  for (const tpl of OPENSWARM_ROSTER) {
    if (have.has(tpl.name.toLowerCase())) continue;
    const agent = {
      ...tpl,
      id: uid('a'),
      status: 'idle',
      task: 'standing by',
      hiredAt: Date.now(),
      lastRun: 'just hired',
      nextRun: 'on demand',
    };
    addAgent(agent);
    added++;
  }
  return added;
}

/* Production note: these used to ship fake "demo" content (a canned chat
   conversation and a fake activity ticker). Real users couldn't tell what was
   real, and the fake chat persisted to localStorage as if it had happened.
   New accounts now start clean — the thread/ticker empty states do the
   teaching instead. */
const INITIAL_CHAT = [];

const ACTIVITY_SEED = [];

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

/* Find a [HANDOFF_TO: name]\n<body>\n[/HANDOFF_TO] block. Returns {to, body}
   or null. Used by CafresoHQ to transfer thread ownership to a single
   specialist — after the handoff the user's next messages go directly to
   that specialist with CafresoHQ out of the loop. */
function extractHandoff(text) {
  if (!text) return null;
  const m = String(text).match(/\[\s*HANDOFF_TO\s*:\s*([^\]\n]+)\]\s*\n?([\s\S]*?)\n?\[\s*\/\s*HANDOFF_TO\s*\]/i);
  return m ? { to: m[1].trim(), body: (m[2] || '').trim() } : null;
}

/* Strip handoff blocks from text so we can render CafresoHQ's reply without
   showing the raw bracket markup. */
function stripHandoff(text) {
  if (!text) return text;
  return String(text).replace(/\[\s*HANDOFF_TO\s*:\s*[^\]\n]+\]\s*\n?[\s\S]*?\n?\[\s*\/\s*HANDOFF_TO\s*\]\s*/gi, '').trim();
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
    const s = await window.CafresoHQClient.vaultStatus();
    _vaultConfiguredCache = { at: now, ok: !!(s.configured && s.exists) };
  } catch (_e) { _vaultConfiguredCache = { at: now, ok: false }; }
  return _vaultConfiguredCache.ok;
}
function clearVaultReadyCache() { _vaultConfiguredCache = { at: 0, ok: false }; }

const TOOL_REGISTRY = {
  search: {
    name: 'SEARCH',
    re: /\[\s*SEARCH\s*:\s*([^\]\n]+)\]/i,
    requires: () => window.CafresoHQClient.getSettings().braveEnabled && window.CafresoHQClient.getSettings().braveKey,
    doc: '- [SEARCH: <query>] — Brave web search. Use for facts, news, current state. Stop after the line; results will be appended.',
    docShort: 'Web search via Brave. Use for facts, news, current state.',
    run: async (query, { signal }) => {
      const results = await window.CafresoHQClient.braveSearch(query.trim(), { count: 6, signal });
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
      const hits = await window.CafresoHQClient.vaultSearch(query.trim(), { limit: 8 });
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
      const text = await window.CafresoHQClient.vaultRead(path.trim());
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
      const r = await window.CafresoHQClient.vaultWrite(path.trim(), body || '', 'append');
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
      const r = await window.CafresoHQClient.vaultWrite(path.trim(), body || '', 'write');
      return `Wrote ${(body||'').length} chars → ${r.path}`;
    },
  },
  /* EXPORT_PPTX / EXPORT_DOCX / EXPORT_PDF — render real binary deliverables
     into the vault. The body is markdown; the server renders to the actual
     binary format using python-pptx / python-docx / weasyprint(or reportlab).
     Used by Sloan / Quill for actual file outputs the boss can download. */
  export_pptx: {
    name: 'EXPORT_PPTX',
    re: /\[\s*EXPORT_PPTX\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*EXPORT_PPTX\s*\]/i,
    requires: () => true,
    doc:
      '- [EXPORT_PPTX: <path>]\n<markdown outline>\n[/EXPORT_PPTX] — render a real .pptx slide deck and save to the vault.\n' +
      '  Outline format: `# Title` for the title slide, `## Slide N: Title` for each slide, `- bullet` lines for points.\n' +
      '  Returns the saved vault path. Use this for any deck deliverable — do NOT save as plain .md.',
    docShort: 'Render markdown into a real .pptx PowerPoint deck and save to the vault.',
    run: async (path, _ctx, body) => {
      const r = await window.CafresoHQClient.exportPptx(path.trim(), body || '');
      return `Saved PowerPoint (${r.slides || '?'} slide${r.slides === 1 ? '' : 's'}) → ${r.path}`;
    },
  },
  export_docx: {
    name: 'EXPORT_DOCX',
    re: /\[\s*EXPORT_DOCX\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*EXPORT_DOCX\s*\]/i,
    requires: () => true,
    doc:
      '- [EXPORT_DOCX: <path>]\n<markdown content>\n[/EXPORT_DOCX] — render a real .docx Word document and save to the vault.\n' +
      '  Use headings (`#` / `##` / `###`), bullets (`-` / `*`), and numbered lists (`1.`). Returns the saved vault path.',
    docShort: 'Render markdown into a real .docx Word document and save to the vault.',
    run: async (path, _ctx, body) => {
      const r = await window.CafresoHQClient.exportDocx(path.trim(), body || '');
      return `Saved Word doc → ${r.path}`;
    },
  },
  export_pdf: {
    name: 'EXPORT_PDF',
    re: /\[\s*EXPORT_PDF\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*EXPORT_PDF\s*\]/i,
    requires: () => true,
    doc:
      '- [EXPORT_PDF: <path>]\n<markdown content>\n[/EXPORT_PDF] — render a real .pdf and save to the vault.\n' +
      '  Renderer: weasyprint if available (better typography), reportlab fallback. Returns the saved vault path.',
    docShort: 'Render markdown into a real .pdf and save to the vault.',
    run: async (path, _ctx, body) => {
      const r = await window.CafresoHQClient.exportPdf(path.trim(), body || '');
      return `Saved PDF (${r.renderer || '?'}) → ${r.path}`;
    },
  },
  /* GENERATE_IMAGE / GENERATE_VIDEO — call the user-configured media provider
     (OpenAI / Google / fal.ai) and save the binary into the vault. The
     provider + model + API key come from settings (mediaProvider / mediaModel
     / per-provider API keys). */
  generate_image: {
    name: 'GENERATE_IMAGE',
    re: /\[\s*GENERATE_IMAGE\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*GENERATE_IMAGE\s*\]/i,
    requires: () => true,
    doc:
      '- [GENERATE_IMAGE: <vault path, e.g. Images/concept.png>]\n<image prompt>\n[/GENERATE_IMAGE] — generate a real image and save to the vault.\n' +
      '  Uses the provider/model from Settings → Media. Returns the saved vault path.',
    docShort: 'Generate a real image using the configured provider and save to the vault.',
    run: async (path, _ctx, body) => {
      const r = await window.CafresoHQClient.generateImage(path.trim(), (body || '').trim());
      return `Generated image (${r.provider}) → ${r.path}`;
    },
  },
  generate_video: {
    name: 'GENERATE_VIDEO',
    re: /\[\s*GENERATE_VIDEO\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*GENERATE_VIDEO\s*\]/i,
    requires: () => true,
    doc:
      '- [GENERATE_VIDEO: <vault path, e.g. Videos/demo.mp4>]\n<video prompt>\n[/GENERATE_VIDEO] — generate a real video and save to the vault.\n' +
      '  Uses the provider/model from Settings → Media. Can take several minutes. Returns the saved vault path.',
    docShort: 'Generate a real video using the configured provider and save to the vault.',
    run: async (path, _ctx, body) => {
      const r = await window.CafresoHQClient.generateVideo(path.trim(), (body || '').trim());
      return `Generated video (${r.provider}) → ${r.path}`;
    },
  },
  /* File / shell tools — only enabled for elevated agents regardless of LLM
     provider. Execution is handled by serve.py /tools/exec, which validates
     paths against CAFRESOHQ_ALLOWED_DIRS server-side. */
  file_read: {
    name: 'FILE_READ',
    re: /\[\s*FILE_READ\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [FILE_READ: <path>] — read a local file. Path must be within the configured allowed directories.',
    docShort: 'Read a local file by absolute path within the allowed directories.',
    run: async (path, { signal, cwd }) => window.CafresoHQClient.toolExec('FILE_READ', path.trim(), { signal, cwd }),
  },
  dir_list: {
    name: 'DIR_LIST',
    re: /\[\s*DIR_LIST\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [DIR_LIST: <path>] — list files and subdirectories at a path. Use to explore project structure before reading files.',
    docShort: 'List files and subdirectories at a path. Use to explore structure before reading.',
    run: async (path, { signal, cwd }) => window.CafresoHQClient.toolExec('DIR_LIST', path.trim(), { signal, cwd }),
  },
  file_write: {
    name: 'FILE_WRITE',
    re: /\[\s*FILE_WRITE\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*FILE_WRITE\s*\]/i,
    requires: () => true,
    doc: '- [FILE_WRITE: <path>]\n<content>\n[/FILE_WRITE] — write (create or overwrite) a local file. Path must be within allowed directories.',
    docShort: 'Write (create or overwrite) a local file; body goes in the "body" field.',
    run: async (path, { cwd }, body) => window.CafresoHQClient.toolExec('FILE_WRITE', path.trim(), { body: body || '', cwd }),
  },
  bash: {
    name: 'BASH',
    re: /\[\s*BASH\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [BASH: <command>] — run a shell command on the proxy machine (cwd = project dir or first allowed dir). Requires Bash in CAFRESOHQ_ALLOWED_TOOLS.',
    docShort: 'Run a shell command on the proxy machine. Requires Bash in CAFRESOHQ_ALLOWED_TOOLS.',
    run: async (cmd, { signal, cwd }) => window.CafresoHQClient.toolExec('BASH', cmd.trim(), { signal, cwd }),
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
  /* HANDOFF_TO — transfer thread ownership from CafresoHQ to ONE specialist.
     After the marker, the user converses directly with the specialist until
     they say "back to CafresoHQ". Host-dispatched. */
  handoff_to: {
    name: 'HANDOFF_TO',
    re: /\[\s*HANDOFF_TO\s*:\s*([^\]\n]+)\]\s*\n?([\s\S]*?)\n?\[\s*\/\s*HANDOFF_TO\s*\]/i,
    requires: () => true,
    doc: '- [HANDOFF_TO: <specialist name>]\n<one-line context for the specialist>\n[/HANDOFF_TO] — transfer the thread to ONE specialist who owns the task end-to-end. The boss will iterate directly with them. Use this for single-specialist tasks. Stop immediately after the block; the specialist takes over.',
    docShort: 'Transfer the chat thread to one specialist (boss talks to them directly until "back to CafresoHQ").',
    run: async () => '(HANDOFF_TO is dispatched by the host)',
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
               TOOL_REGISTRY.vault_append, TOOL_REGISTRY.vault_new,
               // Binary deliverables — pptx/docx/pdf live next to .md notes
               // in the vault. Available to any agent with vault access.
               TOOL_REGISTRY.export_pptx, TOOL_REGISTRY.export_docx,
               TOOL_REGISTRY.export_pdf);
    }
  }
  // Media generation tools — available when a media provider is configured
  // in settings (Settings → Media). Otherwise agents would happily emit the
  // marker and the call would 400 with "provider required".
  try {
    const s = (window.CafresoHQClient && window.CafresoHQClient.getSettings) ? window.CafresoHQClient.getSettings() : {};
    if (s && s.imageProvider) out.push(TOOL_REGISTRY.generate_image);
    if (s && s.videoProvider) out.push(TOOL_REGISTRY.generate_video);
  } catch (_e) { /* settings store may not be ready during init */ }
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
        const all = await window.CafresoHQClient.vaultList();
        const mine = (all || []).filter(p => p.startsWith(root + '/'));
        if (!mine.length) return `(your memory is empty — write your first note with [MEMORY_WRITE: notes/foo.md]…[/MEMORY_WRITE])`;
        return mine.map(p => '• ' + p.slice(root.length + 1)).join('\n');
      },
    });
    out.push({
      ...TOOL_REGISTRY.memory_read,
      run: async (rel) => {
        try {
          const text = await window.CafresoHQClient.vaultRead(scope(rel));
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
        const r = await window.CafresoHQClient.vaultWrite(target, body || '', 'write');
        return `Wrote ${(body||'').length} chars → ${r.path}`;
      },
    });
    out.push({
      ...TOOL_REGISTRY.memory_append,
      run: async (rel, _ctx, body) => {
        const target = scope(rel);
        const stamped = `\n\n## ${new Date().toISOString().slice(0, 19).replace('T', ' ')}\n${body || ''}\n`;
        const r = await window.CafresoHQClient.vaultWrite(target, stamped, 'append');
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
  const { provider } = window.CafresoHQClient.parseModelId(model);
  if (['anthropic', 'cafresohq', 'claudecode', 'codex', 'google'].includes(provider)) return true;
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

const CEO_SYSTEM = `You are CafresoHQ, the CEO and ORCHESTRATOR for the boss's team of AI sub-agents. You are a warm, decisive chief of staff — direct, concise, with light personality. Sign messages as "CafresoHQ" (not "CafresoHQ"). Keep replies tight (2-4 sentences).

═══════════════════════════════════════════════════════════════
ROUTING-ONLY (CRITICAL)
═══════════════════════════════════════════════════════════════
Your ONLY job is to turn the boss's goals into the right multi-agent execution strategy and ROUTE work to specialists on the HIRED roster. You do NOT execute substantive work yourself.

You must NEVER:
- Research, write long-form content, or analyze data yourself.
- Create or edit slides, documents, images, or videos yourself.
- Synthesize or generate deliverables — specialists do that.
- Invent sub-agents that aren't on the HIRED roster.

You ONLY:
- Interpret the boss's request.
- Pick the right specialist(s) and the right delegation mode.
- Delegate via the explicit markers below.
- For parallel fan-outs, combine specialist outputs into one tight final reply.
- For small conversational asks (greetings, status checks, quick clarifying questions about the team) you may answer directly.

If a request needs a specialist you don't have, say so and suggest who to hire — do NOT attempt the work.

═══════════════════════════════════════════════════════════════
DELEGATION MODES — pick ONE per task
═══════════════════════════════════════════════════════════════

1) PARALLEL DELEGATION — use [DM_TO: name] blocks
   Use when the task splits into 2 or more INDEPENDENT subtasks that different specialists can do at the same time.

   Format (one block per recipient — emit them all in the same reply):
     [DM_TO: Mira]
     <subtask for Mira>
     [/DM_TO]
     [DM_TO: Kip]
     <subtask for Kip>
     [/DM_TO]

   You will receive their replies and then synthesize ONE unified summary back to the boss. Do NOT paste the raw specialist outputs verbatim — extract what matters.

2) HANDOFF — use [HANDOFF_TO: name] when ONE specialist owns the task end-to-end and the boss will iterate with them directly.
   Format:
     [HANDOFF_TO: Kip]
     <one-line context for the specialist + what the boss wants>
     [/HANDOFF_TO]

   The specialist takes over the thread. The boss talks to them directly — you step out until the boss says "back to CafresoHQ". Do NOT keep narrating after a HANDOFF_TO marker — emit the block and stop.

RULE OF THUMB:
- 1 specialist needed → HANDOFF_TO (default for single-specialist tasks)
- 2+ specialists in parallel → DM_TO blocks
- Single-specialist task you could finish in one turn with no iteration → either works; prefer HANDOFF_TO if the boss is likely to follow up.

═══════════════════════════════════════════════════════════════
FILE-DELIVERY RULE
═══════════════════════════════════════════════════════════════
Specialists save large deliverables (notes, reports, drafts, analyses over ~200 words) to the vault and return the path. You do NOT paste raw markdown/HTML/long content into chat.

When relaying back: cite the vault path and give a 1-3 sentence summary. Only paste full content if the boss explicitly asks "show me the raw text".

═══════════════════════════════════════════════════════════════
APPROVAL PROTOCOL
═══════════════════════════════════════════════════════════════
For any action that sends an email, posts publicly, schedules a commitment, or spends money over $100, do NOT execute and do NOT delegate yet. End your reply with a single line:
  [NEEDS_APPROVAL: <one-line description of the action and any cost>]
The boss will stamp it. Once stamped you'll be told to proceed.

═══════════════════════════════════════════════════════════════
OUTPUT STYLE
═══════════════════════════════════════════════════════════════
- Briefly state your routing decision ("Handing this to Kip" / "Splitting between Mira and Kip in parallel") in one sentence before the delegation markers.
- After a HANDOFF_TO block, STOP — don't keep talking.
- After parallel DM_TOs return, give the boss ONE combined reply with the synthesized result and any vault paths.`;

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
  return 'Long-term memory (notes CafresoHQ has saved about the boss & ongoing work):\n' +
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
if (window.CafresoHQClient && window.CafresoHQClient.onSettingsChange) {
  window.CafresoHQClient.onSettingsChange(() => {
    _registryCache = { at: 0, value: '', inflight: null };
  });
}
async function registrySnippet() {
  const now = Date.now();
  if (now - _registryCache.at < REGISTRY_TTL_MS) return _registryCache.value;
  if (_registryCache.inflight) return _registryCache.inflight;
  _registryCache.inflight = (async () => {
    try {
      const reg = await window.CafresoHQClient.localRegistry();
      const value = window.CafresoHQClient.formatRegistry(reg);
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
  // It also gets the routing markers (DM_TO for parallel fan-out, HANDOFF_TO
  // for single-specialist transfer) so the openswarm-style orchestrator
  // behavior works.
  const ceoTools = [];
  if (TOOL_REGISTRY.search.requires()) ceoTools.push(TOOL_REGISTRY.search);
  if (await TOOL_REGISTRY.vault_search.requires()) {
    ceoTools.push(TOOL_REGISTRY.vault_search, TOOL_REGISTRY.vault_read,
                  TOOL_REGISTRY.vault_append, TOOL_REGISTRY.vault_new);
  }
  if ((agents || []).length) {
    ceoTools.push(TOOL_REGISTRY.dm_to, TOOL_REGISTRY.handoff_to);
  }
  const useJsonCeo = supportsJsonToolFormat(model);
  const ceoToolSnippet = ceoTools.length ? (useJsonCeo ? toolsPromptSnippetJson(ceoTools) : toolsPromptSnippet(ceoTools)) : '';
  const sys = system || (buildCeoSystem(agents || [], reg) + (ceoToolSnippet ? '\n\n' + ceoToolSnippet : ''));

  for (let hop = 0; hop < MAX_TOOL_HOPS; hop++) {
    let buf = '';
    await window.CafresoHQClient.stream({
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
          emit(peek ? `_(empty after cleaning. Raw: "${peek}…")_`
            : '_(no response from the model. On a free model this usually means the prompt was too large — try **Settings → Connections → Agent capability → "Lite"**, or pick a smaller/paid model.)_');
        }
      }
      return;
    }

    // HANDOFF_TO — transfer thread to a specialist. Host catches the event,
    // updates the active responder, and the CEO stops. We do NOT recurse.
    if (call.tool.name === 'HANDOFF_TO') {
      if (onTool) onTool({ phase: 'handoff', name: 'HANDOFF_TO', arg: call.arg, body: call.body });
      return;
    }

    // DM_TO — host-dispatched parallel fan-out. CEO emits one or more DM
    // blocks; host delivers them to specialists and (eventually) re-invokes
    // CEO with the synthesised replies. Stop streaming after the first
    // marker — the rest of buf may contain additional DM blocks that the
    // host will pick up via extractAllDMs.
    if (call.tool.name === 'DM_TO') {
      const dms = extractAllDMs(buf);
      const list = dms.length ? dms : [{ to: call.arg, body: call.body }];
      if (onTool) {
        for (const dm of list) onTool({ phase: 'dm', name: 'DM_TO', arg: dm.to, body: dm.body });
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

  const base = agent.systemPrompt || `You are ${agent.name}, a specialist sub-agent at CafresoHQ. Role: ${agent.role}. Be concise (2-4 sentences), report progress honestly, and flag anything that needs the boss's decision.

FILE-DELIVERY RULE: Any deliverable longer than ~200 words (notes, drafts, reports, analyses, summaries) MUST be saved to the vault using [VAULT_NEW: <path>]…[/VAULT_NEW] or [VAULT_APPEND: <path>]…[/VAULT_APPEND]. In your chat reply, return ONLY a 1-3 sentence summary plus the vault path. Do NOT paste the full content into chat unless the boss explicitly asks for the raw text. Suggested paths: Research/<topic>.md for findings, Drafts/<topic>.md for drafts, Reports/<topic>.md for analyses.`;
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
    const all = await window.CafresoHQClient.vaultList();
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
    await window.CafresoHQClient.stream({
      system: sys,
      messages,
      model: resolveModel(agent.model),
      temperature: typeof agent.temperature === 'number' ? agent.temperature : 0.5,
      onToken: tok => { buf += tok; onToken(tok); },
      onUsage,
      signal,
      maxTokens,
      // Forwarded only by the cafresohq provider — others ignore it.
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
  INITIAL_AGENTS, INITIAL_CHAT, ACTIVITY_SEED, OPENSWARM_ROSTER, spawnOpenswarmRoster,
  uid, extractApproval, extractDM, extractAllDMs, extractHandoff, stripHandoff, extractMention, extractAllMentions, extractAcks, stripAcks, clearVaultReadyCache, throttleTokens, cleanHarmony,
  ceoStream, agentStream, chatToMessages, buildCeoSystem, supportsJsonToolFormat,
};
// Back-compat alias so older call sites keep working; routes to the real CEO stream.
window.MOCK.mockStream = (prompt, onToken, opts) => ceoStream(prompt, onToken, opts);
