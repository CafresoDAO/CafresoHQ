import { CafresoHQClient } from '../claude-client.jsx';
import { HQ } from '../hq-runtime.jsx';
import { Sprite } from '../sprites.jsx';
import { brainName, candidateBrain, canDoPhrase, poweredBy, specialtyTag, statBars } from '../app/cast.jsx';
import { Modal, ModelPicker, loadTemplates, saveTemplates } from './base.jsx';
import { visibleToolsCatalog } from './settings.jsx';
const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;

/* Every tile on the job-postings board was a bare <div onClick>: reachable
   with a mouse, invisible to the keyboard. Measured on a fresh office — the
   only focusable elements in the entire dialog were "NEW HIRE →" and
   "CLOSE ✕", so a keyboard-only boss could not hire any of the coworkers the
   front desk had just found for them. This is the FIRST screen a new boss
   sees and hiring is the one thing it exists to do, so that is the onboarding
   path dead-ending, not a polish gap.

   The rest of the app already settled on role="button" + tabIndex={0} +
   Enter/Space (views/vault.jsx, ui/panels.jsx, views/core.jsx,
   ui/onboarding.jsx); this board just never got it. Returning onClick from
   the same helper is the point: it keeps the mouse and keyboard paths from
   drifting apart the next time one of them is edited.

   The `e.target !== e.currentTarget` guard is load-bearing on the template
   tile. That tile contains a real nested <button> (post-remove) which stops
   click propagation — but keydown bubbles on its own, so without the guard
   pressing Enter to DELETE a template would also load it into the form. */
const cardActivate = (fn) => ({
  role: 'button',
  tabIndex: 0,
  onClick: fn,
  onKeyDown: (e) => {
    if (e.target !== e.currentTarget) return;
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    fn();
  },
});

/* The grid is the whole vocabulary of this form: an id it cannot SHOW is an
   id it must never WRITE.

   Measured 2026-08-16 — a hire with every box unticked landed on the roster
   holding `files`. The form seeded its tool state with ['web','files'], and
   `files` is deliberately absent from the grid because its real door is the
   elevation switch, not a box here (settings.jsx, GRANTED_ELSEWHERE_TOOL_IDS
   — the decoy removal of #57/#117). So the claim was written, was invisible
   on the hire form AND on the Roster card, and no control in the product
   could take it back. It grants nothing on its own — `toolsForAgent` still
   demands elevation — but every surface that reads the claim repeats it, so
   the new coworker advertised file access their boss never asked for. That
   is #104 again: a card promising what the shelf refused to promise.

   The seed is not the only way in. A saved template, or an OPENSWARM
   candidate whose elevation is deliberately dropped on load, carries its own
   `tools` array straight into the same state — so the rule belongs at every
   writer, not at the one that happened to be caught. */
const formToolIds = (ids) => {
  const shown = new Set(visibleToolsCatalog().map(t => t.id));
  return (ids || []).filter(id => shown.has(id));
};

/* Why HIRE ✓ cannot go through yet, in office words — or '' when the form is
   ready and the button is live.

   HIRE ✓ is the front door. Onboarding step 2 opens this dialog on the NEW
   HIRE form with every box empty, so it is very plausibly the first button a
   beta tester ever presses — and `submit()` opened with a bare
   `if (!name.trim()) return;` over a button with no `disabled` state and no
   message anywhere on the screen. Clicking it on the form exactly as it
   opens did literally nothing: no error, no highlight, no hint, no dialog.
   That is worse than a refusal, because a live button is a promise that it
   can do the thing, and the only reading left for the boss is that the app
   is broken.

   Same shape and same remedy as `noCrewNote(agents)` on the missions form
   (#299) and `inboxEmptyNote(...)` in the inbox (#306): one sentence
   carrying the reason AND the route, read by both the button's `disabled`
   state and the hint the boss can see without hovering, so the two can
   never drift apart. It names the field by the label printed above the box
   (NAME) rather than by the variable — the vocabulary rule §6 that
   `topic + agent required` broke in #299.

   The blank box is not the only thing this door has to catch. A NAME in
   this office is an ADDRESS, not a caption: `@Vera` in the composer, a
   coworker's `[DM_TO: Vera]`, and a `[HANDOFF_TO: Vera]` are all resolved
   with `agents.find(a => a.name.toLowerCase() === …)` — FIRST match wins,
   in app.jsx and again in hq-runtime.jsx. So a second Vera is not a
   near-duplicate, she is unaddressable: every mention, DM and hand-off
   aimed at her lands on the first Vera, and the office says nothing,
   because from where it stands the name resolved fine.

   And the roster she lands on cannot tell the boss which is which. Two
   hires off one saved template share sprite, name and role — the shelf
   filters OPENSWARM candidates by `hiredNames` and the front desk filters
   its cards by `hiredIds`, but the TEMPLATES shelf filters by neither, so
   hiring the same saved role twice is one extra click. The Settings →
   ROSTER row is sprite + name + role and a LET GO button; LET GO on a
   coworker with no assistants runs `onDismiss` straight through with no
   confirm at all. Two identical rows, one irreversible button, and the
   boss picking between them is guessing — the #317 shape (two live PTYs
   both labelled "Hermes #1") on a row where the wrong click takes a
   coworker's prompt, tools, tokens and history with it, unassigns their
   cards and DELETEs their night shifts off the server.

   Refused at the door rather than disambiguated on the roster, because a
   suffix on a row cannot fix routing: `@Vera` has no row to point at.

   The BRAIN is the third thing this door has to catch, and the one a first
   run actually walks into. Measured 2026-09-05 on a cold boot with nothing
   configured: `candidateBrain([])` is null, so every card on the shelf the
   office opens BY ITSELF reads "no brain yet — add one in Settings →
   Connections", `candidates` rewrites each template's model to `''`, and
   `loadCandidate` puts that empty string into the form. What the boss then
   saw was NAME "Vera", BRAIN "— pick a model —", the footer cheerfully
   reading "A new desk will be assigned on spawn.", and HIRE ✓ live. They
   pressed it, and `{"name":"Vera","model":""}` went onto the roster — a
   coworker at a desk, in the ticker, with onboarding step 2 ticked, who can
   never answer anything.

   Two surfaces on that same screen already knew. ⚡ SEED SWARM, one tile
   away, refuses the identical hire out loud ("There is no brain on this
   machine yet, so these 7 would sit at their desks unable to work"), and
   the BRAIN row's own warning opens `if (!provider) return null;` — written
   for a brain that exists and is not signed in, so on the one state a fresh
   install actually produces it said nothing at all. A total failure slipped
   through the check built for the partial one.

   Deliberately silent about a brain that is merely UNSIGNED: the BRAIN row
   owns that sentence, and two blocks over one field is worse than one.

   Kept module-level, pure and import-free so
   scripts/test_the_hire_button_says_what_it_is_waiting_for.py,
   scripts/test_two_coworkers_are_never_hired_under_one_name.py and
   scripts/test_a_coworker_is_never_hired_with_no_brain_at_all.py run it
   verbatim under node. The roster and the brain arrive as arguments for
   that reason — the helper still closes over no component state. */
function hireNeedsNote(name, currentAgents, model) {
  const typed = String(name == null ? '' : name).trim();
  if (!typed) {
    return 'Give your new coworker a name first — type one in the NAME box '
      + 'above, anything you would like to call them.';
  }
  /* Same comparison the resolvers use — trimmed and case-folded — or the
     door would pass a "vera" that `[DM_TO: Vera]` still collides with. */
  const taken = (currentAgents || []).find(a =>
    String((a && a.name) || '').trim().toLowerCase() === typed.toLowerCase());
  if (taken) {
    return `${taken.name} already works here${taken.role ? ` — ${taken.role}` : ''}. `
      + 'A name is how this office reaches somebody: @mentions, teammate DMs '
      + 'and hand-offs all go to the first match, and two rows sharing one '
      + 'name share one LET GO button. Give this hire a different name in the '
      + 'NAME box above.';
  }
  if (!String(model == null ? '' : model).trim()) {
    return `${typed} has no brain yet, so they would sit at their desk unable `
      + 'to work. Pick one in the BRAIN box above, or add a free local brain '
      + '(LM Studio, Ollama) in Settings and come back — the shelf will fill '
      + 'their brain in for you once this machine has one.';
  }
  return '';
}

/* ── The front desk (DRIVER_CONTRACT §3 · OFFICE_AS_INTERFACE §3) ─────────
   What /agent/drivers detected on THIS machine, offered as one-click hires.
   The default is whatever the user already pays for or runs — no driver is
   pre-selected by us. Ids match app.jsx's CLI-sync DEFS (a_cli_*) so the
   version/login refresher keeps maintaining these agents after hire. Copy
   follows the jargon table: subscriptions and sign-ins, never CLIs/keys.
   cloud:true = plain-chat API backend riding POST /agent/stream (the key
   lives server-side, so these only count as found when detect.authenticated
   — a card that would fail its first task is worse than no card). */
/* §6 note: a role is a JOB TITLE. These five used to read "Local Model ·
   your hardware" / "Cloud Model · your account", which is model-as-selector
   on the first surface a new boss ever reads — and the "·" clause also fed
   the office door plate, so hiring the local Llama produced a room labelled
   "LLAMA · HARDWARE". Where the brain runs is already carried honestly by
   the powered-by chip and the found line; the role says what they do. */
/* `tools` here is a DISPLAY signal as much as a stored claim — app/cast.jsx
   turns it into the card's "can do" line, and the stat bars and permission
   chip read it too. Four of these cards listed 'shell', which is not an id
   in TOOLS_CATALOG and is not a key in cast.jsx's CAN_DO either, so it was
   read by nothing: the three coding-agent cards and Hermes silently never
   said they could run code, on cards whose entire role is "Coding Agent".
   The catalog id is 'code'. All four now carry it, which is honest for
   these four specifically because they also carry `elevated: true` — the
   flag that actually grants BASH — so the card's claim and the coworker's
   real capability agree. */
const FRONT_DESK = {
  'claude-code': { id: 'a_cli_claude', name: 'Claude', role: 'Coding Agent', color: 'leaf',
                   model: 'claudecode:sonnet', tools: ['files', 'code', 'web'], elevated: true,
                   poweredBy: 'Claude', found: 'We found your Claude subscription on this machine.' },
  'codex':       { id: 'a_cli_codex', name: 'Codex', role: 'Coding Agent', color: 'mint',
                   model: 'codex:gpt-4.1', tools: ['files', 'code'], elevated: true,
                   poweredBy: 'OpenAI', found: 'We found your Codex subscription on this machine.' },
  /* Gemini CLI (drivers/gemini_cli.py) — distinct from the 'gemini-api'
     cloud card below: this one is the agent CLI on this machine, working
     with computer access like Claude/Codex, signed in with the user's own
     Google account. Until this card existed the driver was hire-less: the
     back office could detect and even install the CLI, but the front desk
     never offered it — a detected subscription the boss couldn't use. */
  'gemini':      { id: 'a_cli_gemini', name: 'Gemini', role: 'Coding Agent', color: 'blush',
                   model: 'gemini:gemini-2.5-pro', tools: ['files', 'code'], elevated: true,
                   poweredBy: 'Google', found: 'We found your Google sign-in on this machine.' },
  /* North-star §3.1: no runtime gets special treatment, "not in code, not in
     copy, not in defaults" — and Hermes is the runtime that section names as
     the original mistake. Its card was the only one written as a pitch
     rather than a detection line: role "Resident Agent", found line "The
     house agent — already moved in and ready to work." Every sibling states
     what was detected and nothing more ("We found your Claude subscription
     on this machine", "Already running on this machine — cheap and
     tireless"). "House" and "resident" are status, not capability, and they
     tell a newcomer which one the office prefers.

     Now in the same register as the rest. The tools it actually holds
     (web + files + shell) are what the card's stat bars and permission
     chip already say.

     The found line was still making two claims nothing had checked:
     "in your container" (on this machine Hermes is a binary in
     ~/.local/bin and a config in ~/.hermes — no container anywhere in the
     detection path) and "ready to work" (printed over a gateway that was
     measurably down). Both replaced by what detect() actually establishes.

     `service: true` marks the runtimes that have to be RUNNING to take
     work, as opposed to a program that has to be repaired. It picks the
     remedy sentence on a card that isn't ready — telling someone to
     reinstall a service they only needed to start is the same wrong
     diagnosis in a different costume. */
  'hermes':      { id: 'a_cli_hermes', name: 'Hermes', role: 'Generalist', color: 'sky',
                   model: 'hermes:hermes-agent', tools: ['web', 'files', 'code'], elevated: true,
                   service: true,
                   poweredBy: 'Nous Research', found: 'Set up on this machine, with its gateway running.' },
  'lmstudio':    { id: 'a_local_lmstudio', name: 'Local Brain', role: 'Generalist', color: 'teal',
                   model: 'lmstudio:local-model', tools: ['web'], service: true,
                   poweredBy: 'LM Studio', found: 'Already running on this machine — cheap and tireless.' },
  'ollama':      { id: 'a_local_ollama', name: 'Llama', role: 'Generalist', color: 'sun',
                   model: 'ollama:llama3.1', tools: ['web'], service: true,
                   poweredBy: 'Ollama', found: 'Already running on this machine — cheap and tireless.' },
  'openrouter':  { id: 'a_cloud_openrouter', name: 'OpenRouter', role: 'Generalist', color: 'rose',
                   model: 'openrouter:openai/gpt-oss-120b:free', tools: ['web'], cloud: true,
                   poweredBy: 'OpenRouter', found: 'Your OpenRouter account is connected to this workspace.' },
  'groq':        { id: 'a_cloud_groq', name: 'Groq', role: 'Generalist', color: 'blush',
                   model: 'groq:llama-3.3-70b-versatile', tools: ['web'], cloud: true,
                   poweredBy: 'Groq', found: 'Your Groq account is connected to this workspace.' },
  'gemini-api':  { id: 'a_cloud_gemini', name: 'Gemini', role: 'Generalist', color: 'cafresohq',
                   model: 'gemini-api:gemini-2.5-flash', tools: ['web'], cloud: true,
                   poweredBy: 'Google', found: 'Your Google AI account is connected to this workspace.' },
};
/* The readiness rule the shelf hires on, at module scope so the effect
   that publishes its answer can sit ABOVE `if (!open) return null;` —
   a hook below an early return is a hook that only sometimes runs, and
   React counts them. Pure, and reads only FRONT_DESK.

   Kept as a const arrow rather than a function declaration because
   scripts/test_a_candidate_names_the_brain_it_will_use.py and
   scripts/test_the_shelf_speaks_the_hermes_drivers_own_word.py find it in
   this file by its assignment text and run it verbatim under node — and for
   the same reason nothing above may quote that text, since they lift from
   the FIRST match. */
const candidateReady = (d) => {
  const det = (d && d.detect) || {};
  if (d.id === 'lmstudio' || d.id === 'ollama') return det.version === 'reachable';
  /* 'reachable' is the LOCAL-DAEMON word (drivers/local_http.py writes it
     from the /models probe). Hermes has never spoken it: drivers/hermes.py
     reports its liveness as `version = 'gateway up' if up else ''`, with
     `probeError: 'is not running'` on the down side. So this arm compared
     against a string the driver cannot produce and was false on EVERY
     machine — including one whose gateway the probe had just found up.
     Hermes is 7th in CANDIDATE_BRAINS, so on a box that also runs a local
     daemon or holds a CLI subscription the wrong answer is masked; on a
     Hermes-only office it is the whole shelf. There, one screen said both
     "Hermes · FOUND · Set up on this machine, with its gateway running"
     and, one row below, "no brain yet — add one in Settings → Connections"
     on every candidate, with ⚡SEED SWARM refusing outright: "There is no
     brain on this machine yet, so these N would sit at their desks unable
     to work." The office contradicting its own measurement, and the
     refusal landing on the boss who was actually ready to hire. */
  if (d.id === 'hermes') return det.installed && det.version === 'gateway up';
  if (FRONT_DESK[d.id] && FRONT_DESK[d.id].cloud) return !!det.authenticated;
  return !!det.installed && !det.probeError;
};
/* Loopback, in the shapes a base URL actually arrives in. A local daemon
   found HERE and one found across the LAN are the same card with a
   different true sentence on it — see the note in deskCards. */
const LOOPBACK = /^(localhost|127(?:\.\d+){3}|\[?::1\]?)$/i;
/* Host out of a base URL, '' if it is not one. `new URL` throws on the
   empty string, which is exactly what an undetected daemon reports. */
const hostOf = (u) => { try { return new URL(String(u || '')).hostname; } catch (_e) { return ''; } };

/* Section 2's card, on the SHELF as well as in the office. A saved
   candidate used to advertise itself as "SONNET · 4 tools" -- the two
   things the design system says a card must not lead with: the vendor's
   model as the identity, and a machine count. The hired coworker's panel
   has shown Speed/Depth/Code/Cost with a small "powered by" chip since
   B1; the cards you pick FROM had never been brought over, which is
   backwards -- this is the surface where the boss is actually choosing.

   Same statBars() the panel uses, so a candidate cannot advertise one
   thing and then show another the moment they are hired.

   `showBars` is the correction to my first version of this card. The bars
   key off the BRAIN, and every seed candidate pins cafresohq:sonnet -- so
   eight cards rendered eight IDENTICAL stat blocks and eight identical
   "strong all-rounder" lines. True, and useless: on the one surface whose
   whole job is CHOOSING, a row that reads the same on every card is not
   neutral, it crowds out the two things that actually differ (the role and
   what they can do). So the block appears only when it discriminates --
   when the cards on screen do not all share one profile. Seed roster: no
   bars. A shelf of templates on different brains: bars. */
/* The facts `canDoPhrase` needs and cannot look up for itself. Each one is
   read from the same place the runtime reads it when it decides whether to
   hand the tool over, so the card and `toolsForAgent` cannot disagree.

   That sentence was written here, about this shelf, and was true of this
   shelf only: the reader was private to this file, so the two surfaces
   that describe a HIRED coworker — the card and the inspect panel — could
   not have used it if they had wanted to, and they did not. It now lives
   in hq-runtime.jsx beside `toolsForAgent`, where its comment explains the
   four facts, and this call is one of three.

   Still wrapped there, for the reason it was wrapped here: this runs during
   render on the first screen of a fresh install, and a settings store that
   is not up yet must produce a quieter card, never a broken one. */
const capabilityFacts = (t) => HQ.capabilityFacts(t);

function CastLine({ t, showBars }) {
  const bars = statBars(t);
  const vendor = poweredBy(t);
  return (
    <>
      {showBars && <div className="post-spec">{specialtyTag(t)}</div>}
      {showBars && <div className="post-bars">
        {[['Speed', bars.speed], ['Depth', bars.depth], ['Code', bars.code], ['Cost', bars.cost]].map(([lbl, n]) => (
          <span className="pb-cell" key={lbl} title={`${lbl}: ${n} of 4`}>
            <span className="pb-lbl">{lbl}</span>
            <span className="pb-track" aria-label={`${lbl}: ${n} of 4`}>
              {[1,2,3,4].map(i => <span key={i} className={'pb-seg' + (i <= n ? ' on' : '')} />)}
            </span>
          </span>
        ))}
      </div>}
      <div className="post-meta">
        <span title={(t.tools||[]).join(', ') || 'no tools'}>Can {canDoPhrase(t.tools, capabilityFacts(t))}</span>
      </div>
      {/* No model at all is not "brain: not set yet" on this shelf — it is
          the shelf reporting that nothing on this machine can run this role
          yet, which is a §7 moment and needs a door. `brainName` still
          covers the saved-template case, where a boss really did leave the
          brain blank on a card they made themselves. */}
      <div className="post-vendor" title={t.model || 'no brain on this machine yet'}>
        {vendor ? `powered by ${vendor}`
                : t.model ? `brain: ${brainName(t)}`
                : 'no brain yet — add one in Settings → Connections'}
      </div>
    </>
  );
}

function HireModal({ open, onClose, onHire, currentAgents = [] }) {
  const [name, setName] = useStateM('');
  const [role, setRole] = useStateM(HQ.ROLES[0]);
  const [prompt, setPrompt] = useStateM('You are a helpful sub-agent. Be concise and warm.');
  const [toolsPicked, setTools] = useStateM(['web']);
  /* ONE choke point, on the read. Every consumer — the grid's ticks, the
     saved template, and the array handed to onHire — goes through `tools`,
     so filtering here is filtering everywhere, and there is no second place
     to forget. Filtering the writes as well was the first shape of this fix
     and it bought nothing: with the read filtered, a write that skipped the
     grid had no observable effect, which a fire arm duly proved by
     surviving. Two guards where one suffices is just two things to keep in
     step.

     Reading rather than writing also behaves better when the catalog itself
     moves: the wallet box comes and goes with the money module, and a tick
     taken while it was on is suppressed while it is off and honoured again
     if it comes back, instead of being silently destroyed by whichever
     unrelated write happened next. */
  const tools = formToolIds(toolsPicked);
  const [avatar, setAvatar] = useStateM('rose');
  const [model, setModel] = useStateM('anthropic:claude-haiku-4-5-20251001');
  const [temp, setTemp] = useStateM(0.4);
  /* elevated = the agent will be backed by an CafresoHQ session with file/shell
     access on the host computer. Off by default — a deliberate, scary opt-in. */
  const [elevated, setElevated] = useStateM(false);
  const [templates, setTemplates] = useStateM(loadTemplates);
  const [showBoard, setShowBoard] = useStateM(true);
  /* Front-desk detection: null = probing (the deep check takes a few seconds
     — CLI version spawns + local-daemon liveness), [] = nothing found. */
  const [driverList, setDriverList] = useStateM(null);

  useEffectM(() => {
    if (!open) return;
    let dead = false;
    setDriverList(null);
    (async () => {
      try {
        const d = await (CafresoHQClient.agentDrivers
          ? CafresoHQClient.agentDrivers(true) : Promise.resolve({ drivers: [] }));
        if (!dead) setDriverList(d.drivers || []);
      } catch (_e) { if (!dead) setDriverList([]); }
    })();
    return () => { dead = true; };
  }, [open]);

  /* Reset the form whenever the modal (re)opens so a previous draft never bleeds
     into a fresh hire. Mirrors MeetingRoomModal's [open]-effect. */
  useEffectM(() => {
    if (!open) return;
    setName(''); setRole(HQ.ROLES[0]);
    setPrompt('You are a helpful coworker. Be concise and warm.');
    setTools(['web']); setAvatar('rose');
    setModel('anthropic:claude-haiku-4-5-20251001'); setTemp(0.4);
    setElevated(false); setShowBoard(true);
  }, [open]);

  /* The brain the shelf will actually use, from the SAME detection the
     front-desk row below is drawn from — see candidateBrain in cast.jsx for
     what this is fixing. `driverList === null` means still probing, and
     unknown is not "nothing found": the cards hold their brain line until
     the probe lands rather than flashing "no brain yet" at every boss for
     the few seconds a deep probe takes.

     readyIds is deliberately STRICTER than "has a desk card" — see
     candidateReady. It is computed HERE, above the early return, because
     the effect below it is a hook. */
  const probing = driverList === null;
  const readyIds = (driverList || []).filter(candidateReady).map(d => d.id);

  /* Tell the rest of the office what this shelf just measured. The topbar's
     ⚠ NOBODY HIRED alarm describes the same machine and had no way to ask —
     see emptyOfficeNote in app/cast.jsx for the sentence that was printed
     instead. Published only once the probe LANDS: `probing` is not "nothing
     found", and a mirror that reports it as such would just move the lie. */
  useEffectM(() => {
    if (probing) return;
    try { HQ.noteFrontDeskBrains(readyIds); } catch (_e) {}
  }, [probing, readyIds.join(',')]);

  /* <Modal> handles open=false → returns null. We still bail before running
     the heavier setup logic when closed. */
  if (!open) return null;

  const loadTpl = (t) => {
    setRole(t.role); setPrompt(t.prompt); setTools(t.tools);
    setAvatar(t.avatar); setModel(t.model); setTemp(t.temp);
    // elevated never flows from a template — operator must re-opt-in deliberately.
    setElevated(false);
    setName('');
    setShowBoard(false);
  };
  /* Candidate = an OPENSWARM_ROSTER template surfaced as an individual card.
     Prefills the whole form (name included) so hiring is review-then-confirm,
     never a blind one-click spawn. */
  const loadCandidate = (tpl) => {
    setName(tpl.name); setRole(tpl.role); setPrompt(tpl.systemPrompt);
    setTools(tpl.tools); setAvatar(tpl.color); setModel(tpl.model);
    setTemp(tpl.temperature != null ? tpl.temperature : 0.4);
    setElevated(false);
    setShowBoard(false);
  };
  const saveAsTemplate = async () => {
    /* The second silent early return on this form. `hqPrompt` resolves
       `string | null` (ui/feedback.jsx) and this collapsed both answers to
       one `|| ''`, so pressing OK on a blank box — or on spaces — closed the
       dialog and did nothing at all, with no template on the shelf and
       nothing said. Cancel MUST stay silent, because the boss just said no;
       an answer that cannot be used is a different event and gets a
       sentence. */
    const answer = await window.hqPrompt('Save this configuration as a template — name it (e.g., "Researcher", "Inbox triage"):');
    if (answer == null) return;
    const tplName = String(answer).trim();
    if (!tplName) {
      await window.hqConfirm(
        'A template is found again by its name, so it needs one — try SAVE AS TEMPLATE again and type what to call this setup.',
        { okLabel: 'Got it', hideCancel: true });
      return;
    }
    const t = { id: 'tpl_'+Math.random().toString(36).slice(2,7), name: tplName, role, prompt, tools, avatar, model, temp };
    const next = [t, ...templates.filter(x => x.name !== tplName)];
    setTemplates(next); saveTemplates(next);
  };
  const deleteTpl = (id) => {
    const next = templates.filter(t => t.id !== id);
    setTemplates(next); saveTemplates(next);
  };

  const toggleTool = (id) => {
    setTools(t => t.includes(id) ? t.filter(x=>x!==id) : [...t, id]);
  };

  /* Roster specialists not yet on the team — shown as CANDIDATE cards and
     counted by the SEED SWARM tile. */
  const hiredNames = new Set((currentAgents || []).map(a => String(a.name || '').toLowerCase()));
  /* `!t.parked` — the park list (north-star section 5) is about the core
     path, the onboarding and the pitch, and this shelf is where a first-run
     stranger meets the cast. A parked template keeps its full definition in
     OPENSWARM_ROSTER; it just does not get offered here. */
  /* The brain the shelf will actually use, off the readyIds measured above
     the early return — see candidateBrain in cast.jsx for what this is
     fixing, and candidateReady for why the rule is stricter than "has a
     desk card". */
  const shelfBrain = probing ? undefined : candidateBrain(readyIds);

  const candidates = (HQ.OPENSWARM_ROSTER || [])
    .filter(t => !t.parked && !hiredNames.has(t.name.toLowerCase()))
    /* The template's own `model` is a placeholder for a brain this office
       may not have. Overwriting it here — rather than at hire time — is
       what keeps the card's chip and the hired coworker's brain the same
       fact. `undefined` while probing leaves the template's value alone. */
    .map(t => (shelfBrain === undefined ? t : { ...t, model: shelfBrain || '' }));

  /* Do the four bars tell these cards apart, or do they say one thing eight
     times? Computed over exactly what is on screen (candidates + saved
     templates), so the answer follows the shelf rather than a guess. */
  const barsDiscriminate = (() => {
    const key = (t) => { const b = statBars(t); return `${b.speed}${b.depth}${b.code}${b.cost}`; };
    return new Set([...candidates, ...(templates || [])].map(key)).size > 1;
  })();

  /* Front-desk cards: present = installed for CLIs/hermes; for local daemons
     only a LIVE probe ('reachable') counts — their detect.installed is true
     from the default URL alone. Detection is a hint, not a verdict (macOS
     keychain creds are invisible), so missing auth reads as "needs a
     sign-in", never "broken". */
  const hiredIds = new Set((currentAgents || []).map(a => a.id));
  const deskCards = (driverList || []).map(d => {
    const def = FRONT_DESK[d.id];
    if (!def || hiredIds.has(def.id)) return null;
    const det = d.detect || {};
    const localDaemon = d.id === 'lmstudio' || d.id === 'ollama';
    if (def.cloud ? !det.authenticated
        : localDaemon ? det.version !== 'reachable' : !det.installed) return null;
    /* `probeError` is set when the CLI RAN and failed — measured on a real
       machine, a Codex shim on PATH whose vendored binary was gone. The
       card still appears, because being installed-but-broken is worth
       knowing and detection is a hint rather than a verdict; what it must
       not do is keep saying "needs a sign-in", which is a different
       diagnosis and sends the boss to fix the wrong thing. */
    /* "Already running on this machine" is the FRONT_DESK line for both
       local daemons, and it used to be true by construction: the proxy and
       the driver disagreed about where LM Studio lived, and the only
       address the DETECTOR ever asked was localhost — so a card that
       appeared had, necessarily, been found locally. Both now read one
       env-configurable address (serve.py `_local_route`), which means a
       backend across the network can be detected for the first time, and
       the same sentence would be a plain untruth on the first screen a new
       boss reads. detect() carries the base URL it actually probed; when
       that host is not loopback, say where it is instead of guessing. */
    const host = localDaemon ? hostOf(det.detail) : '';
    const found = host && !LOOPBACK.test(host)
      ? `Running on ${host}, reachable from here — cheap and tireless.`
      : def.found;
    return { ...def, driverId: d.id, found,
             probeError: det.probeError || '',
             probeDetail: det.probeDetail || '',
             needsLogin: !def.cloud && !localDaemon && d.id !== 'hermes'
                         && !det.probeError && !det.authenticated };
  }).filter(Boolean);

  const hireDetected = async (c) => {
    if (c.elevated && !(await window.hqConfirm(
      `${c.name} works with computer access — reading and writing files and ` +
      `running commands on this machine. Every action is logged and pauses ` +
      `for your approval. Bring them aboard?`,
      { okLabel: `Hire ${c.name}` }))) return;
    onHire({
      id: c.id, name: c.name, role: c.role, color: c.color,
      model: c.model, tools: c.tools, temperature: 0.4,
      status: 'idle', task: 'reporting for duty',
      elevated: !!c.elevated,
      ...(!c.cloud && c.driverId !== 'lmstudio' && c.driverId !== 'ollama'
        ? { cli: c.driverId } : {}),
      hiredAt: Date.now(), lastRun: 'just hired', nextRun: 'on demand',
      recent: 'hired at the front desk',
    });
    onClose();
  };

  const submit = async () => {
    /* Belt and braces: the button below is dark whenever this note is set,
       so this branch should be unreachable from the UI. It stays because a
       silent return is only acceptable when nothing could have got here. */
    if (hireNeedsNote(name, currentAgents, model)) return;
    if (elevated && !(await window.hqConfirm(
      `Hire ${name.trim()} with COMPUTER ACCESS?\n\n` +
      `This agent will be backed by an elevated CafresoHQ session that can read/write files and run shell commands on this machine.\n\n` +
      `· Reachable by teammate DMs — each handoff is noted in the Team thread.\n` +
      `· Research missions are blocked unless you explicitly authorize unattended access.\n` +
      `· Every tool call they make will be logged to Receipts.\n` +
      `· Their actions will pause for your approval before executing.\n\n` +
      `Continue?`, { danger: true, okLabel: 'Hire' }
    ))) return;
    onHire({
      id: HQ.uid('a'),
      name: name.trim(),
      role,
      color: avatar,
      status: 'idle',
      task: 'reporting for duty',
      tools, model, temperature: temp,
      systemPrompt: prompt,
      elevated,
      hiredAt: Date.now(),
      lastRun: 'just hired',
      nextRun: 'on demand',
    });
    onClose();
  };

  const footer = !showBoard ? (
    <>
      {/* The note leads, exactly as #299 put noCrewNote ahead of the
          research costing: while the form cannot go through, what it is
          waiting for outranks a fact about desk assignment. */}
      <div className="hint" style={{marginRight: 'auto'}}>
        {hireNeedsNote(name, currentAgents, model) || 'A new desk will be assigned on spawn.'}
      </div>
      <button className="px-btn secondary" style={{fontSize: 'var(--text-9)'}} onClick={saveAsTemplate}>★ SAVE AS TEMPLATE</button>
      <button className="px-btn secondary" onClick={onClose}>Cancel</button>
      <button className="px-btn primary" onClick={submit}
              disabled={!!hireNeedsNote(name, currentAgents, model)}
              title={hireNeedsNote(name, currentAgents, model) || undefined}>HIRE ✓</button>
    </>
  ) : null;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={showBoard ? 'JOB POSTINGS' : 'BRING IN A HELPER'}
      subtitle={showBoard ? 'pick a saved role · or start from scratch' : 'New hire · character creation'}
      size="lg"
      headerActions={
        <button className="px-btn secondary" style={{fontSize: 'var(--text-9)'}} onClick={() => setShowBoard(b => !b)}>
          {showBoard ? 'NEW HIRE →' : '← TEMPLATES'}
        </button>
      }
      footer={footer}
    >
          {showBoard ? (
            <div className="hire-board">
              {driverList === null && (
                <div className="frontdesk-head" style={{gridColumn: '1 / -1'}}>
                  AT THE FRONT DESK <span className="hint">— checking who's available on this machine…</span>
                </div>
              )}
              {deskCards.length > 0 && (
                <div className="frontdesk-head" style={{gridColumn: '1 / -1'}}>
                  AT THE FRONT DESK <span className="hint">
                    {/* "ready to join" is a promise about every card below it,
                        so it cannot stand over one that will not start. */}
                    {deskCards.some(c => c.probeError)
                      ? '— found on this machine · not all of them are ready'
                      : '— found on this machine, ready to join'}
                  </span>
                </div>
              )}
              {deskCards.map(c => (
                <div key={c.id} className="post-card frontdesk-card"
                     aria-label={`Hire ${c.name}, ${c.role}`}
                     {...cardActivate(() => hireDetected(c))}>
                  <div className="post-head">
                    <Sprite data={c.color} scale={2}/>
                    <div className="post-name">{c.name}</div>
                    <span className="post-tag">
                      {c.probeError ? (c.service ? 'NOT RUNNING' : "WON'T START") : 'FOUND'}
                    </span>
                  </div>
                  <div className="post-role">{c.role}</div>
                  <div className="frontdesk-note" title={c.probeDetail || undefined}>
                    {c.probeError
                      ? `${c.name} is on this machine, but it ${c.probeError}. `
                        + (c.service
                            ? 'Starting it is all it needs. You can hire them now '
                              + 'and start it before their first task.'
                            : 'Signing in will not fix that — it needs repairing or '
                              + 'reinstalling first. You can still hire them and try.')
                      : `${c.found}${c.needsLogin ? ' Needs a sign-in before their first task.' : ''}`}
                  </div>
                  <div className="post-meta">
                    <span>powered by {c.poweredBy}</span>
                    <span>·</span>
                    <span className="frontdesk-cta">HIRE ✓</span>
                  </div>
                </div>
              ))}
              {templates.length === 0 && candidates.length === 0 && deskCards.length === 0 && (
                <div className="empty-state" style={{gridColumn:'1 / -1'}}>
                  <div className="empty-title">No saved roles yet.</div>
                  <div className="empty-sub">Build one with "NEW HIRE →" then click "SAVE AS TEMPLATE" to pin it here for next time.</div>
                </div>
              )}
              {candidates.map(t => (
                <div key={'cand_' + t.name} className="post-card"
                     aria-label={`Open candidate ${t.name}, ${t.role}`}
                     {...cardActivate(() => loadCandidate(t))}>
                  <div className="post-head">
                    <Sprite data={t.color} scale={2}/>
                    <div className="post-name">{t.name}</div>
                    <span className="post-tag">CANDIDATE</span>
                  </div>
                  <div className="post-role">{t.role}</div>
                  <CastLine t={t} showBars={barsDiscriminate} />
                </div>
              ))}
              {templates.map(t => (
                <div key={t.id} className="post-card"
                     aria-label={`Open saved role ${t.name}, ${t.role}`}
                     {...cardActivate(() => loadTpl(t))}>
                  <div className="post-head">
                    <Sprite data={t.avatar} scale={2}/>
                    <div className="post-name">{t.name}</div>
                  </div>
                  <div className="post-role">{t.role}</div>
                  <CastLine t={t} showBars={barsDiscriminate} />
                  <button className="px-btn ghost post-remove" style={{fontSize:8}} onClick={(e)=>{e.stopPropagation(); deleteTpl(t.id);}}>✕</button>
                </div>
              ))}
              <div className="post-card hire-tile"
                   aria-label="Create a new hire from scratch"
                   {...cardActivate(() => setShowBoard(false))}>
                <div className="plus">+<br/>NEW</div>
              </div>
              {candidates.length > 0 && (
                <div
                  className="post-card hire-tile"
                  aria-label={`Seed swarm: hire all ${candidates.length} specialists at once`}
                  {...cardActivate(async () => {
                    /* Hiring seven coworkers onto a brain that does not
                       exist is seven desks that can never answer, and the
                       confirm used to promise it cheerfully. This guard used
                       to read `!probing && !shelfBrain` — which only
                       suppressed the WARNING while still probing, not the
                       hire itself. A boss who clicked SEED SWARM before the
                       front-desk probe resolved (driverList still null, a
                       real window: "checking who's available on this
                       machine…" is on screen for a few seconds on every
                       cold open) skipped this check entirely: `shelfBrain`
                       is `undefined` while probing (line ~317), so below,
                       `spawnOpenswarmRoster(currentAgents, onHire,
                       shelfBrain)` passes `model: undefined`, hq-runtime.jsx
                       treats that as "keep the template's own value" via
                       `...(model ? { model } : {})`, and every template's
                       hardcoded `cafresohq:sonnet` goes out the door
                       whether or not this machine has ever seen Claude —
                       the exact "quietly picks Claude" outcome
                       app/cast.jsx's candidateBrain() comment says a caller
                       must never let an unresolved answer become. Probing
                       now blocks the hire on its own, before shelfBrain is
                       ever read. */
                    if (probing) {
                      await window.hqConfirm(
                        `Still checking what's available on this machine — try SEED SWARM again in a moment.`,
                        { okLabel: 'Got it', hideCancel: true });
                      return;
                    }
                    if (!shelfBrain) {
                      await window.hqConfirm(
                        `There is no brain on this machine yet, so these ${candidates.length} would sit at their desks unable to work.\n\n` +
                        `Add one in Settings → Connections — a free local one (LM Studio, Ollama) is enough — then hire the shelf.`,
                        { okLabel: 'Got it', hideCancel: true });
                      return;
                    }
                    const ok = await window.hqConfirm(
                      `Hire ${candidates.length} openswarm-style specialist${candidates.length === 1 ? '' : 's'}: ${candidates.map(t => t.name).join(', ')}?`,
                      { okLabel: `Hire ${candidates.length}` });
                    if (!ok) return;
                    HQ.spawnOpenswarmRoster(currentAgents, onHire, shelfBrain);
                    onClose();
                  })}
                  style={{ background: 'linear-gradient(135deg, var(--accent-sun-10, rgba(218,165,32,0.12)) 0%, transparent 100%)', border: '2px solid var(--accent-sun, #d4a017)' }}
                  title={probing
                    ? 'Still checking what\'s available on this machine…'
                    : `Hire the whole shelf at once: ${candidates.map(c => c.name).join(", ")}`}
                >
                  <div className="plus" style={{ fontSize: 18, lineHeight: 1.2, padding: 8 }}>
                    ⚡<br/>SEED<br/>SWARM<br/>
                    <span style={{ fontSize: 8, opacity: 0.7 }}>+{candidates.length}</span>
                  </div>
                </div>
              )}
            </div>
          ) : (
          <div className="form-grid">
            <div className="form-row">
              <label>NAME</label>
              <input placeholder="e.g. Nova" value={name} onChange={e=>setName(e.target.value)} />
              <span className="hint">what your colleagues will call them</span>
            </div>
            <div className="form-row">
              <label>ROLE / TITLE</label>
              <select value={role} onChange={e=>setRole(e.target.value)}>
                {/* Candidate/template roles aren't always in ROLES — keep the
                    current value selectable so the select never renders blank. */}
                {!HQ.ROLES.includes(role) && <option key={role}>{role}</option>}
                {HQ.ROLES.map(r => <option key={r}>{r}</option>)}
              </select>
              <span className="hint">make it playful</span>
            </div>
            <div className="form-row full">
              {/* §6, binding: "system prompt" is on the never-say list —
                  "job description" is the office word for the exact same
                  field ("This IS the system prompt — we just never call
                  it that", §2). The character-creation form was still
                  using the raw term. */}
              <label>JOB DESCRIPTION</label>
              <textarea rows={4} value={prompt} onChange={e=>setPrompt(e.target.value)} />
            </div>
            <div className="form-row">
              {/* Same rule, same fix as the coworker card's Brain field —
                  "Model" as a selector label is banned outright. The
                  picker itself still needs to show real ids (you're
                  choosing exactly which one), same as Settings. */}
              <label>BRAIN</label>
              <ModelPicker value={model} onChange={setModel} />
              {/* The guided front desk only ever offers brains it FOUND on
                  this machine ("We found your Claude subscription…"). This
                  manual form offers all 27 and defaults to
                  `anthropic:claude-haiku-…` — so on a fresh install, where
                  the topbar is already showing ⚠ ADD AI KEY, a boss could
                  build a coworker, hire them, drop a task on their desk and
                  only then learn the brain was never signed in.

                  The office already knows the answer: `hasUsableKey` is what
                  drives that very chip. Applying it here costs nothing, and
                  §7 says a block names its route out. */}
              {(() => {
                const { provider, model: pinned } = CafresoHQClient.parseModelId(model) || {};
                if (!provider) return null;
                /* `hasUsableKey` answers "is this provider configured as the
                   DEFAULT", and for the local ones that means "has a model
                   been picked in Settings". A per-agent brain pins its own
                   model in the id (`ollama:llama3.1:latest`), so the global
                   setting is irrelevant — feed the pinned model in, or the
                   warning fires on a brain that runs perfectly well.

                   Caught by checking: the first version of this warning did
                   not clear when the local brain was selected, which would
                   have put a false alarm on every hire. */
                const probe = Object.assign({}, CafresoHQClient.getSettings(), { provider });
                if (pinned && provider === 'ollama')   probe.ollamaModel = pinned;
                if (pinned && provider === 'lmstudio') probe.lmstudioModel = pinned;
                const ready = CafresoHQClient.hasUsableKey(probe);
                return ready
                  ? <span className="hint">each option is one real brain, grouped by who runs it</span>
                  : <span className="hint" style={{color:'#E8A9A9'}}>
                      ⚠ this brain isn't signed in yet — they can be hired, but can't work until you add it in Settings → Connections
                    </span>;
              })()}
            </div>
            <div className="form-row">
              {/* §6's table bans "temperature" outright and prescribes the
                  replacement in the same row: "(hidden; 'creativity' dial
                  behind Advanced if ever)". This form is the Advanced half
                  already — the quick-hire candidate cards, which is what a
                  first run actually meets, carry no such dial at all — so
                  the placement was fine and only the word was wrong.

                  Missed by the §6 pass that did this very form: it caught
                  SYSTEM PROMPT → JOB DESCRIPTION and MODEL → BRAIN, and left
                  the third banned term sitting in the row between them. The
                  hint underneath ("0 = precise · 1 = spicy") was already
                  doing the explaining, which is probably why the label read
                  as harmless. */}
              <label>CREATIVITY · {temp.toFixed(2)}</label>
              <input type="range" className="pxslider" min="0" max="1" step="0.05" value={temp} onChange={e=>setTemp(parseFloat(e.target.value))}/>
              <span className="hint">0 = precise · 1 = spicy</span>
            </div>
            <div className="form-row full">
              <label>ALLOWED TOOLS</label>
              {/* Same hole `cardActivate` closed on the board above, one
                  layer deeper: these ticks were an onClick-only div with no
                  role and no place in the tab order, so Tab from CREATIVITY
                  landed on PRIVILEGES and a keyboard-only boss could not
                  grant or deny a single tool. Reusing `cardActivate` (not a
                  second copy of Enter/Space handling) keeps this from
                  drifting from the board fix the next time either is
                  touched; role/aria-checked are overridden after the spread
                  since these are toggles, not plain buttons like the board. */}
              <div className="tool-grid">
                {visibleToolsCatalog().map(t => (
                  <div key={t.id} className={`tool-chk ${tools.includes(t.id)?'on':''}`}
                       {...cardActivate(()=>toggleTool(t.id))} role="checkbox" aria-checked={tools.includes(t.id)}>
                    <div className="box" />
                    <span>{t.label}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="form-row full">
              <label>AVATAR</label>
              <div className="avatar-picker">
                {HQ.AGENT_COLORS.map(c => (
                  <div key={c} className={`slot ${avatar===c?'selected':''}`}
                       {...cardActivate(()=>setAvatar(c))} role="radio" aria-checked={avatar===c}>
                    <Sprite data={c} scale={2}/>
                  </div>
                ))}
              </div>
            </div>
            <div className={`form-row full elevated-opt ${elevated ? 'on' : ''}`}>
              <label>PRIVILEGES</label>
              <label style={{display:'flex',alignItems:'flex-start',gap:8,fontFamily:'VT323',fontSize:16,cursor:'pointer',lineHeight:1.3}}>
                <input type="checkbox" checked={elevated} onChange={e=>setElevated(e.target.checked)} style={{marginTop:3}}/>
                <span>
                  <b style={{color: elevated ? '#c44' : 'inherit'}}>🛡 FILE & SHELL ACCESS</b><br/>
                  <span className="hint" style={{display:'block',marginTop:2}}>
                    Backed by a CafresoHQ session with file and shell access on this machine. Reachable by teammate DMs (each handoff noted in Team), missions opt-in, every action logged.
                  </span>
                </span>
              </label>
            </div>
          </div>
          )}
    </Modal>
  );
}

/* ── Settings shell registry ────────────────────────────────────────────────
   Single source of truth for the settings nav: id, icon, label, one-line
   description. Order = display order; first entry is the default tab (the
   most-actioned one — Connections). Legacy deep-link ids map via ALIAS. */
/* Managed premium: Cafreso provisions the container, brain, keys and CLIs on
   OCI — so the self-host setup surface (CONNECTIONS / CODE AGENTS / SYSTEM /
   MEDIA provider pickers) is gone from Settings entirely. ApiTab and the two
   CLI panels it renders still exist in modals/providers.jsx for a future
   self-host build flag, unreachable from the UI. This note used to say that
   of the whole file; #37/#39/#40/#60 have since mounted VaultTab, BraveTab,
   MediaTab and BrowserKeysTab under Connections and Media, and #123 found
   the stale version of this claim load-bearing for a deletion elsewhere.
   ACCOUNT replaces SYSTEM as the "is my HQ
   healthy" surface, in plan-and-usage language instead of gateway jargon. */

export { HireModal };
