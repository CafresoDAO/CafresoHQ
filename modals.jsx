/* ==========================================================================
   CafresoHQ — modals (Hire / Settings)
   ========================================================================== */

const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;

/* Single source of truth for settings — subscribes to the client's pub/sub so
   any component using this hook re-renders whenever setSettings() is called,
   even from a different component tree. */
function useSettingsStore() {
  const [s, setS] = useStateM(() => window.CafresoHQClient.getSettings());
  useEffectM(() => {
    return window.CafresoHQClient.onSettingsChange(fresh => setS({ ...fresh }));
  }, []);
  return [s, patch => window.CafresoHQClient.setSettings(patch)];
}

/* Live model picker — loads all providers from localModelOptions(), which now
   has per-fetch AbortController timeouts on slow local services (LM Studio,
   Ollama) so it resolves quickly. Falls back to static lists only if the
   whole function rejects (shouldn't happen in normal use). */
function ModelPicker({ value, onChange, refreshKey }) {
  const [groups, setGroups] = useStateM([]);
  const [loading, setLoading] = useStateM(true);
  const [error, setError] = useStateM(false);
  useEffectM(() => {
    let live = true;
    setLoading(true);
    setError(false);
    window.CafresoHQClient.localModelOptions()
      .then(g => {
        if (!live) return;
        setGroups(g);
        setLoading(false);
      })
      .catch(() => {
        if (!live) return;
        /* Last-resort fallback — all static model lists so the picker
           is never blank. Static lists only. */
        const s = window.CafresoHQClient.getSettings();
        const fallback = [
          { label: 'Anthropic (Claude API)', provider: 'anthropic',
            options: window.CafresoHQClient.ANTHROPIC_MODELS.map(m => ({ id: 'anthropic:' + m, label: m })) },
          { label: 'Google (Gemini API)', provider: 'google',
            options: window.CafresoHQClient.GEMINI_MODELS.map(m => ({ id: 'google:' + m, label: m })) },
          { label: 'Codex CLI', provider: 'codex',
            options: window.CafresoHQClient.CODEX_MODELS.map(m => ({ id: 'codex:' + m, label: m })) },
        ];
        setGroups(fallback);
        setLoading(false);
        setError(true);
      });
    return () => { live = false; };
  }, [refreshKey]);

  const flat = groups.flatMap(g => g.options);
  const known = flat.some(o => o.id === value);
  return (
    <select value={known ? value : ''} onChange={e => onChange(e.target.value)}
      title={error ? 'Static fallback — proxy unreachable' : undefined}>
      {!known && <option value="">{loading ? 'loading…' : (value || '— pick a model —')}</option>}
      {groups.map(g => (
        <optgroup key={g.provider} label={g.label}>
          {g.options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
        </optgroup>
      ))}
    </select>
  );
}

const TEMPLATES_KEY = 'cafresohq_hire_templates_v1';
function loadTemplates() {
  try { return JSON.parse(localStorage.getItem(TEMPLATES_KEY) || '[]'); }
  catch (_e) { return []; }
}
function saveTemplates(ts) {
  try { localStorage.setItem(TEMPLATES_KEY, JSON.stringify(ts)); }
  catch (err) {
    console.warn('[cafresohq] saveTemplates failed:', err);
    try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key: TEMPLATES_KEY, error: err } })); } catch (_e) {}
  }
}

/* ─────────────────────────────────────────────────────────────────────
   <Modal>
   Reusable shell for every dialog in the app. Provides:
     · Backdrop with click-to-close
     · Esc to close (skips when typing in inputs/textareas)
     · Focus trap — first focusable element auto-focused; Tab/Shift-Tab
       cycle within the modal; focus returns to the trigger on close
     · Scroll lock on <body>
     · Animated entry/exit using motion tokens
     · Header with title/subtitle + optional `headerActions` slot
     · Body and optional `footer` slots
     · `size` controls width: sm/md/lg/xl/fullscreen

   Migration note: existing modals can keep their .modal-head and .modal-body
   CSS classes — we render with `data-modal-shell` so old per-modal styles still
   apply, but the new shell handles a11y and motion uniformly.

   Props:
     open         (bool)              — render or null
     onClose      (fn)                 — invoked by ✕ / Esc / backdrop
     title        (node)               — main heading
     subtitle     (node, optional)     — kicker line below title
     headerActions (node, optional)    — extra buttons in the header right side
     footer       (node, optional)     — sticky footer area below body
     size         (str, default 'md')  — 'sm' | 'md' | 'lg' | 'xl' | 'fullscreen'
     dismissable  (bool, default true) — set false to prevent backdrop/Esc close
     children     (node)               — body content
   ───────────────────────────────────────────────────────────────────── */
const MODAL_SIZE_MAX_WIDTH = { sm: 420, md: 560, lg: 760, xl: 980, fullscreen: '100vw' };

function Modal({ open, onClose, title, subtitle, headerActions, footer, size = 'md', dismissable = true, children }) {
  const dialogRef = useRefM(null);
  const triggerRef = useRefM(null);
  const [entered, setEntered] = useStateM(false);

  /* Capture the focused element when opening so we can restore on close. */
  useEffectM(() => {
    if (open) {
      triggerRef.current = document.activeElement;
      // animate in next frame
      requestAnimationFrame(() => setEntered(true));
    } else {
      setEntered(false);
      // restore focus to whatever opened us
      if (triggerRef.current && typeof triggerRef.current.focus === 'function') {
        triggerRef.current.focus();
      }
      triggerRef.current = null;
    }
  }, [open]);

  /* Body scroll lock while open. */
  useEffectM(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  /* Esc to close + focus trap. */
  useEffectM(() => {
    if (!open) return;
    const node = dialogRef.current;
    if (!node) return;

    /* Auto-focus the first focusable thing in the dialog. */
    const focusables = () => Array.from(node.querySelectorAll(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(el => el.offsetParent !== null || el === document.activeElement);

    const firstFocus = setTimeout(() => {
      const list = focusables();
      if (list.length) list[0].focus();
      else node.focus();
    }, 30);

    const onKey = (e) => {
      if (e.key === 'Escape' && dismissable) {
        e.stopPropagation();
        onClose && onClose();
        return;
      }
      if (e.key === 'Tab') {
        const list = focusables();
        if (list.length === 0) { e.preventDefault(); node.focus(); return; }
        const first = list[0];
        const last  = list[list.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
      }
    };
    node.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(firstFocus);
      node.removeEventListener('keydown', onKey);
    };
  }, [open, dismissable]);

  if (!open) return null;

  const maxW = MODAL_SIZE_MAX_WIDTH[size] || MODAL_SIZE_MAX_WIDTH.md;
  const isFull = size === 'fullscreen';

  return (
    <div
      className="backdrop"
      data-modal-shell
      onClick={() => dismissable && onClose && onClose()}
      style={{
        zIndex: 'var(--z-modal)',
        opacity: entered ? 1 : 0,
        transition: 'opacity var(--motion-base) var(--ease-out)',
      }}
    >
      <div
        className="modal"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'oc-modal-title' : undefined}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: isFull ? '100vw' : (typeof maxW === 'number' ? maxW + 'px' : maxW),
          width:    isFull ? '100vw' : 'min(94vw, ' + (typeof maxW === 'number' ? maxW + 'px' : maxW) + ')',
          height:   isFull ? '100vh' : undefined,
          maxHeight: isFull ? '100vh' : '90vh',
          transform: entered ? 'translateY(0) scale(1)' : 'translateY(8px) scale(0.985)',
          transition: 'transform var(--motion-base) var(--ease-out)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {(title || subtitle || headerActions) && (
          <div className="modal-head">
            <div>
              {title && <div className="title" id="oc-modal-title">{title}</div>}
              {subtitle && <div className="sub">{subtitle}</div>}
            </div>
            <div style={{display: 'flex', gap: 'var(--sp-3)', alignItems: 'center'}}>
              {headerActions}
              {dismissable && (
                <button
                  className="px-btn ghost"
                  onClick={() => onClose && onClose()}
                  style={{color: '#fff8ee', borderColor: '#fff8ee'}}
                  aria-label="Close dialog"
                  title="Close (Esc)"
                >CLOSE ✕</button>
              )}
            </div>
          </div>
        )}
        <div className="modal-body" style={{flex: 1, minHeight: 0}}>
          {children}
        </div>
        {footer && (
          <div className="modal-foot" style={{
            padding: 'var(--sp-4) var(--sp-6)',
            borderTop: '1px solid var(--rule)',
            background: 'var(--paper-2)',
            display: 'flex',
            gap: 'var(--sp-3)',
            justifyContent: 'flex-end',
            flexShrink: 0,
          }}>{footer}</div>
        )}
      </div>
    </div>
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

  /* Reset the form whenever the modal (re)opens so a previous draft never bleeds
     into a fresh hire. Mirrors MeetingRoomModal's [open]-effect. */
  useEffectM(() => {
    if (!open) return;
    setName(''); setRole(MOCK.ROLES[0]);
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
              {templates.length === 0 && (
                <div className="empty-state" style={{gridColumn:'1 / -1'}}>
                  <div className="empty-title">No saved roles yet.</div>
                  <div className="empty-sub">Build one with "NEW HIRE →" then click "SAVE AS TEMPLATE" to pin it here for next time.</div>
                </div>
              )}
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
              {(() => {
                const haveNames = new Set((currentAgents || []).map(a => String(a.name || '').toLowerCase()));
                const missing = (HQ.OPENSWARM_ROSTER || []).filter(t => !haveNames.has(t.name.toLowerCase()));
                if (!missing.length) return null;
                return (
                  <div
                    className="post-card hire-tile"
                    onClick={() => {
                      if (!window.confirm(`Hire ${missing.length} openswarm-style specialist${missing.length === 1 ? '' : 's'}: ${missing.map(t => t.name).join(', ')}?`)) return;
                      HQ.spawnOpenswarmRoster(currentAgents, onHire);
                      onClose();
                    }}
                    style={{ background: 'linear-gradient(135deg, var(--accent-sun-10, rgba(218,165,32,0.12)) 0%, transparent 100%)', border: '2px solid var(--accent-sun, #d4a017)' }}
                    title="Seed openswarm-style roster: Vera, Kip, Dax, Sloan, Quill, Pixel, Reel"
                  >
                    <div className="plus" style={{ fontSize: 18, lineHeight: 1.2, padding: 8 }}>
                      ⚡<br/>SEED<br/>SWARM<br/>
                      <span style={{ fontSize: 8, opacity: 0.7 }}>+{missing.length}</span>
                    </div>
                  </div>
                );
              })()}
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
                {HQ.TOOLS_CATALOG.map(t => (
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
const SETTINGS_TABS = [
  { id: 'keys',        ico: '🔌', label: 'CONNECTIONS', desc: 'brain · keys · search' },
  { id: 'agentcli',    ico: '🤖', label: 'CODE AGENTS', desc: 'CLIs in your container' },
  { id: 'icp-services',ico: '⛓', label: 'ICP SERVICES',desc: 'wallets · publish · on-chain' },
  { id: 'agents',      ico: '👥', label: 'ROSTER',      desc: 'per-agent config' },
  { id: 'media',       ico: '🎨', label: 'MEDIA',       desc: 'image & video gen' },
  { id: 'appearance',  ico: '🖥', label: 'APPEARANCE',  desc: 'theme & ambience' },
  { id: 'system',      ico: '🛰', label: 'SYSTEM',      desc: 'health & runtime' },
];
const SETTINGS_TAB_ALIAS = { global: 'appearance' }; // old id → new id

/* Search index — one entry per meaningful control so "key", "model", "dark"
   etc. jump straight to the right drawer. kw = extra match terms. */
const SETTINGS_INDEX = [
  { tab:'keys', label:'Backend provider', hint:'which brain powers CafresoHQ & crew', kw:'provider brain hermes anthropic google lmstudio ollama claudecode codex' },
  { tab:'keys', label:'Hermes model', hint:'free open-weights model presets', kw:'model preset gpt-oss nemotron llama' },
  { tab:'keys', label:'Backend service', hint:'OpenRouter · Gemini · Groq (free keys)', kw:'openrouter gemini groq free reliable service' },
  { tab:'keys', label:'Service API key', hint:'your personal free key for the backend service', kw:'key api sk-or aiza gsk openrouter gemini groq' },
  { tab:'keys', label:'Agent capability', hint:'Lite (free-tier safe) vs Full prompt', kw:'capability lite full prompt 413' },
  { tab:'keys', label:'Max tokens per reply', hint:'caps response length', kw:'tokens length limit' },
  { tab:'keys', label:'Connection test', hint:'verifies keys/URL work', kw:'test probe verify' },
  { tab:'keys', label:'Sub-agent model', hint:'pin or inherit the spawner model', kw:'subagent pin inherit spawn' },
  { tab:'keys', label:'Anthropic key & model', hint:'BYOK Claude via API credits', kw:'anthropic claude key' },
  { tab:'keys', label:'Google key & model', hint:'BYOK Gemini via API credits', kw:'google gemini key' },
  { tab:'keys', label:'LM Studio / Ollama URL', hint:'local OpenAI-compatible servers', kw:'lmstudio ollama local url base' },
  { tab:'keys', label:'Claude Code / Codex CLI', hint:'CLI path override + model', kw:'claudecode codex cli path' },
  { tab:'keys', label:'Brave web search', hint:'web search tool + API key', kw:'brave search web key' },
  { tab:'keys', label:'Vault backend', hint:'markdown vault storage + browser', kw:'vault notes markdown obsidian rest' },
  { tab:'agentcli', label:'Install code agents', hint:'add Claude Code / Codex / Gemini CLI on demand', kw:'install npm cli agents claude codex gemini version' },
  { tab:'icp-services', label:'ICP Services catalog', hint:'install on-chain services like adding an MCP', kw:'icp internet computer dfinity service catalog install marketplace on-chain blockchain wallet publish canister' },
  { tab:'icp-services', label:'Agent wallet', hint:'per-agent on-chain wallet + spend cap', kw:'wallet icp ckusdt ckuni token balance fund send cap spend agent money crypto' },
  { tab:'icp-services', label:'Publish to canister', hint:'ship a site to a *.icp0.io URL', kw:'publish canister deploy site url icp0 web hosting' },
  { tab:'agents', label:'Agent model & temperature', hint:'per-agent brain settings', kw:'roster model temperature creativity' },
  { tab:'agents', label:'Agent tools', hint:'which tools each agent may use', kw:'tools catalog permissions' },
  { tab:'agents', label:'Tool call format', hint:'JSON vs bracket fallback', kw:'json bracket format' },
  { tab:'agents', label:'Elevated · computer access', hint:'file/shell access per agent', kw:'elevated computer shell files access security' },
  { tab:'agents', label:'Dismiss an agent', hint:'remove a hire from the roster', kw:'dismiss fire let go remove' },
  { tab:'media', label:'Image generation', hint:'provider + model for Pixel', kw:'image generation openai fal a1111 comfyui pixel' },
  { tab:'media', label:'Video generation', hint:'provider + model for Reel', kw:'video generation fal reel' },
  { tab:'appearance', label:'Scanline overlay', hint:'soft CRT shimmer', kw:'scanlines crt overlay' },
  { tab:'appearance', label:'Sound FX', hint:'pixel blips on action', kw:'sound audio blips mute' },
  { tab:'appearance', label:'Night mode', hint:'dark pixel theme', kw:'night dark theme day light' },
  { tab:'system', label:'Backend health', hint:'live gateway + container status', kw:'health status backend gateway api runtime' },
  { tab:'system', label:'Hermes provider status', hint:'active service + key state', kw:'provider configured status hermes' },
  { tab:'system', label:'Export agent setup', hint:'download your Hermes config (no keys)', kw:'export config backup portability hermes yaml' },
  { tab:'system', label:'Import agent setup', hint:'apply an exported or existing Hermes config', kw:'import config restore migrate hermes yaml' },
  { tab:'system', label:'Copy diagnostics', hint:'one-click support snapshot', kw:'diagnostics debug support copy' },
  { tab:'system', label:'Reset onboarding', hint:'replay the new-user guide', kw:'onboarding tour guide reset replay' },
];

/* ── ICP Services catalog ──────────────────────────────────────────────────
   One-click install of on-chain capabilities — like adding an MCP server, but
   for ICP. Installing flips a flag in cafresohq_state (via the shell bridge)
   and mirrors it to settings.icpServices so agent-tool gating is synchronous.
   Everything here needs the ai.cafreso.com shell (which holds Internet Identity);
   standalone (no bridge) shows a hint. */
const ICP_SERVICES = [
  {
    id: 'wallet', ico: '👛', name: 'Agent Wallet',
    blurb: "Give each agent its own on-chain HQ wallet (ICP, ckUSDT, ckUNI, sGLDT, $nanas) with a spend cap you set. Agents spend within the cap automatically; anything over asks you first.",
    tools: ['WALLET_BALANCE', 'WALLET_SEND'],
  },
  {
    id: 'publish', ico: '🚀', name: 'Publish to Canister',
    blurb: 'Publish an agent-built site to the Internet Computer and get back a verifiable *.icp0.io link your users can click.',
    tools: ['PUBLISH_SITE'],
  },
];

const WALLET_TOKEN_DECIMALS = { ICP: 8, ckUSDT: 6, ckUNI: 18, sGLDT: 8, nanas: 8 };
function toBaseUnits(whole, decimals) {
  const s = String(whole == null ? '' : whole).trim();
  if (!s || isNaN(Number(s))) return '0';
  const neg = s.startsWith('-'); const body = neg ? s.slice(1) : s;
  const [i, f = ''] = body.split('.');
  const frac = (f + '0'.repeat(decimals)).slice(0, decimals);
  const digits = ((i || '0') + frac).replace(/^0+(?=\d)/, '') || '0';
  return (neg ? '-' : '') + digits;
}
function fromBaseUnits(raw, decimals) {
  try {
    const n = BigInt(raw);
    const base = BigInt(10) ** BigInt(decimals);
    const int = n / base; const frac = n % base;
    const fracStr = frac.toString().padStart(decimals, '0').replace(/0+$/, '');
    return fracStr ? `${int}.${fracStr}` : `${int}`;
  } catch { return '0'; }
}

function AgentWalletCard({ agent }) {
  const [policy, setPolicy] = useStateM(null);
  const [bals, setBals] = useStateM(null);
  const [busy, setBusy] = useStateM('');
  const [msg, setMsg] = useStateM('');
  const [capTok, setCapTok] = useStateM('ICP');
  const [capAmt, setCapAmt] = useStateM('0.1');
  const [capHrs, setCapHrs] = useStateM('24');
  const [fundTok, setFundTok] = useStateM('ICP');
  const [fundAmt, setFundAmt] = useStateM('0.05');
  const chain = () => window.CafresoHQChain;
  const agentId = agent.id || agent.name;

  const load = async () => {
    try {
      const p = await chain().wallet.policy(agentId);
      setPolicy(p || null);
      if (p) {
        setCapTok(p.token);
        setCapAmt(fromBaseUnits(p.spendCap, WALLET_TOKEN_DECIMALS[p.token] ?? 8));
        setCapHrs(String(Math.round((p.windowSecs || 0) / 3600) || 24));
      }
    } catch (_e) { /* not deployed / not signed in — leave defaults */ }
  };
  useEffectM(() => { load(); }, []);

  const refreshBalances = async () => {
    setBusy('bal'); setMsg('');
    try { setBals(await chain().wallet.balances(agentId, Object.keys(WALLET_TOKEN_DECIMALS))); }
    catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const saveCap = async () => {
    setBusy('cap'); setMsg('');
    try {
      const dec = WALLET_TOKEN_DECIMALS[capTok] ?? 8;
      await chain().wallet.put({
        agentId, token: capTok, spendCap: toBaseUnits(capAmt, dec),
        windowSecs: Math.max(0, Math.round(parseFloat(capHrs || '0') * 3600)),
        paused: policy?.paused || false,
      });
      setMsg('Saved.'); await load();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const fund = async () => {
    setBusy('fund'); setMsg('');
    try {
      // Tell the tip watcher this credit is OURS before it can land on-chain —
      // a self-funded top-up must not rain coins as a "tip".
      try { window.dispatchEvent(new CustomEvent('cafresohq:walletLocalMove', { detail: { agentId } })); } catch (_e) {}
      const r = await chain().wallet.fund(agentId, fundTok, fundAmt);
      setMsg(r && r.ok != null ? `Funded (block ${r.ok}).` : (r && r.err ? `Fund failed: ${r.err}` : 'Fund sent.'));
      await refreshBalances();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const togglePause = async () => {
    setBusy('pause');
    try {
      const dec = WALLET_TOKEN_DECIMALS[policy?.token || capTok] ?? 8;
      await chain().wallet.put({
        agentId, token: policy?.token || capTok,
        spendCap: policy?.spendCap || toBaseUnits(capAmt, dec),
        windowSecs: policy?.windowSecs || Math.round(parseFloat(capHrs || '0') * 3600),
        paused: !(policy?.paused),
      });
      await load();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };

  const toks = Object.keys(WALLET_TOKEN_DECIMALS);
  return (
    <div className="cb-panel icp-wallet-card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="lbl">👛 {agent.name} <span className="tiny">· {agent.role}</span></span>
        {policy && (
          <button className={`px-btn ${policy.paused ? 'primary' : 'secondary'}`} style={{ fontSize: 8 }} disabled={busy === 'pause'} onClick={togglePause}>
            {policy.paused ? '▶ RESUME' : '⏸ PAUSE'}
          </button>
        )}
      </div>
      {!policy && <div className="sub" style={{ marginTop: 4 }}>No wallet yet — set a spend cap to create one.</div>}
      <div className="stack" style={{ marginTop: 6 }}>
        <div className="row-knob icp-in-row">
          <span className="lbl">Spend cap</span>
          <input className="icp-in" style={{ width: 66 }} value={capAmt} onChange={e => setCapAmt(e.target.value)} />
          <select value={capTok} onChange={e => setCapTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
          <span className="tiny">per</span>
          <input className="icp-in" style={{ width: 40 }} value={capHrs} onChange={e => setCapHrs(e.target.value)} />
          <span className="tiny">h</span>
          <button className="px-btn primary" style={{ fontSize: 8 }} disabled={busy === 'cap'} onClick={saveCap}>{policy ? 'SAVE' : 'CREATE'}</button>
        </div>
        <div className="row-knob icp-in-row">
          <span className="lbl">Fund</span>
          <input className="icp-in" style={{ width: 66 }} value={fundAmt} onChange={e => setFundAmt(e.target.value)} />
          <select value={fundTok} onChange={e => setFundTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
          <button className="px-btn" style={{ fontSize: 8 }} disabled={busy === 'fund'} onClick={fund}>⬆ FUND</button>
        </div>
        <div className="row-knob">
          <span className="lbl">Balances</span>
          <button className="px-btn secondary" style={{ fontSize: 8 }} disabled={busy === 'bal'} onClick={refreshBalances}>↻ REFRESH</button>
        </div>
        {bals && (
          <div className="tiny icp-bal-grid">
            {toks.map(t => <div key={t}>{t}: <b>{bals[t] == null ? '—' : fromBaseUnits(bals[t], WALLET_TOKEN_DECIMALS[t])}</b></div>)}
          </div>
        )}
        {msg && <div className="tiny" style={{ color: 'var(--accent-leaf)' }}>{msg}</div>}
      </div>
    </div>
  );
}

function IcpServicesPanel({ agents }) {
  const [installed, setInstalled] = useStateM({});
  const [available, setAvailable] = useStateM(true);
  const [pausedAll, setPausedAll] = useStateM(false);
  const [loading, setLoading] = useStateM(true);
  const [err, setErr] = useStateM('');
  const chain = () => window.CafresoHQChain;

  const load = async () => {
    setLoading(true); setErr('');
    const avail = !!(chain() && chain().isAvailable());
    setAvailable(avail);
    if (!avail) { setLoading(false); return; }
    try {
      const flags = await chain().services.list();
      const map = {}; (flags || []).forEach(f => { map[f.serviceId] = !!f.enabled; });
      setInstalled(map);
      window.CafresoHQClient.setSettings({ icpServices: map });
      setPausedAll(await chain().wallet.pausedAll());
    } catch (e) { setErr(String(e.message || e)); }
    setLoading(false);
  };
  useEffectM(() => { load(); }, []);

  const toggleInstall = async (svc) => {
    const next = !installed[svc.id];
    try {
      await chain().services.set(svc.id, next, '');
      const map = { ...installed, [svc.id]: next };
      setInstalled(map);
      window.CafresoHQClient.setSettings({ icpServices: map });
    } catch (e) { setErr(String(e.message || e)); }
  };
  const togglePauseAll = async () => {
    try { const n = !pausedAll; await chain().wallet.pauseAll(n); setPausedAll(n); }
    catch (e) { setErr(String(e.message || e)); }
  };

  if (!available) {
    return (
      <div className="control-board"><div className="cb-panel">
        <h4>ICP SERVICES</h4>
        <div className="muted" style={{ lineHeight: 1.6 }}>
          ICP Services need your Internet Identity, which lives in the CafresoHQ shell.
          Open your HQ at <b>ai.cafreso.com</b> (not the standalone container) to install
          wallets, publish sites, and manage on-chain features.
        </div>
      </div></div>
    );
  }

  const walletOn = !!installed.wallet;
  const walletAgents = (agents || []).filter(a => (a.tools || []).includes('wallet'));

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>ICP SERVICES · CATALOG</h4>
        {err && <div className="tiny" style={{ color: '#c44' }}>{err}</div>}
        {loading && <div className="muted">Loading…</div>}
        <div className="stack">
          {ICP_SERVICES.map(svc => (
            <div key={svc.id} className="row-knob" style={{ alignItems: 'flex-start' }}>
              <div style={{ maxWidth: 300 }}>
                <div className="lbl">{svc.ico} {svc.name}</div>
                <div className="sub" style={{ marginTop: 2 }}>{svc.blurb}</div>
                <div className="tiny" style={{ marginTop: 2, opacity: .7 }}>Agent tools: {svc.tools.join(', ')}</div>
              </div>
              <button className={`px-btn ${installed[svc.id] ? 'danger' : 'primary'}`} style={{ fontSize: 8, whiteSpace: 'nowrap' }} onClick={() => toggleInstall(svc)}>
                {installed[svc.id] ? '✓ REMOVE' : '＋ INSTALL'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {walletOn && (
        <div className="cb-panel">
          <h4>AGENT WALLETS</h4>
          <div className="row-knob">
            <div><div className="lbl">Pause all agent spending</div><div className="sub">Global kill switch — blocks every agent send</div></div>
            <div className={`pxswitch ${pausedAll ? 'on' : ''}`} onClick={togglePauseAll}><div className="nub" /></div>
          </div>
          {walletAgents.length === 0
            ? <div className="muted" style={{ marginTop: 6 }}>Grant an agent the <b>ICP Wallet</b> tool in <b>Roster</b> to give it a wallet.</div>
            : walletAgents.map(a => <AgentWalletCard key={a.id} agent={a} />)}
        </div>
      )}
    </div>
  );
}

function SettingsModal({ open, onClose, agents, onDismiss, onUpdateAgent, scanlines, setScanlines, sound, setSound, night, setNight, initialTab }) {
  // Last-used tab survives reopen (and reload) — small thing, big QoL.
  const [tab, _setTab] = useStateM(() => {
    try {
      const t = localStorage.getItem('hq:settingsTab');
      if (t && SETTINGS_TABS.some(x => x.id === t)) return t;
    } catch (_e) {}
    return SETTINGS_TABS[0].id;
  });
  const setTab = (t) => {
    const id = SETTINGS_TAB_ALIAS[t] || t;
    _setTab(id);
    try { localStorage.setItem('hq:settingsTab', id); } catch (_e) {}
  };
  const [q, setQ] = useStateM('');
  const [selected, setSelected] = useStateM(agents[0]?.id || null);
  const sel = agents.find(a => a.id === selected) || agents[0];

  // Live status for the nav rail: provider key state, CLI install count,
  // backend reachability. Refetched each time the modal opens.
  const [navStat, setNavStat] = useStateM({});
  useEffectM(() => {
    if (!open) return;
    let live = true;
    const C = window.CafresoHQClient;
    (async () => {
      const stat = {};
      try { stat.backend = !!(await C.backendHealth()); } catch (_e) { stat.backend = false; }
      try {
        if (C.hermesGetProvider) {
          const p = await C.hermesGetProvider();
          stat.provider = !!(p && p.configured);
        }
      } catch (_e) {}
      try {
        if (C.agentsStatus) {
          const a = await C.agentsStatus();
          const list = (a && a.agents) || [];
          if (list.length) stat.clis = `${list.filter(x => x.installed).length}/${list.length}`;
        }
      } catch (_e) {}
      if (live) setNavStat(stat);
    })();
    return () => { live = false; };
  }, [open]);

  // Deep-link: jump to a requested tab each time the modal is (re)opened
  // (e.g. the "no API key" chip opens straight to CONNECTIONS).
  const prevOpenRef = useRefM(false);
  useEffectM(() => {
    if (open && !prevOpenRef.current && initialTab) setTab(initialTab);
    prevOpenRef.current = open;
  }, [open, initialTab]);

  if (!open) return null;

  const update = (patch) => {
    if (!sel) return;
    onUpdateAgent(sel.id, patch);
  };

  // All query terms must match label+hint+kw (case-insensitive).
  const terms = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const hits = terms.length
    ? SETTINGS_INDEX.filter(e => {
        const hay = (e.label + ' ' + e.hint + ' ' + e.kw).toLowerCase();
        return terms.every(t => hay.includes(t));
      })
    : [];

  const navDot = (t) => {
    if (t.id === 'keys' && navStat.provider !== undefined)
      return <span className={`sn-dot ${navStat.provider ? 'ok' : 'warn'}`} title={navStat.provider ? 'provider key set' : 'no provider key'}/>;
    if (t.id === 'system' && navStat.backend !== undefined)
      return <span className={`sn-dot ${navStat.backend ? 'ok' : 'err'}`} title={navStat.backend ? 'backend reachable' : 'backend unreachable'}/>;
    if (t.id === 'agentcli' && navStat.clis)
      return <span className="sn-badge" title="installed CLIs">{navStat.clis}</span>;
    return null;
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="SETTINGS · CONTROL BOARD"
      subtitle="pull the drawers · flip the switches"
      size="xl"
      footer={
        <>
          <div className="hint" style={{marginRight: 'auto'}}>Changes save automatically.</div>
          <button className="px-btn primary" onClick={onClose}>DONE</button>
        </>
      }
    >
      <div className="settings-shell">
        <aside className="settings-nav">
          <input className="settings-search" type="search" placeholder="🔍 search settings…"
            value={q} onChange={e => setQ(e.target.value)} aria-label="Search settings"/>
          {SETTINGS_TABS.map(t => (
            <button key={t.id} className={`sn-item ${tab===t.id && !terms.length ? 'active' : ''}`}
              onClick={() => { setQ(''); setTab(t.id); }}>
              <span className="sn-ico">{t.ico}</span>
              <span className="sn-txt">
                <span className="sn-label">{t.label}</span>
                <span className="sn-desc">{t.desc}</span>
              </span>
              {navDot(t)}
            </button>
          ))}
        </aside>
        <div className="settings-body">
          {terms.length > 0 && (
            <div className="cb-panel">
              <h4>SEARCH · {hits.length} RESULT{hits.length === 1 ? '' : 'S'}</h4>
              {hits.length === 0 && <div className="muted">Nothing matches “{q}”.</div>}
              {hits.map((e, i) => {
                const t = SETTINGS_TABS.find(x => x.id === e.tab);
                return (
                  <div key={i} className="row-knob" style={{cursor:'pointer'}}
                    onClick={() => { setQ(''); setTab(e.tab); }}>
                    <div>
                      <div className="lbl">{t ? t.ico : ''} {e.label}</div>
                      <div className="sub">{e.hint}</div>
                    </div>
                    <span className="tiny" style={{whiteSpace:'nowrap'}}>{t ? t.label : e.tab} →</span>
                  </div>
                );
              })}
            </div>
          )}

          {!terms.length && tab === 'icp-services' && (
            <IcpServicesPanel agents={agents} />
          )}

          {!terms.length && tab === 'agents' && (
            <div className="control-board">
              <div className="cb-panel">
                <h4>ROSTER</h4>
                <div className="stack">
                  {agents.length === 0 && <div className="muted">No sub-agents hired.</div>}
                  {agents.map(a => (
                    <div key={a.id} className={`row`} style={{
                      padding: '6px 8px',
                      background: selected===a.id ? 'var(--accent-sun)' : 'transparent',
                      border: '2px solid ' + (selected===a.id?'var(--ink)':'transparent'),
                      cursor: 'pointer',
                    }} onClick={()=>setSelected(a.id)}>
                      <Sprite data={a.color} scale={1.5}/>
                      <div className="grow" style={{display:'flex',flexDirection:'column',lineHeight:1.1}}>
                        <span style={{fontFamily:'Press Start 2P',fontSize:9}}>{a.name}</span>
                        <span className="tiny">{a.role}</span>
                      </div>
                      <button className="px-btn danger" style={{fontSize:8,padding:'6px 8px'}} onClick={(e)=>{e.stopPropagation(); onDismiss(a.id);}}>LET GO</button>
                    </div>
                  ))}
                </div>
              </div>
              <div className="cb-panel">
                <h4>{sel ? `${sel.name.toUpperCase()} · CONFIG` : 'NO AGENT'}</h4>
                {sel && (
                  <div className="stack">
                    <div className="row-knob">
                      <span className="lbl">Model</span>
                      <ModelPicker value={sel.model} onChange={v=>update({model:v})}/>
                    </div>
                    <div className="row-knob" style={{flexDirection:'column',alignItems:'stretch',gap:4}}>
                      <div className="row" style={{justifyContent:'space-between'}}><span className="lbl">Temperature</span><span className="sub">{sel.temperature?.toFixed(2)}</span></div>
                      <input type="range" className="pxslider" min="0" max="1" step="0.05" value={sel.temperature||0} onChange={e=>update({temperature:parseFloat(e.target.value)})}/>
                    </div>
                    <div style={{marginTop:6}}>
                      <div className="sub" style={{marginBottom:6}}>TOOLS</div>
                      <div className="tool-grid">
                        {HQ.TOOLS_CATALOG.map(t => (
                          <div key={t.id} className={`tool-chk ${sel.tools.includes(t.id)?'on':''}`}
                               onClick={()=>update({tools: sel.tools.includes(t.id)?sel.tools.filter(x=>x!==t.id):[...sel.tools,t.id]})}>
                            <div className="box"/><span>{t.label}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="row-knob" style={{marginTop:6}}>
                      <div>
                        <div className="lbl">Tool call format</div>
                        <div className="sub">JSON = reliable for capable models; bracket = fallback for local OSS</div>
                      </div>
                      <select value={sel.toolFormat || 'auto'} onChange={e => update({ toolFormat: e.target.value })}>
                        <option value="auto">Auto-detect</option>
                        <option value="json">JSON ({"<<<TOOL>>>"})</option>
                        <option value="bracket">Bracket [TOOL: arg]</option>
                      </select>
                    </div>
                    <div className={`row-knob elevated-opt ${sel.elevated ? 'on' : ''}`} style={{marginTop:8,alignItems:'flex-start'}}>
                      <div>
                        <div className="lbl" style={{color: sel.elevated ? '#c44' : 'inherit'}}>🛡 Elevated · computer access</div>
                        <div className="sub" style={{maxWidth:240,marginTop:2}}>
                          Elevated session with file/shell access. DMs blocked, missions opt-in, actions logged.
                        </div>
                      </div>
                      <div className={`pxswitch ${sel.elevated?'on':''}`} onClick={()=>{
                        if (!sel.elevated) {
                          if (!window.confirm(
                            `Grant ${sel.name} COMPUTER ACCESS?\n\n` +
                            `They will be backed by an elevated CafresoHQ session that can read/write files and run shell commands on this machine. ` +
                            `DMs from other agents will be blocked, missions require explicit authorization, and every tool call is logged.\n\n` +
                            `Continue?`
                          )) return;
                        }
                        update({ elevated: !sel.elevated });
                      }}><div className="nub"/></div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {!terms.length && tab === 'appearance' && (
            <div className="control-board">
              <div className="cb-panel">
                <h4>AMBIENCE</h4>
                <div className="row-knob">
                  <div><div className="lbl">Scanline overlay</div><div className="sub">soft CRT shimmer</div></div>
                  <div className={`pxswitch ${scanlines?'on':''}`} onClick={()=>setScanlines(!scanlines)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">Sound FX</div><div className="sub">pixel blips on action</div></div>
                  <div className={`pxswitch ${sound?'on':''}`} onClick={()=>setSound(!sound)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">{night ? '☀ Day Mode' : '☾ Night Mode'}</div><div className="sub">{night ? 'switch to warm pastels' : 'switch to dark pixel theme'}</div></div>
                  <div className={`pxswitch ${night?'on':''}`} onClick={()=>setNight(v=>!v)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">Keyboard shortcuts</div><div className="sub">1–8 switch views · S settings · D theme · Ctrl+K palette</div></div>
                  <span className="tiny">press Ctrl+K</span>
                </div>
              </div>
            </div>
          )}

          {!terms.length && tab === 'agentcli' && <AgentClisTab />}
          {!terms.length && tab === 'media' && <MediaTab />}
          {!terms.length && tab === 'keys' && <ApiTab />}
          {!terms.length && tab === 'system' && <SystemTab />}
        </div>
      </div>
    </Modal>
  );
}

/* System tab — live backend/runtime visibility so "is it the key, the
   container, or the gateway?" is answerable from inside the app instead of
   the browser devtools. Read-only except the two action buttons. */
function SystemTab() {
  const [health, setHealth] = useStateM(null);   // null=loading · false=down · object=ok
  const [prov, setProv] = useStateM(null);
  const [busy, setBusy] = useStateM(false);
  const [note, setNote] = useStateM('');
  const apiBase = (window._API_BASE || '');

  const load = async () => {
    setBusy(true);
    try {
      const r = await fetch(apiBase + '/health');
      setHealth(r.ok ? await r.json() : false);
    } catch (_e) { setHealth(false); }
    try {
      const C = window.CafresoHQClient;
      if (C.hermesGetProvider) setProv(await C.hermesGetProvider());
    } catch (_e) { setProv(null); }
    setBusy(false);
  };
  useEffectM(() => { load(); }, []);

  const copyDiag = async () => {
    const diag = {
      when: new Date().toISOString(),
      apiBase: apiBase || '(same origin)',
      health: health || 'unreachable',
      provider: prov || 'unknown',
      ua: navigator.userAgent,
      url: location.href.split('?')[0],
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(diag, null, 2));
      setNote('✓ diagnostics copied — paste into a support chat');
    } catch (_e) { setNote('copy failed — clipboard blocked'); }
  };

  // Agent-config portability (Hermes setup travels; keys never do).
  const importInputRef = useRefM(null);
  const [importBusy, setImportBusy] = useStateM(false);
  const exportConfig = async () => {
    try {
      const C = window.CafresoHQClient;
      const data = await C.hermesExportConfig();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'cafresohq-hermes-config.json';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      setNote('✓ config exported (keys not included)');
    } catch (e) { setNote('export failed: ' + e.message); }
  };
  const importConfig = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    setImportBusy(true); setNote('');
    try {
      const text = await file.text();
      const C = window.CafresoHQClient;
      const r = await C.hermesImportConfig(text);
      setNote(r.restarted
        ? '✓ config imported — agent reloading (~10s). Re-enter your key in Connections if needed.'
        : '✓ config written (gateway restart pending)');
      load();
    } catch (er) { setNote('import failed: ' + er.message); }
    setImportBusy(false);
  };

  const resetOnboarding = () => {
    if (!window.confirm('Replay the new-user guide on next reload?')) return;
    try {
      const kill = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && /tourseen|gettingstarted|gsdismissed/i.test(k)) kill.push(k);
      }
      kill.forEach(k => localStorage.removeItem(k));
      setNote(`✓ onboarding reset (${kill.length} flag${kill.length === 1 ? '' : 's'} cleared) — reload to replay`);
    } catch (_e) { setNote('reset failed'); }
  };

  const dot = (on) => (
    <span className={`sn-dot ${on ? 'ok' : 'err'}`} style={{position:'static', marginRight:6}}/>
  );
  const yn = (v) => v ? 'yes' : 'no';

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>BACKEND</h4>
        <div className="row-knob">
          <div><div className="lbl">API base</div><div className="sub">where this UI sends requests</div></div>
          <span className="tiny" style={{maxWidth:220, textAlign:'right', wordBreak:'break-all'}}>{apiBase || '(same origin)'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Status</div><div className="sub">{health === null ? 'checking…' : health ? 'serving' : 'unreachable'}</div></div>
          <span>{health === null ? '…' : dot(!!health)}</span>
        </div>
        {health && (
          <>
            <div className="row-knob">
              <div><div className="lbl">Runtime</div><div className="sub">container environment</div></div>
              <span className="tiny">{health.runtime_env || 'unknown'}{health.auth_required ? ' · key-gated' : ''}</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">Hermes gateway</div><div className="sub">in-container agent runtime</div></div>
              <span className="tiny">{dot(!!health.hermes)}{yn(!!health.hermes)}</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">Gemini CLI</div><div className="sub">installed in container</div></div>
              <span className="tiny">{dot(!!health.gemini)}{yn(!!health.gemini)}</span>
            </div>
          </>
        )}
        <div className="row-knob">
          <div><div className="lbl">Re-check</div><div className="sub">probe /health again</div></div>
          <button className="px-btn secondary" disabled={busy} onClick={load}>{busy ? '…' : 'REFRESH'}</button>
        </div>
      </div>
      <div className="cb-panel">
        <h4>HERMES PROVIDER</h4>
        <div className="row-knob">
          <div><div className="lbl">Service</div><div className="sub">active backend behind Hermes</div></div>
          <span className="tiny">{prov ? prov.provider : '…'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Model</div><div className="sub">current default</div></div>
          <span className="tiny" style={{maxWidth:200, textAlign:'right', wordBreak:'break-all'}}>{prov ? (prov.model || 'unknown') : '…'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Key configured</div><div className="sub">set one in Connections if not</div></div>
          <span className="tiny">{prov === null ? '…' : <>{dot(!!(prov && prov.configured))}{yn(!!(prov && prov.configured))}</>}</span>
        </div>
      </div>
      <div className="cb-panel">
        <h4>AGENT CONFIG</h4>
        <div className="row-knob">
          <div><div className="lbl">Export setup</div><div className="sub">download your Hermes agent config (keys NOT included)</div></div>
          <button className="px-btn secondary" onClick={exportConfig}>EXPORT</button>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Import setup</div><div className="sub">apply an exported file or a raw ~/.hermes/config.yaml</div></div>
          <button className="px-btn secondary" disabled={importBusy}
            onClick={() => importInputRef.current && importInputRef.current.click()}>
            {importBusy ? '…' : 'IMPORT'}
          </button>
          <input ref={importInputRef} type="file" accept=".json,.yaml,.yml,.txt" style={{display:'none'}}
            onChange={importConfig}/>
        </div>
        <div className="hint">Moving between HQs (or from a local Hermes install)? Export here, import there — then re-enter your key in Connections.</div>
      </div>
      <div className="cb-panel">
        <h4>SUPPORT</h4>
        <div className="row-knob">
          <div><div className="lbl">Copy diagnostics</div><div className="sub">health + provider snapshot, no keys included</div></div>
          <button className="px-btn secondary" onClick={copyDiag}>COPY</button>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Reset onboarding</div><div className="sub">replay the new-user tour & checklist</div></div>
          <button className="px-btn secondary" onClick={resetOnboarding}>RESET</button>
        </div>
        {note && <div className="hint" style={{marginTop:6}}>{note}</div>}
      </div>
    </div>
  );
}

/* Media tab — user-configured image / video generation provider + model.
   Read by claude-client.jsx _mediaConfig() and forwarded to serve.py's
   /generate/image and /generate/video endpoints. API keys come from the
   per-provider on-device key vault (Connections tab). */
function MediaTab() {
  const [s, update] = useSettingsStore();
  const imgProvider = s.imageProvider || '';
  const imgModel = s.imageModel || '';
  const vidProvider = s.videoProvider || '';
  const vidModel = s.videoModel || '';
  const a1111Url = s.a1111Url || 'http://127.0.0.1:7860';
  const comfyUrl = s.comfyUrl || 'http://127.0.0.1:8188';
  const imageDefaults = {
    openai:  'gpt-image-1',
    // Default to Gemini Flash Image ("nano banana") — cheaper and faster than
    // Imagen, uses the same GOOGLE_API_KEY the user already has for chat.
    google:  'gemini-2.5-flash-image-preview',
    fal:     'fal-ai/flux/schnell',
    a1111:   '',  // A1111 uses whatever ckpt is loaded; empty = no override
    comfyui: 'sd_xl_base_1.0.safetensors',
  };
  const videoDefaults = {
    fal:     'fal-ai/bytedance/seedance/v1/lite/text-to-video',
    comfyui: '',
  };
  // When switching providers always reset the model to the new provider's
  // default — otherwise you'd carry e.g. "dall-e-3" into Google and it'd fail.
  // Users can still customise the model after the switch.
  const setImgProvider = (p) => update({ imageProvider: p, imageModel: imageDefaults[p] || '' });
  const setVidProvider = (p) => update({ videoProvider: p, videoModel: videoDefaults[p] || '' });
  const isLocalImg = imgProvider === 'a1111' || imgProvider === 'comfyui';
  const isLocalVid = vidProvider === 'comfyui';
  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>🖼 IMAGE GENERATION</h4>
        <div className="row-knob">
          <div>
            <div className="lbl">Provider</div>
            <div className="sub">where Pixel sends image prompts</div>
          </div>
          <select value={imgProvider} onChange={e => setImgProvider(e.target.value)}>
            <option value="">— disabled —</option>
            <optgroup label="Cloud">
              <option value="openai">OpenAI (DALL·E / gpt-image-1)</option>
              <option value="google">Google (Gemini Flash Image / Imagen)</option>
              <option value="fal">fal.ai (Flux / SDXL / many)</option>
            </optgroup>
            <optgroup label="Local">
              <option value="a1111">Automatic1111 WebUI</option>
              <option value="comfyui">ComfyUI</option>
            </optgroup>
          </select>
        </div>
        {imgProvider && (
          <>
            <div className="row-knob" style={{flexDirection:'column', alignItems:'stretch', gap:6}}>
              <div className="row" style={{justifyContent:'space-between'}}>
                <div>
                  <div className="lbl">{imgProvider === 'a1111' ? 'Checkpoint (optional)' : 'Model ID'}</div>
                  <div className="sub">
                    {imgProvider === 'openai' && 'e.g. gpt-image-1, dall-e-3, dall-e-2'}
                    {imgProvider === 'google' && 'gemini-2.5-flash-image-preview ("nano banana", recommended) · or imagen-3.0-generate-002 / imagen-4.0-generate-001'}
                    {imgProvider === 'fal' && 'e.g. fal-ai/flux/schnell, fal-ai/flux-pro, fal-ai/recraft-v3'}
                    {imgProvider === 'a1111' && 'leave blank to use whatever is loaded; or e.g. sd_xl_base_1.0.safetensors'}
                    {imgProvider === 'comfyui' && 'checkpoint filename, e.g. sd_xl_base_1.0.safetensors'}
                  </div>
                </div>
                <button className="px-btn ghost" style={{fontSize:8}} onClick={()=>update({imageModel: imageDefaults[imgProvider] || ''})}>
                  RESET
                </button>
              </div>
              <input
                type="text"
                placeholder={imageDefaults[imgProvider] || 'model id (optional)'}
                value={imgModel}
                onChange={e => update({ imageModel: e.target.value })}
                style={{width:'100%',boxSizing:'border-box',fontFamily:'JetBrains Mono, monospace',fontSize:11}}
              />
            </div>
            {isLocalImg && (
              <div className="row-knob" style={{flexDirection:'column', alignItems:'stretch', gap:6}}>
                <div>
                  <div className="lbl">{imgProvider === 'a1111' ? 'Automatic1111 URL' : 'ComfyUI URL'}</div>
                  <div className="sub">
                    {imgProvider === 'a1111' && 'launch A1111 with --api flag · default :7860'}
                    {imgProvider === 'comfyui' && 'default :8188 — ComfyUI exposes its API by default'}
                  </div>
                </div>
                <input
                  type="text"
                  placeholder={imgProvider === 'a1111' ? 'http://127.0.0.1:7860' : 'http://127.0.0.1:8188'}
                  value={imgProvider === 'a1111' ? a1111Url : comfyUrl}
                  onChange={e => update(imgProvider === 'a1111' ? { a1111Url: e.target.value } : { comfyUrl: e.target.value })}
                  style={{width:'100%',boxSizing:'border-box',fontFamily:'JetBrains Mono, monospace',fontSize:11}}
                />
              </div>
            )}
            <div className="hint" style={{marginTop:6, fontSize:10}}>
              {imgProvider === 'openai' && <>API key from <strong>Connections</strong> → OPENAI_API_KEY. Server env vars override.</>}
              {imgProvider === 'google' && <>API key from <strong>Connections</strong> → GOOGLE_API_KEY. Server env vars override.</>}
              {imgProvider === 'fal' && <>API key from <strong>Connections</strong> → FAL_KEY (add via the agent-key vault). Server env vars override.</>}
              {imgProvider === 'a1111' && <>Local — no API key needed. Make sure A1111 is running with <code>--api</code>.</>}
              {imgProvider === 'comfyui' && <>Local — no API key needed. ComfyUI exposes its API automatically.</>}
            </div>
          </>
        )}
      </div>

      <div className="cb-panel">
        <h4>🎬 VIDEO GENERATION</h4>
        <div className="row-knob">
          <div>
            <div className="lbl">Provider</div>
            <div className="sub">where Reel sends video prompts</div>
          </div>
          <select value={vidProvider} onChange={e => setVidProvider(e.target.value)}>
            <option value="">— disabled —</option>
            <optgroup label="Cloud">
              <option value="fal">fal.ai (Seedance / Veo / Kling)</option>
              <option value="openai">OpenAI Sora (gated)</option>
              <option value="google">Google Veo (direct API not wired)</option>
            </optgroup>
            <optgroup label="Local">
              <option value="comfyui">ComfyUI (AnimateDiff / SVD / Mochi / Hunyuan)</option>
            </optgroup>
          </select>
        </div>
        {vidProvider && (
          <>
            {vidProvider !== 'comfyui' && (
              <div className="row-knob" style={{flexDirection:'column', alignItems:'stretch', gap:6}}>
                <div className="row" style={{justifyContent:'space-between'}}>
                  <div>
                    <div className="lbl">Model ID</div>
                    <div className="sub">
                      {vidProvider === 'fal' && 'e.g. fal-ai/bytedance/seedance/v1/lite/text-to-video, fal-ai/veo3, fal-ai/kling-video/v2/master/text-to-video'}
                      {vidProvider === 'openai' && 'e.g. sora-1 (when available on your account)'}
                      {vidProvider === 'google' && 'e.g. veo-3'}
                    </div>
                  </div>
                  <button className="px-btn ghost" style={{fontSize:8}} onClick={()=>update({videoModel: videoDefaults[vidProvider] || ''})}>
                    RESET
                  </button>
                </div>
                <input
                  type="text"
                  placeholder={videoDefaults[vidProvider] || 'model id'}
                  value={vidModel}
                  onChange={e => update({ videoModel: e.target.value })}
                  style={{width:'100%',boxSizing:'border-box',fontFamily:'JetBrains Mono, monospace',fontSize:11}}
                />
              </div>
            )}
            {isLocalVid && (
              <div className="row-knob" style={{flexDirection:'column', alignItems:'stretch', gap:6}}>
                <div>
                  <div className="lbl">ComfyUI URL</div>
                  <div className="sub">default :8188 — load an AnimateDiff/SVD/Mochi/Hunyuan workflow inside Comfy</div>
                </div>
                <input
                  type="text"
                  placeholder="http://127.0.0.1:8188"
                  value={comfyUrl}
                  onChange={e => update({ comfyUrl: e.target.value })}
                  style={{width:'100%',boxSizing:'border-box',fontFamily:'JetBrains Mono, monospace',fontSize:11}}
                />
              </div>
            )}
            <div className="hint" style={{marginTop:6, fontSize:10}}>
              {vidProvider === 'fal' && 'API key from Connections → FAL_KEY. Most fal models cost $0.01-$0.50 per video.'}
              {vidProvider === 'openai' && 'Sora API is currently gated — most accounts will get 403. Use fal.ai for production.'}
              {vidProvider === 'google' && 'Direct Veo API not yet wired in the backend. Use fal.ai/veo3 instead.'}
              {vidProvider === 'comfyui' && (
                <>Local. <strong>Reel must pass a workflow JSON</strong> in the GENERATE_VIDEO body — export it from ComfyUI's "Save (API Format)" after building a working AnimateDiff/SVD/Mochi/Hunyuan graph. No auto-default because video workflows are model-specific.</>
              )}
            </div>
          </>
        )}
      </div>

      <div className="cb-panel" style={{gridColumn:'1 / -1'}}>
        <h4>ℹ HOW IT WORKS</h4>
        <div className="hint" style={{fontSize:11, lineHeight:1.5}}>
          When configured, the <strong>Pixel</strong> and <strong>Reel</strong> agents on your roster can emit{' '}
          <code>[GENERATE_IMAGE: path]</code> / <code>[GENERATE_VIDEO: path]</code> markers.
          The server calls your chosen provider and saves the binary result into the vault at the requested path.
          <br/><br/>
          <strong>Cloud</strong> providers are pay-as-you-go (cents per image, ~$0.01–$0.50 per video).{' '}
          <strong>Local</strong> providers (Automatic1111, ComfyUI) are free but require you to be running the tool yourself with a model loaded on your GPU.
          {!imgProvider && !vidProvider && (
            <> <strong>Both providers are disabled</strong> — Pixel and Reel will tell you to configure one here.</>
          )}
        </div>
      </div>
    </div>
  );
}

/* Agents tab — the in-container CLI agent fleet (distinct from the per-agent
   sub-agent roster). The HQ ships with Hermes (default, always installed);
   Claude Code and Codex install on demand via the backend's `npm i -g`, which
   runs synchronously and can take 30-60 s. Backed by GET /agents and
   POST /agents/install (claude-client: agentsStatus / agentsInstall). */
function AgentClisTab() {
  const C = window.CafresoHQClient;
  const [agents, setAgents] = useStateM(null);   // null = loading
  const [loadErr, setLoadErr] = useStateM(null);
  const [busyId, setBusyId] = useStateM(null);    // agent id currently installing
  const [rowErr, setRowErr] = useStateM({});      // { [id]: errorString }

  const AGENT_ICON = { hermes: '☼', 'claude-code': '✦', codex: '◈', gemini: '✧' };

  const load = async () => {
    setLoadErr(null);
    try {
      const r = await C.agentsStatus();
      setAgents(r.agents || []);
    } catch (e) {
      setAgents([]);
      setLoadErr(e.message || String(e));
    }
  };

  useEffectM(() => { load(); }, []);

  const install = async (id) => {
    if (busyId) return;
    setBusyId(id);
    setRowErr(prev => { const n = { ...prev }; delete n[id]; return n; });
    try {
      const d = await C.agentsInstall(id);
      // Optimistically mark this row installed with the returned version, then
      // refresh from the backend so installed/removable/etc. stay authoritative.
      setAgents(prev => (prev || []).map(a =>
        a.id === id ? { ...a, installed: true, version: d.version || a.version } : a));
      load();
    } catch (e) {
      setRowErr(prev => ({ ...prev, [id]: e.message || String(e) }));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="control-board">
      <div className="cb-panel" style={{ gridColumn: '1 / -1' }}>
        <h4>🤖 AGENTS</h4>
        <div className="sub" style={{ marginBottom: 12, lineHeight: 1.5 }}>
          Your HQ ships with <strong>Hermes</strong>. Add Claude Code, Codex, or Gemini when you need them.
        </div>

        {agents === null && (
          <div className="muted" style={{ padding: '8px 2px' }}>Loading agents…</div>
        )}

        {loadErr && (
          <div className="row-knob" style={{ alignItems: 'center' }}>
            <div><div className="lbl" style={{ color: 'var(--error)' }}>⚠ Couldn't load agents</div>
              <div className="sub">{loadErr}</div></div>
            <button className="px-btn secondary" style={{ fontSize: 9 }} onClick={load}>RETRY</button>
          </div>
        )}

        {agents && agents.length > 0 && (
          <div className="stack">
            {agents.map(a => {
              const installing = busyId === a.id;
              const err = rowErr[a.id];
              return (
                <div key={a.id} className="row-knob" style={{ alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', gap: 10, minWidth: 0 }}>
                    <span style={{ fontSize: 18, color: '#7c6bff', lineHeight: 1.2 }}>
                      {AGENT_ICON[a.id] || '◆'}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div className="lbl" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        {a.label || a.id}
                        {a.default && (
                          <span style={{
                            fontSize: 8, fontWeight: 700, letterSpacing: '0.04em',
                            color: '#7c6bff', background: 'rgba(124,107,255,0.16)',
                            borderRadius: 4, padding: '2px 6px',
                          }}>DEFAULT</span>
                        )}
                      </div>
                      <div className="sub" style={{ maxWidth: 320 }}>{a.desc || ''}</div>
                      {err && (
                        <div className="sub" style={{ color: 'var(--error)', marginTop: 4 }}>⚠ {err}</div>
                      )}
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                    {a.installed ? (
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                        <span style={{
                          fontSize: 9, fontWeight: 700, letterSpacing: '0.03em',
                          color: 'var(--live)', background: 'rgba(111,168,111,0.14)',
                          border: '1px solid var(--live)', borderRadius: 5,
                          padding: '4px 9px', whiteSpace: 'nowrap',
                        }}>
                          {a.default ? 'Default · Installed' : `Installed${a.version ? ' · ' + a.version : ''}`}
                        </span>
                        {/* Login state — /agents reports best-effort credential
                           detection. hermes additionally reports gateway liveness. */}
                        {a.id === 'hermes' ? (
                          <span className="tiny" style={{
                            color: a.running ? 'var(--live)' : 'var(--ink-3)', whiteSpace: 'nowrap',
                          }}>
                            {a.running ? '● gateway running' : '○ gateway not running'}
                          </span>
                        ) : a.authenticated ? (
                          <span className="tiny" style={{ color: 'var(--live)', whiteSpace: 'nowrap' }}>
                            ✓ logged in{a.auth === 'api-key' ? ' (API key)' : ''}
                          </span>
                        ) : (
                          <span className="tiny" style={{ color: 'var(--ink-3)', whiteSpace: 'nowrap' }}
                            title="No saved login found — open a Terminal tab and run the CLI once to sign in.">
                            needs login · use Terminal
                          </span>
                        )}
                      </div>
                    ) : installing ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <button className="px-btn primary is-loading" disabled style={{ fontSize: 9, minWidth: 76 }}>
                          INSTALLING
                        </button>
                        <span className="tiny" style={{ maxWidth: 150, lineHeight: 1.3 }}>
                          Installing… this can take up to a minute.
                        </span>
                      </div>
                    ) : (
                      <button className="px-btn primary" style={{ fontSize: 9 }}
                        disabled={!!busyId} onClick={() => install(a.id)}>
                        {err ? 'RETRY' : 'INSTALL'}
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {agents && agents.length === 0 && !loadErr && (
          <div className="muted" style={{ padding: '8px 2px' }}>No agents reported.</div>
        )}
      </div>
    </div>
  );
}

// Hermes backend services the user can pick (the free LLM behind Hermes). Each
// row adapts the key field's label / placeholder / "get a free key" link. Gemini
// direct is the most reliable free tier (≈15 RPM / 1500 per day) — the fix for
// OpenRouter :free's 20 RPM / 50-per-day throttling. Mirrors serve.py
// _HERMES_PROVIDERS + claude-client HERMES_PROVIDER_KEY_FIELD.
const HBACKENDS = {
  openrouter: { label: 'OpenRouter', field: 'openrouterKey', ph: 'sk-or-v1-…',
                link: 'https://openrouter.ai/keys', linkText: 'openrouter.ai/keys',
                note: 'free open-weights · no per-request size cap' },
  gemini:     { label: 'Google Gemini', field: 'geminiKey', ph: 'AIza…',
                link: 'https://aistudio.google.com/apikey', linkText: 'aistudio.google.com/apikey',
                note: 'most reliable free tier · ~15/min · 1500/day (Flash)' },
  groq:       { label: 'Groq', field: 'groqKey', ph: 'gsk_…',
                link: 'https://console.groq.com/keys', linkText: 'console.groq.com/keys',
                note: 'fastest free tier · use Lite capability (free size limits)' },
};

function ApiTab() {
  const C = window.CafresoHQClient;
  const [s, update] = useSettingsStore();
  const [probing, setProbing] = useStateM(false);
  const [probeResult, setProbeResult] = useStateM(null);
  const [lmModels, setLmModels] = useStateM([]);
  const [olModels, setOlModels] = useStateM([]);
  // Hermes capability: 'lite' vs 'full' system-prompt size. Backed by serve.py
  // /hermes/capability (rewrites config.yaml + restarts gateway).
  const [capMode, setCapMode] = useStateM('lite');
  const [capBusy, setCapBusy] = useStateM(false);
  // Hermes model quick-switch: current model + curated free presets (incl. Nemotron 120B).
  const [hModel, setHModel] = useStateM('');
  const [hPresets, setHPresets] = useStateM([]);
  const [hBusy, setHBusy] = useStateM(false);
  useEffectM(() => {
    if (C && C.hermesGetCapability) C.hermesGetCapability().then(setCapMode).catch(()=>{});
    if (C && C.hermesGetModel) C.hermesGetModel().then(r => { setHModel(r.model || ''); setHPresets(r.presets || []); }).catch(()=>{});
  }, []);
  const changeCap = async (mode) => {
    if (mode === capMode || capBusy) return;
    const prev = capMode; setCapMode(mode); setCapBusy(true);
    try { await C.hermesSetCapability(mode); }
    catch (e) { setCapMode(prev); setProbeResult({ ok:false, detail:'capability: ' + e.message }); }
    finally { setCapBusy(false); }
  };
  const changeModel = async (model) => {
    if (!model || model === hModel || hBusy) return;
    const prev = hModel; setHModel(model); setHBusy(true);
    try { await C.hermesSetModel(model); }
    catch (e) { setHModel(prev); setProbeResult({ ok:false, detail:'model: ' + e.message }); }
    finally { setHBusy(false); }
  };

  // Hermes backend service (which free LLM powers Hermes). Init from the saved
  // preference, then reconcile with whatever the container actually has live.
  const [hBackend, setHBackend] = useStateM(s.hermesBackend || 'openrouter');
  const [keyBusy, setKeyBusy] = useStateM(false);
  useEffectM(() => {
    if (C && C.hermesGetProvider) C.hermesGetProvider()
      .then(r => { if (r && r.configured && HBACKENDS[r.provider]) setHBackend(r.provider); })
      .catch(() => {});
  }, []);
  const changeBackend = (prov) => {
    if (!HBACKENDS[prov]) return;
    setHBackend(prov); update({ hermesBackend: prov });
  };
  const saveKey = async (prov, val) => {
    const meta = HBACKENDS[prov]; if (!meta) return;
    if (val === (s[meta.field] || '')) return;
    setKeyBusy(true); setProbeResult(null);
    try {
      let r = { serverStored: false };
      if (C && C.hermesSetProvider) r = await C.hermesSetProvider(prov, val, '');
      else update({ [meta.field]: val, hermesBackend: prov });
      if (!val) setProbeResult({ ok: true, detail: `${meta.label} key cleared` });
      else if (r && r.serverStored) setProbeResult({ ok: true, detail: `${meta.label} applied · gateway reloading (~15s)` });
      else setProbeResult({ ok: false, detail: (r && r.detail) || 'saved locally only' });
    } catch (e) { setProbeResult({ ok: false, detail: e.message }); }
    finally { setKeyBusy(false); }
  };

  useEffectM(() => {
    if (s.provider === 'lmstudio') {
      window.CafresoHQClient.listLMStudioModels().then(setLmModels).catch(() => setLmModels([]));
    } else if (s.provider === 'ollama') {
      window.CafresoHQClient.listOllamaModels().then(ms => setOlModels(ms.map(m => m.name))).catch(() => setOlModels([]));
    }
  }, [s.provider, s.lmstudioUrl, s.ollamaUrl]);

  const runProbe = async () => {
    setProbing(true); setProbeResult(null);
    try {
      const r = await window.CafresoHQClient.probe();
      setProbeResult(r);
      if (s.provider === 'lmstudio') {
        setLmModels(await window.CafresoHQClient.listLMStudioModels());
      } else if (s.provider === 'ollama') {
        const ms = await window.CafresoHQClient.listOllamaModels();
        setOlModels(ms.map(m => m.name));
      } else if (s.provider === 'google') { // Add this block for Google models
        // No specific model listing needed here as it's done in claude-client.jsx
      }
    } catch (e) { setProbeResult({ ok:false, detail: e.message }); }
    setProbing(false);
  };

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>PROVIDER</h4>
        <div className="row-knob">
          <div><div className="lbl">Backend</div><div className="sub">which brain powers CafresoHQ & crew</div></div>
          <select value={s.provider} onChange={e=>update({provider:e.target.value})}>
            <option value="lmstudio">LM Studio (local)</option>
            <option value="ollama">Ollama (local)</option>
            <option value="anthropic">Anthropic — API credits</option>
            <option value="google">Google (Gemini) — API credits</option>
            <option value="claudecode">Anthropic — Pro/Max (via Claude Code)</option>
            <option value="hermes">Hermes (default · in your container)</option>
            <option value="codex">OpenAI Codex CLI (local + tools)</option>
          </select>
          <span className="hint" style={{maxWidth:240}}>fallback for agents whose model isn't pinned</span>
        </div>
        {s.provider === 'hermes' && (
          <div className="row-knob">
            <div>
              <div className="lbl">Model</div>
              <div className="sub">
                {hBusy ? 'Switching model… (~10s)'
                  : 'Free open-weights in your container · switch anytime'}
              </div>
            </div>
            <select value={hPresets.some(p=>p.id===hModel) ? hModel : ''}
                    disabled={hBusy} onChange={e=>changeModel(e.target.value)}>
              {!hPresets.some(p=>p.id===hModel) && hModel &&
                <option value="">{hModel} (custom)</option>}
              {hPresets.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
            </select>
          </div>
        )}
        {s.provider === 'hermes' && (
          <div className="row-knob">
            <div>
              <div className="lbl">Backend service</div>
              <div className="sub">{HBACKENDS[hBackend] ? HBACKENDS[hBackend].note : 'free LLM behind Hermes'}</div>
            </div>
            <select value={hBackend} disabled={keyBusy} onChange={e=>changeBackend(e.target.value)}>
              <option value="openrouter">OpenRouter (default)</option>
              <option value="gemini">Google Gemini (most reliable free)</option>
              <option value="groq">Groq (fastest free)</option>
            </select>
          </div>
        )}
        {s.provider === 'hermes' && HBACKENDS[hBackend] && (
          <div className="row-knob">
            <div>
              <div className="lbl">{HBACKENDS[hBackend].label} key</div>
              <div className="sub">
                {keyBusy ? 'applying key · gateway reloading (~15s)…' : (
                  <>your free personal key · get one at{' '}
                  <a href={HBACKENDS[hBackend].link} target="_blank" rel="noopener noreferrer"
                     style={{color:'var(--accent-rose, #c45)', textDecoration:'underline'}}>
                    {HBACKENDS[hBackend].linkText}
                  </a></>
                )}
              </div>
            </div>
            <input type="password" key={hBackend} placeholder={HBACKENDS[hBackend].ph}
              autoComplete="off" spellCheck={false} style={{width:200}} disabled={keyBusy}
              defaultValue={s[HBACKENDS[hBackend].field] || ''}
              onBlur={e => saveKey(hBackend, e.target.value.trim())}/>
          </div>
        )}
        {s.provider === 'hermes' && (
          <div className="row-knob">
            <div>
              <div className="lbl">Agent capability</div>
              <div className="sub">
                {capBusy ? 'Reloading agent… (~10s)'
                  : capMode === 'full'
                    ? 'Full toolset in every prompt — needs a larger/paid key (free tiers will 413).'
                    : 'Lite: trimmed prompt that fits free tiers (e.g. Groq free). Tools load on demand.'}
              </div>
            </div>
            <select value={capMode} disabled={capBusy} onChange={e=>changeCap(e.target.value)}>
              <option value="lite">Lite — free-tier safe</option>
              <option value="full">Full — BYOK / heavy</option>
            </select>
          </div>
        )}
        <div className="row-knob">
          <div><div className="lbl">Max tokens per reply</div><div className="sub">caps response length</div></div>
          <input type="number" min="64" max="8192" step="64" style={{width:90}}
            value={s.maxTokens} onChange={e=>update({maxTokens: parseInt(e.target.value)||1024})}/>
        </div>
        <div className="row-knob">
          <div>
            <div className="lbl">Connection test</div>
            <div className="sub">
              {probing ? 'probing…'
                : probeResult ? (probeResult.ok ? `✓ ${probeResult.detail}` : `✕ ${probeResult.detail}`)
                : 'verifies keys/URL work'}
            </div>
          </div>
          <button className="px-btn secondary" onClick={runProbe} disabled={probing}>
            {probing ? '…' : 'TEST'}
          </button>
        </div>
      </div>

      {/* Sub-agent panel — controls the model used by transient sub-agents
          spawned via [SPAWN_SUBAGENT]. Default 'inherit' uses the spawner's
          model. Pinning a small/cheap model here is useful when sub-agents
          are doing high-volume one-shot tasks (e.g. summaries) and you
          don't want to burn the parent's premium model on each. */}
      <div className="cb-panel">
        <h4>SUB-AGENT MODEL</h4>
        <div className="row-knob">
          <div>
            <div className="lbl">Sub-agent model</div>
            <div className="sub">
              {s.subagentModel === 'inherit'
                ? 'Sub-agents inherit the spawner\'s model.'
                : `All sub-agents pinned to: ${s.subagentModel}`}
            </div>
          </div>
          {s.subagentModel === 'inherit' ? (
            <button className="px-btn secondary"
                    onClick={() => update({ subagentModel: window.CafresoHQClient.getSettings().anthropicModel ? 'anthropic:' + window.CafresoHQClient.getSettings().anthropicModel : 'inherit' })}>
              PIN A MODEL…
            </button>
          ) : (
            <button className="px-btn secondary"
                    onClick={() => update({ subagentModel: 'inherit' })}>
              RESET TO INHERIT
            </button>
          )}
        </div>
        {s.subagentModel !== 'inherit' && (
          <div className="row-knob">
            <div>
              <div className="lbl">Pinned model</div>
              <div className="sub">used for every transient sub-agent</div>
            </div>
            <ModelPicker value={s.subagentModel}
                         onChange={(id) => update({ subagentModel: id || 'inherit' })} />
          </div>
        )}
        <div className="row-knob">
          <div>
            <div className="lbl">Per-spawn override</div>
            <div className="sub">
              Spawning agents can override this with
              <code style={{margin:'0 4px'}}>[SPAWN_SUBAGENT: role | model:&lt;id&gt;]</code>
              syntax — that always wins.
            </div>
          </div>
          <span className="hint" style={{maxWidth:240}}>e.g. <code>[SPAWN_SUBAGENT: code-reviewer | model:claudecode:sonnet]</code></span>
        </div>
      </div>

      {s.provider === 'claudecode' && <ClaudeCodePanel s={s} update={update} />}
      {s.provider === 'codex' && <CodexPanel s={s} update={update} />}

      {s.provider === 'anthropic' && (
        <div className="cb-panel">
          <h4>ANTHROPIC</h4>
          <div className="form-row" style={{marginBottom:8}}>
            <label>API KEY</label>
            <input type="password" placeholder="sk-ant-…"
              value={s.anthropicKey} onChange={e=>update({anthropicKey: e.target.value})}/>
            <span className="hint">stored in this browser's localStorage only</span>
          </div>
          <div className="form-row">
            <label>MODEL</label>
            <select value={s.anthropicModel} onChange={e=>update({anthropicModel: e.target.value})}>
              {window.CafresoHQClient.ANTHROPIC_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <span className="hint">used for CEO + any sub-agent whose model isn't pinned</span>
          </div>
        </div>
      )}

      {s.provider === 'google' && (
        <div className="cb-panel">
          <h4>GOOGLE (GEMINI)</h4>
          <div className="form-row" style={{marginBottom:8}}>
            <label>API KEY</label>
            <input type="password" placeholder="AIza…"
              value={s.googleKey} onChange={e=>update({googleKey: e.target.value})}/>
            <span className="hint">stored in this browser's localStorage only</span>
          </div>
          <div className="form-row">
            <label>MODEL</label>
            <select value={s.googleModel} onChange={e=>update({googleModel: e.target.value})}>
              {window.CafresoHQClient.GEMINI_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
            <span className="hint">used for CEO + any sub-agent whose model isn't pinned</span>
          </div>
        </div>
      )}

      {s.provider === 'lmstudio' && (
        <div className="cb-panel">
          <h4>LM STUDIO</h4>
          <div className="form-row" style={{marginBottom:8}}>
            <label>BASE URL</label>
            <input placeholder="/lmstudio/v1"
              value={s.lmstudioUrl} onChange={e=>update({lmstudioUrl: e.target.value})}/>
            <span className="hint">OpenAI-compatible endpoint root (use the /lmstudio/v1 proxy to avoid CORS)</span>
          </div>
          <div className="form-row">
            <label>MODEL</label>
            {lmModels.length ? (
              <select value={s.lmstudioModel} onChange={e=>update({lmstudioModel: e.target.value})}>
                <option value="">— server default —</option>
                {lmModels.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <input placeholder="auto-detect via TEST, or type a model id"
                value={s.lmstudioModel} onChange={e=>update({lmstudioModel: e.target.value})}/>
            )}
            <span className="hint">{lmModels.length ? `${lmModels.length} loaded` : 'hit TEST to list loaded models'}</span>
          </div>
        </div>
      )}

      {s.provider === 'ollama' && (
        <div className="cb-panel">
          <h4>OLLAMA</h4>
          <div className="form-row" style={{marginBottom:8}}>
            <label>BASE URL</label>
            <input placeholder="/ollama/v1"
              value={s.ollamaUrl} onChange={e=>update({ollamaUrl: e.target.value})}/>
            <span className="hint">OpenAI-compatible endpoint (use the /ollama/v1 proxy to avoid CORS)</span>
          </div>
          <div className="form-row">
            <label>MODEL</label>
            {olModels.length ? (
              <select value={s.ollamaModel} onChange={e=>update({ollamaModel: e.target.value})}>
                <option value="">— server default —</option>
                {olModels.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
            ) : (
              <input placeholder="auto-detect via TEST, or type a model id"
                value={s.ollamaModel} onChange={e=>update({ollamaModel: e.target.value})}/>
            )}
            <span className="hint">{olModels.length ? `${olModels.length} loaded` : 'hit TEST to list loaded models'}</span>
          </div>
        </div>
      )}


      <BraveTab s={s} update={update} />
      <VaultTab />
    </div>
  );
}

function ClaudeCodePanel({ s, update }) {
  const [status, setStatus] = useStateM({ configured: false, binary: '', override: '' });
  const [draft, setDraft] = useStateM('');
  const [busy, setBusy] = useStateM(false);
  const [msg, setMsg] = useStateM(null);

  const refresh = async () => {
    try {
      const st = await window.CafresoHQClient.claudecodeStatus();
      setStatus(st);
      if (!draft) setDraft(st.override || '');
    } catch (_e) {}
  };
  useEffectM(() => { refresh(); }, []);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await window.CafresoHQClient.claudecodeConfigure(draft.trim());
      await refresh();
      setMsg({ ok: true, text: draft.trim() ? 'override saved' : 'cleared (using PATH)' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  return (
    <div className="cb-panel">
      <h4>🟣 CLAUDE CODE (PRO / MAX)</h4>
      <div className="hint" style={{marginBottom:10}}>
        Routes calls through your locally-installed <code>claude</code> CLI, which is already
        authenticated against your Pro/Max subscription. Each call spawns a subprocess on the
        proxy machine, so requests are slightly slower than direct API but use your subscription
        instead of API credits. Tool use inside Claude Code is disabled so CafresoHQ's own
        tool loop stays in charge.
      </div>
      <div className="row-knob">
        <div>
          <div className="lbl">CLI status</div>
          <div className="sub">
            {status.configured
              ? <>✓ found at <code>{status.binary}</code></>
              : '✕ claude binary not found on the proxy machine'}
            {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
          </div>
        </div>
      </div>
      <div className="form-row" style={{marginBottom:8,marginTop:6}}>
        <label>OVERRIDE PATH</label>
        <input placeholder="(blank = look up `claude` on PATH)"
          value={draft} onChange={e=>setDraft(e.target.value)}/>
        <span className="hint">absolute path to a different claude binary; leave blank to auto-detect</span>
      </div>
      <div className="row-knob">
        <div><div className="lbl">Default model</div><div className="sub">used when an agent hasn't pinned one</div></div>
        <select value={s.claudecodeModel} onChange={e=>update({claudecodeModel: e.target.value})}>
          {window.CafresoHQClient.CLAUDECODE_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="row-knob">
        <div><div className="lbl">Save override</div><div className="sub">stored in the proxy's memory; re-set on restart unless CAFRESOHQ_CLAUDE_BIN env var</div></div>
        <button className="px-btn secondary" onClick={save} disabled={busy}>{busy ? '…' : 'SAVE'}</button>
      </div>
    </div>
  );
}

function CodexPanel({ s, update }) {
  const [status, setStatus] = useStateM({ configured: false, binary: '', override: '', allowedDirs: [], badDirs: [] });
  const [draft, setDraft] = useStateM('');
  const [busy, setBusy] = useStateM(false);
  const [msg, setMsg] = useStateM(null);

  const refresh = async () => {
    try {
      const st = await window.CafresoHQClient.codexStatus();
      setStatus(st);
      if (!draft) setDraft(st.override || '');
    } catch (_e) {}
  };
  useEffectM(() => { refresh(); }, []);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await window.CafresoHQClient.codexConfigure(draft.trim());
      await refresh();
      setMsg({ ok: true, text: draft.trim() ? 'override saved' : 'cleared (using PATH)' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  return (
    <div className="cb-panel">
      <h4>CODEX CLI</h4>
      <div className="hint" style={{marginBottom:10}}>
        Routes calls through your locally-installed <code>codex</code> CLI using the profiles in
        <code> ~/.codex/config.toml</code>. Pick a default profile-backed model below; agent-specific
        pins still override it.
      </div>
      <div className="row-knob">
        <div>
          <div className="lbl">CLI status</div>
          <div className="sub">
            {status.configured
              ? <>found at <code>{status.binary}</code></>
              : 'codex binary not found on the proxy machine'}
            {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
          </div>
          {!!status.badDirs?.length && (
            <div className="sub" style={{color:'var(--warning, #c97b2a)', marginTop:4}}>
              invalid CAFRESOHQ_ALLOWED_DIRS: {status.badDirs.join(', ')}
            </div>
          )}
        </div>
      </div>
      <div className="form-row" style={{marginBottom:8,marginTop:6}}>
        <label>OVERRIDE PATH</label>
        <input placeholder="(blank = look up `codex` on PATH)"
          value={draft} onChange={e=>setDraft(e.target.value)}/>
        <span className="hint">absolute path to a different codex binary; leave blank to auto-detect</span>
      </div>
      <div className="row-knob">
        <div>
          <div className="lbl">Default model</div>
          <div className="sub">maps to a profile in <code>~/.codex/config.toml</code></div>
        </div>
        <select value={s.codexModel} onChange={e=>update({codexModel: e.target.value})}>
          {window.CafresoHQClient.CODEX_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="row-knob">
        <div><div className="lbl">Save override</div><div className="sub">stored in the proxy's memory; re-set on restart unless CAFRESOHQ_CODEX_BIN env var</div></div>
        <button className="px-btn secondary" onClick={save} disabled={busy}>{busy ? '...' : 'SAVE'}</button>
      </div>
    </div>
  );
}

function VaultTab() {
  const [status, setStatus] = useStateM({
    configured: false, backend: 'fs', root: '', defaultRoot: '', restUrl: '', restKey: '',
    fsExists: false, restReachable: false, restDetail: '', unavailable: false, error: '',
  });
  const [draftRoot, setDraftRoot] = useStateM('');
  const [draftUrl, setDraftUrl] = useStateM('');
  const [draftKey, setDraftKey] = useStateM('');
  const [busy, setBusy] = useStateM(false);
  const [msg, setMsg] = useStateM(null);
  const [files, setFiles] = useStateM(null);

  const refresh = async () => {
    try {
      const s = await window.CafresoHQClient.vaultStatus();
      setStatus({ ...s, unavailable: false, error: '' });
      setDraftRoot(s.root || '');
      setDraftUrl(s.restUrl || '');
      // We never get the actual key back from the server; only the masked sentinel.
      if (!draftKey) setDraftKey('');
      if (s.configured) {
        try { setFiles(await window.CafresoHQClient.vaultList()); } catch (_e) { setFiles(null); }
      } else { setFiles(null); }
    } catch (e) {
      const message = e.message || 'CafresoHQ bridge is not reachable.';
      setStatus({
        configured: false, backend: 'fs', root: draftRoot || '', defaultRoot: '', restUrl: draftUrl || '', restKey: '',
        fsExists: false, restReachable: false, restDetail: '', unavailable: true, error: message,
      });
      setFiles(null);
      setMsg({ ok: false, text: message });
    }
  };
  useEffectM(() => { refresh(); }, []);

  const cleanLocalRoot = (value) => (value || '').trim().replace(/^["']+|["']+$/g, '');

  const setBackend = async (backend) => {
    setBusy(true); setMsg(null);
    try {
      await window.CafresoHQClient.vaultConfigure({ backend });
      window.HQ.clearVaultReadyCache();
      await refresh();
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const saveFs = async () => {
    const root = cleanLocalRoot(draftRoot);
    setBusy(true); setMsg(null);
    try {
      await window.CafresoHQClient.vaultConfigure({ backend: 'fs', root });
      window.HQ.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: root ? 'configured' : 'cleared' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const useCafresoHQVault = async () => {
    const root = status.defaultRoot || draftRoot.trim();
    if (!root) return;
    setBusy(true); setMsg(null);
    try {
      setDraftRoot(root);
      await window.CafresoHQClient.vaultConfigure({ backend: 'fs', root });
      window.HQ.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: 'using CafresoHQ vault' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const detectObsidianVault = async () => {
    setBusy(true); setMsg(null);
    try {
      const found = await window.CafresoHQClient.vaultDiscover();
      const vaults = found.vaults || [];
      const pick = vaults.find(v => v.exists) || vaults[0];
      if (!pick) {
        setMsg({ ok: false, text: 'no Obsidian vaults found' });
      } else if (!pick.exists) {
        setMsg({ ok: false, text: `found ${pick.name}, but path is missing` });
      } else {
        setDraftRoot(pick.path);
        await window.CafresoHQClient.vaultConfigure({ backend: 'fs', root: pick.path });
        window.HQ.clearVaultReadyCache();
        await refresh();
        setMsg({ ok: true, text: `using ${pick.name}` });
      }
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const saveRest = async () => {
    setBusy(true); setMsg(null);
    try {
      const patch = { restUrl: draftUrl.trim() };
      if (draftKey.trim()) patch.restKey = draftKey.trim();
      await window.CafresoHQClient.vaultConfigure(patch);
      setDraftKey(''); // clear the in-memory draft so we don't redisplay
      window.HQ.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: 'saved' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const isRest = status.backend === 'rest';

  return (
    <div className="cb-panel">
      <h4>MARKDOWN VAULT</h4>
      <div className="row-knob">
        <div><div className="lbl">Storage</div><div className="sub">CafresoHQ works with a plain Markdown folder; Obsidian is optional</div></div>
        <div style={{display:'flex',gap:6}}>
          <button className={`px-btn ${!isRest?'primary':'secondary'}`} style={{fontSize:9}} onClick={()=>setBackend('fs')} disabled={busy}>LOCAL DIRECTORY</button>
          <button className={`px-btn ${isRest?'primary':'secondary'}`} style={{fontSize:9}} onClick={()=>setBackend('rest')} disabled={busy}>OBSIDIAN REST</button>
        </div>
      </div>

      {!isRest && (<>
        <div className="form-row" style={{marginBottom:8,marginTop:6}}>
          <label>VAULT DIRECTORY</label>
          <input placeholder={status.defaultRoot || 'C:/Users/you/Documents/cafresohq/hq-state/vault'}
            value={draftRoot} onChange={e=>setDraftRoot(e.target.value)}/>
          <span className="hint">absolute path to a Markdown folder; the default lives inside CafresoHQ under <code>hq-state/vault</code></span>
        </div>
        <div className="row-knob">
          <div>
            <div className="lbl">Status</div>
            <div className="sub">
              {status.fsExists
                ? `✓ ${files?.length ?? '…'} note${files?.length === 1 ? '' : 's'} indexed`
                : (draftRoot ? `path not yet saved` : 'not configured')}
              {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
            </div>
          </div>
          <div style={{display:'flex',gap:6,flexWrap:'wrap',justifyContent:'flex-end'}}>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={useCafresoHQVault} disabled={busy}>{busy ? '...' : 'USE APP VAULT'}</button>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={detectObsidianVault} disabled={busy}>{busy ? '...' : 'DETECT OBSIDIAN'}</button>
            <button className="px-btn secondary" style={{fontSize:9}} onClick={saveFs} disabled={busy}>{busy ? '...' : 'SAVE'}</button>
          </div>
        </div>
      </>)}

      {isRest && (<>
        <div className="form-row" style={{marginBottom:8,marginTop:6}}>
          <label>REST URL</label>
          <input placeholder="https://127.0.0.1:27124"
            value={draftUrl} onChange={e=>setDraftUrl(e.target.value)}/>
          <span className="hint">optional Obsidian Local REST API endpoint (HTTPS, self-signed cert OK via proxy)</span>
        </div>
        <div className="form-row" style={{marginBottom:8}}>
          <label>API KEY</label>
          <input type="password" placeholder={status.restKey ? '•••• (saved — type to replace)' : 'paste from Obsidian → Local REST API settings'}
            value={draftKey} onChange={e=>setDraftKey(e.target.value)}/>
          <span className="hint">optional; stored only on this proxy server (in memory); never logged</span>
        </div>
        <div className="row-knob">
          <div>
            <div className="lbl">Status</div>
            <div className="sub">
              {status.restReachable
                ? `✓ plugin reachable · ${files?.length ?? '…'} note${files?.length === 1 ? '' : 's'} indexed`
                : (status.restDetail ? `✕ ${status.restDetail}` : 'not yet tested')}
              {msg && <span style={{marginLeft:8, color: msg.ok ? '#4a8c4a' : 'var(--error)'}}>{msg.text}</span>}
            </div>
          </div>
          <button className="px-btn secondary" onClick={saveRest} disabled={busy}>{busy ? '…' : 'SAVE'}</button>
        </div>
        <div className="hint" style={{marginTop:8}}>
          Obsidian REST is optional. It unlocks plugin-mediated file access and open-in-Obsidian.
          Install the <em>Local REST API</em> community plugin in Obsidian, copy its API key, and paste above.
        </div>
      </>)}

      <div className="hint" style={{marginTop:8,fontSize:11}}>
        Agents whose role includes the <strong>Vault Notes</strong> tool can search/read/append/create Markdown notes from the local directory.
        Tip: pass <code>CAFRESOHQ_VAULT</code> to override the app vault, or <code>CAFRESOHQ_OBSIDIAN_URL</code> / <code>CAFRESOHQ_OBSIDIAN_KEY</code> for optional Obsidian REST.
      </div>
    </div>
  );
}

function BraveTab({ s, update }) {
  const [probing, setProbing] = useStateM(false);
  const [result, setResult] = useStateM(null);
  const test = async () => {
    setProbing(true); setResult(null);
    try { setResult(await window.CafresoHQClient.braveProbe()); }
    catch (e) { setResult({ ok:false, detail: e.message }); }
    setProbing(false);
  };
  return (
    <div className="cb-panel">
      <h4>🔍 BRAVE WEB SEARCH</h4>
      <div className="row-knob">
        <div><div className="lbl">Enable web search tool</div><div className="sub">agents with the WEB tool can call <code>[SEARCH: query]</code></div></div>
        <div className={`pxswitch ${s.braveEnabled?'on':''}`} onClick={()=>update({braveEnabled: !s.braveEnabled})}><div className="nub"/></div>
      </div>
      <div className="form-row" style={{marginBottom:8}}>
        <label>API KEY</label>
        <input type="password" placeholder="BSA-…"
          value={s.braveKey} onChange={e=>update({braveKey: e.target.value})}/>
        <span className="hint">stored in this browser's localStorage; sent to /brave/search on this proxy only</span>
      </div>
      <div className="row-knob">
        <div>
          <div className="lbl">Connection test</div>
          <div className="sub">
            {probing ? 'probing…' : result ? (result.ok ? `✓ ${result.detail}` : `✕ ${result.detail}`) : 'verifies key works'}
          </div>
        </div>
        <button className="px-btn secondary" onClick={test} disabled={probing || !s.braveKey}>
          {probing ? '…' : 'TEST'}
        </button>
      </div>
    </div>
  );
}

function WorkflowModal({ open, onClose, tasks, workflows, onSave }) {
  const [name, setName] = useStateM('');
  const [desc, setDesc] = useStateM('');
  const [steps, setSteps] = useStateM([]); // array of task ids in order
  const [autoDispatch, setAutoDispatch] = useStateM(false);

  /* Reset on (re)open so a previous workflow draft doesn't persist. */
  useEffectM(() => {
    if (!open) return;
    setName(''); setDesc(''); setSteps([]); setAutoDispatch(false);
  }, [open]);

  if (!open) return null;

  const inboxTasks = tasks.filter(t => t.status !== 'done' && !steps.includes(t.id));
  const addStep = (taskId) => setSteps(s => [...s, taskId]);
  const removeStep = (taskId) => setSteps(s => s.filter(id => id !== taskId));
  const moveUp = (i) => { if (i === 0) return; const s = [...steps]; [s[i-1], s[i]] = [s[i], s[i-1]]; setSteps(s); };

  const submit = () => {
    if (!name.trim() || steps.length < 2) return;
    const wfId = HQ.uid('wf');
    // Link tasks: set chainTo for each step pointing to the next
    onSave({
      workflow: { id: wfId, name: name.trim(), description: desc.trim(), steps, createdAt: Date.now() },
      taskPatches: steps.map((id, i) => ({
        id,
        workflowId: wfId,
        chainTo: steps[i + 1] || null,
        autoDispatch,
        dependsOn: i > 0 ? [steps[i - 1]] : null,
      })),
    });
    onClose();
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="NEW WORKFLOW"
      subtitle="chain tasks · auto-run or step-approve"
      size="lg"
      footer={
        <>
          <div className="hint" style={{marginRight: 'auto'}}>
            {steps.length < 2 ? 'Add at least 2 tasks to create a workflow.' : `${steps.length} steps ready.`}
          </div>
          <button className="px-btn primary" onClick={submit} disabled={!name.trim() || steps.length < 2}>CREATE WORKFLOW ✓</button>
        </>
      }
    >
          <div className="control-board">
            <div className="cb-panel">
              <h4>DETAILS</h4>
              <div className="form-row" style={{marginBottom:8}}>
                <label>NAME</label>
                <input placeholder="e.g. Code Review Pipeline" value={name} onChange={e=>setName(e.target.value)}/>
              </div>
              <div className="form-row" style={{marginBottom:8}}>
                <label>DESC</label>
                <input placeholder="optional description" value={desc} onChange={e=>setDesc(e.target.value)}/>
              </div>
              <div className="row-knob" style={{marginTop:8}}>
                <div><div className="lbl">Auto-dispatch steps</div><div className="sub">skip approval between steps</div></div>
                <div className={`pxswitch ${autoDispatch?'on':''}`} onClick={()=>setAutoDispatch(v=>!v)}><div className="nub"/></div>
              </div>
            </div>
            <div className="cb-panel">
              <h4>STEPS ({steps.length})</h4>
              <div className="stack" style={{marginBottom:10}}>
                {steps.length === 0 && <div className="muted">Add tasks from the list below →</div>}
                {steps.map((id, i) => {
                  const t = tasks.find(x => x.id === id);
                  if (!t) return null;
                  return (
                    <div key={id} className="row" style={{padding:'4px 6px',gap:4}}>
                      <span className="sub" style={{minWidth:16}}>{i+1}.</span>
                      <span className="grow" style={{fontFamily:'Press Start 2P',fontSize:8}}>{t.title.slice(0,40)}</span>
                      <button className="px-btn secondary" style={{fontSize:7,padding:'3px 5px'}} onClick={()=>moveUp(i)}>↑</button>
                      <button className="px-btn danger" style={{fontSize:7,padding:'3px 5px'}} onClick={()=>removeStep(id)}>✕</button>
                    </div>
                  );
                })}
              </div>
              <h4 style={{marginTop:8}}>AVAILABLE TASKS</h4>
              <div className="stack">
                {inboxTasks.length === 0 && <div className="muted">No inbox tasks available.</div>}
                {inboxTasks.map(t => (
                  <div key={t.id} className="row" style={{padding:'4px 6px',cursor:'pointer'}} onClick={()=>addStep(t.id)}>
                    <span className="grow tiny">{t.title.slice(0,50)}</span>
                    <button className="px-btn secondary" style={{fontSize:7,padding:'3px 5px'}}>+ ADD</button>
                  </div>
                ))}
              </div>
            </div>
          </div>
    </Modal>
  );
}

/* ==========================================================================
   MeetingRoomModal — spin up a multi-agent meeting room.
   The boss picks 2+ agents from the roster and (optionally) a topic. The
   meeting is persisted as a `meeting:<id>` thread; messages sent inside
   that thread fan out to every attendee in parallel, with each reply
   streaming inline. Attendees see who else is "in the room" and can
   reference each other in their replies. Closing the meeting (× on the
   tab) removes it from the meetings list — the chat history stays in
   the global chat store but becomes unreachable via tab.
   ========================================================================== */
function MeetingRoomModal({ open, onClose, agents, meetings, setMeetings, onOpenMeeting }) {
  const [name, setName] = useStateM('');
  const [topic, setTopic] = useStateM('');
  const [selectedIds, setSelectedIds] = useStateM([]);
  useEffectM(() => {
    if (open) {
      /* If something stashed a prefill on window (Tasks "📋 ROOM" button
         does this — fills name/topic/agentIds from a task), consume and
         clear it. Otherwise generate a default timestamp name. */
      const pre = (typeof window !== 'undefined') ? window._cafresohqMeetingPrefill : null;
      if (pre && pre.name) {
        setName(pre.name);
        setTopic(pre.topic || '');
        setSelectedIds(Array.isArray(pre.agentIds) ? pre.agentIds : []);
        try { delete window._cafresohqMeetingPrefill; } catch (_) { window._cafresohqMeetingPrefill = null; }
        return;
      }
      const stamp = new Date();
      const hh = String(stamp.getHours()).padStart(2, '0');
      const mm = String(stamp.getMinutes()).padStart(2, '0');
      setName(`Meeting ${hh}:${mm}`);
      setTopic('');
      setSelectedIds([]);
    }
  }, [open]);
  if (!open) return null;
  const toggle = (id) => setSelectedIds(prev =>
    prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  const canCreate = name.trim() && selectedIds.length >= 1;
  const create = () => {
    if (!canCreate) return;
    const id = 'mt_' + Math.random().toString(36).slice(2, 9);
    const meeting = {
      id, name: name.trim(),
      topic: topic.trim() || null,
      agentIds: selectedIds,
      createdAt: Date.now(),
    };
    setMeetings(prev => [...(prev || []), meeting]);
    onClose && onClose();
    if (onOpenMeeting) onOpenMeeting(id);
  };
  return (
    <Modal open={open} onClose={onClose} title="📋 NEW MEETING ROOM" size="md">
      <div className="meeting-modal-body">
        <label>
          Name
          <input
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="Architecture review"
            autoFocus
          />
        </label>
        <label>
          Topic <span style={{opacity:0.5,fontSize:9,marginLeft:4}}>(optional — included in opening prompt context)</span>
          <input
            value={topic}
            onChange={e => setTopic(e.target.value)}
            placeholder="Plan the v2 migration"
          />
        </label>
        <label>
          Attendees <span style={{opacity:0.5,fontSize:9,marginLeft:4}}>(pick at least one — they'll all see each other's replies)</span>
          <div className="meeting-attendee-grid">
            {agents.length === 0 && (
              <div style={{fontSize:10,opacity:0.5,gridColumn:'1/-1',padding:'8px'}}>
                No agents hired. Hire some on the Team tab first.
              </div>
            )}
            {agents.map(a => (
              <div
                key={a.id}
                className={'meeting-attendee' + (selectedIds.includes(a.id) ? ' selected' : '')}
                onClick={() => toggle(a.id)}
              >
                <span style={{fontSize:14}}>{a.elevated ? '🛡' : '👤'}</span>
                <div style={{display:'flex',flexDirection:'column',lineHeight:1.1,minWidth:0}}>
                  <span className="meeting-attendee-name">{a.name}</span>
                  <span className="meeting-attendee-role">{a.role}</span>
                </div>
              </div>
            ))}
          </div>
        </label>
        <div style={{display:'flex',justifyContent:'flex-end',gap:'8px',marginTop:'8px'}}>
          <button className="px-btn secondary" onClick={onClose}>Cancel</button>
          <button className="px-btn primary" onClick={create} disabled={!canCreate}>
            Open Meeting · {selectedIds.length} attendee{selectedIds.length === 1 ? '' : 's'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   InboxModal — shows the durable message registry (Phase 1 of the agent-
   communication refactor). Reads from window.CafresoHQMessages which is
   exposed by app.jsx's MessageRegistry. Message records persist
   independently of the chat scrollback so the boss can always trace what
   happened to a handoff: who sent it, what state it's in, what artifacts
   came out of it, and on failure the structured cause + action needed.

   Filters by state (active / blocked / failed / completed / all) and by
   counterpart agent. Threads can be expanded to see the full child chain.
   ───────────────────────────────────────────────────────────────────── */
function InboxModal({ open, onClose }) {
  // Pick up an initial filter from sessionStorage when the modal is
  // opened via the palette commands `Show blockers` / `Show failed` etc.
  // Cleared after read so a manual nav-button open defaults back to 'active'.
  const initialFilter = React.useMemo(() => {
    if (!open) return 'active';
    try {
      const v = sessionStorage.getItem('cafresohq:inbox-filter');
      if (v) {
        sessionStorage.removeItem('cafresohq:inbox-filter');
        return v;
      }
    } catch(_e) {}
    return 'active';
  }, [open]);
  const [filterState, setFilterState] = React.useState(initialFilter);
  const [filterAgent, setFilterAgent] = React.useState('all');
  const [expanded, setExpanded] = React.useState(new Set());
  const [tick, setTick] = React.useState(0);  // poll the registry for updates

  // When the modal toggles open with a fresh initialFilter, reset state.
  React.useEffect(() => {
    if (open) setFilterState(initialFilter);
  }, [open, initialFilter]);

  /* Re-render every 1.5s while open so in-flight state changes show up
     without us having to thread a subscription through MessageRegistry.
     Fast enough to feel live, slow enough not to thrash. */
  React.useEffect(() => {
    if (!open) return;
    const t = setInterval(() => setTick(v => v + 1), 1500);
    return () => clearInterval(t);
  }, [open]);

  if (!open) return null;
  const reg = window.CafresoHQMessages;
  if (!reg) {
    return (
      <Modal open={open} onClose={onClose} title="📬 INBOX" subtitle="message registry unavailable" size="md">
        <div className="empty-state"><div className="empty-title">Registry not loaded.</div><div className="empty-sub">Reload the app and try again.</div></div>
      </Modal>
    );
  }
  const all = reg.list();
  const states = reg.states;

  // Group messages by thread, sort threads by most-recent activity desc.
  const byThread = new Map();
  for (const m of all) {
    if (!byThread.has(m.threadId)) byThread.set(m.threadId, []);
    byThread.get(m.threadId).push(m);
  }
  // Sort within thread: oldest first (so chain reads top→down).
  for (const arr of byThread.values()) arr.sort((a, b) => a.createdAt - b.createdAt);
  const threads = [...byThread.entries()]
    .map(([tid, msgs]) => ({ tid, msgs, latest: Math.max(...msgs.map(m => m.updatedAt || m.createdAt)) }))
    .sort((a, b) => b.latest - a.latest);

  // Build the unique counterpart-agent list (anyone who's the counterpart on
  // any visible thread) for the agent filter dropdown.
  const allAgents = new Set();
  for (const m of all) {
    if (m.fromAgentId && m.fromAgentId !== 'boss') allAgents.add(m.fromAgentName || m.fromAgentId);
    if (m.toAgentId) allAgents.add(m.toAgentName || m.toAgentId);
  }
  const agentList = ['all', ...[...allAgents].sort()];

  // Apply filters at thread level (a thread is included if ANY of its
  // messages match the filter — keeps context).
  const matchesState = (m) => {
    if (filterState === 'all') return true;
    if (filterState === 'active') return states[m.state] && !states[m.state].terminal;
    return m.state === filterState;
  };
  const matchesAgent = (m) =>
    filterAgent === 'all' ||
    m.fromAgentName === filterAgent || m.toAgentName === filterAgent ||
    m.fromAgentId === filterAgent || m.toAgentId === filterAgent;

  const visibleThreads = threads.filter(({ msgs }) =>
    msgs.some(m => matchesState(m) && matchesAgent(m)));

  const fmtTs = (t) => {
    if (!t) return '—';
    const d = Date.now() - t;
    if (d < 60_000) return 'now';
    if (d < 3_600_000) return Math.floor(d / 60_000) + 'm';
    if (d < 86_400_000) return Math.floor(d / 3_600_000) + 'h';
    return Math.floor(d / 86_400_000) + 'd';
  };

  const statePill = (state) => {
    const meta = states[state] || { label: state, color: '#888' };
    return (
      <span style={{
        display:'inline-block', fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
        padding: '2px 7px', borderRadius: 999,
        background: meta.color, color: '#fff',
        textTransform: 'uppercase',
      }}>{meta.label}</span>
    );
  };

  const renderMessage = (m, isChild = false) => (
    <div key={m.id} style={{
      borderLeft: isChild ? '2px solid var(--rule)' : 'none',
      marginLeft: isChild ? 12 : 0,
      paddingLeft: isChild ? 10 : 0,
      paddingTop: 8, paddingBottom: 8,
      borderTop: isChild ? '1px dashed var(--rule)' : 'none',
    }}>
      <div style={{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap',marginBottom:4}}>
        {statePill(m.state)}
        <span style={{fontWeight:600,fontSize:11}}>
          <span style={{opacity:0.7}}>{m.fromAgentName || 'Agent'}</span>
          <span style={{opacity:0.4,margin:'0 4px'}}>→</span>
          <span>{m.toAgentName || '?'}</span>
        </span>
        {m.priority && m.priority !== 'med' && (
          <span style={{fontSize:9,padding:'1px 5px',borderRadius:4,background:'var(--paper-2)'}}>{m.priority}</span>
        )}
        <span style={{marginLeft:'auto',fontSize:10,opacity:0.55}}>{fmtTs(m.updatedAt || m.createdAt)}</span>
      </div>
      <div style={{fontSize:11,lineHeight:1.45,opacity:0.85,marginBottom:4,whiteSpace:'pre-wrap',
        display:'-webkit-box',WebkitLineClamp:3,WebkitBoxOrient:'vertical',overflow:'hidden'}}>
        {m.body || '(no body)'}
      </div>
      {m.failureCause && (
        <div style={{
          fontSize:10,padding:'5px 8px',marginTop:4,borderRadius:4,
          background:'rgba(217,87,87,0.10)', borderLeft:'3px solid #d95757',
        }}>
          <div style={{fontWeight:700,marginBottom:2}}>{m.failureCause.kind} · {m.failureCause.retryable ? 'retryable' : 'not retryable'}</div>
          <div style={{opacity:0.85}}><b>Action:</b> {m.failureCause.actionNeeded || '(none)'}</div>
          {m.failureCause.message && (
            <div style={{opacity:0.6,fontFamily:'monospace',fontSize:9,marginTop:3}}>{m.failureCause.message}</div>
          )}
        </div>
      )}
      {m.artifacts && m.artifacts.length > 0 && (
        <div style={{fontSize:10,opacity:0.75,marginTop:4}}>
          📎 {m.artifacts.map((a, i) => (
            <span key={i} style={{marginRight:6}}>
              {a.kind} <code style={{fontSize:9}}>{a.path}</code>
            </span>
          ))}
        </div>
      )}
      {m.history && m.history.length > 1 && (
        <details style={{marginTop:4}}>
          <summary style={{fontSize:9,opacity:0.55,cursor:'pointer'}}>history ({m.history.length} events)</summary>
          <div style={{fontSize:9,opacity:0.7,marginTop:4,fontFamily:'monospace'}}>
            {m.history.map((h, i) => (
              <div key={i}>{new Date(h.at).toLocaleTimeString()} · <b>{h.state}</b> · {h.by} {h.note ? `— ${h.note}` : ''}</div>
            ))}
          </div>
        </details>
      )}
    </div>
  );

  // Counts by state across the whole registry — for the filter chips.
  const stateCounts = (() => {
    const c = { active: 0, all: all.length };
    for (const m of all) {
      const t = (states[m.state] && states[m.state].terminal);
      if (!t) c.active++;
      c[m.state] = (c[m.state] || 0) + 1;
    }
    return c;
  })();

  return (
    <Modal open={open} onClose={onClose}
           title="📬 INBOX"
           subtitle={`${visibleThreads.length} thread${visibleThreads.length === 1 ? '' : 's'} · ${all.length} message${all.length === 1 ? '' : 's'} total`}
           size="xl">
      <div style={{display:'flex',gap:6,flexWrap:'wrap',marginBottom:10,alignItems:'center'}}>
        {['active','blocked','failed','completed','all'].map(s => (
          <button key={s} className={`px-btn ${filterState === s ? 'primary' : 'secondary'}`}
                  style={{fontSize:9}} onClick={() => setFilterState(s)}>
            {s.toUpperCase()} {stateCounts[s] != null && <span style={{opacity:0.6,marginLeft:4}}>{stateCounts[s]}</span>}
          </button>
        ))}
        <select value={filterAgent} onChange={e => setFilterAgent(e.target.value)}
                style={{marginLeft:'auto',fontSize:11,padding:'3px 6px',border:'2px solid var(--ink)',background:'var(--paper)',color:'var(--ink)'}}>
          {agentList.map(a => <option key={a} value={a}>{a === 'all' ? 'all agents' : a}</option>)}
        </select>
      </div>
      {visibleThreads.length === 0 ? (
        <div className="empty-state">
          <div className="empty-title">No messages match this filter.</div>
          <div className="empty-sub">Try widening the state filter, or @-mention an agent to start a thread.</div>
        </div>
      ) : (
        <div style={{display:'flex',flexDirection:'column',gap:10}}>
          {visibleThreads.slice(0, 100).map(({ tid, msgs }) => {
            const head = msgs[0];
            const tail = msgs[msgs.length - 1];
            const isOpen = expanded.has(tid);
            const summary = `${head.fromAgentName} → ${head.toAgentName}${msgs.length > 1 ? ` (+${msgs.length - 1} replies)` : ''}`;
            return (
              <div key={tid} style={{border:'1px solid var(--rule)',borderRadius:4,padding:10,background:'var(--paper)'}}>
                <div onClick={() => setExpanded(prev => { const n = new Set(prev); n.has(tid) ? n.delete(tid) : n.add(tid); return n; })}
                     style={{cursor:'pointer',display:'flex',alignItems:'center',gap:8,marginBottom:6}}>
                  <span style={{fontSize:10,opacity:0.6}}>{isOpen ? '▼' : '▶'}</span>
                  <span style={{fontSize:11,fontWeight:700,flex:1}}>{summary}</span>
                  {statePill(tail.state)}
                  <span style={{fontSize:10,opacity:0.55,marginLeft:6}}>{fmtTs(tail.updatedAt || tail.createdAt)}</span>
                </div>
                {isOpen ? (
                  <div>{msgs.map((m, i) => renderMessage(m, i > 0))}</div>
                ) : (
                  <div style={{fontSize:10,opacity:0.7,whiteSpace:'pre-wrap',
                    display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical',overflow:'hidden'}}>
                    {head.body || '(empty)'}
                  </div>
                )}
              </div>
            );
          })}
          {visibleThreads.length > 100 && (
            <div style={{fontSize:10,opacity:0.55,textAlign:'center'}}>
              … {visibleThreads.length - 100} more threads. Filter to narrow down.
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

window.CafresoHQModals = { Modal, HireModal, SettingsModal, WorkflowModal, MeetingRoomModal, InboxModal };
