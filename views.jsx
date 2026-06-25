/* ==========================================================================
   CafresoHQ — main-area views (one per sidebar item)
   The Office cross-section stays in app.jsx; everything else lives here.
   ========================================================================== */

const { useState: useSV, useMemo: useMV, useRef: useRV } = React;

/* Persistent React state — backed by localStorage with debounced writes.
   Used by TerminalSession to keep msgs/model/authMethod alive across
   project switches and reloads so the orchestrator context survives. */
function useStoredV(key, initial) {
  const [v, set] = React.useState(() => {
    if (!key) return typeof initial === 'function' ? initial() : initial;
    try {
      const raw = localStorage.getItem(key);
      if (raw == null) return typeof initial === 'function' ? initial() : initial;
      return JSON.parse(raw);
    } catch (_e) { return typeof initial === 'function' ? initial() : initial; }
  });
  const timer = React.useRef(null);
  React.useEffect(() => {
    if (!key) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      try { localStorage.setItem(key, JSON.stringify(v)); }
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
const { TaskBoard } = window.CafresoHQV2;

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
function TasksView({ tasks, agents, onAdd, onMove, onDelete, onDropTaskOnAgent, onAssign, onAssignToChat, onMakeRoomFromTask }) {
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

function TeamView({ agents, activity = [], onHire, onInspect, onDismiss, onShowCEO, onOpenTasks, onMarkRead, approvals = [], onApprove, onReject, onRetry }) {
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
            return (
              <div key={a.id} className="team-card" onClick={()=>onInspect(a)}>
                <div className={`status-pill ${a.status}`}>{a.status.toUpperCase()}</div>
                <div className="sprite-box"><Sprite data={a.color} scale={3} className="bob"/></div>
                <div className="name">{a.name}</div>
                <div className="role">{a.role}</div>
                <div className="team-stats">
                  <div><span className="lbl">Model</span><span className="val">{(a.model||'').replace(/^[a-z]+:/,'') || '—'}</span></div>
                  <div><span className="lbl">Tokens</span><span className="val">{(a.tokens||0).toLocaleString()}</span></div>
                  <div><span className="lbl">Cost</span><span className="val">${cost}</span></div>
                  <div><span className="lbl">Tasks</span><span className="val">{a.tasksDone||0}</span></div>
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
function VaultView({ agents = null, onOpenSettings } = {}) {
  const [status, setStatus] = useSV(null);
  const [files, setFiles] = useSV([]);
  const [q, setQ] = useSV('');
  const [hits, setHits] = useSV(null);
  const [openNote, setOpenNote] = useSV(null);
  const [busy, setBusy] = useSV(false);
  const [err, setErr] = useSV(null);
  const [expanded, setExpanded] = useSV(new Set());
  const [preview, setPreview] = useSV(true);
  const [graphMinimized, setGraphMinimized] = useSV(false);
  const _isMobileV = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;
  const [vaultTab, setVaultTab] = useSV(_isMobileV ? 'graph' : null); // 'tree' | 'graph' | 'editor'

  // ── Bridge mode: when running inside the SvelteKit shell iframe, all vault
  // reads/writes go through window.VaultBridge (postMessage → parent decrypts).
  // Falls back to the local serve.py API when opened standalone.
  const _bridge = typeof window !== 'undefined' && window.VaultBridge?.isAvailable()
    ? window.VaultBridge : null;
  // Map display path → blob id (only populated in bridge mode)
  const _pathToId = useRV({});

  // Helper: adapt bridge file list [{id,name,...}] → [{path,title,id,...}]
  const _adaptBridgeFiles = (bridgeFiles) => {
    const m = {};
    const adapted = (bridgeFiles || []).map(f => {
      m[f.name] = f.id;
      return { ...f, path: f.name, title: f.name.split(/[\\/]/).pop().replace(/\.md$/i, '') };
    });
    _pathToId.current = m;
    return adapted;
  };

  const refresh = async () => {
    setErr(null);
    if (_bridge) {
      try {
        const bridgeFiles = await _bridge.list();
        setFiles(_adaptBridgeFiles(bridgeFiles));
        setStatus({ configured: true, exists: true, name: '🔐 Encrypted Vault', backend: 'bridge' });
      } catch (e) {
        setErr(e.message || 'Could not load vault from shell.');
        setStatus({ configured: false, unavailable: true, error: e.message });
      }
      return;
    }
    try {
      const s = await window.CafresoHQClient.vaultStatus();
      setStatus(s);
      if (!s.configured) { setFiles([]); return; }
      try {
        setFiles(await window.CafresoHQClient.vaultList());
      } catch (e) {
        setFiles([]);
        setErr(e.message || 'Could not list vault notes.');
      }
    } catch (e) {
      const message = e.message || 'CafresoHQ bridge is not reachable.';
      setFiles([]);
      setStatus({ configured: false, unavailable: true, error: message });
      setErr(message);
    }
  };
  React.useEffect(() => { refresh(); }, []);

  // Listen for live vault file updates pushed from the parent shell
  React.useEffect(() => {
    if (!_bridge) return;
    const handler = (e) => {
      if (e.source !== window.parent) return;
      if (e.data?.type === 'vault:files:update') {
        setFiles(_adaptBridgeFiles(e.data.files || []));
        if (!status) setStatus({ configured: true, exists: true, name: '🔐 Encrypted Vault', backend: 'bridge' });
      }
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, []);

  React.useEffect(() => {
    const handler = (e) => { if (e.detail && e.detail.path) openByPath(e.detail.path); };
    window.addEventListener('cafresohq:openNote', handler);
    return () => window.removeEventListener('cafresohq:openNote', handler);
  }, []);

  // Esc closes the open note (so the graph can re-expand to fullspan).
  // Don't fire while typing into inputs/textareas.
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      const t = e.target;
      const tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) return;
      closeNote();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const search = async () => {
    if (!q.trim()) { setHits(null); return; }
    try { setHits(await window.CafresoHQClient.vaultSearch(q.trim())); }
    catch (e) { setErr(e.message); setHits([]); }
  };

  const openByPath = async (path) => {
    if (!path) return;
    // Binary files (images, video, audio) can't open in the text editor
    const fileMeta = files.find(f => f.path === path);
    if (fileMeta?.isBinary) {
      alert(`"${fileMeta.title}" is a binary file.\nDownload it from ai.cafreso.com/vault to view it.`);
      return;
    }
    // Flush any dirty buffer before swapping files — no silent edit loss.
    if (openNoteRef.current && openNoteRef.current.dirty) {
      await saveNoteRef.current({ quiet: true });
    }
    setBusy(true); setErr(null); setSaveState('');
    try {
      let text;
      if (_bridge) {
        const id = _pathToId.current[path];
        if (!id) throw new Error('File not found in vault index: ' + path);
        text = await _bridge.read(id);
      } else {
        text = await window.CafresoHQClient.vaultRead(path);
      }
      setOpenNote({ path, id: _pathToId.current[path] || null, content: text, dirty: false });
      if (_isMobileV) setVaultTab('editor');
      const parts = path.split('/').filter(Boolean);
      const newExp = new Set(expanded);
      for (let i = 1; i < parts.length; i++) newExp.add(parts.slice(0, i).join('/'));
      setExpanded(newExp);
    } catch (e) { setErr(e.message); }
    setBusy(false);
  };

  /* Saving is tracked per-editor (inline chip) and NEVER via the view-level
     `err` — a failed save used to replace the whole vault view with an error
     screen, hiding the user's unsaved text. Autosave (2.5s idle) plus
     flush-on-leave below mean typed text can no longer be silently lost. */
  const [saveState, setSaveState] = React.useState('');   // '' | 'saving' | 'saved' | 'error: …'
  const openNoteRef = React.useRef(null);
  openNoteRef.current = openNote;

  const saveNote = async (opts) => {
    const note = openNoteRef.current;
    if (!note || !note.dirty) return;
    setBusy(true); setSaveState('saving');
    try {
      if (_bridge) {
        if (note.id) {
          await _bridge.write(note.id, note.content);
        } else {
          const meta = await _bridge.create(note.path, note.content);
          setOpenNote(n => (n && n.path === note.path ? { ...n, id: meta.id } : n));
        }
      } else {
        await window.CafresoHQClient.vaultWrite(note.path, note.content, 'write');
      }
      // Clear dirty only if nothing was typed while the save was in flight.
      setOpenNote(n => (n && n.path === note.path && n.content === note.content)
        ? { ...n, dirty: false } : n);
      setSaveState('saved');
      if (!(opts && opts.quiet)) await refresh();
    } catch (e) {
      setSaveState('error: ' + (e.message || 'save failed'));
    }
    setBusy(false);
  };
  const saveNoteRef = React.useRef(saveNote);
  saveNoteRef.current = saveNote;

  // Autosave: 2.5s after the last keystroke.
  React.useEffect(() => {
    if (!openNote || !openNote.dirty) return;
    const t = setTimeout(() => { saveNoteRef.current({ quiet: true }); }, 2500);
    return () => clearTimeout(t);
  }, [openNote && openNote.content, openNote && openNote.dirty]);

  // Flush-on-leave: unmounting the vault view (switching to another app view)
  // fires a final save of any dirty buffer.
  React.useEffect(() => () => {
    const n = openNoteRef.current;
    if (n && n.dirty) saveNoteRef.current({ quiet: true });
  }, []);

  // Closing or switching notes flushes the dirty buffer first.
  const closeNote = () => {
    const n = openNoteRef.current;
    if (n && n.dirty) saveNoteRef.current({ quiet: true });
    setSaveState('');
    setOpenNote(null);
  };

  /* File management — upload / rename / delete. Server-vault backends only
     (the encrypted bridge vault manages its own files in the parent shell). */
  const fileInputRef = React.useRef(null);
  const onUpload = async (e) => {
    const list = Array.from(e.target.files || []);
    e.target.value = '';
    if (!list.length) return;
    setBusy(true);
    try {
      const r = await window.CafresoHQClient.vaultUpload(list);
      await refresh();
      if (r && r.failed && r.failed.length) {
        alert(`Uploaded ${r.count}, failed ${r.failed.length}:\n` +
              r.failed.map(f => `${f.path}: ${f.error}`).join('\n'));
      }
    } catch (er) { alert('Upload failed: ' + er.message); }
    setBusy(false);
  };
  const renameNote = async () => {
    const n = openNoteRef.current;
    if (!n) return;
    const to = window.prompt('Rename / move to (path inside the vault):', n.path);
    if (!to || to.trim() === n.path) return;
    if (n.dirty) await saveNoteRef.current({ quiet: true });
    try {
      await window.CafresoHQClient.vaultRename(n.path, to.trim());
      setOpenNote(o => o ? { ...o, path: to.trim() } : o);
      await refresh();
    } catch (e) { alert('Rename failed: ' + e.message); }
  };
  const deleteNote = async () => {
    const n = openNoteRef.current;
    if (!n) return;
    if (!window.confirm(`Delete "${n.path}"? This cannot be undone.`)) return;
    try {
      await window.CafresoHQClient.vaultDelete(n.path);
      setSaveState('');
      setOpenNote(null);
      await refresh();
    } catch (e) { alert('Delete failed: ' + e.message); }
  };

  const newNote = () => {
    const path = window.prompt('New note path (e.g. "Inbox/idea.md"):');
    if (!path) return;
    const norm = path.endsWith('.md') ? path : path + '.md';
    // id is null for new notes — saveNote() will call bridge.create()
    setOpenNote({ path: norm, id: null, content: '', dirty: true });
  };

  const openInObsidian = async () => {
    if (!openNote) return;
    try { await window.CafresoHQClient.vaultOpenInObsidian(openNote.path); }
    catch (e) { alert('Could not open in Obsidian: ' + e.message); }
  };

  if (!status) {
    return <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}><div className="section-title">📓 VAULT</div><div className="empty-state"><div className="empty-title">Loading…</div></div></div>;
  }
  if (err) {
    return <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}><div className="section-title">📓 VAULT</div><div className="empty-state"><div className="empty-title error">Error</div><div className="empty-sub">{err}</div></div></div>;
  }
  if (!status.configured) {
    return <div className={_isMobileV ? "vault-mobile" : "view-soon"} style={_isMobileV ? {display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'} : undefined}><div className="section-title">📓 VAULT</div><div className="empty-state"><div className="empty-title">Vault not configured.</div><div className="empty-sub">Choose a Markdown vault directory in Connections settings.</div>{onOpenSettings && <button className="px-btn primary" style={{marginTop:16,fontSize:12,padding:'10px 20px'}} onClick={onOpenSettings}>⚙️ Open Settings</button>}</div></div>;
  }

  const hasNote = !!openNote;
  const showGraph = !graphMinimized;

  // Grid columns: tree pane is fixed-ish, edit + graph share remaining space.
  let gridCols;
  if (hasNote && showGraph)        gridCols = '240px 1fr 1fr';
  else if (hasNote && !showGraph)  gridCols = '240px 1fr';
  else if (!hasNote && showGraph)  gridCols = '240px 1fr';
  else                              gridCols = '240px 1fr';

  /* ---- Mobile: single-pane tab switcher ---- */
  if (_isMobileV) {
    const mobileOpenByPath = async (p) => {
      await openByPath(p);
      setVaultTab('editor');
    };
    return (
      <div className="vault-mobile" style={{display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'}}>
        {/* Tab switcher bar */}
        <div style={{
          display:'flex',gap:0,
          borderBottom:'2px solid var(--ink)',
          background:'var(--paper-2)',
          flexShrink:0,
        }}>
          {[
            ['tree', '\u{1F4C1}', 'Files'],
            ['graph', '\u{1F9E0}', 'Graph'],
            ...(openNote ? [['editor', '✏️', openNote.path.split(/[\\/]/).pop().replace(/\.md$/,'')]] : []),
          ].map(([key, ico, label]) => (
            <button
              key={key}
              onClick={() => setVaultTab(key)}
              style={{
                flex:1,
                padding:'10px 6px',
                background: vaultTab === key ? 'var(--paper)' : 'transparent',
                border:'none',
                borderBottom: vaultTab === key ? '3px solid var(--accent-sun)' : '3px solid transparent',
                color: vaultTab === key ? 'var(--ink)' : 'var(--ink-2)',
                cursor:'pointer',
                fontFamily:"'Press Start 2P',monospace",
                fontSize:9,
                display:'flex',alignItems:'center',justifyContent:'center',gap:4,
                minHeight:44,
              }}
            >
              <span>{ico}</span> {label}
            </button>
          ))}
        </div>

        {/* Active pane */}
        <div style={{flex:1,display:'flex',flexDirection:'column',minHeight:0,overflow:'hidden'}}>
          {vaultTab === 'tree' && (
            <div className="vault-tree-pane" style={{flex:1,display:'flex',flexDirection:'column',overflow:'auto',borderRight:'none',maxHeight:'none'}}>
              <div className="vault-toolbar">
                <span style={{fontWeight:600,fontSize:11,flex:1}}>{status ? status.name : 'Vault'}</span>
                <button className="px-btn ghost" onClick={newNote} title="New note">{'➕'}</button>
                {!_bridge && (
                  <button className="px-btn ghost" onClick={() => fileInputRef.current && fileInputRef.current.click()}
                    title="Upload files into the vault">📤</button>
                )}
                <button className="px-btn ghost" onClick={refresh} title="Refresh">{'↻'}</button>
                <input ref={fileInputRef} type="file" multiple style={{display:'none'}} onChange={onUpload}/>
              </div>
              <div style={{padding:'4px 6px',display:'flex',flexDirection:'column',gap:3}}>
                <input style={{width:'100%',boxSizing:'border-box'}} value={q} onChange={e=>setQ(e.target.value)} placeholder="Search vault…" onKeyDown={e=>e.key==='Enter'&&search()} />
                <button className="px-btn secondary" style={{fontSize:9}} onClick={search}>{'🔎'} SEARCH</button>
              </div>
              {hits ? (
                <div style={{overflowY:'auto',flex:1}}>
                  <div style={{padding:'4px 8px',fontSize:9,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                    {hits.length} result(s)
                    <button className="px-btn ghost" style={{fontSize:9}} onClick={()=>setHits(null)}>{'✕'}</button>
                  </div>
                  {hits.map(h => (
                    <div key={h.path} className="tree-row tree-file" onClick={()=>{ mobileOpenByPath(h.path); }}>
                      <span className="tree-name">{h.title || h.path}</span>
                      <span style={{fontSize:9,opacity:0.6}}>{(h.score*100).toFixed(1)}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <FolderTree files={files} openPath={openNote?.path} onOpen={(p) => mobileOpenByPath(p)} expanded={expanded} setExpanded={setExpanded} />
              )}
            </div>
          )}

          {vaultTab === 'graph' && (
            <div className="vault-graph-pane fullspan" style={{flex:1,display:'flex',flexDirection:'column',borderLeft:'none'}}>
              <GraphView embedded agents={agents} activePath={openNote?.path} onOpenNote={(p) => mobileOpenByPath(p)} onMinimize={() => setVaultTab('tree')} />
            </div>
          )}

          {vaultTab === 'editor' && openNote && (
            <div className="vault-edit-pane" style={{flex:1,display:'flex',flexDirection:'column',borderRight:'none'}}>
              <div className="vault-edit-head">
                <div style={{fontSize:10,opacity:0.7,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>{openNote.path}</div>
                <label style={{fontSize:9,display:'flex',alignItems:'center',gap:4,whiteSpace:'nowrap'}}>
                  <input type="checkbox" checked={preview} onChange={e=>setPreview(e.target.checked)} /> Preview
                </label>
                {!_bridge && <button className="px-btn ghost" onClick={renameNote} title="Rename / move">✎</button>}
                {!_bridge && <button className="px-btn ghost" onClick={deleteNote} title="Delete file">🗑</button>}
                <button className="px-btn ghost" onClick={openInObsidian} title="Open in Obsidian">{'↗'}</button>
                <button className={`px-btn ${saveState.startsWith('error') ? 'danger' : 'primary'}`}
                  onClick={() => saveNote()} disabled={!openNote.dirty || busy} title={saveState}>
                  {saveState.startsWith('error') ? '⚠ Retry save' : busy ? 'Saving…' : openNote.dirty ? 'Save' : 'Saved'}
                </button>
                <button className="px-btn ghost" onClick={() => { closeNote(); setVaultTab('tree'); }} title="Close" style={{fontSize:11}}>{'✕'}</button>
              </div>
              {preview ? (
                <div className="vault-preview" dangerouslySetInnerHTML={{ __html: renderMarkdown(openNote.content) }} />
              ) : (
                <textarea className="vault-edit" value={openNote.content} onChange={e=>setOpenNote({ ...openNote, content: e.target.value, dirty: true })} />
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  /* ---- Desktop: 3-column grid ---- */
  return (
    <div className="vault-layout-3col" style={{ gridTemplateColumns: gridCols }}>
      <div className="vault-tree-pane">
        <div className="vault-toolbar">
          <span style={{fontWeight:600,fontSize:11,flex:1}}>{status.name}</span>
          <button className="px-btn ghost" onClick={newNote} title="New note">➕</button>
          {!_bridge && (
            <button className="px-btn ghost" onClick={() => fileInputRef.current && fileInputRef.current.click()}
              title="Upload files into the vault">📤</button>
          )}
          <button className="px-btn ghost" onClick={refresh} title="Refresh">↻</button>
          <input ref={fileInputRef} type="file" multiple style={{display:'none'}} onChange={onUpload}/>
        </div>
        <div style={{padding:'4px 6px',display:'flex',flexDirection:'column',gap:3}}>
          <input style={{width:'100%',boxSizing:'border-box'}} value={q} onChange={e=>setQ(e.target.value)} placeholder="Search vault…" onKeyDown={e=>e.key==='Enter'&&search()} />
          <button className="px-btn secondary" style={{fontSize:9}} onClick={search}>🔎 SEARCH</button>
        </div>
        {hits ? (
          <div style={{overflowY:'auto',flex:1}}>
            <div style={{padding:'4px 8px',fontSize:9,display:'flex',justifyContent:'space-between',alignItems:'center'}}>
              {hits.length} result(s)
              <button className="px-btn ghost" style={{fontSize:9}} onClick={()=>setHits(null)}>✕</button>
            </div>
            {hits.map(h => (
              <div key={h.path} className="tree-row tree-file" onClick={()=>openByPath(h.path)}>
                <span className="tree-name">{h.title || h.path}</span>
                <span style={{fontSize:9,opacity:0.6}}>{(h.score*100).toFixed(1)}</span>
              </div>
            ))}
          </div>
        ) : (
          <FolderTree files={files} openPath={openNote?.path} onOpen={openByPath} expanded={expanded} setExpanded={setExpanded} />
        )}
      </div>

      {hasNote && (
        <div className={`vault-edit-pane${!showGraph ? ' fullspan' : ''}`}>
          <div className="vault-edit-head">
            <div style={{fontSize:10,opacity:0.7,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>{openNote.path}</div>
            <label style={{fontSize:9,display:'flex',alignItems:'center',gap:4,whiteSpace:'nowrap'}}>
              <input type="checkbox" checked={preview} onChange={e=>setPreview(e.target.checked)} /> Preview
            </label>
            {!_bridge && <button className="px-btn ghost" onClick={renameNote} title="Rename / move">✎</button>}
            {!_bridge && <button className="px-btn ghost" onClick={deleteNote} title="Delete file">🗑</button>}
            <button className="px-btn ghost" onClick={openInObsidian} title="Open in Obsidian">↗</button>
            <button className={`px-btn ${saveState.startsWith('error') ? 'danger' : 'primary'}`}
              onClick={() => saveNote()} disabled={!openNote.dirty || busy} title={saveState}>
              {saveState.startsWith('error') ? '⚠ Retry save' : busy ? 'Saving…' : openNote.dirty ? 'Save' : 'Saved'}
            </button>
            {!showGraph && (
              <button className="px-btn ghost" onClick={() => setGraphMinimized(false)} title="Show graph">🧠</button>
            )}
            <button
              className="px-btn ghost"
              onClick={closeNote}
              title="Close note (Esc)"
              style={{fontSize:11}}
            >✕</button>
          </div>
          {preview ? (
            <div className="vault-preview" dangerouslySetInnerHTML={{ __html: renderMarkdown(openNote.content) }} />
          ) : (
            <textarea className="vault-edit" value={openNote.content} onChange={e=>setOpenNote({ ...openNote, content: e.target.value, dirty: true })} />
          )}
        </div>
      )}

      {showGraph && (
        <div className={`vault-graph-pane${!hasNote ? ' fullspan' : ''}`}>
          <GraphView embedded agents={agents} activePath={openNote?.path} onOpenNote={p => openByPath(p)} onMinimize={() => setGraphMinimized(true)} />
        </div>
      )}

      {graphMinimized && !hasNote && (
        <div className="vault-graph-pane fullspan" style={{display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer'}} onClick={() => setGraphMinimized(false)}>
          <span style={{fontSize:11,opacity:0.5}}>🧠 VAULT GRAPH (click to show)</span>
        </div>
      )}
    </div>
  );
}


/* ---------------- Vault Graph (force-directed canvas) ---------------- */

const useForceGraph = (initialState) => {
  const stateRef = React.useRef(initialState);
  const [_, setTick] = useSV(0);

  const wakeSim = () => {
    if (stateRef.current.energy < 1) stateRef.current.energy = 1;
  };

  React.useEffect(() => {
    let frame;
    const loop = () => {
      if (stateRef.current.energy > 0.001) {
        simulate(stateRef.current);
        setTick(t => t + 1);
        stateRef.current.energy *= 0.99; // Cooling
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, []);

  return [stateRef.current, wakeSim, _];
};


const DEFAULT_SETTINGS = {
  centerForce:  0.0008,
  repelForce:   900,
  linkForce:    0.022,
  linkDistance: 150,
  layerForce:   0.003,
  // Color/style edges by their semantic type (cites, supports, contradicts,
  // child_of, etc) instead of all uniform. Off by default since the visual
  // change is significant; users opt-in via the gear panel. See
  // EDGE_TYPE_STYLE in this file for the palette.
  colorEdgesByType: false,
};

const GRAPH_PREFS_KEY = 'cafresohq:graph:prefs';

function loadGraphPrefs() {
  try {
    const raw = localStorage.getItem(GRAPH_PREFS_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw);
    return (v && typeof v === 'object') ? v : null;
  } catch (_) { return null; }
}

function saveGraphPrefs(prefs) {
  try { localStorage.setItem(GRAPH_PREFS_KEY, JSON.stringify(prefs)); } catch (_) {}
}

/* Edge color from the typed-edge palette (shared with the legacy renderer's
   EDGE_TYPE_STYLE). Falls back to a soft theme default for plain links. */
function edgeColorForType(type, isDark) {
  const s = EDGE_TYPE_STYLE[type];
  if (s && s.color) return s.color;
  return isDark ? 'rgba(168,152,190,0.22)' : 'rgba(120,108,90,0.24)';
}

// Concept-map mode reads note bodies client-side; cap how many we pull so a big
// vault doesn't fire hundreds of fetches. Scoping to a folder keeps it focused.
const CONCEPT_NOTE_CAP = 120;

/* InfraNodus-grade WebGL graph view (sigma.js + graphology via
   window.CafresoGraphEngine). Replaces the legacy Canvas-2D renderer below.
   Keeps the external contract: props {onOpenNote, embedded, activePath,
   onMinimize, agents}, the window.CafresoHQGraph API, and the popout. Adds an
   analytics side panel (communities, betweenness, structure, gaps) and a second
   data source — a concept co-occurrence map (window.CafresoCooccur) — that drops
   into the same engine/analytics/publish path. */
function GraphView({ onOpenNote, embedded = false, activePath = null, onMinimize = null, agents = null }) {
  const containerRef = React.useRef(null);
  const engineRef = React.useRef(null);
  const rawRef = React.useRef({ byId: {}, maxInlinks: 0, mtimeRange: null });
  const persistedRef = React.useRef(null);
  if (persistedRef.current === null) persistedRef.current = loadGraphPrefs() || {};
  const persisted = persistedRef.current;

  const [colorMode, setColorMode] = useSV(persisted.colorMode || 'community');
  const [localMode, setLocalMode] = useSV(persisted.localMode || 'global');
  const [filter, setFilter] = useSV('');
  const [analytics, setAnalytics] = useSV(null);
  const [loading, setLoading] = useSV(true);
  const [panelOpen, setPanelOpen] = useSV(persisted.drawerOpen !== false);
  const [ctxMenu, setCtxMenu] = useSV(null); // { id, x, y }
  const [nodeCount, setNodeCount] = useSV(0);
  const [shareUrl, setShareUrl] = useSV(null);
  const [sharing, setSharing] = useSV(false);
  const [edgesHover, setEdgesHover] = useSV(!!persisted.edgesHover); // hide edges until hover
  const edgesHoverRef = React.useRef(edgesHover);
  edgesHoverRef.current = edgesHover;

  // Data source: 'links' = wikilink graph (/vault/graph); 'concepts' = co-occurrence map.
  const [source, setSource] = useSV(persisted.source === 'concepts' ? 'concepts' : 'links');
  const [scope, setScope] = useSV(persisted.scope || '__all__');   // folder prefix for concepts
  const [folders, setFolders] = useSV([]);
  const [conceptMeta, setConceptMeta] = useSV(null);
  // Refs keep the loader/mount helpers reading the latest values without re-binding.
  const sourceRef = React.useRef(source); sourceRef.current = source;
  const scopeRef = React.useRef(scope); scopeRef.current = scope;
  const filterRef = React.useRef(filter); filterRef.current = filter;
  const colorModeRef = React.useRef(colorMode); colorModeRef.current = colorMode;
  const localModeRef = React.useRef(localMode); localModeRef.current = localMode;
  const activePathRef = React.useRef(activePath); activePathRef.current = activePath;

  const isDark = typeof document !== 'undefined' && document.body.classList.contains('night');
  const titleFor = (id) => {
    const n = rawRef.current.byId[id];
    return (n && (n.title || n.label)) || String(id).split('/').pop().replace(/\.md$/, '');
  };

  // Color function for non-community modes — reuses the legacy colorForNode.
  const colorFor = React.useCallback((id, node) => {
    if (!node || colorMode === 'community') return null;
    const cs = (typeof getComputedStyle === 'function') ? getComputedStyle(document.documentElement) : null;
    return colorForNode(node, {
      colorMode,
      maxInlinks: rawRef.current.maxInlinks,
      mtimeRange: rawRef.current.mtimeRange,
      clusterColoring: false, clusters: null,
    }, isDark, cs);
  }, [colorMode, isDark]);

  const wireEngine = React.useCallback((eng) => {
    // Concept nodes are terms, not note paths — don't try to open them.
    eng.on('nodeClick', (id) => { if (sourceRef.current === 'links') onOpenNote && onOpenNote(id); });
    eng.on('nodeDoubleClick', (id) => { if (sourceRef.current === 'links') onOpenNote && onOpenNote(id); });
    eng.on('hover', () => { /* highlight handled inside the engine */ });
    eng.on('stageClick', () => setCtxMenu(null));
    eng.on('analytics', (a) => setAnalytics(a));
    eng.on('nodeRightClick', (id, evt) => {
      const ox = (evt && evt.original) ? evt.original.clientX : (evt && evt.x) || 0;
      const oy = (evt && evt.original) ? evt.original.clientY : (evt && evt.y) || 0;
      setCtxMenu({ id, x: ox, y: oy });
    });
  }, [onOpenNote]);

  const buildData = (g) => {
    rawRef.current.byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
    let maxIn = 0, mMin = Infinity, mMax = -Infinity;
    for (const n of g.nodes) {
      if ((n.inlinks || 0) > maxIn) maxIn = n.inlinks;
      if (n.mtime) { if (n.mtime < mMin) mMin = n.mtime; if (n.mtime > mMax) mMax = n.mtime; }
    }
    rawRef.current.maxInlinks = maxIn;
    rawRef.current.mtimeRange = mMin < mMax ? { min: mMin, max: mMax } : null;
    const edges = g.edges.map((e) => ({ ...e, color: edgeColorForType(e.type, isDark) }));
    return { nodes: g.nodes, edges };
  };

  // Pull note bodies for the concept map (scoped + capped to bound the fetches).
  const loadConceptDocs = async () => {
    const all = await window.CafresoHQClient.vaultList();
    let files = (all || []).filter((f) => /\.md$/i.test(f.path || ''));
    const sc = scopeRef.current;
    if (sc && sc !== '__all__') files = files.filter((f) => f.path === sc || f.path.startsWith(sc.replace(/\/$/, '') + '/'));
    files = files.sort((a, b) => (b.mtime || 0) - (a.mtime || 0)).slice(0, CONCEPT_NOTE_CAP);
    const docs = [];
    const CONC = 6;
    for (let i = 0; i < files.length; i += CONC) {
      const got = await Promise.all(files.slice(i, i + CONC).map(async (f) => {
        try { return { id: f.path, title: f.title || titleFor(f.path), text: await window.CafresoHQClient.vaultRead(f.path) }; }
        catch (_) { return null; }
      }));
      for (const d of got) if (d) docs.push(d);
    }
    return docs;
  };

  // Resolve the active data source into {nodes, edges} for the engine.
  const loadData = async () => {
    if (sourceRef.current === 'concepts') {
      if (!window.CafresoCooccur) throw new Error('concept builder unavailable');
      const docs = await loadConceptDocs();
      const built = window.CafresoCooccur.build(docs, { window: 4, maxNodes: 200 });
      setConceptMeta({ docs: docs.length, terms: built.nodes.length });
      return built;
    }
    setConceptMeta(null);
    return await window.CafresoHQClient.vaultGraph();
  };

  // (Re)mount the engine on fresh data, re-applying controls a remount drops.
  const mountData = (g) => {
    if (!containerRef.current || !window.CafresoGraphEngine) return null;
    try { engineRef.current && engineRef.current.destroy(); } catch (_) {}
    const eng = window.CafresoGraphEngine.mount(containerRef.current, buildData(g), {
      dark: isDark, colorMode: colorModeRef.current, colorFor, now: Date.now(),
      edgeMode: edgesHoverRef.current ? 'hover' : 'always',
    });
    engineRef.current = eng;
    wireEngine(eng);
    if (filterRef.current) eng.setFilter(filterRef.current);
    if (sourceRef.current === 'links' && activePathRef.current) {
      eng.setActivePath(activePathRef.current);
      if (localModeRef.current !== 'global') eng.setLocalMode(activePathRef.current, parseInt(localModeRef.current, 10));
    }
    setNodeCount(g.nodes.length);
    return eng;
  };

  // Load + mount on first render and whenever the source/scope changes.
  React.useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const g = await loadData();
        if (cancelled || !containerRef.current) { setLoading(false); return; }
        const eng = mountData(g);
        setLoading(false);
        if (!eng) return;
        window.CafresoHQGraph = {
          _lastGraph: g,
          pulse: (id) => { try { engineRef.current && engineRef.current.focusNode(id); } catch (_) {} },
          refresh: async () => {
            try {
              const g2 = await loadData();
              if (!containerRef.current) return;
              const e2 = mountData(g2);
              if (e2) window.CafresoHQGraph._lastGraph = g2;
            } catch (_) {}
          },
        };
      } catch (e) { console.warn('graph load:', e); setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [source, scope]);

  // Folder list for the concept-map scope picker (cheap, once).
  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const all = await window.CafresoHQClient.vaultList();
        if (cancelled) return;
        const set = new Set();
        for (const f of all || []) { const i = (f.path || '').indexOf('/'); if (i > 0) set.add(f.path.slice(0, i)); }
        setFolders([...set].sort());
      } catch (_) {}
    })();
    return () => { cancelled = true; };
  }, []);

  // Destroy the engine on unmount.
  React.useEffect(() => () => {
    try { engineRef.current && engineRef.current.destroy(); } catch (_) {}
    if (window.CafresoHQGraph) { try { delete window.CafresoHQGraph; } catch (_) {} }
  }, []);

  // Control → engine wiring.
  React.useEffect(() => { const e = engineRef.current; if (e) { e.setColorMode(colorMode); e.setColorFor(colorFor); } }, [colorMode, colorFor]);
  React.useEffect(() => { const e = engineRef.current; if (e) e.setFilter(filter); }, [filter]);
  React.useEffect(() => { const e = engineRef.current; if (e) e.setEdgeMode(edgesHover ? 'hover' : 'always'); }, [edgesHover]);
  React.useEffect(() => {
    const e = engineRef.current; if (!e) return;
    // Local depth is note-relative — only meaningful for the wikilink graph.
    if (source !== 'links' || localMode === 'global' || !activePath) e.setLocalMode(null, 0);
    else e.setLocalMode(activePath, parseInt(localMode, 10));
  }, [localMode, activePath, source]);
  React.useEffect(() => { const e = engineRef.current; if (e && source === 'links' && activePath) e.setActivePath(activePath); }, [activePath, source]);

  // Persist prefs.
  React.useEffect(() => {
    saveGraphPrefs({ ...persisted, colorMode, localMode, drawerOpen: panelOpen, edgesHover, source, scope });
  }, [colorMode, localMode, panelOpen, edgesHover, source, scope]);

  // Keep sigma sized to its container.
  React.useEffect(() => {
    const el = containerRef.current; if (!el || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(() => { const e = engineRef.current; if (e) e.resize(); });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Publish: export the laid-out snapshot to a shareable public graph URL.
  const publish = React.useCallback(async () => {
    const e = engineRef.current; if (!e) return;
    setSharing(true);
    try {
      const snap = e.exportSnapshot();
      snap.title = sourceRef.current === 'concepts'
        ? ('Concept map' + (scopeRef.current && scopeRef.current !== '__all__' ? ' · ' + scopeRef.current : ''))
        : (activePath ? titleFor(activePath) : 'Vault graph');
      const base = (typeof window !== 'undefined' && window._API_BASE != null) ? window._API_BASE : '';
      const res = await fetch(base + '/graph/publish', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(snap),
      });
      const j = await res.json();
      if (j && j.viewerUrl) {
        const full = (base || (typeof location !== 'undefined' ? location.origin : '')) + j.viewerUrl;
        setShareUrl(full);
        try { await navigator.clipboard.writeText(full); } catch (_) {}
        // Onboarding: mark "publish your first graph" complete.
        try { localStorage.setItem('cafresohq_hq_v1:publishedGraph', '1'); window.dispatchEvent(new CustomEvent('cafresohq:graph-published')); } catch (_) {}
      }
    } catch (err) { console.warn('publish graph:', err); }
    finally { setSharing(false); }
  }, [activePath]);

  const m = analytics && analytics.metrics;
  const STRUCT_COPY = {
    biased: 'One dominant topic — add contrasting ideas.',
    focused: 'A clear main theme with some branches.',
    diversified: 'Several well-connected topics — healthy balance.',
    dispersed: 'Many scattered topics — consider bridging them.',
  };
  const COLOR_MODES = [['community', 'Topics'], ['tags', 'Tags'], ['type', 'Type'], ['folder', 'Folder'], ['inlinks', 'Links'], ['modified', 'Recency']];

  const ctrlStyle = { background: 'rgba(20,18,12,0.55)', color: '#e9e2d4', border: '1px solid rgba(245,210,93,0.25)', borderRadius: 6, padding: '3px 7px', fontSize: 12, fontFamily: 'Inter, system-ui, sans-serif' };

  return React.createElement('div', { style: { position: 'relative', width: '100%', height: '100%', minHeight: 0, overflow: 'hidden', background: isDark ? '#171310' : '#f4efe6' } },
    // Sigma mounts here.
    React.createElement('div', { ref: containerRef, style: { position: 'absolute', inset: 0 } }),

    // Loading hint.
    loading && React.createElement('div', { style: { position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#bdb3a0', font: '13px Inter, sans-serif', pointerEvents: 'none' } }, source === 'concepts' ? 'Building concept map…' : 'Loading graph…'),

    // Top toolbar.
    React.createElement('div', { style: { position: 'absolute', top: 10, left: 10, right: 10, display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', pointerEvents: 'none' } },
      React.createElement('input', {
        value: filter, placeholder: source === 'concepts' ? 'Filter concepts' : 'Filter  (tag:x  type:y  -term)',
        onChange: (e) => setFilter(e.target.value),
        style: { ...ctrlStyle, width: 180, pointerEvents: 'auto' },
      }),
      // Data source: wikilink graph vs concept co-occurrence map.
      React.createElement('select', { value: source, onChange: (e) => setSource(e.target.value), title: 'Graph source', style: { ...ctrlStyle, pointerEvents: 'auto' } },
        React.createElement('option', { value: 'links' }, '🔗 Links'),
        React.createElement('option', { value: 'concepts' }, '🧠 Concepts')),
      React.createElement('select', { value: colorMode, onChange: (e) => setColorMode(e.target.value), title: 'Color by', style: { ...ctrlStyle, pointerEvents: 'auto' } },
        COLOR_MODES.map(([v, l]) => React.createElement('option', { key: v, value: v }, l))),
      // Concept mode → folder scope picker; link mode → local depth around the active note.
      source === 'concepts'
        ? React.createElement('select', { value: scope, onChange: (e) => setScope(e.target.value), title: 'Concept-map scope (folder)', style: { ...ctrlStyle, pointerEvents: 'auto', maxWidth: 150 } },
            React.createElement('option', { value: '__all__' }, 'All notes'),
            folders.map((f) => React.createElement('option', { key: f, value: f }, f + '/')))
        : React.createElement('select', { value: localMode, onChange: (e) => setLocalMode(e.target.value), title: 'Local depth around active note', style: { ...ctrlStyle, pointerEvents: 'auto' } },
            [['global', 'Whole graph'], ['1', '1 hop'], ['2', '2 hops'], ['3', '3 hops']].map(([v, l]) => React.createElement('option', { key: v, value: v }, l))),
      React.createElement('button', { onClick: () => setEdgesHover((v) => !v), title: edgesHover ? 'Edges appear on hover' : 'Edges always visible — click to calm', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto', ...(edgesHover ? { color: '#F5D25D', borderColor: 'rgba(245,210,93,0.55)' } : {}) } }, edgesHover ? 'Edges: hover' : 'Edges: on'),
      source === 'concepts'
        ? React.createElement('button', { onClick: () => { const a = window.CafresoHQGraph; if (a && a.refresh) a.refresh(); }, title: 'Re-read notes and rebuild the concept map', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, '↻ Rebuild')
        : React.createElement('button', { onClick: () => { const e = engineRef.current; if (e) e.refreshLayout(); }, title: 'Re-run layout', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, '↻ Layout'),
      React.createElement('button', { onClick: publish, title: 'Publish a shareable public graph', style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, sharing ? 'Publishing…' : '⤴ Share'),
      React.createElement('div', { style: { flex: 1 } }),
      React.createElement('button', { onClick: () => setPanelOpen((v) => !v), style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, panelOpen ? 'Hide analytics ›' : '‹ Analytics'),
      onMinimize && React.createElement('button', { onClick: onMinimize, style: { ...ctrlStyle, cursor: 'pointer', pointerEvents: 'auto' } }, '✕'),
    ),

    // Analytics side panel (InfraNodus-style).
    panelOpen && React.createElement('div', { style: { position: 'absolute', top: 50, right: 10, bottom: 10, width: 246, overflowY: 'auto', background: 'rgba(20,18,12,0.82)', backdropFilter: 'blur(6px)', border: '1px solid rgba(245,210,93,0.22)', borderRadius: 10, padding: '12px 13px', color: '#e9e2d4', font: '12px Inter, system-ui, sans-serif' } },
      React.createElement('div', { style: { fontWeight: 600, fontSize: 13, marginBottom: 8, color: '#F5D25D' } }, source === 'concepts' ? 'Concept analysis' : 'Graph analysis'),
      source === 'concepts' && conceptMeta && React.createElement('div', { style: { color: '#8f8676', fontSize: 11, marginBottom: 8 } }, 'Co-occurrence over ' + conceptMeta.docs + ' note' + (conceptMeta.docs === 1 ? '' : 's')),
      !m && React.createElement('div', { style: { color: '#9b938a' } }, 'Computing…'),
      m && React.createElement(React.Fragment, null,
        React.createElement('div', { style: { display: 'inline-block', padding: '3px 9px', borderRadius: 20, background: 'rgba(245,210,93,0.16)', color: '#F5D25D', fontWeight: 600, textTransform: 'capitalize', marginBottom: 6 } }, m.structure || '—'),
        React.createElement('div', { style: { color: '#cabfa9', marginBottom: 10, lineHeight: 1.4 } }, STRUCT_COPY[m.structure] || ''),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 10px', marginBottom: 12 } },
          [[source === 'concepts' ? 'Concepts' : 'Notes', m.nodes], ['Links', m.edges], ['Topics', m.communityCount], ['Components', m.components], ['Modularity', (m.modularity || 0).toFixed(2)], ['Avg degree', (m.avgDegree || 0).toFixed(1)]]
            .map(([k, v]) => React.createElement('div', { key: k }, React.createElement('span', { style: { color: '#8f8676' } }, k + ': '), React.createElement('b', null, v)))),

        // Top influential (betweenness brokers).
        React.createElement('div', { style: { fontWeight: 600, margin: '4px 0 5px', color: '#F5D25D' } }, 'Most influential'),
        (analytics.topInfluential || []).slice(0, 6).map((t) =>
          React.createElement('div', { key: t.id, onClick: () => { const e = engineRef.current; if (e) e.focusNode(t.id); }, title: 'Focus', style: { cursor: 'pointer', padding: '2px 0', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
            '◆ ' + titleFor(t.id))),

        // Topical clusters.
        React.createElement('div', { style: { fontWeight: 600, margin: '12px 0 5px', color: '#F5D25D' } }, 'Main topics'),
        (analytics.clusters || []).slice(0, 5).map((c) =>
          React.createElement('div', { key: c.community, style: { marginBottom: 6 } },
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 6 } },
              React.createElement('span', { style: { width: 9, height: 9, borderRadius: '50%', background: window.CafresoGraphEngine.communityColor(c.community), display: 'inline-block', flex: '0 0 auto' } }),
              React.createElement('b', null, Math.round(c.share * 100) + '%'),
              React.createElement('span', { style: { color: '#8f8676' } }, c.size + (source === 'concepts' ? ' concepts' : ' notes'))),
            React.createElement('div', { style: { color: '#cabfa9', fontSize: 11, paddingLeft: 15, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' } },
              c.topNodes.slice(0, 3).map(titleFor).join(', ')))),

        // Structural gap.
        analytics.gap && React.createElement('div', { style: { marginTop: 12, padding: 8, borderRadius: 8, background: 'rgba(232,169,169,0.10)', border: '1px solid rgba(232,169,169,0.25)' } },
          React.createElement('div', { style: { fontWeight: 600, color: '#E8A9A9', marginBottom: 3 } }, 'Structural gap'),
          React.createElement('div', { style: { color: '#cabfa9', fontSize: 11, lineHeight: 1.4 } },
            'Weakly connected: ', React.createElement('b', null, titleFor(analytics.gap.aTop)), ' ⟷ ', React.createElement('b', null, titleFor(analytics.gap.bTop)))),
      ),
    ),

    // Node context menu.
    ctxMenu && React.createElement('div', { style: { position: 'fixed', left: Math.min(ctxMenu.x, (typeof window !== 'undefined' ? window.innerWidth : 9999) - 170), top: ctxMenu.y, zIndex: 50, background: 'rgba(28,24,16,0.97)', border: '1px solid rgba(245,210,93,0.3)', borderRadius: 8, padding: 4, minWidth: 150, font: '12px Inter, sans-serif', color: '#e9e2d4' },
      onMouseLeave: () => setCtxMenu(null) },
      [...(source === 'links' ? [['Open note', () => { onOpenNote && onOpenNote(ctxMenu.id); setCtxMenu(null); }]] : []),
       ['Focus', () => { const e = engineRef.current; if (e) e.focusNode(ctxMenu.id); setCtxMenu(null); }],
       ['Hide node', () => { const e = engineRef.current; if (e) { const s = new Set(e.hidden); s.add(ctxMenu.id); e.setHidden(s); } setCtxMenu(null); }]]
        .map(([label, fn]) => React.createElement('div', { key: label, onClick: fn, style: { padding: '6px 10px', cursor: 'pointer', borderRadius: 5 }, onMouseEnter: (ev) => ev.currentTarget.style.background = 'rgba(245,210,93,0.14)', onMouseLeave: (ev) => ev.currentTarget.style.background = 'transparent' }, label))),

    // Share modal.
    shareUrl && React.createElement('div', { style: { position: 'absolute', left: '50%', top: '50%', transform: 'translate(-50%,-50%)', zIndex: 60, width: 420, maxWidth: '90%', background: 'rgba(24,20,14,0.98)', border: '1px solid rgba(245,210,93,0.3)', borderRadius: 12, padding: 18, color: '#e9e2d4', font: '13px Inter, sans-serif', boxShadow: '0 18px 60px rgba(0,0,0,0.5)' } },
      React.createElement('div', { style: { fontWeight: 600, color: '#F5D25D', marginBottom: 8 } }, '⤴ Public graph published'),
      React.createElement('div', { style: { color: '#cabfa9', marginBottom: 10, lineHeight: 1.4 } }, 'Anyone with this link can view this graph (read-only). Copied to your clipboard.'),
      React.createElement('input', { readOnly: true, value: shareUrl, onFocus: (e) => e.target.select(), style: { width: '100%', boxSizing: 'border-box', ...ctrlStyle, marginBottom: 10 } }),
      React.createElement('div', { style: { display: 'flex', gap: 8 } },
        React.createElement('button', { onClick: () => window.open(shareUrl, '_blank'), style: { ...ctrlStyle, cursor: 'pointer' } }, 'Open ↗'),
        React.createElement('button', { onClick: () => { try { navigator.clipboard.writeText('<iframe src="' + shareUrl + '" width="100%" height="600" style="border:0;border-radius:12px"></iframe>'); } catch (_) {} }, style: { ...ctrlStyle, cursor: 'pointer' } }, 'Copy embed'),
        React.createElement('div', { style: { flex: 1 } }),
        React.createElement('button', { onClick: () => setShareUrl(null), style: { ...ctrlStyle, cursor: 'pointer' } }, 'Close')),
    ),
  );
}

function GraphViewLegacy({ onOpenNote, embedded = false, activePath = null, onMinimize = null, agents = null }) {
  const canvasRef = React.useRef(null);
  const wrapRef   = React.useRef(null);
  const centeredRef = React.useRef(false);

  // Load persisted preferences once.
  const persistedRef = React.useRef(null);
  if (persistedRef.current === null) persistedRef.current = loadGraphPrefs() || {};
  const persisted = persistedRef.current;

  const filterRef = React.useRef(null);
  // Tracks the most recent activePath we've already auto-centered on, so we
  // don't fight the user every render.
  const centeredOnRef = React.useRef(null);
  // Mouse position relative to the wrapper — used to anchor hover-preview tooltip + context menu.
  const lastMouseRef = React.useRef({ x: 0, y: 0 });

  const [hover, setHover] = useSV(null);
  const [selected, setSelected] = useSV(null);
  const [drawerOpen, setDrawerOpen] = useSV(!!persisted.drawerOpen);
  const [showAllLabels, setShowAllLabels] = useSV(!!persisted.showAllLabels);
  const [filter, setFilter] = useSV('');
  const [showSettings, setShowSettings] = useSV(false);
  const [settings, setSettings] = useSV({ ...DEFAULT_SETTINGS, ...(persisted.settings || {}) });
  const [localMode, setLocalMode] = useSV(persisted.localMode || 'global'); // 'global' | '1' | '2' | '3'
  const [colorMode, setColorMode] = useSV(persisted.colorMode || 'tags');   // 'tags' | 'folder' | 'modified' | 'inlinks' | 'type'
  const [viewMode, setViewMode] = useSV(persisted.viewMode || 'free'); // free | research | execution | agents | decisions | stale

  // Per-vault behaviours — persisted with prefs.
  const [hiddenIds, setHiddenIds] = useSV(new Set(persisted.hiddenIds || []));
  const [pinned, setPinned]       = useSV(persisted.pinned || {}); // { [id]: {x,y} }

  // Right-click menu and hover preview state.
  const [contextMenu, setContextMenu] = useSV(null);  // { x, y, node }
  const [previewNote, setPreviewNote] = useSV(null);  // { id, title, content }
  const previewCacheRef = React.useRef(new Map());
  const previewTimerRef = React.useRef(null);

  // Round-2 features ────────────────────────────────────────────────────
  // Cluster auto-coloring (connected components). Computed once per data load.
  const clustersRef = React.useRef(null);
  const [clusterColoring, setClusterColoring] = useSV(!!persisted.clusterColoring);
  const [highlightOrphans, setHighlightOrphans] = useSV(!!persisted.highlightOrphans);
  // Shortest-path: shift-click selects path endpoints, then we BFS.
  const [pathEndpoints, setPathEndpoints] = useSV([]);  // ids
  const [shortestPath, setShortestPath]   = useSV(null); // Set<id> on path, null = none
  // Saved views (snapshots of UI state).
  const [savedViews, setSavedViews] = useSV(persisted.savedViews || []);
  // Command palette.
  const [paletteOpen, setPaletteOpen] = useSV(false);
  const [paletteQuery, setPaletteQuery] = useSV('');
  // Sub-menu: pick agent for an action (used by right-click "Send to agent" path).
  const [agentSubmenu, setAgentSubmenu] = useSV(null); // { kind, node }
  // Status messages from agent actions.
  /* Status messages now route through the global toast system (Session 2).
     We keep the local `setStatusMsg({ text, kind })` shape so the dozens of
     existing call sites don't have to be rewritten — this adapter just
     translates them into the new toast queue. */
  const setStatusMsg = React.useCallback((msg) => {
    if (!msg) return;
    const toast = window.cafresohqToast;
    if (!toast) return;
    const k = msg.kind || 'info';
    if (k === 'error')      toast.error(msg.text, { detail: msg.detail });
    else if (k === 'warn')  toast.warn(msg.text);
    else if (k === 'success') toast.success(msg.text);
    else toast.info(msg.text);
  }, []);

  // Round-3 features ────────────────────────────────────────────────────
  // Lasso multi-select.
  const [selectedSet, setSelectedSet] = useSV(new Set()); // Set<id>
  const [lassoRect, setLassoRect] = useSV(null); // {x0,y0,x1,y1} screen-space (relative to wrapper)
  // Drag-edge-out (Ctrl/Cmd + drag from node body).
  const [linkDrag, setLinkDrag] = useSV(null); // {fromId, x, y}
  // AI cluster labels — { clusterIdx → string }.
  const [clusterLabels, setClusterLabels] = useSV(persisted.clusterLabels || {});
  // Live agent activity overlay — Map<id, {agentId, agentName, color, kind, until}>
  const agentActivityRef = React.useRef(new Map());
  const [activityTick, setActivityTick] = useSV(0);
  // Insights tab toggle inside the gear panel.
  const [showInsights, setShowInsights] = useSV(false);
  // Time scrubber: when enabled, only show notes with mtime ≤ value.
  const [timeScrubEnabled, setTimeScrubEnabled] = useSV(false);
  const [timeScrub, setTimeScrub] = useSV(null); // ms timestamp, null = max
  // Multi-select batch agent submenu.
  const [batchAgentOpen, setBatchAgentOpen] = useSV(false);
  // Compare mode: { aId, bId, depth }. Renders A's BFS subgraph + B's, and
  // colors shared nodes specially.
  const [compareSet, setCompareSet] = useSV(null);
  const [compareDepth, setCompareDepth] = useSV(2);
  // Semantic similarity ghost edges, computed in-browser from titles+tags+folder.
  const ghostEdgesRef = React.useRef([]); // [{a, b, score}]
  const [showGhostEdges, setShowGhostEdges] = useSV(!!persisted.showGhostEdges);
  const [ghostEdgesReady, setGhostEdgesReady] = useSV(false);
  // 3D mode: orbit camera defined by rotX (pitch), rotY (yaw). Stored on
  // state for the render path to read each frame.
  const [is3D, setIs3D] = useSV(!!persisted.is3D);
  const rot3DRef = React.useRef({ rotX: -0.3, rotY: 0.5 }); // gentle starting tilt

  // When 3D mode toggles ON, give nodes an aggressive z-scatter (always — not
  // just first-time, so the user sees the cloud puff into 3D every toggle).
  // When it toggles OFF, flatten z back to 0. Either way, re-warm the
  // simulation with a fresh freeze + warmup so motion is gentle.
  React.useEffect(() => {
    if (!state.nodes || !state.nodes.length) return;
    if (is3D) {
      // Cloud-wide radius so the spread feels coherent regardless of which
      // node is near the origin and which is at the rim.
      let cloudR = 150;
      for (const n of state.nodes) {
        const r = Math.hypot(n.x, n.y);
        if (r > cloudR) cloudR = r;
      }
      for (const n of state.nodes) {
        // Spread proportional to cloud radius so depth is visible relative
        // to width — without this, perspective barely registers.
        n.z = (Math.random() - 0.5) * cloudR * 1.6;
        n.vz = 0;
      }
    } else {
      for (const n of state.nodes) { n.z = 0; n.vz = 0; }
    }
    // Re-warm: short freeze, longer warmup → cloud floats into shape.
    state.freezeUntil = Date.now() + 600;
    state.warmupUntil = state.freezeUntil + 2000;
    state.energy = 1;
    wakeSim();
  }, [is3D]);

  // Global keyboard shortcuts: "/" filter, Cmd/Ctrl-P palette, arrows for graph nav.
  React.useEffect(() => {
    const onKey = (e) => {
      const t = e.target;
      const tag = t && t.tagName;
      const inField = tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable);

      // Cmd/Ctrl-P → command palette (works even from inputs).
      if ((e.metaKey || e.ctrlKey) && (e.key === 'p' || e.key === 'P')) {
        e.preventDefault();
        setPaletteOpen(true);
        setPaletteQuery('');
        return;
      }
      if (inField) return;

      // "/" focuses filter.
      if (e.key === '/') {
        e.preventDefault();
        filterRef.current && filterRef.current.focus();
        return;
      }

      // Arrow keys: move selection to nearest neighbor in that direction.
      const dirs = { ArrowRight: [1, 0], ArrowLeft: [-1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      if (dirs[e.key] && selected) {
        e.preventDefault();
        const [dx, dy] = dirs[e.key];
        const next = neighborInDirection(state, selected, dx, dy);
        if (next) {
          setSelected(next.id);
          // Pan toward selection.
          if (canvasRef.current) {
            const rect = canvasRef.current.getBoundingClientRect();
            state.pan.x = rect.width / 2 - next.x * state.zoom;
            state.pan.y = rect.height / 2 - next.y * state.zoom;
          }
          wakeSim();
        }
        return;
      }

      // Enter opens currently selected note.
      if (e.key === 'Enter' && selected && onOpenNote) {
        onOpenNote(selected);
        return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [selected]);

  // Persist on change.
  React.useEffect(() => {
    saveGraphPrefs({
      settings, showAllLabels, drawerOpen, localMode, colorMode, viewMode,
      hiddenIds: [...hiddenIds], pinned,
      clusterColoring, highlightOrphans, savedViews, clusterLabels,
      showGhostEdges, is3D,
    });
  }, [settings, showAllLabels, drawerOpen, localMode, colorMode, viewMode, hiddenIds, pinned,
      clusterColoring, highlightOrphans, savedViews, clusterLabels,
      showGhostEdges, is3D]);

  const _isMobileG = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;

  const [state, wakeSim, tick] = useForceGraph({
    nodes: [], edges: [], byId: {}, pan: {x:0,y:0}, zoom: 1, energy: 1,
    pulses: new Map(), settings: DEFAULT_SETTINGS,
  });

  state.activePath    = activePath;
  state.showAllLabels = showAllLabels;
  state.filter        = filter.trim();
  state.settings      = settings;
  state.colorMode     = colorMode;
  state.viewMode      = viewMode;
  state.hiddenIds     = hiddenIds;
  state.clusters      = clustersRef.current;
  state.clusterColoring = clusterColoring;
  state.clusterLabels = clusterLabels;
  state.highlightOrphans = highlightOrphans;
  state.shortestPath  = shortestPath;
  state.selectedSet   = selectedSet;
  state.linkDrag      = linkDrag;
  state.lassoRect     = lassoRect;
  state.agentActivity = agentActivityRef.current;
  state.timeScrub     = timeScrubEnabled ? timeScrub : null;
  // Compare mode: precompute the A and B BFS sets for render.
  if (compareSet && compareSet.aId && compareSet.bId
      && state.byId[compareSet.aId] && state.byId[compareSet.bId]) {
    const aSet = bfsLocal(state, compareSet.aId, compareDepth) || new Set();
    const bSet = bfsLocal(state, compareSet.bId, compareDepth) || new Set();
    const shared = new Set([...aSet].filter(id => bSet.has(id)));
    state.compare = { a: aSet, b: bSet, shared, aId: compareSet.aId, bId: compareSet.bId };
  } else {
    state.compare = null;
  }
  state.ghostEdges = showGhostEdges ? ghostEdgesRef.current : null;
  state.is3D = is3D;
  state.rot3D = rot3DRef.current;
  // Local-graph visible set: BFS from active note out to N hops.
  state.localVisible = (localMode !== 'global' && activePath)
    ? bfsLocal(state, activePath, parseInt(localMode, 10))
    : null;

  React.useEffect(() => {
    if (_isMobileG) {
      // Delay slightly so the canvas has its correct size
      const t = setTimeout(() => {
        if (canvasRef.current) {
          const rect = canvasRef.current.getBoundingClientRect();
          state.zoom = 0.3;
          state.pan.x = rect.width / 2;
          state.pan.y = rect.height / 2;
          wakeSim();
        }
      }, 300);
      return () => clearTimeout(t);
    }
  }, []);

  React.useEffect(() => {
    const fetchGraph = async () => {
      try {
        const g = await window.CafresoHQClient.vaultGraph();
        const r = Math.max(120, 30 + Math.sqrt(g.nodes.length) * 40);
        const wantZ = !!state.is3D;
        const nodes = g.nodes.map((n, i) => {
          const angle = (i / Math.max(1, g.nodes.length)) * Math.PI * 2;
          // Add a few px of jitter so no two nodes share coordinates (avoids force singularities).
          const jx = (Math.random() - 0.5) * 6;
          const jy = (Math.random() - 0.5) * 6;
          // If 3D mode is already on, seed z so the new data lands as a cloud
          // rather than a disk that has to puff out later.
          const z = wantZ ? (Math.random() - 0.5) * r * 1.6 : 0;
          return { ...n, x: Math.cos(angle) * r + jx, y: Math.sin(angle) * r + jy, z, vx: 0, vy: 0, vz: 0 };
        });
        const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
        const edges = g.edges.filter(e => byId[e.source] && byId[e.target]);
        // Restore any pinned positions from prefs.
        for (const id of Object.keys(pinned || {})) {
          const n = byId[id];
          if (n) { n.fx = pinned[id].x; n.fy = pinned[id].y; n.x = n.fx; n.y = n.fy; }
        }
        state.nodes = nodes;
        state.edges = edges;
        state.byId = byId;
        state.energy = 1;
        // Cache ranges for color-by-mode gradients.
        let maxIn = 0, mMin = Infinity, mMax = -Infinity;
        for (const n of nodes) {
          if ((n.inlinks || 0) > maxIn) maxIn = n.inlinks;
          if (n.mtime) { if (n.mtime < mMin) mMin = n.mtime; if (n.mtime > mMax) mMax = n.mtime; }
        }
        state.maxInlinks = maxIn;
        state.mtimeRange = mMin < mMax ? { min: mMin, max: mMax } : null;
        // Compute connected components for cluster coloring.
        clustersRef.current = connectedComponents(state);
        state.clusters = clustersRef.current;
        // Semantic similarity ghost edges are useful, but pairwise TF-IDF can
        // be heavy on larger vaults. Defer them until after the graph has
        // painted so startup animation stays responsive.
        ghostEdgesRef.current = [];
        setGhostEdgesReady(false);
        const runGhostEdges = () => {
          try {
            ghostEdgesRef.current = computeGhostEdges(state);
            setGhostEdgesReady(true);
            if (showGhostEdges) wakeSim();
          } catch (e) {
            ghostEdgesRef.current = [];
            setGhostEdgesReady(true);
          }
        };
        if (window.requestIdleCallback) {
          window.requestIdleCallback(runGhostEdges, { timeout: 1800 });
        } else {
          setTimeout(runGhostEdges, 250);
        }
        // Cache the raw graph payload for the agent runner shim.
        if (window.CafresoHQGraph) window.CafresoHQGraph._lastGraph = g;
        centeredOnRef.current = null; // allow re-centering on the active note when data lands
        // Hold the seed circle layout for ~1.4s, then ease physics in slowly
        // over ~2.4s so nodes drift into place rather than snapping.
        // simulate() reads these to scale forces and clamp peak velocity.
        state.freezeUntil = Date.now() + 1400;
        state.warmupUntil = state.freezeUntil + 2400;
        wakeSim();
      } catch (e) { console.warn('vaultGraph:', e); }
    };
    fetchGraph();
  }, []);

  React.useEffect(() => {
    window.CafresoHQGraph = {
      pulse: (nodeId) => {
        for (const edge of state.edges) {
          if (edge.source === nodeId || edge.target === nodeId) {
            state.pulses.set(edge.source + '\0' + edge.target, { start: Date.now(), edge });
          }
        }
        wakeSim();
      },
      refresh: async () => {
        try {
          const g = await window.CafresoHQClient.vaultGraph();
          const r = 200;
          const nodes = g.nodes.map((n, i) => {
            const angle = (i / Math.max(1, g.nodes.length)) * Math.PI * 2;
            return { ...n, x: Math.cos(angle) * r, y: Math.sin(angle) * r, vx: 0, vy: 0 };
          });
          const byId = Object.fromEntries(nodes.map(n => [n.id, n]));
          state.nodes = nodes;
          state.edges = g.edges.filter(e => byId[e.source] && byId[e.target]);
          state.byId = byId;
          state.energy = 1;
          wakeSim();
        } catch (e) {}
      },
    };
    return () => { delete window.CafresoHQGraph; };
  }, []);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // First-time pan centering — without this, the (0,0) world origin sits at
    // the canvas top-left and half the graph is offscreen.
    if (!centeredRef.current) {
      const rect = canvas.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        state.pan.x = rect.width / 2;
        state.pan.y = rect.height / 2;
        centeredRef.current = true;
      }
    }
    // When a note is opened, slide the graph so that node sits at canvas center.
    // Re-runs on every tick (cheap bail-out) until the node exists in byId
    // (data may load after activePath changes), then once until activePath flips.
    if (activePath && centeredOnRef.current !== activePath) {
      const n = state.byId[activePath];
      if (n) {
        const rect = canvas.getBoundingClientRect();
        if (rect.width > 0) {
          let cx = n.x, cy = n.y;
          if (state.is3D && state.rot3D) {
            const p = project3D(n.x, n.y, n.z || 0, state.rot3D.rotX, state.rot3D.rotY);
            cx = p.sx; cy = p.sy;
          }
          state.pan.x = rect.width / 2 - cx * state.zoom;
          state.pan.y = rect.height / 2 - cy * state.zoom;
          centeredOnRef.current = activePath;
          state.energy = 1;
          wakeSim();
        }
      }
    }
    if (is3D) render3D(canvas, state, hover, selected);
    else render(canvas, state, hover, selected);
  }, [tick, hover, selected, filter, activePath, colorMode, hiddenIds,
      selectedSet, lassoRect, linkDrag, activityTick, clusterColoring,
      clusterLabels, highlightOrphans, timeScrubEnabled, timeScrub, shortestPath,
      compareSet, compareDepth, showGhostEdges, ghostEdgesReady, is3D]);

  /* Live agent activity overlay. The rest of the app dispatches:
       window.dispatchEvent(new CustomEvent('cafresohq:agentActivity', {
         detail: { nodeId, agentId, agentName, color, kind: 'read'|'write'|'link', linkTo? }
       }))
     We track the recent activity per node so render() can draw avatars/pulses. */
  React.useEffect(() => {
    const handler = (e) => {
      const d = e.detail || {};
      if (!d.nodeId || !state.byId[d.nodeId]) return;
      const map = agentActivityRef.current;
      map.set(d.nodeId, {
        agentId: d.agentId,
        agentName: d.agentName || 'agent',
        color: d.color || '#7db5b5',
        kind: d.kind || 'read',
        until: Date.now() + 5000,
      });
      // Trigger pulses for write/link too.
      if ((d.kind === 'write' || d.kind === 'link') && window.CafresoHQGraph) {
        window.CafresoHQGraph.pulse(d.nodeId);
      }
      setActivityTick(t => t + 1);
    };
    window.addEventListener('cafresohq:agentActivity', handler);
    // Sweeper — drop expired entries and bump tick at ~12fps while activity
    // exists so the halo pulse keeps animating.
    const sweep = setInterval(() => {
      const now = Date.now();
      const map = agentActivityRef.current;
      let changed = false;
      for (const [k, v] of map) if (v.until < now) { map.delete(k); changed = true; }
      if (map.size > 0 || changed) setActivityTick(t => t + 1);
    }, 80);
    /* Cluster-label resolution from the agent runner. */
    const labelHandler = (e) => {
      const labels = e && e.detail && e.detail.labels;
      if (labels && typeof labels === 'object') {
        // Convert string-keys to numbers if possible.
        const norm = {};
        for (const [k, v] of Object.entries(labels)) norm[Number(k)] = String(v);
        setClusterLabels(prev => ({ ...prev, ...norm }));
      }
    };
    window.addEventListener('cafresohq:clusterLabelsResolved', labelHandler);

    return () => {
      window.removeEventListener('cafresohq:agentActivity', handler);
      window.removeEventListener('cafresohq:clusterLabelsResolved', labelHandler);
      clearInterval(sweep);
    };
  }, []);

  // Hover preview: 400ms after hover settles on a node, fetch and show
  // the first ~200 chars in a floating tooltip. Cache per id so re-hover
  // doesn't refetch.
  React.useEffect(() => {
    if (previewTimerRef.current) {
      clearTimeout(previewTimerRef.current);
      previewTimerRef.current = null;
    }
    if (!hover) { setPreviewNote(null); return; }
    const node = state.byId[hover];
    if (!node) return;
    previewTimerRef.current = setTimeout(async () => {
      const cache = previewCacheRef.current;
      let content = cache.get(hover);
      if (content === undefined) {
        try {
          content = await window.CafresoHQClient.vaultRead(hover);
        } catch (_) { content = null; }
        cache.set(hover, content);
      }
      // strip frontmatter and trim
      let body = (content || '').replace(/^---[\s\S]*?---\s*/, '').trim();
      if (body.length > 220) body = body.slice(0, 220) + '…';
      setPreviewNote({ id: hover, title: node.title || hover, content: body });
    }, 400);
    return () => {
      if (previewTimerRef.current) {
        clearTimeout(previewTimerRef.current);
        previewTimerRef.current = null;
      }
    };
  }, [hover]);

  /* Generate cluster labels. Tries an agent first (dispatches an event), and
     in parallel applies a heuristic fallback: pick the highest-inlinks node's
     title in each cluster, fallback to the most common tag, fallback to the
     folder name of the dominant member. */
  const generateClusterLabels = () => {
    if (!clustersRef.current) return;
    const { comp, count } = clustersRef.current;
    const buckets = Array.from({ length: count }, () => []);
    for (const n of state.nodes) {
      const idx = comp[n.id];
      if (idx != null) buckets[idx].push(n);
    }
    const labels = {};
    buckets.forEach((members, idx) => {
      if (members.length < 3) return;
      // 1) tag mode majority
      const tagCounts = new Map();
      for (const m of members) for (const t of (m.tags || [])) tagCounts.set(t, (tagCounts.get(t) || 0) + 1);
      const topTag = [...tagCounts.entries()].sort((a, b) => b[1] - a[1])[0];
      if (topTag && topTag[1] >= members.length / 3) {
        labels[idx] = topTag[0];
        return;
      }
      // 2) common folder
      const folderCounts = new Map();
      for (const m of members) {
        const folder = (m.id || '').split('/').slice(0, -1).join('/') || 'root';
        folderCounts.set(folder, (folderCounts.get(folder) || 0) + 1);
      }
      const topFolder = [...folderCounts.entries()].sort((a, b) => b[1] - a[1])[0];
      if (topFolder && topFolder[1] >= members.length / 2) {
        labels[idx] = topFolder[0].split('/').pop() || 'root';
        return;
      }
      // 3) hub node title
      const hub = [...members].sort((a, b) => (b.inlinks || 0) - (a.inlinks || 0))[0];
      labels[idx] = (hub.title || hub.id).replace(/\.md$/, '');
    });
    setClusterLabels(labels);
    // Also dispatch for an LLM agent to refine (the app can listen and
    // overwrite later with smarter labels).
    const ev = new CustomEvent('cafresohq:agentAction', {
      detail: {
        kind: 'labelClusters',
        clusters: buckets.map((members, idx) => ({
          idx, size: members.length,
          ids: members.map(m => m.id),
          titles: members.map(m => m.title || m.id),
          tags: [...new Set(members.flatMap(m => m.tags || []))],
        })).filter(c => c.size >= 3),
      },
    });
    window.dispatchEvent(ev);
    setStatusMsg({ text: `Labeled ${Object.keys(labels).length} clusters`, kind: 'info' });
  };

  /* Multi-select batch operations. */
  const selectionList = state.nodes.filter(n => selectedSet.has(n.id));
  const clearSelection = () => setSelectedSet(new Set());
  const hideSelection = () => {
    setHiddenIds(prev => {
      const next = new Set(prev);
      for (const id of selectedSet) next.add(id);
      return next;
    });
    clearSelection();
  };
  const sendSelectionToAgent = (agent) => {
    const ev = new CustomEvent('cafresohq:agentAction', {
      detail: {
        kind: 'batchMission',
        nodeIds: [...selectedSet],
        agentId: agent ? agent.id : null,
      },
    });
    window.dispatchEvent(ev);
    setStatusMsg({
      text: agent ? `${selectedSet.size} notes → ${agent.name}` : `${selectedSet.size} notes dispatched`,
      kind: 'info',
    });
    setBatchAgentOpen(false);
  };

  /* Saved view = snapshot of UI state. */
  const captureView = () => ({
    name: '',
    filter, colorMode, viewMode, localMode, clusterColoring, highlightOrphans,
    pan: { ...state.pan }, zoom: state.zoom,
    showAllLabels, settings,
  });
  const saveCurrentView = () => {
    const name = window.prompt('Name this view:');
    if (!name) return;
    const view = captureView(); view.name = name;
    setSavedViews(v => [...v, view]);
    setStatusMsg({ text: `Saved "${name}"`, kind: 'info' });
  };
  const applyView = (v) => {
    setFilter(v.filter || '');
    setColorMode(v.colorMode || 'tags');
    setViewMode(v.viewMode || 'free');
    setLocalMode(v.localMode || 'global');
    setClusterColoring(!!v.clusterColoring);
    setHighlightOrphans(!!v.highlightOrphans);
    setShowAllLabels(!!v.showAllLabels);
    if (v.settings) setSettings(v.settings);
    if (v.pan) { state.pan.x = v.pan.x; state.pan.y = v.pan.y; }
    if (v.zoom) state.zoom = v.zoom;
    state.energy = 1; wakeSim();
    setStatusMsg({ text: `Applied "${v.name}"`, kind: 'info' });
  };
  const deleteView = (idx) => {
    setSavedViews(v => v.filter((_, i) => i !== idx));
  };

  /* Export current canvas as PNG. */
  const exportPng = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    try {
      const url = canvas.toDataURL('image/png');
      const a = document.createElement('a');
      a.href = url;
      a.download = `vault-graph-${new Date().toISOString().slice(0,10)}.png`;
      document.body.appendChild(a); a.click(); document.body.removeChild(a);
      setStatusMsg({ text: 'Exported PNG', kind: 'info' });
    } catch (err) {
      setStatusMsg({ text: 'Export failed: ' + err.message, kind: 'error' });
    }
  };

  /* Agent actions — dispatched as CustomEvents so the rest of the app can hook
     in. Summaries request chat responses instead of writing Markdown files. */
  const dispatchAgentAction = (kind, payload) => {
    const ev = new CustomEvent('cafresohq:agentAction', { detail: { kind, ...payload } });
    window.dispatchEvent(ev);
  };

  const summarizeNote = async (node, includeNeighbors) => {
    setContextMenu(null);
    setStatusMsg({ text: `Reading ${node.id}…`, kind: 'info' });
    try {
      const own = await window.CafresoHQClient.vaultRead(node.id);
      let neighbors = [];
      if (includeNeighbors) {
        for (const e of state.edges) {
          const sid = e.source.id || e.source, tid = e.target.id || e.target;
          if (sid === node.id) neighbors.push(tid);
          else if (tid === node.id) neighbors.push(sid);
        }
        neighbors = [...new Set(neighbors)];
      }
      const neighborContents = await Promise.all(neighbors.slice(0, 8).map(async id => {
        try { return { id, body: await window.CafresoHQClient.vaultRead(id) }; }
        catch (_) { return null; }
      }));
      // Dispatch event for app-level runner. The runner will answer in the
      // floating chat window instead of writing a Markdown stub.
      dispatchAgentAction('summarize', {
        nodeId: node.id, includeNeighbors,
        responseMode: 'chat',
        ownContent: own,
        neighbors: neighborContents.filter(Boolean),
      });
      setStatusMsg({ text: 'Summarizing in chat…', kind: 'info' });
      if (window.cafresohqSetChatOpen) window.cafresohqSetChatOpen(true);
    } catch (err) {
      setStatusMsg({ text: 'Summarize failed: ' + err.message, kind: 'error' });
    }
  };

  const sendToAgent = (kind, node, agent) => {
    setAgentSubmenu(null);
    setContextMenu(null);
    dispatchAgentAction(kind, { nodeId: node.id, agentId: agent ? agent.id : null });
    setStatusMsg({
      text: agent ? `Dispatched "${kind}" to ${agent.name}` : `Dispatched "${kind}"`,
      kind: 'info',
    });
  };

  const safeVaultName = (s) => (s || 'untitled').replace(/\.md$/, '').replace(/[\\/:*?"<>|]/g, '_');

  const createTaskFromNode = async (node) => {
    setContextMenu(null);
    const title = safeVaultName(node.title || node.id);
    const path = `05-Projects/GraphView Tasks/${title}-task.md`;
    const body = `---\ntype: task\nsource: "[[${node.id}]]"\nstatus: proposed\ncreated: ${new Date().toISOString()}\n---\n\n# Task: Improve ${title}\n\n## Source\n[[${node.id}]]\n\n## Goal\nUse this graph node as context and define the next concrete implementation step.\n\n## Acceptance Criteria\n- [ ] Explain why this task exists\n- [ ] Link supporting research or decisions\n- [ ] Define a testable done state\n`;
    try {
      await window.CafresoHQClient.vaultWrite(path, body, 'write');
      setStatusMsg({ text: `Created task · ${path}`, kind: 'success' });
      if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) window.CafresoHQGraph.refresh();
    } catch (err) { setStatusMsg({ text: 'Task creation failed: ' + err.message, kind: 'error' }); }
  };

  const createProposalFromNode = async (node) => {
    setContextMenu(null);
    const title = safeVaultName(node.title || node.id);
    const path = `Research/Graphviewupdate/Proposals/${title}-proposal.md`;
    const body = `---\ntype: proposal\nsource: "[[${node.id}]]"\nstatus: draft\ncreated: ${new Date().toISOString()}\n---\n\n# Proposal: ${title}\n\n## Research / Source\n[[${node.id}]]\n\n## Insight\nWhat does this source teach us?\n\n## Proposed GraphView Behavior\nWhat should change in the UI or workflow?\n\n## Implementation Task\nWhat concrete task should be created?\n\n## Acceptance Criteria\n- [ ] User can understand why this exists\n- [ ] Behavior is visible in GraphView\n- [ ] Provenance is preserved\n`;
    try {
      await window.CafresoHQClient.vaultWrite(path, body, 'write');
      setStatusMsg({ text: `Created proposal · ${path}`, kind: 'success' });
      if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) window.CafresoHQGraph.refresh();
    } catch (err) { setStatusMsg({ text: 'Proposal creation failed: ' + err.message, kind: 'error' }); }
  };

  const applyOpinionatedMode = (mode) => {
    setViewMode(mode);
    if (mode === 'research') { setFilter('type:research OR path:Research'); setColorMode('type'); setLocalMode('global'); setClusterColoring(true); }
    else if (mode === 'execution') { setFilter('type:project OR type:task OR type:decision OR type:code_file'); setColorMode('type'); setLocalMode('global'); setClusterColoring(false); }
    else if (mode === 'agents') { setFilter('type:agent OR created_by OR assigned_to'); setColorMode('type'); setLocalMode('global'); }
    else if (mode === 'decisions') { setFilter('type:decision OR type:proposal'); setColorMode('type'); setLocalMode('global'); }
    else if (mode === 'stale') { setFilter('stale OR orphan'); setColorMode('heatmap'); setLocalMode('global'); setHighlightOrphans(true); }
    else { setFilter(''); setColorMode('tags'); }
    setDrawerOpen(true);
    wakeSim();
  };

  const recenter = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    state.pan.x = rect.width / 2;
    state.pan.y = rect.height / 2;
    state.zoom = _isMobileG ? 0.3 : 1;
    state.energy = 1;
    wakeSim();
  };

  const getNodeAt = (x, y) => {
    if (!canvasRef.current) return null;
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = (x - rect.left - state.pan.x) / state.zoom;
    const my = (y - rect.top - state.pan.y) / state.zoom;
    if (state.is3D) {
      // Test in projected screen space, prefer the front-most (smallest depth).
      let best = null, bestDepth = Infinity;
      for (let i = state.nodes.length - 1; i >= 0; i--) {
        const n = state.nodes[i];
        if (n._sx == null) continue; // not visible last frame
        if (state.hiddenIds && state.hiddenIds.has(n.id)) continue;
        const r = (3.5 + Math.sqrt(n.inlinks || 0) * 2.2) * (n._scale || 1);
        if (Math.hypot(mx - n._sx, my - n._sy) < r && n._depth < bestDepth) {
          best = n; bestDepth = n._depth;
        }
      }
      return best;
    }
    for (let i = state.nodes.length - 1; i >= 0; i--) {
      const n = state.nodes[i];
      const nr = 3.5 + Math.sqrt(n.inlinks || 0) * 2.2;
      if (Math.hypot(mx - n.x, my - n.y) < nr) return n;
    }
    return null;
  };

  const onWheel = (e) => {
    e.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const dx = (mx - state.pan.x) / state.zoom;
    const dy = (my - state.pan.y) / state.zoom;
    const newZoom = Math.max(0.2, Math.min(5, state.zoom * (1 - e.deltaY * 0.001)));
    state.pan.x = mx - dx * newZoom;
    state.pan.y = my - dy * newZoom;
    state.zoom = newZoom;
    wakeSim();
  };

  const onMouseDown = (e) => {
    state.dragging = true;
    state.dragStart = { x: e.clientX, y: e.clientY };
    state.panStart = { ...state.pan };
    const n = getNodeAt(e.clientX, e.clientY);
    // Ctrl/Cmd + drag from a node body → start "drag out an edge" gesture
    // to create a new wikilink in the source note.
    if (n && (e.ctrlKey || e.metaKey)) {
      state.linkDragging = true;
      const wr = wrapRef.current.getBoundingClientRect();
      setLinkDrag({
        fromId: n.id,
        x: e.clientX - wr.left,
        y: e.clientY - wr.top,
        endX: e.clientX - wr.left,
        endY: e.clientY - wr.top,
      });
      return;
    }
    // Shift + empty canvas → lasso multi-select.
    if (!n && e.shiftKey) {
      state.lassoActive = true;
      const wr = wrapRef.current.getBoundingClientRect();
      const x = e.clientX - wr.left, y = e.clientY - wr.top;
      setLassoRect({ x0: x, y0: y, x1: x, y1: y });
      return;
    }
    if (n) { state.dragNode = n; n.fx = n.x; n.fy = n.y; }
  };

  const onMouseMove = (e) => {
    // Track cursor relative to wrapper for tooltip + context menu positioning.
    if (wrapRef.current) {
      const wr = wrapRef.current.getBoundingClientRect();
      lastMouseRef.current = { x: e.clientX - wr.left, y: e.clientY - wr.top };
    }
    const n = getNodeAt(e.clientX, e.clientY);
    setHover(n ? n.id : null);

    // Lasso rectangle update.
    if (state.lassoActive) {
      const wr = wrapRef.current.getBoundingClientRect();
      setLassoRect(prev => prev ? { ...prev, x1: e.clientX - wr.left, y1: e.clientY - wr.top } : null);
      return;
    }
    // Link-drag rubber-band line.
    if (state.linkDragging) {
      const wr = wrapRef.current.getBoundingClientRect();
      setLinkDrag(prev => prev ? { ...prev, endX: e.clientX - wr.left, endY: e.clientY - wr.top } : null);
      return;
    }
    if (!state.dragging) return;
    if (state.dragNode) {
      const dx = (e.clientX - state.dragStart.x) / state.zoom;
      const dy = (e.clientY - state.dragStart.y) / state.zoom;
      state.dragNode.fx += dx;
      state.dragNode.fy += dy;
      state.dragStart = { x: e.clientX, y: e.clientY };
    } else if (state.is3D) {
      // 3D: drag empty = orbit camera (yaw + pitch).
      const dx = e.clientX - state.dragStart.x;
      const dy = e.clientY - state.dragStart.y;
      rot3DRef.current.rotY += dx * 0.005;
      rot3DRef.current.rotX += dy * 0.005;
      // Clamp pitch so the cloud doesn't flip upside-down.
      const lim = Math.PI / 2 - 0.05;
      if (rot3DRef.current.rotX >  lim) rot3DRef.current.rotX =  lim;
      if (rot3DRef.current.rotX < -lim) rot3DRef.current.rotX = -lim;
      state.dragStart = { x: e.clientX, y: e.clientY };
    } else {
      state.pan.x = state.panStart.x + e.clientX - state.dragStart.x;
      state.pan.y = state.panStart.y + e.clientY - state.dragStart.y;
    }
    wakeSim();
  };

  const onMouseUp = async (e) => {
    state.dragging = false;
    // Finish lasso → collect nodes inside the rect.
    if (state.lassoActive && lassoRect) {
      state.lassoActive = false;
      const x0 = Math.min(lassoRect.x0, lassoRect.x1);
      const y0 = Math.min(lassoRect.y0, lassoRect.y1);
      const x1 = Math.max(lassoRect.x0, lassoRect.x1);
      const y1 = Math.max(lassoRect.y0, lassoRect.y1);
      const wr = wrapRef.current.getBoundingClientRect();
      const picked = new Set();
      for (const n of state.nodes) {
        if (state.hiddenIds && state.hiddenIds.has(n.id)) continue;
        // In 3D, use the cached projected coords; in 2D, use raw x/y.
        const wx = state.is3D && n._sx != null ? n._sx : n.x;
        const wy = state.is3D && n._sy != null ? n._sy : n.y;
        const sx = state.pan.x + wx * state.zoom;
        const sy = state.pan.y + wy * state.zoom;
        if (sx >= x0 && sx <= x1 && sy >= y0 && sy <= y1) picked.add(n.id);
      }
      setSelectedSet(picked);
      setLassoRect(null);
      if (picked.size > 0) setStatusMsg({ text: `${picked.size} selected · use the bar below`, kind: 'info' });
      return;
    }
    // Finish link-drag → if released on another node, write a [[wikilink]].
    if (state.linkDragging && linkDrag) {
      state.linkDragging = false;
      const target = e ? getNodeAt(e.clientX, e.clientY) : null;
      const fromId = linkDrag.fromId;
      setLinkDrag(null);
      if (target && target.id !== fromId) {
        try {
          const body = await window.CafresoHQClient.vaultRead(fromId);
          // Prevent duplicate links.
          const linkText = `[[${target.title || target.id.replace(/\.md$/, '')}]]`;
          if (!body.includes(linkText)) {
            const newBody = body.replace(/\s*$/, '\n\n') + linkText + '\n';
            await window.CafresoHQClient.vaultWrite(fromId, newBody, 'write');
            setStatusMsg({ text: `Linked → ${target.title || target.id}`, kind: 'info' });
            if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) window.CafresoHQGraph.refresh();
          } else {
            setStatusMsg({ text: 'Link already exists', kind: 'warn' });
          }
        } catch (err) {
          setStatusMsg({ text: 'Link failed: ' + err.message, kind: 'error' });
        }
      }
      return;
    }
    if (state.dragNode) {
      state.dragNode.fx = null; state.dragNode.fy = null; state.dragNode = null;
      wakeSim();
    }
  };

  const onClick = (e) => {
    if (state.dragStart && Math.hypot(e.clientX - state.dragStart.x, e.clientY - state.dragStart.y) > 5) return;
    const n = getNodeAt(e.clientX, e.clientY);
    // Shift-click → shortest-path workflow. First shift-click sets the source
    // endpoint, second computes and shows the path. Third resets.
    if (e.shiftKey && n) {
      setPathEndpoints(prev => {
        if (prev.length === 0) {
          setShortestPath(null);
          return [n.id];
        }
        if (prev.length === 1 && prev[0] !== n.id) {
          const path = shortestPathBetween(state, prev[0], n.id);
          if (path) {
            const nodeSet = new Set(path);
            const edgeSet = new Set();
            for (let i = 0; i < path.length - 1; i++) {
              const a = path[i], b = path[i + 1];
              edgeSet.add(a < b ? a + '\0' + b : b + '\0' + a);
            }
            setShortestPath({ nodes: nodeSet, edges: edgeSet, ordered: path });
            setStatusMsg({ text: `Path · ${path.length - 1} hop${path.length === 2 ? '' : 's'}`, kind: 'info' });
          } else {
            setShortestPath(null);
            setStatusMsg({ text: 'No path between selected nodes', kind: 'warn' });
          }
          return [prev[0], n.id];
        }
        // Reset on third shift-click.
        setShortestPath(null);
        return [n.id];
      });
      wakeSim();
      return;
    }
    // Ghost-edge click → offer to materialize into a real link.
    if (!n && showGhostEdges && ghostEdgesRef.current.length) {
      const rect = canvasRef.current.getBoundingClientRect();
      const wx = (e.clientX - rect.left - state.pan.x) / state.zoom;
      const wy = (e.clientY - rect.top  - state.pan.y) / state.zoom;
      // Find ghost edge whose segment is closest to (wx,wy), within ~6px world.
      let best = null, bestD = Infinity;
      for (const ge of ghostEdgesRef.current) {
        const a = state.byId[ge.a], b = state.byId[ge.b];
        if (!a || !b) continue;
        // Distance from point to segment.
        const dx = b.x - a.x, dy = b.y - a.y;
        const len2 = dx*dx + dy*dy || 1;
        let t = ((wx - a.x)*dx + (wy - a.y)*dy) / len2;
        t = Math.max(0, Math.min(1, t));
        const px = a.x + t*dx, py = a.y + t*dy;
        const d = Math.hypot(wx - px, wy - py);
        if (d < bestD) { bestD = d; best = ge; }
      }
      if (best && bestD < 6 / state.zoom) {
        const a = state.byId[best.a], b = state.byId[best.b];
        if (a && b && window.confirm(`Add link from "${a.title || a.id}" to "${b.title || b.id}"? (similarity ${(best.score*100).toFixed(0)}%)`)) {
          (async () => {
            try {
              const body = await window.CafresoHQClient.vaultRead(a.id);
              const linkText = `[[${b.title || b.id.replace(/\.md$/,'')}]]`;
              if (!body.includes(linkText)) {
                const newBody = body.replace(/\s*$/, '\n\n') + linkText + '\n';
                await window.CafresoHQClient.vaultWrite(a.id, newBody, 'write');
                setStatusMsg({ text: `Linked → ${b.title || b.id}`, kind: 'info' });
                if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) window.CafresoHQGraph.refresh();
              }
            } catch (err) {
              setStatusMsg({ text: 'Link failed: ' + err.message, kind: 'error' });
            }
          })();
        }
        return;
      }
    }
    // Plain click — clear path and select / open.
    if (shortestPath) { setShortestPath(null); setPathEndpoints([]); }
    if (n) {
      setSelected(n.id);
      setDrawerOpen(true);
      if (onOpenNote) onOpenNote(n.id);
      for (const edge of state.edges) {
        if (edge.source === n.id) {
          state.pulses.set(edge.source + '\0' + edge.target, { start: Date.now(), edge });
        }
      }
      wakeSim();
    } else {
      setSelected(null);
    }
  };

  /* Double-click empty canvas → quick-create note at click position. */
  const onDoubleClick = async (e) => {
    const n = getNodeAt(e.clientX, e.clientY);
    if (n) return; // double-click on a node falls through to default open
    const name = window.prompt('New note path (e.g. "Inbox/idea.md"):');
    if (!name) return;
    const path = name.endsWith('.md') ? name : name + '.md';
    try {
      const title = path.split('/').pop().replace(/\.md$/, '');
      await window.CafresoHQClient.vaultWrite(path, `# ${title}\n\n`, 'write');
      setStatusMsg({ text: `Created ${path}`, kind: 'info' });
      // Refresh graph data; the new node will appear at the canvas-center coords.
      if (window.CafresoHQGraph && window.CafresoHQGraph.refresh) {
        await window.CafresoHQGraph.refresh();
      }
      // Place it near the click point so it's visible immediately.
      setTimeout(() => {
        const node = state.byId[path];
        if (!node || !canvasRef.current) return;
        const rect = canvasRef.current.getBoundingClientRect();
        const wx = (e.clientX - rect.left - state.pan.x) / state.zoom;
        const wy = (e.clientY - rect.top  - state.pan.y) / state.zoom;
        node.x = wx; node.y = wy; node.vx = 0; node.vy = 0;
        wakeSim();
      }, 100);
    } catch (err) {
      setStatusMsg({ text: 'Create failed: ' + err.message, kind: 'error' });
    }
  };

  /* Right-click → context menu over a node. */
  const onContextMenu = (e) => {
    e.preventDefault();
    const node = getNodeAt(e.clientX, e.clientY);
    if (!node) { setContextMenu(null); return; }
    const wr = wrapRef.current.getBoundingClientRect();
    setContextMenu({ x: e.clientX - wr.left, y: e.clientY - wr.top, node });
  };

  /* Close menu on outside click or Esc. */
  React.useEffect(() => {
    if (!contextMenu) return;
    const close = () => setContextMenu(null);
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', onKey);
    };
  }, [contextMenu]);

  const togglePin = (node) => {
    const id = node.id;
    setPinned(prev => {
      const next = { ...prev };
      if (next[id]) {
        delete next[id];
        node.fx = null; node.fy = null;
      } else {
        next[id] = { x: node.x, y: node.y };
        node.fx = node.x; node.fy = node.y;
      }
      return next;
    });
    state.energy = 1;
    wakeSim();
    setContextMenu(null);
  };

  const hideNode = (node) => {
    setHiddenIds(prev => {
      const next = new Set(prev);
      next.add(node.id);
      return next;
    });
    setContextMenu(null);
  };

  const showAllHidden = () => setHiddenIds(new Set());

  const openNodeInObsidian = async (node) => {
    try { await window.CafresoHQClient.vaultOpenInObsidian(node.id); }
    catch (e) { /* swallow */ }
    setContextMenu(null);
  };

  const canvasProps = {
    ref: canvasRef,
    onWheel, onMouseDown, onMouseMove, onMouseUp, onClick,
    onDoubleClick,
    onContextMenu,
    onMouseLeave: () => { state.dragging = false; setHover(null); },
  };

  /* Touch handlers — single finger pan, two-finger pinch zoom, tap to select */
  canvasProps.onTouchStart = (e) => {
    if (e.touches.length === 1) {
      const t = e.touches[0];
      state.dragging = true;
      state.dragStart = { x: t.clientX, y: t.clientY };
      state.panStart = { ...state.pan };
      state._touchMoved = false;
      const n = getNodeAt(t.clientX, t.clientY);
      state._touchNode = n;
      if (n) { state.dragNode = n; n.fx = n.x; n.fy = n.y; }
    } else if (e.touches.length === 2) {
      state.dragging = false; state.dragNode = null;
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      state._pinchDist = Math.hypot(dx, dy);
      state._pinchMidX = (e.touches[0].clientX + e.touches[1].clientX) / 2;
      state._pinchMidY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
    }
  };
  canvasProps.onTouchMove = (e) => {
    if (e.touches.length === 1 && state.dragging) {
      const t = e.touches[0];
      const dx = t.clientX - state.dragStart.x;
      const dy = t.clientY - state.dragStart.y;
      if (Math.hypot(dx, dy) > 3) state._touchMoved = true;
      if (state.dragNode) {
        state.dragNode.fx += dx / state.zoom;
        state.dragNode.fy += dy / state.zoom;
        state.dragStart = { x: t.clientX, y: t.clientY };
      } else {
        state.pan.x = state.panStart.x + dx;
        state.pan.y = state.panStart.y + dy;
      }
      wakeSim();
    } else if (e.touches.length === 2 && state._pinchDist != null) {
      const dx = e.touches[0].clientX - e.touches[1].clientX;
      const dy = e.touches[0].clientY - e.touches[1].clientY;
      const newDist = Math.hypot(dx, dy);
      const rect = canvasRef.current.getBoundingClientRect();
      const mx = state._pinchMidX - rect.left;
      const my = state._pinchMidY - rect.top;
      const ox = (mx - state.pan.x) / state.zoom;
      const oy = (my - state.pan.y) / state.zoom;
      state.zoom = Math.max(0.2, Math.min(5, state.zoom * (newDist / state._pinchDist)));
      state.pan.x = mx - ox * state.zoom;
      state.pan.y = my - oy * state.zoom;
      state._pinchDist = newDist;
      wakeSim();
    }
  };
  canvasProps.onTouchEnd = () => {
    state.dragging = false;
    if (!state._touchMoved && state._touchNode) {
      const n = state._touchNode;
      setSelected(n.id);
      setDrawerOpen(true);
      if (onOpenNote) onOpenNote(n.id);
      for (const edge of state.edges) {
        if (edge.source === n.id) state.pulses.set(edge.source + '\0' + edge.target, { start: Date.now(), edge });
      }
      wakeSim();
    }
    if (state.dragNode) { state.dragNode.fx = null; state.dragNode.fy = null; state.dragNode = null; }
    state._pinchDist = null; state._touchNode = null; state._touchMoved = false;
  };

  const setCfg = (key, val) => setSettings(s => ({ ...s, [key]: val }));

  /* Obsidian-style floating settings panel */
  const settingsPanel = showSettings && (
    <div
      onMouseDown={e => e.stopPropagation()}
      onWheel={e => e.stopPropagation()}
      onTouchStart={e => e.stopPropagation()}
      style={{
        position: 'absolute', top: 44, left: 8, right: 8, zIndex: 6,
        pointerEvents: 'auto',
        background: 'var(--paper, #f6f1e6)',
        color: 'var(--ink)',
        border: '1px solid var(--rule, #cdbfa5)',
        borderRadius: 6,
        padding: 10,
        maxWidth: 320,
        fontSize: 10,
        boxShadow: '0 4px 16px rgba(0,0,0,0.18)',
        display: 'flex', flexDirection: 'column', gap: 8,
      }}
    >
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <span style={{fontWeight:600,letterSpacing:1}}>FORCES</span>
        <button className="px-btn ghost" style={{fontSize:9,padding:'2px 6px'}} onClick={() => setSettings(DEFAULT_SETTINGS)}>RESET</button>
      </div>
      {[
        { key: 'centerForce',  label: 'Center force',  min: 0,    max: 0.005, step: 0.0001 },
        { key: 'repelForce',   label: 'Repel force',   min: 100,  max: 2500,  step: 25 },
        { key: 'linkForce',    label: 'Link force',    min: 0,    max: 0.1,   step: 0.001 },
        { key: 'linkDistance', label: 'Link distance', min: 30,   max: 400,   step: 5 },
        { key: 'layerForce',   label: 'Layer (out→in)',min: 0,    max: 0.02,  step: 0.0005 },
      ].map(s => (
        <label key={s.key} style={{display:'flex',flexDirection:'column',gap:2}}>
          <span style={{display:'flex',justifyContent:'space-between'}}>
            <span>{s.label}</span>
            <span style={{opacity:0.6}}>{Number(settings[s.key]).toFixed(s.step < 0.01 ? 4 : s.step < 1 ? 3 : 0)}</span>
          </span>
          <input type="range"
            min={s.min} max={s.max} step={s.step}
            value={settings[s.key]}
            onChange={e => { setCfg(s.key, parseFloat(e.target.value)); wakeSim(); }}
          />
        </label>
      ))}
      <div style={{borderTop:'1px solid var(--rule)',paddingTop:6,display:'flex',flexDirection:'column',gap:6}}>
        <span style={{fontWeight:600,letterSpacing:1,fontSize:9}}>DISPLAY</span>

        <label style={{display:'flex',flexDirection:'column',gap:2}}>
          <span style={{fontSize:9,opacity:0.7}}>Color by</span>
          <select
            value={colorMode}
            onChange={e => setColorMode(e.target.value)}
            style={{fontSize:10,padding:'2px 4px',background:'var(--paper)',color:'var(--ink)',border:'1px solid var(--rule)',borderRadius:3}}
          >
            <option value="tags">Tags</option>
            <option value="folder">Folder</option>
            <option value="modified" disabled={!state.mtimeRange}>Last modified (range)</option>
            <option value="heatmap"  disabled={!state.mtimeRange}>Heatmap (recency 🔥)</option>
            <option value="inlinks">Inlinks</option>
            <option value="type">Type / provenance</option>
          </select>
        </label>

        <label style={{display:'flex',alignItems:'center',gap:4}}>
          <input type="checkbox" checked={showAllLabels} onChange={e => setShowAllLabels(e.target.checked)} />
          Show all labels
        </label>
        <label style={{display:'flex',alignItems:'center',gap:4}}>
          <input type="checkbox" checked={clusterColoring} onChange={e => setClusterColoring(e.target.checked)} />
          Cluster coloring
          <span style={{fontSize:9,opacity:0.55,marginLeft:'auto'}}>
            {clustersRef.current ? `${clustersRef.current.count}` : ''}
          </span>
        </label>
        <label style={{display:'flex',alignItems:'center',gap:4}}>
          <input type="checkbox" checked={highlightOrphans} onChange={e => setHighlightOrphans(e.target.checked)} />
          Highlight orphans/dead-ends
        </label>
        <label style={{display:'flex',alignItems:'center',gap:4}}>
          <input type="checkbox" checked={showGhostEdges} onChange={e => setShowGhostEdges(e.target.checked)} disabled={!ghostEdgesReady} />
          Suggest similar links {ghostEdgesReady && <span style={{fontSize:9,opacity:0.55,marginLeft:'auto'}}>{ghostEdgesRef.current.length} found</span>}
        </label>
        <label style={{display:'flex',alignItems:'center',gap:4}}
               title="Color edges by their semantic relationship: cites (amber), supports (green), contradicts (red dashed), child_of (blue), supersedes (orange dashed), etc.">
          <input type="checkbox"
                 checked={!!settings.colorEdgesByType}
                 onChange={e => setCfg('colorEdgesByType', e.target.checked)} />
          🔗 Color edges by type
        </label>
        <label style={{display:'flex',alignItems:'center',gap:4}}>
          <input type="checkbox" checked={is3D} onChange={e => setIs3D(e.target.checked)} />
          🎲 3D mode <span style={{fontSize:9,opacity:0.55,marginLeft:'auto'}}>{is3D ? 'drag empty to orbit' : ''}</span>
        </label>
        {compareSet && (
          <div style={{display:'flex',gap:4,alignItems:'center',fontSize:9,padding:'4px 6px',background:'var(--paper-2)',borderRadius:3}}>
            <span style={{flex:1,opacity:0.7}}>Compare mode active</span>
            <button
              onClick={() => setCompareSet(null)}
              style={{fontSize:9,padding:'1px 5px',border:'1px solid var(--rule)',borderRadius:3,background:'transparent',color:'var(--ink)',cursor:'pointer'}}
            >Exit</button>
          </div>
        )}

        {hiddenIds.size > 0 && (
          <button
            onClick={showAllHidden}
            style={{fontSize:9,padding:'3px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'transparent',color:'var(--ink)',cursor:'pointer'}}
            title="Restore nodes hidden via right-click"
          >Show {hiddenIds.size} hidden</button>
        )}

        <div style={{display:'flex',flexDirection:'column',gap:3}}>
          <span style={{fontSize:9,opacity:0.7}}>Scope · {activePath ? 'active note' : 'no note open'}</span>
          <div style={{display:'flex',gap:3}}>
            {[
              { v: 'global', label: 'Global' },
              { v: '1',      label: 'Local 1' },
              { v: '2',      label: 'Local 2' },
              { v: '3',      label: 'Local 3' },
            ].map(opt => (
              <button
                key={opt.v}
                onClick={() => setLocalMode(opt.v)}
                disabled={opt.v !== 'global' && !activePath}
                style={{
                  flex: 1, fontSize: 9, padding: '3px 4px',
                  border: '1px solid var(--rule)', borderRadius: 3,
                  background: localMode === opt.v ? 'var(--paper-2)' : 'transparent',
                  color: 'var(--ink)', cursor: 'pointer',
                  opacity: (opt.v !== 'global' && !activePath) ? 0.4 : 1,
                }}
              >{opt.label}</button>
            ))}
          </div>
        </div>

        <div style={{display:'flex',justifyContent:'space-between',fontSize:9,opacity:0.65}}>
          <span>{state.nodes.length} nodes · {state.edges.length} links</span>
          {state.localVisible && <span>{state.localVisible.size} visible</span>}
        </div>

        <div style={{display:'flex',gap:4}}>
          <button
            onClick={recenter}
            style={{flex:1,fontSize:10,padding:'4px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'var(--paper-2)',color:'var(--ink)',cursor:'pointer'}}
          >↻ Recenter</button>
          <button
            onClick={exportPng}
            style={{flex:1,fontSize:10,padding:'4px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'var(--paper-2)',color:'var(--ink)',cursor:'pointer'}}
            title="Save current canvas as PNG"
          >📷 PNG</button>
          {/* Popout button — hide if we're already inside a popout window
              (window.opener is set on popouts spawned via window.open). */}
          {!window.opener && (
            <button
              onClick={() => {
                /* Open the popout window — same origin, popout=graph flag.
                   The popout listens on BroadcastChannel('cafresohq-graph')
                   so click sync works in both directions. */
                const url = window.location.pathname + '?popout=graph';
                const w = window.open(url, 'cafresohqGraphPopout', 'width=900,height=700,menubar=no,toolbar=no');
                if (w) {
                  if (window.cafresohqToast) window.cafresohqToast.success('Graph popped out · drag to your second monitor');
                } else {
                  if (window.cafresohqToast) window.cafresohqToast.warn('Popup blocked — allow popups for this site');
                }
              }}
              style={{flex:1,fontSize:10,padding:'4px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'var(--paper-2)',color:'var(--ink)',cursor:'pointer'}}
              title="Open this graph in a separate window"
            >🪟 POP OUT</button>
          )}
        </div>

        <div style={{borderTop:'1px solid var(--rule)',paddingTop:6,display:'flex',flexDirection:'column',gap:4}}>
          <span style={{fontWeight:600,letterSpacing:1,fontSize:9}}>VIEWS</span>
          {savedViews.length === 0 && <span style={{fontSize:9,opacity:0.5}}>No saved views yet.</span>}
          {savedViews.map((v, i) => (
            <div key={i} style={{display:'flex',gap:4,alignItems:'center'}}>
              <button
                onClick={() => applyView(v)}
                style={{flex:1,textAlign:'left',fontSize:10,padding:'3px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'transparent',color:'var(--ink)',cursor:'pointer',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}
              >{v.name}</button>
              <button
                onClick={() => deleteView(i)}
                style={{fontSize:10,padding:'3px 5px',border:'1px solid var(--rule)',borderRadius:3,background:'transparent',color:'var(--ink)',cursor:'pointer',opacity:0.6}}
                title="Delete view"
              >✕</button>
            </div>
          ))}
          <button
            onClick={saveCurrentView}
            style={{fontSize:10,padding:'4px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'var(--paper-2)',color:'var(--ink)',cursor:'pointer'}}
          >+ Save current view</button>
        </div>

        <div style={{fontSize:9,opacity:0.45,paddingTop:4,lineHeight:1.45}}>
          Shift-click 2 nodes for shortest path · Shift-drag to lasso · Ctrl-drag to link · ⌘P palette
          {is3D && ' · drag empty space to orbit · scroll to dolly'}
        </div>
      </div>

      {/* Insights tab */}
      <div style={{borderTop:'1px solid var(--rule)',paddingTop:6,display:'flex',flexDirection:'column',gap:6}}>
        <button
          onClick={() => setShowInsights(v => !v)}
          style={{display:'flex',justifyContent:'space-between',alignItems:'center',background:'transparent',border:'none',color:'var(--ink)',cursor:'pointer',padding:0,fontSize:9,fontWeight:600,letterSpacing:1}}
        >
          <span>INSIGHTS</span><span style={{opacity:0.55}}>{showInsights ? '▾' : '▸'}</span>
        </button>
        {showInsights && (() => {
          const orphans  = state.nodes.filter(n => (n.inlinks || 0) === 0).length;
          const deadEnds = state.nodes.filter(n => (n.outlinks || 0) === 0).length;
          const recent   = state.mtimeRange
            ? state.nodes.filter(n => n.mtime && Date.now() - n.mtime < 7*24*3600*1000).length
            : 0;
          const hubs = [...state.nodes].sort((a, b) => (b.inlinks || 0) - (a.inlinks || 0)).slice(0, 3);
          const clusterCount = clustersRef.current ? clustersRef.current.count : 0;
          const stat = (label, value, action) => (
            <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',fontSize:10}}>
              <span style={{opacity:0.75}}>{label}</span>
              {action ? (
                <button
                  onClick={action}
                  style={{fontSize:10,padding:'1px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'var(--paper-2)',color:'var(--ink)',cursor:'pointer'}}
                >{value}</button>
              ) : (<span style={{fontWeight:600}}>{value}</span>)}
            </div>
          );
          return (
            <div style={{display:'flex',flexDirection:'column',gap:4}}>
              {stat('Notes', state.nodes.length)}
              {stat('Links', state.edges.length)}
              {stat('Clusters', clusterCount, () => setClusterColoring(true))}
              {stat('Orphans (no inlinks)', orphans, () => { setHighlightOrphans(true); })}
              {stat('Dead-ends (no outlinks)', deadEnds, () => { setHighlightOrphans(true); })}
              {stat('Recent (7 days)', recent, () => setColorMode('modified'))}
              <div style={{paddingTop:4,borderTop:'1px dashed var(--rule)'}}>
                <div style={{fontSize:9,opacity:0.6,marginBottom:2}}>Top hubs</div>
                {hubs.length === 0 && <div style={{fontSize:10,opacity:0.5}}>—</div>}
                {hubs.map(h => (
                  <button
                    key={h.id}
                    onClick={() => { setSelected(h.id); if (onOpenNote) onOpenNote(h.id); }}
                    style={{display:'block',width:'100%',textAlign:'left',background:'transparent',border:'none',color:'var(--ink)',cursor:'pointer',fontSize:10,padding:'2px 0',whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}
                  >· {(h.title || h.id).replace(/\.md$/,'')} <span style={{opacity:0.55}}>· {h.inlinks||0}</span></button>
                ))}
              </div>
              <button
                onClick={generateClusterLabels}
                style={{fontSize:10,padding:'4px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'var(--paper-2)',color:'var(--ink)',cursor:'pointer',marginTop:4}}
                title="Auto-name each cluster (heuristic + agent dispatch)"
              >✨ Generate cluster labels</button>
              {Object.keys(clusterLabels).length > 0 && (
                <button
                  onClick={() => setClusterLabels({})}
                  style={{fontSize:9,padding:'2px 6px',border:'1px solid var(--rule)',borderRadius:3,background:'transparent',color:'var(--ink)',cursor:'pointer',opacity:0.6}}
                >Clear labels</button>
              )}
            </div>
          );
        })()}
      </div>

      {/* Time scrubber */}
      <div style={{borderTop:'1px solid var(--rule)',paddingTop:6,display:'flex',flexDirection:'column',gap:4}}>
        <label style={{display:'flex',alignItems:'center',gap:4,fontSize:10}}>
          <input type="checkbox" checked={timeScrubEnabled} onChange={e => setTimeScrubEnabled(e.target.checked)} disabled={!state.mtimeRange} />
          Time travel (mtime ≤ scrub)
        </label>
        {!state.mtimeRange && <span style={{fontSize:9,opacity:0.5}}>No mtime data available.</span>}
      </div>
    </div>
  );

  /* Top overlay bar — title + filter + settings toggle.
     Deliberately NOT using the `.graph-overlay` class because that class sets
     `pointer-events: none`, which makes its children unclickable. */
  const overlayBtn = {
    fontSize: 11,
    padding: '3px 7px',
    background: 'var(--paper)',
    border: '1px solid var(--rule)',
    borderRadius: 4,
    color: 'var(--ink)',
    cursor: 'pointer',
    pointerEvents: 'auto',
    lineHeight: 1,
  };

  const topOverlay = (
    <div
      onMouseDown={e => e.stopPropagation()}
      onWheel={e => e.stopPropagation()}
      style={{
        position: 'absolute', top: 8, left: 8, right: 8, zIndex: 4,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 8, pointerEvents: 'none',
      }}
    >
      <div style={{display:'flex',alignItems:'center',gap:6,pointerEvents:'auto'}}>
        <button
          style={{...overlayBtn, background: showSettings ? 'var(--paper-2)' : 'var(--paper)'}}
          onClick={() => setShowSettings(v => !v)}
          title="Forces & display"
        >⚙</button>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: 1,
          color: 'var(--ink)',
          background: 'var(--paper)',
          padding: '3px 7px',
          border: '1px solid var(--rule)',
          borderRadius: 4,
        }}>VAULT GRAPH</span>
        <select
          value={viewMode}
          onChange={e => applyOpinionatedMode(e.target.value)}
          title="Research-backed graph modes"
          style={{fontSize:10,padding:'3px 6px',background:'var(--paper)',color:'var(--ink)',border:'1px solid var(--rule)',borderRadius:4,pointerEvents:'auto'}}
        >
          <option value="free">Free</option>
          <option value="research">Research Map</option>
          <option value="execution">Execution Map</option>
          <option value="agents">Agent Map</option>
          <option value="decisions">Decision Map</option>
          <option value="stale">Stale Map</option>
        </select>
        <button style={{...overlayBtn, background: drawerOpen ? 'var(--paper-2)' : 'var(--paper)'}} onClick={() => setDrawerOpen(v => !v)} title="Provenance drawer">ⓘ</button>
      </div>
      <div style={{display:'flex',alignItems:'center',gap:6,pointerEvents:'auto'}}>
        <input
          ref={filterRef}
          value={filter}
          onChange={e => setFilter(e.target.value)}
          placeholder="filter… type:research path:Projects stale"
          style={{
            fontSize: 11, padding: '3px 7px', width: 150,
            background: 'var(--paper)', border: '1px solid var(--rule)',
            borderRadius: 4, color: 'var(--ink)', outline: 'none',
          }}
          onMouseDown={e => e.stopPropagation()}
          onKeyDown={e => { if (e.key === 'Escape') { setFilter(''); e.target.blur(); } }}
        />
        {filter && (
          <button
            style={{...overlayBtn, padding:'3px 6px', fontSize:10}}
            onClick={() => setFilter('')}
            title="Clear filter"
          >×</button>
        )}
        <button style={overlayBtn} onClick={recenter} title="Recenter">⌖</button>
        {embedded && onMinimize && (
          <button style={overlayBtn} onClick={onMinimize} title="Minimize graph">－</button>
        )}
      </div>
    </div>
  );

  /* Right-click context menu over a node. */
  const ctxMenuItem = {
    display:'block', width:'100%', textAlign:'left',
    fontSize:11, padding:'6px 10px',
    background:'transparent', color:'var(--ink)',
    border:'none', cursor:'pointer',
  };
  const ctxSection = {
    fontSize: 9, fontWeight: 700, letterSpacing: 1,
    color: 'var(--ink)', opacity: 0.55,
    padding: '6px 10px 2px', textTransform: 'uppercase',
  };
  const contextMenuJsx = contextMenu && (
    <div
      onMouseDown={e => e.stopPropagation()}
      style={{
        position:'absolute', left: contextMenu.x, top: contextMenu.y, zIndex: 8,
        minWidth: 220,
        background: 'var(--paper)',
        border: '1px solid var(--rule)',
        borderRadius: 4,
        boxShadow: '0 6px 18px rgba(0,0,0,0.22)',
        padding: 4,
        pointerEvents: 'auto',
      }}
    >
      <div style={{fontSize:10,fontWeight:600,padding:'6px 10px',borderBottom:'1px solid var(--rule)',marginBottom:2,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>
        {contextMenu.node.title || contextMenu.node.id}
      </div>
      <button style={ctxMenuItem} onClick={() => openNodeInObsidian(contextMenu.node)}>Open in Obsidian ↗</button>
      <button style={ctxMenuItem} onClick={() => togglePin(contextMenu.node)}>
        {pinned[contextMenu.node.id] ? 'Unpin position' : 'Pin position 📌'}
      </button>
      <button style={ctxMenuItem} onClick={() => hideNode(contextMenu.node)}>Hide from graph</button>

      <div style={ctxSection}>AI actions</div>
      <button style={ctxMenuItem} onClick={() => summarizeNote(contextMenu.node, false)}>Summarize this note ✦</button>
      <button style={ctxMenuItem} onClick={() => summarizeNote(contextMenu.node, true)}>Summarize this + linked notes ✦</button>
      <button style={ctxMenuItem} onClick={() => sendToAgent('suggestTags', contextMenu.node, null)}>Suggest tags ✦</button>
      <button style={ctxMenuItem} onClick={() => sendToAgent('findMissingLinks', contextMenu.node, null)}>Find missing links ✦</button>
      <button style={ctxMenuItem} onClick={() => sendToAgent('generateChild', contextMenu.node, null)}>Generate child note ✦</button>
      <button style={ctxMenuItem} onClick={() => sendToAgent('explainConnections', contextMenu.node, null)}>Explain how this connects ✦</button>
      <button style={ctxMenuItem} onClick={() => createProposalFromNode(contextMenu.node)}>Create proposal from node</button>
      <button style={ctxMenuItem} onClick={() => createTaskFromNode(contextMenu.node)}>Create implementation task</button>

      <div style={ctxSection}>Compare</div>
      <button
        style={{...ctxMenuItem, opacity: activePath ? 1 : 0.4}}
        disabled={!activePath || activePath === contextMenu.node.id}
        onClick={() => {
          setCompareSet({ aId: activePath, bId: contextMenu.node.id });
          setStatusMsg({ text: `Comparing active note ↔ ${contextMenu.node.title || contextMenu.node.id}`, kind: 'info' });
          setContextMenu(null);
        }}
      >Compare with active note ⇄</button>
      <button
        style={ctxMenuItem}
        onClick={() => {
          if (!compareSet || compareSet.bId) {
            // Start a new comparison from this node.
            setCompareSet({ aId: contextMenu.node.id, bId: null });
            setStatusMsg({ text: 'Pick a second node — right-click → "Complete comparison"', kind: 'info' });
          } else {
            // Already have an A — finish the pair.
            setCompareSet({ aId: compareSet.aId, bId: contextMenu.node.id });
            setStatusMsg({ text: `Comparing ${compareSet.aId.split('/').pop()} ↔ ${contextMenu.node.title || contextMenu.node.id}`, kind: 'info' });
          }
          setContextMenu(null);
        }}
      >{compareSet && !compareSet.bId ? 'Complete comparison ⇄' : 'Compare from this node ⇄'}</button>
      {compareSet && (
        <button
          style={{...ctxMenuItem, opacity: 0.7}}
          onClick={() => { setCompareSet(null); setContextMenu(null); }}
        >Exit compare mode</button>
      )}

      <div style={ctxSection}>Send to agent</div>
      {agents && agents.length > 0 ? (
        <div style={{maxHeight:160,overflowY:'auto'}}>
          {agents.map(a => (
            <button
              key={a.id}
              style={{...ctxMenuItem, display:'flex', alignItems:'center', gap:8}}
              onClick={() => sendToAgent('mission', contextMenu.node, a)}
            >
              <span style={{display:'inline-block',width:8,height:8,borderRadius:2,background:'var(--accent-teal)'}}></span>
              <span style={{flex:1,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{a.name}</span>
              <span style={{fontSize:9,opacity:0.6}}>{a.role || ''}</span>
            </button>
          ))}
        </div>
      ) : (
        <div style={{fontSize:10,opacity:0.55,padding:'4px 10px 8px'}}>No agents hired yet.</div>
      )}
    </div>
  );

  /* Hover preview tooltip — appears 400ms after hover settles. */
  const previewJsx = previewNote && hover === previewNote.id && (() => {
    // Pin tooltip near cursor but keep on-screen.
    const wr = wrapRef.current ? wrapRef.current.getBoundingClientRect() : { width: 600, height: 400 };
    const margin = 12;
    const W = 280;
    let left = lastMouseRef.current.x + margin;
    let top  = lastMouseRef.current.y + margin;
    if (left + W > wr.width - margin) left = lastMouseRef.current.x - W - margin;
    if (top > wr.height - 140) top = wr.height - 140;
    if (left < margin) left = margin;
    if (top < margin) top = margin;
    return (
      <div style={{
        position:'absolute', left, top, width: W, zIndex: 7,
        background: 'var(--paper)',
        border: '1px solid var(--rule)',
        borderRadius: 5,
        padding: '8px 10px',
        boxShadow: '0 6px 16px rgba(0,0,0,0.18)',
        color: 'var(--ink)',
        pointerEvents: 'none',
        fontSize: 11,
        lineHeight: 1.45,
      }}>
        <div style={{fontWeight:700,marginBottom:4,whiteSpace:'nowrap',overflow:'hidden',textOverflow:'ellipsis'}}>{previewNote.title}</div>
        <div style={{opacity:0.85,whiteSpace:'pre-wrap',wordBreak:'break-word'}}>
          {previewNote.content || <span style={{opacity:0.55,fontStyle:'italic'}}>{previewNote.content === null ? '(could not read)' : '(empty note)'}</span>}
        </div>
      </div>
    );
  })();

  const selectedNode = selected ? state.byId[selected] : null;
  const provenanceDrawer = drawerOpen && (
    <div
      onMouseDown={e => e.stopPropagation()}
      onWheel={e => e.stopPropagation()}
      style={{
        position:'absolute', top:44, right:8, bottom:44, width:300, zIndex:6,
        background:'var(--paper)', border:'1px solid var(--rule)', borderRadius:6,
        boxShadow:'0 8px 24px rgba(0,0,0,0.22)', padding:10,
        color:'var(--ink)', pointerEvents:'auto', overflowY:'auto', fontSize:11,
      }}
    >
      <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:8}}>
        <div style={{fontWeight:800,letterSpacing:1,fontSize:10}}>PROVENANCE</div>
        <button style={{...overlayBtn,fontSize:10,padding:'2px 6px'}} onClick={() => setDrawerOpen(false)}>×</button>
      </div>
      {!selectedNode ? (
        <div style={{opacity:0.7,lineHeight:1.45}}>
          Select a node to see why it exists, what connects to it, and what action to take next.
          <div style={{marginTop:10,fontWeight:700}}>Filter examples</div>
          {['type:research','path:Projects','tag:project','stale','orphan','type:decision OR type:proposal'].map(q => (
            <button key={q} onClick={() => setFilter(q)} style={{...ctxMenuItem,padding:'4px 0',fontSize:10,color:'var(--accent-teal)'}}>{q}</button>
          ))}
        </div>
      ) : (() => {
        const incoming = [], outgoing = [];
        for (const e of state.edges) {
          const sid = e.source.id || e.source, tid = e.target.id || e.target;
          if (sid === selectedNode.id) outgoing.push({ edge:e, node:state.byId[tid] });
          if (tid === selectedNode.id) incoming.push({ edge:e, node:state.byId[sid] });
        }
        const ageDays = selectedNode.mtime ? Math.floor((Date.now() - selectedNode.mtime) / 86400000) : null;
        const chip = (txt, bg='var(--paper-2)') => <span style={{display:'inline-block',padding:'2px 6px',border:'1px solid var(--rule)',borderRadius:999,background:bg,margin:'0 4px 4px 0'}}>{txt}</span>;

        // Per-type tally across both directions, used for the relationship
        // summary chips below the counts grid. Skips plain `links_to` so the
        // user only sees the semantically-loaded relationships.
        const typeTally = (() => {
          const counts = new Map();
          for (const { edge } of [...incoming, ...outgoing]) {
            const t = edge.type || 'links_to';
            if (t === 'links_to') continue;
            counts.set(t, (counts.get(t) || 0) + 1);
          }
          return [...counts.entries()].sort((a, b) => b[1] - a[1]);
        })();

        // Render one connection row with: typed chip (color = EDGE_TYPE_STYLE
        // entry if any), target title, and a one-line sourceText snippet
        // (provenance) below when present. The chip's color tells the user
        // what KIND of relationship this is at a glance.
        const typedChip = (etype, conf) => {
          const style = EDGE_TYPE_STYLE[etype];
          const swatch = (style && style.color) || 'rgba(125, 125, 125, 0.6)';
          const dim = conf != null && conf < 0.85;
          return (
            <span title={conf != null ? `confidence ${conf.toFixed(2)}` : ''} style={{
              display:'inline-flex', alignItems:'center', gap:4,
              fontSize:9, padding:'1px 5px', borderRadius:8,
              border:'1px solid var(--rule)',
              background: 'var(--paper-2)',
              opacity: dim ? 0.7 : 1,
              marginRight:4,
            }}>
              <span style={{width:6,height:6,borderRadius:'50%',background:swatch,display:'inline-block'}}/>
              {etype}
            </span>
          );
        };

        const relList = (items, empty) => items.length ? items.slice(0,12).map(({edge,node}, i) => {
          const etype = edge.type || 'links_to';
          const snip = (edge.sourceText || '').trim();
          return (
            <div key={(node && node.id) || i} style={{padding:'4px 0',borderBottom:'1px dotted rgba(0,0,0,0.05)'}}>
              <div style={{display:'flex',alignItems:'center',gap:4,flexWrap:'wrap'}}>
                {typedChip(etype, edge.confidence)}
                <button
                  onClick={() => { if (node) { setSelected(node.id); if (onOpenNote) onOpenNote(node.id); } }}
                  style={{...ctxMenuItem,padding:'1px 0',fontSize:10,flex:1,textAlign:'left'}}
                >{node ? (node.title || node.id) : '(missing)'}</button>
              </div>
              {snip && (
                <div style={{
                  fontSize:9,opacity:0.55,marginTop:2,marginLeft:4,
                  fontStyle:'italic',lineHeight:1.3,
                  display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical',overflow:'hidden',
                }}>"{snip.length > 120 ? snip.slice(0, 117) + '…' : snip}"</div>
              )}
            </div>
          );
        }) : <div style={{opacity:0.5,fontSize:10}}>{empty}</div>;
        return (
          <div>
            <div style={{fontSize:14,fontWeight:800,lineHeight:1.25,marginBottom:4}}>{selectedNode.title || selectedNode.id}</div>
            <div style={{fontSize:10,opacity:0.65,wordBreak:'break-all',marginBottom:8}}>{selectedNode.path || selectedNode.id}</div>
            <div style={{marginBottom:8}}>
              {chip(selectedNode.type || 'note')}
              {chip(selectedNode.source || 'markdownvault')}
              {ageDays != null && chip(ageDays === 0 ? 'modified today' : `${ageDays}d old`)}
              {(selectedNode.tags || []).slice(0,5).map(t => chip('#' + String(t).replace(/^#/,'')))}
            </div>
            <div style={{display:'grid',gridTemplateColumns:'1fr 1fr 1fr',gap:4,marginBottom:10}}>
              <div><b>{incoming.length}</b><br/><span style={{opacity:0.55}}>incoming</span></div>
              <div><b>{outgoing.length}</b><br/><span style={{opacity:0.55}}>outgoing</span></div>
              <div><b>{selectedNode.size || 0}</b><br/><span style={{opacity:0.55}}>bytes</span></div>
            </div>
            {typeTally.length > 0 && (
              <div style={{margin:'4px 0 10px'}}>
                <div style={{fontWeight:700,fontSize:9,letterSpacing:1,opacity:0.65,marginBottom:4}}>RELATIONSHIPS</div>
                <div style={{display:'flex',flexWrap:'wrap',gap:3}}>
                  {typeTally.map(([t, n]) => {
                    const style = EDGE_TYPE_STYLE[t];
                    const swatch = (style && style.color) || 'rgba(125,125,125,0.6)';
                    return (
                      <span key={t} style={{
                        display:'inline-flex',alignItems:'center',gap:3,
                        fontSize:9,padding:'1px 6px',borderRadius:8,
                        border:'1px solid var(--rule)',background:'var(--paper-2)',
                      }}>
                        <span style={{width:6,height:6,borderRadius:'50%',background:swatch}}/>
                        {t} <b style={{marginLeft:2}}>{n}</b>
                      </span>
                    );
                  })}
                </div>
              </div>
            )}
            <div style={{fontWeight:700,fontSize:10,letterSpacing:1,margin:'8px 0 4px'}}>WHY AM I SEEING THIS?</div>
            <div style={{opacity:0.75,lineHeight:1.45,marginBottom:8}}>
              It matches the current scope/filter as a <b>{selectedNode.type || 'note'}</b>.
              {typeTally.length > 0 ? (
                <> Its connections are typed: <b>{typeTally.map(([t,n]) => `${n} ${t}`).join(', ')}</b>. Hover a connection below to see the source passage.</>
              ) : (
                <> Its connections are plain <code>links_to</code> mentions — add typed cues like <code>Source:&nbsp;[[X]]</code>, a <code>## Related</code> section, or a <code>{'>'}&nbsp;[!supports]</code> callout to upgrade them.</>
              )}
            </div>
            <div style={{fontWeight:700,fontSize:10,letterSpacing:1,margin:'8px 0 4px'}}>ACTIONS</div>
            <button style={ctxMenuItem} onClick={() => summarizeNote(selectedNode, true)}>Summarize cluster</button>
            <button style={ctxMenuItem} onClick={() => sendToAgent('findMissingLinks', selectedNode, null)}>Find missing links</button>
            <button style={ctxMenuItem} onClick={() => createProposalFromNode(selectedNode)}>Turn into proposal</button>
            <button style={ctxMenuItem} onClick={() => createTaskFromNode(selectedNode)}>Create implementation task</button>
            <div style={{fontWeight:700,fontSize:10,letterSpacing:1,margin:'10px 0 4px'}}>INCOMING</div>
            {relList(incoming, 'No incoming links')}
            <div style={{fontWeight:700,fontSize:10,letterSpacing:1,margin:'10px 0 4px'}}>OUTGOING</div>
            {relList(outgoing, 'No outgoing links')}
          </div>
        );
      })()}
    </div>
  );

  /* Top-of-canvas tag chips. Aggregate top tags across nodes; click toggles
     the filter to that tag. */
  const tagChips = (() => {
    const counts = new Map();
    for (const n of state.nodes) {
      for (const t of (n.tags || [])) counts.set(t, (counts.get(t) || 0) + 1);
    }
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    if (top.length === 0) return null;
    return (
      <div
        onMouseDown={e => e.stopPropagation()}
        style={{
          position:'absolute', top: 44, left: 8, right: 8, zIndex: 3,
          display:'flex', flexWrap:'wrap', gap:4,
          pointerEvents:'none',
        }}
      >
        {top.map(([t, c]) => {
          const active = filter.trim() === t;
          return (
            <button
              key={t}
              onClick={() => setFilter(active ? '' : t)}
              style={{
                pointerEvents:'auto',
                fontSize:10, padding:'2px 7px',
                background: active ? 'var(--accent-sun)' : 'var(--paper)',
                border:'1px solid var(--rule)',
                borderRadius: 999,
                color:'var(--ink)', cursor:'pointer',
                opacity: active ? 1 : 0.85,
              }}
            >{t} <span style={{opacity:0.55,marginLeft:3}}>{c}</span></button>
          );
        })}
      </div>
    );
  })();

  /* Command palette — Cmd/Ctrl-P. */
  const paletteCommands = [
    { label: 'Recenter view', run: () => { recenter(); } },
    { label: 'Mode: Research Map', run: () => applyOpinionatedMode('research') },
    { label: 'Mode: Project Execution Map', run: () => applyOpinionatedMode('execution') },
    { label: 'Mode: Agent Contribution Map', run: () => applyOpinionatedMode('agents') },
    { label: 'Mode: Decision Provenance Map', run: () => applyOpinionatedMode('decisions') },
    { label: 'Mode: Stale Knowledge Map', run: () => applyOpinionatedMode('stale') },
    { label: 'Export PNG', run: () => { exportPng(); } },
    { label: 'Save current view…', run: () => { saveCurrentView(); } },
    { label: 'Toggle: Cluster coloring', run: () => setClusterColoring(v => !v) },
    { label: 'Toggle: Highlight orphans', run: () => setHighlightOrphans(v => !v) },
    { label: 'Toggle: Suggest similar links (ghost edges)', run: () => setShowGhostEdges(v => !v) },
    { label: 'Toggle: 3D mode 🎲', run: () => setIs3D(v => !v) },
    { label: '3D: Reset camera', run: () => { rot3DRef.current = { rotX: -0.3, rotY: 0.5 }; wakeSim(); } },
    { label: '3D: Top-down view', run: () => { rot3DRef.current = { rotX: -Math.PI/2 + 0.05, rotY: 0 }; wakeSim(); } },
    { label: '3D: Front view', run: () => { rot3DRef.current = { rotX: 0, rotY: 0 }; wakeSim(); } },
    { label: '3D: Side view', run: () => { rot3DRef.current = { rotX: 0, rotY: Math.PI/2 }; wakeSim(); } },
    { label: '3D: Shake (re-puff cloud)', run: () => {
      let cloudR = 150;
      for (const n of state.nodes) { const r = Math.hypot(n.x, n.y); if (r > cloudR) cloudR = r; }
      for (const n of state.nodes) {
        n.z = (n.z || 0) + (Math.random() - 0.5) * cloudR * 1.2;
        n.vz = (n.vz || 0) + (Math.random() - 0.5) * 8;
      }
      state.energy = 1;
      wakeSim();
    } },
    { label: 'Exit compare mode', run: () => setCompareSet(null) },
    { label: 'Toggle: Show all labels', run: () => setShowAllLabels(v => !v) },
    { label: 'Color by Tags',         run: () => setColorMode('tags') },
    { label: 'Color by Folder',       run: () => setColorMode('folder') },
    { label: 'Color by Inlinks',      run: () => setColorMode('inlinks') },
    { label: 'Color by Last modified',run: () => setColorMode('modified') },
    { label: 'Color by Heatmap (recency)', run: () => setColorMode('heatmap') },
    { label: 'Scope: Global',  run: () => setLocalMode('global') },
    { label: 'Scope: Local 1', run: () => setLocalMode('1') },
    { label: 'Scope: Local 2', run: () => setLocalMode('2') },
    { label: 'Scope: Local 3', run: () => setLocalMode('3') },
    { label: 'Clear filter',   run: () => setFilter('') },
    { label: 'Clear shortest path', run: () => { setShortestPath(null); setPathEndpoints([]); } },
    { label: 'Show all hidden nodes', run: () => setHiddenIds(new Set()) },
    { label: 'Refresh graph data', run: () => window.CafresoHQGraph && window.CafresoHQGraph.refresh && window.CafresoHQGraph.refresh() },
    ...savedViews.map(v => ({ label: `View: ${v.name}`, run: () => applyView(v) })),
  ];
  const filteredCmds = paletteQuery.trim()
    ? paletteCommands.filter(c => c.label.toLowerCase().includes(paletteQuery.trim().toLowerCase()))
    : paletteCommands;
  const paletteJsx = paletteOpen && (
    <div
      onMouseDown={e => e.stopPropagation()}
      style={{
        position:'absolute', top: 70, left: '50%', transform: 'translateX(-50%)',
        zIndex: 9, width: 360, maxWidth: 'calc(100% - 24px)',
        background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 6,
        boxShadow: '0 12px 32px rgba(0,0,0,0.28)',
        padding: 6, pointerEvents: 'auto',
      }}
    >
      <input
        autoFocus
        value={paletteQuery}
        onChange={e => setPaletteQuery(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Escape') { setPaletteOpen(false); return; }
          if (e.key === 'Enter' && filteredCmds[0]) {
            filteredCmds[0].run();
            setPaletteOpen(false);
          }
        }}
        placeholder="Type a command…"
        style={{
          width:'100%', boxSizing:'border-box',
          fontSize:13, padding:'8px 10px',
          background:'var(--paper-2)', color:'var(--ink)',
          border:'1px solid var(--rule)', borderRadius:4, outline:'none',
        }}
      />
      <div style={{maxHeight:280, overflowY:'auto', marginTop:4}}>
        {filteredCmds.length === 0 && <div style={{padding:'8px 10px',fontSize:11,opacity:0.6}}>No commands match.</div>}
        {filteredCmds.slice(0, 20).map((c, i) => (
          <button
            key={c.label + i}
            onClick={() => { c.run(); setPaletteOpen(false); }}
            style={{
              display:'block', width:'100%', textAlign:'left',
              fontSize:12, padding:'6px 10px',
              background: i === 0 ? 'var(--paper-2)' : 'transparent',
              border:'none', color:'var(--ink)', cursor:'pointer',
              borderRadius:3,
            }}
          >{c.label}</button>
        ))}
      </div>
      <div style={{padding:'4px 8px',fontSize:9,opacity:0.5,display:'flex',justifyContent:'space-between'}}>
        <span>Enter to run · Esc to close</span>
        <span>{filteredCmds.length} command{filteredCmds.length === 1 ? '' : 's'}</span>
      </div>
    </div>
  );

  /* Local status toast removed in Session 2 — graph statuses now go through
     the global ToastProvider via window.cafresohqToast (see setStatusMsg above). */
  const statusToastJsx = null;

  /* Multi-select action bar — appears bottom-center when ≥1 node is lasso'd. */
  const multiSelectBar = selectedSet.size > 0 && (
    <div
      onMouseDown={e => e.stopPropagation()}
      style={{
        position:'absolute', bottom: timeScrubEnabled && state.mtimeRange ? 56 : 16,
        left: '50%', transform: 'translateX(-50%)',
        zIndex: 5,
        background: 'var(--paper)', border: '1px solid var(--rule)', borderRadius: 6,
        padding: '6px 10px',
        boxShadow: '0 4px 14px rgba(0,0,0,0.22)',
        display:'flex', alignItems:'center', gap:8,
        pointerEvents:'auto',
      }}
    >
      <span style={{fontSize:11,fontWeight:600}}>{selectedSet.size} selected</span>
      <button
        onClick={() => setBatchAgentOpen(v => !v)}
        style={{...overlayBtn}}
      >Send to agent ▾</button>
      <button onClick={hideSelection} style={overlayBtn}>Hide all</button>
      <button onClick={clearSelection} style={overlayBtn}>Clear</button>
      {batchAgentOpen && (
        <div style={{
          position:'absolute', bottom:'100%', left:0, marginBottom:4,
          background:'var(--paper)', border:'1px solid var(--rule)', borderRadius:5,
          padding:4, minWidth:200, boxShadow:'0 4px 14px rgba(0,0,0,0.22)',
        }}>
          {agents && agents.length > 0 ? agents.map(a => (
            <button
              key={a.id}
              onClick={() => sendSelectionToAgent(a)}
              style={ctxMenuItem}
            >{a.name} <span style={{opacity:0.55,fontSize:9}}>· {a.role}</span></button>
          )) : (
            <div style={{fontSize:10,opacity:0.55,padding:'4px 8px'}}>No agents hired.</div>
          )}
        </div>
      )}
    </div>
  );

  /* Time scrubber bottom strip — appears when toggled on and mtime data exists. */
  const timeScrubberBar = (timeScrubEnabled && state.mtimeRange) && (
    <div
      onMouseDown={e => e.stopPropagation()}
      style={{
        position:'absolute', bottom: 8, left: 8, right: 8,
        zIndex: 4,
        background: 'var(--paper)',
        border: '1px solid var(--rule)',
        borderRadius: 4,
        padding: '6px 10px',
        display:'flex', alignItems:'center', gap:8,
        pointerEvents:'auto', fontSize:10,
      }}
    >
      <span style={{whiteSpace:'nowrap',opacity:0.7}}>{new Date(state.mtimeRange.min).toLocaleDateString()}</span>
      <input
        type="range"
        min={state.mtimeRange.min} max={state.mtimeRange.max} step={86400000}
        value={timeScrub == null ? state.mtimeRange.max : timeScrub}
        onChange={e => setTimeScrub(parseInt(e.target.value, 10))}
        style={{flex:1}}
      />
      <span style={{whiteSpace:'nowrap',fontWeight:600}}>
        {new Date(timeScrub == null ? state.mtimeRange.max : timeScrub).toLocaleDateString()}
      </span>
      <button
        onClick={() => setTimeScrub(state.mtimeRange.max)}
        style={overlayBtn}
        title="Show all"
      >MAX</button>
    </div>
  );

  // Bottom-right status pill: zoom % + visible/total node counts.
  const visibleCount = state.localVisible
    ? state.localVisible.size
    : (filter ? state.nodes.filter(n => nodeMatchesFilter(n, filter.trim())).length : state.nodes.length);
  const statusPill = (
    <div style={{
      position: 'absolute', bottom: 8, right: 8, zIndex: 4,
      fontSize: 9, fontFamily: 'monospace', letterSpacing: 0.5,
      padding: '3px 7px',
      background: 'var(--paper)',
      border: '1px solid var(--rule)',
      borderRadius: 4,
      color: 'var(--ink)',
      opacity: 0.75,
      pointerEvents: 'none',
    }}>
      {Math.round(state.zoom * 100)}% · {visibleCount}/{state.nodes.length}
      {localMode !== 'global' && <span style={{marginLeft:4,opacity:0.7}}>· local-{localMode}</span>}
      {is3D && <span style={{marginLeft:4,opacity:0.7}}>· 3D</span>}
    </div>
  );

  if (embedded) {
    return (
      <div ref={wrapRef} style={{position:'relative',flex:1,minHeight:0,minWidth:0,overflow:'hidden',background:'var(--paper)'}}>
        {topOverlay}
        {tagChips}
        {settingsPanel}
        {contextMenuJsx}
        {previewJsx}
        {provenanceDrawer}
        {paletteJsx}
        {multiSelectBar}
        {timeScrubberBar}
        {statusToastJsx}
        {statusPill}
        <canvas
          className="graph-stage"
          style={{
            width: '100%',
            height: '100%',
            display: 'block',
            background: 'var(--paper)',
          }}
          {...canvasProps}
        />
      </div>
    );
  }

  return (
    <div ref={wrapRef} style={{display:'flex',flexDirection:'column',height:'100%',minHeight:0,overflow:'hidden',position:'relative',background:'var(--paper)'}}>
      <div className="section-title">
        🧠 VAULT GRAPH
        <span className="tag">Obsidian-style force graph · drag · scroll · click</span>
      </div>
      <div style={{position:'relative',flex:1,minHeight:0,overflow:'hidden',background:'var(--paper)'}}>
        {topOverlay}
        {tagChips}
        {settingsPanel}
        {contextMenuJsx}
        {previewJsx}
        {provenanceDrawer}
        {paletteJsx}
        {multiSelectBar}
        {timeScrubberBar}
        {statusToastJsx}
        {statusPill}
        <canvas
          className="graph-stage"
          style={{
            width: '100%',
            height: '100%',
            display: 'block',
            background: 'var(--paper)',
          }}
          {...canvasProps}
        />
      </div>
    </div>
  );
}

/* Connected-components labeling. Returns { id → componentIndex } and the
   total component count. Used for auto-cluster coloring. */
function connectedComponents(state) {
  const adj = graphAdjacency(state);
  const comp = {};
  let idx = 0;
  for (const n of state.nodes) {
    if (comp[n.id] != null) continue;
    const queue = [n.id]; comp[n.id] = idx;
    while (queue.length) {
      const cur = queue.shift();
      for (const nb of adj.get(cur) || []) {
        if (comp[nb] == null) { comp[nb] = idx; queue.push(nb); }
      }
    }
    idx++;
  }
  return { comp, count: idx };
}

/* BFS shortest path between two node ids. Returns array of ids inclusive,
   or null if unreachable. Treats edges as undirected. */
function shortestPathBetween(state, fromId, toId) {
  if (!fromId || !toId || fromId === toId) return fromId ? [fromId] : null;
  const adj = graphAdjacency(state);
  const prev = new Map(); prev.set(fromId, null);
  const queue = [fromId];
  while (queue.length) {
    const cur = queue.shift();
    if (cur === toId) {
      const path = []; let c = cur;
      while (c != null) { path.unshift(c); c = prev.get(c); }
      return path;
    }
    for (const nb of adj.get(cur) || []) {
      if (!prev.has(nb)) { prev.set(nb, cur); queue.push(nb); }
    }
  }
  return null;
}

/* Choose neighbor in roughly the given direction vector (dx,dy). Used by
   keyboard arrow navigation. */
function neighborInDirection(state, fromId, dx, dy) {
  const from = state.byId[fromId]; if (!from) return null;
  const targetAngle = Math.atan2(dy, dx);
  let best = null, bestScore = -Infinity;
  for (const e of state.edges) {
    const s = e.source.id || e.source, t = e.target.id || e.target;
    let other = null;
    if (s === fromId) other = state.byId[t];
    else if (t === fromId) other = state.byId[s];
    if (!other) continue;
    const a = Math.atan2(other.y - from.y, other.x - from.x);
    let diff = Math.abs(((a - targetAngle + Math.PI) % (Math.PI * 2)) - Math.PI);
    // Score: prefer aligned direction, secondarily prefer closer nodes.
    const dist = Math.hypot(other.x - from.x, other.y - from.y) || 1;
    const score = -diff * 4 - dist * 0.001;
    if (score > bestScore) { bestScore = score; best = other; }
  }
  return best;
}

/* In-browser semantic similarity using TF-IDF over a node's title tokens,
   tags, and folder path. Returns top-K candidate ghost edges between
   currently-unlinked node pairs. Cheap enough for vaults up to ~5k notes;
   beyond that we sample. */
function graphAdjacency(state) {
  if (!state) return new Map();
  if (state._adjEdgesRef === state.edges && state._adjacency) return state._adjacency;
  const adj = new Map();
  for (const n of (state.nodes || [])) adj.set(n.id, []);
  for (const e of (state.edges || [])) {
    const s = e.source && e.source.id ? e.source.id : e.source;
    const t = e.target && e.target.id ? e.target.id : e.target;
    if (adj.has(s) && adj.has(t)) { adj.get(s).push(t); adj.get(t).push(s); }
  }
  state._adjEdgesRef = state.edges;
  state._adjacency = adj;
  return adj;
}

function computeGhostEdges(state, opts = {}) {
  const TOPK       = opts.topK || 40;
  const MIN_SCORE  = opts.minScore || 0.18;
  const stop = new Set(['the','and','of','to','a','for','in','on','is','at','it','this','that','with','as','an','by','be','or','from','my','i']);

  const tokenize = (s) => (s || '').toLowerCase()
    .replace(/\.md$/, '')
    .replace(/[^\w\s-]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length > 2 && !stop.has(t));

  const docs = state.nodes.map(n => {
    const titleToks = tokenize(n.title || n.id.split('/').pop());
    const folderToks = tokenize((n.id || '').split('/').slice(0, -1).join(' '));
    const tagToks    = (n.tags || []).map(t => t.replace(/^#/, '').toLowerCase());
    // Tags weighted 3x, folder 2x.
    const all = [...titleToks, ...folderToks, ...folderToks, ...tagToks, ...tagToks, ...tagToks];
    const tf = new Map();
    for (const t of all) tf.set(t, (tf.get(t) || 0) + 1);
    return { id: n.id, tf };
  });

  // IDF
  const df = new Map();
  for (const d of docs) for (const t of d.tf.keys()) df.set(t, (df.get(t) || 0) + 1);
  const N = docs.length;
  const idf = new Map();
  for (const [t, c] of df) idf.set(t, Math.log(1 + N / (1 + c)));

  // Build TF-IDF vectors as Maps; norm them.
  const vecs = docs.map(d => {
    const v = new Map();
    let normSq = 0;
    for (const [t, c] of d.tf) {
      const w = c * (idf.get(t) || 0);
      if (w > 0) { v.set(t, w); normSq += w * w; }
    }
    return { id: d.id, v, norm: Math.sqrt(normSq) || 1 };
  });

  // Existing-edge set so we skip pairs already linked.
  const linked = new Set();
  for (const e of state.edges) {
    const s = e.source.id || e.source, t = e.target.id || e.target;
    linked.add(s < t ? s + '\0' + t : t + '\0' + s);
  }

  // Pairwise — bail out early if vault is huge (sample 1500 nodes).
  const sample = vecs.length > 1500
    ? vecs.slice().sort(() => Math.random() - 0.5).slice(0, 1500)
    : vecs;

  const candidates = [];
  for (let i = 0; i < sample.length; i++) {
    const a = sample[i];
    for (let j = i + 1; j < sample.length; j++) {
      const b = sample[j];
      const key = a.id < b.id ? a.id + '\0' + b.id : b.id + '\0' + a.id;
      if (linked.has(key)) continue;
      // dot product over the smaller map for speed
      const [s1, s2] = a.v.size <= b.v.size ? [a.v, b.v] : [b.v, a.v];
      let dot = 0;
      for (const [t, w] of s1) {
        const w2 = s2.get(t);
        if (w2) dot += w * w2;
      }
      const score = dot / (a.norm * b.norm);
      if (score >= MIN_SCORE) candidates.push({ a: a.id, b: b.id, score });
    }
  }
  candidates.sort((x, y) => y.score - x.score);
  return candidates.slice(0, TOPK);
}

/* Cluster palette — 12 distinct hues spaced for maximum visual separation. */
const CLUSTER_HUES = [10, 35, 55, 95, 130, 175, 200, 230, 270, 300, 325, 350];
function clusterColor(idx, isDark) {
  const hue = CLUSTER_HUES[idx % CLUSTER_HUES.length];
  return `hsl(${hue}, ${isDark ? 60 : 50}%, ${isDark ? 65 : 58}%)`;
}

/* BFS from rootId out to maxDepth (inclusive). Returns the set of node ids
   reachable through the graph's edges in either direction. Used by Local mode. */
function bfsLocal(state, rootId, maxDepth) {
  if (!rootId || !state.byId[rootId]) return null;
  const adj = graphAdjacency(state);
  const visited = new Set([rootId]);
  let frontier = [rootId];
  for (let d = 0; d < maxDepth; d++) {
    const next = [];
    for (const id of frontier) {
      for (const nb of (adj.get(id) || [])) {
        if (!visited.has(nb)) { visited.add(nb); next.push(nb); }
      }
    }
    if (next.length === 0) break;
    frontier = next;
  }
  return visited;
}

function getNeighbors(state, nodeId) {
  if (!nodeId) return null;
  const neighbors = new Set([nodeId]);
  const adj = graphAdjacency(state);
  for (const nb of (adj.get(nodeId) || [])) neighbors.add(nb);
  return neighbors;
}

function simulate(s) {
  const cfg = s.settings || {};

  // Settling: freeze on the seed circle for state.freezeUntil ms, then ramp
  // forces in linearly between freezeUntil and warmupUntil. This produces a
  // smooth "circle pause → drift → settle" intro instead of an instant explosion.
  const now = Date.now();
  let warmth = 1;
  if (s.freezeUntil && now < s.freezeUntil) {
    warmth = 0;
  } else if (s.warmupUntil && now < s.warmupUntil) {
    const span = s.warmupUntil - (s.freezeUntil || s.warmupUntil);
    const t = span > 0 ? (now - (s.freezeUntil || 0)) / span : 1;
    // Ease-in-out cubic — slow start, gentle end. Feels like nodes "drift" into place.
    const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    warmth = e < 0 ? 0 : e > 1 ? 1 : e;
  }

  const REPULSE     = (cfg.repelForce    != null ? cfg.repelForce    : 900)   * warmth;
  const SPRING      = (cfg.linkForce     != null ? cfg.linkForce     : 0.022) * warmth;
  const SPRING_LEN  = cfg.linkDistance  != null ? cfg.linkDistance  : 150;
  const CENTER      = (cfg.centerForce   != null ? cfg.centerForce   : 0.0008) * warmth;
  const LAYER       = (cfg.layerForce    != null ? cfg.layerForce    : 0.003) * warmth;
  const DAMP        = 0.85;

  // Stability clamps — cap force per pair, velocity per step, displacement per step.
  // Without these the inverse-square repulsion explodes when two nodes overlap.
  // Velocity & step caps are scaled by warmth so the intro drift is gentle.
  const MIN_DIST2   = 100;
  const MAX_FORCE   = 12 * warmth;
  const MAX_VEL     = 4 + 14 * warmth;   // 4 px/frame at start of warmup → 18 at full
  const MAX_STEP    = 6 + 18 * warmth;   // 6 → 24

  const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;

  const { nodes, edges } = s;
  const D3 = !!s.is3D;

  // During the introductory freeze, keep repainting overlays/pulses but skip
  // the expensive O(n²) force pass. Previously we multiplied every force by 0
  // and still paid the full pairwise cost, causing the first seconds to hitch.
  if (warmth <= 0.0001) return;

  /* Repulsion — every pair pushes apart (Coulomb-like). */
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      let dx = b.x - a.x, dy = b.y - a.y;
      let dz = D3 ? (b.z || 0) - (a.z || 0) : 0;
      let d2 = dx*dx + dy*dy + dz*dz;
      if (d2 < 0.01) {
        dx = (Math.random() - 0.5) * 2;
        dy = (Math.random() - 0.5) * 2;
        if (D3) dz = (Math.random() - 0.5) * 2;
        d2 = dx*dx + dy*dy + dz*dz;
      }
      if (d2 < MIN_DIST2) d2 = MIN_DIST2;
      const d = Math.sqrt(d2);
      const f = -REPULSE / d2;
      let fx = clamp(dx / d * f, -MAX_FORCE, MAX_FORCE);
      let fy = clamp(dy / d * f, -MAX_FORCE, MAX_FORCE);
      a.vx += fx; a.vy += fy;
      b.vx -= fx; b.vy -= fy;
      if (D3) {
        let fz = clamp(dz / d * f, -MAX_FORCE, MAX_FORCE);
        a.vz = (a.vz || 0) + fz; b.vz = (b.vz || 0) - fz;
      }
    }
  }

  /* Springs — linked nodes attract toward link distance. */
  for (const e of edges) {
    const a = e.source.id ? e.source : s.byId[e.source];
    const b = e.target.id ? e.target : s.byId[e.target];
    if (!a || !b) continue;
    const dx = b.x - a.x, dy = b.y - a.y;
    const dz = D3 ? (b.z || 0) - (a.z || 0) : 0;
    const d = Math.sqrt(dx*dx + dy*dy + dz*dz) || 1;
    const f = (d - SPRING_LEN) * SPRING;
    let fx = clamp(dx / d * f, -MAX_FORCE, MAX_FORCE);
    let fy = clamp(dy / d * f, -MAX_FORCE, MAX_FORCE);
    a.vx += fx; a.vy += fy;
    b.vx -= fx; b.vy -= fy;
    if (D3) {
      let fz = clamp(dz / d * f, -MAX_FORCE, MAX_FORCE);
      a.vz = (a.vz || 0) + fz; b.vz = (b.vz || 0) - fz;
    }
  }

  /* Integrate. */
  for (const n of nodes) {
    if (n.fx != null) { n.x = n.fx; n.y = n.fy; n.vx = 0; n.vy = 0; if (D3) n.vz = 0; continue; }

    n.vx += ((n.outlinks || 0) - (n.inlinks || 0)) * LAYER;
    n.vx -= n.x * CENTER;
    n.vy -= n.y * CENTER;
    n.vx *= DAMP; n.vy *= DAMP;
    n.vx = clamp(n.vx, -MAX_VEL, MAX_VEL);
    n.vy = clamp(n.vy, -MAX_VEL, MAX_VEL);
    n.x += clamp(n.vx, -MAX_STEP, MAX_STEP);
    n.y += clamp(n.vy, -MAX_STEP, MAX_STEP);

    if (D3) {
      n.z = n.z || 0;
      // Weaker z-centering so the cloud stays voluminous instead of
      // collapsing into a flat plane.
      n.vz = (n.vz || 0) - n.z * (CENTER * 0.25);
      n.vz *= DAMP;
      n.vz = clamp(n.vz, -MAX_VEL, MAX_VEL);
      n.z += clamp(n.vz, -MAX_STEP, MAX_STEP);
    }
  }
}

/* ---- Obsidian-style colour map for tagged notes -------------------------
   These are *fallbacks*. Each tag also reads a CSS variable
   (e.g. --tag-project) so styles.css can override per theme. */
const TAG_FALLBACKS = {
  '#project': '#7DB5B5',
  '#person':  '#C9B8E0',
  '#moc':     '#F0C674',
  '#idea':    '#E8A9A9',
  '#daily':   '#A5C4A1',
  '#archive': '#A39C8C',
};

function resolveTagColor(tag, computedStyle) {
  const varName = '--tag-' + tag.replace(/^#/, '');
  const v = computedStyle.getPropertyValue(varName).trim();
  return v || TAG_FALLBACKS[tag] || null;
}

/* ---- Color-by-mode helpers --------------------------------------------- */

/* Stable hash → 0..359 hue, bucketed into 12 evenly-spaced slots so similar
   folders are visually distinct rather than all "kinda blue". */
function folderHueFor(path) {
  const folder = (path || '').split('/').slice(0, -1).join('/') || '__root__';
  let h = 2166136261;
  for (let i = 0; i < folder.length; i++) {
    h ^= folder.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  const slot = Math.abs(h) % 12;
  return slot * 30; // 0,30,60,…,330
}

function folderColor(path, isDark) {
  return `hsl(${folderHueFor(path)}, ${isDark ? 55 : 45}%, ${isDark ? 65 : 60}%)`;
}

/* Heat gradient — sharp recency-aware color. Returns vivid red/orange for
   "today", warm yellow for "this week", cool blue for "this month", dim
   gray for older. Tuned to feel like a thermal camera. */
function heatmapColor(daysOld, isDark) {
  if (daysOld == null || isNaN(daysOld)) return isDark ? '#5a5670' : '#cdbfa5';
  const d = Math.max(0, daysOld);
  // Hot zones with sharp transitions.
  if (d < 1)   return isDark ? '#ff6b6b' : '#e84d4d';   // today
  if (d < 3)   return isDark ? '#ff9a5a' : '#e87a3d';   // last 3 days
  if (d < 7)   return isDark ? '#ffcc66' : '#d9a040';   // this week
  if (d < 14)  return isDark ? '#e8cc7a' : '#bfa05a';   // this fortnight
  if (d < 30)  return isDark ? '#a8b5d9' : '#6a8aa8';   // this month
  if (d < 90)  return isDark ? '#7a8aa0' : '#8a9aa8';   // last 3 months
  return isDark ? '#5a5670' : '#9a948a';                // older
}

/* Map a number into a cool→warm gradient. v ∈ [0,1] */
function gradientCoolWarm(v, isDark) {
  v = v < 0 ? 0 : v > 1 ? 1 : v;
  // Stops: deep teal → sage → cream → peach → rose
  const stops = isDark
    ? [[80,170,170],[150,200,150],[230,210,160],[235,170,140],[230,140,140]]
    : [[110,180,180],[160,200,150],[230,210,160],[230,170,140],[210,130,130]];
  const i = Math.min(stops.length - 2, Math.floor(v * (stops.length - 1)));
  const t = (v * (stops.length - 1)) - i;
  const a = stops[i], b = stops[i + 1];
  const r = Math.round(a[0] + (b[0]-a[0])*t);
  const g = Math.round(a[1] + (b[1]-a[1])*t);
  const bl = Math.round(a[2] + (b[2]-a[2])*t);
  return `rgb(${r},${g},${bl})`;
}

/* Resolve final fill given the current colorMode. Returns null if mode is
   'tags' and no tag matched (caller falls back to inlink-shade). */
function typeColor(type, isDark) {
  const t = type || 'note';
  const colors = {
    research: isDark ? '#9fd3ff' : '#3d7fb8',
    project:  isDark ? '#7db5b5' : '#2d8b8b',
    task:     isDark ? '#f0c674' : '#a57400',
    agent:    isDark ? '#c9b8e0' : '#7d5bb5',
    decision: isDark ? '#e8a9a9' : '#b84a4a',
    proposal: isDark ? '#ffcf99' : '#bd6b19',
    memory:   isDark ? '#a5c4a1' : '#4f8a49',
    code_file:isDark ? '#b7c9ff' : '#526fb8',
    risk:     isDark ? '#ff9d9d' : '#b83333',
    // HQ-state ingestion adds these extra node types alongside the vault notes:
    mission:        isDark ? '#ffe19a' : '#c08a30',  // gold — running work
    receipt:        isDark ? '#cfcfcf' : '#7a7a7a',  // grey — audit trail / past actions
    'message-thread': isDark ? '#cfb8e8' : '#7d5bb5', // soft violet — comms threads
    note:     isDark ? '#d8c9a8' : '#9c8555',
  };
  return colors[t] || colors.note;
}

function colorForNode(n, state, isDark, computedStyle) {
  // Cluster coloring overrides colorMode when toggled on.
  if (state.clusterColoring && state.clusters) {
    const idx = state.clusters.comp[n.id];
    if (idx != null) return clusterColor(idx, isDark);
  }
  const mode = state.colorMode || 'tags';
  if (mode === 'folder') {
    return folderColor(n.id, isDark);
  }
  if (mode === 'type') {
    return typeColor(n.type, isDark);
  }
  if (mode === 'inlinks') {
    const max = state.maxInlinks || 1;
    return gradientCoolWarm((n.inlinks || 0) / max, isDark);
  }
  if (mode === 'modified') {
    const r = state.mtimeRange;
    if (!r || !n.mtime) return null;
    const v = (n.mtime - r.min) / Math.max(1, r.max - r.min);
    return gradientCoolWarm(v, isDark);
  }
  if (mode === 'heatmap') {
    if (!n.mtime) return null;
    const daysOld = (Date.now() - n.mtime) / 86400000;
    return heatmapColor(daysOld, isDark);
  }
  // 'tags' default
  for (const t of (n.tags || [])) {
    const c = resolveTagColor(t, computedStyle);
    if (c) return c;
  }
  return null;
}

function nodeMatchesFilter(n, filter) {
  if (!filter) return true;
  const raw = String(filter).trim();
  if (!raw) return true;
  const ageDays = n.mtime ? (Date.now() - n.mtime) / 86400000 : 0;
  const isOrphan = (n.inlinks || 0) === 0;
  const hay = [n.title, n.id, n.path, n.type, ...(n.tags || [])].join(' ').toLowerCase();
  const evalTerm = (term) => {
    term = term.trim();
    if (!term) return true;
    let neg = false;
    if (term.startsWith('-')) { neg = true; term = term.slice(1).trim(); }
    const low = term.toLowerCase().replace(/^"|"$/g, '');
    let ok;
    if (low.startsWith('type:')) ok = String(n.type || 'note').toLowerCase() === low.slice(5);
    else if (low.startsWith('path:')) ok = String(n.id || '').toLowerCase().includes(low.slice(5).replace(/^"|"$/g, ''));
    else if (low.startsWith('tag:')) ok = (n.tags || []).some(t => String(t).replace(/^#/,'').toLowerCase().includes(low.slice(4).replace(/^#/,'').replace(/^"|"$/g, '')));
    else if (low.startsWith('file:')) ok = String(n.title || n.id || '').toLowerCase().includes(low.slice(5).replace(/^"|"$/g, ''));
    else if (low === 'orphan') ok = isOrphan;
    else if (low === 'stale') ok = !!n.mtime && ageDays > 60;
    else ok = hay.includes(low);
    return neg ? !ok : ok;
  };
  return raw.split(/\s+OR\s+/i).some(part => part.split(/\s+AND\s+|\s+/i).every(evalTerm));
}

function nodeIsVisible(n, state) {
  if (state.hiddenIds && state.hiddenIds.has(n.id)) return false;
  if (state.filter && !nodeMatchesFilter(n, state.filter)) return false;
  if (state.localVisible && !state.localVisible.has(n.id)) return false;
  // Time scrubber: hide notes newer than the scrub timestamp.
  if (state.timeScrub && n.mtime && n.mtime > state.timeScrub) return false;
  return true;
}

/* Compute centroid + member count for each cluster, used for label placement. */
function clusterCentroids(state) {
  if (!state.clusters) return [];
  const acc = {}; // idx → {sx,sy,n,members[]}
  for (const node of state.nodes) {
    if (state.hiddenIds && state.hiddenIds.has(node.id)) continue;
    const idx = state.clusters.comp[node.id];
    if (idx == null) continue;
    if (!acc[idx]) acc[idx] = { sx: 0, sy: 0, n: 0, members: [] };
    acc[idx].sx += node.x; acc[idx].sy += node.y; acc[idx].n += 1;
    acc[idx].members.push(node);
  }
  return Object.entries(acc)
    .filter(([, v]) => v.n >= 3) // skip tiny clusters
    .map(([idx, v]) => ({ idx: Number(idx), x: v.sx / v.n, y: v.sy / v.n, n: v.n, members: v.members }));
}

function nodeRadius(n) {
  return 3.5 + Math.sqrt(n.inlinks || 0) * 2.2;
}

/* Project a 3D world point into 2D screen space (relative to the canvas's
   transform). Returns {sx, sy, scale, depth}. The canvas is already
   translated by pan & scaled by zoom, so the returned (sx,sy) are in
   pre-pan/zoom world coords — render3D applies pan/zoom outside. */
function project3D(x, y, z, rotX, rotY) {
  const cy = Math.cos(rotY), sy = Math.sin(rotY);
  // Yaw around the y-axis: (x, z) → (x', z')
  const x1 = x * cy - z * sy;
  const z1 = x * sy + z * cy;
  // Pitch around the x-axis: (y, z') → (y', z'')
  const cx = Math.cos(rotX), sx = Math.sin(rotX);
  const y2 = y * cx - z1 * sx;
  const z2 = y * sx + z1 * cx;
  // Perspective: a focal length of 800 gives a soft 3D feel — points near
  // the camera grow, points behind shrink. Values < -700 are clamped to
  // avoid the projection blowing up.
  const FOC = 800;
  const eyeZ = z2 + 600; // push the cloud away from the camera
  const persp = FOC / Math.max(60, eyeZ);
  return { sx: x1 * persp, sy: y2 * persp, scale: persp, depth: z2 };
}

/* Edge-type rendering palette. Keys must match the `type` field that
   serve.py's _classify_edge produces. Each entry: { color, dash, widthMul }.
   `widthMul` multiplies the base lineWidth (1/zoom). Dash is an array of
   user-space (pre-zoom) lengths or null for solid.

   The grouping is roughly:
     - structural: child_of/parent_of (blue), supersedes (orange-dashed)
     - epistemic: cites (amber), supports (green), contradicts (red-dashed)
     - workflow:  blocks (red), depends_on (violet-dashed), implements (teal)
     - agent:     assigned_to, created_by, edited_by, reviewed_by (cyan)
     - signal:    has_risk (red-dotted), has_task (cyan-dashed), decided (gold)
     - soft:      related_to, notes, mentions (default color, lower weight)
   The default case (`links_to` and unknown types) falls through to the
   theme's edgeColor so nothing regresses visually. */
const EDGE_TYPE_STYLE = {
  links_to:      { color: null,                      dash: null,    widthMul: 1.0 },
  cites:         { color: 'rgba(207, 154, 71, 0.95)',dash: null,    widthMul: 1.4 },
  related_to:    { color: null,                      dash: [3, 4],  widthMul: 0.95, alphaMul: 0.85 },
  child_of:      { color: 'rgba(102, 145, 209, 0.95)',dash: null,   widthMul: 1.5 },
  parent_of:     { color: 'rgba(102, 145, 209, 0.95)',dash: null,   widthMul: 1.5 },
  implements:    { color: 'rgba(110, 178, 168, 0.95)',dash: null,   widthMul: 1.4 },
  implemented_by:{ color: 'rgba(110, 178, 168, 0.95)',dash: null,   widthMul: 1.4 },
  supports:      { color: 'rgba(120, 178, 95, 0.95)',dash: null,    widthMul: 1.4 },
  contradicts:   { color: 'rgba(217, 87, 87, 0.95)', dash: [6, 4],  widthMul: 1.6 },
  derived_from:  { color: 'rgba(170, 122, 196, 0.95)',dash: null,   widthMul: 1.3 },
  supersedes:    { color: 'rgba(232, 145, 80, 0.95)',dash: [8, 4],  widthMul: 1.5 },
  superseded_by: { color: 'rgba(232, 145, 80, 0.6)', dash: [4, 6],  widthMul: 1.0 },
  blocks:        { color: 'rgba(217, 87, 87, 0.95)', dash: null,    widthMul: 1.5 },
  blocked_by:    { color: 'rgba(217, 87, 87, 0.7)',  dash: [3, 3],  widthMul: 1.2 },
  depends_on:    { color: 'rgba(155, 124, 199, 0.9)',dash: [5, 4],  widthMul: 1.2 },
  has_risk:      { color: 'rgba(217, 87, 87, 0.85)', dash: [1.5, 2.5], widthMul: 1.2 },
  decided:       { color: 'rgba(220, 178, 89, 0.95)',dash: null,    widthMul: 1.6 },
  has_task:      { color: 'rgba(110, 178, 200, 0.9)',dash: [4, 4],  widthMul: 1.1 },
  has_proposal:  { color: 'rgba(155, 178, 195, 0.9)',dash: [4, 4],  widthMul: 1.1 },
  created_by:    { color: 'rgba(125, 181, 181, 0.9)',dash: null,    widthMul: 1.2 },
  edited_by:     { color: 'rgba(125, 181, 181, 0.7)',dash: [2, 4],  widthMul: 1.0 },
  assigned_to:   { color: 'rgba(125, 181, 181, 0.95)',dash: null,   widthMul: 1.4 },
  reviewed_by:   { color: 'rgba(125, 181, 181, 0.85)',dash: [3, 3], widthMul: 1.1 },
  notes:         { color: null,                      dash: null,    widthMul: 0.85, alphaMul: 0.7 },
  mentions:      { color: null,                      dash: [2, 5],  widthMul: 0.85, alphaMul: 0.65 },
  exemplifies:   { color: 'rgba(120, 178, 95, 0.85)',dash: [4, 3],  widthMul: 1.1 },
  questions:     { color: 'rgba(220, 178, 89, 0.9)', dash: [3, 6],  widthMul: 1.1 },
  // HQ-state edges (task/mission/receipt → vault notes & agents)
  references:    { color: null,                      dash: [2, 3],  widthMul: 0.95, alphaMul: 0.85 },
  produces:      { color: 'rgba(86, 168, 124, 0.95)',dash: null,    widthMul: 1.5 },
  modified:      { color: 'rgba(168, 124, 86, 0.85)',dash: [3, 3],  widthMul: 1.1 },
  targets:       { color: 'rgba(110, 178, 200, 0.9)',dash: [5, 4],  widthMul: 1.2 },
  runs_as:       { color: 'rgba(125, 181, 181, 1.0)',dash: null,    widthMul: 1.6 },
  // Message-thread edges (agent ↔ thread)
  sent_to:       { color: 'rgba(155, 124, 199, 0.95)',dash: null,   widthMul: 1.4 },
  received:      { color: 'rgba(155, 124, 199, 0.7)',dash: [4, 3],  widthMul: 1.2 },
  // Org-chart: assistant → senior. Solid teal, slightly heavier so the
  // hierarchy stands out among the noisier message/thread edges.
  reports_to:    { color: 'rgba(86, 138, 178, 1.0)',  dash: null,   widthMul: 1.7 },
};

/* Group edges by render style and stroke each group in one batched path.
   Falls back to a single batched pass with `defaultColor` when colored-edges
   is disabled (or when state.colorEdgesByType is false). `getXY` returns
   [x,y] for a node id — lets the same helper work for 2D and 3D. */
function _drawEdgesByType(ctx, edges, getXY, opts) {
  const {
    defaultColor, baseAlpha, baseLineWidth,
    enabled, hidden, focusId, byId, focusedSkip,
  } = opts;
  // Bucket edges by style key. Default bucket = no special styling.
  const buckets = new Map();
  const fallback = { type: '__default__', style: { color: null, dash: null, widthMul: 1.0 }};
  for (const e of edges) {
    const aId = e.source.id || e.source;
    const bId = e.target.id || e.target;
    const a = byId[aId]; const b = byId[bId];
    if (!a || !b) continue;
    if (hidden && (hidden.has(aId) || hidden.has(bId))) continue;
    if (focusedSkip && focusId && (aId === focusId || bId === focusId)) continue;
    let key = '__default__';
    if (enabled) {
      const t = e.type;
      if (t && EDGE_TYPE_STYLE[t]) key = t;
    }
    let bucket = buckets.get(key);
    if (!bucket) {
      const style = key === '__default__' ? fallback.style : EDGE_TYPE_STYLE[key];
      bucket = { style, segs: [] };
      buckets.set(key, bucket);
    }
    bucket.segs.push([a, b, e.confidence == null ? 1 : e.confidence]);
  }
  // Render each bucket. Heaviest/most-styled last so they sit on top.
  const order = ['__default__','notes','mentions','related_to','links_to'];
  const ordered = [];
  for (const k of order) if (buckets.has(k)) ordered.push(k);
  for (const k of buckets.keys()) if (!ordered.includes(k)) ordered.push(k);
  for (const k of ordered) {
    const { style, segs } = buckets.get(k);
    if (!segs.length) continue;
    ctx.strokeStyle = style.color || defaultColor;
    ctx.lineWidth = baseLineWidth * (style.widthMul || 1);
    const alpha = baseAlpha * (style.alphaMul == null ? 1 : style.alphaMul);
    ctx.globalAlpha = alpha;
    if (style.dash) ctx.setLineDash(style.dash.map(v => v * baseLineWidth));
    else ctx.setLineDash([]);
    ctx.beginPath();
    for (const [a, b] of segs) {
      const A = getXY(a); const B = getXY(b);
      ctx.moveTo(A[0], A[1]); ctx.lineTo(B[0], B[1]);
    }
    ctx.stroke();
  }
  ctx.setLineDash([]);
  ctx.globalAlpha = 1;
}

/* 3D-mode render. Sibling to render(); same overlays apply but nodes/edges
   are drawn with perspective and back-to-front depth sorting. */
function render3D(canvas, state, hover, selected) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const { width, height } = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
  }

  const style = getComputedStyle(canvas);
  const isDark = document.body.classList.contains('night');
  const edgeColor = isDark
    ? (style.getPropertyValue('--ink-3').trim() || '#a898be')
    : (style.getPropertyValue('--rule').trim() || '#cdbfa5');
  const labelColor = (style.getPropertyValue('--ink').trim() || '#3b2e2a');
  const labelRgb = hexToRgb(labelColor) || { r: 59, g: 46, b: 42 };
  const baseEdgeAlpha = isDark ? 0.55 : 0.40;
  const dimEdgeAlpha  = isDark ? 0.20 : 0.15;

  const { nodes, edges, pan, zoom } = state;
  const rotX = state.rot3D ? state.rot3D.rotX : 0;
  const rotY = state.rot3D ? state.rot3D.rotY : 0;
  const focusId  = selected || hover;
  const neighbors = getNeighbors(state, focusId);
  const focused = !!focusId;
  const filter = state.filter || '';
  const hidden = state.hiddenIds || new Set();

  ctx.clearRect(0, 0, width, height);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // Project every visible node once and cache on the node so getNodeAt can read.
  const visList = [];
  for (const n of nodes) {
    if (hidden.has(n.id)) continue;
    if (state.timeScrub && n.mtime && n.mtime > state.timeScrub) continue;
    const p = project3D(n.x, n.y, n.z || 0, rotX, rotY);
    n._sx = p.sx; n._sy = p.sy; n._scale = p.scale; n._depth = p.depth;
    visList.push(n);
  }
  // Sort back-to-front so far edges/nodes render under near ones.
  visList.sort((a, b) => b._depth - a._depth);
  // Also build a lookup for edge endpoints.
  const projById = {};
  for (const n of visList) projById[n.id] = n;

  // ---- Edges (base + highlighted pass) ---------------------------------
  // 3D variant uses projected screen coords (_sx, _sy) instead of raw x,y;
  // hidden + focused-skip semantics are identical to the 2D path.
  const get3D = (n) => [n._sx, n._sy];
  _drawEdgesByType(ctx, edges, get3D, {
    defaultColor: edgeColor,
    baseAlpha: focused ? dimEdgeAlpha : baseEdgeAlpha,
    baseLineWidth: 1 / zoom,
    enabled: !!(state.settings && state.settings.colorEdgesByType),
    hidden,
    focusId,
    byId: projById,
    focusedSkip: focused,
  });
  ctx.lineWidth = 1 / zoom;
  ctx.globalAlpha = 1;
  if (focused) {
    ctx.strokeStyle = 'rgba(232, 169, 169, 0.9)';
    ctx.lineWidth = 1.6 / zoom;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    for (const e of edges) {
      const a = projById[e.source.id || e.source];
      const b = projById[e.target.id || e.target];
      if (!a || !b) continue;
      if (!(a.id === focusId || b.id === focusId)) continue;
      ctx.moveTo(a._sx, a._sy);
      ctx.lineTo(b._sx, b._sy);
    }
    ctx.stroke();
  }

  // Ghost edges in 3D too.
  if (state.ghostEdges && state.ghostEdges.length) {
    ctx.save();
    ctx.setLineDash([4 / zoom, 4 / zoom]);
    ctx.lineWidth = 0.9 / zoom;
    for (const ge of state.ghostEdges) {
      const a = projById[ge.a]; const b = projById[ge.b];
      if (!a || !b) continue;
      ctx.globalAlpha = Math.min(0.5, ge.score * 0.9);
      ctx.strokeStyle = isDark ? 'rgba(201, 184, 224, 1)' : 'rgba(125, 181, 181, 1)';
      ctx.beginPath();
      ctx.moveTo(a._sx, a._sy);
      ctx.lineTo(b._sx, b._sy);
      ctx.stroke();
    }
    ctx.restore();
  }

  // Shortest-path emphasis edges.
  if (state.shortestPath && state.shortestPath.edges) {
    ctx.strokeStyle = 'rgba(240, 198, 116, 0.95)';
    ctx.lineWidth = 2.4 / zoom;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    for (const e of edges) {
      const a = projById[e.source.id || e.source];
      const b = projById[e.target.id || e.target];
      if (!a || !b) continue;
      const key = a.id < b.id ? a.id + '\0' + b.id : b.id + '\0' + a.id;
      if (state.shortestPath.edges.has(key)) {
        ctx.moveTo(a._sx, a._sy);
        ctx.lineTo(b._sx, b._sy);
      }
    }
    ctx.stroke();
  }

  // ---- Nodes (depth-sorted back to front) -----------------------------
  for (const n of visList) {
    const inlinks = n.inlinks || 0;
    const r0 = nodeRadius(n);
    const r = r0 * n._scale; // perspective scaling
    const isFocus    = selected === n.id || hover === n.id;
    const isNeighbor = neighbors && neighbors.has(n.id);
    const visible    = nodeIsVisible(n, state);
    const inCompare  = state.compare ? (state.compare.a.has(n.id) || state.compare.b.has(n.id)) : true;
    const dim        = (focused && !isNeighbor) || !visible || (state.compare && !inCompare);

    // Glow halo for focus + neighbours.
    if (isFocus || (focused && isNeighbor)) {
      const g = ctx.createRadialGradient(n._sx, n._sy, 0, n._sx, n._sy, r * 4);
      const col = isFocus ? '232, 169, 169' : '201, 184, 224';
      g.addColorStop(0, `rgba(${col}, ${isFocus ? 0.55 : 0.35})`);
      g.addColorStop(1, `rgba(${col}, 0)`);
      ctx.fillStyle = g;
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(n._sx, n._sy, r * 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Color resolution (mirrors 2D path).
    const modeFill = colorForNode(n, state, isDark, style);
    let compareFill = null;
    if (state.compare) {
      const inA = state.compare.a.has(n.id), inB = state.compare.b.has(n.id);
      if (inA && inB) compareFill = '#f0c674';
      else if (inA)   compareFill = '#7db5b5';
      else if (inB)   compareFill = '#e8a9a9';
    }
    let fill;
    if (selected === n.id)              fill = '#e8a9a9';
    else if (state.activePath === n.id) fill = '#f0c674';
    else if (hover === n.id)            fill = '#c9b8e0';
    else if (compareFill)               fill = compareFill;
    else if (modeFill)                  fill = modeFill;
    else if (inlinks >= 6)              fill = '#7db5b5';
    else if (inlinks >= 1)              fill = '#bfa9d9';
    else                                fill = '#d8c9a8';

    ctx.globalAlpha = dim ? 0.18 : 1;
    ctx.beginPath();
    ctx.arc(n._sx, n._sy, r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = 'rgba(59, 46, 42, 0.45)';
    ctx.lineWidth = 1 / zoom;
    ctx.stroke();

    // Multi-select ring.
    if (state.selectedSet && state.selectedSet.has(n.id)) {
      ctx.strokeStyle = 'rgba(125, 181, 181, 0.95)';
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.arc(n._sx, n._sy, r + 5 / zoom, 0, Math.PI * 2);
      ctx.stroke();
    }
    // Agent activity halo.
    if (state.agentActivity && state.agentActivity.has(n.id)) {
      const act = state.agentActivity.get(n.id);
      const phase = ((Date.now() - (act.until - 5000)) % 1500) / 1500;
      const ringR = r + (4 + phase * 10) / zoom;
      ctx.save();
      ctx.globalAlpha = 0.55 * (1 - phase);
      ctx.strokeStyle = act.color || '#7db5b5';
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.arc(n._sx, n._sy, ringR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }
    // Orphan ring.
    if (state.highlightOrphans) {
      const isOrphan  = (n.inlinks  || 0) === 0;
      const isDeadEnd = (n.outlinks || 0) === 0;
      if (isOrphan || isDeadEnd) {
        ctx.save();
        ctx.setLineDash([3 / zoom, 3 / zoom]);
        ctx.strokeStyle = isOrphan && isDeadEnd
          ? 'rgba(220, 90, 90, 0.85)'
          : isOrphan ? 'rgba(220, 130, 90, 0.75)' : 'rgba(220, 180, 80, 0.65)';
        ctx.lineWidth = 1.4 / zoom;
        ctx.beginPath();
        ctx.arc(n._sx, n._sy, r + 4 / zoom, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }
  }

  // Pulses (interpolate along projected positions).
  if (state.pulses.size > 0) {
    const now = Date.now();
    ctx.fillStyle = 'rgba(232, 169, 169, 0.95)';
    ctx.globalAlpha = 1;
    for (const [key, p] of state.pulses.entries()) {
      const elapsed = (now - p.start) / 1000;
      if (elapsed > 1.2) { state.pulses.delete(key); continue; }
      const a = projById[p.edge.source.id || p.edge.source];
      const b = projById[p.edge.target.id || p.edge.target];
      if (!a || !b) continue;
      const t = elapsed / 1.2;
      const x = a._sx + (b._sx - a._sx) * t;
      const y = a._sy + (b._sy - a._sy) * t;
      ctx.beginPath();
      ctx.arc(x, y, 2.6 / zoom, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // Labels (hover + selected always; others honour showAllLabels / zoom).
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  const drawLabel = (n, alpha) => {
    const r = nodeRadius(n) * n._scale;
    const fontPx = (11 * n._scale) / zoom;
    ctx.font = `${Math.max(8, fontPx)}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = `rgba(${labelRgb.r}, ${labelRgb.g}, ${labelRgb.b}, 0.92)`;
    ctx.fillText(n.title || n.id, n._sx, n._sy + r + (4 / zoom));
  };
  if (state.showAllLabels) {
    for (const n of visList) drawLabel(n, 0.85);
  } else if (zoom > 1.4) {
    const a = Math.min(1, (zoom - 1.4) / 0.5);
    for (const n of visList) {
      if (focused && !neighbors.has(n.id)) continue;
      drawLabel(n, a);
    }
  } else if (focused && neighbors) {
    for (const id of neighbors) {
      const n = projById[id];
      if (n) drawLabel(n, n.id === selected || n.id === hover ? 1 : 0.7);
    }
  }
  if (hover && projById[hover]) drawLabel(projById[hover], 1);

  ctx.restore();

  // ---- Screen-space overlays (lasso, link drag) -----------------------
  if (state.lassoRect) {
    const r = state.lassoRect;
    const x = Math.min(r.x0, r.x1), y = Math.min(r.y0, r.y1);
    const w = Math.abs(r.x1 - r.x0), h = Math.abs(r.y1 - r.y0);
    ctx.save();
    ctx.fillStyle = 'rgba(125, 181, 181, 0.12)';
    ctx.strokeStyle = 'rgba(125, 181, 181, 0.85)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([4, 4]);
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
    ctx.restore();
  }
  if (state.linkDrag) {
    const ld = state.linkDrag;
    const fromNode = state.byId[ld.fromId];
    if (fromNode && fromNode._sx != null) {
      const sx = state.pan.x + fromNode._sx * state.zoom;
      const sy = state.pan.y + fromNode._sy * state.zoom;
      ctx.save();
      ctx.strokeStyle = 'rgba(232, 169, 169, 0.9)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(ld.endX, ld.endY);
      ctx.stroke();
      ctx.restore();
    }
  }

  // 3D camera indicator (small axes gizmo bottom-left).
  ctx.save();
  ctx.translate(36, height - 36);
  const drawAxis = (vec3, color, label) => {
    const p = project3D(vec3[0], vec3[1], vec3[2], rotX, rotY);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(p.sx, p.sy);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(p.sx, p.sy, 2.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = '700 9px sans-serif';
    ctx.fillText(label, p.sx + 4, p.sy + 3);
  };
  drawAxis([22, 0, 0], '#e84d4d', 'X');
  drawAxis([0, 22, 0], '#5a9a5a', 'Y');
  drawAxis([0, 0, 22], '#5a8acf', 'Z');
  ctx.restore();
}

function render(canvas, state, hover, selected) {
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const { width, height } = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
    canvas.width  = width  * dpr;
    canvas.height = height * dpr;
    ctx.scale(dpr, dpr);
  }

  // Theme-aware colours from CSS variables.
  // In night mode --rule is too dim against the dark paper, so use --ink-3
  // (which is tuned brighter) and bump alpha for connections.
  const style = getComputedStyle(canvas);
  const isDark = document.body.classList.contains('night');
  const edgeColor = isDark
    ? (style.getPropertyValue('--ink-3').trim() || '#a898be')
    : (style.getPropertyValue('--rule').trim() || '#cdbfa5');
  const labelColor = (style.getPropertyValue('--ink').trim() || '#3b2e2a');
  const labelRgb = hexToRgb(labelColor) || { r: 59, g: 46, b: 42 };
  const baseEdgeAlpha = isDark ? 0.7 : 0.45;
  const dimEdgeAlpha  = isDark ? 0.30 : 0.18;

  const { nodes, edges, pan, zoom } = state;
  const focusId  = selected || hover;
  const neighbors = getNeighbors(state, focusId);
  const filter = state.filter || '';
  const focused = !!focusId;

  ctx.clearRect(0, 0, width, height);
  ctx.save();
  ctx.translate(pan.x, pan.y);
  ctx.scale(zoom, zoom);

  // -------- Edges -------------------------------------------------------
  // Two passes: dim edges first, highlighted edges on top.
  // Pass 1 = bulk base edges, grouped by edge.type when colorEdgesByType is on
  // (off by default for backwards-compat — toggled in settings panel).
  const hidden = state.hiddenIds || new Set();
  const get2D = (n) => [n.x, n.y];
  _drawEdgesByType(ctx, edges, get2D, {
    defaultColor: edgeColor,
    baseAlpha: focused ? dimEdgeAlpha : baseEdgeAlpha,
    baseLineWidth: 1 / zoom,
    enabled: !!(state.settings && state.settings.colorEdgesByType),
    hidden,
    focusId,
    byId: state.byId,
    focusedSkip: focused, // skip focused edges here, redrawn in pass 2
  });
  ctx.lineWidth = 1 / zoom;
  ctx.globalAlpha = 1;

  // Pass 2 — highlighted edges (connected to focus)
  if (focused) {
    ctx.strokeStyle = 'rgba(232, 169, 169, 0.85)';
    ctx.lineWidth = 1.6 / zoom;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    for (const e of edges) {
      const a = state.byId[e.source.id || e.source];
      const b = state.byId[e.target.id || e.target];
      if (!a || !b) continue;
      if (hidden.has(a.id) || hidden.has(b.id)) continue;
      if (!(a.id === focusId || b.id === focusId)) continue;
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
    }
    ctx.stroke();
    ctx.lineWidth = 1 / zoom;
  }

  // Ghost edges — dashed lines for high-similarity unlinked pairs.
  if (state.ghostEdges && state.ghostEdges.length) {
    ctx.save();
    ctx.setLineDash([4 / zoom, 4 / zoom]);
    ctx.lineWidth = 0.9 / zoom;
    for (const ge of state.ghostEdges) {
      const a = state.byId[ge.a]; const b = state.byId[ge.b];
      if (!a || !b) continue;
      if (state.hiddenIds && (state.hiddenIds.has(a.id) || state.hiddenIds.has(b.id))) continue;
      // Strength → opacity; cap at 0.5 so they always feel "ambient."
      ctx.globalAlpha = Math.min(0.5, ge.score * 0.9);
      ctx.strokeStyle = isDark ? 'rgba(201, 184, 224, 1)' : 'rgba(125, 181, 181, 1)';
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.stroke();
    }
    ctx.restore();
  }

  // Pass 3 — shortest-path edges (thick, rose-gold) — only consecutive pairs.
  if (state.shortestPath && state.shortestPath.edges && state.shortestPath.edges.size > 0) {
    ctx.strokeStyle = 'rgba(240, 198, 116, 0.95)';
    ctx.lineWidth = 2.4 / zoom;
    ctx.globalAlpha = 1;
    ctx.beginPath();
    for (const e of edges) {
      const a = state.byId[e.source.id || e.source];
      const b = state.byId[e.target.id || e.target];
      if (!a || !b) continue;
      const key = a.id < b.id ? a.id + '\0' + b.id : b.id + '\0' + a.id;
      if (state.shortestPath.edges.has(key)) {
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
      }
    }
    ctx.stroke();
    ctx.lineWidth = 1 / zoom;
  }

  // -------- Pulses (animated dots travelling along edges) ---------------
  if (state.pulses.size > 0) {
    const now = Date.now();
    ctx.fillStyle = 'rgba(232, 169, 169, 0.95)';
    ctx.globalAlpha = 1;
    for (const [key, p] of state.pulses.entries()) {
      const elapsed = (now - p.start) / 1000;
      if (elapsed > 1.2) { state.pulses.delete(key); continue; }
      const a = state.byId[p.edge.source.id || p.edge.source];
      const b = state.byId[p.edge.target.id || p.edge.target];
      if (!a || !b) continue;
      const t = elapsed / 1.2;
      const x = a.x + (b.x - a.x) * t;
      const y = a.y + (b.y - a.y) * t;
      ctx.beginPath();
      ctx.arc(x, y, 2.6 / zoom, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // -------- Nodes (with soft glow for selected + neighbours) ------------
  for (const n of nodes) {
    if (state.hiddenIds && state.hiddenIds.has(n.id)) continue; // truly hidden
    const inlinks = n.inlinks || 0;
    const r = nodeRadius(n);
    const isFocus    = selected === n.id || hover === n.id;
    const isNeighbor = neighbors && neighbors.has(n.id);
    const visible    = nodeIsVisible(n, state);
    const inCompare  = state.compare ? (state.compare.a.has(n.id) || state.compare.b.has(n.id)) : true;
    const dim        = (focused && !isNeighbor) || !visible || (state.compare && !inCompare);

    // Soft glow underlay for the focused node and its neighbours.
    if (isFocus || (focused && isNeighbor)) {
      const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 4);
      const col = isFocus ? '232, 169, 169' : '201, 184, 224';
      g.addColorStop(0, `rgba(${col}, ${isFocus ? 0.55 : 0.35})`);
      g.addColorStop(1, `rgba(${col}, 0)`);
      ctx.fillStyle = g;
      ctx.globalAlpha = 1;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r * 4, 0, Math.PI * 2);
      ctx.fill();
    }

    // Color resolution (selected/active/hover always win, then color-by-mode,
    // then inlink-based fallback shade).
    const modeFill = colorForNode(n, state, isDark, style);
    let fill;
    // Compare-mode wins over coloring schemes — left side teal, right side rose,
    // shared nodes gold, all others dim.
    let compareFill = null;
    let compareDim  = false;
    if (state.compare) {
      const inA = state.compare.a.has(n.id);
      const inB = state.compare.b.has(n.id);
      if (inA && inB)         compareFill = '#f0c674';
      else if (inA)           compareFill = '#7db5b5';
      else if (inB)           compareFill = '#e8a9a9';
      else                    compareDim  = true;
    }
    if (selected === n.id)              fill = '#e8a9a9';
    else if (state.activePath === n.id) fill = '#f0c674';
    else if (hover === n.id)            fill = '#c9b8e0';
    else if (compareFill)               fill = compareFill;
    else if (modeFill)                  fill = modeFill;
    else if (inlinks >= 6)              fill = '#7db5b5';
    else if (inlinks >= 1)              fill = '#bfa9d9';
    else                                fill = '#d8c9a8';

    ctx.globalAlpha = dim ? 0.18 : 1;
    ctx.beginPath();
    ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
    ctx.fillStyle = fill;
    ctx.fill();
    ctx.strokeStyle = 'rgba(59, 46, 42, 0.45)';
    ctx.lineWidth = 1 / zoom;
    ctx.stroke();

    // Orphan / dead-end ring (notes with no incoming or no outgoing links).
    if (state.highlightOrphans) {
      const isOrphan  = (n.inlinks  || 0) === 0;
      const isDeadEnd = (n.outlinks || 0) === 0;
      if (isOrphan || isDeadEnd) {
        ctx.save();
        ctx.setLineDash([3 / zoom, 3 / zoom]);
        ctx.strokeStyle = isOrphan && isDeadEnd
          ? 'rgba(220, 90, 90, 0.85)'
          : isOrphan ? 'rgba(220, 130, 90, 0.75)' : 'rgba(220, 180, 80, 0.65)';
        ctx.lineWidth = 1.4 / zoom;
        ctx.beginPath();
        ctx.arc(n.x, n.y, r + 4 / zoom, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
    }

    // Multi-select ring (lasso pick).
    if (state.selectedSet && state.selectedSet.has(n.id)) {
      ctx.save();
      ctx.strokeStyle = 'rgba(125, 181, 181, 0.95)';
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r + 5 / zoom, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // Live agent activity halo — pulse a ring at the agent's color when the
    // agent is currently reading/writing this note.
    if (state.agentActivity && state.agentActivity.has(n.id)) {
      const act = state.agentActivity.get(n.id);
      const phase = ((Date.now() - (act.until - 5000)) % 1500) / 1500;
      const ringR = r + (4 + phase * 10) / zoom;
      ctx.save();
      ctx.globalAlpha = 0.55 * (1 - phase);
      ctx.strokeStyle = act.color || '#7db5b5';
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.arc(n.x, n.y, ringR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    // Shortest-path glow.
    if (state.shortestPath && state.shortestPath.nodes && state.shortestPath.nodes.has(n.id)) {
      ctx.save();
      const grd = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, r * 4);
      grd.addColorStop(0, 'rgba(240, 198, 116, 0.7)');
      grd.addColorStop(1, 'rgba(240, 198, 116, 0)');
      ctx.globalAlpha = 1;
      ctx.fillStyle = grd;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r * 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  // -------- Labels ------------------------------------------------------
  // Always draw the hovered label. Otherwise draw zoomed-in labels or all-on.
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';

  const drawLabel = (n, alpha) => {
    const r = nodeRadius(n);
    const fontPx = 11 / zoom;
    ctx.font = `${fontPx}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = `rgba(${labelRgb.r}, ${labelRgb.g}, ${labelRgb.b}, 0.92)`;
    ctx.fillText(n.title || n.id, n.x, n.y + r + (4 / zoom));
  };

  if (state.showAllLabels) {
    for (const n of nodes) {
      if (!nodeIsVisible(n, state)) continue;
      drawLabel(n, 0.85);
    }
  } else if (zoom > 1.4) {
    const a = Math.min(1, (zoom - 1.4) / 0.5);
    for (const n of nodes) {
      if (!nodeIsVisible(n, state)) continue;
      if (focused && !neighbors.has(n.id)) continue;
      drawLabel(n, a);
    }
  } else if (focused && neighbors) {
    // Show labels for the focused node + neighbours
    for (const id of neighbors) {
      const n = state.byId[id];
      if (n) drawLabel(n, n.id === selected || n.id === hover ? 1 : 0.7);
    }
  }

  // Hover label is always rendered prominently.
  if (hover && state.byId[hover]) {
    drawLabel(state.byId[hover], 1);
  }

  // -------- Cluster labels (overlay text at cluster centroids) ----------
  if (state.clusterColoring && state.clusters && state.clusterLabels) {
    const centroids = clusterCentroids(state);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    for (const c of centroids) {
      const label = state.clusterLabels[c.idx];
      if (!label) continue;
      const fontPx = Math.max(14, Math.min(28, 10 + Math.sqrt(c.n) * 2)) / zoom;
      ctx.font = `700 ${fontPx}px -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif`;
      // Pillow background
      const metrics = ctx.measureText(label);
      const w = metrics.width + 16 / zoom;
      const h = fontPx + 8 / zoom;
      ctx.globalAlpha = 0.85;
      ctx.fillStyle = `rgba(${labelRgb.r}, ${labelRgb.g}, ${labelRgb.b}, 0.10)`;
      ctx.beginPath();
      const rad = 4 / zoom;
      ctx.roundRect ? ctx.roundRect(c.x - w/2, c.y - h/2, w, h, rad) : ctx.rect(c.x - w/2, c.y - h/2, w, h);
      ctx.fill();
      ctx.globalAlpha = 0.92;
      ctx.fillStyle = `rgba(${labelRgb.r}, ${labelRgb.g}, ${labelRgb.b}, 0.92)`;
      ctx.fillText(label, c.x, c.y);
    }
  }

  ctx.restore();

  // -------- Screen-space overlays: lasso rect + link-drag rubber band ---
  // (Drawn after restore so they're in unscaled screen coords.)
  if (state.lassoRect) {
    const r = state.lassoRect;
    const x = Math.min(r.x0, r.x1), y = Math.min(r.y0, r.y1);
    const w = Math.abs(r.x1 - r.x0), h = Math.abs(r.y1 - r.y0);
    ctx.save();
    ctx.fillStyle = 'rgba(125, 181, 181, 0.12)';
    ctx.strokeStyle = 'rgba(125, 181, 181, 0.85)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([4, 4]);
    ctx.fillRect(x, y, w, h);
    ctx.strokeRect(x, y, w, h);
    ctx.restore();
  }
  if (state.linkDrag) {
    const ld = state.linkDrag;
    const fromNode = state.byId[ld.fromId];
    if (fromNode) {
      const sx = state.pan.x + fromNode.x * state.zoom;
      const sy = state.pan.y + fromNode.y * state.zoom;
      ctx.save();
      ctx.strokeStyle = 'rgba(232, 169, 169, 0.9)';
      ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.beginPath();
      ctx.moveTo(sx, sy);
      ctx.lineTo(ld.endX, ld.endY);
      ctx.stroke();
      ctx.fillStyle = 'rgba(232, 169, 169, 1)';
      ctx.beginPath();
      ctx.arc(ld.endX, ld.endY, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }
}


/* ================================================================
   Missing components — reconstructed after external file corruption
   ================================================================ */

/* ---------------- Custom Markdown renderer (no marked.js) ---------------- */
function renderMarkdown(text) {
  if (!text) return '';
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s) => {
    s = esc(s);
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
    s = s.replace(/`(.+?)`/g, '<code>$1</code>');
    s = s.replace(/\[\[(.+?)\]\]/g, '<span class="md-tag">$1</span>');
    s = s.replace(/#([\w-]+)/g, '<span class="md-tag">#$1</span>');
    s = s.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2">$1</a>');
    return s;
  };

  let html = '';
  const lines = text.split('\n');
  let i = 0;

  /* Frontmatter block */
  if (lines[0] === '---') {
    i = 1;
    const fmLines = [];
    while (i < lines.length && lines[i] !== '---') { fmLines.push(lines[i]); i++; }
    if (i < lines.length) i++;
    if (fmLines.length > 0) {
      const fmHtml = fmLines.map(l => {
        const m = l.match(/^([\w ]+):\s*(.*)/);
        return m
          ? '<div><span class="md-fm-label">' + esc(m[1]) + ':</span> ' + esc(m[2]) + '</div>'
          : '<div>' + esc(l) + '</div>';
      }).join('');
      html += '<div class="md-frontmatter">' + fmHtml + '</div>';
    }
  }

  let inCode = false;
  let codeLines = [];

  while (i < lines.length) {
    const line = lines[i];

    /* Fenced code blocks */
    if (line.startsWith('```')) {
      if (inCode) {
        html += '<pre class="md-pre"><code>' + esc(codeLines.join('\n')) + '</code></pre>';
        codeLines = [];
        inCode = false;
      } else {
        inCode = true;
      }
      i++; continue;
    }
    if (inCode) { codeLines.push(line); i++; continue; }

    /* Headings */
    const hm = line.match(/^(#{1,6})\s+(.*)/);
    if (hm) { html += '<div class="md-h md-h' + hm[1].length + '">' + inline(hm[2]) + '</div>'; i++; continue; }

    /* Unordered lists */
    if (line.startsWith('- ') || line.startsWith('* ')) {
      let items = '';
      while (i < lines.length && (lines[i].startsWith('- ') || lines[i].startsWith('* '))) {
        items += '<li>' + inline(lines[i].slice(2)) + '</li>';
        i++;
      }
      html += '<ul class="md-ul">' + items + '</ul>';
      continue;
    }

    /* Ordered lists */
    if (/^\d+\.\s/.test(line)) {
      let items = '';
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items += '<li>' + inline(lines[i].replace(/^\d+\.\s+/, '')) + '</li>';
        i++;
      }
      html += '<ol class="md-ol">' + items + '</ol>';
      continue;
    }

    /* Blank line */
    if (line.trim() === '') { i++; continue; }

    /* Paragraph */
    html += '<p class="md-p">' + inline(line) + '</p>';
    i++;
  }

  /* Unclosed code block */
  if (inCode && codeLines.length > 0) {
    html += '<pre class="md-pre"><code>' + esc(codeLines.join('\n')) + '</code></pre>';
  }

  return html;
}

/* ---------------- Parse DIR_LIST output into entry objects ----------------
   serve.py /tools/exec DIR_LIST returns one entry per line:
     "Subfolder/"
     "filename.md  (1234 B)"
     "(empty directory)"  // sentinel
     "…(truncated at 300 entries)"  // sentinel
*/
function parseDirEntries(text, basePath) {
  if (typeof text !== 'string') text = String(text || '');
  // Pick directory separator based on what the basePath uses (Windows uses \).
  const useBackslash = /\\/.test(basePath) && !/\//.test(basePath);
  const sep = useBackslash ? '\\' : '/';
  const trimEndSep = (s) => s.replace(/[/\\]+$/, '');

  const out = [];
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('(') || line.startsWith('…')) continue; // sentinels
    const isDir = line.endsWith('/');
    let name, size = 0;
    if (isDir) {
      name = line.slice(0, -1);
    } else {
      // "filename  (1234 B)" — capture name and size separately if present.
      const m = line.match(/^(.+?)\s+\((\d+)\s*B\)\s*$/);
      if (m) { name = m[1]; size = parseInt(m[2], 10) || 0; }
      else   { name = line; }
    }
    out.push({
      name,
      isDir,
      size,
      path: trimEndSep(basePath) + sep + name,
    });
  }
  return out;
}

/* ---------------- Local file-tree with lazy sub-directory loading ---------------- */
function LocalTree({ path, onSelectFile, refreshNonce, onRename, onDelete, onUploadTo, pulsePaths }) {
  const [entries, setEntries] = useSV(null);
  const [expanded, setExpanded] = useSV(new Set());
  const [subEntries, setSubEntries] = useSV({});
  const [loading, setLoading] = useSV(false);
  const [err, setErr] = useSV(null);
  const [dropDir, setDropDir] = useSV(null);   // folder row being dragged over

  /* Collapse + clear cached sub-listings only when the project PATH changes.
     A refresh (refreshNonce bump after an upload) deliberately keeps expanded
     state: dropped files always land in the root, so only the root listing
     needs to change — losing the user's open subfolders would be a regression. */
  React.useEffect(() => {
    setExpanded(new Set());
    setSubEntries({});
  }, [path]);

  /* Re-fetch the root listing when the path changes OR refreshNonce bumps. */
  React.useEffect(() => {
    if (!path) return;
    setLoading(true);
    setErr(null);
    window.CafresoHQClient.toolExec('DIR_LIST', path)
      .then(text => { setEntries(parseDirEntries(text, path)); setLoading(false); })
      .catch(e => { setErr(e.message || String(e)); setLoading(false); });
  }, [path, refreshNonce]);

  const loadSub = (subPath) => {
    if (subEntries[subPath]) return;
    window.CafresoHQClient.toolExec('DIR_LIST', subPath)
      .then(text => { setSubEntries(prev => ({ ...prev, [subPath]: parseDirEntries(text, subPath) })); })
      .catch(() => { setSubEntries(prev => ({ ...prev, [subPath]: [] })); });
  };

  const toggle = (p) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(p)) next.delete(p);
      else { next.add(p); loadSub(p); }
      return next;
    });
  };

  /* Hover/tap actions on a row: upload-here (folders only), rename, delete.
     stopPropagation so they don't trigger the row's open/toggle. */
  const rowActions = (e) => (
    <span className="tree-actions" onClick={ev => ev.stopPropagation()}>
      {onUploadTo && e.isDir && <button className="tree-act" title="Upload files here" onClick={ev => { ev.stopPropagation(); onUploadTo(e); }}>📤</button>}
      {onRename && <button className="tree-act" title="Rename" onClick={ev => { ev.stopPropagation(); onRename(e); }}>✎</button>}
      {onDelete && <button className="tree-act" title="Delete" onClick={ev => { ev.stopPropagation(); onDelete(e); }}>🗑</button>}
    </span>
  );

  const renderEntries = (list, depth) => list.map(e => {
    if (e.isDir) {
      const isOpen = expanded.has(e.path);
      const kids = subEntries[e.path];
      const dropProps = onUploadTo ? {
        onDragOver: (ev) => { ev.preventDefault(); ev.stopPropagation(); setDropDir(e.path); },
        onDragLeave: (ev) => { if (!ev.currentTarget.contains(ev.relatedTarget)) setDropDir(null); },
        onDrop: (ev) => { ev.preventDefault(); ev.stopPropagation(); setDropDir(null); if (ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files.length) onUploadTo(e, ev.dataTransfer.files); },
      } : {};
      return (
        <div key={e.path}>
          <div className={'tree-row tree-folder' + (isOpen ? ' open' : '') + (dropDir === e.path ? ' drop-target' : '') + (pulsePaths && pulsePaths.has(e.path) ? ' agent-wrote' : '')} style={{paddingLeft: 10 + depth * 14}} onClick={() => toggle(e.path)} {...dropProps}>
            <span className="tree-chev">{isOpen ? '▾' : '▸'}</span>
            <span className="tree-icon">{isOpen ? '📂' : '📁'}</span>
            <span className="tree-name">{e.name}</span>
            {pulsePaths && pulsePaths.has(e.path) && <span className="tree-agent-dot" title="just written by an agent">A</span>}
            {rowActions(e)}
          </div>
          {isOpen && kids && renderEntries(kids, depth + 1)}
          {isOpen && !kids && <div style={{paddingLeft: 6 + (depth + 1) * 14, fontSize: 9, opacity: 0.5}}>Loading…</div>}
        </div>
      );
    }
    return (
      <div key={e.path} className={'tree-row tree-file' + (pulsePaths && pulsePaths.has(e.path) ? ' agent-wrote' : '')} style={{paddingLeft: 10 + depth * 14 + 14}} onClick={() => onSelectFile && onSelectFile(e.path)}>
        <span className="tree-name">{e.name}</span>
        {pulsePaths && pulsePaths.has(e.path) && <span className="tree-agent-dot" title="just written by an agent">A</span>}
        {e.size > 0 && <span className="tree-size">{e.size < 1024 ? `${e.size} B` : `${(e.size / 1024).toFixed(1)} KB`}</span>}
        {rowActions(e)}
      </div>
    );
  });

  if (!path) return <div className="proj-empty-msg">No project path set.</div>;
  if (loading) return <div className="proj-empty-msg">Loading…</div>;
  if (err) return <div className="proj-empty-msg" style={{color: 'var(--danger)'}}>Error: {err}</div>;
  if (!entries) return null;
  return <div className="tree-root">{renderEntries(entries, 0)}</div>;
}

/* ---------------- Projects view (with file editing) ---------------- */
/* Simple language detection from filename — used to pick a label and to
   tweak the syntax highlighter when something obvious like a comment
   prefix differs (//, #, --). Default falls back to JS-ish tinting which
   covers most code we'd see. */
function ideLangFromPath(p) {
  if (!p) return 'text';
  const lower = String(p).toLowerCase();
  if (/\.(jsx?|tsx?|mjs)$/.test(lower)) return 'javascript';
  if (/\.py$/.test(lower)) return 'python';
  if (/\.rs$/.test(lower)) return 'rust';
  if (/\.go$/.test(lower)) return 'go';
  if (/\.(c|h|cc|cpp|hpp)$/.test(lower)) return 'c';
  if (/\.css$/.test(lower)) return 'css';
  if (/\.html?$/.test(lower)) return 'html';
  if (/\.json$/.test(lower)) return 'json';
  if (/\.md$/.test(lower)) return 'markdown';
  if (/\.toml$/.test(lower)) return 'toml';
  if (/\.ya?ml$/.test(lower)) return 'yaml';
  if (/\.sh$/.test(lower)) return 'shell';
  return 'text';
}
function ideFileIcon(p) {
  const l = ideLangFromPath(p);
  return ({
    javascript: '𝙅𝙎', python: '🐍', rust: '🦀', go: 'GO',
    c: 'C', css: '🎨', html: '🌐', json: '{}', markdown: 'M↓',
    toml: '⚙', yaml: '⚙', shell: '$', text: '📄',
  })[l] || '📄';
}

/* Light-touch IDE-feel editor — keeps the textarea (so all keyboard
   behavior works) but layers a syntax-tinted <pre> behind it for visual
   highlighting, plus a gutter of line numbers that scrolls with content.
   Not Monaco — but feels like an editor instead of a notepad, and ships
   in 50 LOC instead of 200KB. */
function IDEEditor({ value, onChange, path }) {
  const taRef = useRV(null);
  const gutterRef = useRV(null);
  const overlayRef = useRV(null);
  const minimapRef = useRV(null);
  const minimapThumbRef = useRV(null);
  const lineCount = value.split('\n').length;
  const lang = ideLangFromPath(path);
  const _isMobileIDE = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;

  /* Sync scroll between textarea, the syntax overlay <pre>, the line-
     number gutter, and the minimap viewport indicator. The textarea is
     the "source of truth" — scrolling it scrolls the others. */
  const onScroll = () => {
    const ta = taRef.current; if (!ta) return;
    if (gutterRef.current) gutterRef.current.scrollTop = ta.scrollTop;
    if (overlayRef.current) {
      overlayRef.current.scrollTop = ta.scrollTop;
      overlayRef.current.scrollLeft = ta.scrollLeft;
    }
    // Minimap viewport thumb
    if (minimapRef.current && minimapThumbRef.current) {
      const mm = minimapRef.current;
      const ratio = ta.scrollTop / (ta.scrollHeight - ta.clientHeight || 1);
      const thumbH = Math.max(20, (ta.clientHeight / ta.scrollHeight) * mm.scrollHeight);
      const thumbTop = ratio * (mm.clientHeight - thumbH);
      minimapThumbRef.current.style.height = thumbH + 'px';
      minimapThumbRef.current.style.top = thumbTop + 'px';
    }
  };

  /* Tab inserts 2 spaces (no tab character — keeps diffs consistent and
     avoids screen jumps). Shift-Tab dedents the current line. */
  const onKey = (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const ta = e.target;
      const start = ta.selectionStart, end = ta.selectionEnd;
      if (e.shiftKey) {
        const before = value.slice(0, start);
        const lineStart = before.lastIndexOf('\n') + 1;
        const head = value.slice(0, lineStart);
        const middle = value.slice(lineStart, end);
        const dedented = middle.replace(/^( {1,2})/gm, '');
        const tail = value.slice(end);
        onChange(head + dedented + tail);
      } else {
        const next = value.slice(0, start) + '  ' + value.slice(end);
        onChange(next);
        requestAnimationFrame(() => {
          if (taRef.current) {
            taRef.current.selectionStart = taRef.current.selectionEnd = start + 2;
          }
        });
      }
    }
  };

  /* Click on minimap scrolls to that position */
  const onMinimapClick = (e) => {
    const ta = taRef.current;
    const mm = minimapRef.current;
    if (!ta || !mm) return;
    const rect = mm.getBoundingClientRect();
    const ratio = (e.clientY - rect.top) / rect.height;
    ta.scrollTop = ratio * (ta.scrollHeight - ta.clientHeight);
  };

  const tinted = ideTintCode(value, lang);
  const lineNumbers = Array.from({ length: lineCount }, (_, i) => i + 1).join('\n');

  return (
    <div className="ide-editor-wrap">
      <div className="ide-gutter" ref={gutterRef}>
        <pre>{lineNumbers}</pre>
      </div>
      <div className="ide-edit-area">
        <pre className="ide-overlay" ref={overlayRef} aria-hidden="true">{tinted}</pre>
        <textarea
          ref={taRef}
          className="ide-textarea"
          value={value}
          onChange={e => onChange(e.target.value)}
          onScroll={onScroll}
          onKeyDown={onKey}
          spellCheck={false}
          wrap="off"
        />
      </div>
      {/* Sublime-style minimap — scaled-down code overview with viewport thumb */}
      {lineCount > 20 && (
        <div
          className="ide-minimap"
          ref={minimapRef}
          onClick={onMinimapClick}
        >
          <pre className="ide-minimap-code">{tinted}</pre>
          <div className="ide-minimap-thumb" ref={minimapThumbRef} />
        </div>
      )}
    </div>
  );
}

/* Local copy of the chat tintCode — small enough to inline; keeps
   views.jsx independent of ui.jsx loading order. Returns a string with
   color spans interleaved (rendered as React children). */
function ideTintCode(src, lang) {
  if (!src) return '';
  const parts = [];
  let i = 0;
  // Comment syntax varies; support //, #, --, /* */.
  // String quotes: ", ', `.
  // Numbers: integer + float + hex.
  // Keyword set is broad-stroke (covers JS, Python, Rust, Go).
  const re = /(\/\/[^\n]*|#[^\n]*|--[^\n]*|\/\*[\s\S]*?\*\/)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|\b(0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b|\b(function|const|let|var|if|else|for|while|return|class|extends|new|this|import|export|from|async|await|try|catch|throw|true|false|null|undefined|def|lambda|pass|None|True|False|elif|fn|pub|use|impl|struct|enum|match|trait|mut|self|in|not|and|or|is|with|as|raise|yield|break|continue|switch|case|default|do|finally|interface|type|namespace|public|private|protected|static|void|int|float|bool|string|char|long|short|double)\b/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    if (m.index > i) parts.push(src.slice(i, m.index));
    if (m[1]) parts.push(<span key={'c'+m.index} className="cb-comment">{m[1]}</span>);
    else if (m[2]) parts.push(<span key={'s'+m.index} className="cb-string">{m[2]}</span>);
    else if (m[3]) parts.push(<span key={'n'+m.index} className="cb-num">{m[3]}</span>);
    else if (m[4]) parts.push(<span key={'k'+m.index} className="cb-kw">{m[4]}</span>);
    i = m.index + m[0].length;
  }
  if (i < src.length) parts.push(src.slice(i));
  return parts;
}

function EmbeddedTerminal({ project, cli, sessionId, visible }) {
  const containerRef = React.useRef(null);
  const termRef      = React.useRef(null);
  const wsRef        = React.useRef(null);
  const fitRef       = React.useRef(null);

  /* Copy/paste + URL capture. The CLIs (claude/codex/gemini login) print OAuth
     URLs the user must open in a browser — before this, nothing in the PTY was
     copyable, which blocked authenticating AI subscriptions entirely. */
  const [lastUrl, setLastUrl] = React.useState('');
  const [flash, setFlash]     = React.useState('');
  const flashTimer = React.useRef(null);
  const doFlash = (msg) => {
    setFlash(msg);
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(''), 2200);
  };
  const copyText = async (text) => {
    try { await navigator.clipboard.writeText(text); doFlash('✓ copied'); }
    catch (_e) { doFlash('copy blocked — check browser permission'); }
  };
  const copySelectionOrUrl = () => {
    const sel = termRef.current && termRef.current.getSelection();
    if (sel && sel.trim()) return copyText(sel.trim());
    if (lastUrl) return copyText(lastUrl);
    doFlash('select text first');
  };
  const pasteClipboard = async () => {
    try {
      const t = await navigator.clipboard.readText();
      if (t && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(t); doFlash('✓ pasted');
      } else if (!t) doFlash('clipboard is empty');
      else doFlash('terminal not connected');
    } catch (_e) { doFlash('paste blocked — use Ctrl+V or grant clipboard access'); }
  };

  React.useEffect(() => {
    if (!containerRef.current || !project?.path) return;
    const TermClass = window.Terminal;
    const FitClass  = window.FitAddon?.FitAddon ?? window.FitAddon;
    if (!TermClass || !FitClass) {
      containerRef.current.textContent = 'xterm.js not loaded';
      return;
    }

    const term = new TermClass({
      theme: {
        background: '#0c0c14', foreground: '#d4d8e8',
        cursor: '#7c6bff', cursorAccent: '#0c0c14',
        selectionBackground: 'rgba(124,107,255,0.25)',
        black: '#0c0c14', brightBlack: '#3a3555',
      },
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      fontSize: 13, lineHeight: 1.4,
      cursorBlink: true, scrollback: 5000,
    });
    const fit = new FitClass();
    term.loadAddon(fit);
    term.open(containerRef.current);
    termRef.current = term;
    fitRef.current  = fit;

    let cancelled = false;
    let urlTail = '';   // rolling output tail for login-URL capture

    // Registered once — always routes input to the current ws.
    term.onData(data => {
      if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(data);
    });

    // Ctrl/Cmd+C copies when text is selected (and does NOT send SIGINT over a
    // selection); Ctrl+Shift+C always copies. Ctrl+V is deliberately left to the
    // browser's native paste path — xterm's hidden textarea routes it through
    // onData, and that works in every browser (clipboard.readText does not).
    term.attachCustomKeyEventHandler((ev) => {
      if (ev.type !== 'keydown') return true;
      const key = (ev.key || '').toLowerCase();
      if (key === 'c' && (ev.ctrlKey || ev.metaKey) &&
          (ev.shiftKey || term.hasSelection())) {
        const sel = term.getSelection();
        if (sel && sel.trim()) {
          navigator.clipboard.writeText(sel.trim()).catch(() => {});
          term.clearSelection();
          return false;
        }
      }
      return true;
    });

    // Terminal convention: releasing a mouse selection copies it. This is the
    // one-gesture path for grabbing an OAuth URL off the screen.
    const onMouseUp = () => {
      const sel = term.getSelection();
      if (sel && sel.trim()) copyText(sel.trim());
    };
    containerRef.current.addEventListener('mouseup', onMouseUp);

    const connect = async () => {
      if (cancelled) return;
      // Skip if already open or mid-handshake.
      const rs = wsRef.current?.readyState;
      if (rs === WebSocket.OPEN || rs === WebSocket.CONNECTING) return;
      term.writeln('\x1b[2m[connecting…]\x1b[0m');

      // Fetch nonce — /terminal/nonce is same-origin-only so cross-origin
      // pages can't obtain it and therefore can't open a PTY.
      let ptyNonce = '';
      try {
        const _nr = await fetch((window._API_BASE || '') + '/terminal/nonce');
        if (_nr.ok) { const _nd = await _nr.json(); ptyNonce = _nd.nonce || ''; }
      } catch (_) {}

      if (cancelled) return;

      // Target the BACKEND base (window._API_BASE = the gateway when the UI is
      // served cross-origin from the asset canister), NOT the page origin — an
      // ICP asset canister can't serve WebSockets, so the PTY socket must go to
      // the gateway. Falls back to same-origin when _API_BASE is empty (local).
      let _wsBase;
      try { _wsBase = new URL((window._API_BASE || '/').replace(/\/?$/, '/'), window.location.href); }
      catch (_) { _wsBase = new URL('/', window.location.href); }
      const _wsProto = _wsBase.protocol === 'https:' ? 'wss:' : 'ws:';
      const _wsHost  = _wsBase.host;
      const _wsPath  = _wsBase.pathname.replace(/\/$/, '');   // strip trailing slash
      const _wsParams = new URLSearchParams({
        cli, cwd: project.path,
        cols: String(term.cols), rows: String(term.rows),
        ...(sessionId ? { session_id: sessionId } : {}),
      }).toString() + (ptyNonce ? `&nonce=${encodeURIComponent(ptyNonce)}` : '');

      const ws = new WebSocket(`${_wsProto}//${_wsHost}${_wsPath}/terminal/pty?${_wsParams}`);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      // Always send init frame immediately on open — even with no BYOK keys.
      // The server waits up to 2 s for this frame before spawning the PTY;
      // sending it right away eliminates the 2-second blank-screen delay.
      ws.onopen = async () => {
        const oc = window.CafresoHQClient;
        let ak = '', ok = '', gk = '';
        if (oc?.getAgentKey) {
          ak = await oc.getAgentKey('anthropic').catch(() => '');
          ok = await oc.getAgentKey('openai').catch(() => '');
          gk = await oc.getAgentKey('google').catch(() => '');   // Gemini CLI
        }
        ws.send(JSON.stringify({
          type: 'init',
          ...(ak ? { anthropic_key: ak } : {}),
          ...(ok ? { openai_key:    ok } : {}),
          ...(gk ? { gemini_key:    gk } : {}),
        }));
      };

      ws.onmessage = e => {
        const data = e.data instanceof ArrayBuffer
          ? new TextDecoder().decode(e.data) : e.data;
        term.write(data);
        // Capture the most recent URL from the raw PTY stream (login flows
        // print OAuth URLs the user must open in a browser). Keep a rolling
        // tail so URLs split across frames still match; strip ANSI first —
        // OSC-8 hyperlinks keep their target, colors/cursor codes drop.
        urlTail = (urlTail + data).slice(-6000);
        const clean = urlTail
          .replace(/\x1b\]8;;([^\x07\x1b]*)(?:\x07|\x1b\\)/g, ' $1 ')
          .replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, ' ')
          .replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '')
          .replace(/[\r\x07]/g, '\n');
        const m = clean.match(/https?:\/\/[^\s'"<>\x00-\x1f)\]]+/g);
        if (m && m.length) {
          const u = m[m.length - 1].replace(/[.,;:!?]+$/, '');
          if (u.length > 12) setLastUrl(u);
        }
      };

      ws.onerror = () => {
        term.writeln('\r\n\x1b[31m[connection error — is serve.py running?]\x1b[0m');
      };

      ws.onclose = () => {
        if (cancelled) return;
        if (document.visibilityState === 'visible') {
          // Page is in the foreground — reconnect after a short delay.
          term.writeln('\r\n\x1b[2m[reconnecting…]\x1b[0m');
          setTimeout(() => { if (!cancelled) connect(); }, 2000);
        }
        // If hidden, visibilitychange below will reconnect when the user returns.
      };
    };

    const sendResize = () => {
      try { fit.fit(); } catch (_) {}
      if (wsRef.current?.readyState === WebSocket.OPEN)
        wsRef.current.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    };
    const ro = new ResizeObserver(sendResize);
    if (containerRef.current) ro.observe(containerRef.current);
    window.addEventListener('resize', sendResize);

    // Reconnect when the user returns from another app / tab.
    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && !cancelled) {
        const rs = wsRef.current?.readyState;
        if (rs !== WebSocket.OPEN && rs !== WebSocket.CONNECTING) {
          term.writeln('\r\n\x1b[2m[reconnecting…]\x1b[0m');
          connect();
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    requestAnimationFrame(() => {
      if (!cancelled) {
        try { fit.fit(); } catch (_) {}
        connect();
      }
    });

    const containerEl = containerRef.current;
    return () => {
      cancelled = true;
      ro.disconnect();
      window.removeEventListener('resize', sendResize);
      document.removeEventListener('visibilitychange', handleVisibility);
      if (containerEl) containerEl.removeEventListener('mouseup', onMouseUp);
      clearTimeout(flashTimer.current);
      try { if (wsRef.current) wsRef.current.close(); } catch (_) {}
      try { term.dispose(); } catch (_) {}
      termRef.current = wsRef.current = fitRef.current = null;
    };
  }, [project?.id, project?.path, cli]);

  React.useEffect(() => {
    if (visible && fitRef.current) {
      requestAnimationFrame(() => { try { fitRef.current.fit(); } catch (_) {} });
    }
  }, [visible]);

  const tbBtn = {
    fontSize: 9, fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em',
    color: 'rgba(212,216,232,0.75)', background: 'rgba(124,107,255,0.10)',
    border: '1px solid rgba(124,107,255,0.30)', borderRadius: 4,
    padding: '3px 8px', cursor: 'pointer', flexShrink: 0,
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', minHeight: 0 }}>
      {/* Copy/paste toolbar + login-URL chip. Touch users have no Ctrl+C/V and
          no mouse selection — these buttons are their only clipboard path. */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '3px 8px',
        flexShrink: 0, background: '#0a0a12', minHeight: 26,
        borderBottom: '1px solid rgba(124,107,255,0.12)',
      }}>
        <button style={tbBtn} title="Copy selection (or the last URL)" onClick={copySelectionOrUrl}>⧉ COPY</button>
        <button style={tbBtn} title="Paste clipboard into the terminal" onClick={pasteClipboard}>⇩ PASTE</button>
        {flash && <span style={{ fontSize: 10, color: '#8fd18f', fontFamily: "'JetBrains Mono', monospace" }}>{flash}</span>}
        {lastUrl && (
          <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
            <span title={lastUrl} style={{
              fontSize: 10, color: 'rgba(212,216,232,0.55)', fontFamily: "'JetBrains Mono', monospace",
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 240, direction: 'rtl',
            }}>🔗 {lastUrl}</span>
            <button style={tbBtn} title="Copy this URL" onClick={() => copyText(lastUrl)}>COPY</button>
            <button style={tbBtn} title="Open in a new browser tab"
              onClick={() => window.open(lastUrl, '_blank', 'noopener,noreferrer')}>OPEN ↗</button>
            <button style={{ ...tbBtn, padding: '3px 5px' }} title="Dismiss" onClick={() => setLastUrl('')}>✕</button>
          </span>
        )}
      </div>
      <div ref={containerRef} style={{
        flex: 1, minHeight: 0, width: '100%',
        overflow: 'hidden', padding: '4px 0 0 6px', boxSizing: 'border-box',
      }} />
    </div>
  );
}

function TerminalSession({ project, cli, sessionId, visible, ptySupported, spawnSupported }) {
  /* Persistent state keyed on project.id + sessionId. Survives project switches
     and full reloads — so users can resume a CLI conversation without losing
     context. msgs are the visible chat history; the backend gets sessionId in
     the request so the orchestrator can attach long-running context too. */
  const pid = project?.id || project?.path || '';
  const sKey = (suffix) => pid && sessionId ? `cafresohq_terminal:${suffix}:${pid}:${sessionId}` : null;

  /* Every CLI is now dual-mode: a conversational Chat view and the raw PTY.
     - claude / codex / gemini stream Chat via their CLI's non-interactive
       mode (`--print` / `exec --json` / `--prompt`), scoped to the project dir
       and using the CLI's own login — so chat is file-aware and matches PTY.
     - hermes streams Chat through its always-on OpenAI-compatible gateway
       (/hermes/v1/chat/completions); no key needed (server-side auth).
     Default to the PTY so a new tab opens as a real terminal (a full CLI per
     tab); Chat is one click away via the Chat/PTY toggle. */
  const [termModeRaw, setTermMode] = useStoredV(sKey('mode'), 'spawn');  // 'chat' | 'spawn'
  const termMode = termModeRaw;
  const [msgs,      setMsgs]      = useStoredV(sKey('msgs'),  []);
  const [input,     setInput]     = useSV('');
  const [busy,      setBusy]      = useSV(false);
  const [err,       setErr]       = useSV(null);
  const [model,     setModel]     = useStoredV(sKey('model'), '');
  // 'subscription' = CLI's own OAuth login, 'apikey' = BYOK API key. Claude and
  // Gemini default to their subscription/OAuth login; codex defaults to apikey.
  const [authMethod, setAuthMethod] = useStoredV(sKey('auth'), (cli === 'claude' || cli === 'gemini') ? 'subscription' : 'apikey');
  const [keyPanel,  setKeyPanel]  = useSV(false);
  const [keyInput,  setKeyInput]  = useSV('');
  const [keyStored, setKeyStored] = useSV({});
  const [spawnMsg,  setSpawnMsg]  = useSV('');
  const bottomRef = React.useRef(null);
  const inputRef  = React.useRef(null);
  const ctrlRef   = React.useRef(null);

  React.useEffect(() => {
    const oc = window.CafresoHQClient;
    if (!oc || !oc.hasAgentKey) return;
    setKeyStored({
      anthropic: oc.hasAgentKey('anthropic'),
      openai:    oc.hasAgentKey('openai'),
      google:    oc.hasAgentKey('google'),
    });
  }, [cli]);

  // Which stored BYOK key this CLI uses (hermes needs none — server-side auth).
  const provider    = cli === 'claude' ? 'anthropic' : cli === 'gemini' ? 'google' : cli === 'hermes' ? null : 'openai';
  const keyIsStored = !!(provider && keyStored[provider]);

  React.useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [msgs]);

  const stop = () => {
    if (ctrlRef.current) { ctrlRef.current.abort(); ctrlRef.current = null; }
    setBusy(false);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy || !project) return;
    const userMsg = { role: 'user', content: text };
    const history = [...msgs, userMsg];
    setMsgs(history);
    setInput('');
    setBusy(true);
    setErr(null);

    const asstIdx = history.length;
    const asstMsg = { role: 'assistant', segs: [] };
    setMsgs([...history, asstMsg]);

    const ctrl = new AbortController();
    ctrlRef.current = ctrl;

    // Append a streamed chunk to the in-flight assistant message, coalescing
    // consecutive chunks of the same kind ('text'|'tool'|'error') into one seg.
    const appendChunk = (content, type) => {
      setMsgs(prev => {
        const next = [...prev];
        const last = next[asstIdx];
        if (!last || last.role !== 'assistant') return prev;
        const segs = [...(last.segs || [])];
        if (segs.length > 0 && segs[segs.length - 1].type === type) {
          segs[segs.length - 1] = { ...segs[segs.length - 1], text: segs[segs.length - 1].text + content };
        } else {
          segs.push({ text: content, type });
        }
        next[asstIdx] = { ...last, segs };
        return next;
      });
    };

    const wireMessages = history.map(m => ({
      role: m.role,
      content: m.segs ? m.segs.map(s => s.text).join('') : (m.content || ''),
    }));

    try {
      if (cli === 'hermes') {
        // Hermes Chat streams through its always-on OpenAI-compatible gateway
        // (/hermes/v1/chat/completions). Model is server-configured; passing the
        // 'hermes:' prefix forces the provider without overriding the model.
        await window.CafresoHQClient.stream({
          model: model.trim() ? 'hermes:' + model.trim() : 'hermes:',
          messages: wireMessages,
          signal: ctrl.signal,
          onToken: (t) => appendChunk(t, 'text'),
        });
      } else {
        // claude / codex / gemini → the CLI's non-interactive mode, scoped to
        // the project dir, using the CLI's own login (subscription) or BYOK.
        await window.CafresoHQClient.terminalStream({
          messages: wireMessages,
          cli,
          cwd: project.path,
          model: model.trim() || undefined,
          projectName: project.name,
          projectId: project.id,
          sessionId,
          authMethod,
          signal: ctrl.signal,
          onData: appendChunk,
        });
      }
    } catch (e) {
      if (e.name !== 'AbortError') setErr(e.message || String(e));
    }
    ctrlRef.current = null;
    setBusy(false);
    if (inputRef.current) inputRef.current.focus();
  };

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const clear = () => { setMsgs([]); setErr(null); };

  const launchTerminal = async () => {
    const oc = window.CafresoHQClient;
    if (!oc || !oc.spawnTerminal) return;
    setSpawnMsg(''); setErr(null);
    try {
      await oc.spawnTerminal({ cli, cwd: project.path });
      setSpawnMsg(`${cli === 'hermes' ? 'Hermes' : cli === 'claude' ? 'Claude Code' : cli === 'gemini' ? 'Gemini' : 'Codex'} launched in a new terminal window.`);
    } catch (e) {
      setErr(e.message || String(e));
    }
  };

  const saveKey = async () => {
    const oc = window.CafresoHQClient;
    if (!oc || !oc.setAgentKey) return;
    await oc.setAgentKey(provider, keyInput.trim());
    setKeyStored(prev => ({ ...prev, [provider]: !!keyInput.trim() }));
    setKeyInput('');
    setKeyPanel(false);
  };

  const clearKey = async () => {
    const oc = window.CafresoHQClient;
    if (!oc || !oc.setAgentKey) return;
    await oc.setAgentKey(provider, '');
    setKeyStored(prev => ({ ...prev, [provider]: false }));
    setKeyPanel(false);
  };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: 'var(--paper)', fontFamily: "'JetBrains Mono', monospace",
      fontSize: 13, color: 'var(--ink)',
    }}>
      {/* Mode + controls — single unified bar */}
      <div style={{
        display: 'flex', alignItems: 'center', flexShrink: 0,
        borderBottom: '1px solid var(--rule)', background: 'var(--paper-2)',
        minHeight: 44,
      }}>
        {([['chat', '💬', 'Chat'], ...(spawnSupported ? [['spawn', '⚡', 'PTY']] : [])]
        ).map(([mode, ico, label]) => (
          <button key={mode} onClick={() => { setTermMode(mode); setErr(null); setSpawnMsg(''); }}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '0 16px', height: 44, display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 12, fontWeight: 700,
              fontFamily: "'JetBrains Mono', monospace",
              color: termMode === mode ? '#7c6bff' : 'var(--ink-3)',
              borderBottom: termMode === mode ? '2px solid #7c6bff' : '2px solid transparent',
              whiteSpace: 'nowrap', flexShrink: 0,
            }}
          ><span>{ico}</span><span>{label}</span></button>
        ))}
        {spawnSupported === false && (
          <span style={{ fontSize: 9, color: 'var(--ink-3)', paddingLeft: 10 }}>chat only</span>
        )}
        <span style={{ flex: 1 }} />
        {termMode === 'chat' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingRight: 10 }}>
            {cli !== 'hermes' && (
            <select value={model} onChange={e => setModel(e.target.value)} disabled={busy}
              style={{
                background: 'var(--paper)', color: 'var(--ink)', border: '1px solid var(--rule)',
                borderRadius: 4, fontSize: 11, padding: '3px 6px',
                fontFamily: 'inherit', cursor: 'pointer',
              }}
            >
              {cli === 'claude' ? (
                <>
                  <option value="">model (default)</option>
                  <option value="claude-sonnet-4-6">Sonnet 4.6</option>
                  <option value="claude-opus-4-7">Opus 4.7</option>
                  <option value="claude-haiku-4-5-20251001">Haiku 4.5</option>
                  <option value="claude-sonnet-4-5-20250514">Sonnet 4.5</option>
                </>
              ) : cli === 'gemini' ? (
                <>
                  <option value="">model (default)</option>
                  <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
                  <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                  <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
                  <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
                </>
              ) : (
                <>
                  <option value="">model (default)</option>
                  <option value="o3">o3</option>
                  <option value="o4-mini">o4-mini</option>
                  <option value="gpt-4.1">GPT-4.1</option>
                  <option value="gpt-4.1-mini">GPT-4.1 Mini</option>
                </>
              )}
            </select>
            )}
            {cli === 'hermes' && (
              <span style={{ fontSize: 9, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
                model in Settings → System
              </span>
            )}
            {(cli === 'claude' || cli === 'gemini') && (
              <select value={authMethod} onChange={e => { setAuthMethod(e.target.value); setKeyPanel(false); }}
                title={authMethod === 'subscription'
                  ? (cli === 'gemini' ? 'Using your Google login via the gemini CLI' : 'Using Claude Pro/Max subscription via CLI login')
                  : `Using your own ${cli === 'gemini' ? 'Google' : 'Anthropic'} API key`}
                style={{
                  background: authMethod === 'subscription' ? 'rgba(124,107,255,0.10)' : 'var(--paper)',
                  color: authMethod === 'subscription' ? '#7c6bff' : 'var(--ink)',
                  border: `1px solid ${authMethod === 'subscription' ? '#7c6bff' : 'var(--rule)'}`,
                  borderRadius: 4, fontSize: 10, padding: '3px 6px',
                  fontFamily: 'inherit', cursor: 'pointer',
                }}
              >
                <option value="subscription">{cli === 'gemini' ? '⚡ Login' : '⚡ Subscription'}</option>
                <option value="apikey">🔑 API Key</option>
              </select>
            )}
            {provider && (cli !== 'claude' && cli !== 'gemini' ? true : authMethod === 'apikey') && (
              <button onClick={() => { setKeyPanel(p => !p); setKeyInput(''); }}
                title={keyIsStored ? `${provider} key stored (AES-256-GCM)` : `Set ${provider} API key`}
                style={{
                  background: keyIsStored ? 'rgba(111,168,111,0.15)' : 'transparent',
                  color: keyIsStored ? 'var(--live)' : 'var(--ink-3)',
                  border: `1px solid ${keyIsStored ? 'var(--live)' : 'var(--rule)'}`,
                  borderRadius: 4, fontSize: 12, padding: '3px 8px', cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >{keyIsStored ? '🔒' : '🔓'}</button>
            )}
            {busy ? (
              <button onClick={stop} style={{
                background: 'rgba(201,112,112,0.12)', color: 'var(--error)', border: '1px solid var(--error)',
                borderRadius: 4, fontSize: 10, padding: '3px 10px', cursor: 'pointer', fontFamily: 'inherit',
              }}>■ STOP</button>
            ) : (
              <button onClick={clear} style={{
                background: 'transparent', color: 'var(--ink-3)', border: '1px solid var(--rule)',
                borderRadius: 4, fontSize: 10, padding: '3px 8px', cursor: 'pointer', fontFamily: 'inherit',
              }}>CLEAR</button>
            )}
          </div>
        ) : (
          <span style={{ fontSize: 10, color: 'var(--ink-3)', paddingRight: 12, fontFamily: "'JetBrains Mono', monospace", opacity: 0.7 }}>
            {project.name}
          </span>
        )}
      </div>

      {keyPanel && authMethod === 'apikey' && (
        <div style={{
          background: 'var(--paper-2)', borderBottom: '1px solid var(--rule)',
          padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
        }}>
          <span style={{ fontSize: 10, color: '#7c6bff', whiteSpace: 'nowrap' }}>
            {provider === 'anthropic' ? 'ANTHROPIC_API_KEY' : provider === 'google' ? 'GEMINI_API_KEY' : 'OPENAI_API_KEY'}
          </span>
          <input
            type="password"
            value={keyInput}
            onChange={e => setKeyInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && saveKey()}
            placeholder={keyIsStored ? '••••••• (replace)' : 'sk-…'}
            autoFocus
            style={{
              flex: 1, background: 'var(--paper)', color: 'var(--ink)',
              border: '1px solid var(--rule-2)', borderRadius: 4, fontSize: 11,
              padding: '4px 8px', fontFamily: 'inherit',
            }}
          />
          <button onClick={saveKey} disabled={!keyInput.trim()} style={{
            background: 'var(--carpet)', color: 'var(--ink)', border: '1px solid var(--carpet-dk)',
            borderRadius: 4, fontSize: 10, padding: '3px 10px', cursor: 'pointer',
            fontFamily: 'inherit',
          }}>SAVE</button>
          {keyIsStored && (
            <button onClick={clearKey} style={{
              background: 'transparent', color: 'var(--error)', border: '1px solid var(--error)',
              borderRadius: 4, fontSize: 10, padding: '3px 8px', cursor: 'pointer',
              fontFamily: 'inherit',
            }}>CLEAR KEY</button>
          )}
          <span style={{ fontSize: 9, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
            AES-256-GCM · device key
          </span>
        </div>
      )}

      {termMode === 'chat' ? (
        <>
          {/* Claude Desktop-style chat messages */}
          <div style={{
            flex: 1, overflowY: 'auto', padding: '20px 20px 8px',
            display: 'flex', flexDirection: 'column', gap: 18,
            background: 'var(--paper)',
          }}>
            {msgs.length === 0 && (
              <div style={{
                flex: 1, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                gap: 10, paddingTop: 40,
              }}>
                <div style={{ fontSize: 30, opacity: 0.35 }}>
                  {cli === 'claude' ? '✦' : cli === 'hermes' ? '☼' : cli === 'gemini' ? '✧' : '◈'}
                </div>
                <div style={{ textAlign: 'center', fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.6 }}>
                  <strong>{cli === 'claude' ? 'Claude Code' : cli === 'hermes' ? 'Hermes' : cli === 'gemini' ? 'Gemini' : 'OpenAI Codex'}</strong>
                  <br/>
                  <span style={{ fontSize: 10, color: 'var(--ink-3)' }}>
                    {cli === 'hermes'
                      ? 'via gateway · server-side auth'
                      : `${project.name} · ${(cli === 'claude' || cli === 'gemini') && authMethod === 'subscription' ? '⚡ login' : 'BYOK supported'}`}
                  </span>
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              m.role === 'user' ? (
                /* User — right-aligned bubble */
                <div key={i} style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <div style={{
                    background: '#7c6bff', color: '#fff',
                    padding: '10px 14px', borderRadius: '16px 16px 4px 16px',
                    maxWidth: '80%', fontSize: 13, lineHeight: 1.5,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    boxShadow: '0 1px 6px rgba(124,107,255,0.22)',
                    fontFamily: 'Inter, system-ui, sans-serif',
                  }}>
                    {m.content}
                  </div>
                </div>
              ) : (
                /* Assistant — left-aligned with avatar */
                <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <div style={{
                    width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                    background: 'var(--accent-lav)', color: 'var(--ink)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, marginTop: 1, border: '1px solid var(--rule)',
                  }}>
                    {cli === 'claude' ? '✦' : cli === 'hermes' ? '☼' : cli === 'gemini' ? '✧' : '◈'}
                  </div>
                  <div style={{ flex: 1, fontSize: 13, lineHeight: 1.65, color: 'var(--ink)', minWidth: 0, fontFamily: 'Inter, system-ui, sans-serif' }}>
                    {(m.segs || []).map((seg, si) => {
                      if (seg.type === 'tool') return (
                        <div key={si} style={{
                          background: 'var(--paper-2)', border: '1px solid var(--rule)',
                          borderRadius: 6, padding: '5px 10px', margin: '4px 0',
                          fontSize: 11, color: 'var(--ink-2)',
                          fontFamily: "'JetBrains Mono', monospace",
                        }}>⚙ {seg.text}</div>
                      );
                      if (seg.type === 'error') return (
                        <div key={si} style={{
                          background: 'rgba(201,112,112,0.08)', border: '1px solid var(--error)',
                          borderRadius: 6, padding: '6px 10px', margin: '4px 0',
                          color: 'var(--error)', fontSize: 12,
                        }}>⚠ {seg.text}</div>
                      );
                      return (
                        <span key={si} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {seg.text}
                        </span>
                      );
                    })}
                    {busy && i === msgs.length - 1 && (
                      <span style={{
                        display: 'inline-block', width: 7, height: 13,
                        background: '#7c6bff', borderRadius: 1, marginLeft: 2,
                        verticalAlign: 'text-bottom',
                        animation: 'term-blink 1s step-end infinite',
                      }}/>
                    )}
                  </div>
                </div>
              )
            ))}
            {err && (
              <div style={{
                background: 'rgba(201,112,112,0.08)', border: '1px solid var(--error)',
                borderRadius: 8, padding: '10px 14px', color: 'var(--error)', fontSize: 12,
              }}>⚠ {err}</div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Claude Desktop-style input */}
          <div style={{
            padding: '12px 16px 14px', borderTop: '1px solid var(--rule)',
            background: 'var(--paper-2)', flexShrink: 0,
          }}>
            <div style={{
              display: 'flex', gap: 8, alignItems: 'flex-end',
              background: 'var(--paper)', border: '1px solid var(--rule)',
              borderRadius: 12, padding: '8px 8px 8px 14px',
              boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
            }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKey}
                disabled={busy}
                placeholder={`Message ${cli === 'claude' ? 'Claude Code' : cli === 'hermes' ? 'Hermes' : cli === 'gemini' ? 'Gemini' : 'Codex'}…`}
                rows={2}
                style={{
                  flex: 1, background: 'transparent', color: 'var(--ink)',
                  border: 'none', resize: 'none', fontFamily: 'Inter, system-ui, sans-serif',
                  fontSize: 13, padding: 0, outline: 'none',
                  lineHeight: 1.5, caretColor: '#7c6bff',
                }}
              />
              <button
                onClick={busy ? stop : send}
                disabled={!busy && (!input.trim() || !project)}
                style={{
                  width: 32, height: 32, borderRadius: 8, border: 'none',
                  background: busy ? 'rgba(201,112,112,0.15)' : (input.trim() ? '#7c6bff' : 'var(--paper-2)'),
                  color: busy ? 'var(--error)' : (input.trim() ? '#fff' : 'var(--ink-3)'),
                  fontSize: 15, cursor: (busy || input.trim()) ? 'pointer' : 'default',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, transition: 'background 0.15s, color 0.15s',
                  boxShadow: input.trim() && !busy ? '0 2px 6px rgba(124,107,255,0.3)' : 'none',
                }}
              >{busy ? '■' : '↑'}</button>
            </div>
            <div style={{ fontSize: 9, color: 'var(--ink-3)', marginTop: 5, paddingLeft: 4 }}>
              Enter to send · Shift+Enter for newline
            </div>
          </div>
        </>
      ) : (
        /* Embedded PTY terminal panel */
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {ptySupported ? (
            <EmbeddedTerminal project={project} cli={cli} sessionId={sessionId} visible={visible} />
          ) : (
            /* Fallback: launch button */
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32, gap: 16, background: 'var(--paper)' }}>
              <div style={{ textAlign: 'center', fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.7 }}>
                Opens a new <strong style={{ color: 'var(--ink)' }}>Windows Terminal</strong> window running<br/>
                <code style={{ color: '#7c6bff' }}>{cli}</code> in <code style={{ color: '#7c6bff', opacity: 0.75 }}>{project.path}</code>
              </div>
              {spawnMsg && (
                <div style={{ background: 'rgba(111,168,111,0.12)', border: '1px solid var(--live)', borderRadius: 6, padding: '8px 16px', color: 'var(--live)', fontSize: 11 }}>
                  ✓ {spawnMsg}
                </div>
              )}
              {err && (
                <div style={{ background: 'rgba(201,112,112,0.08)', border: '1px solid var(--error)', borderRadius: 6, padding: '8px 16px', color: 'var(--error)', fontSize: 11 }}>⚠ {err}</div>
              )}
              <button onClick={launchTerminal} style={{
                background: '#7c6bff', color: '#fff', border: 'none',
                borderRadius: 8, fontFamily: 'inherit', fontSize: 12, fontWeight: 700,
                padding: '10px 28px', cursor: 'pointer',
                boxShadow: '0 2px 8px rgba(124,107,255,0.3)',
              }}>▶ LAUNCH {cli.toUpperCase()} IN TERMINAL</button>
            </div>
          )}
          {/* Pop-out footer — dark to blend with terminal */}
          {ptySupported && (
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', background: '#0a0a10', padding: '3px 12px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0 }}>
              <button onClick={launchTerminal} title="Open in separate terminal window" style={{
                background: 'transparent', color: '#3a3555', border: 'none',
                fontSize: 9, fontFamily: 'inherit', cursor: 'pointer', letterSpacing: 0.5,
              }}>⬡ pop out</button>
              {spawnMsg && <span style={{ fontSize: 9, color: '#4ade80', marginLeft: 8 }}>✓ launched</span>}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

let _sessionCounter = 0;
/* _uuid() requires a secure context (HTTPS / localhost).
   On plain HTTP over LAN IP it's undefined, so we polyfill. */
const _uuid = () =>
  typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = (crypto.getRandomValues(new Uint8Array(1))[0] & 15) >> (c === 'x' ? 0 : 2);
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
      });
function ProjectTerminal({ project, visible }) {
  /* Sessions persist per-project so closing the project (or reloading) doesn't
     wipe the user's terminal tabs. Keyed on project.id; if the project has no
     id (shouldn't happen but be defensive) we fall back to in-memory only. */
  const pid = project?.id || project?.path || null;
  const sessKey = pid ? `cafresohq_terminal:sessions:${pid}` : null;
  const activeKey = pid ? `cafresohq_terminal:active:${pid}` : null;

  const [sessions, setSessions] = useStoredV(sessKey, () => {
    const id = `s${++_sessionCounter}`;
    return [{ id, cli: 'hermes', sessionId: _uuid() }];
  });
  const [activeId, setActiveId] = useStoredV(activeKey, () => sessions[0]?.id);

  /* Defensive — if persisted activeId points to a session that no longer exists,
     snap to the first available session. */
  React.useEffect(() => {
    if (sessions.length === 0) {
      const id = `s${++_sessionCounter}`;
      const fresh = [{ id, cli: 'hermes', sessionId: _uuid() }];
      setSessions(fresh);
      setActiveId(id);
      return;
    }
    if (!sessions.find(s => s.id === activeId)) {
      setActiveId(sessions[0].id);
    }
  }, [sessions, activeId]);

  const [spawnSupported, setSpawnSupported] = React.useState(true);
  const [ptySupported, setPtySupported]     = React.useState(false);
  const [addMenuOpen, setAddMenuOpen]       = React.useState(false);
  const [addMenuPos,  setAddMenuPos]        = React.useState({ top: 0, left: 0 });
  const addBtnRef = React.useRef(null);
  const addMenuRef = React.useRef(null);

  React.useEffect(() => {
    fetch((window._API_BASE || '') + '/terminal/status')
      .then(r => r.json())
      .then(j => {
        setSpawnSupported(!!j.spawn_supported);
        setPtySupported(!!j.pty_supported);
      })
      .catch(() => { setSpawnSupported(false); setPtySupported(false); });
  }, []);

  React.useEffect(() => {
    if (!addMenuOpen) return;
    const close = (e) => {
      // The menu is portaled to <body>, so it's NOT inside addBtnRef — check both.
      if (addBtnRef.current && addBtnRef.current.contains(e.target)) return;
      if (addMenuRef.current && addMenuRef.current.contains(e.target)) return;
      setAddMenuOpen(false);
    };
    const closeNow = () => setAddMenuOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('touchstart', close);
    window.addEventListener('scroll', closeNow, true);
    window.addEventListener('resize', closeNow);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('touchstart', close);
      window.removeEventListener('scroll', closeNow, true);
      window.removeEventListener('resize', closeNow);
    };
  }, [addMenuOpen]);

  const addSession = (cli) => {
    const id = `s${++_sessionCounter}`;
    setSessions(prev => [...prev, { id, cli, sessionId: _uuid() }]);
    setActiveId(id);
    setAddMenuOpen(false);
  };

  const closeSession = (id) => {
    if (sessions.length <= 1) return;
    const closing = sessions.find(s => s.id === id);
    const next = sessions.filter(s => s.id !== id);
    // Side effects MUST stay OUTSIDE the setState updater — calling setActiveId()
    // from inside the setSessions(prev => …) updater is the React anti-pattern
    // that blanked the whole page when a tab was closed.
    setSessions(next);
    if (activeId === id && next.length) setActiveId(next[next.length - 1].id);
    /* Clear this session's persistent state so localStorage doesn't bloat over
       time. msgs can be hundreds of KB after a long conversation. */
    if (closing && pid) {
      try {
        ['mode', 'msgs', 'model', 'auth'].forEach(suffix => {
          localStorage.removeItem(`cafresohq_terminal:${suffix}:${pid}:${closing.sessionId}`);
        });
      } catch (_e) {}
    }
  };

  const cliName = (cli) => cli === 'hermes' ? 'Hermes' : cli === 'claude' ? 'Claude' : cli === 'gemini' ? 'Gemini' : 'Codex';
  const cliIcon = (cli) => cli === 'hermes' ? '☼' : cli === 'claude' ? '✦' : cli === 'gemini' ? '✧' : '◈';

  const getLabel = (session) => {
    const name = cliName(session.cli);
    const same = sessions.filter(s => s.cli === session.cli);
    if (same.length <= 1) return name;
    return `${name} #${same.indexOf(session) + 1}`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Session tab bar */}
      <div style={{
        display: 'flex', alignItems: 'center',
        borderBottom: '1px solid var(--rule)', flexShrink: 0,
        background: 'var(--paper-2)', padding: '0 6px',
        overflowX: 'auto', WebkitOverflowScrolling: 'touch',
        scrollbarWidth: 'none', gap: 2, minHeight: 44,
      }}>
        {sessions.map(s => {
          const active = s.id === activeId;
          const icon = cliIcon(s.cli);
          return (
            <div key={s.id}
              onClick={() => setActiveId(s.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '0 4px 0 12px', cursor: 'pointer', whiteSpace: 'nowrap',
                minHeight: 44, fontSize: 12, fontWeight: 600,
                fontFamily: "'JetBrains Mono', monospace",
                color: active ? '#7c6bff' : 'var(--ink-3)',
                borderBottom: active ? '2px solid #7c6bff' : '2px solid transparent',
                background: active ? 'rgba(124,107,255,0.06)' : 'transparent',
                borderRadius: '6px 6px 0 0',
                transition: 'background 0.15s, color 0.15s',
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 13 }}>{icon}</span>
              <span>{getLabel(s)}</span>
              {sessions.length > 1 && (
                <button
                  onClick={e => { e.stopPropagation(); closeSession(s.id); }}
                  title="End session"
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'inherit', opacity: active ? 0.7 : 0.35,
                    fontSize: 16, lineHeight: 1, padding: '0 8px', margin: 0,
                    minWidth: 32, minHeight: 32, display: 'flex', alignItems: 'center',
                    justifyContent: 'center', borderRadius: 4,
                    transition: 'opacity 0.15s, background 0.1s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = 1; e.currentTarget.style.background = 'rgba(124,107,255,0.1)'; }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = active ? 0.7 : 0.35; e.currentTarget.style.background = 'none'; }}
                >×</button>
              )}
            </div>
          );
        })}
        {/* Add session */}
        <div ref={addBtnRef} style={{ position: 'relative', flexShrink: 0, marginLeft: 4 }}>
          <button
            onClick={() => {
              if (!addMenuOpen && addBtnRef.current) {
                const r = addBtnRef.current.getBoundingClientRect();
                // Open DOWNWARD from the button. The portal escapes the tab bar's
                // overflow clip, so the menu is no longer hidden under the terminal
                // — and downward avoids running off the top of the screen on mobile
                // (the tab bar sits at the very top there). Clamp left so the 170px
                // menu never runs off a narrow/iPad edge.
                const MENU_W = 170;
                const left = Math.max(8, Math.min(r.left, window.innerWidth - MENU_W - 8));
                const top = r.bottom + 6;
                setAddMenuPos({ top, left });
              }
              setAddMenuOpen(p => !p);
            }}
            title="New CLI session"
            style={{
              background: addMenuOpen ? 'rgba(124,107,255,0.12)' : 'transparent',
              border: '1px solid var(--rule)',
              borderRadius: 6, color: addMenuOpen ? '#7c6bff' : 'var(--ink-3)',
              fontSize: 20, lineHeight: 1,
              width: 36, height: 36, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'background 0.15s, color 0.15s', flexShrink: 0,
            }}
          >+</button>
          {addMenuOpen && ReactDOM.createPortal(
            <div ref={addMenuRef} style={{
              position: 'fixed', top: addMenuPos.top, left: addMenuPos.left, zIndex: 99999,
              background: '#12121e', border: '1px solid rgba(124,107,255,0.25)',
              borderRadius: 10, boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
              padding: 6, minWidth: 170,
            }}>
              {[['hermes', '☼', 'Hermes', true], ['claude', '✦', 'Claude Code', false], ['codex', '◈', 'Codex CLI', false], ['gemini', '✧', 'Gemini CLI', false]].map(([c, ico, label, isDefault]) => (
                <div key={c}
                  onClick={() => addSession(c)}
                  style={{
                    padding: '10px 14px', cursor: 'pointer', fontSize: 12,
                    borderRadius: 6, display: 'flex', alignItems: 'center', gap: 10,
                    fontFamily: "'JetBrains Mono', monospace",
                    color: '#d4d8e8', transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(124,107,255,0.18)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <span style={{ fontSize: 15, color: '#7c6bff' }}>{ico}</span>
                  <span>{label}</span>
                  {isDefault && (
                    <span style={{
                      marginLeft: 'auto', fontSize: 9, fontWeight: 700, letterSpacing: '0.04em',
                      color: '#7c6bff', background: 'rgba(124,107,255,0.16)',
                      borderRadius: 4, padding: '2px 6px',
                    }}>DEFAULT</span>
                  )}
                </div>
              ))}
            </div>,
            document.body
          )}
        </div>
      </div>

      {/* Session panels — all stay mounted, only active is visible */}
      {sessions.map(s => (
        <div key={s.id} style={{
          flex: 1, overflow: 'hidden',
          display: s.id === activeId ? 'flex' : 'none',
          flexDirection: 'column',
        }}>
          <TerminalSession
            project={project}
            cli={s.cli}
            sessionId={s.sessionId}
            visible={visible && s.id === activeId}
            ptySupported={ptySupported}
            spawnSupported={spawnSupported}
          />
        </div>
      ))}
    </div>
  );
}

/* ── Universal artifact preview ──────────────────────────────────────────────
   Renders a file by type so users can SEE what an agent built — HTML pages/decks,
   PDFs, images, markdown, CSV — right beside the editor. Text types render from the
   already-read content (works anywhere); binary types (image/PDF) stream from
   serve.py's /fs/file endpoint. The headline of the "agentic workspace" — view the
   doc/site as the agent writes it. */
function previewKind(path) {
  const ext = (String(path || '').split('.').pop() || '').toLowerCase();
  if (ext === 'html' || ext === 'htm') return 'html';
  if (ext === 'md' || ext === 'markdown') return 'markdown';
  if (ext === 'svg') return 'svg';
  if (ext === 'pdf') return 'pdf';
  if (['png','jpg','jpeg','gif','webp','bmp','ico','avif'].indexOf(ext) >= 0) return 'image';
  if (ext === 'csv' || ext === 'tsv') return 'csv';
  return 'code';
}

/* Does this HTML reference sibling files (relative <link>/<script>/<img>)?
   If so it's a multi-file site and must be served from its directory so those
   refs resolve — a `srcDoc` blob has no base URL and would 404 every asset. */
function htmlNeedsSiteServe(content) {
  if (!content) return false;
  const re = /(?:src|srcset|href)\s*=\s*["']([^"']*)["']/gi;
  let m;
  while ((m = re.exec(content))) {
    const u = (m[1] || '').trim();
    if (!u) continue;
    if (/^(?:https?:|\/\/|data:|blob:|#|mailto:|tel:|javascript:)/i.test(u)) continue;
    return true; // a relative / root-relative ref → needs real serving
  }
  return false;
}

/* Split an OS path (either separator) into { dir, base }. */
function splitOsPath(p) {
  p = String(p || '');
  const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'));
  return i >= 0 ? { dir: p.slice(0, i), base: p.slice(i + 1) } : { dir: '', base: p };
}

/* UTF-8-safe, URL-safe, unpadded base64 — matches serve.py's
   base64.urlsafe_b64decode(b64 + padding) in /fs/site. */
function b64urlUtf8(s) {
  const bytes = new TextEncoder().encode(String(s || ''));
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function CsvPreview({ text, sep }) {
  const rows = String(text || '').replace(/\s+$/, '').split(/\r?\n/).slice(0, 500).map(l => l.split(sep));
  if (!rows.length || (rows.length === 1 && !rows[0][0])) return <div style={{padding:16,opacity:0.6}}>Empty file.</div>;
  const head = rows[0], body = rows.slice(1);
  const cell = { border:'1px solid var(--rule,#d8cfb8)', padding:'3px 8px', fontSize:12, maxWidth:280, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' };
  return (
    <div style={{overflow:'auto', flex:1, padding:8, background:'var(--paper,#fff)'}}>
      <table style={{borderCollapse:'collapse', fontFamily:'var(--mono,ui-monospace,monospace)'}}>
        <thead><tr>{head.map((h,i) => <th key={i} style={{...cell, fontWeight:700, background:'var(--paper-2,#f0e9d8)', position:'sticky', top:0}}>{h}</th>)}</tr></thead>
        <tbody>{body.map((r,i) => <tr key={i}>{r.map((c,j) => <td key={j} style={cell}>{c}</td>)}</tr>)}</tbody>
      </table>
      {rows.length >= 500 && <div style={{padding:8,opacity:0.6,fontSize:11}}>Showing first 500 rows.</div>}
    </div>
  );
}

function FilePreview({ file, nonce }) {
  const [imgErr, setImgErr] = useSV(false);
  const kind = previewKind(file.path);
  const apiBase = (typeof window !== 'undefined' && window._API_BASE) || '';
  // nonce (bumped when an agent rewrites the open file) cache-busts the streamed
  // URLs so image/pdf/site previews actually reload — the "preview chases the agent" effect.
  const bust = nonce ? ('&_n=' + nonce) : '';
  const fileUrl = apiBase + '/fs/file?path=' + encodeURIComponent(file.path) + bust;
  const frame = { flex:1, width:'100%', height:'100%', minHeight:0, border:0, background:'#fff' };
  const pad = { flex:1, overflow:'auto', display:'flex', alignItems:'center', justifyContent:'center', padding:16, background:'#fff' };
  if (kind === 'html') {
    // Multi-file site → serve from its directory so relative assets resolve;
    // self-contained page → render inline (works without the /fs/site endpoint).
    // A truncated FILE_READ also routes to site-serve: detection can't see refs
    // past the 8000-char cap, and the iframe loads the FULL file from disk, so a
    // long page renders complete instead of cut off.
    const truncated = /\(truncated to \d+ chars\)\s*$/.test(file.content || '');
    if (file.path && (htmlNeedsSiteServe(file.content) || truncated)) {
      const { dir, base } = splitOsPath(file.path);
      const siteUrl = apiBase + '/fs/site/' + b64urlUtf8(dir) + '/' + encodeURIComponent(base) + (nonce ? ('?_n=' + nonce) : '');
      return <iframe title="Site preview" style={frame} sandbox="allow-scripts allow-popups allow-forms allow-modals" src={siteUrl} />;
    }
    return <iframe title="HTML preview" style={frame} sandbox="allow-scripts allow-popups allow-forms allow-modals" srcDoc={file.content} />;
  }
  if (kind === 'markdown')
    return <div className="vault-preview" style={{flex:1, overflow:'auto', padding:'16px 22px', background:'var(--paper,#fff)'}} dangerouslySetInnerHTML={{ __html: renderMarkdown(file.content || '') }} />;
  if (kind === 'svg')
    return <div style={pad} dangerouslySetInnerHTML={{ __html: file.content }} />;
  if (kind === 'csv')
    return <CsvPreview text={file.content} sep={String(file.path).toLowerCase().endsWith('.tsv') ? '\t' : ','} />;
  if (kind === 'image')
    return (
      <div style={pad}>
        {imgErr
          ? <div style={{textAlign:'center',opacity:0.6,fontSize:12}}>Couldn't load image.<br/>Needs the updated container (ships <code>/fs/file</code>) — rebuild the image.</div>
          : <img src={fileUrl} alt={file.path} onError={() => setImgErr(true)} style={{maxWidth:'100%', maxHeight:'100%', objectFit:'contain'}} />}
      </div>
    );
  if (kind === 'pdf')
    return <iframe title="PDF preview" style={frame} src={fileUrl} />;
  return <pre style={{flex:1, overflow:'auto', margin:0, padding:16, fontFamily:'var(--mono,ui-monospace,monospace)', fontSize:12, whiteSpace:'pre-wrap', wordBreak:'break-word', background:'var(--paper,#fff)'}}>{file.content}</pre>;
}

/* ═══════════════════ Cohabit Workspace — the unified Agentic-OS surface ═══════
   One screen where you and your agents are two operators on the SAME container
   filesystem: a file tree, a center editor⇄live-preview deck, an integrated
   terminal drawer, and an agent rail co-inhabit a single layout. The agent's
   writes (via the cafresohq:agentTool event bus) light up the tree, refresh the
   preview, and stream into a re-runnable activity ledger — conflict-safely, so a
   live agent write never clobbers your unsaved edits. A top-bar toggle flips to
   the classic Projects view (kept intact). */
function WorkspaceView({ projects, setProjects, agents = [], tasks, onAddTask, onSwitchView }) {
  const LS = (k, d) => { try { const v = localStorage.getItem('ws:' + k); return v == null ? d : JSON.parse(v); } catch (_e) { return d; } };
  const LSset = (k, v) => { try { localStorage.setItem('ws:' + k, JSON.stringify(v)); } catch (_e) {} };
  const baseName = (p) => String(p || '').split(/[\/\\]/).pop();
  const shortPath = (p) => { const s = String(p || '').split(/[\/\\]/).filter(Boolean); return s.slice(-2).join('/'); };
  const joinPath = (dir, name) => { const d = String(dir || ''); const sep = (d.includes('\\') && !d.includes('/')) ? '\\' : '/'; return d.replace(/[\/\\]+$/, '') + sep + name; };
  const isUnder = (p, base) => p === base || p.startsWith(base + '/') || p.startsWith(base + '\\');
  const toast = (k, m) => { if (window.cafresohqToast && window.cafresohqToast[k]) window.cafresohqToast[k](m); };
  const C = window.CafresoHQClient;

  const [mode, setMode] = useSV(() => LS('mode', 'workspace'));
  const flipMode = (m) => { setMode(m); LSset('mode', m); };
  const [selectedId, setSelectedId] = useSV(() => LS('selid', (projects[0] && projects[0].id) || null));
  const project = projects.find(p => p.id === selectedId) || projects[0] || null;
  React.useEffect(() => { if (project) LSset('selid', project.id); }, [project && project.id]);

  const [openFile, setOpenFile] = useSV(null);   // {path, content, mtime, hash, dirty, binary}
  const [previewMode, setPreviewMode] = useSV(false);
  const [busy, setBusy] = useSV(false);
  const [err, setErr] = useSV(null);
  const [conflict, setConflict] = useSV(false);
  const [treeNonce, setTreeNonce] = useSV(0);
  const [previewNonce, setPreviewNonce] = useSV(0);
  const [followAgent, setFollowAgent] = useSV(() => LS('follow', false));
  const [agentStatus, setAgentStatus] = useSV('idle');   // idle | working
  const [ledger, setLedger] = useSV([]);
  const [pulse, setPulse] = useSV(() => new Set());      // paths the agent just touched
  const [termOpen, setTermOpen] = useSV(() => LS('term', true));
  const [fileDrag, setFileDrag] = useSV(false);
  const uploadRef = React.useRef(null);
  const uploadDirRef = React.useRef(null);

  const openFileRef = React.useRef(null); React.useEffect(() => { openFileRef.current = openFile; }, [openFile]);
  const followRef = React.useRef(false); React.useEffect(() => { followRef.current = followAgent; }, [followAgent]);
  const pulseTimers = React.useRef({});
  const idleTimer = React.useRef(null);

  /* ── open a file into the deck (full content + conflict metadata) ── */
  const openPath = async (path) => {
    setErr(null); setConflict(false);
    const kind = previewKind(path);
    const binary = kind === 'image' || kind === 'pdf';
    if (binary) { setOpenFile({ path, content: '', binary: true }); setPreviewMode(true); return; }
    setBusy(true);
    try {
      const r = await C.fsReadText(path);
      setOpenFile({ path, content: r.content, mtime: r.mtime, hash: r.hash, dirty: false, binary: false });
      setPreviewMode(false);
    } catch (e) { setErr(e.message || String(e)); }
    setBusy(false);
  };
  const onEdit = (val) => setOpenFile(f => f ? { ...f, content: val, dirty: true } : f);

  /* ── conflict-safe save: re-stat before writing, never silently clobber ── */
  const save = async (force) => {
    const f = openFileRef.current; if (!f) return;
    setBusy(true); setErr(null);
    try {
      if (!force && f.hash) {
        try { const st = await C.fsStat(f.path); if (st && st.hash && st.hash !== f.hash) { setConflict(true); setBusy(false); return; } } catch (_e) {}
      }
      await C.toolExec('FILE_WRITE', f.path, { body: f.content });
      let nh = f.hash, nm = f.mtime;
      try { const st2 = await C.fsStat(f.path); if (st2 && st2.ok) { nh = st2.hash; nm = st2.mtime; } } catch (_e) {}
      setOpenFile(o => (o && o.path === f.path) ? { ...o, hash: nh, mtime: nm, dirty: false } : o);
      setConflict(false); setTreeNonce(n => n + 1);
      toast('success', 'Saved ' + baseName(f.path));
    } catch (e) { setErr(e.message || String(e)); toast('error', 'Save failed: ' + (e.message || e)); }
    setBusy(false);
  };
  const reloadOpen = async (path) => {
    try { const r = await C.fsReadText(path); setOpenFile(o => (o && o.path === path) ? { ...o, content: r.content, mtime: r.mtime, hash: r.hash, dirty: false } : o); setPreviewNonce(n => n + 1); } catch (_e) {}
  };

  /* ── live presence / ledger / status pip helpers ── */
  const markPulse = (path) => {
    if (!path) return;
    setPulse(prev => { const n = new Set(prev); n.add(path); return n; });
    clearTimeout(pulseTimers.current[path]);
    pulseTimers.current[path] = setTimeout(() => setPulse(prev => { const n = new Set(prev); n.delete(path); return n; }), 2600);
  };
  const addLedger = (verb, name, arg) => setLedger(prev => [{ id: Math.random().toString(36).slice(2, 9), verb, name, path: arg, label: shortPath(arg), kind: verb }, ...prev].slice(0, 40));
  const bumpIdle = () => { clearTimeout(idleTimer.current); idleTimer.current = setTimeout(() => setAgentStatus('idle'), 3500); };

  /* ── the agent event bus: the heart of co-habitation ── */
  React.useEffect(() => {
    const onAgentTool = (e) => {
      const d = e.detail || {}; const name = d.name, phase = d.phase, arg = String(d.arg || '').trim();
      setAgentStatus('working'); bumpIdle();
      if (phase === 'start') { markPulse(arg); return; }
      if (phase !== 'done') return;
      const isWrite = name === 'FILE_WRITE';
      const isVault = name === 'VAULT_NEW' || name === 'VAULT_APPEND';
      const isExport = name && name.indexOf('EXPORT') === 0;
      const isBash = name === 'BASH';
      if (isWrite || isVault || isExport) {
        markPulse(arg); setTreeNonce(n => n + 1);
        addLedger(isExport ? 'exported' : 'wrote', name, arg);
        const cur = openFileRef.current;
        if (isWrite && cur && cur.path === arg) {
          if (cur.dirty) setConflict(true);   // surface banner — do not clobber
          else reloadOpen(arg);               // clean buffer → silent reload + preview chase
        } else if (isWrite && followRef.current && previewKind(arg) !== 'code') {
          openPath(arg);                       // follow the agent into its artifact
        }
      } else if (isBash) {
        addLedger('ran', name, arg);
      }
    };
    window.addEventListener('cafresohq:agentTool', onAgentTool);
    return () => window.removeEventListener('cafresohq:agentTool', onAgentTool);
  }, []);

  /* ── file-manager actions (same backbone as the classic Projects view) ── */
  const fsOK = () => (C && C.fsMkdir) ? C : null;
  const newFolder = async () => {
    if (!project || !fsOK()) { toast('error', 'File ops need the updated container — rebuild the image.'); return; }
    const name = (window.prompt('New folder name:') || '').trim(); if (!name || /[\/\\]/.test(name)) return;
    try { await C.fsMkdir(joinPath(project.path, name)); setTreeNonce(n => n + 1); toast('success', `Created "${name}"`); } catch (e) { toast('error', e.message || String(e)); }
  };
  const renameEntry = async (entry) => {
    if (!fsOK()) return;
    const next = (window.prompt('Rename to:', entry.name) || '').trim(); if (!next || next === entry.name || /[\/\\]/.test(next)) return;
    const to = entry.path.slice(0, Math.max(0, entry.path.length - entry.name.length)) + next;
    try { await C.fsRename(entry.path, to); setTreeNonce(n => n + 1); if (openFileRef.current && isUnder(openFileRef.current.path, entry.path)) setOpenFile(o => ({ ...o, path: to + o.path.slice(entry.path.length) })); toast('success', `Renamed to "${next}"`); } catch (e) { toast('error', e.message || String(e)); }
  };
  const deleteEntry = async (entry) => {
    if (!fsOK()) return;
    if (!window.confirm(`Delete ${entry.isDir ? 'folder' : 'file'} "${entry.name}"?` + (entry.isDir ? '\n\nThis removes everything inside it.' : '') + '\n\nThis cannot be undone.')) return;
    try { await C.fsDelete(entry.path); setTreeNonce(n => n + 1); if (openFileRef.current && isUnder(openFileRef.current.path, entry.path)) setOpenFile(null); toast('success', `Deleted "${entry.name}"`); } catch (e) { toast('error', e.message || String(e)); }
  };
  const doUpload = async (fileList, dir) => {
    setFileDrag(false);
    if (!project) return; const files = Array.from(fileList || []).filter(Boolean); if (!files.length) return;
    if (!C || !C.fsUpload) { toast('error', 'Upload needs the updated container.'); return; }
    try { const res = await C.fsUpload(dir || project.path, files); setTreeNonce(n => n + 1); toast('success', `Shared ${res.count || files.length} file${(res.count || files.length) === 1 ? '' : 's'}`); const f0 = res.uploaded && res.uploaded[0]; if (f0 && f0.path) openPath(f0.path); } catch (e) { toast('error', 'Upload failed: ' + (e.message || e)); }
  };
  const uploadTo = (entry, files) => { if (files && files.length) { doUpload(files, entry.path); return; } uploadDirRef.current = entry.path; if (uploadRef.current) uploadRef.current.click(); };
  const triggerUpload = () => { uploadDirRef.current = null; if (uploadRef.current) uploadRef.current.click(); };
  const openChat = () => { if (window.cafresohqSetChatOpen) window.cafresohqSetChatOpen(true); window.dispatchEvent(new CustomEvent('cafresohq:set-active-thread', { detail: 'project:' + project.id })); };
  const onLedgerClick = (l) => { if (l.kind === 'ran') { setTermOpen(true); LSset('term', true); return; } if (l.path) openPath(l.path); };

  const statusLabel = agentStatus === 'working' ? 'agent working…' : 'agent idle';

  return (
    <div className="ws-root">
      <div className="ws-topbar">
        <div className="ws-seg ws-modeseg">
          <button className={mode === 'workspace' ? 'on' : ''} onClick={() => flipMode('workspace')} title="Unified Workspace — files, editor, terminal & agents on one screen">Workspace</button>
          <button className={mode === 'classic' ? 'on' : ''} onClick={() => flipMode('classic')} title="The original Projects view">Classic</button>
        </div>
        {mode === 'workspace' && project && (
          <>
            <select className="ws-projsel" value={project.id} onChange={e => setSelectedId(e.target.value)}>
              {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <span className="ws-env" title={project.path}><span className="ico">⬡</span> {project.source === 'github' ? 'repo' : 'local'} · {shortPath(project.path) || project.path}</span>
            <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 12 }}>
              <label className="ws-follow" title="Auto-open whatever file the agent is writing"><input type="checkbox" checked={followAgent} onChange={e => { setFollowAgent(e.target.checked); LSset('follow', e.target.checked); }} /> Follow agent</label>
              <span className={'ws-pip ' + agentStatus}><span className="dot" />{statusLabel}</span>
            </div>
          </>
        )}
      </div>

      {mode === 'classic' ? (
        <div className="ws-classic"><ProjectsView projects={projects} setProjects={setProjects} tasks={tasks} agents={agents} onAddTask={onAddTask} onSwitchView={onSwitchView} /></div>
      ) : !project ? (
        <div className="ws-noproj">No project yet — switch to <button className="px-btn" onClick={() => flipMode('classic')}>Classic</button> to create one.</div>
      ) : (
        <div className="ws-body">
          <div className="ws-pane ws-files">
            <div className="ws-pane-hd"><span><i className="ti" /></span>Files<div className="ws-hd-acts"><button onClick={newFolder} title="New folder">＋</button><button onClick={triggerUpload} title="Upload files">⬆</button></div></div>
            <div className={'ws-tree' + (fileDrag ? ' drag' : '')}
              onDragOver={e => { e.preventDefault(); setFileDrag(true); }}
              onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget)) setFileDrag(false); }}
              onDrop={e => { e.preventDefault(); if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) doUpload(e.dataTransfer.files, null); else setFileDrag(false); }}>
              <LocalTree path={project.path} refreshNonce={treeNonce} onSelectFile={openPath} onRename={renameEntry} onDelete={deleteEntry} onUploadTo={uploadTo} pulsePaths={pulse} />
            </div>
            <input ref={uploadRef} type="file" multiple style={{ display: 'none' }} onChange={e => { doUpload(e.target.files, uploadDirRef.current); e.target.value = ''; uploadDirRef.current = null; }} />
          </div>

          <div className="ws-center">
            <div className="ws-editorwrap">
              {openFile ? (
                <>
                  <div className="ws-tabs">
                    <span className="ws-tab on">{ideFileIcon ? ideFileIcon(openFile.path) : '📄'} <span className="nm">{baseName(openFile.path)}</span>{openFile.dirty ? <span className="dirty">•</span> : ''}</span>
                    {!openFile.binary && <div className="ws-seg ws-cpseg"><button className={!previewMode ? 'on' : ''} onClick={() => setPreviewMode(false)}>Code</button><button className={previewMode ? 'on' : ''} onClick={() => setPreviewMode(true)}>Preview</button></div>}
                    {!openFile.binary && openFile.dirty && <button className="ws-save" onClick={() => save(false)} disabled={busy}>Save</button>}
                  </div>
                  {conflict && (
                    <div className="ws-conflict"><i className="ti" />The agent changed this file on disk while you had edits.
                      <button onClick={() => { setConflict(false); openPath(openFile.path); }}>Reload</button>
                      <button onClick={() => save(true)}>Keep mine</button>
                    </div>
                  )}
                  {err && <div className="ws-err">{err}</div>}
                  <div className="ws-stage">
                    {previewMode ? <FilePreview file={openFile} nonce={previewNonce} /> : <IDEEditor value={openFile.content} onChange={onEdit} path={openFile.path} />}
                  </div>
                </>
              ) : (
                <div className="ws-stage-empty">Open a file from the tree — or watch your agents build one.<br /><span className="dim">Code · Preview · live as it's written</span></div>
              )}
            </div>
            <div className={'ws-term' + (termOpen ? '' : ' min')}>
              <div className="ws-term-hd" onClick={() => { const v = !termOpen; setTermOpen(v); LSset('term', v); }}><span className="tl">⌁ Terminal · shared shell</span><span className="ch">{termOpen ? '▾' : '▸'}</span></div>
              {termOpen && <div className="ws-term-body"><ProjectTerminal project={project} visible={termOpen} /></div>}
            </div>
          </div>

          <div className="ws-pane ws-agent">
            <div className="ws-pane-hd">Agents · co-operators<div className="ws-hd-acts"><button className="ws-talk" disabled={(project.agentIds || []).length === 0} onClick={openChat} title="Open the multi-agent room for this project">TALK ↗</button></div></div>
            <div className="ws-ledger">
              {ledger.length === 0 && <div className="ws-led-empty">Your agents share this filesystem &amp; shell. Their writes, runs, and exports appear here as they work — click any line to jump to it.</div>}
              {ledger.map(l => (
                <div key={l.id} className={'ws-led k-' + l.kind} onClick={() => onLedgerClick(l)} title={l.path}>
                  <span className="v">{l.kind}</span><span className="lb">{l.label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ProjectsView({ projects, setProjects, onSave, agents = [], onSwitchView }) {
  const [selected, setSelected] = useSV(null);
  const [openFile, setOpenFile] = useSV(null);
  const [previewMode, setPreviewMode] = useSV(false);
  const [busy, setBusy] = useSV(false);
  const [err, setErr] = useSV(null);
  const [rightTab, setRightTab] = useSV('files');
  const [openedTerminals, setOpenedTerminals] = React.useState([]);
  /* File-drop / upload into the selected project's working dir. treeNonce
     forces LocalTree to re-list after an upload; fileDragHover drives the
     drop-zone highlight. */
  const [treeNonce, setTreeNonce] = useSV(0);
  const [fileDragHover, setFileDragHover] = useSV(false);
  const [uploadTargetDir, setUploadTargetDir] = useSV(null);  // subfolder target for 📤 picker
  const uploadInputRef = React.useRef(null);

  React.useEffect(() => {
    if (rightTab === 'terminal' && selected) {
      setOpenedTerminals(prev =>
        prev.includes(selected) ? prev : [...prev, selected]
      );
    }
  }, [rightTab, selected]);

  /* Toggle assignment of an agent to the current project. The dynamic
     project tab in ChatPanel keys off `agentIds`, so flipping this is
     all that's needed to make the per-project room appear / disappear. */
  const toggleAgent = (agentId) => {
    if (!selected) return;
    setProjects(prev => prev.map(p => {
      if (p.id !== selected) return p;
      const cur = Array.isArray(p.agentIds) ? p.agentIds : [];
      const next = cur.includes(agentId) ? cur.filter(id => id !== agentId) : [...cur, agentId];
      return { ...p, agentIds: next };
    }));
  };
  /* Drag-drop state for the project list — visual hint when a folder is being
     dragged over the panel. The actual OS-path can't be inferred from the
     drop event (browser security), so we only use the drop as a trigger to
     open the "new project" prompt with the folder name pre-filled. */
  const [dragHover, setDragHover] = useSV(false);

  const project = projects.find(p => p.id === selected);

  const [showAdd, setShowAdd] = useSV(false);
  const [addPrefill, setAddPrefill] = useSV('');

  const _isMobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;
  const [mobileStep, setMobileStep] = useSV(_isMobile ? 'list' : null);
  const [mobileDetailTab, setMobileDetailTab] = useSV('files');

  /* Inline rename state — keyed by project id so multiple cards don't
     collide. Stays null when no project is being renamed. */
  const [renamingId, setRenamingId] = useSV(null);
  const [renameDraft, setRenameDraft] = useSV('');

  const beginRename = (p) => {
    setRenamingId(p.id);
    setRenameDraft(p.name || '');
  };
  const commitRename = () => {
    const draft = String(renameDraft || '').trim();
    if (!renamingId) return;
    if (!draft) { setRenamingId(null); return; }
    setProjects(prev => prev.map(p => p.id === renamingId ? { ...p, name: draft } : p));
    if (window.cafresohqToast) window.cafresohqToast.success(`Project renamed to "${draft}"`);
    setRenamingId(null);
  };
  const cancelRename = () => { setRenamingId(null); setRenameDraft(''); };

  /* Delete a project. Confirms because this also wipes the per-project
     chat thread (those messages are scoped via thread:'project:<id>')
     and orphans any tasks that referenced it. We don't cascade-delete
     tasks — those stay in the boss's task list and can be reassigned. */
  const deleteProject = (p) => {
    if (!p) return;
    const assignees = (p.agentIds || []).length;
    const msg = `Delete project "${p.name}"?` +
      (assignees > 0 ? `\n\n${assignees} agent${assignees === 1 ? '' : 's'} ${assignees === 1 ? 'is' : 'are'} currently assigned. Their assignments will be cleared.` : '') +
      `\n\nThis cannot be undone.`;
    if (!window.confirm(msg)) return;
    setProjects(prev => (prev || []).filter(x => x.id !== p.id));
    if (selected === p.id) { setSelected(null); setOpenFile(null); }
    if (window.cafresohqToast) window.cafresohqToast.info(`Deleted project "${p.name}"`);
  };

  /* Add a new project — opens the AddProjectModal. */
  const addProject = (suggestedName) => {
    setAddPrefill(suggestedName || '');
    setShowAdd(true);
  };

  /* Final commit step shared by Local-folder and GitHub-clone tabs. */
  const commitProject = ({ name, path, source }) => {
    const id = 'p_' + Math.random().toString(36).slice(2, 8);
    setProjects && setProjects(prev => [...(prev || []), { id, name, path, source }]);
    setSelected(id);
    setShowAdd(false);
    if (window.cafresohqToast) window.cafresohqToast.success(`Added project "${name}"`);
  };

  const onDropFolder = (e) => {
    e.preventDefault();
    setDragHover(false);
    if (!setProjects) return;
    /* Extract a suggested folder name from the first dropped item. */
    const items = e.dataTransfer && e.dataTransfer.items;
    let suggestedName = '';
    if (items && items.length) {
      try {
        const entry = items[0].webkitGetAsEntry && items[0].webkitGetAsEntry();
        if (entry && entry.isDirectory && entry.name) suggestedName = entry.name;
      } catch (_) {}
    }
    if (!suggestedName && e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
      suggestedName = e.dataTransfer.files[0].name;
    }
    addProject(suggestedName);
  };

  const readFile = async (path) => {
    setBusy(true); setErr(null);
    const kind = previewKind(path);
    const isBinary = kind === 'image' || kind === 'pdf';
    setPreviewMode(isBinary);   // binary auto-previews; text lands in the editor
    if (isBinary) {
      // Not text — don't FILE_READ; the preview pane streams it from /fs/file.
      setOpenFile({ path, content: '', dirty: false, binary: true });
      setBusy(false);
      return;
    }
    try {
      const text = await window.CafresoHQClient.toolExec('FILE_READ', path);
      setOpenFile({
        path,
        content: typeof text === 'string' ? text : String(text || ''),
        dirty: false,
      });
    } catch (e) { setErr(e.message || String(e)); }
    setBusy(false);
  };

  const saveFile = async () => {
    if (!openFile) return;
    setBusy(true); setErr(null);
    try {
      await window.CafresoHQClient.toolExec('FILE_WRITE', openFile.path, { body: openFile.content });
      setOpenFile({ ...openFile, dirty: false });
    } catch (e) { setErr(e.message || String(e)); }
    setBusy(false);
  };

  /* Join a dir + name using whichever separator the dir already uses (so
     Windows paths stay Windows paths). */
  const joinPath = (dir, name) => {
    const d = String(dir || '');
    const sep = (d.includes('\\') && !d.includes('/')) ? '\\' : '/';
    return d.replace(/[\/\\]+$/, '') + sep + name;
  };
  /* Is `p` the path `base` itself, or a descendant of it? Separator-bounded so
     /proj/foobar is NOT treated as living under /proj/foo. */
  const isUnder = (p, base) => p === base || p.startsWith(base + '/') || p.startsWith(base + '\\');
  const toast = (kind, msg) => { if (window.cafresohqToast && window.cafresohqToast[kind]) window.cafresohqToast[kind](msg); };

  /* Upload (drop or picker) files into a working dir so assigned agents can
     read them and the preview pane can render them. targetDir defaults to the
     project root; a folder row's 📤 / drop passes a subfolder. After a
     successful upload we refresh the tree and auto-open the first file. */
  const uploadFiles = async (fileList, targetDir) => {
    setFileDragHover(false);  // a folder-row drop stops propagation to the panel zone
    if (!project || !project.path) {
      toast('info', 'Select a project first to share files with it.');
      return;
    }
    const files = Array.from(fileList || []).filter(Boolean);
    if (!files.length) return;
    if (!window.CafresoHQClient || !window.CafresoHQClient.fsUpload) {
      setErr('Upload needs the updated container (ships /fs/upload) — rebuild the image.');
      toast('error', 'Upload unavailable — container needs a rebuild.');
      return;
    }
    const dir = targetDir || project.path;
    setBusy(true); setErr(null);
    try {
      const res = await window.CafresoHQClient.fsUpload(dir, files);
      setTreeNonce(n => n + 1);
      const n = (res && res.count) || files.length;
      const where = dir === project.path ? project.name : ('…/' + dir.split(/[\/\\]/).pop());
      toast('success', `Shared ${n} file${n === 1 ? '' : 's'} with ${where}`);
      const first = res && res.uploaded && res.uploaded[0];
      if (first && first.path) readFile(first.path);
    } catch (e) {
      setErr(e.message || String(e));
      toast('error', 'Upload failed: ' + (e.message || e));
    }
    setBusy(false);
  };

  /* ── File-manager actions over the working tree (new folder / rename /
     delete / upload-into-subfolder). Each refreshes the tree on success. ── */
  const fsClient = () => (window.CafresoHQClient && window.CafresoHQClient.fsMkdir) ? window.CafresoHQClient : null;

  const newFolder = async () => {
    if (!project || !project.path) return;
    if (!fsClient()) { toast('error', 'File ops need the updated container — rebuild the image.'); return; }
    const name = (window.prompt('New folder name:') || '').trim();
    if (!name) return;
    if (/[\/\\]/.test(name)) { toast('error', 'Folder name can\'t contain slashes.'); return; }
    setBusy(true); setErr(null);
    try {
      await fsClient().fsMkdir(joinPath(project.path, name));
      setTreeNonce(n => n + 1);
      toast('success', `Created folder "${name}"`);
    } catch (e) { setErr(e.message || String(e)); toast('error', 'Couldn\'t create folder: ' + (e.message || e)); }
    setBusy(false);
  };

  const renameEntry = async (entry) => {
    if (!fsClient()) { toast('error', 'File ops need the updated container — rebuild the image.'); return; }
    const cur = entry.name;
    const next = (window.prompt('Rename to:', cur) || '').trim();
    if (!next || next === cur) return;
    if (/[\/\\]/.test(next)) { toast('error', 'Name can\'t contain slashes.'); return; }
    const parent = entry.path.slice(0, Math.max(0, entry.path.length - cur.length));
    const to = parent + next;
    setBusy(true); setErr(null);
    try {
      await fsClient().fsRename(entry.path, to);
      setTreeNonce(n => n + 1);
      // Keep the editor's path live — including when a *folder* with the open
      // file inside it was renamed (else the next Save writes a ghost copy at
      // the old path). Rebase the open file's path prefix onto the new name.
      if (openFile && openFile.path && isUnder(openFile.path, entry.path)) {
        setOpenFile({ ...openFile, path: to + openFile.path.slice(entry.path.length) });
      }
      toast('success', `Renamed to "${next}"`);
    } catch (e) { setErr(e.message || String(e)); toast('error', 'Rename failed: ' + (e.message || e)); }
    setBusy(false);
  };

  const deleteEntry = async (entry) => {
    if (!fsClient()) { toast('error', 'File ops need the updated container — rebuild the image.'); return; }
    const what = entry.isDir ? 'folder' : 'file';
    const msg = `Delete ${what} "${entry.name}"?` + (entry.isDir ? '\n\nThis removes everything inside it.' : '') + '\n\nThis cannot be undone.';
    if (!window.confirm(msg)) return;
    setBusy(true); setErr(null);
    try {
      await fsClient().fsDelete(entry.path);
      setTreeNonce(n => n + 1);
      if (openFile && openFile.path && isUnder(openFile.path, entry.path)) setOpenFile(null);
      toast('success', `Deleted "${entry.name}"`);
    } catch (e) { setErr(e.message || String(e)); toast('error', 'Delete failed: ' + (e.message || e)); }
    setBusy(false);
  };

  /* 📤 on a folder (no files) opens the picker targeting that folder; a drop
     passes its files straight through. */
  const uploadTo = (entry, files) => {
    if (files && files.length) { uploadFiles(files, entry.path); return; }
    setUploadTargetDir(entry.path);
    if (uploadInputRef.current) uploadInputRef.current.click();
  };

  /* ── Mobile drill-down navigation ── */
  if (_isMobile) {
    return (
      <div className="view-projects" style={{display:'flex',flexDirection:'column',height:'100%',background:'var(--paper)'}}>
        {/* Mobile back nav bar */}
        {mobileStep !== 'list' && (
          <div className="proj-mobile-back" style={{
            display:'flex',alignItems:'center',gap:10,
            padding:'10px 14px',
            borderBottom:'2px solid var(--accent-sun)',
            background:'var(--paper-2)',
            minHeight:48,
          }}>
            <button
              className="px-btn ghost"
              style={{fontSize:13,padding:'6px 12px',minWidth:44,minHeight:44,color:'var(--accent-sun)',fontWeight:700}}
              onClick={() => {
                if (mobileStep === 'editor') { setOpenFile(null); setMobileStep('detail'); }
                else { setSelected(null); setOpenFile(null); setMobileStep('list'); }
              }}
            >← Back</button>
            <span style={{fontFamily:"'Press Start 2P',monospace",fontSize:10,letterSpacing:'0.08em',color:'var(--ink)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
              {mobileStep === 'editor' ? (openFile ? openFile.path.split(/[\\/]/).pop() : 'Editor') : (project ? project.name : 'Files')}
            </span>
          </div>
        )}

        {/* Step: project list */}
        {mobileStep === 'list' && (
          <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'auto'}}>
            <div className="proj-section-head" style={{display:'flex',alignItems:'center',gap:'var(--sp-3)',padding:'12px'}}>
              <span style={{flex:1,fontFamily:"'Press Start 2P',monospace",fontSize:11}}>🗂 PROJECTS · {projects.length}</span>
              <button
                onClick={() => addProject('')}
                style={{
                  background:'var(--accent-sun)',border:'none',
                  borderRadius:6,fontSize:12,fontWeight:700,
                  padding:'8px 16px',color:'var(--ink)',cursor:'pointer',
                  minHeight:44,
                }}
              >+ ADD</button>
            </div>
            {projects.length === 0 && (
              <div style={{padding:24,textAlign:'center',opacity:0.6}}>
                No projects yet. Tap + ADD to create one.
              </div>
            )}
            {projects.map(p => (
              <div
                key={p.id}
                style={{
                  padding:'16px 16px',
                  margin:'6px 10px',
                  borderRadius:10,
                  cursor:'pointer',
                  display:'flex',alignItems:'center',gap:12,
                  background: selected === p.id ? 'var(--accent-sun-10, rgba(218,165,32,0.12))' : 'var(--paper-2)',
                  border: selected === p.id ? '1.5px solid var(--accent-sun)' : '1.5px solid var(--rule)',
                  transition:'background 0.15s, border-color 0.15s',
                  minHeight:56,
                }}
                onClick={() => { setSelected(p.id); setOpenFile(null); setMobileStep('detail'); }}
              >
                <span style={{fontSize:24,width:36,height:36,display:'flex',alignItems:'center',justifyContent:'center',borderRadius:8,background:'var(--accent-sun-10, rgba(218,165,32,0.1))'}}>📁</span>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontWeight:700,fontSize:15,marginBottom:3,color:'var(--ink)'}}>{p.name}</div>
                  {p.path && <div style={{fontSize:11,opacity:0.5,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{p.path}</div>}
                </div>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); deleteProject(p); }}
                  title={`Delete "${p.name}"`}
                  aria-label={`Delete project ${p.name}`}
                  style={{
                    width:36,height:36,display:'grid',placeItems:'center',
                    background:'transparent',border:'1px solid var(--rule)',
                    borderRadius:8,cursor:'pointer',fontSize:14,
                    color:'var(--brand-coffee-3, #7a6f63)',
                    flexShrink:0,
                    transition:'background .12s, color .12s, border-color .12s',
                  }}
                  onMouseEnter={(e)=>{ e.currentTarget.style.background='rgba(232,92,86,0.1)'; e.currentTarget.style.color='var(--brand-cart-badge, #E85C56)'; e.currentTarget.style.borderColor='var(--brand-cart-badge, #E85C56)'; }}
                  onMouseLeave={(e)=>{ e.currentTarget.style.background='transparent'; e.currentTarget.style.color='var(--brand-coffee-3, #7a6f63)'; e.currentTarget.style.borderColor='var(--rule)'; }}
                >🗑</button>
                <span style={{fontSize:20,color:'var(--accent-sun)',opacity:0.6}}>›</span>
              </div>
            ))}
          </div>
        )}

        {/* Step: project detail — files / terminal / agents */}
        {mobileStep === 'detail' && project && (
          <div style={{flex:1,display:'flex',flexDirection:'column',overflow:'hidden'}}>
            {/* Mobile sub-tabs: Files | Terminal | Agents */}
            <div style={{
              display:'flex', borderBottom:'1px solid var(--rule)',
              background:'var(--paper-2)', flexShrink:0,
              overflowX:'auto', WebkitOverflowScrolling:'touch',
            }}>
              {[['files','📄 Files'],['terminal','⚡ Terminal'],['agents','👥 Agents']].map(([t,label]) => (
                <button key={t}
                  onClick={() => setMobileDetailTab(t)}
                  style={{
                    background:'none', border:'none', cursor:'pointer',
                    padding:'10px 16px', fontSize:11, fontWeight:700,
                    fontFamily:"'JetBrains Mono',monospace",
                    color: mobileDetailTab === t ? '#7c6bff' : 'var(--ink-3)',
                    borderBottom: mobileDetailTab === t ? '2px solid #7c6bff' : '2px solid transparent',
                    whiteSpace:'nowrap', minHeight:44, flexShrink:0,
                  }}
                >{label}</button>
              ))}
            </div>

            {mobileDetailTab === 'files' && (
              <div style={{flex:1,overflow:'auto',display:'flex',flexDirection:'column'}}>
                <div style={{display:'flex',justifyContent:'flex-end',gap:6,padding:'6px 8px',borderBottom:'1px solid var(--rule)'}}>
                  <button
                    className="px-btn ghost"
                    style={{fontSize:11,padding:'4px 10px'}}
                    title="New folder in this project"
                    onClick={newFolder}
                  >＋ Folder</button>
                  <button
                    className="px-btn ghost"
                    style={{fontSize:11,padding:'4px 10px'}}
                    title="Upload files to share with this project's agents"
                    onClick={() => { setUploadTargetDir(null); if (uploadInputRef.current) uploadInputRef.current.click(); }}
                  >⬆ Share file</button>
                </div>
                <input ref={uploadInputRef} type="file" multiple style={{display:'none'}}
                  onChange={(e) => { uploadFiles(e.target.files, uploadTargetDir); e.target.value = ''; setUploadTargetDir(null); }} />
                <div style={{flex:1,overflow:'auto'}}>
                  <LocalTree path={project.path} refreshNonce={treeNonce} onSelectFile={(path) => { readFile(path); setMobileStep('editor'); }} onRename={renameEntry} onDelete={deleteEntry} onUploadTo={uploadTo} />
                </div>
              </div>
            )}

            {/* Terminal — always mounted once the detail view opens, hidden when inactive.
                Using visibility+height:0 instead of display:none so xterm.js
                ResizeObserver can still measure the element when it becomes visible. */}
            <div style={{
              flex: mobileDetailTab === 'terminal' ? 1 : undefined,
              overflow: 'hidden', display: 'flex', flexDirection: 'column',
              visibility: mobileDetailTab === 'terminal' ? 'visible' : 'hidden',
              height: mobileDetailTab === 'terminal' ? undefined : 0,
              pointerEvents: mobileDetailTab === 'terminal' ? 'auto' : 'none',
            }}>
              <ProjectTerminal project={project} visible={mobileStep === 'detail' && mobileDetailTab === 'terminal'} />
            </div>

            {mobileDetailTab === 'agents' && (
              <div style={{flex:1,overflow:'auto',padding:'12px 14px'}}>
                <div style={{display:'flex',alignItems:'center',gap:8,marginBottom:10}}>
                  <span style={{fontFamily:"'Press Start 2P',monospace",fontSize:10,letterSpacing:'0.05em'}}>👥 ASSIGNED · {(project.agentIds || []).length}</span>
                  {(project.agentIds || []).length > 0 && onSwitchView && (
                    <button className="px-btn primary" style={{fontSize:10,padding:'8px 16px',marginLeft:'auto',minHeight:36}} onClick={() => onSwitchView('chat')}>TALK ›</button>
                  )}
                </div>
                <div style={{display:'flex',flexDirection:'column',gap:6}}>
                  {agents.map(a => {
                    const assigned = (project.agentIds || []).includes(a.id);
                    return (
                      <label key={a.id} style={{display:'flex',alignItems:'center',gap:10,padding:'10px 8px',fontSize:14,cursor:'pointer',borderRadius:8,background: assigned ? 'var(--accent-sun-10, rgba(218,165,32,0.1))' : 'transparent',border: assigned ? '1px solid var(--accent-sun)' : '1px solid transparent',transition:'all 0.15s',minHeight:44}}>
                        <input type="checkbox" checked={assigned} onChange={() => toggleAgent(a.id)} style={{width:22,height:22,accentColor:'var(--accent-sun)'}} />
                        <span style={{fontWeight:assigned ? 700 : 400}}>{a.name}</span>
                        {a.role && <span style={{fontSize:11,opacity:0.5}}>· {a.role}</span>}
                      </label>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step: file editor */}
        {mobileStep === 'editor' && openFile && (
          <div style={{flex:1,display:'flex',flexDirection:'column',minHeight:0}}>
            <div className="proj-edit-head ide-edit-head" style={{flexWrap:'wrap',gap:6,padding:'8px 10px'}}>
              <span className="ide-tab" style={{flex:'1 1 auto',minWidth:0}}>
                <span className="ide-tab-icon">{ideFileIcon(openFile.path)}</span>
                <span className="ide-tab-name" style={{overflow:'hidden',textOverflow:'ellipsis'}}>{openFile.path.split(/[\\/]/).pop()}</span>
                {openFile.dirty && <span className="ide-tab-dot">●</span>}
              </span>
              {err && <span className="proj-edit-err">{err}</span>}
              <span style={{display:'inline-flex', gap:2}}>
                <button className={`px-btn ${!previewMode ? 'primary' : 'secondary'}`} style={{fontSize:10, padding:'5px 10px'}} onClick={() => setPreviewMode(false)}>Code</button>
                <button className={`px-btn ${previewMode ? 'primary' : 'secondary'}`} style={{fontSize:10, padding:'5px 10px'}} onClick={() => setPreviewMode(true)}>Preview</button>
              </span>
              <button className="px-btn primary" style={{fontSize:11,padding:'6px 14px'}} onClick={saveFile} disabled={!openFile.dirty || busy}>
                {busy ? 'Saving…' : openFile.dirty ? 'Save' : 'Saved'}
              </button>
            </div>
            {previewMode
              ? <FilePreview file={openFile} />
              : <IDEEditor
                  value={openFile.content}
                  onChange={(v) => setOpenFile({ ...openFile, content: v, dirty: true })}
                  path={openFile.path}
                />}
          </div>
        )}

        {showAdd ? (
          <AddProjectModal
            prefillName={addPrefill}
            onClose={() => setShowAdd(false)}
            onCommit={commitProject}
          />
        ) : null}
      </div>
    );
  }

  return (
    <div className="view-projects">
      <div className="section-title">
        🗂 PROJECTS
        <span className="tag">{projects.length} project(s)</span>
      </div>
      <div style={{display: 'flex', gap: 0, height: 'calc(100% - 48px)', overflow: 'hidden'}}>
        {/* Left: project list */}
        <div
          style={{
            width: 240, flexShrink: 0, display: 'flex', flexDirection: 'column',
            borderRight: '1px solid var(--rule)', overflow: 'hidden',
            background: dragHover ? 'rgba(240, 198, 116, 0.15)' : 'transparent',
            outline: dragHover ? '2px dashed var(--accent-sun)' : 'none',
            outlineOffset: '-4px',
            transition: 'background var(--motion-fast) var(--ease-out)',
          }}
          onDragOver={(e) => { e.preventDefault(); setDragHover(true); }}
          onDragLeave={() => setDragHover(false)}
          onDrop={onDropFolder}
        >
          <div className="proj-section-head" style={{display:'flex',alignItems:'center',gap:'var(--sp-3)'}}>
            <span style={{flex:1}}>PROJECTS · {projects.length}</span>
            <button
              onClick={() => addProject('')}
              title="Add a new project (drop a folder here too)"
              style={{
                background: 'var(--paper)', border: '1.5px solid var(--ink)',
                borderRadius: 'var(--radius-2)',
                fontSize: 'var(--text-9)', fontWeight: 700,
                padding: 'var(--sp-1) var(--sp-3)',
                color: 'var(--ink)', cursor: 'pointer',
              }}
            >+ ADD</button>
          </div>
          <div style={{overflowY: 'auto', flex: 1, padding: '4px 0'}}>
            {projects.length === 0 && (
              <div className="proj-empty-msg">
                No projects yet.<br/>
                <span style={{fontSize:'var(--text-9)',opacity:0.7}}>Click + ADD or drop a folder here.</span>
              </div>
            )}
            {projects.map(p => (
              <div
                key={p.id}
                className={'tree-row proj-list-row' + (selected === p.id ? ' active' : '')}
                style={{cursor: 'pointer', padding: '8px 12px', flexDirection: 'column', alignItems: 'flex-start', gap: 1, position: 'relative'}}
                onClick={() => { if (renamingId !== p.id) { setSelected(p.id); setOpenFile(null); setRightTab('files'); } }}
                title={p.path}
              >
                {renamingId === p.id ? (
                  <input
                    autoFocus
                    value={renameDraft}
                    onChange={e => setRenameDraft(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') { e.preventDefault(); commitRename(); }
                      else if (e.key === 'Escape') { e.preventDefault(); cancelRename(); }
                    }}
                    onBlur={commitRename}
                    onClick={e => e.stopPropagation()}
                    style={{
                      width: '100%', fontFamily: 'VT323', fontSize: 16,
                      padding: '2px 4px', border: '2px solid var(--ink)',
                      background: 'var(--paper)', color: 'var(--ink)',
                    }}
                  />
                ) : (
                  <div className="proj-list-name">{p.name}</div>
                )}
                {p.path && renamingId !== p.id && <div className="proj-list-path">{p.path}</div>}
                {/* Hover-only row actions — visible only when this row is
                    the active selection so the list stays clean. The
                    renaming UI takes precedence so these don't overlap. */}
                {selected === p.id && renamingId !== p.id && (
                  <div className="proj-row-actions" style={{
                    position: 'absolute', top: 4, right: 4,
                    display: 'flex', gap: 2,
                  }}>
                    <button
                      title="Rename project"
                      onClick={(e) => { e.stopPropagation(); beginRename(p); }}
                      style={{
                        fontSize: 9, padding: '2px 5px',
                        border: '1px solid var(--rule)', borderRadius: 3,
                        background: 'var(--paper)', color: 'var(--ink)',
                        cursor: 'pointer',
                      }}
                    >✎</button>
                    <button
                      title="Delete project"
                      onClick={(e) => { e.stopPropagation(); deleteProject(p); }}
                      style={{
                        fontSize: 9, padding: '2px 5px',
                        border: '1px solid var(--rule)', borderRadius: 3,
                        background: 'var(--paper)', color: 'var(--ink-3, #b85a4a)',
                        cursor: 'pointer',
                      }}
                    >✕</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Middle: file tree + agent assignment panel */}
        {project ? (
          <div style={{width: 260, flexShrink: 0, display: 'flex', flexDirection: 'column', borderRight: '1px solid var(--rule)', overflow: 'hidden'}}>
            <div className="proj-section-head" title={project.path} style={{display:'flex',alignItems:'center',gap:'var(--sp-2)'}}>
              <span style={{flex:1,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{project.name}</span>
              <button
                className="px-btn ghost"
                style={{fontSize:9,padding:'2px 7px',flexShrink:0}}
                title="New folder in this project"
                onClick={newFolder}
              >＋ Folder</button>
              <button
                className="px-btn ghost"
                style={{fontSize:9,padding:'2px 7px',flexShrink:0}}
                title="Upload files to this project — share them with the assigned agents"
                onClick={() => { setUploadTargetDir(null); if (uploadInputRef.current) uploadInputRef.current.click(); }}
              >⬆ Share</button>
            </div>
            <input ref={uploadInputRef} type="file" multiple style={{display:'none'}}
              onChange={(e) => { uploadFiles(e.target.files, uploadTargetDir); e.target.value = ''; setUploadTargetDir(null); }} />
            <div
              style={{overflowY:'auto', flex:1, padding:'4px 0', position:'relative',
                      background: fileDragHover ? 'rgba(240, 198, 116, 0.15)' : 'transparent',
                      outline: fileDragHover ? '2px dashed var(--accent-sun)' : 'none', outlineOffset:'-2px',
                      transition:'background var(--motion-fast) var(--ease-out)'}}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setFileDragHover(true); }}
              onDragLeave={(e) => {
                e.preventDefault();
                // Ignore leaves that just cross onto a child tree row — only
                // clear when the drag actually exits the container (no strobe).
                if (!e.currentTarget.contains(e.relatedTarget)) setFileDragHover(false);
              }}
              onDrop={(e) => {
                e.preventDefault(); e.stopPropagation(); setFileDragHover(false);
                if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
              }}
            >
              <LocalTree path={project.path} onSelectFile={readFile} refreshNonce={treeNonce} onRename={renameEntry} onDelete={deleteEntry} onUploadTo={uploadTo} />
              {fileDragHover && (
                <div style={{position:'absolute', inset:0, display:'flex', alignItems:'center', justifyContent:'center',
                             pointerEvents:'none', fontSize:11, fontWeight:600, color:'var(--accent-sun)',
                             textShadow:'0 1px 2px var(--paper)'}}>Drop to share with agents</div>
              )}
            </div>
            {/* Agent assignment — assigning at least one agent reveals a
                "📁 <project name>" room in the chat panel's thread tabs.
                Sending a message in that room fans out to all assigned
                agents, with all their replies streamed inline. */}
            <div className="proj-agents-panel">
              <div className="proj-agents-head">
                <span>👥 ASSIGNED · {(project.agentIds || []).length}</span>
                <button
                  className="proj-talk-btn"
                  style={{width: 'auto', margin: 0, padding: '2px 8px', fontSize: 9}}
                  disabled={(project.agentIds || []).length === 0}
                  onClick={() => {
                    /* Open the floating chat window (Projects view uses it)
                       and switch its active thread to this project's room.
                       Cross-component event lets ChatPanel set itself
                       without us lifting state. */
                    if (window.cafresohqSetChatOpen) window.cafresohqSetChatOpen(true);
                    window.dispatchEvent(new CustomEvent('cafresohq:set-active-thread', { detail: 'project:' + project.id }));
                  }}
                  title="Open the multi-agent chat room for this project"
                >TALK ↗</button>
              </div>
              <div className="proj-agents-list">
                {agents.length === 0 && (
                  <div style={{fontSize: 10, opacity: 0.5, padding: '6px'}}>
                    No agents hired yet — go to Team to hire some.
                  </div>
                )}
                {agents.map(a => {
                  const checked = (project.agentIds || []).includes(a.id);
                  return (
                    <div
                      key={a.id}
                      className={'proj-agents-row' + (checked ? ' checked' : '')}
                      onClick={() => toggleAgent(a.id)}
                      title={`${a.role}${a.elevated ? ' · elevated (computer access)' : ''}`}
                    >
                      <span className={'proj-agents-checkbox' + (checked ? ' checked' : '')}>
                        {checked ? '✓' : ''}
                      </span>
                      <span style={{flex: 1, fontWeight: 600}}>{a.name}</span>
                      <span style={{fontSize: 9, opacity: 0.6}}>{a.elevated ? '🛡' : '👤'}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          <div style={{width: 260, flexShrink: 0, borderRight: '1px solid var(--rule)'}}>
            <div className="proj-empty-msg">Select a project to browse its files.</div>
          </div>
        )}

        {/* Right: [FILES] [TERMINAL] tab bar + content */}
        <div style={{flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, overflow: 'hidden'}}>
          {project && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 0,
              borderBottom: '1px solid var(--rule)', flexShrink: 0,
              background: 'var(--paper)',
            }}>
              {['files', 'terminal'].map(tab => (
                <button
                  key={tab}
                  onClick={() => setRightTab(tab)}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    padding: '6px 16px', fontSize: 10, fontWeight: 700,
                    fontFamily: "'JetBrains Mono', monospace",
                    color: rightTab === tab ? '#7c6bff' : 'var(--ink-dim)',
                    borderBottom: rightTab === tab ? '2px solid #7c6bff' : '2px solid transparent',
                    letterSpacing: 1, textTransform: 'uppercase',
                  }}
                >
                  {tab === 'files' ? '📄 FILES' : '⚡ TERMINAL'}
                </button>
              ))}
            </div>
          )}
          {/* Persistent terminal sessions — stay mounted so PTY + chat survive tab/project switches */}
          {openedTerminals.map(pid => {
            const p = projects.find(x => x.id === pid);
            if (!p) return null;
            const active = rightTab === 'terminal' && selected === pid;
            return (
              <div key={pid} style={{flex: 1, overflow: 'hidden', display: active ? undefined : 'none'}}>
                <ProjectTerminal project={p} visible={active} />
              </div>
            );
          })}

          {/* Files / empty states — only when terminal is not active */}
          {!(rightTab === 'terminal' && project) && (
            rightTab === 'files' && openFile ? (
              <div style={{flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0}}>
                <div className="proj-edit-head ide-edit-head">
                  <span className="ide-tab">
                    <span className="ide-tab-icon">{ideFileIcon(openFile.path)}</span>
                    <span className="ide-tab-name">{openFile.path.split(/[\\/]/).pop()}</span>
                    {openFile.dirty && <span className="ide-tab-dot" title="unsaved changes">●</span>}
                  </span>
                  <span className="ide-tab-path">{openFile.path}</span>
                  {err && <span className="proj-edit-err">{err}</span>}
                  <span style={{flex:1}}/>
                  <span style={{display:'inline-flex', gap:2, marginRight:8}}>
                    <button className={`px-btn ${!previewMode ? 'primary' : 'secondary'}`} style={{fontSize:9, padding:'3px 9px'}} onClick={() => setPreviewMode(false)}>Code</button>
                    <button className={`px-btn ${previewMode ? 'primary' : 'secondary'}`} style={{fontSize:9, padding:'3px 9px'}} onClick={() => setPreviewMode(true)} title="Render this file (HTML, PDF, image, markdown…)">Preview</button>
                  </span>
                  {!previewMode && (
                    <span className="ide-stats">
                      {openFile.content.split('\n').length} ln · {openFile.content.length} ch · {ideLangFromPath(openFile.path).toUpperCase()}
                    </span>
                  )}
                  <button className="px-btn primary" style={{fontSize: 10, padding: '3px 10px'}} onClick={saveFile} disabled={!openFile.dirty || busy}>
                    {busy ? 'Saving…' : openFile.dirty ? 'Save' : 'Saved'}
                  </button>
                </div>
                {previewMode
                  ? <FilePreview file={openFile} />
                  : <IDEEditor
                      value={openFile.content}
                      onChange={(v) => setOpenFile({ ...openFile, content: v, dirty: true })}
                      path={openFile.path}
                    />}
              </div>
            ) : project ? (
              <div style={{flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
                <div className="proj-empty-msg" style={{textAlign: 'center'}}>
                  <div style={{fontSize: 24, marginBottom: 8, opacity: 0.4}}>📄</div>
                  Select a file to edit, or switch to Terminal to run a CLI agent.
                </div>
              </div>
            ) : null
          )}
        </div>
      </div>
      {showAdd ? (
        <AddProjectModal
          prefillName={addPrefill}
          onClose={() => setShowAdd(false)}
          onCommit={commitProject}
        />
      ) : null}
    </div>
  );
}

/* ---------------- Add Project modal ---------------- */
/* ── File-system browser popup ────────────────────────────────────────────── */
function FileBrowserModal({ initialPath, onSelect, onClose }) {
  const [curPath,  setCurPath]  = useSV('');
  const [parent,   setParent]   = useSV(null);
  const [entries,  setEntries]  = useSV([]);
  const [loading,  setLoading]  = useSV(false);
  const [err,      setErr]      = useSV(null);

  const browse = (p) => {
    setLoading(true); setErr(null);
    const qs = p ? `?path=${encodeURIComponent(p)}` : '';
    fetch(`${window._API_BASE || ''}/fs/browse${qs}`)
      .then(r => r.json())
      .then(j => {
        if (j.error) throw new Error(j.error);
        setCurPath(j.path);
        setParent(j.parent);
        setEntries(j.entries || []);
      })
      .catch(e => setErr(e.message || String(e)))
      .finally(() => setLoading(false));
  };

  React.useEffect(() => { browse(initialPath || ''); }, []);

  return (
    <div className="backdrop" onClick={onClose} style={{ zIndex: 2000 }}>
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--paper)', border: '2px solid var(--rule)',
          borderRadius: 10, width: 'min(520px, 96vw)', maxHeight: '80vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '0 8px 48px rgba(0,0,0,0.5)',
        }}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '10px 14px', borderBottom: '1px solid var(--rule)',
          background: 'var(--paper-2)',
        }}>
          <span style={{ fontWeight: 700, fontSize: 11, flex: 1 }}>📁 BROWSE FOLDERS</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: 'var(--ink-dim)' }}>✕</button>
        </div>

        {/* Path breadcrumb + Up */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '6px 12px', borderBottom: '1px solid var(--rule)',
          background: 'var(--paper-2)',
        }}>
          <button
            onClick={() => parent && browse(parent)}
            disabled={!parent || loading}
            style={{
              background: 'none', border: '1px solid var(--rule)', borderRadius: 4,
              padding: '2px 8px', fontSize: 10, cursor: parent ? 'pointer' : 'default',
              color: parent ? 'var(--ink)' : 'var(--ink-dim)',
            }}
          >↑ Up</button>
          <span style={{
            flex: 1, fontSize: 10, fontFamily: "'JetBrains Mono', monospace",
            color: 'var(--ink)', overflow: 'hidden', textOverflow: 'ellipsis',
            whiteSpace: 'nowrap', direction: 'rtl', textAlign: 'left',
          }}>{curPath || '…'}</span>
        </div>

        {/* Entries */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
          {loading && <div style={{ padding: 16, fontSize: 12, color: 'var(--ink-dim)', textAlign: 'center' }}>Loading…</div>}
          {err    && <div style={{ padding: 12, fontSize: 11, color: 'var(--red, #f87171)' }}>⚠ {err}</div>}
          {!loading && entries.length === 0 && !err && (
            <div style={{ padding: 16, fontSize: 11, color: 'var(--ink-dim)', textAlign: 'center' }}>Empty folder</div>
          )}
          {entries.map(e => (
            <div
              key={e.path}
              onClick={() => e.type === 'dir' && browse(e.path)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '6px 14px', cursor: e.type === 'dir' ? 'pointer' : 'default',
                fontSize: 12, color: e.type === 'dir' ? 'var(--ink)' : 'var(--ink-dim)',
                borderBottom: '1px solid var(--rule)',
              }}
              className={e.type === 'dir' ? 'tree-row' : ''}
            >
              <span style={{ fontSize: 14, width: 20 }}>{e.type === 'dir' ? '📁' : '📄'}</span>
              <span style={{ flex: 1, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 }}>{e.name}</span>
              {e.type === 'dir' && <span style={{ fontSize: 10, color: 'var(--ink-dim)' }}>›</span>}
            </div>
          ))}
        </div>

        {/* Footer — select current folder */}
        <div style={{
          padding: '10px 14px', borderTop: '1px solid var(--rule)',
          display: 'flex', gap: 8, justifyContent: 'flex-end',
          background: 'var(--paper-2)',
        }}>
          <button className="px-btn secondary" onClick={onClose}>Cancel</button>
          <button
            className="px-btn primary"
            disabled={!curPath}
            onClick={() => { if (curPath) onSelect(curPath); }}
          >✓ Select This Folder</button>
        </div>
      </div>
    </div>
  );
}

/* ── Add Project modal ────────────────────────────────────────────────────── */
function AddProjectModal({ prefillName, onClose, onCommit }) {
  const [tab, setTab] = useSV('local');           // 'local' | 'github'
  const [name, setName] = useSV(prefillName || '');
  const [path, setPath] = useSV('');
  const [repoUrl, setRepoUrl] = useSV('');
  const [shallow, setShallow] = useSV(true);
  const [busy, setBusy] = useSV(false);
  const [err, setErr] = useSV(null);
  const [showBrowser, setShowBrowser] = useSV(false);

  const submitLocal = (e) => {
    e && e.preventDefault();
    setErr(null);
    if (!name.trim()) return setErr('name required');
    if (!path.trim()) return setErr('path required');
    onCommit({ name: name.trim(), path: path.trim(), source: 'local' });
  };

  const submitGithub = async (e) => {
    e && e.preventDefault();
    setErr(null);
    const url = repoUrl.trim();
    if (!url) return setErr('repo URL or owner/repo required');
    setBusy(true);
    try {
      const r = await window.CafresoHQClient.cloneRepo({
        url,
        name: name.trim() || undefined,
        depth: shallow ? 1 : 0,
      });
      onCommit({ name: r.name, path: r.path, source: 'github:' + url });
    } catch (e2) {
      setErr((e2.message || String(e2)) + (e2.detail ? '\n' + e2.detail : ''));
      setBusy(false);
    }
  };

  return (
    <div className="backdrop" onClick={onClose}>
      <div className="modal addproj-modal" onClick={e => e.stopPropagation()} style={{width:'min(560px, 100%)', gridTemplateRows: 'auto auto 1fr'}}>
        <div className="modal-head">
          <span className="title">ADD PROJECT</span>
          <button className="px-btn secondary" onClick={onClose} style={{fontSize:11,padding:'4px 10px'}}>✕</button>
        </div>
        <div className="addproj-tabs">
          <button className={'addproj-tab' + (tab === 'local' ? ' active' : '')} onClick={() => setTab('local')}>📁 Local folder</button>
          <button className={'addproj-tab' + (tab === 'github' ? ' active' : '')} onClick={() => setTab('github')}>🐙 GitHub repo</button>
        </div>
        <div className="modal-body">
          {tab === 'local' ? (
            <form onSubmit={submitLocal} className="addproj-form">
              <label>Name<input value={name} onChange={e => setName(e.target.value)} placeholder="My project" autoFocus /></label>
              <label>
                Absolute path
                <div style={{ display: 'flex', gap: 6 }}>
                  <input
                    value={path}
                    onChange={e => setPath(e.target.value)}
                    placeholder="C:\Users\You\projects\myrepo"
                    style={{ flex: 1 }}
                  />
                  <button
                    type="button"
                    className="px-btn secondary"
                    onClick={() => setShowBrowser(true)}
                    style={{ whiteSpace: 'nowrap', fontSize: 11, padding: '4px 10px' }}
                  >📁 Browse</button>
                </div>
              </label>
              <small>Path must be inside CAFRESOHQ_ALLOWED_DIRS for agents to access it.</small>
              {err ? <div className="addproj-err">{err}</div> : null}
              <div className="addproj-actions">
                <button type="button" className="px-btn secondary" onClick={onClose}>Cancel</button>
                <button type="submit" className="px-btn primary">Add</button>
              </div>
            </form>
          ) : (
            <form onSubmit={submitGithub} className="addproj-form">
              <label>Repo<input value={repoUrl} onChange={e => setRepoUrl(e.target.value)} placeholder="owner/repo  or  https://github.com/owner/repo" autoFocus /></label>
              <label>Local folder name (optional)<input value={name} onChange={e => setName(e.target.value)} placeholder="auto from URL if blank" /></label>
              <label className="checkbox-row">
                <input type="checkbox" checked={shallow} onChange={e => setShallow(e.target.checked)} />
                <span>Shallow clone (fast — no history)</span>
              </label>
              <small>Cloned into the first allowed directory. Requires <code>git</code> on the server's PATH.</small>
              {err ? <div className="addproj-err" style={{whiteSpace:'pre-wrap'}}>{err}</div> : null}
              <div className="addproj-actions">
                <button type="button" className="px-btn secondary" onClick={onClose} disabled={busy}>Cancel</button>
                <button type="submit" className="px-btn primary" disabled={busy}>{busy ? 'Cloning…' : 'Clone & add'}</button>
              </div>
            </form>
          )}
        </div>
      </div>
      {showBrowser && (
        <FileBrowserModal
          initialPath={path || ''}
          onSelect={(selected) => { setPath(selected); if (!name.trim()) setName(selected.split(/[\\/]/).filter(Boolean).pop() || ''); setShowBrowser(false); }}
          onClose={() => setShowBrowser(false)}
        />
      )}
    </div>
  );
}

/* ---------------- Coming Soon placeholder ---------------- */
function ComingSoon({ label }) {
  return (
    <div className="view-soon">
      <div className="section-title">{label || 'Coming Soon'}</div>
      <div className="empty-state">
        <div className="empty-title">🚧 In progress</div>
        <div className="empty-sub">This feature is coming soon.</div>
      </div>
    </div>
  );
}

/* ================================================================
   TerminalView — full-screen standalone terminal
   A permanent HQ-global terminal that starts Hermes and lets you
   add Claude Code / Codex / Gemini tabs once they are installed.
   Uses the same ProjectTerminal machinery but with a fixed project
   context (id='hq-global-terminal', path='') so sessions persist.
   ================================================================ */
function TerminalView() {
  // A non-empty path is required — the embedded PTY bails on a falsy project.path
  // (that's why the standalone Terminal tab loaded blank while Projects worked).
  // /root/Documents is the container's code-agent sandbox dir (created in the
  // Dockerfile); local runs override via CAFRESOHQ_TERMINAL_CWD if they want.
  const HQ_PROJECT = React.useMemo(() => ({
    id: 'hq-global-terminal',
    path: (typeof window !== 'undefined' && window._TERMINAL_CWD) || '/root/Documents',
  }), []);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0a10' }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px',
        borderBottom: '1px solid rgba(124,107,255,0.18)',
        background: '#0f0f1a',
        flexShrink: 0,
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.06em', color: '#7c6bff', fontFamily: "'JetBrains Mono', monospace" }}>
          ☼ TERMINAL
        </span>
        <span style={{ fontSize: 10, color: 'rgba(212,216,232,0.45)', fontFamily: "'JetBrains Mono', monospace" }}>
          Hermes · Claude Code · Codex · Gemini
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 9, color: 'rgba(212,216,232,0.3)', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em' }}>
          + to add session · × to close tab
        </span>
      </div>
      {/* Terminal panel fills remaining space */}
      <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
        <ProjectTerminal project={HQ_PROJECT} visible={true} />
      </div>
    </div>
  );
}

/* ================================================================
   Export all views for app.jsx
   ================================================================ */
window.CafresoHQViews = {
  TasksView,
  MemoryPage,
  TeamView,
  CalendarView,
  VaultView,
  GraphView,
  ComingSoon,
  ProjectsView,
  WorkspaceView,
  TerminalView,
  VIEW_LABELS,
};
