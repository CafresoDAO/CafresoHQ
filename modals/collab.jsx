import { CafresoHQChain } from '../claude-client.jsx';
import { HQ } from '../hq-runtime.jsx';
import { Modal } from './base.jsx';
const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;
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

  /* A task already claimed by another workflow (t.workflowId) has its
     chainTo/dependsOn pointing at THAT workflow's neighbors — adding it
     to a second one here would silently overwrite those links with no
     warning, breaking the first workflow without ever saying so. */
  const inboxTasks = tasks.filter(t => t.status !== 'done' && !t.workflowId && !steps.includes(t.id));
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
          {/* `workflows` was passed into this modal since it was built but
             never read — creating one worked, then it vanished: no list,
             no badge anywhere, no way to check on it again. The nav chip
             now shows a count (matching MEETING/RESEARCH); this is the
             other half — where the boss actually SEES what they built. */}
          {workflows.length > 0 && (
            <div className="cb-panel" style={{marginBottom: 12}}>
              <h4>YOUR WORKFLOWS ({workflows.length})</h4>
              <div className="stack">
                {workflows.map(wf => {
                  const stepTasks = wf.steps.map(id => tasks.find(t => t.id === id));
                  const known = stepTasks.filter(Boolean);
                  const done = known.filter(t => t.status === 'done').length;
                  const doing = known.filter(t => t.status === 'doing').length;
                  const missing = stepTasks.length - known.length;
                  const bits = [`${done}/${stepTasks.length} done`];
                  if (doing) bits.push(`${doing} in progress`);
                  if (missing) bits.push(`${missing} removed`);
                  return (
                    <div key={wf.id} className="row" style={{padding:'4px 6px'}}>
                      <span className="grow tiny">{wf.name}</span>
                      <span className="sub">{bits.join(' · ')}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
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
  /* The task this room was raised from, if any. Held until create() so the
     task moves to `doing` when the room really opens — opening a modal the
     boss can still cancel is not work starting. */
  const [srcTaskId, setSrcTaskId] = useStateM(null);
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
        setSrcTaskId(pre.taskId || null);
        try { delete window._cafresohqMeetingPrefill; } catch (_) { window._cafresohqMeetingPrefill = null; }
        return;
      }
      setSrcTaskId(null);
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
    if (srcTaskId && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('cafresohq:taskMeetingStarted', { detail: srcTaskId }));
    }
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
          {/* §6. Was "(optional — included in opening prompt context)":
              two banned words in five, on a modal a first-run boss reaches
              from the Tools drawer. It also described the plumbing rather
              than the effect — what a boss wants to know is who sees it
              and when, not which part of the machinery it is folded into. */}
          Topic <span style={{opacity:0.5,fontSize:9,marginLeft:4}}>(optional — everyone in the room sees this when it opens)</span>
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
                No coworkers hired. Hire someone on the Team tab first.
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
/* The states that need no action from the boss. Anything else is still
   counted in the topbar badge, so anything else gets a way to clear it. */
const TERMINAL_STATES = new Set(['completed', 'cancelled', 'failed']);

function InboxModal({ open, onClose, onResend = null }) {
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
          <span style={{opacity:0.7}}>{m.fromAgentName || 'A coworker'}</span>
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
      {/* The door the box above keeps naming. A retryable cause files
          actionNeeded "Re-send it…" — and this row rendered that sentence
          with no way to do it: the palette's retry only saw 'failed' (and
          only the most recent), so a 'stopped-all' cancellation was told
          to re-send with nowhere to press. Gated exactly as the label is:
          terminal (an in-flight row has nothing to re-send yet) and
          retryable (the box honestly says 'not retryable' otherwise). */}
      {onResend && TERMINAL_STATES.has(m.state) && m.failureCause && m.failureCause.retryable && (
        <div style={{marginTop:6}}>
          <button
            className="px-btn secondary"
            style={{fontSize:8, padding:'3px 6px'}}
            title="Send this message to the same coworker again. This record stays as history — the retry files its own record, chained to this one."
            onClick={(e) => {
              e.stopPropagation();
              onResend(m);
            }}
          >↻ RE-SEND</button>
        </div>
      )}
      {/* The boss's own lever. The registry counts non-terminal messages
          into the topbar badge, and until now nothing in this modal could
          resolve, dismiss or close one — the boss could watch the number
          and not touch it. Live example, still on screen when this was
          added: a Nova → Llama ask stranded at AWAITING REPLY by a race
          since fixed, with no way to clear it.

          Deliberately the BOSS's action and labelled as one. The office
          closing a wait on its own is only honest when the awaited thing
          actually happened (see the fan-out closer in app.jsx); this is
          the other case — the boss deciding they have dealt with it. The
          history keeps who did it, so the record never claims a coworker
          finished something they did not. */}
      {!TERMINAL_STATES.has(m.state) && (
        <div style={{marginTop:6}}>
          <button
            className="px-btn secondary"
            style={{fontSize:8, padding:'3px 6px'}}
            title="Close this off in your inbox. It does not stop or change anything the coworker is doing."
            onClick={(e) => {
              e.stopPropagation();
              reg.transition(m.id, 'completed', { by: 'you', note: 'closed by you' });
              setTick(v => v + 1);
            }}
          >✓ CLEAR THIS</button>
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
          {agentList.map(a => <option key={a} value={a}>{a === 'all' ? 'everyone' : a}</option>)}
        </select>
      </div>
      {visibleThreads.length === 0 ? (
        <div className="empty-state">
          <div className="empty-title">No messages match this filter.</div>
          <div className="empty-sub">Try widening the state filter, or @-mention a coworker to start a thread.</div>
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
                  {/* A thread is listed when ANY message matches the filter,
                      but the pill shows the LAST message's state — so under
                      "ACTIVE · 8" the one visible row read COMPLETED, because
                      the thread had finished while eight replies inside it sit
                      awaiting_reply. The view that exists to explain the badge
                      opened on a word contradicting it.

                      When a filter is on, say how many messages in HERE
                      matched. The tail pill stays: it is the honest answer to
                      "where did this thread get to". */}
                  {filterState !== 'all' && (() => {
                    const hits = msgs.filter(m => matchesState(m) && matchesAgent(m)).length;
                    return hits ? (
                      <span style={{fontSize:9,opacity:0.75,border:'1px solid var(--rule)',
                                    borderRadius:3,padding:'1px 5px',marginRight:6}}
                            title={`${hits} message${hits === 1 ? '' : 's'} in this thread match the current filter`}>
                        {hits} here
                      </span>
                    ) : null;
                  })()}
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

/* ── Furnish Shop — desk decor bought with REAL gold (sGLDT). ─────────────
   Safety model: this modal never moves money itself. Every purchase goes
   through chain.shop.furnish → the II-holding shell shows its approval
   sheet, and only a user-signed ICRC-1 transfer to the DAO treasury
   completes the sale. Declining costs nothing and changes nothing.
   Cosmetic-only by design: no stats, no gameplay advantage, no bundles. */
const FURNISH_CATALOG = [
  { kind: 'wall', id: 'mini-window',  icon: '🪟', label: 'City window',   price: 0.05, note: 'a view of the skyline' },
  { kind: 'wall', id: 'wall-shelf',   icon: '📚', label: 'Wall shelf',    price: 0.03, note: 'books they never read' },
  { kind: 'wall', id: 'poster',       icon: '🖼', label: 'Motivation poster', price: 0.02, note: 'HANG IN THERE' },
  { kind: 'wall', id: 'poster p1',    icon: '🎨', label: 'Art print',     price: 0.02, note: 'gallery-grade pixels' },
  { kind: 'wall', id: 'pin-note',     icon: '📌', label: 'Pin board',     price: 0.01, note: 'for very important notes' },
  { kind: 'rug',  id: 0,              icon: '🟥', label: 'Crimson rug',   price: 0.02, note: 'ties the desk together' },
  { kind: 'rug',  id: 1,              icon: '🟦', label: 'Indigo rug',    price: 0.02, note: 'calm under pressure' },
  { kind: 'rug',  id: 2,              icon: '🟩', label: 'Fern rug',      price: 0.02, note: 'the plant approves' },
];

function FurnishModal({ agent, onClose, onUpdate }) {
  const chain = (typeof window !== 'undefined' && CafresoHQChain) || null;
  const canBuy = !!(chain && chain.isAvailable && chain.isAvailable() && chain.shop);
  const [busyId, setBusyId] = useStateM(null);
  const [note, setNote] = useStateM('');

  if (!agent) return null;
  const owned = (agent.furnishLog || []).map(f => `${f.kind}:${f.id}`);
  const current = agent.decor || {};

  const buy = async (item) => {
    if (!canBuy || busyId) return;
    const key = `${item.kind}:${item.id}`;
    const alreadyOwned = owned.includes(key);
    /* Owned items re-place for free; new items go through the signed sale. */
    if (!alreadyOwned) {
      setBusyId(key); setNote('Waiting for your approval in the shell…');
      try {
        const res = await chain.shop.furnish({
          agentId: agent.id, kind: item.kind, itemId: String(item.id),
          label: item.label, priceGold: item.price,
        });
        if (!res || res.status !== 'paid') {
          setNote(res && res.status === 'declined' ? 'Declined — nothing was spent.' : (res && res.error) || 'Purchase didn’t complete — nothing was spent.');
          setBusyId(null);
          return;
        }
        setNote(`Paid ${item.price} sGLDT · ledger block #${res.block}`);
        try {
          window.dispatchEvent(new CustomEvent('cafresohq:moneyEvent', {
            detail: { agentId: agent.id, amount: item.price, amountRaw: String(Math.round(item.price * 1e8)), token: 'sGLDT', kind: 'furnish' },
          }));
        } catch (_e) {}
        onUpdate(agent.id, {
          furnishLog: [ ...(agent.furnishLog || []), { kind: item.kind, id: item.id, label: item.label, price: item.price, block: res.block, at: Date.now() } ],
        });
      } catch (e) {
        setNote(`Couldn’t reach the shell (${(e && e.message) || 'timeout'}) — nothing was spent.`);
        setBusyId(null);
        return;
      }
      setBusyId(null);
    }
    // Place it (new or already-owned): cosmetic state on the agent record.
    onUpdate(agent.id, {
      decor: item.kind === 'wall'
        ? { ...current, wall: item.id }
        : { ...current, rug: item.id },
    });
  };

  return (
    <Modal open={!!agent} onClose={onClose} size="md"
      title="FURNISH SHOP"
      subtitle={`${agent.name}'s desk · paid in gold (sGLDT) · cosmetic only`}>
      {!canBuy && (
        <div style={{ fontFamily: 'Inter', fontSize: 11.5, lineHeight: 1.5, padding: '8px 10px', marginBottom: 10,
                      border: '1px dashed var(--rule)', borderRadius: 6, opacity: 0.8 }}>
          Browsing only — open HQ from ai.cafreso.com (signed in, wallet service on) to buy with gold.
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 8 }}>
        {FURNISH_CATALOG.map((item) => {
          const key = `${item.kind}:${item.id}`;
          const isOwned = owned.includes(key);
          const isPlaced = item.kind === 'wall' ? current.wall === item.id : current.rug === item.id;
          return (
            <div key={key} style={{ border: '2px solid var(--ink)', borderRadius: 6, padding: '10px 10px 8px',
                                    background: isPlaced ? 'rgba(245,210,93,0.18)' : 'var(--paper-2)' }}>
              <div style={{ fontSize: 18, lineHeight: 1 }}>{item.icon}</div>
              <div style={{ fontFamily: 'Press Start 2P', fontSize: 8, margin: '6px 0 2px' }}>{item.label}</div>
              <div style={{ fontFamily: 'Inter', fontSize: 10, opacity: 0.65, minHeight: 24 }}>{item.note}</div>
              <button className="px-btn" style={{ width: '100%', fontSize: 8, marginTop: 6 }}
                disabled={!!busyId || isPlaced || (!canBuy && !isOwned)}
                onClick={() => buy(item)}>
                {isPlaced ? '✓ PLACED'
                  : isOwned ? 'PLACE'
                  : busyId === key ? 'ASKING…'
                  : `◈ ${item.price} sGLDT`}
              </button>
            </div>
          );
        })}
      </div>
      {note && (
        <div style={{ fontFamily: 'VT323, monospace', fontSize: 13, marginTop: 10, opacity: 0.85 }}>{note}</div>
      )}
      <div style={{ fontFamily: 'Inter', fontSize: 10, marginTop: 10, opacity: 0.55, lineHeight: 1.5 }}>
        Every purchase is a real, user-signed sGLDT transfer to the Cafreso DAO treasury — the shell always asks first,
        and declining costs nothing. Items are cosmetic and stay owned by this coworker.
      </div>
    </Modal>
  );
}


export { FurnishModal, InboxModal, MeetingRoomModal, WorkflowModal };
