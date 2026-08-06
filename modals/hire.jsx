import { CafresoHQClient } from '../claude-client.jsx';
import { HQ } from '../hq-runtime.jsx';
import { Sprite } from '../sprites.jsx';
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
const FRONT_DESK = {
  'claude-code': { id: 'a_cli_claude', name: 'Claude', role: 'Coding Agent', color: 'leaf',
                   model: 'claudecode:sonnet', tools: ['files', 'shell', 'web'], elevated: true,
                   poweredBy: 'Claude', found: 'We found your Claude subscription on this machine.' },
  'codex':       { id: 'a_cli_codex', name: 'Codex', role: 'Coding Agent', color: 'mint',
                   model: 'codex:gpt-4.1', tools: ['files', 'shell'], elevated: true,
                   poweredBy: 'OpenAI', found: 'We found your Codex subscription on this machine.' },
  'hermes':      { id: 'a_cli_hermes', name: 'Hermes', role: 'Resident Agent', color: 'sky',
                   model: 'hermes:hermes-agent', tools: ['web', 'files', 'shell'], elevated: true,
                   poweredBy: 'Nous Research', found: 'The house agent — already moved in and ready to work.' },
  'lmstudio':    { id: 'a_local_lmstudio', name: 'Local Brain', role: 'Local Model · your hardware', color: 'teal',
                   model: 'lmstudio:local-model', tools: ['web'],
                   poweredBy: 'LM Studio', found: 'A local model is running on this machine — cheap and tireless.' },
  'ollama':      { id: 'a_local_ollama', name: 'Llama', role: 'Local Model · your hardware', color: 'sun',
                   model: 'ollama:llama3.1', tools: ['web'],
                   poweredBy: 'Ollama', found: 'A local model is running on this machine — cheap and tireless.' },
  'openrouter':  { id: 'a_cloud_openrouter', name: 'OpenRouter', role: 'Cloud Model · your account', color: 'rose',
                   model: 'openrouter:openai/gpt-oss-120b:free', tools: ['web'], cloud: true,
                   poweredBy: 'OpenRouter', found: 'Your OpenRouter account is connected to this workspace.' },
  'groq':        { id: 'a_cloud_groq', name: 'Groq', role: 'Cloud Model · your account', color: 'blush',
                   model: 'groq:llama-3.3-70b-versatile', tools: ['web'], cloud: true,
                   poweredBy: 'Groq', found: 'Your Groq account is connected to this workspace.' },
  'gemini-api':  { id: 'a_cloud_gemini', name: 'Gemini', role: 'Cloud Model · your account', color: 'cafresohq',
                   model: 'gemini-api:gemini-2.5-flash', tools: ['web'], cloud: true,
                   poweredBy: 'Google', found: 'Your Google AI account is connected to this workspace.' },
};
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
    setPrompt('You are a helpful sub-agent. Be concise and warm.');
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
  const saveAsTemplate = () => {
    const tplName = (window.prompt('Save this configuration as a template — name it (e.g., "Researcher", "Inbox triage"):') || '').trim();
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
  const candidates = (HQ.OPENSWARM_ROSTER || []).filter(t => !hiredNames.has(t.name.toLowerCase()));

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
    return { ...def, driverId: d.id,
             needsLogin: !def.cloud && !localDaemon && d.id !== 'hermes' && !det.authenticated };
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

  const submit = () => {
    if (!name.trim()) return;
    if (elevated && !window.confirm(
      `Hire ${name.trim()} with COMPUTER ACCESS?\n\n` +
      `This agent will be backed by an elevated CafresoHQ session that can read/write files and run shell commands on this machine.\n\n` +
      `· Inter-agent DMs cannot reach them (only your direct dispatches will).\n` +
      `· Research missions are blocked unless you explicitly authorize unattended access.\n` +
      `· Every tool call they make will be logged to Receipts.\n` +
      `· Their actions will pause for your approval before executing.\n\n` +
      `Continue?`
    )) return;
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
      title={showBoard ? 'JOB POSTINGS' : 'HIRE A SUB-AGENT'}
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
                  AT THE FRONT DESK <span className="hint">— found on this machine, ready to join</span>
                </div>
              )}
              {deskCards.map(c => (
                <div key={c.id} className="post-card frontdesk-card" onClick={() => hireDetected(c)}>
                  <div className="post-head">
                    <Sprite data={c.color} scale={2}/>
                    <div className="post-name">{c.name}</div>
                    <span className="post-tag">FOUND</span>
                  </div>
                  <div className="post-role">{c.role}</div>
                  <div className="frontdesk-note">
                    {c.found}{c.needsLogin ? ' Needs a sign-in before their first task.' : ''}
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
                  <div className="post-meta">
                    <span>{(t.model||'').replace(/^[a-z]+:/,'') || '—'}</span>
                    <span>·</span>
                    <span>{(t.tools||[]).length} tool{(t.tools||[]).length===1?'':'s'}</span>
                  </div>
                </div>
              ))}
              {templates.map(t => (
                <div key={t.id} className="post-card" onClick={()=>loadTpl(t)}>
                  <div className="post-head">
                    <Sprite data={t.avatar} scale={2}/>
                    <div className="post-name">{t.name}</div>
                  </div>
                  <div className="post-role">{t.role}</div>
                  <div className="post-meta">
                    <span>{(t.model||'').replace(/^[a-z]+:/,'') || '—'}</span>
                    <span>·</span>
                    <span>{(t.tools||[]).length} tool{t.tools.length===1?'':'s'}</span>
                  </div>
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
                    const ok = await window.hqConfirm(
                      `Hire ${candidates.length} openswarm-style specialist${candidates.length === 1 ? '' : 's'}: ${candidates.map(t => t.name).join(', ')}?`,
                      { okLabel: `Hire ${candidates.length}` });
                    if (!ok) return;
                    HQ.spawnOpenswarmRoster(currentAgents, onHire);
                    onClose();
                  }}
                  style={{ background: 'linear-gradient(135deg, var(--accent-sun-10, rgba(218,165,32,0.12)) 0%, transparent 100%)', border: '2px solid var(--accent-sun, #d4a017)' }}
                  title="Seed openswarm-style roster: Vera, Kip, Dax, Sloan, Quill, Pixel, Reel"
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
              <label>SYSTEM PROMPT</label>
              <textarea rows={4} value={prompt} onChange={e=>setPrompt(e.target.value)} />
            </div>
            <div className="form-row">
              <label>MODEL</label>
              <ModelPicker value={model} onChange={setModel} />
              <span className="hint">backend is encoded in the id (anthropic / lmstudio / ollama)</span>
            </div>
            <div className="form-row">
              <label>TEMPERATURE · {temp.toFixed(2)}</label>
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
                  <b style={{color: elevated ? '#c44' : 'inherit'}}>🛡 ELEVATED — computer access</b><br/>
                  <span className="hint" style={{display:'block',marginTop:2}}>
                    Backed by an elevated CafresoHQ session that can read/write files and run shell commands on this machine. DMs blocked, missions opt-in, every action logged.
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
