import { CafresoHQClient } from '../claude-client.jsx';
import { HQ } from '../hq-runtime.jsx';
import { Sprite } from '../sprites.jsx';
import { brainName, candidateBrain, canDoPhrase, poweredBy, specialtyTag, statBars } from '../app/cast.jsx';
import { Modal, ModelPicker, loadTemplates, saveTemplates } from './base.jsx';
import { visibleToolsCatalog } from './settings.jsx';
const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;

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
   hand the tool over, so the card and `toolsForAgent` cannot disagree:

     canSearch      TOOL_REGISTRY.search.requires() — braveEnabled && braveKey
     elevated       the candidate's own flag, which is what gates FILE_* / BASH
     canMakeImages  settings.imageProvider, same check toolsForAgent makes
     moneyOn        window.hqMoneyOn(), the Wallet ICP-Service switch

   Wrapped in a try because this runs during render on the first screen of a
   fresh install, and a settings store that is not up yet must produce a
   quieter card, never a broken one. The catch leaves the flags ABSENT, not
   false, and the difference is load-bearing in both directions: absent is
   falsey, so nothing gets promised, and `canDoPhrase` can still tell "the
   boss has not set an image provider" from "we could not find out", which
   is what stops an unreadable settings store from telling a boss who
   already configured one to go and configure one. */
function capabilityFacts(t) {
  const f = { elevated: !!(t && t.elevated) };
  try {
    const s = CafresoHQClient.getSettings();
    f.canSearch = !!(s && s.braveEnabled && s.braveKey);
    f.canMakeImages = !!(s && s.imageProvider);
  } catch (_e) { /* leave both false */ }
  try { f.moneyOn = !!(window.hqMoneyOn && window.hqMoneyOn()); } catch (_e) {}
  return f;
}

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
  const [tools, setTools] = useStateM(['web','files']);
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
    setTools(['web','files']); setAvatar('rose');
    setModel('anthropic:claude-haiku-4-5-20251001'); setTemp(0.4);
    setElevated(false); setShowBoard(true);
  }, [open]);

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
    const tplName = ((await window.hqPrompt('Save this configuration as a template — name it (e.g., "Researcher", "Inbox triage"):')) || '').trim();
    if (!tplName) return;
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
  /* The brain the shelf will actually use, from the SAME detection the
     front-desk row above is drawn from — see candidateBrain in cast.jsx for
     what this is fixing. `driverList === null` means still probing, and
     unknown is not "nothing found": the cards hold their brain line until
     the probe lands rather than flashing "no brain yet" at every boss for
     the few seconds a deep probe takes.

     readyIds is deliberately STRICTER than "has a desk card". Hermes gets a
     card reading NOT RUNNING and Codex one reading WON'T START — both worth
     showing, neither able to take a job — so neither may be the brain a
     specialist is silently hired onto. */
  const candidateReady = (d) => {
    const det = (d && d.detect) || {};
    if (d.id === 'lmstudio' || d.id === 'ollama') return det.version === 'reachable';
    if (d.id === 'hermes') return det.installed && det.version === 'reachable';
    if (FRONT_DESK[d.id] && FRONT_DESK[d.id].cloud) return !!det.authenticated;
    return !!det.installed && !det.probeError;
  };
  const probing = driverList === null;
  const readyIds = (driverList || []).filter(candidateReady).map(d => d.id);
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
    if (!name.trim()) return;
    if (elevated && !(await window.hqConfirm(
      `Hire ${name.trim()} with COMPUTER ACCESS?\n\n` +
      `This agent will be backed by an elevated CafresoHQ session that can read/write files and run shell commands on this machine.\n\n` +
      `· Inter-agent DMs cannot reach them (only your direct dispatches will).\n` +
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
      <div className="hint" style={{marginRight: 'auto'}}>A new desk will be assigned on spawn.</div>
      <button className="px-btn secondary" style={{fontSize: 'var(--text-9)'}} onClick={saveAsTemplate}>★ SAVE AS TEMPLATE</button>
      <button className="px-btn secondary" onClick={onClose}>Cancel</button>
      <button className="px-btn primary" onClick={submit}>HIRE ✓</button>
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
                <div key={c.id} className="post-card frontdesk-card" onClick={() => hireDetected(c)}>
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
                <div key={'cand_' + t.name} className="post-card" onClick={() => loadCandidate(t)}>
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
                <div key={t.id} className="post-card" onClick={()=>loadTpl(t)}>
                  <div className="post-head">
                    <Sprite data={t.avatar} scale={2}/>
                    <div className="post-name">{t.name}</div>
                  </div>
                  <div className="post-role">{t.role}</div>
                  <CastLine t={t} showBars={barsDiscriminate} />
                  <button className="px-btn ghost post-remove" style={{fontSize:8}} onClick={(e)=>{e.stopPropagation(); deleteTpl(t.id);}}>✕</button>
                </div>
              ))}
              <div className="post-card hire-tile" onClick={()=>setShowBoard(false)}>
                <div className="plus">+<br/>NEW</div>
              </div>
              {candidates.length > 0 && (
                <div
                  className="post-card hire-tile"
                  onClick={async () => {
                    /* Hiring seven coworkers onto a brain that does not
                       exist is seven desks that can never answer, and the
                       confirm used to promise it cheerfully. */
                    if (!probing && !shelfBrain) {
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
                  }}
                  style={{ background: 'linear-gradient(135deg, var(--accent-sun-10, rgba(218,165,32,0.12)) 0%, transparent 100%)', border: '2px solid var(--accent-sun, #d4a017)' }}
                  title={`Hire the whole shelf at once: ${candidates.map(c => c.name).join(", ")}`}
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
              <div className="tool-grid">
                {visibleToolsCatalog().map(t => (
                  <div key={t.id} className={`tool-chk ${tools.includes(t.id)?'on':''}`} onClick={()=>toggleTool(t.id)}>
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
                  <div key={c} className={`slot ${avatar===c?'selected':''}`} onClick={()=>setAvatar(c)}>
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
                    Backed by a CafresoHQ session with file and shell access on this machine. DMs blocked, missions opt-in, every action logged.
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
   MEDIA provider pickers) is gone from Settings entirely. The tab components
   still exist below (ApiTab etc.) for a future self-host build flag, they're
   just not reachable from the UI. ACCOUNT replaces SYSTEM as the "is my HQ
   healthy" surface, in plan-and-usage language instead of gateway jargon. */

export { HireModal };
