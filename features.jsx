/* ==========================================================================
   CafresoHQ — features v2
   Tasks board, memory shelf, meeting room, focus mode, approval stamps
   ========================================================================== */

const { useState: useSF, useEffect: useEF, useRef: useRF, useMemo: useMF } = React;

/* Pulled from CafresoHQModals so the modals defined in this file can use the
   shared <Modal> shell (focus trap, scroll lock, animated entry). */
const { Modal: OcModal } = window.CafresoHQModals;

/* ---------------- Seed data ----------------
   Empty in production: fake demo tasks/memories used to be written into every
   new account's persisted state (and survived deletion). Empty states in the
   views teach the features instead. */
const SEED_TASKS = [];

const SEED_MEMORY = [];

/* ---------------- Task Board ---------------- */
/* Inline assignee picker for task cards. Renders as a styled native
   <select> so it's accessible + tab-friendly without writing custom
   focus-trap / click-outside logic. Shows the current assignee with a
   colored sprite swatch, an "Unassign" option, and one entry per hired
   agent. Falls back to a static "(no agents)" hint when the team is
   empty so the user knows hiring is the next step. */
function AssigneeSelect({ value, agents, onChange, compact = false }) {
  const a = agents.find(x => x.id === value) || null;
  const swatch = a ? (
    <span style={{display:'inline-block',width:8,height:8,borderRadius:'50%',
      background: a.color && a.color.body ? a.color.body
                 : a.color && a.color.shirt ? a.color.shirt
                 : (typeof a.color === 'string' ? '' : '#7db5b5'),
      verticalAlign:'middle',marginRight:4}}/>
  ) : null;
  return (
    <span style={{display:'inline-flex',alignItems:'center',gap:4,
      padding:'1px 4px',border:'1px solid var(--ink)',borderRadius:4,
      background: a ? 'var(--paper-2,#f0e9d8)' : 'transparent',
      cursor:'pointer'}}
      onClick={(e) => e.stopPropagation()}>
      {swatch}
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value || null)}
        style={{
          appearance:'none',border:0,background:'transparent',
          fontFamily:'VT323',fontSize: compact ? 11 : 13,
          color:'var(--ink)',cursor:'pointer',padding:'1px 14px 1px 0',
          maxWidth: compact ? 92 : 140,
        }}
      >
        <option value="">{a ? 'Unassign…' : 'Assign…'}</option>
        {agents.length === 0 && <option disabled>(no agents hired)</option>}
        {agents.map(opt => (
          <option key={opt.id} value={opt.id}>
            {opt.name}{opt.role ? ' · ' + opt.role : ''}
            {opt.assistant ? ' (asst)' : opt.transient ? ' (sub)' : ''}
          </option>
        ))}
      </select>
    </span>
  );
}

function TaskBoard({ tasks, agents, onAssign, onAdd, onMove, onDelete, onDragStart, onAssignToChat, onMakeRoomFromTask }) {
  const [adding, setAdding] = useSF(false);
  const [title, setTitle] = useSF('');
  const [expanded, setExpanded] = useSF({});
  const cols = [
    ['inbox', 'INBOX'],
    ['doing', 'DOING'],
    ['done',  'DONE'],
  ];

  const submit = () => {
    if (!title.trim()) return;
    onAdd({ id: 'tk_' + Math.random().toString(36).slice(2,7), title: title.trim(), detail: '', assignedTo: null, status: 'inbox', priority: 'med', createdAt: Date.now() });
    setTitle(''); setAdding(false);
  };

  return (
    <div className="task-board">
      <div className="clipboard-head">
        <div className="clip"/>
        <div className="title">TASK BOARD</div>
        <button className="px-btn secondary" style={{fontSize:8,padding:'6px 8px'}} onClick={()=>setAdding(a=>!a)}>+ NEW</button>
      </div>
      {adding && (
        <div style={{padding:8,display:'flex',gap:6,borderBottom:'2px solid var(--ink)'}}>
          <input autoFocus value={title} onChange={e=>setTitle(e.target.value)} onKeyDown={e=>e.key==='Enter'&&submit()}
            placeholder="New task…" style={{flex:1,border:'2px solid var(--ink)',padding:'6px 8px',fontFamily:'VT323',fontSize:17}}/>
          <button className="px-btn primary" style={{fontSize:8}} onClick={submit}>ADD</button>
        </div>
      )}
      <div className="tb-cols">
        {cols.map(([key, label]) => (
          <div key={key} className="tb-col"
            onDragOver={e=>e.preventDefault()}
            onDrop={e=>{ const id=e.dataTransfer.getData('task'); if(id) onMove(id, key); }}>
            <div className="tb-col-head">{label} · {tasks.filter(t=>t.status===key).length}</div>
            <div className="tb-col-body">
              {tasks.filter(t=>t.status===key).map(t => {
                const a = agents.find(x=>x.id===t.assignedTo);
                return (
                  <div key={t.id} className={`task-card pri-${t.priority}${expanded[t.id] ? ' expanded' : ''}`}
                       draggable
                       onDragStart={e=>{ e.dataTransfer.setData('task', t.id); onDragStart && onDragStart(t); }}
                       onClick={()=>setExpanded(prev=>({...prev, [t.id]: !prev[t.id]}))}>
                    {onDelete && (
                      <button className="tc-delete" title="Delete task"
                        onClick={(e)=>{ e.stopPropagation(); onDelete(t.id); }}>✕</button>
                    )}
                    <div className="tc-title">{t.title}</div>
                    {t.detail && <div className="tc-detail">{t.detail}</div>}
                    <div className="tc-foot">
                      {/* Inline assignee picker — tap to reassign without
                          having to drag-and-drop or open a modal. Falls back
                          to the legacy display when no `onAssign` was passed
                          in (older callers / read-only contexts). */}
                      {onAssign ? (
                        <AssigneeSelect
                          value={t.assignedTo}
                          agents={agents}
                          onChange={(newId) => onAssign(t.id, newId)}
                          compact
                        />
                      ) : a ? (
                        <span className="tc-assigned"><Sprite data={a.color} scale={1}/> {a.name}</span>
                      ) : (
                        <span className="tc-unassigned">{onAssignToChat ? 'unassigned · use → CHAT' : '↕ drag to a desk'}</span>
                      )}
                      <span className={`pri pri-${t.priority}`}>{t.priority.toUpperCase()}</span>
                    </div>
                    {/* New chat-bridge actions: → CHAT fans the task out as
                        an @mention in the DIRECT thread; 📋 ROOM opens
                        the meeting-create modal pre-populated with the
                        task title + topic. Both move the task to DOING. */}
                    {(onAssignToChat || onMakeRoomFromTask) && t.status !== 'done' && (
                      <div className="tc-actions">
                        {onAssignToChat && (
                          <button
                            className="tc-action-btn"
                            title={a ? `Send to @${a.name} in chat` : 'Send to chat (CEO will route)'}
                            onClick={(e) => { e.stopPropagation(); onAssignToChat(t); }}
                          >→ CHAT</button>
                        )}
                        {onMakeRoomFromTask && (
                          <button
                            className="tc-action-btn"
                            title="Open a meeting room with this task as the topic"
                            onClick={(e) => { e.stopPropagation(); onMakeRoomFromTask(t); }}
                          >📋 ROOM</button>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
              {tasks.filter(t=>t.status===key).length === 0 && (
                key === 'inbox'
                  ? <div className="tb-empty onboard">No tasks yet.<br/>Hit <strong>+ NEW</strong> above, then drag a card onto an agent's desk to delegate.</div>
                  : <div className="tb-empty">—</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- Memory Shelf (opens filing cabinet) ---------------- */
function MemoryShelf({ open, onClose, memory, onAdd, onRemove }) {
  const [text, setText] = useSF('');
  const [tag, setTag] = useSF('NOTE');
  if (!open) return null;
  const submit = () => {
    if (!text.trim()) return;
    onAdd({ id: 'mem_'+Math.random().toString(36).slice(2,6), tag, text: text.trim(), date: 'Today' });
    setText('');
  };
  return (
    <OcModal
      open={open}
      onClose={onClose}
      title="📁 MEMORY SHELF"
      subtitle="What CafresoHQ remembers about you"
      size="lg"
    >
      <div className="memshelf">
        {memory.map(m => (
          <div key={m.id} className="memrow">
            <span className={`memtag tag-${m.tag.toLowerCase()}`}>{m.tag}</span>
            <div className="memtext">{m.text}</div>
            <div className="memdate">{m.date}</div>
            <button className="px-btn ghost" style={{fontSize: 'var(--text-9)', padding: 'var(--sp-2) var(--sp-3)'}} onClick={()=>onRemove(m.id)}>✕</button>
          </div>
        ))}
      </div>
      <div style={{display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-5)'}}>
        <select value={tag} onChange={e=>setTag(e.target.value)} style={{border:'2px solid var(--ink)', padding: 'var(--sp-3) var(--sp-4)', fontFamily:'VT323', fontSize: 16}}>
          {['NOTE','PREF','PROJECT','PEOPLE','RULE','TONE'].map(t => <option key={t}>{t}</option>)}
        </select>
        <input value={text} onChange={e=>setText(e.target.value)} placeholder="New memory…" onKeyDown={e=>e.key==='Enter'&&submit()}
          style={{flex:1, border:'2px solid var(--ink)', padding: 'var(--sp-3) var(--sp-4)', fontFamily:'VT323', fontSize: 17}}/>
        <button className="px-btn primary" style={{fontSize: 'var(--text-9)'}} onClick={submit}>REMEMBER</button>
      </div>
    </OcModal>
  );
}

/* ---------------- Meeting Room ---------------- */
function MeetingRoom({ participants, agents, onClose, onRemove }) {
  const [msgs, setMsgs] = useSF([]);
  const [input, setInput] = useSF('');
  const [streaming, setStreaming] = useSF(false);
  const logRef = useRF(null);
  useEF(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [msgs]);

  const newId = () => 'mtg_' + Math.random().toString(36).slice(2, 8);

  const abortRef = useRF(null);
  const stop = () => { if (abortRef.current) abortRef.current.abort(); };

  const moderate = async () => {
    if (!input.trim() || streaming) return;
    const you = input.trim();
    setInput('');
    setStreaming(true);

    const youMsg = { id: newId(), who: 'You', color: null, text: you };
    const transcript = msgs.map(m => `${m.who}: ${m.text}`).join('\n') + `\nYou: ${you}`;
    const placeholders = participants.map(a => ({
      id: newId(), who: a.name, color: a.color, text: '', streaming: true, agentRef: a,
    }));
    const ceoPlaceholder = { id: newId(), who: 'CafresoHQ', color: 'cafresohq', text: '', streaming: true };
    setMsgs(m => [...m, youMsg, ...placeholders, ceoPlaceholder]);

    const updateById = (id, patch) =>
      setMsgs(m => m.map(x => x.id === id ? { ...x, ...patch } : x));

    const controller = new AbortController();
    abortRef.current = controller;

    /* Local rAF throttle — same idea as HQ.throttleTokens but the meeting
       view writes via updateById(text=buf) rather than appending, so we
       just gate the update calls themselves to once per frame. */
    const makeRafGate = (id) => {
      let scheduled = false;
      let latest = '';
      return (text) => {
        latest = text;
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => { scheduled = false; updateById(id, { text: latest }); });
      };
    };

    for (const ph of placeholders) {
      let buf = '';
      const update = makeRafGate(ph.id);
      try {
        await window.HQ.agentStream(
          ph.agentRef,
          `Meeting transcript so far:\n${transcript}\n\nRespond briefly (1-2 sentences) from your role's perspective.`,
          tok => { buf += tok; update(buf); },
          { signal: controller.signal }
        );
        updateById(ph.id, { text: buf });  // final flush
      } catch (err) {
        const stopped = err.name === 'AbortError';
        updateById(ph.id, { text: stopped ? (buf + ' …(stopped)') : `⚠ ${err.message}`, error: !stopped });
        if (stopped) break;
      } finally {
        updateById(ph.id, { streaming: false });
      }
    }

    let buf = '';
    if (!controller.signal.aborted) {
      const update = makeRafGate(ceoPlaceholder.id);
      try {
        await window.HQ.ceoStream(
          `You are moderating a team meeting. Transcript:\n${transcript}\n\nSynthesize the discussion in 1-2 sentences and state the next action.`,
          tok => { buf += tok; update(buf); },
          { agents: participants, signal: controller.signal }
        );
        updateById(ceoPlaceholder.id, { text: buf });
      } catch (err) {
        const stopped = err.name === 'AbortError';
        updateById(ceoPlaceholder.id, { text: stopped ? (buf + ' …(stopped)') : `⚠ ${err.message}`, error: !stopped });
      }
    }
    updateById(ceoPlaceholder.id, { streaming: false });
    abortRef.current = null;
    setStreaming(false);
  };

  return (
    <OcModal
      open={true}
      onClose={onClose}
      title="🪑 MEETING ROOM"
      subtitle={`${participants.length + 1} in the room · CafresoHQ moderating`}
      size="xl"
    >
      <div style={{margin: 'calc(-1 * var(--sp-6))'}}>
        <div className="meeting-table">
          <div className="seat seat-head">
            <Sprite data="cafresohq" scale={2}/>
            <div className="seat-name">CafresoHQ</div>
            <div className="seat-role">Moderator</div>
          </div>
          {participants.map(p => (
            <div key={p.id} className="seat">
              <button className="seat-remove" onClick={()=>onRemove(p.id)} title="Excuse from meeting">✕</button>
              <Sprite data={p.color} scale={2}/>
              <div className="seat-name">{p.name}</div>
              <div className="seat-role">{p.role}</div>
            </div>
          ))}
        </div>
        <div className="meeting-log" ref={logRef}>
          {msgs.map(m => (
            <div key={m.id} className={`mtg-msg ${m.who==='You'?'you':''}`}>
              {m.color && <Sprite data={m.color} scale={1}/>}
              <div className="mtg-bubble">
                <div className="mtg-who">{m.who}</div>
                <div>{m.text}{m.streaming ? <span className="typing"><span/><span/><span/></span> : null}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="composer" style={{borderTop:'2px solid var(--ink)'}}>
          <textarea placeholder="Moderate the meeting…" value={input} onChange={e=>setInput(e.target.value)}
            onKeyDown={e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();moderate();} }}/>
          {streaming
            ? <button className="px-btn danger" onClick={stop}>■ STOP</button>
            : <button className="px-btn primary" onClick={moderate}>SEND</button>}
        </div>
      </div>
    </OcModal>
  );
}

/* ---------------- 1:1 Focus mode ---------------- */
function FocusMode({ active, onClose, chat, setChat }) {
  const [input, setInput] = useSF('');
  const [streaming, setStreaming] = useSF(false);
  const ref = useRF(null);
  const abortRef = useRF(null);
  useEF(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [chat]);
  if (!active) return null;
  const stop = () => { if (abortRef.current) abortRef.current.abort(); };
  const send = async () => {
    const text = input.trim(); if (!text || streaming) return;
    setInput('');
    const userMsg = { id: 'm_'+Math.random().toString(36).slice(2,7), from:'user', name:'You', text };
    const pending = [...chat, userMsg];
    setChat(pending);
    setStreaming(true);
    const ceoId = 'm_'+Math.random().toString(36).slice(2,7);
    setChat(p => [...p, { id: ceoId, from:'ceo', name:'CafresoHQ', text:'', streaming:true }]);
    const controller = new AbortController();
    abortRef.current = controller;
    const flush = HQ.throttleTokens(setChat, ceoId);
    try {
      await HQ.ceoStream(text, flush,
        { chat: pending, signal: controller.signal, onHint: flush.note });
      flush.flushNow();
    } catch (err) {
      const stopped = err.name === 'AbortError';
      setChat(p => p.map(m => m.id===ceoId
        ? {...m, text: stopped ? (m.text + ' …(stopped)') : `⚠ ${err.message}`, error: !stopped}
        : m));
    }
    abortRef.current = null;
    setChat(p => p.map(m => m.id===ceoId?{...m,streaming:false}:m));
    setStreaming(false);
  };
  return (
    <div className="focus-overlay">
      <div className="focus-head">
        <Sprite data="cafresohq" scale={3}/>
        <div>
          <div className="focus-title">1:1 WITH CAFRESOHQ</div>
          <div className="focus-sub">quiet room · no distractions</div>
        </div>
        <button className="px-btn secondary" onClick={onClose}>LEAVE ROOM ✕</button>
      </div>
      <div className="focus-chat" ref={ref}>
        {chat.slice(-12).map(m => (
          <div key={m.id} className={`msg ${m.from}`}>
            <div className="who">
              {m.from === 'user'
                ? <div style={{width:22,height:22,background:'var(--accent-sun)',border:'2px solid var(--ink)',display:'grid',placeItems:'center',fontFamily:'Press Start 2P',fontSize:10}}>B</div>
                : <Sprite data="cafresohq" scale={1}/>}
            </div>
            <div className="bubble" style={{maxWidth: '70%'}}>
              <div className="name">{m.name}</div>
              <p>{m.text}{m.streaming ? <span className="typing"><span/><span/><span/></span>:null}</p>
            </div>
          </div>
        ))}
      </div>
      <div className="focus-composer">
        <textarea placeholder="Say anything…" value={input} onChange={e=>setInput(e.target.value)}
          onKeyDown={e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();} }}/>
        {streaming
          ? <button className="px-btn danger" onClick={stop}>■ STOP</button>
          : <button className="px-btn primary" onClick={send}>SEND</button>}
      </div>
    </div>
  );
}

/* ---------------- End-of-day stand-up ---------------- */
const STANDUP_PROMPT = `Give a one-line stand-up. Format EXACTLY (each on its own line, ~80 chars max):
TODAY: <what you worked on or accomplished>
BLOCKED: <what's in your way, or "nothing">
TOMORROW: <what you'll pick up next>
Stop after the TOMORROW line. No reasoning, no commentary, no preamble.`;

/* Tight budgets so a stand-up can't run away on a big local model.
   220 tokens fits 3 lines × ~80 chars with slack; 90s is enough for
   a cold-load on most local models, short enough not to hang a VM. */
const STANDUP_MAX_TOKENS = 220;
const STANDUP_TIMEOUT_MS = 90_000;

function StandupModal({ open, onClose, agents, onArchive }) {
  const [reports, setReports] = useSF([]);   // [{agentId, name, color, text, streaming, error}]
  const [summary, setSummary] = useSF('');
  const [phase, setPhase] = useSF('idle');   // idle | running | summarizing | done
  const [archived, setArchived] = useSF(false);
  const [excluded, setExcluded] = useSF(new Set());
  const abortRef = useRF(null);

  if (!open) return null;

  const participating = agents.filter(a => !excluded.has(a.id));
  const isLocal = (a) => /^(lmstudio|ollama):/.test(a.model || '');
  const localCount = participating.filter(isLocal).length;

  const start = async () => {
    if (phase === 'running' || phase === 'summarizing') return;
    if (participating.length === 0) return;
    setArchived(false);
    setSummary('');
    setReports(participating.map(a => ({ agentId: a.id, name: a.name, color: a.color, role: a.role, text: '', streaming: true, error: false })));
    setPhase('running');
    const controller = new AbortController();
    abortRef.current = controller;

    const finished = [];
    /* rAF gate to batch setReports per-frame — same reason as the chat panel:
       per-token state churn pegs CPU when reports list grows. */
    const makeReportGate = (agentId) => {
      let scheduled = false;
      let latest = '';
      return (text) => {
        latest = text;
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => { scheduled = false;
          setReports(prev => prev.map(r => r.agentId === agentId ? { ...r, text: latest } : r));
        });
      };
    };
    for (const a of participating) {
      let buf = '';
      const updateReport = makeReportGate(a.id);
      // Per-agent timeout so a stuck local model can't lock the whole stand-up.
      const perAgent = new AbortController();
      const onParentAbort = () => perAgent.abort();
      controller.signal.addEventListener('abort', onParentAbort);
      const timeoutId = setTimeout(() => perAgent.abort(), STANDUP_TIMEOUT_MS);
      try {
        await window.HQ.agentStream(a, STANDUP_PROMPT,
          tok => { buf += tok; updateReport(buf); },
          { signal: perAgent.signal, maxTokens: STANDUP_MAX_TOKENS }
        );
        // Final non-throttled flush so the displayed text matches buf exactly.
        setReports(prev => prev.map(r => r.agentId === a.id ? { ...r, text: buf } : r));
        setReports(prev => prev.map(r => r.agentId === a.id ? { ...r, streaming: false } : r));
        finished.push({ name: a.name, role: a.role, text: buf });
      } catch (err) {
        const userStopped = controller.signal.aborted;
        const timedOut = !userStopped && perAgent.signal.aborted;
        const label = userStopped ? '…(stopped)' : timedOut ? '…(timed out — model too slow or unloaded)' : null;
        setReports(prev => prev.map(r => r.agentId === a.id
          ? { ...r, streaming: false, error: !label, text: label ? (buf + ' ' + label) : `⚠ ${err.message}` }
          : r));
        if (userStopped) { clearTimeout(timeoutId); controller.signal.removeEventListener('abort', onParentAbort); setPhase('idle'); abortRef.current = null; return; }
        // Skip to next agent on per-agent timeout instead of hanging.
      } finally {
        clearTimeout(timeoutId);
        controller.signal.removeEventListener('abort', onParentAbort);
      }
    }

    setPhase('summarizing');
    let buf = '';
    const transcript = finished.map(f => `${f.name} (${f.role}):\n${f.text}`).join('\n\n');
    const sumTimeout = setTimeout(() => controller.abort(), STANDUP_TIMEOUT_MS);
    try {
      await window.HQ.ceoStream(
        `End-of-day stand-up reports:\n\n${transcript}\n\nSynthesize this in 2 sentences and call out the single most important next action for the boss.`,
        tok => { buf += tok; setSummary(buf); },
        { agents, signal: controller.signal, maxTokens: 200 }
      );
    } catch (err) {
      const stopped = controller.signal.aborted;
      setSummary(stopped ? (buf + ' …(stopped)') : `⚠ ${err.message}`);
    } finally {
      clearTimeout(sumTimeout);
    }
    abortRef.current = null;
    setPhase('done');
  };

  const stop = () => { if (abortRef.current) abortRef.current.abort(); };

  const fullText = () => {
    const date = new Date().toLocaleDateString(undefined, { weekday:'long', month:'long', day:'numeric' });
    const lines = [`# Stand-up — ${date}`, ''];
    reports.forEach(r => {
      lines.push(`## ${r.name} (${r.role})`);
      lines.push(r.text || '(no report)');
      lines.push('');
    });
    if (summary) {
      lines.push('## Synthesis (CafresoHQ)');
      lines.push(summary);
    }
    return lines.join('\n');
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(fullText()); }
    catch (_e) { /* fall back: select the textarea */ }
  };

  const archive = () => {
    if (archived) return;
    onArchive({
      id: 'stu_'+Math.random().toString(36).slice(2,8),
      title: `Stand-up — ${new Date().toLocaleDateString(undefined,{month:'short',day:'numeric'})}`,
      detail: 'End-of-day team stand-up.',
      result: fullText(),
      status: 'done',
      priority: 'med',
      assignedTo: null,
      createdAt: Date.now(),
    });
    setArchived(true);
  };

  return (
    <OcModal
      open={open}
      onClose={onClose}
      title="🌅 END-OF-DAY STAND-UP"
      subtitle={phase === 'idle' ? 'click START to gather reports'
        : phase === 'running' ? 'agents are reporting…'
        : phase === 'summarizing' ? 'CafresoHQ is synthesizing…'
        : 'done — archive or copy'}
      size="lg"
      footer={
        <>
          <div className="hint" style={{marginRight: 'auto'}}>{archived ? '✓ archived to Docs' : phase==='done' ? 'tap ARCHIVE to save to Docs' : ''}</div>
          {phase === 'idle' && agents.length > 0 && <button className="px-btn primary" onClick={start} disabled={participating.length === 0}>▶ START ({participating.length})</button>}
          {(phase === 'running' || phase === 'summarizing') && <button className="px-btn danger" onClick={stop}>■ STOP</button>}
          {phase === 'done' && (<>
            <button className="px-btn secondary" onClick={copy}>COPY MARKDOWN</button>
            <button className="px-btn secondary" onClick={archive} disabled={archived}>{archived ? 'ARCHIVED ✓' : 'ARCHIVE'}</button>
            <button className="px-btn primary" onClick={start}>RE-RUN</button>
          </>)}
        </>
      }
    >
          {phase === 'idle' && reports.length === 0 && (
            <div>
              <div className="standup-preflight">
                <div className="empty-title">Run today's stand-up?</div>
                <div className="empty-sub">
                  {participating.length} of {agents.length} agent{agents.length===1?'':'s'} · cap {STANDUP_MAX_TOKENS} tok/each · {(STANDUP_TIMEOUT_MS/1000)|0}s timeout
                  {localCount > 0 && <span className="warn"> · ⚠ {localCount} local model{localCount===1?'':'s'} — heavy on a VM</span>}
                </div>
              </div>
              <div className="standup-list" style={{marginTop:10}}>
                {agents.map(a => {
                  const off = excluded.has(a.id);
                  const local = isLocal(a);
                  return (
                    <div key={a.id} className={`standup-row ${off?'disabled':''}`} style={{cursor:'pointer'}}
                      onClick={() => setExcluded(s => { const n = new Set(s); if (n.has(a.id)) n.delete(a.id); else n.add(a.id); return n; })}>
                      <Sprite data={a.color} scale={2}/>
                      <div className="su-body">
                        <div className="su-name">
                          {a.name} <span className="tiny">· {a.role}</span>
                          {local && <span className="model-chip local">{(a.model||'').replace(/^[a-z]+:/,'')}</span>}
                          {!local && a.model && <span className="model-chip cloud">{(a.model||'').replace(/^[a-z]+:/,'')}</span>}
                        </div>
                        <div className="su-text" style={{fontFamily:'Inter',fontSize:11,color:'var(--ink-3)'}}>
                          {off ? 'skipping' : 'will report'}
                        </div>
                      </div>
                      <div className={`pxswitch ${off?'':'on'}`}><div className="nub"/></div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {reports.length > 0 && (
            <div className="standup-list">
              {reports.map(r => (
                <div key={r.agentId} className={`standup-row ${r.error?'error':''}`}>
                  <Sprite data={r.color} scale={2}/>
                  <div className="su-body">
                    <div className="su-name">{r.name} <span className="tiny">· {r.role}</span></div>
                    <div className="su-text">{r.text || (r.streaming ? '' : '(silent)')}{r.streaming ? <span className="typing"><span/><span/><span/></span> : null}</div>
                  </div>
                </div>
              ))}
              {(summary || phase === 'summarizing') && (
                <div className="standup-summary">
                  <div className="su-name">CafresoHQ · synthesis</div>
                  <div className="su-text">{summary || ''}{phase==='summarizing' ? <span className="typing"><span/><span/><span/></span> : null}</div>
                </div>
              )}
            </div>
          )}
    </OcModal>
  );
}


function ReceiptTray({ receipts, onOpen }) {
  if (!receipts.length) return null;
  return (
    <button className="receipt-tray" onClick={onOpen} title={`${receipts.length} receipt${receipts.length===1?'':'s'} on file`}>
      <div className="rt-stack">
        <div className="rt-paper"/><div className="rt-paper"/><div className="rt-paper"/>
      </div>
      <span className="rt-label">📋 RECEIPTS · {receipts.length}</span>
    </button>
  );
}

function ReceiptsModal({ open, onClose, receipts, onPin, onClear }) {
  const [filter, setFilter] = useSF('all');
  if (!open) return null;
  const filtered = receipts.filter(r => {
    if (filter === 'all') return true;
    if (filter === 'tool-execution') return r.kind === 'tool-execution';
    if (filter === 'deliverable') return r.kind === 'deliverable';
    return r.decision === filter;
  });
  const fmt = (ts) => new Date(ts).toLocaleString(undefined, { month:'short', day:'numeric', hour:'numeric', minute:'2-digit' });
  const stampFor = (r) => r.kind === 'deliverable' ? '📝' : (r.kind === 'tool-execution' ? '🛠' : (r.decision === 'approved' ? '✓' : '✕'));
  return (
    <OcModal
      open={open}
      onClose={onClose}
      title="📋 RECEIPTS"
      subtitle="stamped approvals · audit trail"
      size="lg"
      footer={receipts.length > 0 ? (
        <>
          <button className="px-btn ghost" style={{fontSize: 'var(--text-9)', marginRight: 'auto'}} onClick={()=>{ if (confirm('Clear all receipts? Audit trail is lost.')) onClear(); }}>CLEAR ALL</button>
          <button className="px-btn primary" onClick={onClose}>DONE</button>
        </>
      ) : null}
    >
      <div style={{display:'flex',gap: 'var(--sp-3)', marginBottom: 'var(--sp-4)', alignItems:'center'}}>
        {['all','deliverable','approved','rejected','tool-execution'].map(f => (
          <button key={f} className={`px-btn ${filter===f?'primary':'secondary'}`} style={{fontSize: 'var(--text-9)'}} onClick={()=>setFilter(f)}>{f.toUpperCase().replace('-', ' ')}</button>
        ))}
        <span className="tiny" style={{marginLeft:'auto'}}>{filtered.length} of {receipts.length}</span>
      </div>
      {filtered.length === 0 && <div className="empty-state"><div className="empty-title">No receipts yet.</div><div className="empty-sub">Stamp an approval and it lands here.</div></div>}
      <div className="receipts-list">
        {filtered.map(r => (
          <div key={r.id} className={`receipt-card ${r.decision}${r.kind === 'tool-execution' ? ' tool-execution' : ''}`}>
            <div className="rc-stamp">{stampFor(r)}</div>
            <div className="rc-body">
              <div className="rc-title">{r.elevated && r.kind !== 'tool-execution' ? '🛡 ' : ''}{r.title}</div>
              <div className="rc-meta">
                <span>by {r.by}</span>
                <span>·</span>
                <span>{r.kind || (r.amount ? '$'+r.amount : 'action')}</span>
                <span>·</span>
                <span>{fmt(r.decidedAt)}</span>
              </div>
            </div>
            {onPin && r.kind !== 'tool-execution' && <button className="px-btn secondary" style={{fontSize: 'var(--text-9)'}} onClick={()=>onPin(r)}>📌 PIN</button>}
          </div>
        ))}
      </div>
    </OcModal>
  );
}

/* ---------------- Approval stamp tray ---------------- */
function ApprovalTray({ pending, onApprove, onReject }) {
  if (pending.length === 0) return null;
  return (
    <div className="approval-tray">
      <div className="ap-head">⚖ APPROVALS · {pending.length}</div>
      {pending.map(p => (
        <div key={p.id} className={`ap-row${p.elevated ? ' elevated' : ''}`}>
          <div>
            <div className="ap-title">{p.elevated ? '🛡 ' : ''}{p.title}</div>
            <div className="ap-sub">
              by {p.by} · {p.amount ? '$' + p.amount : p.kind}
              {p.elevated && <span style={{color:'#c44',marginLeft:6}}>· agent waiting on your call</span>}
            </div>
          </div>
          <div style={{display:'flex',gap:4}}>
            <button className="stamp green" onClick={()=>onApprove(p.id)}>APPROVE</button>
            <button className="stamp red" onClick={()=>onReject(p.id)}>REJECT</button>
          </div>
        </div>
      ))}
    </div>
  );
}

window.CafresoHQV2 = { TaskBoard, MemoryShelf, MeetingRoom, FocusMode, ApprovalTray, ReceiptTray, ReceiptsModal, StandupModal, SEED_TASKS, SEED_MEMORY };
