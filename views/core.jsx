import { CafresoHQV2 } from '../features.jsx';
import { CafresoHQClient } from '../claude-client.jsx';
import { Sprite } from '../sprites.jsx';
import { xpStats } from '../app/experience.jsx';
import { officeDate } from '../app/artifacts.jsx';
import { brainName, CAN_USE_OFF_TIP, CAN_USE_TIP, EFFORT_TIP, grantedTools, memoryLabel, memoryNotes, payrollLabel, poweredBy } from '../app/cast.jsx';
import { attentionCount as attentionCountOf, groupAttention, onRoster } from '../app/attention.jsx';
import { HQ } from '../hq-runtime.jsx';
/* One source of truth with the runtime that does the folding. */
const MEM_CAP = HQ.MEMORY_PROMPT_CAP;
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
  /* The Library, not the Vault, and not "Markdown" anything: this room
     holds decks, documents, images, video and research alongside the .md
     notes, and a boss who reads MARKDOWN VAULT over a folder of .pptx has
     been told the wrong thing about where their work lives. The view id
     stays `vault` — it is a route, a state key and a bridge message name
     shared with offices already on disk. See the Library/vault split in
     scripts/test_the_library_has_one_name.py. */
  vault:     'LIBRARY',
  graph:     'LIBRARY GRAPH',
  team:      'STAFF ROSTER',
  calendar:  'CALENDAR',
  projects:  'WORKSPACE',
  terminal:  'TERMINAL',
};

/* ---------------- Tasks (full board with filter + search) ---------------- */
function TasksView({ tasks, agents, onAdd, onMove, onDelete, onCyclePriority, onDropTaskOnAgent, onAssign, onAssignToChat, onMakeRoomFromTask, onStartTask, experience = [] }) {
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
        {/* Both buttons DRAFT — they hand the boss something to review, and
            deliberately so (the handlers say as much). Measured live:
            → CHAT prefills the composer with the task and sends nothing,
            with at most the assignee's @mention — not a fan-out, which is
            what happens only if the boss types more @names themselves.
            📋 ROOM opens the pre-filled NEW MEETING ROOM form without
            creating the meeting. The old line promised both were done
            deals. */}
        <span className="tag">{filtered.length} of {tasks.length} · click → CHAT to draft it in chat, 📋 ROOM to set up a meeting</span>
      </div>
      <div className="view-toolbar">
        <input className="view-search" placeholder="Search tasks…" value={q} onChange={e=>setQ(e.target.value)} />
        <label className="view-check">
          <input type="checkbox" checked={showDone} onChange={e=>setShowDone(e.target.checked)} />
          show completed
        </label>
      </div>
      <TaskBoard tasks={filtered} agents={agents}
        /* The UNFILTERED count — `filtered` shrinks with the search box and
           the show-completed toggle, and neither of those makes the office
           new again. */
        totalCount={tasks.length}
        onAdd={onAdd} onMove={onMove} onDelete={onDelete}
        onCyclePriority={onCyclePriority}
        onAssign={onAssign}
        onAssignToChat={onAssignToChat}
        onMakeRoomFromTask={onMakeRoomFromTask}
        onStartTask={onStartTask}
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
        {/* Only the newest MEMORY_PROMPT_CAP entries actually reach a
            prompt (hq-runtime `memorySummary`). Below the cap the old
            unqualified line was true; above it, the boss would have been
            told every note was working when the oldest silently weren't.
            Say which ones, and only once it matters. */}
        <span className="tag">
          {memory.length > MEM_CAP
            ? `${memory.length} saved · the newest ${MEM_CAP} go out with every job CafresoHQ and the team pick up`
            : `${memory.length} ${memory.length === 1 ? 'entry' : 'entries'} · carried into every job CafresoHQ and the team pick up`}
        </span>
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
              {/* "remembers it forever" was false twice over: nothing is
                  forever, and a note stops reaching any prompt at all once it
                  falls past the newest MEM_CAP — which is precisely the drift
                  the header above this guards against, contradicted one
                  paragraph later. The cap is not mentioned here on purpose:
                  this only renders at zero entries, where it would be noise,
                  and the header starts saying it the moment it matters. */}
              Long-term memory goes out with every job your CEO and crew pick up — facts,
              preferences, rules, people. Add your first note below and the whole team works from it.
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
/* Action → icon for the inbox rows.

   Kept in step with `INSPECT_ACT_ICON` in ui/panels.jsx, which is the same
   map for the same rows in a different panel. Adding an action to one and
   not the other was measured on 2026-08-16: a chain-hold row came out ⛓ on
   the coworker's card and ✦ — the "no idea what this is" fallback — in the
   inbox, for the same event. Two feeds disagreeing about what kind of thing
   just happened is the office talking over itself. */
const ACT_ICON = {
  hired: '✦', assigned: '📋', dm: '✉', tool: '⚙', progress: '…',
  done: '✓', failed: '⚠', attention: '⚠', coffee: '☕', meeting: '👥', vault: '✎',
  blocked: '⛓', mission: '🔬',
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
  /* Same scoping `filtered` below applies before it ever reads `tab` — a
     boss who has clicked one coworker's chip is looking at THEIR inbox, not
     the whole office's. Without this, clicking Selvin's chip narrowed the
     row list to Selvin's events while the header ("N events"), the
     Attention tab's badge and the Done tab's badge kept counting every
     coworker — a boss reads "Needs attention · 6" over a filtered list of
     2 and has no way to tell which number lied. */
  const scopedActivity = React.useMemo(
    () => selectedAgentId ? activity.filter(e => e.agentId === selectedAgentId) : activity,
    [activity, selectedAgentId]);
  /* Same rule as the office pill and the nav badge — one shared helper, so
     the three can't drift apart (app/attention.jsx). Scoped activity in,
     already-scoped pendingApprovals in — both arguments now agree on whose
     inbox this is. */
  const attentionCount = React.useMemo(
    () => attentionCountOf(scopedActivity, pendingApprovals, agents),
    [scopedActivity, pendingApprovals, agents]);
  const doneCount = React.useMemo(
    () => scopedActivity.filter(e => e.action === 'done').length, [scopedActivity]);

  const counts = React.useMemo(() => {
    const c = new Map();
    for (const e of activity) c.set(e.agentId, (c.get(e.agentId) || 0) + 1);
    return c;
  }, [activity]);

  /* The attention tab groups; Activity and Done stay a full chronological
     log. This is the split that keeps grouping honest — the queue answers
     "what needs me", the log still shows every single event that happened,
     so nothing is ever actually hidden from the boss. */
  const filtered = React.useMemo(() => {
    let xs = scopedActivity;
    if (tab === 'attention') {
      /* onRoster here as well as in the count — if the pill filtered ghosts
         and this list didn't, the badge would say 3 over a list of 15, which
         is a worse bug than the one being fixed. One rule, both surfaces. */
      return groupAttention(onRoster(xs, agents).filter(e => e.priority === 'attention'));
    }
    if (tab === 'done') xs = xs.filter(e => e.action === 'done');
    return xs.map(e => ({ key: e.id, entry: e, count: 1, ids: [e.id] }));
  }, [scopedActivity, tab, agents]);

  /* Opening a group marks every occurrence read, not just the newest —
     otherwise the count would drop by one and the same row would come
     straight back unread, which is exactly the loop this fixes. */
  const toggle = (g) => {
    const e = g.entry;
    setExpandedId(prev => prev === g.key ? null : g.key);
    if (e.priority === 'attention' && onMarkRead) {
      (g.ids || [e.id]).forEach(id => onMarkRead(id));
    }
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
        <span style={{flex:1}}>📥 COWORKER INBOX</span>
        <span style={{fontSize:'var(--text-9)', opacity:0.7}}>{scopedActivity.length} event{scopedActivity.length===1?'':'s'}</span>
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
                <span style={{fontWeight:600}}>{ap.by || 'A coworker'}</span> needs a stamp: {ap.title}
              </div>
              <div className="oc-notif-meta"><span>{ap.kind || 'approval'}{ap.elevated ? ' · 🛡 file and shell access' : ''}</span></div>
              <div className="oc-act-jumps" style={{marginTop:6}}>
                <button className="px-btn primary" style={{fontSize:8}} onClick={() => onApprove && onApprove(ap.id)}>✓ Approve</button>
                <button className="px-btn danger" style={{fontSize:8}} onClick={() => onReject && onReject(ap.id)}>✕ Reject</button>
              </div>
            </div>
          </div>
        ))}
        {filtered.length === 0 && pendingApprovals.length === 0 && (
          <div className="proj-empty-msg">
            {tab === 'attention' ? 'Nothing needs you right now. 🎉' : tab === 'done' ? 'No completed work yet.' : 'Nothing from your team yet.'}<br/>
            <span style={{fontSize:'var(--text-9)',opacity:0.7}}>
              {tab === 'attention'
                ? 'Failures, blocks, and approval requests surface here.'
                : 'Assign a task or chat with the team and every real action lands here.'}
            </span>
          </div>
        )}
        {filtered.map(g => {
          const e = g.entry;
          const attn = e.priority === 'attention';
          const open = expandedId === g.key;
          return (
            <div key={g.key} className={'oc-notif-row' + (attn ? ' is-attn' : '')}
              onClick={() => toggle(g)} role="button" tabIndex={0}
              aria-expanded={open}
              onKeyDown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); toggle(g); } }}>
              <span className="oc-notif-icon" style={{color: attn ? 'var(--error)' : (e.color || 'var(--ink-3)')}} aria-hidden="true">
                {ACT_ICON[e.action] || '✦'}
              </span>
              <div className="oc-notif-body">
                <div className="oc-notif-msg">
                  <span style={{fontWeight:600}}>{e.agentName || 'HQ'}</span> {e.text}
                  {/* The repeat count, so collapsing hides nothing: this
                      said one thing N times and the row says so. */}
                  {g.count > 1 && <span className="oc-notif-times" title={`reported ${g.count} times`}>×{g.count}</span>}
                </div>
                <div className="oc-notif-meta">
                  <span>{fmtAgo(e.ts)} ago</span>
                  {g.count > 1 && <span> · latest of {g.count}</span>}
                </div>
                {/* Retry sits ON the row, not behind an expand.

                    This is the surface whose whole job is "something needs
                    you", and the one verb that answers a failure was hidden
                    until you clicked to open the row — the same shape as the
                    attention banner that looked live and did nothing. The
                    pinned approval rows above already show Approve/Reject
                    inline; a failure is no less actionable than a stamp.

                    Acting on a row also marks it read: the header count means
                    "not dealt with yet", and this dealt with it. If the retry
                    fails again a fresh unread row lands and the count rises —
                    which is the honest answer, not a bookkeeping trick. */}
                {e.action === 'failed' && onRetry && (
                  <div className="oc-act-jumps" style={{marginTop:6}} onClick={ev => ev.stopPropagation()}>
                    {/* Retry acts on the NEWEST occurrence (g.entry) and
                        clears the whole group — retrying "Kenji is stuck"
                        deals with that problem, not with one of its three
                        reports.

                        A row that names neither a run nor a coworker — the
                        runner dropping, a publish falling over — has no
                        message behind it, and the button used to grab the
                        newest failure anywhere in the office and send it.
                        Same rule as the Inbox's ↻ RE-SEND: the door only
                        appears where it can do what its label says. The
                        row keeps "What happened?" either way. */}
                    {(e.messageId || e.agentId) && (
                    <button className="px-btn primary" style={{fontSize:8}}
                      onClick={() => { onRetry(e); if (onMarkRead) (g.ids || [e.id]).forEach(id => onMarkRead(id)); }}>↻ Retry</button>
                    )}
                    <button className="px-btn ghost" style={{fontSize:8}} onClick={() => toggle(g)}>
                      {open ? 'Hide what happened' : 'What happened?'}
                    </button>
                  </div>
                )}
                {open && (e.detail || e.taskId || e.nodeId || e.action === 'failed') && (
                  <div className="oc-act-detail" onClick={ev => ev.stopPropagation()}>
                    {e.detail && <div className="oc-act-detail-body">{e.detail}</div>}
                    <div className="oc-act-jumps">
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

  /* The roster grid was blind to a coworker who just failed. Watching a real
     one (Miko, no brain configured) confirmed it: the floor sprite two
     panels away showed an honest "hit a snag — …" bubble, and this card —
     the one place a boss actually goes to see "who's who" — read IDLE, 0
     work done, identical to a coworker who has never been given anything.
     `agent.mood === 'stuck'` already carries the signal (set alongside the
     honest sentence in `agent.task`); the card just never looked at it.

     `activity` is newest-first (logActivity prepends), so the first 'failed'
     entry per agent IS the latest — the same one Retry should act on. Gated
     on the LIVE mood, not "has ever failed": the moment a retry succeeds,
     mood clears and the card should stop pointing at old news. */
  const lastFailedByAgent = React.useMemo(() => {
    const m = new Map();
    for (const e of activity) if (e.action === 'failed' && !m.has(e.agentId)) m.set(e.agentId, e);
    return m;
  }, [activity]);

  /* What each coworker has written down. The notes have always existed —
     `Agents/<name>/` in the vault — but no boss-facing surface ever showed
     them, so the office's one persistent, across-sessions fact about an
     employee was invisible unless you went digging in the file tree.

     One list for the whole roster, not one fetch per card. `null` means the
     cabinet could not be read, and that is deliberately NOT the same as an
     empty list: rendering "0 notes" when nobody looked would claim the
     coworker has saved nothing, which is the exact shape of dishonesty §4
     forbids. memoryLabel returns null for it and the row disappears. */
  const [vaultPaths, setVaultPaths] = useSV(null);
  React.useEffect(() => {
    let dead = false;
    (async () => {
      try {
        const list = await CafresoHQClient.vaultList();
        if (!dead) setVaultPaths((list || []).map(f => (f && typeof f === 'object') ? String(f.path || '') : String(f || '')).filter(Boolean));
      } catch (_e) { if (!dead) setVaultPaths(null); }
    })();
    return () => { dead = true; };
  }, [agents.length]);

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
          title="Show what your coworkers have been doing"
        >📥 INBOX</button>
        <button
          onClick={onHire}
          className="px-btn primary"
          style={{ fontSize: 'var(--text-10)', padding: '6px 12px' }}
          title="Hire a new coworker"
        >+ HIRE</button>
      </div>
      <div style={{display: 'flex', flex: 1, minHeight: 0, gap: 0}}>
        <div className="team-grid" style={{flex: 1, minWidth: 0, overflowY: 'auto', alignContent: 'start'}}>
          {agents.map(a => {
            const pay = payrollLabel(a);
            // Experience (§5): jobs from the ledger, not a.tasksDone — that
            // legacy counter also counted chat replies, which aren't jobs.
            const xp = xpStats(experience, a.id);
            // Live distress, not history: see the useMemo above for why this
            // is gated on mood rather than "ever failed".
            const stuck = a.mood === 'stuck';
            const lastFailed = stuck ? lastFailedByAgent.get(a.id) : null;
            return (
              <div key={a.id} className={'team-card' + (stuck ? ' is-stuck' : '')} onClick={()=>onInspect(a)}>
                {/* The STATUS pill stays truthful about liveness (busy/idle) —
                    §4's rule that only agent.status answers "is this running
                    right now" applies here too. Distress is a second axis and
                    gets its own badge, never borrows this one's word. */}
                <div className={`status-pill ${a.status}`}>{a.status.toUpperCase()}</div>
                {stuck && <div className="team-stuck-badge" title="Needs you">!</div>}
                <div className="sprite-box"><Sprite data={a.color} scale={3} className="bob"/></div>
                <div className="name">{a.name}</div>
                <div className="role">{a.role}</div>
                {stuck && a.task && (
                  <div className="team-stuck-line" title={a.task}>⚠ {a.task}</div>
                )}
                <div className="team-stats">
                  {/* §6, binding: no raw model ids and no "tokens"/"cost" on
                      a coworker card — brain · work done · payroll. The id
                      stays in the tooltip so debugging doesn't lose it. */}
                  <div><span className="lbl">Brain</span><span className="val" title={(() => {
                    /* The VISIBLE text here was fixed once already — the card
                       used to print `openrouter:google/gemma-3-27b-it` under a
                       label reading "Model", and brainName() was written to
                       stop it. The tooltip kept the raw id anyway: hovering
                       the roster card showed `ollama:llama3.1` on the front
                       door, which north-star §3.6 rules out in as many words
                       ("no settings pages, no model IDs") and §6 allows only
                       in Settings and desktop mode.

                       Copy fixed, state left behind — recurring shape (2),
                       this time hiding in an attribute rather than a
                       variable. A `title` is copy; it just does not show up
                       when you read the screen. */
                    const v = poweredBy(a);
                    return v ? `Powered by ${v} — the coworker is yours; the vendor is just the engine`
                             : 'Runs on whatever brain you gave them';
                  })()}>{brainName(a)}</span></div>
                  {/* "Work done" for a TOKEN COUNT, sitting directly above
                      "Jobs" — the actual count of work done. Two labels on
                      one card claiming the same thing, and only one of them
                      earned it. §6 banned the word "tokens" here and the
                      rename obeyed the letter of that while making the
                      collision worse: the number stopped saying what it was
                      and started saying what Jobs says.
                      Effort and delivery are different claims. */}
                  <div><span className="lbl">Effort</span><span className="val" title={EFFORT_TIP}>{(a.tokens||0).toLocaleString()}</span></div>
                  <div><span className="lbl">Payroll</span><span className="val" title={pay.title}>{pay.text}</span></div>
                  <div><span className="lbl">Jobs</span><span className="val">{xp.jobs}{xp.streak >= 3 ? ' 🔥' : ''}</span></div>
                  {/* Reliability. xpStats has always computed snags and no
                      surface showed it, so a boss could see how much a
                      coworker delivered but never how often they came back
                      empty. Shown only when there ARE snags: Jobs already
                      carries the denominator, and a standing "Snags 0" on
                      every card is noise, not reassurance.
                      §5: a run the USER stopped is never recorded as a snag —
                      taking the folder back is not their failure. */}
                  {xp.snags > 0 && (
                    <div><span className="lbl">Snags</span>
                      <span className="val" title={`${xp.snags} run${xp.snags === 1 ? '' : 's'} came back empty or failed. Runs you stopped yourself are not counted.`}>{xp.snags}</span></div>
                  )}
                  {/* Their notebook. Hidden entirely when the cabinet is
                      unreadable — see the comment on vaultPaths. */}
                  {(() => {
                    const label = memoryLabel(a, vaultPaths);
                    if (!label) return null;
                    const notes = memoryNotes(a, vaultPaths);
                    return (
                      <div><span className="lbl">Remembers</span>
                        <span className="val" title={notes.length ? notes.slice(0, 12).join('\n') : 'nothing saved yet'}>{label}</span>
                      </div>
                    );
                  })()}
                  {/* The twin of the inspect panel's row, missed when that
                      one was renamed off "Tools used" to "Can use" earlier
                      today. This card lists five stats as label/value pairs
                      — Brain, Effort, Payroll, Jobs, Remembers — and then
                      ended with a bare `WEB` and no tooltip, so the one item
                      on the card that is a PERMISSION read like an
                      unlabelled achievement. Same words and same tooltip as
                      the panel, because it is the same fact.

                      Inside `.team-stats`, not after it: `.lbl` and the
                      column layout are scoped to that container, so the
                      first cut put a correctly-worded label outside the only
                      rule that styles it. */}
                  {/* Over `grantedTools`, not `a.tools` — the stored list is
                      the CLAIM, and printing it made this row promise Dax
                      "files" with elevation off and "db", which reaches
                      nothing anywhere. See the note on grantedTools. */}
                  {(() => {
                    const reach = grantedTools(a.tools, HQ.capabilityFacts(a));
                    if (!reach.granted.length && !reach.locked.length) return null;
                    return (
                      <div><span className="lbl">Can use</span>
                        <span className="team-tools" title={CAN_USE_TIP + (reach.locked.length ? CAN_USE_OFF_TIP : '')}>
                          {reach.granted.map(g => <span key={g.id} title={`Can ${g.say}`}>{g.id}</span>)}
                          {/* Dimmed rather than dropped: the capability is
                              real and the switch is nameable, so §7 wants the
                              route on the card, not a row that quietly got
                              shorter. Inline opacity because this row has no
                              stylesheet of its own to add a class to. */}
                          {reach.locked.map(l => (
                            <span key={l.id} style={{opacity: 0.45}}
                                  title={l.unlock ? `Not yet — ${l.unlock}.` : 'Switched off.'}>{l.id} · off</span>
                          ))}
                        </span>
                      </div>
                    );
                  })()}
                </div>
                <button
                  className="px-btn ghost team-inbox-btn"
                  style={{fontSize: 'var(--text-9)', position: 'absolute', top: 6, right: 6}}
                  onClick={(e)=>{ e.stopPropagation(); setShowInbox(true); setSelectedAgentId(a.id); }}
                  title="Show what this coworker has been doing"
                >📥</button>
                {lastFailed && onRetry ? (
                  <div className="team-card-actions">
                    <button className="px-btn primary" style={{fontSize:8, flex:1}}
                      onClick={(e)=>{ e.stopPropagation(); onRetry(lastFailed); }}>↻ Retry</button>
                    <button className="px-btn danger team-dismiss" style={{fontSize:8, flex:1}}
                      onClick={(e)=>{e.stopPropagation(); onDismiss(a.id);}}>LET GO</button>
                  </div>
                ) : (
                  <button className="px-btn danger team-dismiss" style={{fontSize:8}} onClick={(e)=>{e.stopPropagation(); onDismiss(a.id);}}>LET GO</button>
                )}
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
/* The business's day view.

   It was a task-creation log wearing a calendar's name: every entry was a
   `createdAt`, so the one question a calendar exists to answer — what is
   still to come — had no answer here, and the header carried a standing
   IOU ("scheduling coming with stand-up") for a feature that had since
   shipped somewhere else entirely.

   Live missions are the scheduled work the app already has: a running one
   knows exactly when it ends (`startedAt + durationMs`). Those land on the
   day they finish, which is a real future entry. Nothing here is invented —
   a mission that isn't running contributes nothing, the same way an
   un-created task does. (Night-shift schedules carry a `nextRunAt` too and
   belong here as well, but they live behind the container bridge; they are
   not local state this view can read honestly, so they are left out rather
   than faked.) */
function CalendarView({ tasks, agents, missions = [], nightShiftBoard = [], nightShiftRuns = [] }) {
  const groups = useMV(() => {
    const out = new Map();
    /* officeDate, not toISOString — the office runs on the BOSS'S clock.
       artifacts.jsx already carries this scar: "a delivery filed at 8pm in
       New York was dated TOMORROW in its own header". The calendar had the
       same UTC bug and it reads worse here, because this view's whole job is
       to answer "what did we get done today".

       Measured on a live floor at Aug 7, 2:30 AM local: three tasks raised
       the previous evening (11:18, 11:26, 11:32 PM on Aug 6) were filed
       under "Today · 4" alongside one genuinely from Aug 7. West of UTC, last
       night's late work carries today's UTC date, so a boss checking the
       morning's numbers sees yesterday's evening folded into them. */
    const push = (ts, entry) => {
      const key = officeDate(new Date(ts));
      if (!out.has(key)) out.set(key, []);
      out.get(key).push(entry);
    };
    for (const t of tasks) {
      push(t.createdAt || Date.now(), { kind: 'task', at: t.createdAt || Date.now(), task: t });
    }
    /* A finished mission used to VANISH from here. The filter was
       `status !== 'running' → skip`, so this view showed the one thing that
       has not happened yet (a projected wrap) and dropped the thing that
       has (a run that actually ended) — in a view whose title is "your
       business by day" and whose job is answering "what did we get done".
       A four-hour research mission could wrap at 3pm and leave no trace on
       the day it wrapped, while the tag above promised "missions when they
       wrap".

       Both now appear, and the distinction is kept rather than blurred:
         · running  → filed at its PROJECTED wrap, labelled "wraps up",
                      which is a forecast and is marked as one.
         · finished → filed at `endedAt`, when it really stopped.

       `endedAt` is new — no terminal transition recorded a time before
       this, which is why the honest version could not be built. For a
       mission that ended before the field existed, fall back to the
       projected wrap; that is exact for the common deadline case and an
       estimate otherwise, and it beats erasing the run. */

    /* Night Shift missions ("close the laptop, work continues") never
       reached this view at all — running or finished — even though the
       tag above draws no line between them and an in-browser research
       mission; both are just "missions" that "wrap." nightShiftBoard
       (currently running, from /missions/scheduled) and nightShiftRuns
       (recently finished, from /missions/runs) are shaped differently
       from `missions` — normalize each into the same fields the loop
       below already expects, then fold them into the exact same pass so
       every rule above (projected wrap vs. real endedAt, the fallback
       for a run that predates a field) applies identically. A run still
       mid-flight can appear in BOTH nightShiftBoard and nightShiftRuns
       (mission-runs.json is written progressively) — its `finishedAt`
       is still 0 there, so `!m.durationMs` below correctly drops the
       not-really-finished duplicate and only the running entry shows. */
    const nightRunning = (nightShiftBoard || []).map(n => ({
      id: n.id, agentId: n.agentId, topic: n.topic, status: 'running',
      startedAt: n.startedAt, durationMs: n.durationMs, intervalMs: n.intervalMs,
    }));
    const nightFinished = (nightShiftRuns || []).map(r => ({
      id: r.id, agentId: r.agentId, topic: r.topic,
      status: (r.errors > 0) ? 'error' : 'done',
      startedAt: r.startedAt,
      durationMs: Math.max(0, (r.finishedAt || 0) - (r.startedAt || 0)),
      endedAt: r.finishedAt, notesWritten: r.writes || [],
    }));
    for (const m of [...missions, ...nightRunning, ...nightFinished]) {
      if (!m || !m.startedAt || !m.durationMs) continue;
      if (m.status === 'running') {
        push(m.startedAt + m.durationMs,
             { kind: 'mission', at: m.startedAt + m.durationMs, mission: m, done: false });
      } else {
        const at = m.endedAt || (m.startedAt + m.durationMs);
        push(at, { kind: 'mission', at, mission: m, done: true });
      }
    }
    return [...out.entries()]
      .map(([day, items]) => [day, items.sort((a, b) => b.at - a.at)])
      .sort((a,b) => b[0].localeCompare(a[0]));
  }, [tasks, missions, nightShiftBoard, nightShiftRuns]);

  const fmt = (k) => {
    const d = new Date(k + 'T12:00:00');
    const today = officeDate();          // local, matching the keys above
    if (k === today) return 'Today';
    return d.toLocaleDateString(undefined, { weekday:'short', month:'short', day:'numeric' });
  };

  return (
    <div className="view-calendar">
      <div className="section-title">
        🗓 CALENDAR
        {/* Was "scheduling coming with stand-up" — a standing IOU for a
            feature that had since shipped elsewhere. Say what the view
            shows now, not what it might one day. */}
        <span className="tag">your business by day · tasks when raised · missions when they wrap</span>
      </div>
      {groups.length === 0 && (
        <div className="empty-state onboard">
          <div className="empty-title">🗓 Nothing on the calendar yet</div>
          <div className="empty-sub">
            Your business by day. Add a task on the <strong>board</strong> (or drop one on
            a coworker's desk in the office) and it lands here — so does a research
            mission, on the day it's due to wrap up.
          </div>
        </div>
      )}
      {groups.map(([day, items]) => (
        <div key={day} className="cal-day">
          <div className="cal-day-head">{fmt(day)}<span className="cal-count">{items.length}</span></div>
          <div className="cal-day-body">
            {items.map(entry => {
              const time = new Date(entry.at).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'});
              if (entry.kind === 'mission') {
                const m = entry.mission;
                const a = agents.find(x => x.id === m.agentId);
                /* Says what the clock actually means for this row — the
                   time is when the run STOPS, not when it was set up.
                   A finished row must not borrow the running row's words:
                   "wraps up" is a forecast, and printing it over a run that
                   ended hours ago is the same tense error as a verdict about
                   a graph with no shape. Past tense, real time, real
                   outcome — including the unhappy ones, which are still
                   business that happened. */
                const notes = (m.notesWritten || []).length;
                const OUT = { done:   ['finished',  'DONE',    'ok'],
                              paused: ['stopped',   'STOPPED', 'warn'],
                              error:  ['ended early', 'FAILED', 'bad'] };
                const [verb, pill, tone] = OUT[m.status] || ['ended', String(m.status || '').toUpperCase(), 'warn'];
                return (
                  <div key={m.id} className={'cal-item cal-mission' + (entry.done ? ' is-done' : '')}>
                    <div className="cal-time">{time}</div>
                    <div className="cal-title">🔬 {m.topic} — {entry.done ? verb : 'wraps up'}</div>
                    <div className="cal-meta">
                      {a ? <><Sprite data={a.color} scale={1}/> {a.name}</> : <span className="muted">{m.agentId}</span>}
                      {entry.done
                        ? <span className="pri">{notes} note{notes === 1 ? '' : 's'} filed</span>
                        : <span className="pri">every {Math.max(1, Math.round((m.intervalMs || 0) / 60000))}m</span>}
                      <span className={'status-pill ' + (entry.done ? tone : 'busy')}>
                        {entry.done ? pill : 'RUNNING'}
                      </span>
                    </div>
                  </div>
                );
              }
              const t = entry.task;
              const a = agents.find(x => x.id === t.assignedTo);
              return (
                <div key={t.id} className={`cal-item status-${t.status}`}>
                  <div className="cal-time">{time}</div>
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
        node.children.set(seg, { name: seg, path: f.path, title: f.title || seg.replace(/\.md$/, ''), mtime: f.mtime, size: f.size, isBinary: !!f.isBinary, isFolder: false });
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

function FolderTree({ files, openPath, onOpen, expanded, setExpanded, onMove = null }) {
  const tree = useMV(() => buildTree(files), [files]);
  /* Drag-to-file: with onMove (the Library's server backends), a file
     row can be dragged onto a folder row — or the tree's empty ground,
     meaning the root. The payload rides a custom type so the Library's
     drop-to-UPLOAD overlay (which listens for real OS 'Files') never
     mistakes an internal move for an upload. */
  const [dragOverF, setDragOverF] = useSV(null);
  /* dataTransfer payloads are unreadable during dragover, so the dragged
     path is mirrored in state — it's how a folder row refuses to claim a
     drop onto itself or its own children while the drag is still in the
     air, instead of erroring after the drop. */
  const [dragSrc, setDragSrc] = useSV(null);
  const _MOVE_T = 'application/x-library-path';
  const dragProps = (path) => onMove ? {
    draggable: true,
    onDragStart: (e) => {
      e.dataTransfer.setData(_MOVE_T, path);
      e.dataTransfer.effectAllowed = 'move';
      setDragSrc(path);
    },
    onDragEnd: () => { setDragSrc(null); setDragOverF(null); },
  } : {};
  const dropProps = (folder) => onMove ? {
    onDragOver: (e) => {
      if (![...(e.dataTransfer.types || [])].includes(_MOVE_T)) return;
      if (dragSrc && (folder + '/').startsWith(dragSrc + '/')) return;
      e.preventDefault();
      e.stopPropagation();
      e.dataTransfer.dropEffect = 'move';
      if (dragOverF !== folder) setDragOverF(folder);
    },
    onDragLeave: () => { if (dragOverF === folder) setDragOverF(null); },
    onDrop: (e) => {
      const src = e.dataTransfer.getData(_MOVE_T);
      if (!src) return;
      // a folder dropped on itself/its children falls through to the
      // ground below — whose claim is the highlight the boss was shown
      if ((folder + '/').startsWith(src + '/')) return;
      e.preventDefault();
      e.stopPropagation();
      setDragOverF(null);
      onMove(src, folder);
    },
  } : {};
  const toggle = (path) => setExpanded(prev => {
    const next = new Set(prev);
    if (next.has(path)) next.delete(path); else next.add(path);
    return next;
  });
  /* Rows are divs with onClick, which a keyboard can't reach — Enter/Space
     activate them the way a click does, and the tree/treeitem roles let a
     screen reader announce folders as expandable instead of as bare text. */
  const rowKeys = (fn) => (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(); }
  };
  const renderNode = (n, depth) => {
    if (n.isFolder) {
      const isOpen = expanded.has(n.path);
      return (
        <div key={n.path}>
          <div className={`tree-row tree-folder ${isOpen?'open':''}`}
            style={{paddingLeft: 6 + depth * 14,
                    ...(dragOverF === n.path ? {outline: '2px dashed var(--accent-sun, #7c6bff)', outlineOffset: -2} : {})}}
            role="treeitem" aria-expanded={isOpen} tabIndex={0}
            {...dropProps(n.path)}
            {...dragProps(n.path)}
            onClick={()=>toggle(n.path)} onKeyDown={rowKeys(()=>toggle(n.path))}>
            <span className="tree-chev" aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
            <span className="tree-icon" aria-hidden="true">{isOpen ? '📂' : '📁'}</span>
            <span className="tree-name">{n.name}</span>
          </div>
          {isOpen && n.children.map(c => renderNode(c, depth + 1))}
        </div>
      );
    }
    const isBase = /\.base$/i.test(n.name);
    /* A deck sitting between two notes should look like a deck. Every row
       used to render as bare text with only `.md` stripped, so `slides.pptx`
       and `slides` — a real note of that name — were one glyph apart in a
       tree the boss scans by shape. The extension moves into the tag the
       BASE chip already uses, so the name stays readable and the KIND is the
       thing that stands out. Only for files the editor can't open: a `.md`
       carries no tag, because the tree is mostly notes and a chip on every
       row is a chip on none. */
    const binExt = n.isBinary ? (n.name.match(/\.([A-Za-z0-9]+)$/) || [])[1] : null;
    const display = binExt ? n.name.slice(0, -(binExt.length + 1)) : n.name.replace(/\.md$/i, '');
    return (
      <div key={n.path}
        className={`tree-row tree-file ${openPath === n.path ? 'active' : ''}`}
        style={{paddingLeft: 6 + depth * 14 + 14}}
        role="treeitem" aria-current={openPath === n.path || undefined} tabIndex={0}
        {...dragProps(n.path)}
        onClick={()=>onOpen(n.path)} onKeyDown={rowKeys(()=>onOpen(n.path))}>
        <span className="tree-name">{display}</span>
        {isBase && <span className="tree-tag">BASE</span>}
        {binExt && !isBase && <span className="tree-tag">{binExt.toUpperCase()}</span>}
      </div>
    );
  };
  return (
    <div className="tree-root" role="tree" aria-label="Library files"
      style={dragOverF === '' ? {outline: '2px dashed var(--accent-sun, #7c6bff)', outlineOffset: -2} : undefined}
      {...dropProps('')}>
      {tree.map(c => renderNode(c, 0))}
    </div>
  );
}

/* ---------------- Obsidian Vault — unified Vault + Graph tab ---------------- */

export { CalendarView, FolderTree, MemoryPage, TasksView, TeamView, VIEW_LABELS, hexToRgb, useStoredV };
