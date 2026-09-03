import { CafresoHQChain, CafresoHQClient } from './claude-client.jsx';
import { stripOfficeVoice, visitLine, visitPlace, visitWords } from './app/floor.jsx';
import { memoryRoot } from './app/cast.jsx';
import { citesOutside, officeDate, officeStamp, unwrittenPaths, workingNotes } from './app/artifacts.jsx';
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
  { id: 'web',    label: 'Web Search' },
  { id: 'vault',  label: 'Library'    },
  { id: 'code',   label: 'Code Exec'  },
  { id: 'files',  label: 'File Access'},
  { id: 'email',  label: 'Email Send' },
  { id: 'cal',    label: 'Calendar'   },
  { id: 'db',     label: 'Database'   },
  { id: 'slack',  label: 'Slack'      },
  { id: 'img',    label: 'Image Gen'  },
  // ICP wallet — only takes effect once the Wallet ICP-Service is installed
  // (Settings → ICP Services) and the app runs inside the ai.cafreso.com shell.
  { id: 'wallet', label: 'ICP Wallet' },
];

/* Legacy unprefixed IDs — kept for any callers still reading HQ.MODELS.
   The live ModelPicker (CafresoHQClient.localModelOptions) is the
   source of truth for new code; agents store provider-prefixed ids. */
const MODELS = [
  'anthropic:claude-opus-4-7',
  'anthropic:claude-sonnet-4-6',
  'anthropic:claude-haiku-4-5-20251001',
];

/* No pre-seeded agents. New offices open with the CEO alone and a floor of
   VACANT desks — same never-fabricate-state rule as INITIAL_CHAT below: the
   old Mira/Kip/Bop seed shipped invented histories ("triaging 23 emails",
   28k tokens spent) that users couldn't tell from real work, and it kept the
   first-launch onboarding tour (gated on an empty roster) from ever firing.
   The CEO's scripted welcome + the HireModal candidates deck do the
   introduction instead. */
const INITIAL_AGENTS = [];

/* OpenSwarm-style specialist roster.
   Seven specialists modeled on github.com/VRSEN/openswarm. CafresoHQ (CEO) is
   the orchestrator; these are the workers. Each template provides a name, a
   crisp role, a tailored system prompt, and the tools they need.
   Tools currently wired in CafresoHQ: 'web' (search), 'vault' (notes), 'img'
   (media, with a provider), and file/shell work, which is NOT a tools entry —
   it rides the 🛡 File & shell access switch.

   The three this list used to also name — 'email', 'cal', 'db' — were audited
   out on 2026-08-13: no EMAIL_SEND, no CALENDAR, no DATABASE tool exists, so
   `toolsForAgent` has never had anything to hand over for them, and both
   pickers hide them (modals/settings.jsx, NEVER_WIRED_TOOL_IDS). This comment
   went on saying they were wired, and Vera and Dax went on being minted with
   them, which is how a hired coworker's card ended up advertising "DB". They
   are gone from the templates below. The catalog entries stay where the audit
   left them; what changes here is that the shelf stops handing out claims
   nothing can honour.

   Use spawnOpenswarmRoster(setAgents, existingAgents) to hire missing ones. */
const OPENSWARM_ROSTER = [
  {
    name: 'Vera',
    role: 'Virtual Assistant',
    color: 'rose',
    tools: ['web','vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.4,
    systemPrompt:
      "You are Vera, the Virtual Assistant on CafresoHQ's team. You handle everyday operational work: writing short-form copy, scheduling, messaging, task management, and external system queries. Be concise (2-4 sentences). For composed messages or scheduling drafts longer than ~200 words, save to the Library under Drafts/<slug>.md via [VAULT_NEW] and return just the path + a one-line summary. Flag anything that needs the boss's decision.",
  },
  {
    name: 'Kip',
    role: 'Deep Research',
    color: 'teal',
    tools: ['web','vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.5,
    systemPrompt:
      "You are Kip, the Deep Research specialist. You conduct evidence-based research with citations and balanced analysis. Use [SEARCH] to gather sources, then synthesize into a research note saved to Research/<topic>.md via [VAULT_NEW]. In chat, return ONLY a 2-4 sentence executive summary + the Library path. Always cite at least 3 distinct sources. Flag conflicting evidence rather than hiding it.",
  },
  {
    name: 'Dax',
    role: 'Data Analyst',
    color: 'sun',
    tools: ['files','vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.2,
    /* No `elevated` on any template. It was never honoured by either
       single-hire path (hire.jsx forces the switch off, deliberately), it
       WAS honoured by the shelf's bulk tile, and it is read on this screen
       one more time: `capabilityFacts` hands it to the candidate card, so
       the flag made the card promise "can work with your files" for a hire
       that would arrive without them. Dropping it makes the pitch read
       "…once you switch on their file & shell access", which is the same
       sentence the hired card shows and points at the same switch. */
    systemPrompt:
      "You are Dax, the Data Analyst. You analyze structured data, compute KPIs, run statistical checks, and produce charts/tables. For analyses longer than ~200 words, save the full report (with table excerpts and any chart specs) to Reports/<topic>.md via [VAULT_NEW]. In chat, return the headline numbers + the Library path. Be precise about uncertainty; never round away meaningful precision without flagging it.",
  },
  {
    name: 'Sloan',
    role: 'Slides Agent',
    color: 'lavender',
    tools: ['vault','files'],
    model: 'cafresohq:sonnet',
    temperature: 0.5,
    /* Sloan and Quill lose nothing: EXPORT_PPTX/DOCX/PDF are granted off
       the vault claim, never off elevation. See the note on Dax. */
    systemPrompt:
      "You are Sloan, the Slides specialist. You produce REAL .pptx PowerPoint decks via [EXPORT_PPTX: Slides/<topic>.pptx]…[/EXPORT_PPTX]. The body is a markdown outline: `# Deck Title` for the title slide, then `## Slide N: Title` for each slide, then `- bullet` lines for points. The server renders the actual PowerPoint file via python-pptx and files it in the Library. In chat, return: slide count + main theme + the .pptx Library path. Never paste the deck content into chat — the boss opens it directly from the Library. Visual design notes (layout, image suggestions) go as italicised bullets the user can ignore or have Pixel render.",
  },
  {
    name: 'Quill',
    role: 'Docs Agent',
    color: 'leaf',
    tools: ['vault','files'],
    model: 'cafresohq:sonnet',
    temperature: 0.4,
    /* Same as Sloan — the exports ride the vault. See the note on Dax. */
    systemPrompt:
      "You are Quill, the Documents specialist. You produce REAL deliverables: .docx via [EXPORT_DOCX: Docs/<topic>.docx]…[/EXPORT_DOCX] for editable Word documents, or .pdf via [EXPORT_PDF: Docs/<topic>.pdf]…[/EXPORT_PDF] for finalised PDFs. The body is markdown (headings, bullets, tables, numbered lists). Pick the right format: .docx if the boss will edit it, .pdf if they'll just read/send it. The server renders the actual file and files it in the Library. In chat, return: file type + word count + the Library path. Never paste the full content into chat.",
  },
  {
    name: 'Pixel',
    role: 'Image Generation',
    color: 'rose',
    /* Un-parked 2026-08-13. Was parked because `toolsForAgent` only grants
       GENERATE_IMAGE when `getSettings().imageProvider` is set and no
       Settings screen anywhere could ever set it — Pixel's own job
       description promised "configure a provider in Settings → Media", a
       screen that didn't exist. That screen now exists (modals/providers.jsx
       MediaTab, mounted at Settings -> Media), so the promise the prompt
       below makes is real. Reel (video) stays parked — that one is a
       broader product-scope call (north-star section 5), not this gap.

       'img' added 2026-08-14, at which point `toolsForAgent` granted
       GENERATE_IMAGE off the settings provider alone, never off this list,
       so ticking it changed nothing about what Pixel could DO — it was
       added because every card in the product is written from this list,
       and a card built from ['vault'] introduced the image specialist as
       "can read your notes". As of 2026-08-15 the claim is load-bearing:
       the grant reads this list AND the provider, so this line is now the
       only reason Pixel can make images at all. Do not remove it. */
    tools: ['img', 'vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.8,
    systemPrompt:
      "You are Pixel, the Image Generation specialist. You generate REAL images via [GENERATE_IMAGE: Images/<slug>.png]\\n<detailed image prompt>\\n[/GENERATE_IMAGE]. The provider+model come from Settings → Media. Cloud options: OpenAI DALL·E, Google Imagen, fal.ai Flux. Local options (free, no API cost): Automatic1111 WebUI, ComfyUI. The office calls whichever image service is set up and files the rendered image in the Library. Craft the prompt carefully: subject, style, composition, lighting, mood, aspect-ratio hints. In chat, return: 1-line prompt summary + the image's Library path. If the boss asks for multiple variations, emit multiple GENERATE_IMAGE blocks with distinct paths. If Settings → Media isn't configured, you'll see no GENERATE_IMAGE tool — tell the boss to configure a provider.",
  },
  {
    name: 'Reel',
    role: 'Video Generation',
    color: 'lavender',
    /* PARKED — north-star section 5 names this row exactly: "Exporter zoo
       (video gen, ComfyUI/A1111 wiring) — cool, unfocused; image gen can
       return post-core". Parked is not deleted: the template stays here,
       complete and ready, and un-parking is deleting one line. What it
       must not do is stand on the hire board a first-run stranger sees,
       because the park list is about the CORE PATH, the onboarding and
       the pitch — and the candidate shelf is all three at once.

       (Note the row does NOT park pptx/docx/pdf. Sloan and Quill produce
       real documents and stay on the shelf; only video generation and the
       local image-backend wiring are named.) */
    parked: true,
    tools: ['vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.7,
    systemPrompt:
      "You are Reel, the Video Generation specialist. You generate REAL videos via [GENERATE_VIDEO: Videos/<slug>.mp4]\\n<detailed video prompt>\\n[/GENERATE_VIDEO]. Provider+model come from Settings → Media. Cloud: fal.ai (Seedance/Veo/Kling recommended; Sora gated). Local: ComfyUI running an AnimateDiff/SVD/Mochi/Hunyuan workflow (the boss must export the workflow JSON from Comfy first — you don't author workflows yourself). Write the prompt as a single coherent scene description: subject, action, camera, style, mood. Most providers cap at ~5-10s — keep scope tight. The render takes minutes; the server files the .mp4 in the Library. In chat, return: prompt summary + duration + the Library path. For longer pieces, emit multiple GENERATE_VIDEO blocks (separate scenes).",
  },
  {
    name: 'Atlas',
    role: 'News Mapper',
    color: 'teal',
    tools: ['web', 'vault'],
    model: 'cafresohq:sonnet',
    temperature: 0.3,
    systemPrompt:
      "You are Atlas, the News Mapper. Run on a schedule (start a Research mission with a news beat as the topic) and turn a stream of headlines into an explorable CONCEPT MAP. Each cycle: [SEARCH:] the beat for the latest developments, pick ONE story you haven't covered, and write a tight note to News/<beat-slug>/<story-slug>.md via [VAULT_NEW]. Write in plain declarative sentences DENSE with concrete named entities — people, organizations, places, products, technologies, events — because those entities become the nodes of the concept map and their co-occurrence becomes the edges. Avoid filler and hedging; one fact per sentence. Add frontmatter '---\\ntags: [news, <beat-slug>]\\n---' and a few [[wikilinks]] to related notes. In chat return a 1-2 sentence digest + the Library path. The boss views your map in 🧠 Graph → 🧠 Concepts, scoped to your News/ folder, and can publish it as a shareable public graph.",
  },
];

/* Hire any OPENSWARM_ROSTER specialists that aren't already on the team.
   Returns the number of new agents added. Matches by name (case-insensitive)
   so users who hand-edited their roster don't get dupes. */
/* `model` overrides every template's pinned brain — see candidateBrain in
   app/cast.jsx. The shelf resolves ONE brain from detection and hands it in,
   so the seven coworkers this hires run on the same brain their cards
   advertised. Omitted (undefined) keeps the template's own value, which is
   what any non-UI caller with no detection to offer should do. */
function spawnOpenswarmRoster(existingAgents, addAgent, model) {
  const have = new Set((existingAgents || []).map(a => String(a.name || '').toLowerCase()));
  let added = 0;
  for (const tpl of OPENSWARM_ROSTER) {
    if (tpl.parked) continue;                 // section 5 — off the core path
    if (have.has(tpl.name.toLowerCase())) continue;
    const agent = {
      ...tpl,
      ...(model ? { model } : {}),
      /* "elevated never flows from a template — operator must re-opt-in
         deliberately" is the rule modals/hire.jsx states at `loadTpl`, and
         both single-hire paths obey it by forcing the switch off. This one
         spread `...tpl` and carried it.

         Measured live on office 9261, 2026-08-16: the ⚡SEED SWARM tile
         asked "Hire 5 openswarm-style specialists: Dax, Sloan, Quill,
         Pixel, Atlas?" — the coworkers by name, nothing else — and Dax,
         Sloan and Quill arrived with `elevated: true`. That is file and
         shell access on the boss's machine, granted three times by a
         confirm that never said the words, on the same screen where hiring
         those same three one at a time grants it zero times and routes the
         boss through a danger-styled "Grant X COMPUTER ACCESS?" walk.

         Belt and braces: the templates no longer set the flag either, but a
         future one that does must not silently re-open this. The three
         roles lose nothing they can do — pptx/docx/pdf ride the vault
         claim, not elevation — and their cards now read "files · off" with
         the switch named, which is the route the walk exists to be. */
      elevated: false,
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
  /* The full unstripped stream. The CEO finalize used to scan the RENDERED
     message text for [NEEDS_APPROVAL] — which worked only while no strip
     family knew that marker. The moment the bubble got cleaned properly,
     the tray went blind. Scans read this; displays read the cleaned text. */
  ontok.raw = () => raw;
  /* A note is out-of-band: it is the OFFICE speaking about a request that
     never parsed, and it arrives after the stream is done. It therefore has
     to survive `cancel()`, which the callers now use to stop a queued frame
     from repainting the final cleaned text from `raw`.

     Two reasons it appends to the message rather than going through
     `schedule()` once cancelled: a cancelled flush is a no-op, so the note
     would be dropped entirely; and re-rendering from `raw` would undo the
     cleaned text the caller just wrote. Getting this wrong silently kills
     exactly the warnings that exist because a request went silently
     nowhere. */
  /* The containment guard is not defensive tidiness — without it the boss
     reads the office's honesty correction TWICE, in a row, verbatim.

     Measured on port 9260, one hire on a local brain, a reply naming
     `Research/vendor-comparison.md` with nothing filed. One `unfiledPath`
     note, one `note()` call — and two identical sentences in the bubble.
     Instrumented, the order came out:

         flushNow  ->  note() cancelled=true  ->  withNotes suffix="\n\n_(…)_"

     `withNotes` is called at app.jsx:2186 — LEXICALLY BEFORE the note is
     emitted at 2614 — but it is called *inside* a `setChat(prev => …)`
     updater, and React runs updaters when it processes the queue, not when
     the caller enqueues them. So the write that was requested first is
     evaluated last, and it reads a `suffix` that grew in between. Both
     mechanisms that exist so the note is never LOST then applied it: the
     deferred `withNotes` painted `cleaned + suffix`, and this branch
     appended the same sentence on top.

     The append is the half that cannot be reordered safely, because it is
     RELATIVE — it reads the current text and adds to it, so it duplicates
     anything an absolute write already included. Asking "is it already
     there" makes this branch idempotent whichever order React picks, and
     leaves the no-`withNotes` paths (the abort route writes its own text
     and never calls it) working exactly as before.

     All three dispatch paths call `withNotes` from inside an updater —
     @mention, Delegate and a task dropped on a desk — so all three said it
     twice. A doubled sentence is not cosmetic here: this note exists to
     tell the boss the office did not do the thing it was asked to do, and
     a correction that stutters reads like the office is unsure of it. */
  ontok.note = (text) => {
    /* The same guard as below, on the other half. The one underneath stops
       a sentence being APPENDED twice; `suffix` had none, so a sentence
       handed in twice was accumulated twice and `withNotes` painted both
       copies in one go — the guard then looked at a message that already
       contained it and correctly declined to add a third.

       Measured 2026-08-16 on office 9280, once #127 gave the office one
       sentence for a run that stopped part-way: agentStream says it live
       through the hint, and the same string comes round again in the
       honesty list at the end, which is exactly what one fact reaching two
       containers looks like. Deduping on the text is what makes that safe
       — and a note is a sentence about something that did not happen, so
       there is no reading on which the boss wants it twice. */
    if (suffix.indexOf(text) >= 0) return;
    suffix += '\n\n' + text;
    if (cancelled) {
      setChat(prev => prev.map(m => {
        if (m.id !== msgId) return m;
        const cur = String(m.text || '');
        if (cur.indexOf(text) >= 0) return m;   // a deferred withNotes beat us to it
        return { ...m, text: (cur + '\n\n' + text).replace(/\n{3,}/g, '\n\n') };
      }));
      return;
    }
    schedule();
  };
  /* flushNow is the LAST paint this throttle ever makes, and saying so is
     the whole point. Every caller does the same two steps: `flushNow()`,
     then write the finished text — `visibleReply` + `cleanHarmony`, markers
     stripped. But `flush` renders from `raw`, which still has every marker
     in it, so any frame that fires after that write undoes it.

     And one usually is queued: the final tokens schedule a frame, flushNow
     runs synchronously inside the same task, and the queued callback fires
     afterwards. React batches all three writes into one commit, so the
     cleaned text never even paints — the bubble goes straight from
     streaming to raw-markers-and-all.

     Watched live on the CEO, which is the bubble the boss reads most: it
     rendered `[HANDOFF_TO: Nova]` and `[ACK: completed: …]` verbatim,
     directly underneath a strip written to be unconditional for exactly
     this reason. The strip ran every time; its result was overwritten every
     time. Whether it survives depends only on whether the last token
     happened to land in an earlier frame, which is why a slow remote model
     hides it and a fast local one shows it every run.

     The abort path already knew: it calls `cancel()` and its comment says
     a queued frame "would fire AFTER this rewrite and overwrite" it. Only
     the success path was left holding the same open door. Ending the
     throttle here closes it, and `note()` already does the right thing
     once cancelled — it APPENDS to whatever the caller wrote instead of
     re-rendering from `raw`, which is the behaviour its own comment asks
     for. Every call site is immediately after an awaited stream, so there
     is no caller left expecting to paint again. */
  ontok.flushNow = () => { flush(); cancelled = true; };
  ontok.cancel = () => { cancelled = true; };
  ontok.raw = () => raw;
  /* The note has to be carried by whoever writes last, and on three paths
     that is NOT this throttle.

     The comment above says flushNow is "the LAST paint this throttle ever
     makes", and it is — but it is not the last paint the BUBBLE gets. The
     dispatch paths do `flushNow()`, then `cancel()`, then one more
     `setChat` of their own with the finished text, computed from `buf`
     alone. `suffix` is not in `buf`. So the office's note was painted by
     flushNow and wiped by the very next write, every time, on the three
     busiest routes in the app: @mention, delegate, and a task dropped on a
     desk.

     Measured on a fresh office (port 9249, one hire, a brain that answers
     with two harmony tool calls and no prose). agentStream reached the
     `!cleaned.trim()` branch and emitted the note; `flush.note` stored it;
     the stored message came out as the raw buffer with no note attached,
     and the boss got a coworker who had said nothing and an office that
     said nothing about it either. The two sentences added in this commit
     were correct and unreachable.

     This is the same shape as the bug flushNow was written to fix, one
     step further along the chain — a later write recomputing from the
     unstripped source and undoing the considered one. The fix there was to
     end the throttle; ending it is not enough when the caller writes
     again. So the caller's text goes through here, and the two halves stay
     together no matter which of them is written last.

     A pure function on purpose: the sites differ (one deletes the message
     instead of writing it, one picks between the coworker's words and the
     office's), and a `seal(text)` that owned the setChat could not serve
     all three. This composes with any write shape. */
  ontok.withNotes = (text) => {
    if (!suffix) return text;
    return (String(text || '').trimEnd() + suffix).trim().replace(/\n{3,}/g, '\n\n');
  };
  return ontok;
}

/* Find a [NEEDS_APPROVAL: ...] marker in agent/CEO output. Returns the
   description string (without the wrapping), or null. Tolerant of
   bracket/case/whitespace variations. */
function extractApproval(text) {
  if (!text) return null;
  /* Masked, like every other "did they actually do this" reader: a stamp a
     coworker CONSIDERED asking for, inside its own reasoning, must not put
     a card on the boss's desk. Applied at the four extractors rather than
     at their ten call sites — the rule belongs to the question, not to
     each place that asks it. See maskReasoning. */
  const m = maskReasoning(text).match(/\[\s*NEEDS[_ ]APPROVAL\s*:\s*([^\]\n]+)\]/i);
  if (!m) return null;
  const desc = m[1].trim();
  /* A stamp is a DECISION, and a decision has to say what is being decided.
     Watched live: a coworker emitted [NEEDS_APPROVAL: N/A] alongside an
     unrelated DM, and the boss's tray read "N/A · by Gemma · awaiting
     stamp" — an authorisation request with no content, which is worse than
     no request at all because the only safe answer to it is no.

     Read it as what it is: the model filling the slot to say "nothing to
     approve here". Dropping it is not a silent drop — nobody asked for
     anything. Inventing a pending authorisation out of it would be the
     approval-shaped version of fabricatedRelay(). */
  /* Two guards, and they genuinely divide the work — checked by removing
     each alone: the word list is what catches "none needed" and "tbd"
     (long enough to pass a length test), the length floor is what catches
     "N/A", "-" and "..." (too short to be worth listing exhaustively).
     Neither is redundant. */
  if (/^(?:none(?:\s+needed)?|nil|null|not applicable|tbd|to be decided)\.?$/i.test(desc)) return null;
  if (desc.replace(/[^A-Za-z0-9]/g, '').length < 3) return null;   // "N/A", "-", "…", "??"
  return desc;
}

/* The work being stamped, sized for the approval tray's <pre>.

   The tray renders `detail` under a comment stating the rule exactly:
   the title is the REQUESTER's summary of its own request, and the gate
   exists so the boss can see both. For the commonest approval in the
   product — the stamp on a finished deliverable — nothing was ever passed
   to it. Watched end to end in a virgin office: a coworker researched a
   brief, filed it to the cabinet, and asked for a stamp, and the card read

       Research brief on pros and cons of remote work for a small team
       by Llama · awaiting stamp                      [APPROVE] [REJECT]

   That title is not a description written by the office. It is the string
   `extractApproval` lifted out of the coworker's own [NEEDS_APPROVAL: …]
   marker — the requester grading its own homework. The brief itself was
   in scope at every call site, and every one of them handed it to the
   activity feed's detail and not to the card where the decision is made.

   Truncation is announced: silently showing the first 1200 characters of
   a longer piece would swap one false impression for another. */
function approvalBody(text, limit = 1200) {
  const s = String(text || '').trim();
  if (!s) return '';
  return s.length <= limit ? s
    : s.slice(0, limit).trimEnd() + '\n\n… shortened for this card.';
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
  text = maskReasoning(text);   // see extractApproval
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
/* `[^\]]*` for the trailing detail stopped at the FIRST `]`, which a real
   reply beat by nesting markers inside the ACK:

     [ACK: completed: • [BROWSER_FETCH: …/Primary_color] • [MEMORY_READ: …]]

   That removed everything up to the first inner `]` and left
   " • [MEMORY_READ: …]]" sitting mid-line — where ORPHAN_TAG_RE, which is
   line-anchored, could never reach it. Allowing one level of nesting covers
   the shape models actually emit (a list of the calls they made) without
   turning this into a full bracket matcher. */
function stripAcks(text) {
  return String(text || '')
    .replace(/\[\s*ACK\s*:\s*[a-z_]+\s*(?::\s*(?:[^\[\]]|\[[^\[\]]*\])*)?\]\s*/gi, '');
}

/* The reply as the BOSS should see it — protocol markers gone.

   Two ways this went wrong, both caught by driving a real successful run
   against a small local model (which emits bare ACKs far more readily than
   a large one, so a session of failure-only testing never saw either):

   - The task-dispatch path stripped nothing at all. `[ACK: in_progress: …]`
     went straight into the chat bubble AND was stored as the task's
     `result` — the deliverable the boss opens was scaffolding.
   - The chat path stripped, then fell back with `cleaned || m.text`. When
     the whole reply IS one ACK, `cleaned` is '' and the fallback restored
     the raw bracket — the exact thing stripping exists to prevent.

   A bare ACK still carries the agent's own note, which is real information
   they wrote, so use it. Only when there is nothing at all do we say so
   plainly, rather than showing an empty bubble or a bracket. */
/* Orphaned protocol tags — an opener whose block never closed.

   Every strip in this file is conditional on a WELL-FORMED match, which is
   fine for a model that closes its blocks and useless for one that doesn't.
   Observed live: an 8B local model emitted `[DM_TO: Claude]` with no
   `[/DM_TO]`, so `extractDM` didn't match, nothing stripped it, and the
   opener went to the boss as if it were prose.

   Deliberately narrow: only this file's own marker vocabulary, only when
   the tag stands alone on its line. An agent writing about `[DM_TO: …]` in
   the middle of a sentence keeps it — we remove scaffolding, not content. */
/* The EXECUTED tools belong here too. A model that calls one emits its
   invocation line, the runtime runs it, and the office appends the visit
   — so the kept record carried the same call twice, once as the coworker's
   raw syntax and once as the office's own line. Measured: a stored task
   result read

     I will use the BROWSER_FETCH tool to fetch a webpage…
     [BROWSER_FETCH: https://en.wikipedia.org/wiki/Primary_color]
     🌐 Read en.wikipedia.org/wiki/Primary_color
     …

   Same watching-vs-keeping split as the tool echo (§3.6): the live
   transcript still shows the coworker's literal output, because that is
   what watching someone work looks like. What gets KEPT — task result,
   journal, `recent`, filed note — is the record, and an invocation line is
   scaffolding in it.

   Still whole-line only: the memo above also contained "I will use
   [MEMORY_READ: decisions/buildings.md] to check…", a marker INSIDE a
   sentence. Removing that would leave a broken sentence, so it stays; the
   model narrating its own tooling is a prompt problem, not a strip one. */
/* Anchored at line START, and consuming the rest of the line ONLY when
   what follows the bracket is the registry's own doc-string echo — never
   for a model's genuine continuation.
   It used to require the marker to be the whole line (`\s*$`), which the
   models defeated by copying the tool's own documentation after it.
   Measured twice on the @mention route, the cure three failure notes tell
   the boss to use:

     [BROWSER_FETCH: https://en.wikipedia.org/wiki/Lime] — fetch a URL and
     return its readable text content.

   The tool RAN — the visit block underneath says so — so the line is
   redundant scaffolding, and the trailing words are the registry's own doc
   string echoed back.

   But "consume to end of line" is too blunt: a coworker whose reply is
   `[MEMORY_READ: decisions/banana.md]I do see that 'banana' was a result
   from a previous task.` — genuine prose, no newline before it — had that
   prose eaten by the same rule, leaving `cleaned` empty, which tripped
   visibleReply's own "nothing survived, show the raw text" fallback and
   put the raw marker back in front of the boss (worse: filed verbatim
   into the delivered .md, a permanent record, not a bubble that scrolls
   away). Root-caused with a minimal node harness against the real,
   unmodified regex — one inserted `\n` was the entire difference between
   correct and broken.

   Every `doc:` string in TOOL_REGISTRY below uses the exact same
   separator to introduce its human-readable half: `] — <description>`
   (bracket, space, em dash, space) — never anything else, and never
   omitted. That is the one place this line-opening machine syntax reads
   like natural English, so it is the one place it's safe to key on: text
   starting with an em dash right after the bracket is the doc string
   coming back, everything else is the coworker's own words. Consume the
   line ONLY in that case; otherwise stop at the bracket and leave
   whatever follows untouched.

   The line-START anchor is what keeps this safe, and the suite already
   pins it: "Use [DM_TO: Mika] to reach someone." has prose BEFORE the
   marker, so it is a coworker explaining and survives untouched. A line
   that OPENS with a protocol marker is machine syntax by construction.

   ── and a line that ENDS with one is too ──────────────────────────────
   "Prose before it means the coworker is explaining" was half a rule, and
   `stripBlocks` two hundred lines down had the other half — "a marker the
   model meant as an instruction ends the line, one it is talking about has
   a sentence after it". Read together they agree: the marker is machine
   syntax unless there is prose on BOTH sides of it. Read apart, each door
   let through exactly what the other would have caught, and the shape that
   satisfies neither anchor walked past both. Measured live against a canned
   brain, one task, and the office filed this into the cabinet:

     I checked the vendor list [VAULT_READ: Research/vendors.md]
     B wins on cost, so B is the one to go with.
     ---
     **Working**
     - Opened Research/vendors.md in the cabinet
     - `Research/vendors.md` is named above, but nothing was written to
       the cabinet on this run — this sheet is the only file it produced.

   Three claims about one act, disagreeing. The tool RAN — `re` in
   TOOL_REGISTRY is unanchored, so a marker behind prose executes exactly
   like one at line start — and the footer already reports it in English on
   the line above. That is §6's banned row ("tool call → shown as the action
   itself") reappearing one space to the right of where it was fixed. The
   footer's second line went with it: that one reads the CLEANED body, so the
   leaked path was warning the boss about a file the office had just opened.
   The same sentence in the chat bubble and the stored result survived this
   fix for a while — `honestyNotes` read the RAW buffer — until #87 pointed
   its two surface-claim guards at `shownBody`, the same text the bubble
   shows. The marker guards still read raw; see the note in honestyNotes.

   So the second branch below: any prose, then the marker, then the end of
   the line. `Use [DM_TO: Mika] to reach someone.` is still untouched — it
   has a sentence after the bracket, which is the discriminator both halves
   of the rule always agreed on.

   No em-dash trailer on that branch, deliberately. On the line-START branch
   `] — <description>` is the registry's own doc string coming back. Behind
   prose it is likelier to be the coworker's sentence continuing, and eating
   a real clause is the worse error of the two. */
const ORPHAN_TAG_NAMES =
  'DM_TO|TASK_DONE|TASK_PROGRESS|TASK_BLOCKED|HANDOFF_TO|HANDOFF|NEEDS[_ ]APPROVAL|' +
  'REQUEST_ELEVATION|SPAWN_SUBAGENT|HIRE_AGENT|HIRE_ASSISTANT|SEARCH|VAULT_SEARCH|' +
  'VAULT_READ|VAULT_NEW|VAULT_APPEND|MEMORY_LIST|MEMORY_READ|MEMORY_WRITE|' +
  'MEMORY_APPEND|FILE_READ|FILE_WRITE|DIR_LIST|BASH|BROWSER_FETCH|' +
  'BROWSER_SCREENSHOT|EXPORT_PPTX|EXPORT_DOCX|EXPORT_PDF|GENERATE_IMAGE|GENERATE_VIDEO|' +
  /* These four were never in this list at all — not behind prose, not at
     line start either. Every one of them EXECUTES and then prints its own
     machine syntax to the boss. Found by the coverage check in
     scripts/test_a_marker_behind_prose.py, which reads the names out of
     TOOL_REGISTRY rather than trusting this string, on its first run. That
     is the #79 remedy doing its job: broaden what the sweep recognises AND
     keep an assertion that names the authority, because the enumerated list
     is always the half that goes stale. */
  'PUBLISH_SITE|PEER_JOURNAL|WALLET_BALANCE|WALLET_SEND';
/* One core, two anchorings. Written as a shared string rather than two
   literals because a thirty-name vocabulary copied twice is a vocabulary
   that drifts — the same hazard that left HANDOFF_TO and HIRE_ASSISTANT out
   of this list entirely while `stripBlocks` carried them. */
const ORPHAN_TAG_CORE = '\\[\\s*\\/?\\s*(?:' + ORPHAN_TAG_NAMES + ')\\b[^\\]\\n]*\\]';
const ORPHAN_TAG_RE = new RegExp(
  '^[ \\t]*' + ORPHAN_TAG_CORE + '[ \\t]*(?:\u2014[^\\n]*)?'
  + '|[ \\t]*' + ORPHAN_TAG_CORE + '[ \\t]*$', 'gim');

/* The header line above a tool result in the live transcript.

   Was `📡 MEMORY_READ("facts/france.md") →` — §6's table bans exactly that
   ("tool call → shown as the action itself"), and the row below it in the
   same bubble was the model's own raw `[MEMORY_READ: facts/france.md]`, so
   the boss read the same call twice, in machine syntax both times.

   Now `📁 Opened facts/france.md`, from the one floor vocabulary that also
   writes the desk bubble, the activity row and the filed note. The RESULT
   underneath is untouched — that is the work, and watching it arrive is
   the point of showing the visit at all. A visit with no argument keeps a
   bare verb rather than inventing a subject. */
function toolEchoHead(name, arg) {
  const w = visitWords(name);
  const line = visitLine(name, arg, 'past', 60) || visitPlace(name, 'past');
  return `${w.icon} ${line}`;
}

/* `/vault/list` returns records — `{path, title, mtime, size}` — and every
   consumer in the app reads `f.path`. The two MEMORY_* sites below read the
   entries as plain strings and called `.startsWith` on them, so:

     · [MEMORY_LIST] threw `d.startsWith is not a function` on every call;
     · memorySummary() threw the same inside a try/catch that swallowed it,
       so `agentMemoryNote` was ALWAYS empty and no coworker was ever told
       what was in its own memory folder.

   That is the whole private-memory feature dead, silently, and it stayed
   hidden because the thrown message was buried in the tool echo spliced
   into a chat bubble. It surfaced the moment a visit became its own
   rendered element with the result on its own line — which is the argument
   for that change, restated as a bug.

   Tolerates both shapes: a record, or a bare string from any older path. */
function vaultPaths(list) {
  return (list || [])
    .map(f => (f && typeof f === 'object') ? String(f.path || '') : String(f || ''))
    .filter(Boolean);
}

/* The office labels peer turns as `[Name · Role]: …` when it builds the
   model's context (chatToMessages, below) so a coworker can tell who said
   what. Small models read that shape as house style and type it back at the
   top of their own reply — seen verbatim:

     [Llama · Generalist]: [MEMORY_WRITE: notes/figs.md]

   which is worse than noise: it shoves the marker off column zero, and
   ORPHAN_TAG_RE is line-anchored on purpose, so the strip that would have
   removed the marker no longer matches. One echoed label defeats the
   cleaner for the whole line.

   The bubble is already captioned with the speaker, so a coworker naming
   themselves inside it is redundant even when harmless.

   Deliberately keyed on the ` · ` separator rather than "a leading bracket":
   that is the office's own `${name} · ${role}` template and nothing else
   emits it, so a markdown reference definition (`[1]: http://…`), a
   checkbox, or a real tool marker cannot match. Start of text only — a
   mid-reply quotation of someone else stays. */
function stripSelfLabel(text, selfName) {
  let out = String(text || '');
  /* When the office knows WHO is replying it can do better than "first line
     only". A label naming somebody else is content — a coworker quoting what
     Mika said. A label naming the SPEAKER is never content, wherever it
     lands, because a person does not announce themselves mid-sentence.

     A real task delivery made the difference concrete. Asked for one fruit,
     Llama filed:

       The boss likes figs.

       [Llama · Generalist]: Grape.

     — a stale line from earlier context, then its own label, then the actual
     answer. Anchored at the start of TEXT the label survived; anchored at
     the start of a LINE, with the speaker's own name required, it goes and
     "Grape." is what the boss reads. */
  const self = String(selfName || '').trim();
  if (self) {
    const esc = self.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    out = out.replace(new RegExp('^[ \\t]*\\[\\s*' + esc + '[^\\]\\n]*\\]\\s*:[ \\t]*', 'gim'), '');
  }
  /* Fallback for callers that cannot name the speaker: the office's own
     `${name} · ${role}` template at the very start of the reply. */
  return out.replace(/^\s*\[[^\]\n]*\s·\s[^\]\n]*\]\s*:\s*/, '');
}

function stripOrphanTags(text) {
  return String(text || '').replace(ORPHAN_TAG_RE, '');
}

/* ORPHAN_TAG_RE is whole-line, which is right for the one-line markers but
   wrong for the 16 BLOCK-form ones, because those carry a payload between
   two delimiters. Stripping both delimiters and keeping what they wrapped is
   the worst of the three options — the office looked like it had cleaned up
   after the coworker while leaving the machinery on the floor.

   Seen on the real transcript: the boss asked for one colour and got

     <content>
     Local file access is required for reading the file.

   the body of a [MEMORY_WRITE: projects/local_file_access.md] block whose
   opening and closing tags had both been tidied away above and below it. The
   note itself had already been written — this was a second, unasked-for copy
   of it pasted into the conversation.

   Closed blocks only, for the PAYLOAD. An UNCLOSED one never parsed, so its
   tool never ran, and stripping to end-of-text on a missing closer would
   also eat whatever real answer came after it. Same 16 names the comment on
   unsentBlocks enumerates, plus the ORPHAN list's `HANDOFF` spelling
   alongside `HANDOFF_TO`.

   The lone OPENER is a different question from its payload, and keeping it
   was wrong. Measured on the first-run path, on the very first deliverable
   a new boss ever receives: Llama answered a Research brief with

     **Vault Path:** [VAULT_NEW: Research/sourdough_starter.md]

     Sourdough bread needs a starter because…

   and that line went into the filed .md in the cabinet — a kept file
   asserting a vault path that does not exist and was never written.
   ORPHAN_TAG_RE would have caught it, but it is whole-line by design and
   this marker sat mid-line behind a label the model invented.

   So: remove the unclosed opener TAG, never the text after it. That keeps
   the reason the original rule existed (the real answer survives) and drops
   the part that lies. `unsentBlocks` is unaffected — every caller runs it on
   the RAW buffer, not on this output, so the honest "no file reached the
   cabinet" note still fires from the same opener this now hides.

   The name list lives INSIDE the function for the same reason unsentBlocks'
   does: scripts/test_reply_hygiene.py lifts named functions out of this file
   to run under node, and a module-level const beside one is invisible to it.
   Written as a const first, which cost a red suite to remember. */
function stripBlocks(text) {
  const NAMES = 'DM_TO|HANDOFF_TO|HANDOFF|HIRE_AGENT|HIRE_ASSISTANT|REQUEST_ELEVATION|' +
    'SPAWN_SUBAGENT|VAULT_NEW|VAULT_APPEND|MEMORY_WRITE|MEMORY_APPEND|FILE_WRITE|' +
    'EXPORT_PPTX|EXPORT_DOCX|EXPORT_PDF|GENERATE_IMAGE|GENERATE_VIDEO';
  const re = new RegExp(
    '\\[\\s*(' + NAMES + ')\\s*:[^\\]\\n]*\\][\\s\\S]*?\\[\\s*\\/\\s*\\1\\s*\\]', 'gi');
  /* Closed blocks and their payload go first. Whatever opener survives that
     pass had no closer, so its tool never ran: drop the tag, keep the line.

     Anchored to END OF LINE, and that anchor is the whole rule. A first cut
     stripped the tag anywhere and broke a case that was already in the
     suite — `Use [DM_TO: Mika] to reach someone.` is a coworker EXPLAINING
     the marker, and eating it there turns an explanation into "Use  to
     reach someone." The two forms are told apart by what follows on the
     line: a marker the model meant as an instruction ends the line, one it
     is talking about has a sentence after it. */
  /* Consumes a short LABEL immediately before the marker on the same line.
     Removing the marker alone left the label dangling, and it showed up in
     five filed deliverables as

       **Vault Path:**

     with nothing after it — a heading for a value the office had just
     deleted. That residue is not the model's prose to leave alone; it is
     litter from this function's own cut, and cleaning up after yourself is
     not guessing at sentences.

     Bounded hard: the label must be short, end in a colon, and sit
     immediately before a marker that is itself being removed. A label
     followed by real content is untouched, because the marker regex will
     not match there. */
  /* LEAD also allows a markdown list marker, because the reply that made
     this necessary was a coworker being tidy:

       Saved. Here is what I did:

       - **Vault Path:** [VAULT_NEW: Notes/sourdough.md]
       - [MEMORY_WRITE: the boss bakes sourdough on weekends]

     Both lines reached the boss verbatim — on the task card, in chat, and
     inside the filed cabinet sheet. A bullet is not the model's prose any
     more than the label is; it is the wrapper the marker arrived in, and a
     bullet whose whole content was machine syntax is a bullet with nothing
     in it. Same litter rule, one line further out. */
  const LEAD = '^[ \\t]*(?:[-*+\u2022]|\\d{1,2}[.)])?[ \\t]*';
  const LABEL = '(?:\\*{0,2}[\\w ][\\w \\-]{0,22}:\\*{0,2}[ \\t]*)?';
  const lone = new RegExp(
    LEAD + LABEL + '\\[\\s*(' + NAMES + ')\\s*:[^\\]\\n]*\\][ \\t]*(?=\\n|$)',
    'gim');
  /* Third pass: the opener whose BRACKET never closed.

     Both passes above need a `]` to match, and so does ORPHAN_TAG_RE, so a
     marker that never closed its bracket walked through all three. Measured
     end to end against a canned brain, one task, reply exactly:

       [VAULT_NEW: Notes/scratch.md

     The board went green. The stored deliverable was that string. The office
     then FILED it, and the boss's cabinet gained
     `Deliveries/save-a-note-about-sourdough-to-the-vault.md` whose entire
     body — between the title and the Working footer — is a broken machine
     marker. And because filing succeeded, the task path passed VAULT_NEW in
     `skipKinds`, so the one guard that would have said "no file reached the
     cabinet" stayed quiet: the office suppressed its own warning on the
     strength of having filed the warning's subject.

     One missing `]`, four surfaces wrong, and the deepest of them is a file
     in the cabinet that the boss will open in a month. Fixing it here fixes
     all four, because the other three all read what this returns.

     WHOLE-LINE, which is the same bound ORPHAN_TAG_RE chose and for the same
     reason. The `lone` pass above can afford to be looser because a closed
     bracket is already strong evidence of intent; with no `]` at all, the
     text is likelier to be prose that happens to mention a marker. So the
     line must OPEN with the marker (a label ahead of it aside, same litter
     rule as above) and reach end-of-line without ever closing — which is
     what `[^\]\n]*$` says. `Use [DM_TO: Mika] to reach someone.` is
     untouched, having both a `]` and prose before the bracket. */
  const broken = new RegExp(LEAD + LABEL + '\\[\\s*(' + NAMES + ')\\s*:[^\\]\\n]*$',
    'gim');
  /* Fourth pass, and the reason the other two needed rewriting.
     `LABEL` is written as an optional group, but it sits directly behind a
     `^` anchor, so optional is exactly what it is not: when the label runs
     one word past the 22-char bound, the group declines to match, the
     anchor then demands a `[` where prose is, and the whole match fails.
     The pass does not fall back to removing just the marker — it removes
     NOTHING. So a bound written to decide "should the label go too?"
     silently answered a different question, "should the boss see machine
     syntax?", and answered it yes:

       **Here is the vault path for you:** [VAULT_NEW: Notes/a.md]

     That is backwards. Failing to recognise the wrapper is not permission
     to publish the contents. The two decisions are separate and only one
     of them is a judgement call: the marker is machine syntax and always
     goes, and how much of the surrounding text goes with it is where a
     bound belongs.

     So this pass strips the marker alone, after a colon of any length,
     keeping everything the model wrote. It leaves a dangling `:` on a long
     label, which is the litter the `lone` bound was avoiding — accepted,
     because the alternative is eating a real sentence. `I saved your notes
     and the path is here:` is worth more to the boss than tidiness, and
     unlike the raw marker it cannot be mistaken for something the office
     did. Anchored to end of line and to a colon immediately before the
     bracket, so `Use [DM_TO: Mika] to reach someone.` and `Meet at 10:30`
     are both untouched. */
  const residue = new RegExp(
    '(:\\*{0,2})[ \\t]*\\[\\s*(?:' + NAMES + ')\\s*:[^\\]\\n]*(?:\\][ \\t]*)?$',
    'gim');
  /* No fifth pass here, and the absence is the point.
     `Filed it [VAULT_NEW: Research/x.md]` — prose, marker, end of line — has
     no colon, no bullet and no label, so all four passes above decline it,
     and that is the leak #81 measured. The obvious fix is a pass right here
     that strips a trailing marker whatever sits before it. Written, and then
     removed: `ORPHAN_TAG_RE` now carries exactly that rule, this function's
     entire NAMES list is a strict subset of that vocabulary, and the only
     caller of stripBlocks runs stripOrphanTags over its output. Two passes
     implementing one rule is the shape of the defect, not a fix for it — it
     is what let the line-start half and the end-of-line half disagree for as
     long as they did. So the trailing form is owned in one place, and this
     function keeps the job only it can do: closed blocks and their payload,
     the wrapper litter, and the opener whose bracket never closed. */
  return String(text || '').replace(re, '').replace(lone, '')
    .replace(broken, '').replace(residue, '$1');
}

/* ── A handoff that never left the building ───────────────────────────────
   Caught driving the first real two-coworker run: Llama replied

     • Blue is a primary color. [DM_TO: Mika] Can you provide your
       perspective on this request?

   written INLINE — no newline, no closing `[/DM_TO]`. The parser requires
   the documented block form, so it never matched, was never dispatched, and
   sat in the boss's chat as raw syntax. To the boss that reads as a handoff
   that was sent. Nothing was.

   The parser stays strict on purpose: a loose one would fire on prose that
   merely mentions the marker. What was missing is that the office KNOWS —
   it can see an opening DM_TO in the reply while its delivery queue came
   back empty. Same shape as `placeholderRefusal`: an unactioned request
   that says nothing invites a false belief.

   Deliberately conservative. If ANYTHING was delivered this run we say
   nothing, so a well-formed handoff alongside a malformed one is missed
   rather than risking a false alarm on a run that really did delegate. */
/* `selfName` is the coworker who is SPEAKING, and it exists because of a
   note the office printed at a boss who had done nothing wrong. Asked Nova
   a plain question, Nova answered it and also emitted `[DM_TO: Nova]` —
   addressed to itself, empty body, no closing tag. The office skipped it,
   which is right; nothing should be delivered. Then this fired:

     the handoff to Nova didn't go out … ask them yourself with @Nova

   The boss HAD just asked Nova, in that exact bubble. The sentence invents
   a third person, and its one piece of advice is the thing already done.
   Nothing failed to reach anybody here: a coworker talking to itself has
   no recipient left waiting, which is the entire premise of this guard.

   Surfaced the moment the honesty guards started running on the @mention
   path at all (they had been reading an empty string — see the note on
   `rawReply` in app.jsx). Un-deadening a guard means meeting the cases it
   never got to be wrong about.

   A self-addressed marker does not hide a real one: every DM_TO in the
   reply is checked and the first with someone ELSE'S name still reports. */
/* `roster` is what makes the last clause of this sentence true.

   It suggested `@${who.split(/\s+/)[0]}` — the first word of the name. For
   "Nova" that is "Nova"; for a coworker called "Local Brain" it is "@Local",
   which is nobody. Measured end to end: the guard printed "ask them yourself
   with @Local", the boss typed exactly that, and the CEO answered instead.
   A way forward that leads somewhere else is the failure this file has
   already recorded twice — a note whose one piece of advice does not work
   costs more than no note, because the boss spends the try.

   With the roster in hand the name is resolved to the one the office
   actually knows, and mentions now carry spaces (see extractAllMentions),
   so the full name is a working instruction. Off-roster names keep the
   first-word form: a model that emits `[DM_TO: Nova, the researcher]` has
   named nobody, and "@Nova" is the better guess to hand the boss. */
function unsentHandoff(text, deliveredCount, selfName, roster) {
  if (deliveredCount > 0) return null;
  const me = String(selfName || '').trim().toLowerCase();
  const team = (roster || []).map(n => String(n || '').trim()).filter(Boolean);
  const re = /\[\s*DM_TO\s*:\s*([^\]\n]+)\]/gi;
  let m;
  while ((m = re.exec(String(text || '')))) {
    const who = String(m[1]).trim().slice(0, 40);
    if (me && who.toLowerCase() === me) continue;
    // The way forward has to be typeable, or it is just a shrug with a
    // name in it. Three things can be inside a DM_TO the model wrote by
    // hand: the exact roster name; a short form of it ("Local" for
    // "Local Brain"); or a name with prose stuck to it ("Nova, the
    // researcher"). Prefer the roster spelling, since that is the one the
    // mention parser resolves. Otherwise take the leading run of
    // name characters — "@Nova," is nobody, and neither is the whole
    // sentence. If nothing survives that, say so rather than inventing a
    // handle the boss will type into an empty room.
    const lc = who.toLowerCase();
    const known = team.find(n => n.toLowerCase() === lc)
      || team.find(n => n.toLowerCase().startsWith(lc + ' '));
    const how = known || (who.match(/^[A-Za-z][A-Za-z0-9_-]*/) || [''])[0];
    const lead = `_(the handoff to ${who} didn't go out — they started the message and stopped partway. Nothing was sent;`;
    return how
      ? `${lead} ask them yourself with @${how}.)_`
      : `${lead} and no name in it was clear enough to route — send it again yourself.)_`;
  }
  return null;
}

/* The worst one found so far, and the first clean data point after the
   delegate bug was fixed. The boss asked Nova, in plain words and without
   naming any protocol: "Find out from Llama what colour a ripe lemon is,
   then tell me their answer." Nova sent nothing -- no DM_TO, no dispatch,
   zero child messages -- and replied:

     [Llama \u2192 Nova]:
     - A ripe lemon is typically yellow.

   `X \u2192 Y` is the office's OWN label: app.jsx sets it as the speaker
   name on a relayed bubble. So this is not a coworker describing a
   conversation in prose, which would be uncheckable and none of the
   office's business. It is a coworker writing the office's own record
   format around words it invented, and presenting a colleague as having
   said them.

   That lands on the checkable side of the boundary: the office knows how
   many messages it delivered this run, and if the answer is none, a relay
   label naming two hired coworkers is false.

   Conservative in the same three ways as its siblings: silent if anything
   was delivered, silent unless BOTH names are on the roster, and it takes
   the roster as DATA rather than pattern-matching names out of prose. */
function fabricatedRelay(text, deliveredCount, names) {
  if (deliveredCount > 0) return null;
  const roster = (Array.isArray(names) ? names : [])
    .map(n => String(n || '').trim().toLowerCase()).filter(Boolean);
  if (roster.length < 2) return null;
  const re = /\[\s*([^\]\n\u2192]{1,40}?)\s*\u2192\s*([^\]\n]{1,40}?)\s*\]\s*:/g;
  let m;
  while ((m = re.exec(String(text || '')))) {
    const from = m[1].trim().toLowerCase();
    const to = m[2].trim().toLowerCase();
    if (roster.includes(from) && roster.includes(to)) {
      const who = m[1].trim().slice(0, 40);
      return `_(that reply is written as though ${who} had answered, but nothing was sent to them and they never ran. Those words are not ${who}'s. Ask them yourself with @${who.split(/\s+/)[0]}.)_`;
    }
  }
  return null;
}

/* The gap `unsentHandoff` cannot see, found by driving two local coworkers
   on 2026-08-07 and failing to produce a handoff twice.

   Attempt one: Llama replied "Nova, can you name one colour of a ripe
   lemon?" — plain prose, no marker at all. Attempt two, after being told
   explicitly to use the block: it emitted an ACK reading
   `asked Nova about lemon color` and still sent nothing.

   `unsentHandoff` needs an OPENING MARKER to notice, and there was none
   either time, so it stayed silent — correctly, by its own rule. But in
   the second case the office holds a structured contradiction it can prove
   without reading a word of prose: the coworker declared the state
   `awaiting_reply` — "I have asked someone and I'm waiting" — while the
   delivery queue came back empty. A state the model CHOSE from a fixed set
   is not prose; it is a claim in the office's own vocabulary, and this one
   is false.

   Same conservatism as its sibling: silent if anything was delivered, and
   silent unless the coworker actually declared the wait. Prose that merely
   mentions a teammate is left alone — that is a sentence, not a claim, and
   guessing at sentences is the thing this file refuses to do.

   Takes the ACK STATES rather than the raw text so it cannot be fooled by
   the word appearing in a reply, and so the harness can drive it. */
function unsentAsk(ackStates, deliveredCount) {
  if (deliveredCount > 0) return null;
  const arr = Array.isArray(ackStates) ? ackStates : [];
  if (!arr.some(s => String(s || '').trim() === 'awaiting_reply')) return null;
  return '_(they marked this as waiting on a teammate, but nothing was sent and nobody has picked it up. Ask them again, or hand it to someone yourself.)_';
}

/* Same shape as unsentHandoff, for the one marker where silence is worst.
   [REQUEST_ELEVATION] only parses in its BLOCK form — opening tag, a line of
   detail, closing tag — and a model that writes just the opening line has
   asked for nothing. Driven live: a coworker emitted
   "[REQUEST_ELEVATION: need to read a local file]" on its own, the parser
   correctly ignored it, and the boss was left reading a sentence that says a
   request was made while the approvals tray stayed empty. Both of them then
   wait for the other.

   Deliberately conservative in the same way: if an approval really was
   raised this run, say nothing. `raised` is what the caller actually
   queued, so a well-formed request alongside a malformed one is missed
   rather than risking a false alarm on a run that really did ask. */
function unsentElevation(text, raised) {
  if (raised) return null;
  const t = String(text || '');
  if (!/\[\s*REQUEST_ELEVATION\s*:/i.test(t)) return null;
  if (/\[\s*\/\s*REQUEST_ELEVATION\s*\]/i.test(t)) return null;   // well-formed
  return '_(that request for file and shell access never reached you — they started writing it out and stopped partway. Nothing is waiting in your approvals; ask them to try again, or grant it yourself in Settings → Roster.)_';
}

/* The rest of the "request that leaves someone waiting" class.
   DM_TO and REQUEST_ELEVATION each got a bespoke guard after being caught in
   the wild; sweeping the registry showed four more with the same
   consequence — a coworker believes they asked for something, and nobody
   is coming.

   The WRITE markers used to be deliberately excluded, on the argument that
   a failed parse means the tool never ran and "the office already has an
   honest record of that: no visit block". Watching a real run retired that
   argument. Asked to save a note, Llama replied:

     [MEMORY_WRITE: notes/citrus.md]
     The boss likes lemons.
     [ACK: completed: • saved note on citrus preferences]

   — no closing tag, so nothing was written, while the coworker's own ACK
   announced success. An ABSENT visit block is not a record a person reads;
   it is the lack of one, and it loses every time against an explicit claim
   to the contrary. Three runs, three confident claims, zero files on disk.

   So write-class is guarded too now, with one difference in the wording:
   nobody is left waiting for a hire, but the boss is left believing a note
   exists. The sentence has to contradict the claim, not just describe a
   parse failure.

   The arithmetic, so a reader can check it rather than trust it:
   16 block-form markers = 6 request-class (DM_TO, HANDOFF_TO, HIRE_AGENT,
   HIRE_ASSISTANT, REQUEST_ELEVATION, SPAWN_SUBAGENT — all guarded now) +
   10 write-class (VAULT_NEW, VAULT_APPEND, MEMORY_WRITE, MEMORY_APPEND,
   FILE_WRITE, EXPORT_PPTX/DOCX/PDF, GENERATE_IMAGE/VIDEO — all guarded
   now). The commit that added this said 13; that was a miscount off a
   printed list, found by re-running the classifier during an audit of my
   own comments.

   Unlike unsentHandoff this needs no "did anything land" flag: a marker
   opened with no closing tag of its own is proof THAT ONE did not parse,
   whatever else in the reply did.

   ...with one exception, which is what `skipKinds` is for. On the TASK
   path the office files the deliverable itself (fileDelivery in app.jsx —
   best-effort, exactly so a coworker's own botched filing cannot lose the
   work). Watched live on a VIRGIN office's very first starter task: Llama
   opened a [VAULT_APPEND: with no closer, the office filed the finished
   draft anyway, the FIRST DELIVERY sheet said "filed it in your cabinet",
   the floor log said "filed to Drafts 🗄", the file sat in the Vault with
   the full draft — and this guard appended "nothing was appended in the
   cabinet … Ask them to try again." Three surfaces telling the boss it
   landed, and the honesty note calling all three liars, on the product's
   proudest first-run moment. The note exists to contradict FALSE success
   claims; when the office itself put the deliverable in the cabinet, the
   success is real and the note is the part that lies. So the task path
   passes the two cabinet-write kinds here once filing succeeded; every
   other kind (memory, exports, hires, hand-offs) stays guarded because
   the office does NOT do those on the coworker's behalf. */
function unsentBlocks(text, skipKinds) {
  /* Table lives inside the function: scripts/test_reply_hygiene.py lifts
     named functions out of this file to run them under node, so a
     module-level const beside it is invisible to the harness. */
  /* Every sentence here is written for the boss, so §6 binds it — and §6 is
     what these sentences used to break. Each one diagnosed the failure as
     "it needs a closing tag", "it needs the detail lines", "the message on
     its own line". A closing tag is not a thing in the boss's world. They
     cannot supply one, cannot ask for one, and cannot tell a coworker who
     forgot one from a coworker who is simply not very good.

     Worse than useless, it teaches. The whole office is built so the boss
     never learns there is a marker protocol underneath; these notes are the
     surface that told them, and they told them at the exact moment the boss
     was already being handed bad news. Two ticks ago the raw marker printed
     BESIDE this sentence was removed, on the reasoning that it was showing
     the machine's name for a failure already described in words. The words
     kept the machine's name. Same rule, one layer in.

     What replaced it is not a metaphor, it is the plainer description: an
     opener with no closer IS a coworker who began the write and stopped
     partway. That is true, it is in the office's own vocabulary, and it
     tells the boss the one thing that changes what they do next — the
     coworker meant to do it, so asking again is worth the trouble.

     What did NOT change is the shape §7 requires: the contradiction first,
     because the coworker may have just claimed success and that claim is
     what the boss actually read, and then the way forward. Only the middle
     clause was ever the problem.

     ...except that nine of the fourteen never had the second half. Found by
     writing the test for the first half and letting it check the shape it
     assumed was already there:

       no deck was produced — that export needs a closing tag. Nothing was
       created.

     Full stop. Bad news, jargon, and nothing to do about it. §7 is one
     honest sentence PLUS a way forward, and the honest half on its own is
     the thing the section exists to rule out — it tells the boss the office
     is broken and leaves them holding it. Every note ends with a next step
     now, and the test refuses any that doesn't. */
  const KINDS = [
    ['HIRE_AGENT',      'that request to hire never reached you — they started writing it out and stopped partway. Nothing is waiting in your approvals. Ask them again, or hire someone yourself from an empty desk in the office.'],
    ['HIRE_ASSISTANT',  'that request for an assistant never reached you — they started writing it out and stopped partway. Nothing is waiting in your approvals. Ask them again, or hire someone yourself from an empty desk in the office.'],
    ['SPAWN_SUBAGENT',  'no helper was ever brought in — they started asking for one and stopped partway. Ask them to try again, or hand the job to a coworker yourself.'],
    ['HANDOFF_TO',      'that hand-off never went out — they started the message and stopped partway. Nothing was sent. Ask them again, or @-mention whoever should have it.'],
    /* Write-class. Phrased to contradict the success the coworker may have
       just claimed, because that claim is what the boss actually read. */
    ['MEMORY_WRITE',    'nothing was saved to their memory — they started the note and stopped partway, so it is not there however it was described above. Ask them to save it again.'],
    ['MEMORY_APPEND',   'nothing was added to their memory — they started the note and stopped partway. Ask them to try again.'],
    ['VAULT_NEW',       'no file reached the cabinet — they started filing it and stopped partway, so the Library does not have it. Ask them to file it again.'],
    ['VAULT_APPEND',    'nothing was appended in the cabinet — they started writing and stopped partway. Ask them to try again.'],
    ['FILE_WRITE',      'nothing was written to the workspace — they started the file and stopped partway. The file is unchanged. Ask them to try again.'],
    ['EXPORT_PPTX',     'no deck was produced — they started the export and stopped partway. Nothing was created. Ask them to try again.'],
    ['EXPORT_DOCX',     'no document was produced — they started the export and stopped partway. Nothing was created. Ask them to try again.'],
    ['EXPORT_PDF',      'no PDF was produced — they started the export and stopped partway. Nothing was created. Ask them to try again.'],
    ['GENERATE_IMAGE',  'no image was made — they started it and stopped partway. Nothing was created. Ask them to try again.'],
    ['GENERATE_VIDEO',  'no video was made — they started it and stopped partway. Nothing was created. Ask them to try again.'],
  ];
  const t = String(text || '');
  const skip = Array.isArray(skipKinds) ? skipKinds : [];
  const notes = [];
  for (const [name, why] of KINDS) {
    if (skip.includes(name)) continue;
    const opened = new RegExp('\\[\\s*' + name + '\\s*:', 'i').test(t);
    if (!opened) continue;
    const closed = new RegExp('\\[\\s*\\/\\s*' + name + '\\s*\\]', 'i').test(t);
    if (closed) continue;
    notes.push('_(' + why + ')_');
  }
  return notes.length ? notes.join('\n') : null;
}

/* ── Sources named on a run that opened nothing ───────────────────────────
   `buildDelivery` in app/artifacts.jsx already knows how to say this, and
   says it well: when a delivery's Working record is empty and the prose
   names outside sources, it writes "…nothing was opened or searched while
   it was written — treat those as recalled, not checked" into the filed
   note, directly beneath the claim.

   It says it in exactly one place. Measured on a fresh office, first task,
   local Llama, no search key: the brief came back citing CB Insights,
   Gartner and Clarity, none of them opened. The filed .md carried the
   caveat. The chat bubble the boss reads first did not. The task card they
   open from DONE did not. The activity row's detail did not. Three of the
   four surfaces showed the citations alone, and the one that told the
   truth is the one you have to go looking for.

   So it belongs here instead — this is the function whose whole job is
   being the single copy, and whose own comment records the last two times
   a guard lived on one path out of three. Chat gets it through `flush.note`
   and the activity row through `honesty.join(' ')`, on all three dispatch
   paths, for free.

   `visits` absent is NOT the same as `visits` empty. A path that does not
   count what it opened knows nothing about whether anything was opened,
   and accusing a coworker of inventing sources on that basis is the §7
   failure pointed the other way — the same reason `citesOutside` is
   deliberately narrow. Unknowable means say nothing. */
function unverifiedSources(text, visits, citesFn, workingFn) {
  if (!Array.isArray(visits)) return null;
  if ((workingFn || workingNotes)(visits).length) return null;
  return (citesFn || citesOutside)(text)
    ? '_(this names sources, but nothing was opened or searched while it was written — treat those as recalled, not checked.)_'
    : null;
}

/* ── A filename promised, and no file ─────────────────────────────────────
   Measured on a fresh office, first task, the LAN brain, cabinet configured
   and working. Brief: "Write a 400-word briefing on why sourdough starters
   need feeding, and file it in the vault." The board marked it DONE, and
   the whole deliverable was:

     I will write a 400-word briefing explaining the necessity of feeding
     sourdough starters and save it to the vault under
     `Drafts/Sourdough_Feeding_Briefing.md`.

   A sentence in the future tense, a named file that does not exist, and a
   green DONE over the top of it. The filed sheet carried that line as the
   deliverable and then, eight lines below, its own Working record said
   "Nothing opened, saved or looked up for this one." Both true statements
   about the same run, one of them the office's and correct, and nobody
   connected them.

   The office is NOT asked to decide whether prose is "only an intention" —
   that is judging the writing, and §4 says detection is a hint, not a
   verdict. It is asked something it knows exactly: a path was named, and
   nothing was written to the cabinet on this run. Those two facts are a
   contradiction on their face, the same way a citation dated next year is
   arithmetic rather than an accusation.

   Narrow on purpose, and the narrowness is all in the path shape. It needs
   a folder, a slash and a document extension, so a bare "the vault" or a
   sentence about `Drafts` alone says nothing. A first segment containing a
   dot is excluded, which drops `example.com/report.md` and every other URL
   tail — a coworker naming a page it read is not claiming to have filed it.
   A miss here costs the caveat; a false alarm calls an honest coworker a
   liar, which is the more expensive mistake and the one 6cf5957 was about.

   Silent whenever ANY cabinet write happened, without checking whether the
   written path matches the named one. Two names for one file is a mistake
   the office cannot tell from a coworker filing twice, and this note exists
   for the run that filed nothing at all.

   Silent, too, for a path this run OPENED — see `unwrittenPaths` in
   app/artifacts.jsx, which owns that detection. The office telling the boss
   a file is not there while its own visit log says it read that file is the
   false alarm this whole note is written to avoid, and #82 measured it.

   The detection lives in app/artifacts.jsx, which is where the delivery
   sheet needs the identical answer and which this file already imports from
   — one rule in one place, not two kept in step by hope. That door and this
   one each carried their own copy of it until #82, and both copies had the
   same half-question in them. It comes in as a parameter for the same reason
   `unverifiedSources` takes its two: scripts/test_reply_hygiene.py lifts
   these functions out of this file to run under node, and a lifted function
   that calls an import is a ReferenceError.

   The message says "they never wrote it", not "nothing was written" or "it
   is not there", because that is all the witness saw. The detection reads
   the SPEAKER'S visit log; it cannot see the office's own filing (the task
   path runs fileDelivery AFTER these notes are computed — measured on a
   done card whose artifact row said Deliveries/briefing-status.md two lines
   from a note swearing nothing was written to the cabinet on that run), and
   it cannot see what earlier runs left in the cabinet, so "that file is not
   there" was a guess wearing a verdict's clothes. A note that outclaims its
   witness gets one contradiction on a card, and then every note after it
   reads as machine noise. */
/* A path sitting inside a tool marker is not a prose promise, and this note
   is only ever about a prose promise — see the section head: "a filename
   promised, and no file". `unsentBlocks` above owns the other story, and
   tells it better.

   Measured live (office 8847, first @mention of a hired coworker). Llama
   answered "I've saved a note to start building my memory with
   [MEMORY_WRITE: decisions/intro.md]." — an opener with no closer. The boss
   got both notes, stacked:

     _(nothing was saved to their memory — they started the note and stopped
       partway, so it is not there however it was described above. Ask them
       to save it again.)_
     _(`decisions/intro.md` is named above, but they never wrote it to the
       cabinet on this run — ask them to file it if you need it.)_

   One fact, twice, and the second one wrong twice over. It reads as a
   different failure ("never wrote it" against "started and stopped
   partway"), so a boss counting problems counts two. And it names the
   CABINET for a path that was never headed there: MEMORY_WRITE goes to the
   coworker's own notes folder, which is exactly why app/artifacts.jsx's
   CABINET_WRITE leaves the MEMORY_* markers out — "the coworker's private
   notes folder (Agents/<name>/), not a deliverable for the boss". So the
   closing advice, "ask them to file it if you need it", asks the boss to
   chase a file into a drawer it was never going into.

   Prose wins over the marker when a path is in both: a coworker who writes
   "saved to Research/x.md" AND emits a truncated marker for it has still
   made the claim in the boss's own words, and that claim is what this note
   answers. Only an occurrence with no prose twin is dropped.

   Inlined, not two helpers beside it, for the reason `unsentBlocks` keeps
   its KINDS table inside itself: five suites lift THIS function by name and
   run it under node, so anything it calls from module scope is a
   ReferenceError in every one of them. Written as siblings first, and all
   five went red together — the hazard is documented two functions up and
   still caught me. */
function unfiledPath(text, visits, unwrittenFn) {
  if (!Array.isArray(visits)) return null;         // unknowable, so silent
  const t = String(text || '');
  const spans = [];
  const markerRe = /\[\s*\/?\s*[A-Za-z][A-Za-z0-9_]*\s*:[^\]\n]*\]/g;
  let mm;
  while ((mm = markerRe.exec(t))) spans.push([mm.index, mm.index + mm[0].length]);
  const onlyInsideMarkers = (path) => {
    if (!spans.length) return false;
    let at = t.indexOf(path), seen = false;
    while (at !== -1) {
      seen = true;
      if (!spans.some(([s, e]) => at >= s && at + path.length <= e)) return false;
      at = t.indexOf(path, at + 1);
    }
    return seen;
  };
  const named = (unwrittenFn || unwrittenPaths)(text, visits)
    .filter(p => !onlyInsideMarkers(p));
  if (!named.length) return null;
  const one = named.length === 1;
  return '_(' + named.map(p => '`' + p + '`').join(' and ')
    + (one ? ' is named above, but they never wrote it' : ' are named above, but they never wrote them')
    + ' to the cabinet on this run — ask them to file '
    + (one ? 'it if you need it' : 'those if you need them') + '.)_';
}

/* Every "the coworker claimed something the office did not do" check, run
   once, in one place.

   Three dispatch paths each grew their own copy of this block — @mention,
   Delegate, and a task run — and copies drift. They had: five guards, four,
   and four. `unsentAsk` (the coworker who ACKs "waiting on a teammate" with
   an empty delivery queue) was wired into the @mention path only, so the
   same reply on the Delegate button said nothing at all. The comment in the
   task-path copy already records the previous round of this — fabricatedRelay
   "was wired into one path of three, and the run that first exposed the
   fabrication was a TASK run, which was one of the two without it."

   The second reason it is one function: the CALLER needs to know whether
   anything fired, not just show it. The activity feed writes its row before
   these run, so a turn where nothing was saved was still filed as
   `finished "…" ✓` — the office's own ledger contradicting the honesty note
   it had just printed in chat. Returning an array lets the row ask.

   `delivered` is how many DMs actually went out this run; several of these
   are silent whenever something DID land, which is what stops them firing
   on a run that worked. `roster` is real coworker names, so fabricatedRelay
   only fires on a colleague who exists. `self` is the coworker speaking, so
   a marker addressed to itself is not reported as a person left waiting.
   `skipKinds` is the task path's exception, documented on unsentBlocks. */
function honestyNotes(raw, opts) {
  /* Every guard below reads this buffer to accuse the coworker of leaving
     something unsent, unclosed or unfiled. A marker written inside a
     reasoning block was never sent, so there is nothing to accuse: an
     unclosed `[VAULT_NEW:` that the model was only sketching out would
     otherwise print "no file reached the cabinet" about a file nobody was
     promised. `shownBody` below inherits the mask too, and should — its
     two guards assert about what the boss can READ, and the boss does not
     read the reasoning (cleanHarmony removes it). */
  raw = maskReasoning(raw);
  const o = opts || {};
  const delivered = o.delivered || 0;
  const out = [];
  const push = (n) => { if (n) out.push(n); };
  push(unsentHandoff(raw, delivered, o.self, o.roster));
  /* extractApproval on the same buffer answers "did a well-formed ask get
     raised this run" — a good one keeps this silent, only a malformed one
     is called out. Re-derived rather than passed in: the two call sites
     that tried to borrow it from an enclosing block produced a no-undef and
     a live ReferenceError respectively, and it is pure, so it costs
     nothing. */
  push(unsentElevation(raw, !!extractApproval(raw)));
  push(unsentBlocks(raw, o.skipKinds));
  push(unsentAsk(extractAcks(raw).map(a => a.state), delivered));
  push(fabricatedRelay(raw, delivered, o.roster || []));
  /* Two kinds of guard, two inputs — the split is the point.

     Everything above detects MARKERS: unsent blocks, orphaned hand-offs,
     acks. Markers exist only in the raw buffer — the strip chain deletes
     them — so those guards must read raw or go blind.

     These last two assert about the boss's SURFACE: "is named above",
     "this names sources". Their notes render under the CLEANED bubble, so
     their "above" has to be the bubble's text, not the wire's. Measured
     (office 9261, 2026-08-15): a coworker DM'd a teammate "Please check
     Research/plan.md", the block was stripped and delivered, the boss's
     bubble read "On it." — and beneath it the office warned that
     `Research/plan.md` "is named above" when no such name was above, on a
     card that showed the run's own Deliveries/ artifact two lines down.
     A note about what the boss can read must read what the boss reads. */
  const shown = shownBody(raw, o.self);
  push(unverifiedSources(shown, o.visits));
  push(unfiledPath(shown, o.visits));
  return out;
}

/* What the boss actually sees: the one strip chain, shared.

   Blocks first: their delimiters are also whole-line markers, so letting
   stripOrphanTags run first would remove the tags stripBlocks needs to find
   the payload by, and strand the body exactly as before. stripSelfLabel
   FIRST: while the echoed label is still there the marker is not at column
   zero, and the line-anchored strips below cannot see it.

   Extracted from visibleReply because a second reader appeared: the two
   honesty guards that assert about the boss's surface ("is named above")
   were reading the RAW buffer, and the chain existed in exactly one place —
   so their "above" and the bubble's "above" were two different texts. One
   rule, one place; both surfaces now read the same body. */
function shownBody(text, selfName) {
  return stripOrphanTags(stripAcks(stripBlocks(stripSelfLabel(String(text || ''), selfName))))
    .replace(/\n{3,}/g, '\n\n').trim();
}

function visibleReply(text, selfName) {
  const raw = String(text || '');
  const cleaned = shownBody(raw, selfName);
  /* A CLOSED [DM_TO]...[/DM_TO] block is fully consumed by stripBlocks
     above, tag and body together -- so when a reply is prose plus a
     well-formed hand-off ("On it.\n[DM_TO: Nano]\nq\n[/DM_TO]"), `cleaned`
     is just the prose ("On it."), and that is correct: real content wins
     over the placeholder below.

     An UNCLOSED trailing opener is different, and `cleaned` lies about it.
     stripBlocks can't touch it (no closer to match), so only
     stripOrphanTags fires -- and that strips just the marker's own LINE,
     leaving the recovered DM's body sitting in `cleaned` as if it were the
     coworker's own words to the boss. Watched live: the boss's bubble read
     "What is 4+4?", Gemma's question for Nano, presented as if Gemma were
     asking the BOSS. Detected by comparing: if `cleaned` is EXACTLY the
     recovered hand-off's body and nothing else, it isn't leftover prose,
     it's the hand-off's own payload with its wrapper stripped -- fall
     through to the placeholder branch below instead of returning it. */
  const dmsForRecoveryCheck = extractAllDMs(raw);
  const trailingDm = dmsForRecoveryCheck[dmsForRecoveryCheck.length - 1];
  const cleanedIsOrphanedDmBody = !!trailingDm && cleaned === trailingDm.body;
  if (cleaned && !cleanedIsOrphanedDmBody) return cleaned;
  /* Nothing survived the strip. `stripAcks` matches ANY lowercase state
     while `extractAcks` only accepts the four real ones, so a typo'd
     marker ([ACK: banana: …]) gets deleted without ever being understood
     — and the agent's entire reply disappears into an empty bubble.
     Only trust the strip when a marker was genuinely recognised; if it
     wasn't protocol, it was text, and text is the boss's to see. Showing
     an odd string beats silently dropping what someone said. */
  const acks = extractAcks(raw);
  /* A reply that was ONLY a hand-off. The strip understood it perfectly and
     removed it, leaving nothing -- and the raw fallback below then printed
     the protocol back out. Watched live: the boss asked Gemma a question and
     their bubble read, in full,

         [DM_TO: Nano] Can you name one color of a ripe banana? [/DM_TO]

     The fallback exists for markers we did NOT understand, on the principle
     that showing an odd string beats silently dropping what someone said.
     A recognised block is the opposite case: we know exactly what happened,
     so say it. Handled before the ack branch because a hand-off reply
     usually carries no ack at all. */
  const dms = extractAllDMs(raw);
  if (dms.length) {
    const who = dms.map(d => d.to).filter(Boolean);
    const uniq = [...new Set(who)];
    const names = uniq.length <= 1 ? (uniq[0] || 'a coworker')
                : uniq.slice(0, -1).join(', ') + ' and ' + uniq[uniq.length - 1];
    /* Wording watched, then corrected. "Asked Nano — I'll come back to you
       with what they say" reads beautifully in the boss's thread and is
       wrong twice. It PROMISES a follow-up the office does not currently
       deliver (the answer lands in the team room and the direct thread
       never hears again), and the same branch renders when a coworker DMs
       someone BACK -- so Nano answering Gemma's question rendered as
       "Asked Gemma - I'll come back to you", which inverts who asked whom.
       State the fact and point at where the reply actually goes. */
    return `Sent this to ${names} — their reply lands in the team room.`;
  }
  /* Same shape as the hand-off placeholder, one door over: a reply that
     was ONLY an approval ask. The strip understood the marker and removed
     it; the raw fallback would print the protocol back at the boss on
     precisely the surface the design doc names "the coworker walks to
     your desk and asks". The TRAY carries the request; the bubble should
     read like the walk. */
  const ask = extractApproval(raw);
  if (ask) {
    return `Asked for your stamp — "${ask}". It's waiting on your desk.`;
  }
  /* Third door, same principle as the two above, and the one that decides
     the measured case. The fallback's own rule — stated at the top of this
     block — is that raw survives for markers the office did NOT understand:
     "if it wasn't protocol, it was text, and text is the boss's to see."
     A write marker that opened and never closed is the opposite. The office
     understands it exactly: `unsentBlocks` is, at this moment, composing a
     full sentence about it for the same reply ("no file reached the cabinet
     — that one needs a closing tag … Ask them to file it again"). Printing
     the syntax back beside that sentence is not showing the boss what their
     coworker said; it is showing them the machine's name for a failure the
     office is already describing in words.

     Measured before this door existed, against a canned brain returning
     exactly `[VAULT_NEW: Notes/scratch.md`: the strip removed it correctly,
     this fallback put it straight back, the board went green, and the office
     FILED the marker — the boss's cabinet gained a .md whose whole body was
     that string. The filing then set `deliveryFiled`, which suppressed the
     very guard quoted above. Every one of those four follows from this line
     handing back what the cleaner had just removed.

     Returning empty is safe in a way it was not a few days ago: an empty
     reply is now a case the office handles honestly rather than silently —
     the card parks in `doing` and wears the guard's sentence as its reason.
     Reached only when `cleaned` is empty, so there is no prose to lose. */
  if (unsentBlocks(raw)) return '';
  if (!acks.length) return raw.trim();
  const note = String(acks[acks.length - 1].note || '').trim();
  return note || 'still working on it';
}

/* True when `text` is the sentence visibleReply substitutes for a reply
   that was nothing but hand-offs. One function to WRITE it (visibleReply,
   above) and one to RECOGNISE it, kept adjacent so they cannot drift --
   call sites re-dress the placeholder for rooms the generic sentence
   cannot know about (drop it beside its own DM bubble in the team room;
   upgrade it to a promise in the thread the report-back will land in). */
function isHandoffPlaceholder(text) {
  return /^Sent this to [^\n]+ — their reply lands in the team room\.$/
    .test(String(text || '').trim());
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
   dispatch for all of them, not just the first -- and, since both known
   real-world misses of this marker (an 8B Claude-family model, then
   gemma-4-e4b, captured verbatim through the live proxy) were the model
   opening the tag correctly and simply never emitting the closer, ALSO
   the single authority both dispatch (detectToolCall) and display
   (visibleReply) consult for whether a trailing unclosed opener should
   count as a real hand-off. One rule, not two that can quietly diverge --
   see the note in detectToolCall for what happens when they do. */
function extractAllDMs(text) {
  if (!text) return [];
  text = maskReasoning(text);   // see extractApproval
  const out = [];
  const re = /\[\s*DM_TO\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*DM_TO\s*\]/gi;
  let m, lastEnd = 0;
  while ((m = re.exec(text)) !== null) {
    out.push({ to: m[1].trim(), body: (m[2] || '').trim() });
    lastEnd = re.lastIndex;
  }
  /* Trailing recovery: an opener AFTER every well-formed block's end,
     with nothing to close it. Scoped tight, on purpose --
       - only the text after the last real closer, so a properly closed
         block earlier in the reply is never touched;
       - the opener must be immediately followed by its own line (the
         shape the model actually produces, name on the tag, body below);
       - the tail must be non-empty and read as ONE continuous message --
         a blank line before more text means the model kept talking after
         the opener and likely abandoned the hand-off rather than just
         forgetting the closer, so that case is deliberately left alone
         for ORPHAN_TAG_RE's existing cosmetic cleanup instead. */
  const tailText = text.slice(lastEnd);
  if (!/\[\s*\/\s*DM_TO\s*\]/i.test(tailText)) {
    const openRe = /\[\s*DM_TO\s*:\s*([^\]\n]+)\]/gi;
    let lastOpen = null, om;
    while ((om = openRe.exec(tailText)) !== null) lastOpen = om;
    if (lastOpen) {
      const afterOpen = tailText.slice(lastOpen.index + lastOpen[0].length);
      if (/^\s*\n/.test(afterOpen)) {
        const body = afterOpen.trim();
        if (body && !/\n[ \t]*\n/.test(body)) {
          out.push({ to: lastOpen[1].trim(), body });
        }
      }
    }
  }
  return out;
}

/* Find a [HANDOFF_TO: name]\n<body>\n[/HANDOFF_TO] block. Returns {to, body}
   or null. Used by CafresoHQ to transfer thread ownership to a single
   specialist — after the handoff the user's next messages go directly to
   that specialist with CafresoHQ out of the loop. */
function extractHandoff(text) {
  if (!text) return null;
  const m = maskReasoning(text).match(/\[\s*HANDOFF_TO\s*:\s*([^\]\n]+)\]\s*\n?([\s\S]*?)\n?\[\s*\/\s*HANDOFF_TO\s*\]/i);   // see extractApproval
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
/* `roster` — the names actually on the team, longest matched first, so a
   coworker whose name contains a space can be addressed at all.

   The token was `@[A-Za-z][A-Za-z0-9_-]*`: one word, no spaces. The front
   desk hires a coworker called **Local Brain**. The task→chat bridge writes
   `@${assignee.name} ` verbatim. So the office generated a mention it could
   not parse: `@Local Brain do X` read as a mention of "Local" with the body
   "Brain do X", matched nobody, and fell through to the CEO.

   Measured: the boss typed `@Local In one sentence, disagree` — the exact
   words the office's own handoff guard had just told them to type — and the
   CEO answered instead, with nothing anywhere saying the addressee had
   changed.

   Without a roster this behaves exactly as before, which is what keeps the
   fallback honest: an unknown name still parses as one word and is still
   reported as unknown. A roster name only ever wins where it matches
   wholly, up to a space or the end, so "@Local Brain" cannot be stolen by a
   coworker who happens to be called "Local". */
function extractAllMentions(text, roster) {
  if (!text) return null;
  const names = (roster || []).map(n => String(n || '').trim()).filter(Boolean)
    .sort((a, b) => b.length - a.length);
  const src = String(text);
  const targetNames = [];
  /* Dedup case-insensitively but KEEP the first-seen original casing —
     the old check compared lowercase against a mixed-case array, so
     "@Plato @plato" produced two targets and a double dispatch. */
  const seen = new Set();
  let i = 0;
  for (;;) {
    while (i < src.length && /\s/.test(src[i])) i++;
    if (src[i] !== '@') break;
    const rest = src.slice(i + 1);
    // A whole roster name, or failing that the single-word token.
    let hit = names.find(n => rest.slice(0, n.length).toLowerCase() === n.toLowerCase()
                              && /^(\s|$)/.test(rest.slice(n.length)));
    if (!hit) {
      const m = rest.match(/^[A-Za-z][A-Za-z0-9_-]*/);
      // Same trailing rule as the regex this replaced: a name runs up to
      // whitespace, so "@plato," is not a mention of "plato".
      if (!m || !/^(\s|$)/.test(rest.slice(m[0].length))) break;
      hit = m[0];
    }
    i += 1 + hit.length;
    const lc = hit.toLowerCase();
    if (!seen.has(lc)) { seen.add(lc); targetNames.push(hit); }
  }
  const body = src.slice(i).trim();
  if (!targetNames.length || !body) return null;
  return { targetNames, body };
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
/* `at: 0` is not "stale", it is NEVER ASKED, and the two have to stay
   distinguishable — see `vaultReadySync` below. */
let _vaultConfiguredCache = { at: 0, ok: false };
const _vaultWatchers = new Set();
function _noteVaultReady(ok, now) {
  const first = !_vaultConfiguredCache.at;
  const changed = first || _vaultConfiguredCache.ok !== ok;
  _vaultConfiguredCache = { at: now, ok };
  if (changed) for (const fn of [..._vaultWatchers]) { try { fn(ok); } catch (_e) { /* a watcher must not break the probe */ } }
}
async function isVaultReady() {
  const now = Date.now();
  /* `at &&` first: a never-asked cache is not a fresh one. Real clocks make
     `now - 0` enormous so this never bit in the browser, but the whole point
     of the `at` field is that zero means "no answer yet", and a freshness
     test that reads it as an answer from 1970 is one stubbed clock away from
     handing back `ok: false` for a vault nobody has looked at. */
  if (_vaultConfiguredCache.at && now - _vaultConfiguredCache.at < 5000) return _vaultConfiguredCache.ok;
  try {
    const s = await CafresoHQClient.vaultStatus();
    _noteVaultReady(!!(s.configured && s.exists), now);
  } catch (_e) {
    /* The office is unreachable, so whether a vault is CONFIGURED is
       genuinely unknown — but what the coworker gets is not: `toolsForAgent`
       awaits this same function and hands over nothing. Recording it as an
       observation of "not ready" is what keeps the card and the grant
       saying the same thing, which is the only invariant here worth
       protecting. */
    _noteVaultReady(false, now);
  }
  return _vaultConfiguredCache.ok;
}
function clearVaultReadyCache() {
  _vaultConfiguredCache = { at: 0, ok: false };
  /* Back to "never asked", and the watchers are told so they can ask again.
     Without this, Settings → Connections → MARKDOWN VAULT would clear the
     cache after a backend swap and every coworker card would sit on the
     unknown branch — no chip at all — until the next dispatch happened to
     probe. */
  for (const fn of [..._vaultWatchers]) { try { fn(undefined); } catch (_e) { /* as above */ } }
}
/* The synchronous half of `isVaultReady`, for the surfaces that describe a
   coworker while React renders.

   `undefined` means the office has never had an answer. That is NOT false:
   app/cast.jsx drops a capability whose condition is unestablished rather
   than printing it as switched off, on the same "do not sell on unknown"
   rule that governs canSearch and canMakeImages. A card that has not yet
   heard from the vault says nothing about the vault. */
function vaultReadySync() {
  return _vaultConfiguredCache.at ? _vaultConfiguredCache.ok : undefined;
}
/* Subscribe to that answer arriving or changing. The office kicks one probe
   at start-up (app.jsx) so the shrug is measured in milliseconds. */
function onVaultReadyChange(fn) {
  _vaultWatchers.add(fn);
  return () => _vaultWatchers.delete(fn);
}

/* Whether the agent-wallet ICP-Service is installed AND the on-chain bridge is
   reachable (i.e. we're inside the ai.cafreso.com shell that holds the II key).
   The catalog mirrors the on-chain flag to settings.icpServices.wallet so tool
   gating stays synchronous. */
function icpWalletEnabled() {
  try {
    // Master money-module gate first — when the user has money OFF, agents
    // must not even see the WALLET_* tools, regardless of install state.
    if (!(window.hqMoneyOn && window.hqMoneyOn())) return false;
    const s = CafresoHQClient.getSettings();
    const installed = !!(s && s.icpServices && s.icpServices.wallet);
    const bridge = !!(CafresoHQChain && CafresoHQChain.isAvailable());
    return installed && bridge;
  } catch (_e) { return false; }
}

/* Publish service — writes a clickable .url deliverable via the container's
   /fs endpoints, so (unlike the wallet) it works without the shell bridge. */
function icpPublishEnabled() {
  try {
    const s = CafresoHQClient.getSettings();
    return !!(s && s.icpServices && s.icpServices.publish);
  } catch (_e) { return false; }
}

/* The boss asking for something the office can do and has switched off.

   Measured on office 9262, 2026-08-15. Mika had just built site/index.html
   — the file was on disk, 467 chars, and the office had said so. The boss
   then asked: "put that lemonade page live on the internet and give me the
   link." The reply, in full:

     I can create the local file at site/index.html, but publishing it
     online requires deployment access or a hosting service that isn't
     currently available in this environment.

   Nothing in that is a lie, and every word of it is the model's. That is
   the problem. PUBLISH_SITE exists, is implemented, and works; it is gated
   on `icpPublishEnabled()`, so with the module off it never reached the
   coworker's tool list, and the coworker explained the absence the only way
   it could — by guessing. The office knew the real reason and said nothing,
   which left the boss at a dead end one toggle away from the thing they
   asked for. §7: a failure is one honest sentence PLUS a way forward.

   Keyed on the BOSS's own words, not on the coworker's prose. Whether the
   reply "sounds like a refusal" is a judgement; whether the boss asked to
   put something live is nearly in the text, and whether the module is off
   is a flag. Both halves are things the office knows.

   The sentence is true whenever it fires, even if the boss meant something
   else by "deploy" — the worst case is a line that did not need saying,
   never a line that is wrong. So the match is allowed to be broad, with one
   deliberate exclusion: "internet" and "web" are only matched behind "live
   on the", because a bare "look it up on the internet" is how people ask
   for a SEARCH and has nothing to do with publishing. Everything else is
   let through on purpose. "publish" inside a filename will fire this, and
   that is the cheap direction to be wrong in.

   Named the way the boss sees it. The setting's id is `icpServices.publish`
   and the panel function is IcpServicesPanel, but the tab reads MODULES and
   the row reads "Publish to Web" — and this file has twice recorded what a
   note costs when it names a door by its internal name (#49, #68). */
const ASKS_TO_PUBLISH =
  /\b(?:publish|deploy)\b|\bgo(?:es|ing)?\s+live\b|\bput\s+[^.!?\n]{0,40}\blive\b|\blive\s+on\s+the\s+(?:internet|web)\b|\bship\s+[^.!?\n]{0,30}\blive\b/i;

function publishDoorNote(askText, publishOn) {
  if (publishOn) return null;
  if (!ASKS_TO_PUBLISH.test(String(askText || ''))) return null;
  return '_(nothing can go live from here yet — Publish to Web is switched off.'
       + ' Turn it on in Settings → Modules, then ask again.)_';
}

/* ── A 200 is not a page ──────────────────────────────────────────────────
   Measured live on a fresh office, 2026-08-13. `search.requires()` reads
   `braveEnabled && braveKey`, and until this same commit no control existed
   anywhere in the UI to set either — so no coworker was ever handed
   [SEARCH:]. BROWSER_FETCH, meanwhile, goes to anyone claiming 'web'
   unconditionally. Asked to "search the web", Llama did the only thing left
   open to it and fetched a search engine. All three majors answer 200 with
   nothing in them:

     google.com/search?q=…   200 · 104 chars · "If you're having trouble
                             accessing Google Search, please click here"
     duckduckgo.com/?q=…     200 ·  41 chars · the title, and no results
     bing.com/search?q=…     200 · 631 chars · nav chrome, a few snippets

   (Control, same office, same minute: en.wikipedia.org/wiki/Four-day_week
   → 200 · 8032 chars.)

   The tool returned `Status: 200` above the bot-check notice, the bubble
   rendered "🌐 Read www.google.com/search?…" — and "Read" is a claim that
   reading happened — and the model then wrote three headlines attributed
   to the Guardian, CNBC and Forbes out of a page containing none of them.
   The office filed it `finished ✓` into Done and told the boss "Nothing
   needs you right now. 🎉".

   The invention is the model's and this app cannot stop it. The claim that
   a page was read is OURS. §4: detection is a hint, not a verdict — and a
   status code is a hint about the request, never a verdict about the page.

   So this measures the one thing that can honestly be measured — how much
   readable text actually came back — and reports THAT, in the one string
   both readers see: the boss in the bubble, and the model as its
   [TOOL_RESULT]. The last clause is aimed at the model on purpose; it is
   the only part of this that stands between an empty page and a citation.

   The floor is deliberately low. This must not fire on a short-but-real
   page, so it only speaks when there is essentially nothing there — and it
   says what it counted rather than diagnosing why, except in the one case
   the host name settles outright. */
const READABLE_FLOOR = 220;
const SEARCH_HOSTS = /^https?:\/\/(?:[a-z0-9-]+\.)*(?:google\.[a-z.]+|duckduckgo\.com|bing\.com|search\.yahoo\.com|search\.brave\.com|baidu\.com|yandex\.(?:com|ru)|ecosia\.org|startpage\.com)\//i;

function barrenPage(j, url) {
  const n = String(j.text || '').replace(/\s+/g, ' ').trim().length;
  if (n >= READABLE_FLOOR) return '';
  const nothing = `it answered ${j.status} but only ${n} characters of readable text came back`;
  const dontQuote = ' There is nothing on it to quote, cite or summarise.';
  if (SEARCH_HOSTS.test(String(url || '').trim())) {
    /* The host settles this one: search engines serve results to browsers
       and a bot-check to everything else, so the honest cause is known and
       §7 wants the way forward with it. */
    return `that is a search engine's results page, and they hand automated `
      + `readers a bot check instead of results — ${nothing}.${dontQuote}`
      + ` To search properly the office needs a search provider: `
      + `Settings → Connections → Brave Web Search.`;
  }
  return `${nothing} — pages that assemble themselves with JavaScript look `
    + `like this to a plain fetch.${dontQuote}`;
}

const TOOL_REGISTRY = {
  search: {
    name: 'SEARCH',
    re: /\[\s*SEARCH\s*:\s*([^\]\n]+)\]/i,
    requires: () => CafresoHQClient.getSettings().braveEnabled && CafresoHQClient.getSettings().braveKey,
    doc: '- [SEARCH: <query>] — Brave web search. Use for facts, news, current state. Stop after the line; results will be appended.',
    docShort: 'Web search via Brave. Use for facts, news, current state.',
    run: async (query, { signal }) => {
      const results = await CafresoHQClient.braveSearch(query.trim(), { count: 6, signal });
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
    doc: '- [VAULT_SEARCH: <query>] — search the Library for anything mentioning the query. Returns top matches with snippets.',
    docShort: 'Search the Library for anything matching a query. Returns paths and snippets.',
    run: async (query) => {
      const hits = await CafresoHQClient.vaultSearch(query.trim(), { limit: 8 });
      if (!hits.length) return 'No matches in the Library.';
      return hits.map(h => `• ${h.path}\n  ${h.snippet}`).join('\n\n');
    },
  },
  vault_read: {
    name: 'VAULT_READ',
    re: /\[\s*VAULT_READ\s*:\s*([^\]\n]+)\]/i,
    requires: isVaultReady,
    doc: '- [VAULT_READ: <path>] — read the full contents of a Library file (e.g. "Daily/2026-04-25.md"). Use after VAULT_SEARCH narrows the right one.',
    docShort: 'Read the full contents of a Library file by path. Use after VAULT_SEARCH.',
    run: async (path) => {
      const text = await CafresoHQClient.vaultRead(path.trim());
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
    docShort: 'Append multi-line markdown to an existing Library file (creates if missing).',
    run: async (path, _ctx, body) => {
      const r = await CafresoHQClient.vaultWrite(path.trim(), body || '', 'append');
      return `Appended ${(body||'').length} chars → ${r.path} (now ${r.size} bytes)`;
    },
  },
  vault_new: {
    name: 'VAULT_NEW',
    re: /\[\s*VAULT_NEW\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*VAULT_NEW\s*\]/i,
    requires: isVaultReady,
    doc: '- [VAULT_NEW: <path>]\n<content>\n[/VAULT_NEW] — create a new note (overwrites if exists). Use for new findings, summaries, drafts.',
    docShort: 'Create or overwrite a Library file at the given path with provided content.',
    run: async (path, _ctx, body) => {
      const r = await CafresoHQClient.vaultWrite(path.trim(), body || '', 'write');
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
      '- [EXPORT_PPTX: <path>]\n<markdown outline>\n[/EXPORT_PPTX] — render a real .pptx slide deck and file it in the Library.\n' +
      '  Outline format: `# Title` for the title slide, `## Slide N: Title` for each slide, `- bullet` lines for points.\n' +
      '  Returns the saved Library path. Use this for any deck deliverable — do NOT save as plain .md.',
    docShort: 'Render markdown into a real .pptx PowerPoint deck and file it in the Library.',
    run: async (path, _ctx, body) => {
      const r = await CafresoHQClient.exportPptx(path.trim(), body || '');
      return `Saved PowerPoint (${r.slides || '?'} slide${r.slides === 1 ? '' : 's'}) → ${r.path}`;
    },
  },
  export_docx: {
    name: 'EXPORT_DOCX',
    re: /\[\s*EXPORT_DOCX\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*EXPORT_DOCX\s*\]/i,
    requires: () => true,
    doc:
      '- [EXPORT_DOCX: <path>]\n<markdown content>\n[/EXPORT_DOCX] — render a real .docx Word document and file it in the Library.\n' +
      '  Use headings (`#` / `##` / `###`), bullets (`-` / `*`), and numbered lists (`1.`). Returns the saved Library path.',
    docShort: 'Render markdown into a real .docx Word document and file it in the Library.',
    run: async (path, _ctx, body) => {
      const r = await CafresoHQClient.exportDocx(path.trim(), body || '');
      return `Saved Word doc → ${r.path}`;
    },
  },
  export_pdf: {
    name: 'EXPORT_PDF',
    re: /\[\s*EXPORT_PDF\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*EXPORT_PDF\s*\]/i,
    requires: () => true,
    doc:
      '- [EXPORT_PDF: <path>]\n<markdown content>\n[/EXPORT_PDF] — render a real .pdf and file it in the Library.\n' +
      '  Renderer: weasyprint if available (better typography), reportlab fallback. Returns the saved Library path.',
    docShort: 'Render markdown into a real .pdf and file it in the Library.',
    run: async (path, _ctx, body) => {
      const r = await CafresoHQClient.exportPdf(path.trim(), body || '');
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
      '- [GENERATE_IMAGE: <Library path, e.g. Images/concept.png>]\n<what the image should show>\n[/GENERATE_IMAGE] — generate a real image and file it in the Library.\n' +
      '  Uses the provider/model from Settings → Media. Returns the saved Library path.',
    docShort: 'Generate a real image using the configured provider and file it in the Library.',
    run: async (path, _ctx, body) => {
      const r = await CafresoHQClient.generateImage(path.trim(), (body || '').trim());
      return `Generated image (${r.provider}) → ${r.path}`;
    },
  },
  generate_video: {
    name: 'GENERATE_VIDEO',
    re: /\[\s*GENERATE_VIDEO\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*GENERATE_VIDEO\s*\]/i,
    requires: () => true,
    doc:
      '- [GENERATE_VIDEO: <Library path, e.g. Videos/demo.mp4>]\n<what the video should show>\n[/GENERATE_VIDEO] — generate a real video and file it in the Library.\n' +
      '  Uses the provider/model from Settings → Media. Can take several minutes. Returns the saved Library path.',
    docShort: 'Generate a real video using the configured provider and file it in the Library.',
    run: async (path, _ctx, body) => {
      const r = await CafresoHQClient.generateVideo(path.trim(), (body || '').trim());
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
    run: async (path, { signal, cwd, meta }) => CafresoHQClient.toolExec('FILE_READ', path.trim(), { signal, cwd, meta }),
  },
  dir_list: {
    name: 'DIR_LIST',
    re: /\[\s*DIR_LIST\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [DIR_LIST: <path>] — list files and subdirectories at a path. Use to explore project structure before reading files.',
    docShort: 'List files and subdirectories at a path. Use to explore structure before reading.',
    run: async (path, { signal, cwd, meta }) => CafresoHQClient.toolExec('DIR_LIST', path.trim(), { signal, cwd, meta }),
  },
  file_write: {
    name: 'FILE_WRITE',
    re: /\[\s*FILE_WRITE\s*:\s*([^\]\n]+)\]\s*\n([\s\S]*?)\n?\[\s*\/\s*FILE_WRITE\s*\]/i,
    requires: () => true,
    doc: '- [FILE_WRITE: <path>]\n<content>\n[/FILE_WRITE] — write (create or overwrite) a local file. Path must be within allowed directories.',
    docShort: 'Write (create or overwrite) a local file; body goes in the "body" field.',
    run: async (path, { cwd, meta }, body) => CafresoHQClient.toolExec('FILE_WRITE', path.trim(), { body: body || '', cwd, meta }),
  },
  bash: {
    name: 'BASH',
    re: /\[\s*BASH\s*:\s*([^\]\n]+)\]/i,
    requires: () => true,
    doc: '- [BASH: <command>] — run a shell command on the proxy machine (cwd = project dir or first allowed dir). Requires Bash in CAFRESOHQ_ALLOWED_TOOLS.',
    docShort: 'Run a shell command on the proxy machine. Requires Bash in CAFRESOHQ_ALLOWED_TOOLS.',
    run: async (cmd, { signal, cwd, meta }) => CafresoHQClient.toolExec('BASH', cmd.trim(), { signal, cwd, meta }),
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
    /* "projects/<slug>.md" used to be one of the examples here, and it is
       the one word in this list the OFFICE had already spent. The boss's
       Projects view, the folder they add in Add Project, and the Workspace
       they watch are all "projects" — so a coworker asked for a file "in
       the Site Check project folder" reached for the layout suggested
       right here and wrote to `projects/Site%20Check/index.html` inside
       its own private notes. Watched end to end: the coworker then said
       "The index.html file has been created in the projects/Site%20Check/
       folder", which is true of its notes and false of the folder the boss
       was looking at, and the project's own Files tab stayed empty.
       "work/" collides with nothing. */
    doc: '- [MEMORY_WRITE: <relative-path>]\n<content>\n[/MEMORY_WRITE] — create or overwrite a note in your memory. Use markdown freely. Examples of good memory: "decisions/<topic>.md", "preferences.md", "people/<name>.md", "work/<slug>.md".',
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
    run: async (url, { signal, meta }) => {
      const u = `/browser/fetch?url=${encodeURIComponent(url.trim())}&max_chars=8000`;
      const r = await fetch(u, { signal });
      const j = await r.json();
      /* `meta.failed` exists for exactly this, and this tool was not using
         it: a page that could not be read answers normally, with the reason
         as its result, so nothing threw and every surface captioned it a
         success. The visit header is built from the tool NAME and tense —
         `fail` picks a different verb and icon — so without this the boss
         got "🌐 Read www.google.com/search?…" as the headline and
         "Couldn't read that page" as the body of the same element. The
         sibling note on this mechanism already names the shape: "Opened
         ./site" directly above "Not a directory: ./site". */
      const fail = (why) => { if (meta) meta.failed = true; return `Couldn't read that page — ${why}`; };
      /* §7 wants an honest sentence, and the label was the machine-ish part
         ("Browser fetch error:"), not the message — `j.error` is authored by
         our own serve.py and already reads as English.

         That last sentence was true of every branch but one, and this comment
         is why nobody looked: the fetch route's catch-all formatted the raw
         exception, so a mistyped domain reached the boss as "fetch failed:
         URLError: <urlopen error [Errno 8] nodename nor servname provided, or
         not known>" (#145). serve.py's `_page_fetch_cause` now owns that
         clause, which is what makes the sentence above true rather than
         merely intended — see scripts/test_a_page_that_would_not_load.py.

         Do NOT route this through snagCause. That classifier is tuned for
         BRAIN failures, and a page is not a brain: a site answering 401 came
         back as "that brain isn't signed in yet — add it in Settings", 429 as
         "that brain is rate-limited", 503 as "that brain's service is having
         trouble". All confidently wrong about the wrong subject, which
         SNAG_CAUSES' own comment calls worse than a vague honest one. I had
         applied it here and had to take it back out. */
      if (j.error) return fail(j.error);
      /* A status code is a hint about the REQUEST. It is never a verdict
         about the page — §4's line, on the one tool whose whole job is to
         bring back a page. */
      const barren = barrenPage(j, url);
      if (barren) return fail(barren);
      const head = `URL: ${j.url}\nStatus: ${j.status}\nTitle: ${j.title || '(none)'}\n${'─'.repeat(40)}\n`;
      return head + j.text;
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
      /* Office voice on the label, the backend's own words for the cause —
         see the note on BROWSER_FETCH above for why snagCause must NOT be
         used here. The hint is kept: §7 wants the route out. */
      if (j.error) return `Couldn't take that screenshot — ${j.error}` +
        (j.hint ? `\n${j.hint}` : '');
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
    doc: '- [PEER_JOURNAL: <coworker name>] — read your coworker\'s last 5 journal entries to understand what they\'ve been working on. Use BEFORE [DM_TO: name] when you want to brief them on what has happened so far.',
    docShort: 'Read a coworker\'s last 5 journal entries.',
    run: async (_name) => '(no peer roster bound)',
  },
  /* WALLET_BALANCE / WALLET_SEND — the agent's own on-chain "HQ wallet"
     (an ICRC subaccount of the boss's principal). Available only when the
     Wallet ICP-Service is installed and the app runs inside the shell.
     The `run`s are rebound per-agent in toolsForAgent (they need the agentId
     to derive the subaccount + apply that agent's spend cap). Signing happens
     in the authenticated shell — the agent only requests. */
  wallet_balance: {
    name: 'WALLET_BALANCE',
    re: /\[\s*WALLET_BALANCE\s*(?::\s*([^\]\n]*))?\]/i,
    requires: () => icpWalletEnabled(),
    doc: '- [WALLET_BALANCE] — check your HQ wallet balances across all tokens. Optional filter: [WALLET_BALANCE: ICP].',
    docShort: 'Check your HQ wallet balances (ICP, ckUSDT, ckUNI, sGLDT, $nanas).',
    run: async () => '(WALLET_BALANCE is bound at agent-build time — see toolsForAgent)',
  },
  wallet_send: {
    name: 'WALLET_SEND',
    re: /\[\s*WALLET_SEND\s*:\s*([^\]\n]+)\]/i,
    requires: () => icpWalletEnabled(),
    doc:
      '- [WALLET_SEND: <token> <amount> <to-principal> : <memo>] — send from your HQ wallet.\n' +
      '  Within your spend cap it settles automatically; over the cap the boss is asked to approve first.\n' +
      '  Tokens: ICP, ckUSDT, ckUNI, sGLDT, $nanas. Memo is optional.\n' +
      '  Example: [WALLET_SEND: ICP 0.05 aaaaa-bbbbb-ccccc-ddddd-cai : tip for the design review]',
    docShort: 'Send tokens from your HQ wallet (auto under your cap; over-cap asks the boss).',
    run: async () => '(WALLET_SEND is bound at agent-build time — see toolsForAgent)',
  },
  /* PUBLISH_SITE — Ship-to-chain (DRIVER_CONTRACT §7). Making something
     PUBLIC is the boss's call: the marker queues a one-click approval and
     returns immediately — the actual publish runs host-side after the stamp
     (WALLET_SEND's over-cap pattern; a stream must never block on a human).
     Available when the Publish ICP-Service is installed. (Public *.icp0.io
     canister hosting is the gated upgrade — see docs/PUBLISH_TO_CANISTER.md.) */
  publish_site: {
    name: 'PUBLISH_SITE',
    re: /\[\s*PUBLISH_SITE\s*:\s*([^\]\n]+)\]/i,
    requires: () => icpPublishEnabled(),
    doc:
      '- [PUBLISH_SITE: <dir or index.html path>] — ask the boss to put a built site live on the public internet.\n' +
      '  Point it at the site\'s folder (or its index.html). The boss gets a one-click approval; once stamped,\n' +
      '  the site publishes and a clickable <name>.url lands in the project. NOTHING is public until they stamp it.\n' +
      '  When you have an HQ wallet, published pages automatically include a tip jar paying into it —\n' +
      '  append " : tip=off" to publish without one (e.g. [PUBLISH_SITE: site/dist : tip=off]).',
    docShort: 'Ask the boss to publish a built site (one stamp; tip jar rides along unless tip=off).',
    run: async (arg) => {
      const raw = String(arg || '').replace(/\s*:\s*tip\s*=\s*(on|off)\s*$/i, '').trim();
      try {
        window.dispatchEvent(new CustomEvent('cafresohq:publishRequest', {
          /* agentName null, not 'agent': this tool genuinely does not know
             who invoked it (agentId is null too), and a placeholder that
             names nobody is more honest than one that names a fake. The
             approval card falls back on its own. */
          detail: { agentId: null, agentName: null, path: raw, tip: false },
        }));
      } catch (e) { return `Couldn't queue that publish — ${e && e.message || e}`; }
      return `Asked the boss to publish "${raw}" — waiting for the stamp. Nothing is public yet.`;
    },
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
    /* This instruction used to end: "ALWAYS end completed handoffs with a
       [ACK: completed: …] containing a 3-bullet result + risks +
       next-action so the boss can move fast."

       The office then STRIPPED it. `stripAcks` removes every marker before
       the reply is shown, stored or filed, and `visibleReply` only falls
       back to an ack note when everything else is empty. Verified against
       the real helper: given

         "Here is what I found.\n\n[ACK: completed: • Primary colours are
          red, blue, yellow. • Risk: unsourced. • Next: verify…]"

       the boss sees exactly "Here is what I found." The result, the risk
       and the next action — the three things the instruction demanded —
       are deleted by the office that asked for them.

       Same lens as the narration fix: the office was asking coworkers for
       things it already had (`in_progress` and `completed` duplicate
       `agent.status`, which §4 makes the ONLY authority on whether someone
       is working). Those states stay PARSEABLE, because old histories
       contain them, but are no longer taught. What remains is the half a
       coworker genuinely knows and the floor cannot see: that they are
       stuck, or waiting on somebody. */
    doc:
      '- [ACK: <state>: <one-line note>] — tell the boss something they CANNOT see from the floor.\n' +
      '  Use it for: blocked (you need something to continue), awaiting_reply (you are waiting on someone).\n' +
      '  Examples:\n' +
      '    [ACK: blocked: need Library access — please grant]\n' +
      '    [ACK: awaiting_reply: asked Kenji which draft is current]\n' +
      '  Do NOT report starting or finishing — the office already shows the boss both.\n' +
      '  Put your ANSWER in the reply itself, never inside a marker: markers are stripped before the boss reads it.',
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
      '- [SPAWN_SUBAGENT: <role / specialty>]\n<task description>\n[/SPAWN_SUBAGENT] — bring in a one-shot helper for a focused task.\n' +
      '  The role says what kind of helper you need (e.g. "code reviewer", "summarizer", "fact-checker", "JSON wrangler").\n' +
      '  The task is what they should do. Write it like you\'d brief a fresh coworker — clear scope, expected output.\n' +
      '  Helpers are sandboxed: NEVER elevated, can\'t bring in helpers of their own, and leave when the job is done. Use sparingly (budget caps apply).\n' +
      '  Optional per-spawn model override: `[SPAWN_SUBAGENT: code-reviewer | model:claudecode:sonnet]` — pin a specific model id for this one sub-agent (overrides the global "Sub-agent model" setting). Useful when a particular task warrants a stronger or cheaper model than the spawner uses.',
    docShort: 'Bring in a one-shot helper for a focused task.',
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
      '- [REQUEST_ELEVATION: <one-line reason>]\n<details: which tools you need (file/shell), what specifically you\'ll do with them, why your current toolset isn\'t enough>\n[/REQUEST_ELEVATION] — ask the boss for file and shell access.\n' +
      '  Requires boss APPROVAL. Use ONLY when ordinary tools (Library, web) genuinely cannot complete the task. Most work doesn\'t need this.\n' +
      '  Approval applies to your NEXT job — this reply finishes with the tools you already have. Tell the boss what you\'d do once approved so they can decide.',
    docShort: 'Ask the boss for file and shell access.',
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
      '  Requires boss APPROVAL. Cap of 2 active assistants per senior. They CAN message peers and bring in one-shot helpers, but CANNOT propose further hires of their own (the team is one level deep).\n' +
      '  Difference vs. HIRE_AGENT: assistants are subordinates (you brief them, they report findings to you). HIRE_AGENT proposes a peer for the team.\n' +
      '  Difference vs. SPAWN_SUBAGENT: assistants stay and remember your work between turns; a helper is one-shot and starts fresh.',
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
      '  Cannot grant elevation — only the boss can give a coworker file and shell access, and only by hand.\n' +
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
    doc: '- [DM_TO: <coworker name>]\n<message>\n[/DM_TO] — direct-message another coworker on the team. Use this when you need their expertise or to hand off a sub-task. Stop after the block; the host will deliver it and continue the chain.',
    docShort: 'Send a direct message to a coworker to hand off a task.',
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
    doc: '- [HANDOFF_TO: <specialist name>]\n<one line on what they are picking up>\n[/HANDOFF_TO] — transfer the thread to ONE specialist who owns the task end-to-end. The boss will iterate directly with them. Use this for single-specialist tasks. Stop immediately after the block; the specialist takes over.',
    docShort: 'Transfer the chat thread to one specialist (boss talks to them directly until "back to CafresoHQ").',
    run: async () => '(HANDOFF_TO is dispatched by the host)',
  },
};

/* ── Naming a capability the boss can actually go and find ───────────────
   A coworker that reaches for something it wasn't given produces a hint,
   and that hint used to print the runtime's own name for it:

     _(model attempted WEB_SEARCH, VAULT_NEW but those aren't wired up —
       check Settings → Roster)_

   Two §6 breaks in one line ("model", and the tool call by its raw name),
   and a §5 one underneath them: Settings → Roster does not have a box
   called WEB_SEARCH. It has one called **Web Search**. Sending the boss to
   a checkbox under a name that is not printed on it is the same wrong door
   as pointing them at a page that doesn't hire.

   So the label comes from TOOLS_CATALOG — the very list the checkboxes are
   rendered from — and only the grouping is written here.

   That paragraph used to continue: "it mirrors the grants in
   `toolsForAgent` directly below, which is the one place a claimed box
   becomes a real tool." Two of the five rows never did. There is no
   `claimed.has('code')` and no `claimed.has('files')` anywhere in
   `toolsForAgent` — FILE_*, DIR_* and BASH are gated on `agent.elevated`
   alone, and `elevated` is granted by the 🛡 switch on the coworker's card
   (modals/settings.jsx, ~twenty lines BELOW the checkbox grid) or by the
   boss approving a REQUEST_ELEVATION. The two checkboxes printed "Code
   Exec" and "File Access" were decoys: the boss could tick both, watch
   nothing change, and never notice the working switch further down the
   same card.

   So this table is the wrong shape for those two. A group does not map to
   a checkbox id; it maps to a DOOR, and the door for file and shell work
   is a switch with its own printed label. The checkbox rows still resolve
   through TOOLS_CATALOG so a reworded label still follows; the elevation
   rows carry their label directly, because there is no catalog entry
   behind them to follow — that was the whole defect. `code` and `files`
   are no longer rendered as chips at all (see the audit note in
   modals/settings.jsx), so resolving them through the catalog would now
   name a box the boss cannot even see.

   Deliberately NOT a second copy of the floor's visit vocabulary
   (`visitLine`/`visitWords`, imported at the top of this file). That table
   answers "what is this coworker doing right now"; this one answers "which
   box would let them". Different questions, and the floor's answer —
   "searching for X" — cannot be typed into a settings search field. */
const ELEVATION_DOOR = 'File & shell access';

/* What the 🛡 switch grants, written in the vocabulary every reader of a
   roster already speaks. These are TOOLS_CATALOG ids, and that is the
   entire point of them existing.

   Reproduced 2026-08-16 on a scratch office: a coworker asked for file and
   shell access, the boss approved, the office announced "🛡 Dee now has
   file and shell access" — and the approval handler wrote `'file'` and
   `'shell'` into her tools. Neither is a catalog id (they are `files` and
   `code`), so app/cast.jsx dropped both, and her card went on reading

       CAN USE   VAULT

   for a coworker who had just been given the run of the machine. The two
   strings were not inert, though: memory/hq-agents.md — the roster the
   office renders for coworkers to read — came out as "Tools: vault, file,
   shell", and the same raw join reaches the chief of staff's roster line
   and the hint channel's `claimedRaw`. Machine words nothing else in the
   product uses, describing a real capability under a name no screen has.

   The other elevation door — the switch on the coworker's card — wrote
   nothing at all, so the same coworker's card was wrong in the same way
   by a different route. Both go through app.jsx's `onUpdateAgent`, which
   is where this list is applied, once. */
const ELEVATION_TOOL_IDS = ['files', 'code'];

/* The chief of staff, as somebody the registry can name.

   Everywhere else in the product this is a bare `'CafresoHQ'` string in a
   chat bubble, which is fine — a bubble only has to be read. A message
   record has to be ATTRIBUTED, and until 2026-08-16 the office had no id
   to attribute one to, so the two dispatches the chief of staff makes on
   the boss's behalf were filed as if the boss had typed them. `'ceo'`
   matches the `from` the chat bubbles already use for the same speaker. */
const CHIEF_OF_STAFF = { id: 'ceo', name: 'CafresoHQ' };

const TOOL_CLAIM_GROUPS = [
  [/^(WEB_)?SEARCH|BROWSER_|FETCH|HTTP/i,        'web'],
  [/^VAULT_|^EXPORT_/i,                          'vault'],
  [/^GENERATE_(IMAGE|VIDEO)/i,                   'img'],
  [/^BASH$|^SHELL/i,                             ELEVATION_DOOR],
  [/^FILE_|^DIR_/i,                              ELEVATION_DOOR],
];

/* Which family a marker belongs to, as the group id — the same question
   `toolClaimLabel` asks, one step earlier. Split out because the chief of
   staff needs the same classification and a DIFFERENT door name for it
   (see CEO_DOORS): a second copy of these five regexes on the CEO path is
   precisely the drift this file keeps paying for. */
function toolClaimGroup(name) {
  const n = String(name || '').trim();
  if (!n) return '';
  for (const [re, door] of TOOL_CLAIM_GROUPS) if (re.test(n)) return door;
  return '';
}

function toolClaimLabel(name) {
  const door = toolClaimGroup(name);
  if (!door) return '';
  // A door written out in full is a control that has no catalog entry —
  // today that is the elevation switch, which is not a checkbox.
  if (door === ELEVATION_DOOR) return ELEVATION_DOOR;
  const entry = TOOLS_CATALOG.find(t => t.id === door);
  return entry ? entry.label : '';
}

/* The hint's subject, as a list the boss can read out loud. Anything with
   no checkbox behind it is DROPPED rather than named: a coworker reaching
   for MEMORY_WRITE (which every coworker already has) is not a capability
   question, and printing the raw name to fill the gap is exactly the habit
   this function exists to break. If nothing survives, the caller says the
   vaguer true thing instead of the precise wrong one. */
function claimLabels(names, agent) {
  const seen = [];
  for (const n of names || []) {
    if (claimNeedsMediaDoor(n, agent)) continue;
    if (claimNeedsVaultDoor(n, agent)) continue;
    const label = toolClaimLabel(n);
    if (label && !seen.includes(label)) seen.push(label);
  }
  if (seen.length <= 1) return seen[0] || '';
  return seen.slice(0, -1).join(', ') + ' and ' + seen[seen.length - 1];
}

/* 'img' is the only claim with TWO doors, and they are on different
   screens: the box on the coworker's card, and a provider in Settings →
   Media. `toolsForAgent` needs both, so "which door is shut" is a
   different answer for two coworkers missing the same tool — and naming
   the wrong one costs the boss a trip and teaches them the hint is
   unreliable.

   The box being ALREADY TICKED is the case the shipped sentence got
   wrong. "Turn it on from their card in Settings → Roster" sends the boss
   to a control that is on, they turn it off and on again, nothing
   changes, and the actual shut door — a screen away — is never mentioned.

   `agent` absent means the caller does not know which boxes are ticked
   (the CEO path has an office, not one coworker). Unknown is not false:
   name the box, say nothing about the second screen. Same rule
   app/cast.jsx's `established()` applies to the coworker card. */
function claimNeedsMediaDoor(name, agent) {
  if (!/^GENERATE_/i.test(String(name || '').trim())) return false;
  return ((agent && agent.tools) || []).indexOf('img') >= 0;
}

function claimHitsMediaDoor(names, agent) {
  return (names || []).some(n => claimNeedsMediaDoor(n, agent));
}

/* 'vault' has the same two-door shape, and the office already knew it —
   CEO_DOORS below sends the chief of staff to Settings → Connections for
   exactly this tool family. The coworker path did not, so the boss whose
   coworker reached for the vault got the Roster sentence instead.

   Measured 2026-08-16 on office 9261. Kip, Markdown Vault box TICKED, the
   vault backend switched to Obsidian REST with Obsidian closed. His job
   description orders "synthesize into a research note saved to
   Research/<topic>.md via [VAULT_NEW]" and the same system prompt lists
   what is actually wired up — BROWSER_FETCH, ACK, SPAWN_SUBAGENT,
   HIRE_AGENT, HIRE_ASSISTANT, REQUEST_ELEVATION, DM_TO, PEER_JOURNAL —
   under "ONLY invoke these exact tools". He obeyed the order, and the
   boss read:

     _(Kip reached for Vault Notes, which they don't have — turn it on
       from their card in Settings → Roster, or @-mention a coworker who
       already has it.)_

   The box was on. The trip is wasted, the toggle changes nothing, and the
   shut door — Settings → Connections → MARKDOWN VAULT — goes unnamed.

   Same `agent`-absent rule as the media door: unknown boxes are not
   ticked boxes, so the CEO's one-argument call still gets the label. */
function claimNeedsVaultDoor(name, agent) {
  if (!/^(VAULT_|EXPORT_)/i.test(String(name || '').trim())) return false;
  return ((agent && agent.tools) || []).indexOf('vault') >= 0;
}

function claimHitsVaultDoor(names, agent) {
  return (names || []).some(n => claimNeedsVaultDoor(n, agent));
}

/* Which of `known` marker names this reply OPENED, whatever else it says.

   `known` and the granted list come in as parameters rather than being read
   off TOOL_REGISTRY here, for the reason the comments on `unsentBlocks` and
   `stripBlocks` both give: scripts/test_reply_hygiene.py lifts named
   functions out of this file to run under node, and a lifted function that
   reaches for a module-level const is a ReferenceError. Same rule as
   `unfiledPath`'s injected `pathsFn`/`filedFn`.

   Openers only, closed or not. A closed block whose tool never ran is the
   case this exists for; an unclosed one is `unsentBlocks`' business and it
   runs on the same raw buffer. */
function openedMarkers(text, known) {
  const t = String(text || '');
  const out = [];
  for (const name of known || []) {
    if (out.includes(name)) continue;
    if (new RegExp('\\[\\s*' + name + '\\s*:', 'i').test(t)) out.push(name);
  }
  return out;
}

/* Which tools the prompt ORDERS that the session cannot run.

   The office writes half a system prompt and the boss writes the other
   half, and until this existed the two halves were never compared.
   Measured 2026-08-16 on office 9261, both halves, both wrong:

   Kip, vault healthy so VAULT_* granted, no Brave key. His shipped
   persona: "Use [SEARCH] to gather sources, then synthesize into a
   research note saved to Research/<topic>.md via [VAULT_NEW]." Four
   paragraphs down, the same prompt: "ONLY invoke these exact tools",
   list without SEARCH.

   Otto, hired through NEW HIRE with the job description cleared so the
   default base applies, no vault box: "FILE-DELIVERY RULE: Any deliverable
   longer than ~200 words … MUST be saved to the Library using [VAULT_NEW:
   <path>]…" — the office's own MUST, for two tools it did not grant.

   A coworker that obeys gets its marker stripped and hands the boss a path
   with no file behind it; one that obeys the other half does the work and
   says nothing about why it could not file. Either way the round trip is
   spent on a contradiction the office could have resolved before sending.

   `known` and `granted` come in as parameters, not read off TOOL_REGISTRY
   here, for the reason `openedMarkers` gives above: the suites lift this
   function into node and a module-level const would be a ReferenceError.
   `known` also does the filtering that matters — a job description full of
   [[wikilinks]] or a literal [TODO] is not a tool order. */
function orderedButNotGranted(text, known, granted) {
  const have = new Set(granted || []);
  const real = new Set(known || []);
  const out = [];
  const re = /\[\s*\/?\s*([A-Z][A-Z0-9_]{2,})\s*[:\]]/g;
  let m;
  while ((m = re.exec(String(text || '')))) {
    const n = m[1];
    if (!real.has(n) || have.has(n) || out.includes(n)) continue;
    out.push(n);
  }
  return out;
}

/* One sentence, two callers — the empty-reply branch below and the branch
   that fires when a coworker wrapped the same reach in prose. It read as
   two independent notes and would have drifted the way the three honesty
   blocks did before `honestyNotes` collected them. */
function reachedForNote(missing, agent) {
  const want = claimLabels(missing, agent);
  const media = claimHitsMediaDoor(missing, agent);
  const vault = claimHitsVaultDoor(missing, agent);
  /* Read off the catalog the checkboxes are rendered from, so a reworded
     box follows the sentence. The Image Gen line below still spells its
     label out; left alone deliberately — rewriting a shipped sentence is
     not this ticket, and the two suites that lift these functions pin it. */
  const vaultBox = toolClaimLabel('VAULT_NEW');
  return want
    ? `_(${agent.name} reached for ${want}, which they don't have — turn it on from their card in Settings → Roster${media ? ', and pick an image provider in Settings → Media' : ''}${vault ? ', and connect a Library in Settings → Connections' : ''}, or @-mention a coworker who already has it.)_`
    : media && vault
    ? `_(${agent.name} reached for image work and for the Library. Both boxes are already on — what's missing is an image provider, which you pick in Settings → Media, and a Library connection, which you set up in Settings → Connections.)_`
    : media
    ? `_(${agent.name} reached for image work. Their Image Gen box is already on — what's missing is an image provider, which you pick in Settings → Media.)_`
    : vault
    ? `_(${agent.name} reached for the Library. Their ${vaultBox} box is already on — what's missing is the Library connection, which you set up in Settings → Connections.)_`
    : `_(${agent.name} reached for something they haven't been given — check what they're allowed to do in Settings → Roster, or @-mention a coworker who can.)_`;
}

/* ── The same sentence, for the one speaker who has no card ──────────────
   Everything above is written for a hire: "their card", "Settings →
   Roster", "@-mention a coworker". The chief of staff is none of those
   things, and until this existed it was handed the coworker copy anyway.
   Measured 2026-08-15 on a throwaway office (port 9261, canned brain on
   9236), asking the chief of staff "what's the price of cycles today?":

     CafresoHQ  _(they reached for Web Search, which they don't have —
                 turn it on from their card in Settings → Roster and ask
                 again.)_

   Two wrong things in one sentence the office says about itself. "They"
   casts the speaker as a third party — the boss reads it as a coworker
   having failed, when the office is describing its own reach. And the
   Roster renders `agents.map(...)`; opening it live on that same office
   listed Vera and Kip and nobody else. There is no card to go to.

   The doors that ARE real: `ceoTools` is built from
   `TOOL_REGISTRY.search.requires()` (braveEnabled + braveKey) and
   `isVaultReady` — and both switches live on ONE screen, Settings →
   Connections, as the 🔍 BRAVE WEB SEARCH and MARKDOWN VAULT panels.
   Opening Connections on the reproducing office confirmed both were
   present, so the note has a true door to name.

   Anything else the chief of staff reaches for — image work, files, a
   shell — is not a switch it can be given at all. There is no setting
   that grants the office a shell, so pointing anywhere in Settings would
   be a second wrong door. §7 still wants a way forward, and there is a
   real one: a coworker can hold those tools even though the office can't. */
const CEO_DOORS = {
  web: 'Settings → Connections',
  vault: 'Settings → Connections',
};

function ceoReachedForNote(missing) {
  /* Split first. One reply can reach for both kinds — "let me look that up
     and check the logs" is two markers — and a single door named for both
     sends the boss to Connections looking for a shell switch that is not
     there and never will be.

     Nothing is filtered on the way in. A marker with no label — DM_TO,
     MEMORY_WRITE — falls into `unavailable` and is then dropped by
     claimLabels, which is the one place that rule lives. A guard here
     would be a second copy of that decision, and fire-testing it proved
     the point: an arm that deleted the guard changed no output at all. */
  const openable = [];
  const unavailable = [];
  for (const n of missing || []) {
    (CEO_DOORS[toolClaimGroup(n)] ? openable : unavailable).push(n);
  }
  const open = claimLabels(openable);
  const none = claimLabels(unavailable);
  if (!open && !none) return '';
  const doors = [];
  for (const n of openable) {
    const d = CEO_DOORS[toolClaimGroup(n)];
    if (!doors.includes(d)) doors.push(d);
  }
  /* First person throughout, because `from: 'ceo'` renders these as the
     office speaking. Each of the three leaves a way forward (§7): a
     switch for what can be switched on, and a coworker for what can't. */
  /* Each family named ONCE. The first draft opened "I reached for X and Y"
     and then said X and Y again to give each its door — which makes the
     boss parse the same list twice, the habit #64 was filed against. */
  if (open && none) {
    return `_(I reached for ${open}, which isn't switched on yet — you can turn it on in ${doors.join(' and ')}. I also reached for ${none}, which isn't something I can be given at all — @-mention a coworker who has it, or hire one from the front desk.)_`;
  }
  if (open) {
    return `_(I reached for ${open}, which isn't switched on yet — you can turn it on in ${doors.join(' and ')}, then ask me again.)_`;
  }
  return `_(I reached for ${none}. That isn't something I can be given — I run the office, I don't hold tools of my own. @-mention a coworker who has it, or hire one from the front desk.)_`;
}

/* The facts app/cast.jsx needs and deliberately refuses to look up for
   itself — read HERE, in the file that hands the tools over, so that a card
   and `toolsForAgent` cannot quietly drift apart. Each line below is the
   SAME expression the grant uses, a few dozen lines further down:

     canSearch      TOOL_REGISTRY.search.requires() — braveEnabled && braveKey
     elevated       the subject's own flag, which gates FILE_* / BASH
     canMakeImages  settings.imageProvider, the second door for 'img'
     moneyOn        icpWalletEnabled() — money module, install AND bridge
     vaultOn        the last answer `isVaultReady` got, which gates VAULT_*

   It lived in modals/hire.jsx, where exactly one surface used it and the
   comment above it promised the card and the runtime "cannot disagree".
   That promise held only on the shelf: the two surfaces that render a HIRED
   coworker never called it. A shared fact-reader next to the grant is what
   makes that sentence structural instead of aspirational.

   Every read is wrapped, and a failed read leaves the fact ABSENT rather
   than false — see `grantedTools`. Absent is "we could not find out", which
   must never be shown to the boss as "you have not set it up".

   `subject` is an agent or a candidate template; both carry `.elevated`. */
function capabilityFacts(subject) {
  const f = { elevated: !!(subject && subject.elevated) };
  try { f.canSearch = !!TOOL_REGISTRY.search.requires(); } catch (_e) { /* settings unreadable */ }
  try {
    const s = (CafresoHQClient && CafresoHQClient.getSettings) ? CafresoHQClient.getSettings() : null;
    if (s) f.canMakeImages = !!s.imageProvider;
  } catch (_e) { /* settings unreadable */ }
  try { f.moneyOn = icpWalletEnabled(); } catch (_e) { /* never throws, but the rule is the rule */ }
  /* The only fact here the office cannot read on demand: `isVaultReady` is a
     round trip to /vault/status and a card renders synchronously. So this
     reads the last answer, and leaves the key OFF the object entirely when
     there has never been one — the difference between "the vault is not
     there" and "nobody has asked yet", which `grantedTools` treats as the
     difference between saying "off" and saying nothing. */
  const vaultOn = vaultReadySync();
  if (vaultOn !== undefined) f.vaultOn = vaultOn;
  return f;
}

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
  /* Media generation. TWO facts have to hold, and the shipped code read
     only one of them.

     A provider in Settings → Media is what makes the call work — without
     it the marker fires and the request comes back "provider required".
     That check was here and is still here. What was NOT here is
     `claimed.has('img')`: the moment any boss picked an image provider,
     GENERATE_IMAGE went into the prompt of EVERY coworker in the office,
     including ones whose Image Gen box had never been ticked. Measured
     2026-08-15 on a fresh office — a hire named Marge, tools ['web',
     'files'], no 'img' — and her system prompt carried
     `[GENERATE_IMAGE: <vault path>]` all the same.

     So the box granted nothing and, worse, removing it removed nothing:
     two directions of the same lie, on a control the boss is looking
     straight at. The provider is the OTHER door, on another screen, and
     the fix is not to pick one of them — it is to require both, which is
     what app/cast.jsx already tells the boss on the coworker card
     (CAN_DO.img + CAN_DO_NEEDS.img = 'canMakeImages').

     Video rides the same claim deliberately. There is no 'video' id in
     TOOLS_CATALOG, so leaving GENERATE_VIDEO on its provider alone would
     have kept exactly this defect alive for the half nobody had a box
     for — and TOOL_CLAIM_GROUPS has always answered "Image Gen" when a
     coworker reached for video, a sentence that was wrong when it was
     written and is true now. One box, both kinds of media, each still
     needing its own provider. */
  try {
    const s = (CafresoHQClient && CafresoHQClient.getSettings) ? CafresoHQClient.getSettings() : {};
    if (claimed.has('img') && s && s.imageProvider) out.push(TOOL_REGISTRY.generate_image);
    if (claimed.has('img') && s && s.videoProvider) out.push(TOOL_REGISTRY.generate_video);
  } catch (_e) { /* settings store may not be ready during init */ }
  // File/shell tools for elevated agents — available regardless of LLM provider.
  if (agent.elevated) {
    out.push(TOOL_REGISTRY.file_read, TOOL_REGISTRY.dir_list, TOOL_REGISTRY.file_write, TOOL_REGISTRY.bash);
  }
  // FETCH is plain HTTP (urllib) — no local dependency, no jargon if it
  // fails, safe to bundle with the single most common claim a coworker
  // has. Available to any agent that opted into 'web' or is elevated.
  if (agent.elevated || claimed.has('web') || claimed.has('browser')) {
    out.push(TOOL_REGISTRY.browser_fetch);
  }
  /* SCREENSHOT is the OTHER kind of browser tool, and section 5 names it
     specifically: "CDP browser screenshots — niche, heavy, off-thesis for
     v1". It was bundled onto the SAME `claimed.has('web')` check as fetch
     above — so any coworker with plain web search, the cheapest, first,
     most-hired checkbox on the form, silently also got an autonomous tool
     that requires the BOSS to be running Chrome with a debug flag. When it
     fires and CDP isn't there, the failure is not office voice at all —
     it is serve.py's own words, verbatim into the chat bubble:

       "Couldn't take that screenshot — No CDP-enabled browser detected.
        Launch Brave or Chrome with --remote-debugging-port=9222 (or set
        CAFRESOHQ_BROWSER_CDP_URL to a different host:port)."

     That is not a UI element a boss has to go find — an LLM can choose to
     call it on its own initiative from "check out this site", so this is
     the terminal's own "#1 this-isn't-for-me signal" with no door to
     avoid it behind. `elevated` is the one advanced gate this app already
     has (file/shell access, granted through the boss's own approval walk)
     — screenshot rides that gate now, same as the desktop-mode door parks
     the terminal, instead of riding the tool everyone has by default. */
  if (agent.elevated) {
    out.push(TOOL_REGISTRY.browser_screenshot);
  }

  // Per-agent memory — every agent gets a private vault folder regardless
  // of capability flags. Folder root is `Agents/<safe-name>/`. Bind run()
  // to the live agent so paths are scoped server-side and the agent
  // can't read another agent's notes by accident.
  const memReady = await TOOL_REGISTRY.memory_list.requires();
  if (memReady) {
    const root = memoryRoot(agent);
    const scope = (rel) => {
      const p = String(rel || '').replace(/^[./\\]+/, '').replace(/\\/g, '/');
      // Refuse path-traversal attempts.
      if (p.includes('..')) throw new Error('Path traversal not allowed in memory paths.');
      return root + '/' + p;
    };
    out.push({
      ...TOOL_REGISTRY.memory_list,
      run: async () => {
        const all = vaultPaths(await CafresoHQClient.vaultList());
        const mine = all.filter(p => p.startsWith(root + '/'));
        /* A tool result has TWO readers: the coworker, who acts on it, and
           the BOSS, who sees it verbatim in the visit block on the floor.
           This one taught marker syntax — "[MEMORY_WRITE: notes/foo.md]…
           [/MEMORY_WRITE]" — which §6 bans outright on the floor, and which
           is addressed to the wrong person anyway: bosses do not write
           markers. Seen live in a visit block reading "📁 at the filing
           cabinet (your memory is empty — write your first note with
           [MEMORY_WRITE: …])".
           The coworker already has the vocabulary from its system prompt, so
           the nudge only has to say WHAT to do, not spell the syntax. */
        if (!mine.length) return `(your memory is empty — nothing saved here yet; save a note to start one)`;
        return mine.map(p => '• ' + p.slice(root.length + 1)).join('\n');
      },
    });
    out.push({
      ...TOOL_REGISTRY.memory_read,
      run: async (rel) => {
        try {
          const text = await CafresoHQClient.vaultRead(scope(rel));
          return text.length > 4000 ? text.slice(0, 4000) + '\n\n…(truncated)' : text;
        } catch (e) {
          if (String(e.message || '').includes('404') || String(e.message || '').toLowerCase().includes('not found')) {
            // Same two-reader problem as memory_list above.
            return `(no memory saved at "${rel}" — list your memory to see what is there)`;
          }
          throw e;
        }
      },
    });
    out.push({
      ...TOOL_REGISTRY.memory_write,
      run: async (rel, _ctx, body) => {
        const target = scope(rel);
        const r = await CafresoHQClient.vaultWrite(target, body || '', 'write');
        return `Wrote ${(body||'').length} chars → ${r.path}`;
      },
    });
    out.push({
      ...TOOL_REGISTRY.memory_append,
      run: async (rel, _ctx, body) => {
        const target = scope(rel);
        // A heading inside the coworker's own note — the boss reads these
        // in the vault, so the boss's clock. Seconds dropped with the UTC.
        const stamped = `\n\n## ${officeStamp()}\n${body || ''}\n`;
        const r = await CafresoHQClient.vaultWrite(target, stamped, 'append');
        return `Appended ${(body||'').length} chars → ${r.path} (now ${r.size} bytes)`;
      },
    });
  }
  // ICP wallet tools — only when the agent opted into 'wallet', the Wallet
  // service is installed, and the on-chain bridge is reachable. Bound to the
  // agent's id so spends hit its own subaccount + cap.
  if (claimed.has('wallet') && icpWalletEnabled()) {
    const walletAgentId = agent.id || String(agent.name || 'agent').replace(/[^A-Za-z0-9_-]+/g, '_');
    const WALLET_TOKENS = ['ICP', 'ckUSDT', 'ckUNI', 'sGLDT', 'nanas'];
    out.push({
      ...TOOL_REGISTRY.wallet_balance,
      run: async (arg) => {
        const filter = (arg || '').trim();
        const tokens = filter && filter.toLowerCase() !== 'all' ? [filter] : WALLET_TOKENS;
        const bals = await CafresoHQChain.wallet.balances(walletAgentId, tokens);
        const lines = Object.entries(bals).map(([k, v]) => `• ${k}: ${v == null ? '—' : v}`);
        /* "raw base units" is jargon, but the CAVEAT it carries is the
           honest part — these are unscaled ledger figures, so 100000000 is
           not a hundred million of anything. Dropping the warning to sound
           friendlier would trade §6 jargon for a misleading number, which is
           a worse trade. Plain words, same warning; no decimal conversion is
           invented here because the office does not reliably know each
           token's precision. */
        return lines.length ? `Your HQ wallet (exact ledger amounts, not rounded for reading):\n${lines.join('\n')}` : '(no balances yet)';
      },
    });
    out.push({
      ...TOOL_REGISTRY.wallet_send,
      run: async (arg) => {
        // <token> <amount> <to-principal> : <memo>
        const [mainPart, ...memoParts] = String(arg || '').split(':');
        const memo = memoParts.join(':').trim();
        const bits = mainPart.trim().split(/\s+/).filter(Boolean);
        /* Same two-reader problem as the memory results above: this lands
           verbatim in the visit block the boss watches. Spelling the marker
           back is the obvious way to correct a malformed call, but §6 bans
           that vocabulary on the floor and the coworker already has the form
           in its system prompt — so name what is MISSING instead, which is
           the part they actually got wrong. */
        if (bits.length < 3) return 'That send was incomplete — it needs a token, an amount and a destination, in that order. Nothing was sent.';
        const [token, amount, to] = bits;
        const res = await CafresoHQChain.wallet.send(walletAgentId, token, amount, to, memo);
        switch (res.status) {
          case 'ok': return `Sent ${amount} ${token} → ${to} (block ${res.block}).`;
          case 'needsApproval': return `Awaiting the boss's approval to send ${amount} ${token} → ${to} (${res.reason || 'over cap'}). Nothing sent yet.`;
          case 'declined': return `The boss declined the ${amount} ${token} send to ${to}.`;
          case 'paused': return `Wallet spending is paused — ask the boss to un-pause before sending.`;
          case 'noWallet': return `You don't have a wallet yet — the boss can set one up in Settings → ICP Services.`;
          /* Attributed, not classified. snagCause read "insufficient funds"
             as "that brain's account is out of credit — top it up" — an AI
             billing sentence for a TOKEN LEDGER failure, which is the worst
             place in the office to be confidently wrong. Quoting the ledger
             says exactly as much as we actually know.
             Also deliberately does not add "nothing was sent": a failed send
             is not proof the ledger was untouched, and this office does not
             guess about money. */
          case 'error': return `That send didn't go through — the ledger said: "${res.error}"`;
          default: return `Send result: ${JSON.stringify(res)}`;
        }
      },
    });
  }
  // PUBLISH_SITE — when the Publish ICP-Service is installed. Any agent that
  // can build a site can ASK to ship it; the boss's stamp does the shipping
  // (Ship-to-chain, DRIVER_CONTRACT §7 — one approval per deploy, and the
  // approval carries agentId so the coworker walks to the boss desk, §4).
  // Bound per-agent so the tip jar credits the PUBLISHING agent's wallet.
  // Tip default: on whenever the Wallet service is installed; opt out per
  // publish with a trailing " : tip=off". The flag is stripped with a
  // tail-anchored regex — never split the arg on ':' (C:\... paths survive).
  if (icpPublishEnabled()) {
    const pubAgentId = agent.id || String(agent.name || 'agent').replace(/[^A-Za-z0-9_-]+/g, '_');
    const pubAgentName = String(agent.name || 'a coworker');
    out.push({
      ...TOOL_REGISTRY.publish_site,
      run: async (arg) => {
        let raw = String(arg || '').trim();
        let tip = icpWalletEnabled();
        const flag = /\s*:\s*tip\s*=\s*(on|off)\s*$/i.exec(raw);
        if (flag) { tip = flag[1].toLowerCase() === 'on' && icpWalletEnabled(); raw = raw.slice(0, flag.index).trim(); }
        if (!raw) return 'PUBLISH_SITE needs a folder or index.html path — nothing queued.';
        try {
          window.dispatchEvent(new CustomEvent('cafresohq:publishRequest', {
            detail: { agentId: pubAgentId, agentName: pubAgentName, path: raw, tip },
          }));
        } catch (e) { return `Couldn't queue that publish — ${e && e.message || e}`; }
        return `Asked the boss to publish "${raw}" — waiting for the stamp. Nothing is public yet.`;
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
    /* "STOP" is procedural and small models read straight past it. The
       failure it is meant to prevent has a name, so name it: writing the
       answer you expect. Observed live — a coworker emitted [MEMORY_LIST]
       and, in the same breath, listed three files for a vault created
       minutes earlier. The runtime now truncates at the marker
       (upToToolCall), which stops that reaching the next turn; this is the
       cheaper half, asking the model not to write it at all so the boss
       never watches it stream past either. */
    'Rules: only one tool call per turn; only invoke tools listed above; if a question needs no tool, just answer.',
    'NEVER write a tool\'s result yourself. After the call, stop. If you have not been handed a result, you do not have one — do not guess it, summarise it, or list what you think it contains.',
    'Use the real value, never the example: [BROWSER_FETCH: <url>] is the shape, not a request. A call whose argument is still a placeholder is refused and nothing is looked up.',
    /* A marker written INSIDE a sentence survives every strip we have, on
       purpose: stripToolMarkers only removes lines that are entirely one
       marker, because cutting one out mid-sentence leaves a broken sentence.
       Both comments on that decision call it a prompt problem, so this is
       the prompt half finally being written.
       Seen in a filed deliverable — the note a boss opens months later:
       "I've created a new note at [VAULT_NEW: projects/local_file_access.md]
       to store my thoughts". The marker is not a call there, it is the
       coworker narrating its own plumbing into a kept record.

       Led on "inside a sentence" until 2026-08-07, and a local model read
       that narrowly: asked to file, it produced

         **Vault Path:** [VAULT_NEW: Research/pears.md]

       — not a sentence, so not covered, and the delivery kept it. The rule
       now leads with POSITION instead of grammar, because a label, a bullet,
       a heading and a table cell are all "not a sentence" and all put the
       marker off column zero, where the line-anchored strip cannot reach it
       and the parser never sees a call.

       RE-TESTED after this rewrite, and it changed nothing: the same 8B local
       model produced "**Vault Path:** [VAULT_APPEND: Research/pears.md]" on
       the very next task, and bled the previous task's pears into a request
       about plums. The rule is more precise and a capable model should follow
       it — but do not read it as a fix. It is another data point for the
       standing note that no instruction makes a small model honest.

       What held again, unprompted, is downstream: the delivery carried
       "Nothing opened, saved or looked up for this one." four lines under the
       invented path. */
    'A marker must be ALONE on its line: nothing before it, nothing after — no label, no bullet, no heading, no bold, no quotes. "**Vault Path:** [VAULT_NEW: notes.md]" is not a call; it is machine syntax in a record the boss keeps, and the file never gets written. If you are TELLING the boss what you did rather than doing it, use plain words instead ("saved it to work/notes.md").',
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
    'NEVER write the result yourself. If you have not been handed one, you do not have one — do not guess it or list what you think it contains.',
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
/* ── Don't hand a coworker back its own guesswork ─────────────────────────
   Every tool hop pushes the model's text back as its own turn, immediately
   followed by the real `[TOOL_RESULT: …]`. That is right for the text
   BEFORE the tool marker. It is wrong for everything after it.

   Anything the model wrote after emitting a call was produced before the
   tool ran, so by construction it cannot be based on the result — and a
   small model will happily write the result it expects. Caught on a clean
   first run: Llama emitted `[MEMORY_LIST]` and, in the same breath,
   "Here are the notes in my private memory folder: decisions/auth.md,
   preferences.md, projects/mdc.md" — three files invented for a vault
   created minutes earlier.

   The old behaviour then fed that invention back as something the coworker
   had SAID, and put the true (empty) listing underneath it as a
   contradiction. That is the worst available framing: it establishes the
   fabrication as prior context and asks the model to reconcile.

   Cutting at the marker is the honest boundary. The coworker still sees it
   asked for the listing; what it never sees is the answer it made up.
   `raw` is the exact matched text and every detector path supplies it
   (bracket, JSON and harmony), so an unrecognised shape leaves the buffer
   untouched rather than truncating something real. */
/* ── A template is not an argument ────────────────────────────────────────
   Caught on a clean run: a coworker emitted `[BROWSER_FETCH: <url>]` —
   copying the shape straight out of its own tool docs — and the office
   dutifully executed it, spent one of the four tool hops, and put

     🌐 Read <url>
     Browser fetch error: url must start with http:// or https://

   on the floor as a real visit. It was never a real attempt. §4 says a prop
   visit plays only while that tool is REALLY running; running a placeholder
   makes the animation honest about something that shouldn't have happened.

   The rule is deliberately narrow: the WHOLE argument is a single
   angle-bracket token. `<url>`, `<path>`, `<your-file.md>` are unambiguously
   template syntax — no real path, query or URL is shaped that way. Anything
   with content outside the brackets ("see <a>", "a<b") is left alone,
   because a wrong refusal costs the boss a real tool call.

   The model gets a correction rather than silence, which is the whole
   point: an unexecuted call that says nothing invites the coworker to
   invent the result (see upToToolCall above). */
const PLACEHOLDER_ARG = /^\s*<[^<>]*>\s*$/;

function placeholderRefusal(name, arg) {
  if (!PLACEHOLDER_ARG.test(String(arg == null ? '' : arg))) return null;
  return `[NOT RUN] "${String(arg).trim()}" is the example from the ${name} instructions, not a real value. `
       + `Nothing was looked up. Send ${name} again with the actual value, or answer without it.`;
}

function upToToolCall(text, raw) {
  const s = String(text || '');
  if (!raw) return s;
  const i = s.indexOf(raw);
  if (i === -1) return s;
  return s.slice(0, i + String(raw).length);
}

function detectToolCall(text, tools) {
  /* A marker a coworker wrote while THINKING is not a call. Measured
     2026-08-16 (office 9280): a brain reasoned "I could run [VAULT_READ:
     Reports/q3-summary.md] to look — but that file almost certainly does
     not exist yet … better to simply ask the boss", and the office ran the
     read it had just talked itself out of, then showed the boss the snag.
     Deliberating about a tool is the opposite of calling it, and every
     detector below has to agree about that, so the mask goes here rather
     than in each of them. See maskReasoning for why it blanks in place. */
  const scan = maskReasoning(text);
  const jsonCall = detectJsonToolCall(scan, tools);
  if (jsonCall) return jsonCall;
  for (const t of tools) {
    const m = String(scan).match(t.re);
    if (m) return { tool: t, arg: m[1], body: m[2] || '', raw: m[0] };
  }
  /* A [DM_TO: name] opener whose [/DM_TO] simply never got emitted.
     Observed twice, both documented in this file: an 8B Claude-family
     local model (the orphan-tag note above), and -- found by capturing
     the exact bytes gemma-4-e4b streamed back through the real proxy,
     not a guess -- 3 consecutive live misses today that looked like a
     prompt regression and were not. The raw SSE was "[DM_TO: Nano]" on
     its own line followed by "What is 4+4?", full stop. The model asked
     the right question, in the right shape, and simply stopped
     generating instead of adding the four-token closer.

     The existing fix for this shape (ORPHAN_TAG_RE) only cleans it up
     for DISPLAY -- it deletes the opener line, which quietly turned
     Gemma's hand-off attempt into a non-sequitur: the boss saw a
     coworker asking THEM "What is 4+4?" out of nowhere, because Nano
     never got the question and the office never knew a hand-off had
     been attempted at all.

     Delegated to extractAllDMs (below) rather than re-implemented here,
     so dispatch and display -- visibleReply calls the very same
     function -- can never disagree about what counts as a recovered
     hand-off. Third time this session a "two sources, one rule" split
     has been the actual bug (the seed-swarm tooltip, the picker's
     offline fallback, the approval scan reading stripped text). Safe to
     call post-stream, which every caller of detectToolCall already is --
     both `await` the full response before reaching this line. */
  const recovered = extractAllDMs(scan);
  if (recovered.length) {
    const dmTool = tools.find(t => t.name === 'DM_TO');
    if (dmTool) {
      const last = recovered[recovered.length - 1];
      return { tool: dmTool, arg: last.to, body: last.body, raw: '' };
    }
  }
  // Fall back to harmony format: gpt-oss-20b, qwen-3, and other OSS models
  // emit tool calls as <|channel|>commentary to=NAME<|message|>{…json…}
  // We map the harmony name to one of our registered tools and extract
  // the arg from common JSON keys.
  const h = extractHarmonyToolCalls(scan);
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
  const { provider } = CafresoHQClient.parseModelId(model);
  if (['anthropic', 'cafresohq', 'claudecode', 'codex', 'google'].includes(provider)) return true;
  const capableLocal = ['qwen3', 'mistral-nemo', 'llama-3.3', 'deepseek'];
  return capableLocal.some(n => (model || '').toLowerCase().includes(n));
}

/* ── The third wire format for "this is not for the boss" ─────────────────
   A reasoning model's chain of thought reaches this office three ways, and
   until this change only two of them were handled:

     1. `delta.reasoning_content`, its own SSE field. Routed to the
        onReasoning channel in claude-client.jsx and dropped when nobody
        claims it — and nobody does, so the office's shipped answer for a
        brain's private reasoning is "drop it". Fixed when LM Studio's
        gemma-4 opened a FILED message with "💭 Thinking Process: 1.
        **Analyze the Request:** The user is asking me to...".
     2. `<|channel|>analysis<|message|>…`, harmony. Removed whole by
        cleanHarmony below, whose own comment states the rule outright:
        "chain of thought and tool calls are not for the boss".
     3. `<think>…</think>`, inline in `delta.content` — deepseek-r1, qwen3,
        and everything Ollama's OpenAI-compatible endpoint serves. Matched
        by nothing, anywhere in the tree.

   The note that fixed (1) ends "One concept, two wire formats, and only one
   of them was handled." It was three. Which one a boss meets is not a
   property of the model they hired: the SAME deepseek-r1 splits its
   thinking into `reasoning_content` through one local runtime and inlines
   `<think>` through another, so the identical thought was silently dropped
   or pasted into the bubble depending on which daemon happened to be
   running. Same brain, same thought, opposite treatment — which is the
   whole of it, on a product whose point is that the brain is swappable.

   Measured 2026-08-16, office 9280, canned brain on the LM Studio door: the
   boss's bubble carried the tags and the full deliberation, and because the
   tool parser had already eaten the marker inside the reasoning, the
   sentence arrived mutilated — "I could run  to look". The office deleted
   the evidence of what it was about to do, and then did it.

   The tag list IS a list, and #73's lesson is that a list silently stops
   being complete. It stays narrow on purpose: these four delimiters only
   ever appear as reasoning scaffolding, and a wrong strip costs the boss
   real words — worse than a leaked tag. An unknown fifth convention leaks
   visibly, as text, which is the failure direction to prefer. */
/* Built inside a function, cached on first call, rather than as five
   module-level consts. Eight suites lift `cleanHarmony` out of this file by
   name and run it under node; a lifted function whose dependency is a bare
   const needs the const lifted too, at every one of those call sites, and
   the failure is a ReferenceError deep in a harness rather than anything
   legible. One liftable name is one line in a tuple those suites already
   keep. The regexes are stateless apart from REASONING_CLOSED's /g lastIndex,
   which every use resets via String.replace. */
function reasoningPatterns() {
  if (reasoningPatterns._cache) return reasoningPatterns._cache;
  /* Declared HERE, not at module scope, for the same reason the patterns
     are: the suites that lift this function lift functions only, and a
     free const in the body is a ReferenceError they cannot see coming.
     scripts/test_reasoning_is_not_the_bosss.py compares this string to
     night_runner.REASONING_TAGS, so the two cannot drift. */
  const REASONING_TAGS = 'think|thinking|reasoning|reflection';
  const T = REASONING_TAGS;
  /* An opening tag that has not finished ARRIVING. #75's lesson one level
     down: that fix was "the word `final` alone in the bubble", a frame where
     the stream had emitted `<|channel|>final` but not yet `<|message|>`, and
     the pattern required the token that was missing. Same shape here — the
     frame whose buffer ends `…<think` has no `>` yet, so the opener pattern
     cannot match and the boss reads a stray `<think` for one frame. Found by
     sweeping every prefix of the measured reply rather than by reasoning
     about it: it was 1 frame in 442.

     Derived from REASONING_TAGS rather than written out, so the partial can
     never disagree with the whole. At least one letter is required — a lone
     trailing `<` is ordinary prose far more often than it is a tag
     starting. */
  const partial = T.split('|')
    .flatMap(t => Array.from({ length: t.length }, (_, i) => t.slice(0, i + 1)))
    .sort((a, b) => b.length - a.length).join('|');
  return (reasoningPatterns._cache = [
    // closed: opener, thought, closer
    new RegExp('<(' + T + ')\\b[^>]*>[\\s\\S]*?<\\/\\1\\s*>', 'gi'),
    // a closer with no opener — some deepseek-r1 builds send the thought
    // first and mark only where it ends
    new RegExp('^[\\s\\S]*?<\\/(?:' + T + ')\\s*>', 'i'),
    // an opener with no closer — EVERY mid-stream frame, plus any reply cut
    // off inside the thought
    new RegExp('<(?:' + T + ')\\b[^>]*>[\\s\\S]*$', 'i'),
    new RegExp('<(?:' + partial + ')$', 'i'),
  ]);
}

function stripReasoning(text) {
  const s = String(text || '');
  if (s.indexOf('<') < 0) return s;
  let out = s;
  for (const re of reasoningPatterns()) out = out.replace(re, '');
  return out === s ? s : out.trim();
}

/* Blank reasoning blocks to EQUAL LENGTH — the "did they actually do this"
   half, for every function that reads a raw buffer to decide whether a
   coworker called a tool, asked for a stamp, or handed work over.

   Equal-length blanking rather than deletion because `detectToolCall`
   returns the matched text as `raw` and `upToToolCall` then finds it by
   index in the ORIGINAL buffer; removing bytes here would cut the reply at
   the wrong place. Newlines are preserved so line-anchored patterns outside
   the block still see the same line structure. */
function maskReasoning(text) {
  const s = String(text || '');
  if (s.indexOf('<') < 0) return s;
  const blank = (m) => m.replace(/[^\n]/g, ' ');
  let out = s;
  for (const re of reasoningPatterns()) out = out.replace(re, blank);
  return out;
}

/* Strip harmony channel/message/end tags from a block of text, keeping only
   the "final" channel content (what the user is meant to see). Non-harmony
   text passes through unchanged.

   Reasoning blocks go first, and this function is where they go because it
   is the one chokepoint every reply passes: throttleTokens.flush() runs it
   per animation frame for the live bubble, and all ten final-text recipes
   wrap it around visibleReply. A separate seam would be a second place to
   keep in sync, which is the split this file has already been bitten by
   three times. The name stays `cleanHarmony` — it is exported and read in
   six suites — so the docstring carries what it actually does. */
function cleanHarmony(text) {
  const t = stripReasoning(text);
  if (!t || t.indexOf('<|') < 0) return t;
  let out = String(t);
  /* Remove every channel block that is not `final`, content and all —
     chain of thought and tool calls are not for the boss. Match up to the
     next channel/end/call/return marker.

     This named the two channels it knew, `analysis` and `commentary`, and
     kept the content of anything else. Found by sweeping this function
     against a stream carrying a third: a model that writes

         <|channel|>critic<|message|>Too terse.<|end|>
         <|channel|>final<|message|>Rewritten.<|return|>

     put "Too terse.Rewritten." in the coworker's bubble — an internal
     critique welded onto the front of the answer, reading as though the
     coworker said both. The docstring above has always said this function
     keeps the final channel and only the final channel; it enumerated
     instead, and an enumeration is a list that silently stops being
     complete (#73). Now the rule is the one that was written down: not
     final, not shown. */
  out = out.replace(
    /<\|channel\|>\s*(?!final\b)[A-Za-z0-9_.]*[\s\S]*?(?=<\|channel\||<\|end\|>|<\|call\|>|<\|return\|>|$)/g,
    ''
  );
  /* Any remaining channel header, and the header is framing whatever it is
     called. This used to require the literal name `final` AND a closing
     `<|message|>`; anything else fell through to the catch-all below, which
     removes the TAG and leaves the channel NAME sitting in the reply as
     prose.

     Measured on screen, office 9262, 2026-08-15, gpt-oss-20b through LM
     Studio: a coworker's entire reply, in their own bubble, was the single
     word

         final

     — a stream that stopped at `<|channel|>final` before the model got to
     `<|message|>`. Reproduced deterministically against this function. The
     same input truncated one channel earlier vanishes correctly, because
     the analysis/commentary regex above eats its whole block; `final` is
     the one channel whose content is KEPT, so it is the one whose header
     had to be matched exactly, and the one that leaks when it isn't.

     Two things are deliberate. The name is optional and unenumerated —
     #73's lesson one level down, that a list of names is a list which
     silently stops being complete, and a channel this office has never
     heard of must not become the coworker's first word either. And
     `<|message|>` is optional, because that is precisely the token that
     was missing. The word "final" in ordinary prose is untouched: nothing
     matches without the literal `<|channel|>` in front of it.

     A truncated stream now cleans to empty, which is what it is, and the
     empty reply already has an honest line of its own. */
  out = out.replace(
    /<\|channel\|>\s*[A-Za-z0-9_.]*\s*(?:to=[^\s<]+\s*)?(?:<\|constrain\|>\w+\s*)?(?:<\|message\|>)?/g,
    ''
  );
  /* Subsumed by the line below it, which matches any `<|…|>` at all —
     deleting this one changes no output, and the fire-test for this fix
     proved it by deleting it. Kept as documentation of the tokens that
     are expected here; do not read it as a guard. The catch-all is the
     guard, and it is the one carrying an unknown token like `<|refusal|>`. */
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

/* Which JSON key holds the ARGUMENT, and which holds the BODY.

   This used to be a switch with a case per tool and `default: { arg:
   payload }` underneath, which covered ten of the office's thirty-one
   tools. The other twenty-one — every file, export, publish, memory and
   wallet tool, i.e. the entire surface on which a coworker produces
   something the boss keeps — fell through, and the WHOLE JSON OBJECT was
   handed over as the argument.

   Reproduced on office 9262, 2026-08-15, gpt-oss-20b via LM Studio. The
   boss asked for a landing page at site/index.html. The model got it
   exactly right:

     <|channel|>commentary to=FILE_WRITE <|constrain|>json<|message|>
     {"path":"site/index.html","content":"<!DOCTYPE html>\n…"}

   The office took that entire string as the path. Every `/` in the HTML —
   `</title>`, `</head>`, `</h1>`, `</p>`, `</body>`, `</html>` — became a
   directory separator, so the workspace got a seven-level tree of
   directories named after fragments of the boss's own web page, with an
   empty file at the bottom. The visit block read:

     Saved {"path":"site/index.html","content":"<html>… in the project
     Wrote 0 chars → …/sp62/{"path":"site/index.html","content":"…

   "Saved" and "0 chars", in the same block, about a path nobody asked for.
   §4: the office said work happened. Nothing did.

   So the mapping is now driven by key lists with a generic default, and a
   tool added later is covered without anyone remembering to come back
   here. That is the whole lesson: an allow-list of tools is a list that
   silently stops being complete. */
const JSON_ARG_KEYS = ['path', 'file', 'filename', 'filepath', 'file_path',
  'dir', 'directory', 'folder', 'query', 'q', 'search', 'url', 'link',
  'command', 'cmd', 'to', 'name', 'agent', 'recipient', 'coworker', 'target'];
/* `prompt` is deliberately body-only. GENERATE_IMAGE takes a vault path as
   its argument and the description as its body; if a model sends only a
   prompt there is no path, and using the description as one would put us
   right back to writing files named after their own contents. */
const JSON_BODY_KEYS = ['content', 'body', 'text', 'message', 'details',
  'description', 'outline', 'prompt'];

/* Per-tool key lists, for the ones whose argument is not a path or a query.
   These reproduce the old switch exactly — the point of the rewrite is the
   DEFAULT, not a change of behaviour for the tools that already worked. */
const JSON_KEYS_BY_TOOL = {
  SEARCH:            { arg: ['query', 'q', 'search'] },
  VAULT_SEARCH:      { arg: ['query', 'q'] },
  VAULT_READ:        { arg: ['path', 'file'] },
  VAULT_APPEND:      { arg: ['path', 'file'], body: ['content', 'body', 'text'] },
  VAULT_NEW:         { arg: ['path', 'file'], body: ['content', 'body', 'text'] },
  DM_TO:             { arg: ['to', 'name', 'agent', 'recipient'], body: ['message', 'body', 'text', 'content'] },
  HANDOFF_TO:        { arg: ['to', 'name', 'agent', 'recipient', 'specialist'], body: ['message', 'body', 'text', 'content'] },
  SPAWN_SUBAGENT:    { arg: ['role', 'specialty', 'kind'], body: ['task', 'description', 'brief', 'body', 'message'] },
  REQUEST_ELEVATION: { arg: ['reason', 'why', 'summary', 'arg'], body: ['details', 'rationale', 'body', 'message'] },
  PEER_JOURNAL:      { arg: ['name', 'coworker', 'agent', 'who'] },
};

/* Map a harmony JSON payload to the {arg, body} our tool runners expect. */
function harmonyArgsFor(tool, payload) {
  let parsed = null;
  try { parsed = JSON.parse(payload); } catch (_e) {}
  const isObj = parsed && typeof parsed === 'object' && !Array.isArray(parsed);
  /* A payload that is not a JSON object is the argument, verbatim — a bare
     query string or path is a perfectly ordinary thing for a model to send
     and always worked. Only the OBJECT case was broken. */
  if (!isObj) return { arg: payload };

  const get = (keys) => {
    for (const k of keys) {
      if (parsed[k] == null) continue;
      const v = parsed[k];
      if (typeof v === 'object') continue;   // an object is not an argument
      return String(v);
    }
    return null;
  };
  const spec = JSON_KEYS_BY_TOOL[tool.name] || {};
  const body = get(spec.body || JSON_BODY_KEYS) || '';

  /* Composed arguments: two tools take one string built from two fields. */
  if (tool.name === 'HIRE_AGENT' || tool.name === 'HIRE_ASSISTANT') {
    const name = get(['name', 'agent_name', 'agentName', 'title']);
    const role = get(['role', 'specialty', 'position']);
    const arg = (name && role) ? (name + ' · ' + role)
      : name || get(['nameAndRole', 'name_and_role']) || '';
    return { arg, body: get(['rationale', 'reason', 'details', 'body', 'message']) || '' };
  }
  /* WALLET_SEND is deliberately NOT mapped. Its argument is a compound —
     `<token> <amount> <to-principal> : <memo>` — and a generic key match
     would build a plausible-looking one out of whichever fields happened to
     be present. Every other tool on this list fails by doing nothing; this
     one would fail by moving somebody's money. An unmapped argument stops
     it, which is the correct outcome for a transfer nobody can parse. */
  if (tool.name === 'WALLET_SEND') return { arg: '', body };

  /* No key matched. The office does not know what was meant, and the one
     thing it must not do is hand the raw object on as if it did — that is
     the defect this whole block exists for. An empty argument fails the
     tool, which the boss sees as a failed visit rather than as a save. */
  return { arg: get(spec.arg || JSON_ARG_KEYS) || '', body };
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
Specialists save large deliverables (notes, reports, drafts, analyses over ~200 words) to the Library and return the path. You do NOT paste raw markdown/HTML/long content into chat.

When relaying back: cite the Library path and give a 1-3 sentence summary. Only paste full content if the boss explicitly asks "show me the raw text".

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
- After parallel DM_TOs return, give the boss ONE combined reply with the synthesized result and any Library paths.`;

/* `selfName` is who this transcript is being built FOR, and it decides who
   the `assistant` turns belong to. Omit it and the recipient is the chief
   of staff (ceoStream); pass a coworker's name and the recipient is that
   coworker.

   Without it, every reader got the CEO's turns as `assistant` — and
   `assistant` is not decoration, it is the one role every chat API defines
   as "you said this". Measured on a canned brain, the request sent to a
   newly hired Vera (system prompt: "You are Vera, a specialist coworker")
   opened with three assistant turns she had never spoken:

     assistant  Welcome to your HQ — I'm CafresoHQ, your chief of staff…
     assistant  We don't have a shared brain here… I'm opening the
                candidate book now…
     assistant  Welcome aboard, Vera! I've set up a desk.
     user       [Direct request from the boss]: hello

   So Vera was shown greeting herself, and shown claiming to be the chief
   of staff. Meanwhile her OWN prior replies arrived as `[Vera · Role]: …`
   under `user` — the mirror image of the same error. The only turns marked
   as hers were the ones she did not say, and none of the ones she did.

   A small local brain reads that as an instruction about who it is; this
   is precisely the failure that ends with a specialist answering in the
   chief of staff's voice. It is also the most runtime-agnostic surface in
   the product — every brain, local or hosted, is handed this envelope — so
   getting authorship right here is worth more than any per-provider fix.

   The peer form on the last line was always the correct shape for a third
   party. The CEO simply is one, whenever the reader is not the CEO. */
function chatToMessages(chat, { omitLastCeo = false, selfName = '' } = {}) {
  const src = (omitLastCeo && chat.length && chat[chat.length - 1].from === 'ceo')
    ? chat.slice(0, -1) : chat;
  /* Bubbles are captioned `${name} · ${role}`; the name is what identifies
     the speaker across a role edit. */
  const speaker = (m) => String(m.name || '').split(' · ')[0].trim();
  const out = [];
  for (const m of src) {
    /* stripOfficeVoice: the office's report of its OWN actions must not
       re-enter the model's context as prior conversation. Measured — a
       coworker that had seen real `📡 …→` echoes in history wrote its own,
       with a fabricated result and an invented vault path, in a bubble
       where the real read had just returned nothing. This is the single
       choke point where stored chat becomes prompt, so it is the place to
       stop it. Result bodies survive; only the template goes. */
    const text = stripOfficeVoice(m.text);
    /* Whether this bubble is the READER's own past turn, decided once
       here because the tool-visit replay below has to ask the same
       question and must not answer it differently. */
    let mine;
    if (m.from === 'user') { mine = false; if (text) out.push({ role: 'user', content: text }); }
    /* `m.from !== 'ceo'` guards the self branch as well as the CEO branch:
       a coworker who happened to be named CafresoHQ must not inherit the
       chief of staff's turns as their own. */
    else {
      mine = m.from === 'ceo' ? !selfName : (!!selfName && speaker(m) === selfName);
      if (text) {
        out.push(mine ? { role: 'assistant', content: text }
                      : { role: 'user', content: `[${m.name}]: ${text}` });
      }
    }
    /* What the tools actually came back with.

       The office has held this all along — `toVisit` puts each result on
       the message as `body` — and it never went back to the brain, because
       everything above reads `m.text` and a visit is not in the text. So a
       run that spent its hop budget was told by the office that asking
       again would pick it up, and the re-ask arrived carrying the
       coworker's own "let me go and look" with not one byte of what
       looking had found. Measured 2026-08-16 on office 9280: four
       VAULT_READs of a file containing ZEPHYR-QUOTA-8841, the boss re-asks
       exactly as instructed, and the request on the wire held no
       TOOL_RESULT turn, no file content and no sentinel — only "Let me
       check the vendor notes on file before I answer." four times over.

       `head` and `icon` stay behind. That is the office's REPORT of the
       trip — the template a model once learned to forge — and leaving it
       out is the rule this function already enforced one line up: result
       bodies survive, the office's voice does not. What does go back is
       the protocol frame the brain is shown on every hop of a LIVE run,
       so a resumed turn reads exactly like the turn it resumes.

       Only on `mine`. Replaying another coworker's trip as this one's own
       work would be the office attributing a visit to somebody who never
       made it — and for a reader who is not the CEO, that includes the
       chief of staff's. Their turns are already quoted as `[Name]: …`,
       which is hearsay, and hearsay is where somebody else's results
       belong. */
    if (!mine) continue;
    for (const v of (m.visits || [])) {
      const body = v && typeof v.body === 'string' ? v.body.trim() : '';
      if (!body) continue;
      /* Visits stored before this change carry no tool name. A frame with
         no name is still honest — a result came back — and it beats both
         dropping a body the coworker earned and naming a tool that might
         not be the one that ran. */
      if (v.name) {
        out.push({ role: 'assistant',
                   content: v.arg ? `[${v.name}: ${v.arg}]` : `[${v.name}]` });
      }
      out.push({ role: 'user',
                 content: `${v.name ? `[TOOL_RESULT: ${v.name}]` : '[TOOL_RESULT]'}\n${body}` });
    }
  }
  return out;
}

function rosterSummary(agents) {
  /* §6 starts HERE. The office scrubbed "sub-agent" from its own copy, but
     kept TELLING the model that is what its colleagues are — so the model
     echoed it straight back onto the floor. Protocol tokens below stay
     verbatim (SPAWN_SUBAGENT is wire format); only the English changes. */
  if (!agents || !agents.length) return 'No coworkers hired yet.';
  return 'Your coworkers:\n' + agents.map(a =>
    `- ${a.name} (${a.role}) — status: ${a.status}, tools: ${(a.tools||[]).join(', ') || 'none'}`
  ).join('\n');
}

/* How many memory entries actually reach a prompt. Exported because the
   Memory Shelf tells the boss what happens to what they save — and an
   unqualified "folded into every prompt" stops being true the moment the
   shelf outgrows this number. One constant, so the copy and the runtime
   can't drift apart. Entries are newest-first, so this keeps the newest. */
const MEMORY_PROMPT_CAP = 24;

function memorySummary(memory) {
  if (!memory || !memory.length) return '';
  return 'Long-term memory (notes CafresoHQ has saved about the boss & ongoing work):\n' +
    memory.slice(0, MEMORY_PROMPT_CAP).map(m => `  [${m.tag}] ${m.text}`).join('\n');
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
    // Matches the date STORED on the entry (app.jsx), so the work log the
    // coworker reads and the one the boss reads agree on what day it was.
    const when = e.date || (e.at ? officeDate(new Date(e.at)) : '');
    lines.push(`  [${when}] ${(e.summary || '').slice(0, 120)}`);
  }
  return lines.join('\n');
}

function buildCeoSystem(agents, extra) {
  const parts = [CEO_SYSTEM, rosterSummary(agents)];
  const mem = memorySummary(HQ && HQ._memory);
  if (mem) parts.push(mem);
  if (extra) parts.push(extra);
  return parts.join('\n\n');
}

/* Cache the registry snippet for a short window — sub-agents in a meeting all
   stream within seconds of each other, so refetching per call is wasteful.
   Invalidated whenever settings change (provider/URL swaps, etc.). */
const REGISTRY_TTL_MS = 10_000;
let _registryCache = { at: 0, value: '', inflight: null };
if (CafresoHQClient && CafresoHQClient.onSettingsChange) {
  CafresoHQClient.onSettingsChange(() => {
    _registryCache = { at: 0, value: '', inflight: null };
  });
}
async function registrySnippet() {
  const now = Date.now();
  if (now - _registryCache.at < REGISTRY_TTL_MS) return _registryCache.value;
  if (_registryCache.inflight) return _registryCache.inflight;
  _registryCache.inflight = (async () => {
    try {
      const reg = await CafresoHQClient.localRegistry();
      const value = CafresoHQClient.formatRegistry(reg);
      _registryCache = { at: Date.now(), value, inflight: null };
      return value;
    } catch (_e) {
      _registryCache.inflight = null;
      return '';
    }
  })();
  return _registryCache.inflight;
}

/* `prompt` and `chat` are ALTERNATIVES, not a prompt plus its history:
   pass `chat` and `prompt` is never read. That is right for the send path,
   where the boss's message is already the last entry in `chat` and adding
   it again would double the turn — and it is a trap for anyone else. The
   fan-out synthesis passed both for as long as it existed, so the one
   instruction that block is built around ("Here are their replies… now
   synthesize") was dropped on the floor by this line; the office re-ran
   the conversation instead. Named here because the call site cannot see
   it: a discarded argument raises no error and logs nothing. */
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

  /* Accumulated across hops, not read off the last one — the same
     arithmetic agentStream does. A reach on hop 1 is still a reach when
     hop 3 is the one that ends up empty. */
  const reachedFor = new Set();
  const CEO_HAS = new Set(ceoTools.map(t => t.name));
  const KNOWN_MARKERS = Object.keys(TOOL_REGISTRY).map(k => TOOL_REGISTRY[k].name);
  /* Same distinction agentStream draws (see its own comment): a hop that
     ran a tool and then came back empty is not "offline or busy", it is
     legwork with no write-up. Without this the CEO got the generic
     brain-may-be-busy line even right after it had just read the vault. */
  let toolsExecuted = 0;

  for (let hop = 0; hop < MAX_TOOL_HOPS; hop++) {
    let buf = '';
    await CafresoHQClient.stream({
      system: sys,
      messages,
      model: resolveModel(model),
      temperature,
      onToken: tok => { buf += tok; onToken(tok); },
      onUsage,
      signal,
      maxTokens,
    });
    /* Recorded before the tool-call check, so a hop that DOES fire a tool
       still contributes any second, ungranted marker it opened. */
    for (const n of openedMarkers(buf, KNOWN_MARKERS)) {
      if (!CEO_HAS.has(n)) reachedFor.add(n);
    }
    const call = ceoTools.length ? detectToolCall(buf, ceoTools) : null;
    if (!call) {
      const cleaned = cleanHarmony(buf);
      const emit = (msg) => { if (onHint) onHint(msg); else onToken(msg); };
      if (!cleaned.trim()) {
        const orphans = extractHarmonyToolCalls(buf);
        const missing = [...new Set([...orphans.map(o => o.tool), ...reachedFor]
          .filter(n => !CEO_HAS.has(n)))];
        const note = missing.length ? ceoReachedForNote(missing) : '';
        if (toolsExecuted > 0) {
          emit('_(I did the legwork but never wrote it up. Ask me to summarise what I found.)_');
        } else if (note) {
          emit(note);
        } else if (orphans.length) {
          emit('_(I talked myself through that one and never actually answered. Ask me again.)_');
        } else {
          /* Was: "If they are on a free brain … try Settings → Connections
             → Coworker capability → Lite". Three wrong things. The control
             is labelled "Agent capability", not "Coworker capability"; it
             renders only when `s.provider === 'hermes'`, so it is hidden in
             exactly the free-brain case the sentence invokes; and "they"
             is the office describing itself in the third person. Measured
             on the reproducing office: with the provider on lmstudio, the
             only occurrence of the word "capability" anywhere on the
             Connections screen was this note bleeding through from the
             chat behind it. */
          emit('_(nothing came back from me that time — the brain running this office may be offline or busy. Ask me again in a moment, or check Settings → Connections.)_');
        }
      } else if (reachedFor.size) {
        /* The reply is not empty, so the boss has prose — and the marker
           inside it was stripped before they saw it. Reproduced on port
           9261: "Sure — let me pull the current figure for you." arrived
           on its own, with no figure behind it and no note. Silence there
           is the office endorsing a promise it knows was not kept (§4). */
        const note = ceoReachedForNote([...reachedFor]);
        if (note) emit(note);
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
    /* Did it actually work? Not the same question as "did it return". A
       missing file, a path that isn't a directory, a command that exits
       non-zero — all answer normally, with the explanation as the result,
       because the coworker needs that text to recover. `meta.failed` is the
       server saying so out of band; the throw path below sets it too.
       Without it every surface captioned a failure as a success — watched
       live as "Opened ./site" directly above "Not a directory: ./site". */
    const meta = {};
    try { result = await call.tool.run(call.arg, { signal, meta }, call.body); }
    /* Every tool failure in the office lands here, and the string goes to
       BOTH readers: the coworker, who needs the detail to try something
       else, and the boss, who sees it in the visit block. So keep the
       message — it is all anyone knows — but attribute it rather than
       letting the office appear to be announcing "Error:" in its own voice.
       NOT snagCause: that only classifies brain failures and would label a
       vault or shell error as a sign-in problem. */
    catch (err) { result = `That didn't work — ${err.message}`; meta.failed = true; }
    toolsExecuted++;
    /* The visit does NOT go into the token stream any more.

       Everything in the text channel is forgeable, and a local model
       proved it: having seen real visits in its history it wrote its own,
       office format and all, with an invented result and an invented vault
       path, in a bubble where the real read had returned nothing. Stripping
       the office's voice out of the model's CONTEXT removed the incentive;
       this removes the possibility. A visit is now structured data on the
       `done` event, the UI renders it as its own element, and no sentence
       the coworker can type will ever render as the office speaking.

       `echo` stays on the event: histories written before this change still
       carry the banner inline, and filing removes it by exact match. */
    if (onTool) {
      onTool({ phase: 'done', name: call.tool.name, arg: call.arg, result,
               failed: !!meta.failed,
               echo: `\n\n${toolEchoHead(call.tool.name, call.arg)}\n${result}\n\n` });
    }

    messages.push({ role: 'assistant', content: upToToolCall(buf, call.raw) });
    messages.push({ role: 'user', content: `[TOOL_RESULT: ${call.tool.name}]\n${result}\n\nContinue from where you stopped. Do NOT repeat the tool call.` });
  }
  /* "per-turn tool budget exhausted (12 hops)" told the boss a number
     they cannot change about a limit they did not know existed. What is
     true and useful is that the coworker is still mid-job and asking
     again picks it up. */
  if (onHint) onHint('_(I did as much as I can in one go and stopped there. Ask again and I will carry on from where I left off.)_');
}

async function agentStream(agent, prompt, onToken, { chat, signal, onUsage, onTool, onHint, maxTokens, peers = [], maxToolHops = MAX_TOOL_HOPS, cwd } = {}) {
  const reg = await registrySnippet();
  const claimedRaw = (agent.tools || []).join(', ') || 'none';
  const enabledTools = await toolsForAgent(agent, { peers });
  const enabledNames = enabledTools.map(t => t.name).join(', ') || 'none';

  /* Identity is not the job description, and `||` used to conflate them.

     The NEW HIRE form asks for NAME and ROLE / TITLE in their own fields,
     then pre-fills JOB DESCRIPTION with a generic line ("You are a helpful
     coworker. Be concise and warm."). So EVERY hire made through that form
     arrives carrying a systemPrompt — and a systemPrompt used to replace
     the one sentence in the entire prompt that says who they are.

     Measured in the meeting room, two coworkers, same question. Llama
     (front desk, no systemPrompt, fell through to the default below):
     "I'm Llama, Generalist." Nova (NEW HIRE form, ROLE / TITLE set to
     "Head of Inbox Wrangling", job description left at the pre-filled
     default): "I'm Nova, Web Specialist." The meeting had asked it to
     answer "from your role's perspective". It was not being evasive —
     nothing in its prompt had ever told it what its role was, so it made
     one up, and the boss reads an invented job title in a room they are
     moderating.

     The office collected the name and the role in two dedicated fields
     and then wrote a prompt that mentioned neither. So state identity
     ALWAYS and let systemPrompt be what the form calls it: the job
     description. Every OPENSWARM_ROSTER persona already opens with "You
     are <Name>, the <Role>", so for the cast this restates rather than
     contradicts; for the transient helper (app.jsx) and the assistant
     hire it fills in a name they never had. */
  const identity = `You are ${agent.name}, a specialist coworker at CafresoHQ. Role: ${agent.role}.`;
  /* The office's own MUST, and the one instruction here it can check
     before issuing. A coworker with no VAULT_NEW who is ordered to file
     hands the boss a path with no file; the rule's actual purpose — keep a
     long deliverable out of the chat log — survives without it, so the
     no-vault version asks for the same restraint and drops the order.
     `enabledNames` is already computed above from `toolsForAgent`. */
  const canFile = enabledTools.some(t => t.name === 'VAULT_NEW');
  const fileDelivery = canFile
    ? `

FILE-DELIVERY RULE: Any deliverable longer than ~200 words (notes, drafts, reports, analyses, summaries) MUST be saved to the Library using [VAULT_NEW: <path>]…[/VAULT_NEW] or [VAULT_APPEND: <path>]…[/VAULT_APPEND]. In your chat reply, return ONLY a 1-3 sentence summary plus the Library path. Do NOT paste the full content into chat unless the boss explicitly asks for the raw text. Suggested paths: Research/<topic>.md for findings, Drafts/<topic>.md for drafts, Reports/<topic>.md for analyses.`
    : `

FILE-DELIVERY RULE: There is no Library wired up this session, so there is nowhere to file a long deliverable — keep it in your reply and keep it tight. Do not claim you saved anything to a path.`;
  const base = agent.systemPrompt
    ? `${identity}\n\n${agent.systemPrompt}`
    : `${identity} Be concise (2-4 sentences), report progress honestly, and flag anything that needs the boss's decision.${fileDelivery}`;
  /* The boss's half of the prompt, reconciled against what was granted.
     Computed from the assembled text rather than by editing the four
     shipped personas, because JOB DESCRIPTION is a field the boss types
     into — a fix that only knew about Kip's sentence would not survive
     the first custom hire. */
  const ordered = orderedButNotGranted(
    base, Object.values(TOOL_REGISTRY).map(t => t.name), enabledTools.map(t => t.name));
  const plural = ordered.length > 1;
  const orderedNote = ordered.length
    ? `\n\nCONTRADICTION IN YOUR BRIEF: the job description above tells you to use ${ordered.join(', ')}, but ${plural ? 'those are' : 'that is'} NOT wired up this session. Ignore that instruction — do not emit the marker${plural ? 's' : ''}, and do not describe the result as though it happened. If the job genuinely needs ${plural ? 'them' : 'it'}, say so plainly in your reply and stop there.`
    : '';
  const toolsNote = enabledTools.length
    ? `\n\nClaimed capabilities: ${claimedRaw}. Of these, the following are wired up for real execution: ${enabledNames}. ONLY invoke these exact tools using the bracketed format described in the TOOL CALLS section. Do NOT invent functions, do NOT use OpenAI/harmony \`commentary to=\` syntax, do NOT call any tool not in this list. If a request needs a tool you don't have, say so plainly in plain text and suggest the user @-mention a coworker who does.`
    : (agent.elevated
      ? ''
      : `\n\nClaimed capabilities: ${claimedRaw}. NONE are wired up for real execution this session. Do NOT emit tool calls of any form (no bracketed markers, no harmony commentary, no JSON function calls). If a request needs a tool, say so plainly in plain text. You may discuss your capabilities conceptually but cannot actually invoke them.`);
  const elevatedNote = agent.elevated
    ? `\n\nELEVATED SESSION: You have native computer access through Claude Code on the proxy machine. Use your built-in agentic capabilities to work with files and run commands directly — do not claim you lack access.`
    : '';
  /* Every finalize in the app listens for [NEEDS_APPROVAL] (chat, task,
     delegate — extractApproval at each), but only the CEO's system prompt
     ever taught the marker. Watched live: a coworker told to "get the
     boss's approval" invented its own bracket — [Approval Request: …] —
     which matched nothing, so no tray appeared and the ask silently
     became decoration. Teach it HERE because this is the one prompt every
     coworker run passes through, whatever door the work came in by. */
  const approvalNote =
    `\n\nAPPROVAL: before an action that sends anything outside the office, posts publicly, ` +
    `schedules a commitment, or spends money — stop. End your reply with one line:\n` +
    `[NEEDS_APPROVAL: <what you want to do, and any cost>]\n` +
    `It lands on the boss's desk for a stamp; you'll be told once it's decided.`;
  const journalNote = journalSummary(agent);
  const mem = memorySummary(HQ && HQ._memory);
  /* Per-agent persistent memory listing — head-of-prompt so the agent
     knows what's in their private notes folder before they start. We
     fetch the actual file list from the vault (best effort; non-fatal
     if vault isn't configured). Limited to 12 entries to keep prompt
     size reasonable. */
  let agentMemoryNote = '';
  try {
    const safeName = memoryRoot(agent).slice('Agents/'.length);
    const root = memoryRoot(agent) + '/';
    const all = vaultPaths(await CafresoHQClient.vaultList());
    const mine = all.filter(p => p.startsWith(root)).map(p => p.slice(root.length));
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
        /* Same rename as the MEMORY_WRITE doc above, and this is the copy
           that actually did the damage: it is the note a coworker with an
           EMPTY memory reads, so it is the layout every first write
           follows. See the long note at that doc for what it produced. */
        `Save the first note with [MEMORY_WRITE: <path>]…[/MEMORY_WRITE]. Suggested layout: decisions/<topic>.md, references/<thing>.md, preferences.md, work/<slug>.md. Persists across sessions. These are your OWN notes, not the boss's Projects — a file the boss asked you to build belongs in the project folder via [FILE_WRITE], not here.`;
    }
  } catch (_e) { /* vault not configured — skip the memory note */ }
  const useJson = agent.toolFormat === 'json' || (agent.toolFormat !== 'bracket' && supportsJsonToolFormat(agent.model));
  const toolSnippet = enabledTools.length ? (useJson ? toolsPromptSnippetJson(enabledTools) : toolsPromptSnippet(enabledTools)) : '';
  /* `orderedNote` sits AFTER `toolsNote` on purpose: it is a correction to
     the brief, and it reads as one only once the granted list has been
     stated. Before it, it is a third opinion. */
  const sys = [base + toolsNote + orderedNote + elevatedNote + approvalNote, toolSnippet, agentMemoryNote, journalNote, mem, reg].filter(Boolean).join('\n\n');

  const messages = chat
    ? chatToMessages(chat, { selfName: agent.name }).concat([{ role: 'user', content: prompt }])
    : [{ role: 'user', content: prompt }];

  let toolsExecuted = 0;
  /* Accumulated across hops, not read off the last one. A coworker can call
     a tool they DO have on hop 1 and reach for one they don't on hop 2 (or
     the reverse), and only the final hop's buffer reaches the branch below.
     A Set because the same reach repeated over three hops is one thing to
     tell the boss. */
  const reachedFor = new Set();
  const KNOWN_MARKERS = Object.keys(TOOL_REGISTRY).map(k => TOOL_REGISTRY[k].name);
  for (let hop = 0; hop < maxToolHops; hop++) {
    let buf = '';
    const streamResult = await CafresoHQClient.stream({
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
    /* A driver that failed is done — there is no point spending the
       remaining hops on a CLI that will not start. Return rather than break
       so the caller gets the reason: every other exit from this function is
       the model stopping on its own, and `ranOutOfHops` next to it is the
       existing shape for "this run did not end normally, and here is why".
       Whatever the driver managed to say has already gone out through
       onToken, so nothing the boss should see is lost by leaving here. */
    if (streamResult && streamResult.driverError) {
      return { driverError: streamResult.driverError };
    }
    // ACK markers are status-update only — they should NOT halt the stream
    // for a tool round-trip. The host extracts them from `buf` after the
    // stream completes and routes to MessageRegistry.transition().
    const detectable = enabledTools.filter(t => t.name !== 'ACK');
    /* A marker whose tool this coworker does not have can never have run —
       that is not a judgement about the writing, it is arithmetic, the same
       kind `unfiledPath` does. Recorded every hop, reported once at the end. */
    {
      const has = new Set(enabledTools.map(t => t.name));
      for (const n of openedMarkers(buf, KNOWN_MARKERS)) if (!has.has(n)) reachedFor.add(n);
    }
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
        const missing = [...new Set([...orphans.map(o => o.tool), ...reachedFor]
          .filter(n => !enabledSet.has(n)))];
        /* §6 again, and this branch was the worst of it. It used to read
           "Try a stronger model — sonnet/opus or claudecode:sonnet — for
           the synthesis step, or lower temperature", which is three
           breaches stacked: `model` as a selector, a raw routing id at the
           boss, and `temperature`, which the table says is hidden
           outright. The sibling below said "raise max_tokens".

           I first wrote here that none of those dials exist. Half wrong,
           and worth keeping the correction: there IS no max_tokens field,
           but there IS a slider in Settings → Roster — which the table
           says should never have been called Temperature, and which is
           renamed Creativity in the same commit as this. So the reason
           these sentences go is not that the dial is missing. It is that
           "lower temperature" asks a boss with no expertise to make a
           judgement they have no way to make, about a control the product
           deliberately keeps at the back.

           What they CAN judge is whether to ask again or give the job to
           someone else, and that is what these now say. */
        if (toolsExecuted > 0) {
          emit(`_(${agent.name} did the legwork but never wrote it up. Ask them to summarise what they found, or hand the job to a coworker on a stronger brain.)_`);
        } else if (missing.length) {
          /* The second door, and only when it is the shut one — see
             claimNeedsMediaDoor. A coworker with the box already on is
             sent to the screen that will actually change something.

             "tick it" named the wrong ACTION as well as, for file and shell
             work, the wrong control: that door is a switch, not a checkbox.
             "Turn it on" is true of both, so one sentence still covers
             every door on the card. See reachedForNote. */
          emit(reachedForNote(missing, agent));
        } else if (orphans.length) {
          emit(`_(${agent.name} talked themselves through it but never answered. Ask them again, or hand the job to a coworker on a stronger brain.)_`);
        } else {
          emit('_(nothing came back from them this time — your office may be offline, or their brain may be busy. Ask them again in a moment.)_');
        }
      } else if (reachedFor.size) {
        /* The reply is not empty — and until this branch existed, that was
           enough to say nothing at all. Everything above answers "nothing
           came back"; a coworker who reaches for a door they don't have and
           then writes a confident paragraph around it fell through all of
           it.

           Measured on a canned brain: Vera (web, email, cal, vault — no
           file access) answered "write the vendor brief" with a well-formed
           [FILE_WRITE: brief.md] block and the sentence "Done — the brief is
           saved as brief.md." `stripBlocks` removed the block, correctly,
           so the boss never saw the attempt. Nothing was written. The
           office printed the claim with no correction, and the one note
           that exists for precisely this was sitting behind `!cleaned`.

           That is the worst arrangement of the three: silent when the reply
           is empty is merely unhelpful, but silent when the reply CLAIMS
           SUCCESS is the office backing the claim.

           Only doors that can be named are reported. A marker with no
           Roster door behind it (DM_TO, HANDOFF_TO, HIRE_AGENT, the memory
           pair) belongs to `unsentHandoff`/`unsentBlocks`, which run on the
           same raw buffer — reporting it here would be a second note about
           one event, and the generic "something they haven't been given"
           would be a caveat the boss cannot act on. Silence is right when
           there is no door to point at. */
        const missing = [...reachedFor];
        if (claimLabels(missing, agent) || claimHitsMediaDoor(missing, agent)
            || claimHitsVaultDoor(missing, agent)) {
          emit(reachedForNote(missing, agent));
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

    /* Refuse a template before it becomes a visit — no start/done events,
       so the floor never plays a trip that didn't happen. */
    const refusal = placeholderRefusal(call.tool.name, call.arg);
    if (refusal) {
      /* Deliberately silent on the FLOOR — nothing happened, so §4 says
         play nothing. But a refusal that leaves no trace anywhere is
         unverifiable: proving one occurred was impossible when checking
         this live, and "no phantom visit appeared" is equally consistent
         with the model simply not emitting a placeholder that time. One
         console line, for the developer, not the boss. */
      if (typeof console !== 'undefined' && console.warn) {
        console.warn(`[tools] refused ${call.tool.name}(${String(call.arg).trim()}) — template, not a value`);
      }
      messages.push({ role: 'assistant', content: upToToolCall(buf, call.raw) });
      messages.push({ role: 'user', content: refusal });
      continue;
    }
    /* `cwd` rides along on every tool event. A coworker reports the path
       they typed — "index.html" — and that is only meaningful next to the
       directory it was typed for. Listeners downstream (the Workspace's
       file tree, activity ledger and presence pip) are ABOUT one folder,
       and without this they had to guess: the guess was "assume it's mine",
       which resolved another project's relative write into this project's
       root and filed it as a change to this folder. Undefined here is
       itself the honest answer — ceoStream runs its tools with no working
       directory at all, so its events carry none. */
    if (onTool) onTool({ phase: 'start', name: call.tool.name, arg: call.arg, cwd });
    let result;
    /* Did it actually work? Not the same question as "did it return". A
       missing file, a path that isn't a directory, a command that exits
       non-zero — all answer normally, with the explanation as the result,
       because the coworker needs that text to recover. `meta.failed` is the
       server saying so out of band; the throw path below sets it too.
       Without it every surface captioned a failure as a success — watched
       live as "Opened ./site" directly above "Not a directory: ./site". */
    const meta = {};
    try {
      result = await call.tool.run(call.arg, { signal, cwd, meta }, call.body);
    } catch (err) {
      result = `That didn't work — ${err.message}`;   // see the note on the sibling path
      meta.failed = true;
    }
    toolsExecuted++;

    /* Stream the result inline so the user sees what the agent is reading —
       then hand the SAME string back on the done event as `echo`.

       The boss watching a coworker work wants the whole tool visit on screen.
       The boss opening the filing cabinet a month later does not: a filed
       "Three primary colours" came back 8.8KB, of which the coworker's own
       answer was one sentence and the rest was a URL, `Status: 200`, and
       Wikipedia's page text — jargon §6 bans, on a surface the boss keeps.
       Filing strips the echo out again, and exact-string removal only works
       if it gets the exact string. So the format lives here, at the one site
       that owns it, and travels with the event instead of being re-derived
       (and eventually mis-derived) by the code that has to undo it. */
    /* The visit does NOT go into the token stream any more.

       Everything in the text channel is forgeable, and a local model
       proved it: having seen real visits in its history it wrote its own,
       office format and all, with an invented result and an invented vault
       path, in a bubble where the real read had returned nothing. Stripping
       the office's voice out of the model's CONTEXT removed the incentive;
       this removes the possibility. A visit is now structured data on the
       `done` event, the UI renders it as its own element, and no sentence
       the coworker can type will ever render as the office speaking.

       `echo` stays on the event: histories written before this change still
       carry the banner inline, and filing removes it by exact match. */
    if (onTool) {
      onTool({ phase: 'done', name: call.tool.name, arg: call.arg, result,
               failed: !!meta.failed, cwd,
               echo: `\n\n${toolEchoHead(call.tool.name, call.arg)}\n${result}\n\n` });
    }

    messages.push({ role: 'assistant', content: upToToolCall(buf, call.raw) });
    messages.push({ role: 'user', content: `[TOOL_RESULT: ${call.tool.name}]\n${result}\n\nContinue from where you stopped. Now write a concise answer for the user using these results. Do NOT repeat the tool call. Do NOT emit any more bracketed markers or harmony commentary unless you genuinely need another search/lookup.` });
  }
  /* Hop budget exhausted. Two things leave here now.

     The hint stays out-of-band, so it doesn't end up in the agent's journal
     or in user-visible chat as if it were the model speaking. But prose
     aimed at the boss is not a fact the CALLER can act on, and the caller
     is the one holding the task card. The board read the buffer, found four
     paragraphs of ordinary sentences, and filed a run that never reached
     its answer as DONE — cabinet file, ✓ in the feed, a completion in the
     XP ledger. Nothing it read was wrong; the one thing that would have
     told it was only ever said out loud. So the ending is also returned.

     Every other exit from this function is the model stopping on its own or
     the host taking the turn over, which is why they stay `return;`:
     nothing back means "not cut short", and that is the right default for a
     caller that never looks.

     The sentence splits on `chat` because its second half is a promise
     about history. Ask-again holds for the conversational callers — they
     pass the last few turns, and #126 taught that transcript to carry the
     tool results back with them. It is empty for the board, which passes
     none on purpose: a card run is its brief and nothing else.

     It rides back on the return as well as going out through the hint, so
     the caller can put it on a card without writing a second sentence
     about the same fact. Two sentences saying one thing in different words
     is #64 with two authors — and one string means `flush.note`, which
     drops a note the bubble already contains, keeps the boss reading it
     exactly once. */
  const stopNote = chat
    ? '_(they did as much as they can in one go and stopped there. If this is part of a running project it will carry on by itself; otherwise ask again and they will pick it up.)_'
    : '_(they did as much as they can in one go and stopped there. Running it again starts from the brief and carries nothing over, so a narrower brief gets further.)_';
  if (onHint) onHint(stopNote);
  return { ranOutOfHops: true, note: stopNote };
}

/* Whether handing `taskId` to this coworker would displace real work.

   The board's ▶ START warns the boss before it buries a run — "X is
   working on Y … whatever they had done on it so far is lost" — and the
   evidence for "working on" used to be card status alone: any card
   sitting in `doing`. But a card whose run came back empty PARKS in
   `doing` with a `blockedReason` by design (the board has no blocked
   column), so the office asked leave to bin work that had already come
   back empty. Measured 2026-08-15: Vera idle at her desk, her only
   `doing` card stamped "Nothing came back from this run — no answer and
   no file", and ▶ START on a fresh task raised the danger dialog
   claiming she was working on it and that what she had done would be
   lost. Both halves false — the run had ended, and there was nothing in
   flight to lose.

   Two conditions, each enough on its own to kill that lie, both kept:

   `running` — the caller passes the office's own in-flight check (the
   aborter registry holds an entry exactly while a stream is open; the
   run's `finally` and every abort path clear it). The confirm exists to
   warn about beginAgentRun's ABORT, so it is gated on the abort's own
   truth: no live run, nothing can be killed, nothing can be lost.

   `!blockedReason` — a blocked card is definitionally a card whose run
   ENDED (only the run-end path stamps it). Even while this coworker IS
   mid-run on something else, a parked snag is never the run in flight,
   so it is never the work a new start would destroy. */
function displacedTask(tasks, agentId, taskId, running) {
  if (!running) return null;
  return (tasks || []).find(t => t && t.id !== taskId && t.assignedTo === agentId
    && t.status === 'doing' && !t.blockedReason) || null;
}

function resolveModel(m) {
  if (!m) return undefined;
  if (m === 'lmstudio') return undefined;
  return m;
}

const HQ = {
  AGENT_COLORS, ROLES, TOOLS_CATALOG, ELEVATION_TOOL_IDS, CHIEF_OF_STAFF,
  MODELS, MEMORY_PROMPT_CAP,
  INITIAL_AGENTS, INITIAL_CHAT, ACTIVITY_SEED, OPENSWARM_ROSTER, spawnOpenswarmRoster,
  uid, extractApproval, approvalBody, extractDM, extractAllDMs, isHandoffPlaceholder, extractHandoff, stripHandoff, extractMention, extractAllMentions, extractAcks, stripAcks, visibleReply, fabricatedRelay, unsentAsk, unsentBlocks, unsentElevation, unsentHandoff, unverifiedSources, unfiledPath, honestyNotes, publishDoorNote, icpPublishEnabled, clearVaultReadyCache, isVaultReady, vaultReadySync, onVaultReadyChange, throttleTokens, cleanHarmony, reasoningPatterns, stripReasoning, maskReasoning, displacedTask,
  ceoStream, agentStream, chatToMessages, buildCeoSystem, supportsJsonToolFormat,
  /* Exported for the three surfaces that describe a coworker's reach — the
     candidate shelf, the coworker card, the inspect panel. They must all ask
     the same question of the same file that answers it for real. */
  capabilityFacts,
};
// Back-compat alias so older call sites keep working; routes to the real CEO stream.
HQ.mockStream = (prompt, onToken, opts) => ceoStream(prompt, onToken, opts);

export { HQ };
