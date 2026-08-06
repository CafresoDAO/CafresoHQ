import { CafresoHQV2 } from '../features.jsx';
import { Sprite } from '../sprites.jsx';
import { xpStats } from '../app/experience.jsx';
import { brainName } from '../app/cast.jsx';
/* ==========================================================================
   CafresoHQ — main-area views (one per sidebar item)
   The Office cross-section stays in app.jsx; everything else lives here.
   ========================================================================== */

const { useState: useSV, useMemo: useMV, useRef: useRV } = React;

/* Persistent React state — backed by localStorage with debounced writes.
   Used by TerminalSession to keep msgs/model/authMethod alive across
   project switches and reloads so the orchestrator context survives. */
function useStoredV(key, initial, persistTransform) {
  const [v, set] = React.useState(() => {
    const fallback = () => (typeof initial === 'function' ? initial() : initial);
    if (!key) return fallback();
    try {
      const raw = localStorage.getItem(key);
      if (raw == null) return fallback();
      const parsed = JSON.parse(raw);
      /* Same shape guard as app.jsx's useStored: "null"/schema-drifted
         values parse fine and then crash the first .map — fall back. */
      const base = fallback();
      if (base != null) {
        if (Array.isArray(base) ? !Array.isArray(parsed)
          : typeof base === 'object' ? (parsed == null || typeof parsed !== 'object' || Array.isArray(parsed))
          : typeof parsed !== typeof base) return base;
      }
      return parsed;
    } catch (_e) { return fallback(); }
  });
  const timer = React.useRef(null);
  React.useEffect(() => {
    if (!key) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      try { localStorage.setItem(key, JSON.stringify(persistTransform ? persistTransform(v) : v)); }
      catch (_e) { /* quota exceeded, etc */ }
    }, 250);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [key, v]);
  return [v, set];
}

function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!result) return null;
  return {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16),
  };
}
const { TaskBoard } = CafresoHQV2;

const VIEW_LABELS = {
  visual:    'AGENT OFFICE',
  tasks:     'TASKS',
  memory:    'MEMORY SHELF',
  vault:     'MARKDOWN VAULT',
  graph:     'VAULT GRAPH',
  team:      'STAFF ROSTER',
  calendar:  'CALENDAR',
  projects:  'WORKSPACE',
  terminal:  'TERMINAL',
};

/* ---------------- Tasks (full board with filter + search) ---------------- */
function TasksView({ tasks, agents, onAdd, onMove, onDelete, onDropTaskOnAgent, onAssign, onAssignToChat, onMakeRoomFromTask, experience = [] }) {
  const [q, setQ] = useSV('');
  const [showDone, setShowDone] = useSV(true);

  const filtered = useMV(() => {
    const needle = q.trim().toLowerCase();
    return tasks.filter(t => {
      if (!showDone && t.status === 'done') return false;
      if (!needle) return true;
      return (t.title + ' ' + (t.detail || '')).toLowerCase().includes(needle);
    });
  }, [tasks, q, showDone]);

  return (
    <div className="view-tasks">
      <div className="section-title">
        📋 ALL TASKS
        <span className="tag">{filtered.length} of {tasks.length} · click → CHAT to fan out, 📋 ROOM to open a meeting</span>
      </div>
      <div className="view-toolbar">
        <input className="view-search" placeholder="Search tasks…" value={q} onChange={e=>setQ(e.target.value)} />
        <label className="view-check">
          <input type="checkbox" checked={showDone} onChange={e=>setShowDone(e.target.checked)} />
          show completed
        </label>
      </div>
      <TaskBoard tasks={filtered} agents={agents}
        onAdd={onAdd} onMove={onMove} onDelete={onDelete}
        onAssign={onAssign}
        onAssignToChat={onAssignToChat}
        onMakeRoomFromTask={onMakeRoomFromTask}
        experience={experience}
      />
    </div>
  );
}

/* ---------------- Memory shelf as a full page ---------------- */
function MemoryPage({ memory, onAdd, onRemove, onPin }) {
  const [text, setText] = useSV('');
  const [tag, setTag] = useSV('NOTE');
  const [filter, setFilter] = useSV('ALL');
  const tags = ['ALL','NOTE','PREF','PROJECT','PEOPLE','RULE','TONE'];
  const filtered = filter === 'ALL' ? memory : memory.filter(m => m.tag === filter);

  const submit = () => {
    if (!text.trim()) return;
    onAdd({ id: 'mem_'+Math.random().toString(36).slice(2,6), tag, text: text.trim(), date: 'Today' });
    setText('');
  };

  return (
    <div className="view-memory">
      <div className="section-title">
        📁 LONG-TERM MEMORY
        <span className="tag">{memory.length} entries · folded into every prompt CafresoHQ and the team see</span>
      </div>
      <div className="view-toolbar">
        <div className="memtag-row">
          {tags.map(t => (
            <button key={t} className={`px-btn ${filter===t?'primary':'secondary'}`} style={{fontSize:8}} onClick={()=>setFilter(t)}>{t}</button>
          ))}
        </div>
      </div>
      <div className="memshelf shelf-page">
        {memory.length === 0 ? (
          <div className="empty-state onboard">
            <div className="empty-title">🧠 Teach your HQ</div>
            <div className="empty-sub">
              Long-term memory is folded into every prompt your CEO and crew see — facts,
              preferences, rules, people. Add your first note below and the team remembers it forever.
            </div>
            <div className="empty-cta-hint">↓ start typing in the box below</div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="muted" style={{padding:16}}>No entries tagged {filter}. Pick another tag above, or add one below.</div>
        ) : null}
        {filtered.map(m => (
          <div key={m.id} className="memrow">
            <span className={`memtag tag-${m.tag.toLowerCase()}`}>{m.tag}</span>
            <div className="memtext">{m.text}</div>
            <div className="memdate">{m.date}</div>
            {onPin && <button className="px-btn ghost" style={{fontSize:8,padding:'4px 6px'}} title="Pin to corkboard" onClick={()=>onPin({ kind:'memory', text: `[${m.tag}] ${m.text}`, sourceId: m.id })}>📌</button>}
            <button className="px-btn ghost" style={{fontSize:8,padding:'4px 6px'}} onClick={()=>onRemove(m.id)}>✕</button>
          </div>
        ))}
      </div>
      <div className="mem-add">
        <select value={tag} onChange={e=>setTag(e.target.value)}>
          {['NOTE','PREF','PROJECT','PEOPLE','RULE','TONE'].map(t => <option key={t}>{t}</option>)}
        </select>
        <input value={text} onChange={e=>setText(e.target.value)} placeholder="New memory entry…" onKeyDown={e=>e.key==='Enter'&&submit()} />
        <button className="px-btn primary" style={{fontSize:9}} onClick={submit}>+ REMEMBER</button>
      </div>
    </div>
  );
}

/* ---------------- Team grid ---------------- */
/* AgentInbox — per-agent activity stream collected from cafresohq:agentActivity
   events fired by the agent_runner shim. Listens globally and groups by agent.
   Shows the most recent ~50 events per agent. Click a row → fires
   cafresohq:openNote so the vault opens that note in the active view.
   Optionally filterable to a single agent (when selectedAgentId is set). */
/* Action → icon for the inbox rows. */
const ACT_ICON = {
  hired: '✦', assigned: '📋', dm: '✉', tool: '⚙', progress: '…',
  done: '✓', failed: '⚠', attention: '⚠', coffee: '☕', meeting: '👥', vault: '✎',
};

/* AgentInbox — the two-layer activity feed. Reads the canonical `activity` log
   (passed as a prop; app.jsx is the single source of truth — no own listener).
   Tabs split routine flow from items that NEED THE USER and from completions;
   each row drills down to its detail + jump links. */
function AgentInbox({ agents, activity = [], selectedAgentId, onSelectAgent, onOpenTasks, onMarkRead, approvals = [], onApprove, onReject, onRetry }) {
  const [tab, setTab] = useSV('attention');   // 'attention' | 'all' | 'done'
  const [expandedId, setExpandedId] = useSV(null);

  const fmtAgo = (ts) => {
    const dt = Date.now() - ts;
    if (dt < 60_000)    return Math.max(0, Math.floor(dt / 1000)) + 's';
    if (dt < 3_600_000) return Math.floor(dt / 60_000) + 'm';
    if (dt < 86_400_000) return Math.floor(dt / 3_600_000) + 'h';
    return Math.floor(dt / 86_400_000) + 'd';
  };

  // Pending approvals are LIVE-actionable (resolve via onApprove/onReject) and
  // belong at the top of the attention tab — distinct from the historical
  // attention activity rows below them.
  const pendingApprovals = React.useMemo(
    () => (approvals || []).filter(p => !selectedAgentId || p.agentId === selectedAgentId),
    [approvals, selectedAgentId]);
  const attentionCount = React.useMemo(
    () => activity.filter(e => e.priority === 'attention' && e.unread).length + pendingApprovals.length,
    [activity, pendingApprovals]);
  const doneCount = React.useMemo(
    () => activity.filter(e => e.action === 'done').length, [activity]);

  const counts = React.useMemo(() => {
    const c = new Map();
    for (const e of activity) c.set(e.agentId, (c.get(e.agentId) || 0) + 1);
    return c;
  }, [activity]);

  const filtered = React.useMemo(() => {
    let xs = activity;
    if (selectedAgentId) xs = xs.filter(e => e.agentId === selectedAgentId);
    if (tab === 'attention') xs = xs.filter(e => e.priority === 'attention');
    else if (tab === 'done') xs = xs.filter(e => e.action === 'done');
    return xs;
  }, [activity, selectedAgentId, tab]);

  const toggle = (e) => {
    setExpandedId(prev => prev === e.id ? null : e.id);
    if (e.priority === 'attention' && e.unread && onMarkRead) onMarkRead(e.id);
    if (e.action === 'vault' && e.nodeId)
      window.dispatchEvent(new CustomEvent('cafresohq:openNote', { detail: { path: e.nodeId } }));
  };
  const openChat = () => {
    if (window.cafresohqSetChatOpen) window.cafresohqSetChatOpen(true);
  };

  const TABS = [
    ['attention', `Needs attention${attentionCount ? ' · ' + attentionCount : ''}`],
    ['all', 'Activity'],
    ['done', `Done${doneCount ? ' · ' + doneCount : ''}`],
  ];

  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      height: '100%', minHeight: 0,
      borderLeft: '2px solid var(--ink)',
      background: 'var(--paper)',
    }}>
      <div className="proj-section-head" style={{display:'flex', alignItems:'center', gap:'var(--sp-3)'}}>
        <span style={{flex:1}}>📥 AGENT INBOX</span>
        <span style={{fontSize:'var(--text-9)', opacity:0.7}}>{activity.length} event{activity.length===1?'':'s'}</span>
      </div>

      {/* Two-layer tabs */}
      <div className="oc-inbox-tabs">
        {TABS.map(([id, label]) => (
          <button key={id}
            className={'oc-inbox-tab' + (tab === id ? ' is-active' : '') + (id === 'attention' && attentionCount ? ' has-attn' : '')}
            onClick={() => setTab(id)}>{label}</button>
        ))}
      </div>

      {/* Per-agent filter chips */}
      <div style={{
        display:'flex', flexWrap:'wrap', gap:'var(--sp-2)',
        padding:'var(--sp-3) var(--sp-4)',
        borderBottom:'1px solid var(--rule)',
        background:'var(--paper-2)',
      }}>
        <button
          onClick={() => onSelectAgent && onSelectAgent(null)}
          className={'oc-notif-filter' + (!selectedAgentId ? ' is-active' : '')}
        >All</button>
        {agents.map(a => {
          const n = counts.get(a.id) || 0;
          if (n === 0 && a.id !== selectedAgentId) return null;
          return (
            <button
              key={a.id}
              onClick={() => onSelectAgent && onSelectAgent(a.id)}
              className={'oc-notif-filter' + (selectedAgentId === a.id ? ' is-active' : '')}
            >{a.name}{n > 0 ? ` · ${n}` : ''}</button>
          );
        })}
      </div>

      {/* Event stream */}
      <div style={{flex:1, overflowY:'auto'}}>
        {/* Live, actionable approvals — only in the attention tab, pinned on top. */}
        {tab === 'attention' && pendingApprovals.map(ap => (
          <div key={ap.id} className="oc-notif-row is-attn oc-approval-row">
            <span className="oc-notif-icon" style={{color:'var(--brand-banana)'}} aria-hidden="true">🔖</span>
            <div className="oc-notif-body">
              <div className="oc-notif-msg">
                <span style={{fontWeight:600}}>{ap.by || 'agent'}</span> needs a stamp: {ap.title}
              </div>
              <div className="oc-notif-meta"><span>{ap.kind || 'approval'}{ap.elevated ? ' · 🛡 elevated' : ''}</span></div>
              <div className="oc-act-jumps" style={{marginTop:6}}>
                <button className="px-btn primary" style={{fontSize:8}} onClick={() => onApprove && onApprove(ap.id)}>✓ Approve</button>
                <button className="px-btn danger" style={{fontSize:8}} onClick={() => onReject && onReject(ap.id)}>✕ Reject</button>
              </div>
            </div>
          </div>
        ))}
        {filtered.length === 0 && pendingApprovals.length === 0 && (
          <div className="proj-empty-msg">
            {tab === 'attention' ? 'Nothing needs you right now. 🎉' : tab === 'done' ? 'No completed work yet.' : 'No agent activity yet.'}<br/>
            <span style={{fontSize:'var(--text-9)',opacity:0.7}}>
              {tab === 'attention'
                ? 'Failures, blocks, and approval requests surface here.'
                : 'Assign a task or chat with the team and every real action lands here.'}
            </span>
          </div>
        )}
        {filtered.map(e => {
          const attn = e.priority === 'attention';
          const open = expandedId === e.id;
          return (
            <div key={e.id} className={'oc-notif-row' + (attn ? ' is-attn' : '')}
              onClick={() => toggle(e)} role="button" tabIndex={0}
              aria-expanded={open}
              onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle(e); } }}>
              <span className="oc-notif-icon" style={{color: attn ? 'var(--error)' : (e.color || 'var(--ink-3)')}} aria-hidden="true">
                {ACT_ICON[e.action] || '✦'}
              </span>
              <div className="oc-notif-body">
                <div className="oc-notif-msg">
                  <span style={{fontWeight:600}}>{e.agentName || 'HQ'}</span> {e.text}
                </div>
                <div className="oc-notif-meta"><span>{fmtAgo(e.ts)} ago</span></div>
                {open && (e.detail || e.taskId || e.nodeId || e.action === 'failed') && (
                  <div className="oc-act-detail" onClick={ev => ev.stopPropagation()}>
                    {e.detail && <div className="oc-act-detail-body">{e.detail}</div>}
                    <div className="oc-act-jumps">
                      {e.action === 'failed' && onRetry && <button className="px-btn primary" onClick={() => onRetry(e)}>↻ Retry</button>}
                      {e.taskId && onOpenTasks && <button className="px-btn ghost" onClick={onOpenTasks}>Open task board →</button>}
                      {e.nodeId && <button className="px-btn ghost" onClick={() => window.dispatchEvent(new CustomEvent('cafresohq:openNote', { detail: { path: e.nodeId } }))}>Open note →</button>}
                      <button className="px-btn ghost" onClick={openChat}>Open chat →</button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TeamView({ agents, activity = [], experience = [], onHire, onInspect, onDismiss, onShowCEO, onOpenTasks, onMarkRead, approvals = [], onApprove, onReject, onRetry }) {
  const [selectedAgentId, setSelectedAgentId] = useSV(null);
  const [showInbox, setShowInbox] = useSV(false);

  // The office attention pill / nav badge fires this to force the inbox open.
  React.useEffect(() => {
    const open = () => setShowInbox(true);
    window.addEventListener('cafresohq:openAgentInbox', open);
    return () => window.removeEventListener('cafresohq:openAgentInbox', open);
  }, []);

  return (
    <div className="view-team" style={{display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0}}>
      {/* CEO card — first entry in the roster, always visible. Tapping it
          opens the CEOPanel (mini office + arcade + quick actions). This is
          the mobile entry-point since the Rail brand card is hidden there. */}
      {onShowCEO && (
        <div
          className="team-ceo-card"
          role="button"
          tabIndex={0}
          onClick={onShowCEO}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onShowCEO(); } }}
          title="Open the CEO panel"
        >
          <div className="team-ceo-sprite"><Sprite data="cafresohq" scale={3} className="bob"/></div>
          <div className="team-ceo-info">
            <div className="team-ceo-name">CafresoHQ-CEO</div>
            <div className="team-ceo-role">Orchestrator · routes work · 1:1s available</div>
            <div className="team-ceo-meta">
              <span className="team-ceo-chip team-ceo-chip--banana">CEO</span>
              <span className="team-ceo-chip">Office · Pac-Man · Memory · Meeting</span>
            </div>
          </div>
          <div className="team-ceo-arrow" aria-hidden="true">›</div>
        </div>
      )}
      <div className="section-title">
        👥 STAFF ROSTER
        <span className="tag">{agents.length} hired · click to inspect</span>
        <span style={{flex:1}}/>
        <button
          onClick={() => setShowInbox(s => !s)}
          style={{
            fontSize: 'var(--text-10)',
            padding: 'var(--sp-2) var(--sp-3)',
            background: showInbox ? 'var(--brand-banana)' : 'var(--paper)',
            border: '1.5px solid var(--brand-coffee)',
            borderRadius: 8,
            cursor: 'pointer',
            fontFamily: 'inherit', fontWeight: 600,
            color: 'var(--brand-coffee)',
            marginRight: 8,
          }}
          title="Toggle agent activity inbox"
        >📥 INBOX</button>
        <button
          onClick={onHire}
          className="px-btn primary"
          style={{ fontSize: 'var(--text-10)', padding: '6px 12px' }}
          title="Hire a new sub-agent"
        >+ HIRE</button>
      </div>
      <div style={{display: 'flex', flex: 1, minHeight: 0, gap: 0}}>
        <div className="team-grid" style={{flex: 1, minWidth: 0, overflowY: 'auto', alignContent: 'start'}}>
          {agents.map(a => {
            const cost = ((a.tokens||0) * 0.0000015).toFixed(4);
            // Experience (§5): jobs from the ledger, not a.tasksDone — that
            // legacy counter also counted chat replies, which aren't jobs.
            const xp = xpStats(experience, a.id);
            return (
              <div key={a.id} className="team-card" onClick={()=>onInspect(a)}>
                <div className={`status-pill ${a.status}`}>{a.status.toUpperCase()}</div>
                <div className="sprite-box"><Sprite data={a.color} scale={3} className="bob"/></div>
                <div className="name">{a.name}</div>
                <div className="role">{a.role}</div>
                <div className="team-stats">
                  {/* §6, binding: no raw model ids and no "tokens"/"cost" on
                      a coworker card — brain · work done · payroll. The id
                      stays in the tooltip so debugging doesn't lose it. */}
                  <div><span className="lbl">Brain</span><span className="val" title={a.model || 'no brain assigned'}>{brainName(a)}</span></div>
                  <div><span className="lbl">Work done</span><span className="val">{(a.tokens||0).toLocaleString()}</span></div>
                  <div><span className="lbl">Payroll</span><span className="val">${cost}</span></div>
                  <div><span className="lbl">Jobs</span><span className="val">{xp.jobs}{xp.streak >= 3 ? ' 🔥' : ''}</span></div>
                </div>
                <div className="team-tools">
                  {(a.tools||[]).map(t => <span key={t}>{t}</span>)}
                </div>
                <button
                  className="px-btn ghost team-inbox-btn"
                  style={{fontSize: 'var(--text-9)', position: 'absolute', top: 6, right: 6}}
                  onClick={(e)=>{ e.stopPropagation(); setShowInbox(true); setSelectedAgentId(a.id); }}
                  title="Show this agent's activity"
                >📥</button>
                <button className="px-btn danger team-dismiss" style={{fontSize:8}} onClick={(e)=>{e.stopPropagation(); onDismiss(a.id);}}>LET GO</button>
              </div>
            );
          })}
          <div className="team-card hire-tile" onClick={onHire}>
            <div className="plus">+<br/>HIRE</div>
          </div>
        </div>
        {showInbox && (
          <div style={{width: 360, flexShrink: 0, display: 'flex'}}>
            <AgentInbox
              agents={agents}
              activity={activity}
              selectedAgentId={selectedAgentId}
              onSelectAgent={setSelectedAgentId}
              onOpenTasks={onOpenTasks}
              onMarkRead={onMarkRead}
              approvals={approvals}
              onApprove={onApprove}
              onReject={onReject}
              onRetry={onRetry}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- Calendar (tasks grouped by createdAt date) ---------------- */
function CalendarView({ tasks, agents }) {
  const groups = useMV(() => {
    const out = new Map();
    for (const t of tasks) {
      const d = new Date(t.createdAt || Date.now());
      const key = d.toISOString().slice(0,10);
      if (!out.has(key)) out.set(key, []);
      out.get(key).push(t);
    }
    return [...out.entries()].sort((a,b) => b[0].localeCompare(a[0]));
  }, [tasks]);

  const fmt = (k) => {
    const d = new Date(k + 'T12:00:00');
    const today = new Date().toISOString().slice(0,10);
    if (k === today) return 'Today';
    return d.toLocaleDateString(undefined, { weekday:'short', month:'short', day:'numeric' });
  };

  return (
    <div className="view-calendar">
      <div className="section-title">
        🗓 CALENDAR
        <span className="tag">tasks grouped by created date · scheduling coming with stand-up</span>
      </div>
      {groups.length === 0 && (
        <div className="empty-state onboard">
          <div className="empty-title">🗓 Nothing on the calendar yet</div>
          <div className="empty-sub">
            This is a live mirror of your task board, grouped by day. Add a task in the
            <strong> Tasks</strong> tab (or drop one on an agent's desk in the office) and it shows up here.
          </div>
        </div>
      )}
      {groups.map(([day, ts]) => (
        <div key={day} className="cal-day">
          <div className="cal-day-head">{fmt(day)}<span className="cal-count">{ts.length}</span></div>
          <div className="cal-day-body">
            {ts.map(t => {
              const a = agents.find(x => x.id === t.assignedTo);
              return (
                <div key={t.id} className={`cal-item status-${t.status}`}>
                  <div className="cal-time">{new Date(t.createdAt).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'})}</div>
                  <div className="cal-title">{t.title}</div>
                  <div className="cal-meta">
                    {a ? <><Sprite data={a.color} scale={1}/> {a.name}</> : <span className="muted">unassigned</span>}
                    <span className={`pri pri-${t.priority||'med'}`}>{(t.priority||'med').toUpperCase()}</span>
                    <span className={`status-pill ${t.status}`}>{t.status.toUpperCase()}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------------- Obsidian-style folder tree ---------------- */
/* Build a nested tree from a flat list of {path, title} entries. Folders
   sort first (alphabetical), files after (alphabetical). */
function buildTree(files) {
  const root = { name: '', path: '', children: new Map(), isFolder: true };
  for (const f of files) {
    const parts = (f.path || '').split('/').filter(Boolean);
    let node = root;
    for (let i = 0; i < parts.length; i++) {
      const isLast = i === parts.length - 1;
      const seg = parts[i];
      if (isLast) {
        node.children.set(seg, { name: seg, path: f.path, title: f.title || seg.replace(/\.md$/, ''), mtime: f.mtime, size: f.size, isFolder: false });
      } else {
        if (!node.children.has(seg)) {
          const folderPath = parts.slice(0, i + 1).join('/');
          node.children.set(seg, { name: seg, path: folderPath, children: new Map(), isFolder: true });
        }
        node = node.children.get(seg);
      }
    }
  }
  // Convert maps to sorted arrays.
  const sortNode = (n) => {
    if (!n.isFolder) return n;
    const kids = [...n.children.values()].map(sortNode);
    kids.sort((a, b) => {
      if (a.isFolder !== b.isFolder) return a.isFolder ? -1 : 1;
      return a.name.localeCompare(b.name);
    });
    return { ...n, children: kids };
  };
  return sortNode(root).children;
}

function FolderTree({ files, openPath, onOpen, expanded, setExpanded }) {
  const tree = useMV(() => buildTree(files), [files]);
  const toggle = (path) => setExpanded(prev => {
    const next = new Set(prev);
    if (next.has(path)) next.delete(path); else next.add(path);
    return next;
  });
  const renderNode = (n, depth) => {
    if (n.isFolder) {
      const isOpen = expanded.has(n.path);
      return (
        <div key={n.path}>
          <div className={`tree-row tree-folder ${isOpen?'open':''}`} style={{paddingLeft: 6 + depth * 14}} onClick={()=>toggle(n.path)}>
            <span className="tree-chev">{isOpen ? '▾' : '▸'}</span>
            <span className="tree-icon">{isOpen ? '📂' : '📁'}</span>
            <span className="tree-name">{n.name}</span>
          </div>
          {isOpen && n.children.map(c => renderNode(c, depth + 1))}
        </div>
      );
    }
    const isBase = /\.base$/i.test(n.name);
    const display = n.name.replace(/\.md$/i, '');
    return (
      <div key={n.path}
        className={`tree-row tree-file ${openPath === n.path ? 'active' : ''}`}
        style={{paddingLeft: 6 + depth * 14 + 14}}
        onClick={()=>onOpen(n.path)}>
        <span className="tree-name">{display}</span>
        {isBase && <span className="tree-tag">BASE</span>}
      </div>
    );
  };
  return (
    <div className="tree-root">
      {tree.map(c => renderNode(c, 0))}
    </div>
  );
}

/* ---------------- Obsidian Vault — unified Vault + Graph tab ---------------- */

export { CalendarView, FolderTree, MemoryPage, TasksView, TeamView, VIEW_LABELS, hexToRgb, useStoredV };
