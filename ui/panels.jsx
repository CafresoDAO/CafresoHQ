import { SPRITES, Sprite } from '../sprites.jsx';
import { Ico } from './primitives.jsx';
import { xpAffinityText, xpStats, XP_HOT_STREAK } from '../app/experience.jsx';
import { brainName, CAN_USE_OFF_TIP, CAN_USE_TIP, EFFORT_TIP, grantedTools, OFFICE_EFFORT_TIP, poweredBy, specialtyTag, statBars, payrollLabel } from '../app/cast.jsx';
import { HQ } from '../hq-runtime.jsx';
import { officeDate } from '../app/artifacts.jsx';
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
  /* A workflow step held because the step before it did not deliver. Its
     own glyph rather than the '✦' fallback: this is the only row in the
     feed about a task nobody is working on, and the chain is the reason.
     The twin of this map lives in views/core.jsx and must gain the same
     entry — see the note there. */
  blocked: '⛓', mission: '🔬',
};
function InspectPanel({ agent, activity = [], experience = [], onClose, onUpdate, onDismiss, onMessage, onFurnish, onCoffee }) {
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
  /* The cast (§2): vendor chip + four honest class bars + one specialty
     line (earned affinity beats the class hunch). */
  const vendor = poweredBy(agent);
  const bars = statBars(agent);
  const tagLine = specialtyTag(agent, specialty);
  /* Job description = the persona, editable in place (§2). It IS the system
     prompt — we just never call it that (§6). Draft state so a half-typed
     edit never saves on re-render; commit on blur. */
  const [jd, setJd] = React.useState(null);
  React.useEffect(() => { setJd(null); }, [agent.id]);
  /* What we last COMMITTED, and for whom. `agent` is a FROZEN snapshot —
     app.jsx keeps the inspected coworker in its own state and `onUpdate`
     rebuilds the roster immutably, so the object this panel holds still
     carries the OLD systemPrompt after a save. Falling back to it meant the
     textarea snapped back to the previous job description one render after
     the toast said it had been updated: the boss watched their edit vanish
     and was told it was saved. Keyed by agent.id so a save on one coworker
     can never surface on the next one the panel is pointed at. */
  const savedJd = React.useRef(null);
  const jdOnFile = (savedJd.current && savedJd.current.id === agent.id)
    ? savedJd.current.text : (agent.systemPrompt || '');
  const jdValue = jd !== null ? jd : jdOnFile;
  const saveJd = () => {
    if (jd === null || jd === jdOnFile) { setJd(null); return; }
    onUpdate(agent.id, { systemPrompt: jd });
    savedJd.current = { id: agent.id, text: jd };
    setJd(null);
    if (window.cafresohqToast) window.cafresohqToast.success(`${agent.name}'s job description updated`);
  };
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
            <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)'}}>
              {agent.role}
              {vendor && <span className="powered-chip" title="Who runs the model — the coworker is yours; the vendor is just the engine">powered by {vendor}</span>}
            </div>
          </div>
          <div className={`mood ${agent.mood||'idle'}`} style={{position:'static'}}>{(agent.mood||'idle')[0].toUpperCase()}</div>
        </div>
        {agent.elevated && (
          <div className="elevated-banner">
            🛡 <b>FILE & SHELL ACCESS</b> — backed by a CafresoHQ / Codex session with computer access. Every tool call is logged to Receipts.
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
        {/* §6 is binding: never "tokens", never "cost" here — "work done ·
            payroll". Same numbers, office words. Renaming Cost → Payroll
            also un-collides it with the Cost stat-bar two rows down, which
            means something else entirely (value, not spend). */}
        {/* Same number, same word as the roster card — see the note there
            on why "Work done" was the wrong name for it. */}
        <div className="stat"><span className="lbl">Effort</span>
          <span title={EFFORT_TIP}>{agent.tokens?.toLocaleString() || '0'}</span></div>
        <div className="stat"><span className="lbl">Payroll</span>
          <span title={payrollLabel(agent).title}>{payrollLabel(agent).text}</span></div>
        {/* The cast (§2): four bars, no more — honest class judgements,
            not benchmark cosplay. Cost reads as value (4 = costs nothing).

            The tooltip exists because of WHERE these sit: directly above
            "Jobs completed" and "Current streak", which are earned, counted
            from the experience ledger. Four judgements stacked on two
            measurements, with nothing on screen telling them apart — a boss
            reading down the card would fairly take all six as this
            coworker's record. These four are not. They come from
            `statBars(agent)`, which keys off the BRAIN, so two coworkers on
            the same model show identical bars however differently they have
            performed. Saying so costs one line and settles it. */}
        <div className="stat-bars"
             title="What this brain is typically good at — a judgement about the model they run on, not a measurement of their work. Jobs and streak below are the earned record.">
          {[['Speed', bars.speed], ['Depth', bars.depth], ['Code', bars.code], ['Cost', bars.cost]].map(([lbl, n]) => (
            <div className="stat-bar-row" key={lbl}>
              <span className="sb-lbl">{lbl}</span>
              <span className="sb-track" aria-label={`${lbl}: ${n} of 4`}>
                {[1, 2, 3, 4].map(i => <span key={i} className={'sb-seg' + (i <= n ? ' on' : '')} />)}
              </span>
            </div>
          ))}
        </div>
        <div className="stat"><span className="lbl">Specialty</span><span>{tagLine}</span></div>
        <div className="stat"><span className="lbl">Jobs completed</span><span>{xp.jobs}</span></div>
        {/* Twin of the roster card's Snags row (views/core.jsx) — same
            xpStats() field, same "only when there is one" rule so a clean
            record doesn't get a standing "Snags 0" nobody asked for. This
            panel showed Jobs and streak but never the number that explains
            why a streak reset — the one place a boss reads a coworker's
            whole record was missing the half of it that isn't good news. */}
        {xp.snags > 0 && (
          <div className="stat"><span className="lbl">Snags</span>
            <span title={`${xp.snags} run${xp.snags === 1 ? '' : 's'} came back empty or failed. Runs you stopped yourself are not counted.`}>{xp.snags}</span></div>
        )}
        <div className="stat"><span className="lbl">Current streak</span><span>{xp.streak >= XP_HOT_STREAK ? `${xp.streak} 🔥` : xp.streak}</span></div>
        <div>
          <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)',marginBottom:5}}>
            Job description <span style={{textTransform:'none',letterSpacing:0,opacity:0.7}}>· what they believe their job is — edit it and they'll work to it</span>
          </div>
          <textarea className="jobdesc" rows={4} value={jdValue}
            placeholder={`Describe ${agent.name}'s job in plain words — tone, priorities, what "done" means.`}
            onChange={e => setJd(e.target.value)} onBlur={saveJd} />
        </div>
        {/* The brain, by name — the raw id stays reachable in the tooltip
            for debugging, but §6 keeps it off the card face. */}
        <div className="stat"><span className="lbl">Brain</span>
          {/* Twin of the roster card's Brain row, found by censusing every
              render of `.model` after fixing that one. Same raw id
              (`ollama:llama3.1`) in the same kind of tooltip, on a panel a
              boss opens to read about their coworker. §3.6: no model IDs on
              the front door. */}
          <span title={(() => {
            const v = poweredBy(agent);
            return v ? `Powered by ${v} — the coworker is yours; the vendor is just the engine`
                     : 'Runs on whatever brain you gave them';
          })()}>{brainName(agent)}</span></div>
        {/* Was "Tools used" — past tense, a record — over `agent.tools`,
            which is the permission list. So the card said Llama had USED the
            vault when Llama had never written a thing; enabling Vault Notes
            in Settings changed the "record" of what they had already done.

            Renamed rather than rebuilt: a real used-list is derivable from
            the activity log, but that is a different feature, and the label
            was the part that was lying. */}
        {/* …and it was still a permission list read off the stored CLAIM.
            Renaming fixed the tense; it could not fix the contents. This
            panel showed a freshly hired Dax "FILES VAULT DB" while
            `toolsForAgent` was giving him the vault and nothing else, so the
            list now comes from grantedTools — same tables the candidate
            shelf has used since the front-desk audit. */}
        {(() => {
          const reach = grantedTools(agent.tools, HQ.capabilityFacts(agent));
          if (!reach.granted.length && !reach.locked.length) return null;
          return (
            <div>
              <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)',marginBottom:5}}>Can use</div>
              <div className="tools-used" title={CAN_USE_TIP + (reach.locked.length ? CAN_USE_OFF_TIP : '')}>
                {reach.granted.map(g => <span key={g.id} title={`Can ${g.say}`}>{g.id.toUpperCase()}</span>)}
                {reach.locked.map(l => (
                  <span key={l.id} style={{opacity: 0.45}}
                        title={l.unlock ? `Not yet — ${l.unlock}.` : 'Switched off.'}>{l.id.toUpperCase()} · OFF</span>
                ))}
              </div>
            </div>
          );
        })()}
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
                  <span className="jdate">{e.date || officeDate(new Date(e.at||0))}</span>
                  <span className="jsum">{e.summary}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      {/* Lifted OUT of `.body`, which is now the panel's scroller.

          These three are the only things on this panel that DO anything —
          everything above them is a read. They used to be the last children
          of an unbounded, `position: fixed` panel, which meant that on any
          viewport shorter than the panel's content they rendered past the
          bottom edge with nothing in the ancestor chain able to scroll to
          them. Measured at 375×812: the panel stood 984px tall, 252px of it
          off-screen, and all three buttons were in that 252px —
          `elementFromPoint` at each button's centre returned null. They were
          drawn, labelled, correctly 44px, and untouchable.

          So they are a footer now, not the tail of a list: a boss who opens
          a coworker to stop them should not have to scroll a performance
          review to find the stop. */}
      <div className="inspect-actions">
        {onMessage && <button className="px-btn primary" style={{fontSize:8,flex:1}} onClick={()=>onMessage(agent)}>💬 MESSAGE</button>}
        {/* Was "REFRESH CTX" — §6 bans the context-window vocabulary, and
            the button ALSO did a different thing than the floor's mug: it
            zeroed the counter while leaving an in-flight run streaming.
            Same gesture, same surface, one handler.

            This is also the phone's door to coffee. The floor's mug is
            12×12 and always will be — it is pixel art, and §3.2 makes the
            art load-bearing — so the full-size path to the same handler has
            to exist somewhere a thumb can reach. It is here, one tap from
            the Team roster card, and `scripts/test_coffee_reachable_on_mobile.py`
            holds it here. */}
        <button className="px-btn secondary" style={{fontSize:8,flex:1}}
                title="Stops anything they're running and clears their desk for the next job"
                onClick={()=>(onCoffee ? onCoffee(agent) : onUpdate(agent.id, { tokens: 0, recent: 'back from a coffee break — desk clear' }))}>☕ COFFEE BREAK</button>
        <button className="px-btn danger" style={{fontSize:8}} onClick={()=>{onDismiss(agent.id); onClose();}}>LET GO</button>
      </div>
    </div>
  );
}

/* ------------ Token HUD (persistent) ------------ */
/* `budget` is opt-in on purpose. It used to default to 1,000,000 and no
   caller has ever passed one, so the bar was always measuring against a
   ceiling nobody set — a gauge with no scale, which reads as "you have 96%
   of something left". Given a real budget it draws a real bar; without one
   it shows the work done and no bar at all. */
function TokenHUD({ tokens, budget=null, className='' }) {
  const hasBudget = typeof budget === 'number' && isFinite(budget) && budget > 0;
  const pct = hasBudget ? Math.min(100, (tokens/budget)*100) : 0;
  return (
    /* The dollar figure is gone, and deliberately. It multiplied every
       coworker's tokens by one hardcoded rate, so an office running a free
       local model and a flat-rate CLI hire was shown a bill for money
       nobody was spending. A total across brains that charge differently —
       or not at all — is not a number that exists; the work done is. */
    <div className={`token-hud${className ? ' '+className : ''}`} title={OFFICE_EFFORT_TIP}>
      {/* ⚡, not ⛽. The dollar figure and the budget bar were both removed
          from this HUD as invented numbers, and the fuel PUMP outlived them:
          fuel implies a tank and a level remaining, when this is effort
          already spent and nothing caps it. The Situation Wall shows the
          same number as ⚡ — one number should not wear two icons, and
          certainly not one that argues with its own tooltip. */}
      <span>⚡</span>
      <span>{(tokens/1000).toFixed(1)}K</span>
      {hasBudget && <div className="bar"><div className="fill" style={{width: pct+'%'}}/></div>}
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
            <kbd>H</kbd><span>Hire a coworker</span>
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
      <div className="floppy-btn" title="Keyboard shortcuts" role="button" tabIndex={0}
           aria-label="Keyboard shortcuts" aria-expanded={open}
           onClick={()=>setOpen(!open)}
           onKeyDown={(e)=>{ if (e.key==='Enter'||e.key===' ') { e.preventDefault(); setOpen(!open); } }}/>
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
                 target="_blank" rel="noopener noreferrer"
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
             target="_blank" rel="noopener noreferrer"
             onClick={onClose}>
            <span className="ceo-panel-icon" aria-hidden="true">🕹</span>
            <span>Workspaces</span>
          </a>
        </div>
      </div>
    </div>
  );
}




/* ── Topbar overflow menu ─────────────────────────────────────────────────
   The status strip never fit. Measured at 1400px: it needed 1024px of room
   and got 637, so INBOX · MEMORY · STAND-UP · RESEARCH · MEETING · WORKFLOW
   · DAY/NIGHT always lived partly behind a hidden scroll — at EVERY width,
   not just narrow ones. Pinning the alarms (previous pass) stopped the
   dangerous part; this stops the row being overloaded in the first place.

   Grouping is deterministic — by nature, not by measurement. A
   priority-plus toolbar that re-measures on every resize is a lot of
   machinery to decide something that doesn't actually change: these six are
   room-and-facility launchers, INBOX is attention-bearing and stays out.

   `badge` matters. Folding RESEARCH · MEETING · WORKFLOW behind a menu
   would otherwise HIDE their counts, and hiding live state is the thing
   this whole thread of work exists to stop. The button carries the total
   and every row carries its own. */
function TopbarMenu({ label, title, items, className = '' }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const btnRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      setOpen(false);
      /* Focus goes back where it came from — closing a menu should not
         dump the boss at the top of the document. */
      if (btnRef.current) btnRef.current.focus();
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey); };
  }, [open]);

  const live = items.filter(i => i.count > 0);
  const total = live.reduce((n, i) => n + i.count, 0);

  return (
    <div className={'topbar-menu' + (className ? ' ' + className : '')} ref={ref}>
      <button ref={btnRef} className="px-btn ghost sz-sm topbar-menu-btn"
        aria-haspopup="true" aria-expanded={open ? 'true' : 'false'}
        title={total > 0
          ? `${title} — ${live.map(i => `${i.count} ${i.label.toLowerCase()}`).join(', ')}`
          : title}
        onClick={() => setOpen(v => !v)}>
        {label} ▾{total > 0 ? <span className="topbar-menu-badge">{total}</span> : null}
      </button>
      {open && (
        <div className="topbar-menu-pop" role="menu">
          {items.map(i => (
            <button key={i.key} role="menuitem" className="topbar-menu-item"
              title={i.title || ''}
              onClick={() => { setOpen(false); i.onClick(); }}>
              <span className="tmi-label">{i.label}</span>
              {i.count > 0 ? <span className="tmi-count">{i.count}</span> : null}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export { CEOPanel, InspectPanel, ShortcutHud, Toast, TokenHUD, TopbarMenu };
