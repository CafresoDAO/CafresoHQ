/* ==========================================================================
   CafresoAI — modals (Hire / Settings)
   ========================================================================== */

const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;

/* Single source of truth for settings — subscribes to the client's pub/sub so
   any component using this hook re-renders whenever setSettings() is called,
   even from a different component tree. */
function useSettingsStore() {
  const [s, setS] = useStateM(() => window.OpenclawClient.getSettings());
  useEffectM(() => {
    return window.OpenclawClient.onSettingsChange(fresh => setS({ ...fresh }));
  }, []);
  return [s, patch => window.OpenclawClient.setSettings(patch)];
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
    window.OpenclawClient.localModelOptions()
      .then(g => {
        if (!live) return;
        setGroups(g);
        setLoading(false);
      })
      .catch(() => {
        if (!live) return;
        /* Last-resort fallback — all static model lists so the picker
           is never blank. Static lists only. */
        const s = window.OpenclawClient.getSettings();
        const fallback = [
          { label: 'Anthropic (Claude API)', provider: 'anthropic',
            options: window.OpenclawClient.ANTHROPIC_MODELS.map(m => ({ id: 'anthropic:' + m, label: m })) },
          { label: 'Google (Gemini API)', provider: 'google',
            options: window.OpenclawClient.GEMINI_MODELS.map(m => ({ id: 'google:' + m, label: m })) },
          { label: 'Codex CLI', provider: 'codex',
            options: window.OpenclawClient.CODEX_MODELS.map(m => ({ id: 'codex:' + m, label: m })) },
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

const TEMPLATES_KEY = 'openclaw_hire_templates_v1';
function loadTemplates() {
  try { return JSON.parse(localStorage.getItem(TEMPLATES_KEY) || '[]'); }
  catch (_e) { return []; }
}
function saveTemplates(ts) {
  try { localStorage.setItem(TEMPLATES_KEY, JSON.stringify(ts)); }
  catch (err) {
    console.warn('[openclaw] saveTemplates failed:', err);
    try { window.dispatchEvent(new CustomEvent('openclaw:storage-error', { detail: { key: TEMPLATES_KEY, error: err } })); } catch (_e) {}
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
  const [role, setRole] = useStateM(MOCK.ROLES[0]);
  const [prompt, setPrompt] = useStateM('You are a helpful sub-agent. Be concise and warm.');
  const [tools, setTools] = useStateM(['web','files']);
  const [avatar, setAvatar] = useStateM('rose');
  const [model, setModel] = useStateM('anthropic:claude-haiku-4-5-20251001');
  const [temp, setTemp] = useStateM(0.4);
  /* elevated = the agent will be backed by an OpenClaw session with file/shell
     access on the host computer. Off by default — a deliberate, scary opt-in. */
  const [elevated, setElevated] = useStateM(false);
  const [templates, setTemplates] = useStateM(loadTemplates);
  const [showBoard, setShowBoard] = useStateM(true);

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
      `This agent will be backed by an elevated CafresoAI session that can read/write files and run shell commands on this machine.\n\n` +
      `· Inter-agent DMs cannot reach them (only your direct dispatches will).\n` +
      `· Research missions are blocked unless you explicitly authorize unattended access.\n` +
      `· Every tool call they make will be logged to Receipts.\n` +
      `· Their actions will pause for your approval before executing.\n\n` +
      `Continue?`
    )) return;
    onHire({
      id: MOCK.uid('a'),
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
                const missing = (MOCK.OPENSWARM_ROSTER || []).filter(t => !haveNames.has(t.name.toLowerCase()));
                if (!missing.length) return null;
                return (
                  <div
                    className="post-card hire-tile"
                    onClick={() => {
                      if (!window.confirm(`Hire ${missing.length} openswarm-style specialist${missing.length === 1 ? '' : 's'}: ${missing.map(t => t.name).join(', ')}?`)) return;
                      MOCK.spawnOpenswarmRoster(currentAgents, onHire);
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
                {MOCK.ROLES.map(r => <option key={r}>{r}</option>)}
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
                {MOCK.TOOLS_CATALOG.map(t => (
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
                {MOCK.AGENT_COLORS.map(c => (
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
                    Backed by an elevated CafresoAI session that can read/write files and run shell commands on this machine. DMs blocked, missions opt-in, every action logged.
                  </span>
                </span>
              </label>
            </div>
          </div>
          )}
    </Modal>
  );
}

function SettingsModal({ open, onClose, agents, onDismiss, onUpdateAgent, scanlines, setScanlines, sound, setSound, night, setNight }) {
  const [tab, setTab] = useStateM('agents');
  const [selected, setSelected] = useStateM(agents[0]?.id || null);
  const sel = agents.find(a => a.id === selected) || agents[0];

  if (!open) return null;

  const update = (patch) => {
    if (!sel) return;
    onUpdateAgent(sel.id, patch);
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
          <div className="settings-tabs" style={{display:'flex',gap:4,marginBottom:14,flexWrap:'wrap'}}>
            {[
              ['agents', '👥', 'PER-AGENT'],
              ['global', '🎛', 'GLOBAL'],
              ['media',  '🎨', 'MEDIA'],
              ['keys',   '🔌', 'CONNECTIONS'],
            ].map(([t, ico, label]) => (
              <button key={t} className={`px-btn ${tab===t?'primary':'secondary'}`}
                style={{fontSize:9, display:'flex', alignItems:'center', gap:6, padding:'8px 12px', minHeight:36}}
                onClick={()=>setTab(t)}>
                <span style={{fontSize:13}}>{ico}</span> {label}
              </button>
            ))}
          </div>

          {tab === 'agents' && (
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
                        {MOCK.TOOLS_CATALOG.map(t => (
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
                            `They will be backed by an elevated CafresoAI session that can read/write files and run shell commands on this machine. ` +
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

          {tab === 'global' && (
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
              </div>
              <div className="cb-panel">
                <h4>DEFAULTS</h4>
                <div className="row-knob">
                  <div><div className="lbl">Default model</div><div className="sub">new hires inherit this</div></div>
                  <span className="tiny" style={{maxWidth:200,textAlign:'right'}}>set via the Hire modal</span>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">Activity feed</div><div className="sub">break-room bulletin</div></div>
                  <div className="pxswitch on"><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">Auto-delegate</div><div className="sub">CafresoAI picks the best hire</div></div>
                  <div className="pxswitch on"><div className="nub"/></div>
                </div>
              </div>
            </div>
          )}

          {tab === 'media' && <MediaTab />}
          {tab === 'keys' && <ApiTab />}
    </Modal>
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

function ApiTab() {
  const C = window.OpenclawClient;
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

  useEffectM(() => {
    if (s.provider === 'lmstudio') {
      window.OpenclawClient.listLMStudioModels().then(setLmModels).catch(() => setLmModels([]));
    } else if (s.provider === 'ollama') {
      window.OpenclawClient.listOllamaModels().then(ms => setOlModels(ms.map(m => m.name))).catch(() => setOlModels([]));
    }
  }, [s.provider, s.lmstudioUrl, s.ollamaUrl]);

  const runProbe = async () => {
    setProbing(true); setProbeResult(null);
    try {
      const r = await window.OpenclawClient.probe();
      setProbeResult(r);
      if (s.provider === 'lmstudio') {
        setLmModels(await window.OpenclawClient.listLMStudioModels());
      } else if (s.provider === 'ollama') {
        const ms = await window.OpenclawClient.listOllamaModels();
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
          <div><div className="lbl">Backend</div><div className="sub">which brain powers CafresoAI & crew</div></div>
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
                    onClick={() => update({ subagentModel: window.OpenclawClient.getSettings().anthropicModel ? 'anthropic:' + window.OpenclawClient.getSettings().anthropicModel : 'inherit' })}>
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
              {window.OpenclawClient.ANTHROPIC_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
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
              {window.OpenclawClient.GEMINI_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
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
      const st = await window.OpenclawClient.claudecodeStatus();
      setStatus(st);
      if (!draft) setDraft(st.override || '');
    } catch (_e) {}
  };
  useEffectM(() => { refresh(); }, []);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await window.OpenclawClient.claudecodeConfigure(draft.trim());
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
        instead of API credits. Tool use inside Claude Code is disabled so CafresoAI's own
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
          {window.OpenclawClient.CLAUDECODE_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="row-knob">
        <div><div className="lbl">Save override</div><div className="sub">stored in the proxy's memory; re-set on restart unless OPENCLAW_CLAUDE_BIN env var</div></div>
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
      const st = await window.OpenclawClient.codexStatus();
      setStatus(st);
      if (!draft) setDraft(st.override || '');
    } catch (_e) {}
  };
  useEffectM(() => { refresh(); }, []);

  const save = async () => {
    setBusy(true); setMsg(null);
    try {
      await window.OpenclawClient.codexConfigure(draft.trim());
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
              invalid OPENCLAW_ALLOWED_DIRS: {status.badDirs.join(', ')}
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
          {window.OpenclawClient.CODEX_MODELS.map(m => <option key={m} value={m}>{m}</option>)}
        </select>
      </div>
      <div className="row-knob">
        <div><div className="lbl">Save override</div><div className="sub">stored in the proxy's memory; re-set on restart unless OPENCLAW_CODEX_BIN env var</div></div>
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
      const s = await window.OpenclawClient.vaultStatus();
      setStatus({ ...s, unavailable: false, error: '' });
      setDraftRoot(s.root || '');
      setDraftUrl(s.restUrl || '');
      // We never get the actual key back from the server; only the masked sentinel.
      if (!draftKey) setDraftKey('');
      if (s.configured) {
        try { setFiles(await window.OpenclawClient.vaultList()); } catch (_e) { setFiles(null); }
      } else { setFiles(null); }
    } catch (e) {
      const message = e.message || 'CafresoAI bridge is not reachable.';
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
      await window.OpenclawClient.vaultConfigure({ backend });
      window.MOCK.clearVaultReadyCache();
      await refresh();
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const saveFs = async () => {
    const root = cleanLocalRoot(draftRoot);
    setBusy(true); setMsg(null);
    try {
      await window.OpenclawClient.vaultConfigure({ backend: 'fs', root });
      window.MOCK.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: root ? 'configured' : 'cleared' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const useOpenclawVault = async () => {
    const root = status.defaultRoot || draftRoot.trim();
    if (!root) return;
    setBusy(true); setMsg(null);
    try {
      setDraftRoot(root);
      await window.OpenclawClient.vaultConfigure({ backend: 'fs', root });
      window.MOCK.clearVaultReadyCache();
      await refresh();
      setMsg({ ok: true, text: 'using CafresoAI vault' });
    } catch (e) { setMsg({ ok: false, text: e.message }); }
    setBusy(false);
  };

  const detectObsidianVault = async () => {
    setBusy(true); setMsg(null);
    try {
      const found = await window.OpenclawClient.vaultDiscover();
      const vaults = found.vaults || [];
      const pick = vaults.find(v => v.exists) || vaults[0];
      if (!pick) {
        setMsg({ ok: false, text: 'no Obsidian vaults found' });
      } else if (!pick.exists) {
        setMsg({ ok: false, text: `found ${pick.name}, but path is missing` });
      } else {
        setDraftRoot(pick.path);
        await window.OpenclawClient.vaultConfigure({ backend: 'fs', root: pick.path });
        window.MOCK.clearVaultReadyCache();
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
      await window.OpenclawClient.vaultConfigure(patch);
      setDraftKey(''); // clear the in-memory draft so we don't redisplay
      window.MOCK.clearVaultReadyCache();
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
        <div><div className="lbl">Storage</div><div className="sub">CafresoAI works with a plain Markdown folder; Obsidian is optional</div></div>
        <div style={{display:'flex',gap:6}}>
          <button className={`px-btn ${!isRest?'primary':'secondary'}`} style={{fontSize:9}} onClick={()=>setBackend('fs')} disabled={busy}>LOCAL DIRECTORY</button>
          <button className={`px-btn ${isRest?'primary':'secondary'}`} style={{fontSize:9}} onClick={()=>setBackend('rest')} disabled={busy}>OBSIDIAN REST</button>
        </div>
      </div>

      {!isRest && (<>
        <div className="form-row" style={{marginBottom:8,marginTop:6}}>
          <label>VAULT DIRECTORY</label>
          <input placeholder={status.defaultRoot || 'C:/Users/you/Documents/openclawhq/hq-state/vault'}
            value={draftRoot} onChange={e=>setDraftRoot(e.target.value)}/>
          <span className="hint">absolute path to a Markdown folder; the default lives inside OpenclawHQ under <code>hq-state/vault</code></span>
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
            <button className="px-btn secondary" style={{fontSize:9}} onClick={useOpenclawVault} disabled={busy}>{busy ? '...' : 'USE APP VAULT'}</button>
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
        Tip: pass <code>OPENCLAW_VAULT</code> to override the app vault, or <code>OPENCLAW_OBSIDIAN_URL</code> / <code>OPENCLAW_OBSIDIAN_KEY</code> for optional Obsidian REST.
      </div>
    </div>
  );
}

function BraveTab({ s, update }) {
  const [probing, setProbing] = useStateM(false);
  const [result, setResult] = useStateM(null);
  const test = async () => {
    setProbing(true); setResult(null);
    try { setResult(await window.OpenclawClient.braveProbe()); }
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

  if (!open) return null;

  const inboxTasks = tasks.filter(t => t.status !== 'done' && !steps.includes(t.id));
  const addStep = (taskId) => setSteps(s => [...s, taskId]);
  const removeStep = (taskId) => setSteps(s => s.filter(id => id !== taskId));
  const moveUp = (i) => { if (i === 0) return; const s = [...steps]; [s[i-1], s[i]] = [s[i], s[i-1]]; setSteps(s); };

  const submit = () => {
    if (!name.trim() || steps.length < 2) return;
    const wfId = MOCK.uid('wf');
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
      const pre = (typeof window !== 'undefined') ? window._openclawMeetingPrefill : null;
      if (pre && pre.name) {
        setName(pre.name);
        setTopic(pre.topic || '');
        setSelectedIds(Array.isArray(pre.agentIds) ? pre.agentIds : []);
        try { delete window._openclawMeetingPrefill; } catch (_) { window._openclawMeetingPrefill = null; }
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
   communication refactor). Reads from window.OpenclawMessages which is
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
      const v = sessionStorage.getItem('openclaw:inbox-filter');
      if (v) {
        sessionStorage.removeItem('openclaw:inbox-filter');
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
  const reg = window.OpenclawMessages;
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

window.OpenclawModals = { Modal, HireModal, SettingsModal, WorkflowModal, MeetingRoomModal, InboxModal };
