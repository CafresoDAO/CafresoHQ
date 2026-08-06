import { SPRITES, Sprite } from '../sprites.jsx';
import { Ico } from './primitives.jsx';
import { xpAffinityText, xpStats } from '../app/experience.jsx';
const { useState, useEffect, useLayoutEffect, useRef, useMemo, createContext, useContext } = React;
const _elevatedStatusCache = { at: 0, data: null };
function ElevatedToolkit() {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const now = Date.now();
    if (_elevatedStatusCache.data && (now - _elevatedStatusCache.at) < 30000) {
      setStatus(_elevatedStatusCache.data);
      return;
    }
    fetch('/codex/status')
      .then(r => r.ok ? r.json() : null)
      .then(j => {
        if (cancelled) return;
        _elevatedStatusCache.at = Date.now();
        _elevatedStatusCache.data = j;
        setStatus(j);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  if (!status) return null;
  const tools = (status.allowedTools || []);
  const dirs = (status.allowedDirs || []);
  return (
    <div className="elevated-toolkit">
      <div className="elevated-toolkit-row">
        <span className="elevated-toolkit-label">TOOLS</span>
        <div className="elevated-toolkit-pills">
          {tools.length === 0
            ? <span className="elevated-toolkit-empty">none</span>
            : tools.map(t => <span key={t} className="elevated-toolkit-pill">{t}</span>)}
        </div>
      </div>
      <div className="elevated-toolkit-row">
        <span className="elevated-toolkit-label">DIRS</span>
        <div className="elevated-toolkit-dirs">
          {dirs.length === 0
            ? <span className="elevated-toolkit-empty">none configured</span>
            : dirs.map(d => <code key={d} className="elevated-toolkit-dir" title={d}>{d.split(/[\\/]/).pop()}</code>)}
        </div>
      </div>
    </div>
  );
}

const INSPECT_ACT_ICON = {
  hired: '✦', assigned: '📋', dm: '✉', tool: '⚙', progress: '…',
  done: '✓', failed: '⚠', attention: '⚠', coffee: '☕', meeting: '👥', vault: '✎',
};
function InspectPanel({ agent, activity = [], experience = [], onClose, onUpdate, onDismiss, onMessage, onFurnish }) {
  if (!agent) return null;
  /* Live activity for THIS agent, straight from the canonical log — replaces
     the old static `agent.recent` string with what the agent actually did. */
  const mine = React.useMemo(
    () => (activity || []).filter(e => e.agentId === agent.id).slice(0, 8),
    [activity, agent.id]);
  /* Experience (§5) — derived from the append-only ledger, not
     agent.tasksDone (which counted chat replies as tasks). */
  const xp = React.useMemo(() => xpStats(experience, agent.id), [experience, agent.id]);
  const specialty = xpAffinityText(xp);
  const ago = (ts) => {
    const dt = Date.now() - (ts || 0);
    if (dt < 60_000) return Math.max(0, Math.floor(dt / 1000)) + 's';
    if (dt < 3_600_000) return Math.floor(dt / 60_000) + 'm';
    if (dt < 86_400_000) return Math.floor(dt / 3_600_000) + 'h';
    return Math.floor(dt / 86_400_000) + 'd';
  };
  return (
    <div className="inspect">
      <div className="head">
        <div>
          <div className="title">{agent.name.toUpperCase()}</div>
          <div className="sub">Performance review</div>
        </div>
        <button className="px-btn ghost" style={{color:'#fff8ee',borderColor:'#fff8ee',fontSize:8}} onClick={onClose}>✕</button>
      </div>
      <div className="body">
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <Sprite data={agent.color} scale={2}/>
          <div style={{flex:1}}>
            <div style={{fontFamily:'Press Start 2P',fontSize:10}}>{agent.elevated ? '🛡 ' : ''}{agent.name}</div>
            <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)'}}>{agent.role}</div>
          </div>
          <div className={`mood ${agent.mood||'idle'}`} style={{position:'static'}}>{(agent.mood||'idle')[0].toUpperCase()}</div>
        </div>
        {agent.elevated && (
          <div className="elevated-banner">
            🛡 <b>ELEVATED</b> — backed by a CafresoHQ / Codex session with computer access. Every tool call is logged to Receipts.
            <ElevatedToolkit />
          </div>
        )}
        {onFurnish && !agent.transient && (
          <button className="px-btn" style={{width:'100%',fontSize:9}}
            onClick={() => onFurnish(agent)}
            title="Buy desk decor with gold (sGLDT) — cosmetic only, always asks before spending">
            🛋 FURNISH DESK · pay in gold
          </button>
        )}
        <div className="stat"><span className="lbl">Tokens (session)</span><span>{agent.tokens?.toLocaleString() || '0'}</span></div>
        <div className="stat"><span className="lbl">Cost</span><span>${((agent.tokens||0)*0.0000015).toFixed(4)}</span></div>
        <div className="stat"><span className="lbl">Jobs completed</span><span>{xp.jobs}</span></div>
        <div className="stat"><span className="lbl">Current streak</span><span>{xp.streak >= 2 ? `${xp.streak} 🔥` : xp.streak}</span></div>
        {specialty && <div className="stat"><span className="lbl">Specialty</span><span>{specialty}</span></div>}
        <div className="stat"><span className="lbl">Model</span><span>{agent.model}</span></div>
        <div>
          <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)',marginBottom:5}}>Tools used</div>
          <div className="tools-used">
            {(agent.tools||[]).map(t => <span key={t}>{t.toUpperCase()}</span>)}
          </div>
        </div>
        <div>
          <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)',marginBottom:5}}>Live activity</div>
          {mine.length > 0 ? (
            <div className="inspect-activity">
              {mine.map(e => (
                <div key={e.id} className={'ia-row' + (e.priority === 'attention' ? ' is-attn' : '')}>
                  <span className="ia-icon" aria-hidden="true">{INSPECT_ACT_ICON[e.action] || '✦'}</span>
                  <span className="ia-text">{e.text}</span>
                  <span className="ia-ago">{ago(e.ts)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="recent">
              {agent.recent || 'No activity logged yet. Drag a task onto this desk or message the team.'}
            </div>
          )}
        </div>
        {agent.journal && agent.journal.length > 0 && (
          <div>
            <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)',marginBottom:5}}>Work journal · last {Math.min(8, agent.journal.length)}</div>
            <div className="journal">
              {agent.journal.slice(0, 8).map((e, i) => (
                <div key={i} className="jrow">
                  <span className="jdate">{e.date || new Date(e.at||0).toISOString().slice(0,10)}</span>
                  <span className="jsum">{e.summary}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div style={{display:'flex',gap:6,marginTop:4}}>
          {onMessage && <button className="px-btn primary" style={{fontSize:8,flex:1}} onClick={()=>onMessage(agent)}>💬 MESSAGE</button>}
          <button className="px-btn secondary" style={{fontSize:8,flex:1}} onClick={()=>onUpdate(agent.id, { tokens: 0, recent: 'context cleared ☕' })}>☕ REFRESH CTX</button>
          <button className="px-btn danger" style={{fontSize:8}} onClick={()=>{onDismiss(agent.id); onClose();}}>LET GO</button>
        </div>
      </div>
    </div>
  );
}

/* ------------ Token HUD (persistent) ------------ */
function TokenHUD({ tokens, budget=1000000, className='' }) {
  const pct = Math.min(100, (tokens/budget)*100);
  return (
    <div className={`token-hud${className ? ' '+className : ''}`} title={`${tokens.toLocaleString()} tokens · $${(tokens*0.0000015).toFixed(2)} est.`}>
      <span>⛽</span>
      <span>{(tokens/1000).toFixed(1)}K</span>
      <div className="bar"><div className="fill" style={{width: pct+'%'}}/></div>
      <span>${(tokens*0.0000015).toFixed(2)}</span>
    </div>
  );
}

/* ------------ Shortcut HUD ------------ */
function ShortcutHud({ open, setOpen }) {
  return (
    <div className="shortcut-hud">
      {open && (
        <div className="shortcut-panel">
          <h5>⌨ SHORTCUTS</h5>
          <div className="kbrow">
            <kbd>⌘K</kbd><span>Toggle shortcuts</span>
            <kbd>H</kbd><span>Hire sub-agent</span>
            <kbd>S</kbd><span>Open settings</span>
            <kbd>M</kbd><span>Memory shelf</span>
            <kbd>N</kbd><span>Add sticky note</span>
            <kbd>U</kbd><span>End-of-day stand-up</span>
            <kbd>F</kbd><span>1:1 with CafresoHQ</span>
            <kbd>D</kbd><span>Day / night</span>
            <kbd>/</kbd><span>Focus chat</span>
          </div>
        </div>
      )}
      <div className="floppy-btn" title="Keyboard shortcuts" onClick={()=>setOpen(!open)}/>
    </div>
  );
}

/* ------------ Toast ------------ */
function Toast({ msg }) {
  if (!msg) return null;
  return <div className="toast"><span className="kw">{msg.kind || 'HQ'}</span><span>{msg.text}</span></div>;
}

/* ──────────────────────────────────────────────────────────────────────
   CEOPanel — modal that opens when the user clicks the CafresoHQ-CEO
   sidebar card. Shows a mini diorama of the CEO office (with a live
   Pac-Man cabinet) plus quick-action buttons (Settings, Sit 1:1,
   Memory, Meeting, Workspaces). Pattern mirrors InspectPanel but with a
   dedicated layout because the orchestrator's view is richer than a
   sub-agent's stat sheet.
   ──────────────────────────────────────────────────────────────────── */
function CEOPanel({ open, onClose, onOpenSettings, onSitWithCEO, onOpenMemory, onOpenMeeting }) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  const fire = (fn) => () => { if (typeof fn === 'function') fn(); onClose(); };
  return (
    <div className="ceo-panel-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="CafresoHQ-CEO panel">
      <div className="ceo-panel" onClick={(e) => e.stopPropagation()}>
        <header className="ceo-panel-head">
          <div className="ceo-panel-identity">
            <Sprite data={SPRITES.cafresohq} scale={2}/>
            <div>
              <div className="ceo-panel-title">CafresoHQ-CEO</div>
              <div className="ceo-panel-sub">Orchestrator · Cafreso HQ</div>
            </div>
          </div>
          <button className="ceo-panel-close" onClick={onClose} aria-label="Close">✕</button>
        </header>
        {/* The .office wrapper scopes pixel-art rendering + Press Start 2P
            font so the mini diorama looks the same as the Office tab. */}
        <div className="ceo-panel-stage office">
          <div className="ceo-panel-room">
            <div className="interior">
              {/* Office furnishings — run first so they sit behind the
                  interactive pieces (corkboard, arcade, desk, etc.). */}
              <div className="ceo-ceiling-light" aria-hidden="true"/>
              <div className="office-carpet" aria-hidden="true"/>
              <div className="wall-photo" title="Cafreso skyline" aria-hidden="true"/>
              <div className="corkboard">📌 pin memory or receipts here</div>
              <div className="window">
                <div className="sun"/>
                <div className="cloud cloud-a"/>
                <div className="cloud cloud-b"/>
              </div>
              <div className="wall-clock" title="Wall clock">
                <span className="wc-hand wc-hour"/>
                <span className="wc-hand wc-min"/>
                <span className="wc-pin"/>
              </div>
              <div className="whiteboard" title="Strategy whiteboard">
                <span className="wb-line">Q3 — SHIP HQ</span>
                <span className="wb-line wb-r">★ ECOSYSTEM</span>
                <span className="wb-line">DAO · CHAIN · AI</span>
              </div>
              <div className="bookshelf" title="Quarterly binders" aria-hidden="true">
                <div className="shelf"><i className="book b1"/><i className="book b2"/><i className="book b3"/><i className="book b4"/><i className="book b5"/></div>
                <div className="shelf"><i className="book b3"/><i className="book b1"/><i className="book b5"/><i className="book b2"/></div>
                <div className="shelf"><i className="book b4"/><i className="book b3"/><i className="book b1"/></div>
              </div>
              <div className="plant"/>
              <div className="coffee-mug" aria-hidden="true"><span className="cm-steam"/></div>
              <div className="desk-keyboard" aria-hidden="true"/>
              <div className="desk-mouse" aria-hidden="true"/>
              <div className="desk-phone" title="Desk phone" aria-hidden="true"/>
              <div className="trash-bin" title="Trash" aria-hidden="true"/>
              <a className="arcade clickable"
                 href="https://ai.cafreso.com/workspaces"
                 title="PAC-MAN · Boot up Cafreso Workspaces"
                 onClick={(e)=>e.stopPropagation()}>
                <span className="arcade-marquee">PAC-MAN</span>
                <span className="arcade-bezel">
                  <span className="arcade-screen">
                    <i className="dot"/><i className="dot"/><i className="dot"/><i className="dot"/>
                    <i className="pac"/>
                    <i className="ghost blinky"/>
                    <i className="ghost pinky"/>
                    <i className="ghost inky"/>
                  </span>
                </span>
                <span className="arcade-coin"/>
                <span className="arcade-controls">
                  <i className="joystick"/>
                  <i className="btn-red"/>
                  <i className="btn-red"/>
                </span>
                <span className="arcade-base"/>
              </a>
              <div className="filing clickable" title="Memory shelf"
                   onClick={fire(onOpenMemory)}>
                <span/><span/><span/>
              </div>
              <div className="guest-chair" title="Sit 1:1 with the CEO"
                   onClick={fire(onSitWithCEO)}/>
              <div className="meeting-door" title="Meeting room"
                   onClick={fire(onOpenMeeting)}/>
              <div className="desk"/>
              <div className="office-chair" aria-hidden="true"/>
              <div className="sprite-slot">
                <Sprite data={SPRITES.cafresohq} scale={1}/>
              </div>
            </div>
          </div>
        </div>
        <div className="ceo-panel-actions">
          <button className="ceo-panel-action" onClick={fire(onOpenSettings)}>
            <span className="ceo-panel-icon"><Ico kind="settings" size={16}/></span>
            <span>Settings</span>
          </button>
          <button className="ceo-panel-action" onClick={fire(onSitWithCEO)}>
            <span className="ceo-panel-icon" aria-hidden="true">☕</span>
            <span>Sit 1:1</span>
          </button>
          <button className="ceo-panel-action" onClick={fire(onOpenMemory)}>
            <span className="ceo-panel-icon" aria-hidden="true">🗂</span>
            <span>Memory</span>
          </button>
          <button className="ceo-panel-action" onClick={fire(onOpenMeeting)}>
            <span className="ceo-panel-icon" aria-hidden="true">🚪</span>
            <span>Meeting</span>
          </button>
          <a className="ceo-panel-action ceo-panel-action--workspaces"
             href="https://ai.cafreso.com/workspaces"
             onClick={onClose}>
            <span className="ceo-panel-icon" aria-hidden="true">🕹</span>
            <span>Workspaces</span>
          </a>
        </div>
      </div>
    </div>
  );
}



export { CEOPanel, InspectPanel, ShortcutHud, Toast, TokenHUD };
