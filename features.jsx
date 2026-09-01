import { Sprite } from './sprites.jsx';
import { HQ } from './hq-runtime.jsx';
import { CafresoHQModals } from './modals.jsx';
import { floorEmit, snagSentence } from './app/floor.jsx';
import { xpLastAttempt, xpLastAttemptText } from './app/experience.jsx';
import { brainName } from './app/cast.jsx';
import { cardNote, finishedLabel, worklogLine } from './app/worklog.jsx';
/* ==========================================================================
   CafresoHQ — features v2
   Tasks board, memory shelf, meeting room, focus mode, approval stamps
   ========================================================================== */

const { useState: useSF, useEffect: useEF, useRef: useRF, useMemo: useMF } = React;

/* Pulled from CafresoHQModals so the modals defined in this file can use the
   shared <Modal> shell (focus trap, scroll lock, animated entry). */
const { Modal: OcModal, StarterCards, buildStarterTask } = CafresoHQModals;

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
        {agents.length === 0 && <option disabled>(no coworkers hired)</option>}
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

/* `tasks` here is the FILTERED list (TasksView applies search + the
   show-completed toggle), so it must never be used to decide whether the
   office is new. `totalCount` is the unfiltered figure and is the only
   thing allowed to trigger onboarding — otherwise a search matching
   nothing would greet an established boss with "No tasks yet". */
function TaskBoard({ tasks, agents, onAssign, onAdd, onMove, onDelete, onCyclePriority, onDragStart, onAssignToChat, onMakeRoomFromTask, onStartTask, totalCount = null, experience = [], highlightTaskId = null, onConsumeHighlight = null }) {
  const officeIsNew = (totalCount === null ? tasks.length : totalCount) === 0;
  const [adding, setAdding] = useSF(false);
  const [title, setTitle] = useSF('');
  const [expanded, setExpanded] = useSF({});

  /* A calendar row's whole point is landing the boss on THE task that
     prompted the click, not just the board it lives on — the Calendar's
     own mission rows and the pre-existing "Open task board →" door both
     stopped at "here's the board, go find it". Expand the matching card
     (so its detail is what they see, not a title they have to click
     again) and scroll it into view; a brief flash class says WHICH card
     this was, since a fresh scroll position alone reads as "did it move
     the page or did nothing happen". Consumed once so a later visit to
     Tasks (no fresh click) doesn't replay the flash on a stale id. */
  const [flashId, setFlashId] = useSF(null);
  useEF(() => {
    if (!highlightTaskId) return;
    if (!tasks.some(t => t.id === highlightTaskId)) return;   // filtered out or gone
    setExpanded(prev => ({ ...prev, [highlightTaskId]: true }));
    setFlashId(highlightTaskId);
    const raf = requestAnimationFrame(() => {
      const el = document.querySelector(`[data-task-id="${highlightTaskId}"]`);
      if (el && el.scrollIntoView) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
    // Consuming the highlight is intentionally its own effect (below), keyed
    // on flashId rather than highlightTaskId: onConsumeHighlight clears the
    // PARENT's highlightTaskId prop almost immediately, which reruns this
    // effect's cleanup. If the flash-clear timer lived in *this* effect,
    // that cleanup would cancel it before it ever fired — the outline
    // would light up once and then never turn off.
    const t2 = setTimeout(() => onConsumeHighlight && onConsumeHighlight(), 50);
    return () => { cancelAnimationFrame(raf); clearTimeout(t2); };
  }, [highlightTaskId]);
  useEF(() => {
    if (!flashId) return;
    const t1 = setTimeout(() => setFlashId(null), 2600);
    return () => clearTimeout(t1);
  }, [flashId]);
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
                  <div key={t.id} data-task-id={t.id}
                       className={`task-card pri-${t.priority}${expanded[t.id] ? ' expanded' : ''}${flashId===t.id ? ' tc-highlight-flash' : ''}`}
                       style={flashId===t.id ? { outline: '3px solid var(--ink)', outlineOffset: 2, transition: 'outline-color 2.4s ease', animation: 'none' } : undefined}
                       draggable
                       onDragStart={e=>{ e.dataTransfer.setData('task', t.id); onDragStart && onDragStart(t); }}
                       onClick={()=>setExpanded(prev=>({...prev, [t.id]: !prev[t.id]}))}>
                    {onDelete && (
                      <button className="tc-delete" title="Delete task"
                        onClick={(e)=>{ e.stopPropagation(); onDelete(t.id); }}>✕</button>
                    )}
                    <div className="tc-title">{t.title}</div>
                    {t.detail && <div className="tc-detail">{t.detail}</div>}
                    {(() => {
                      const line = xpLastAttemptText(xpLastAttempt(experience, t.id, agents));
                      return line ? <div className="tc-lastry">⚠ {line}</div> : null;
                    })()}
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
                        <span className="tc-unassigned">{onStartTask ? 'unassigned · pick someone, then ▶ START' : onAssignToChat ? 'unassigned · use → CHAT' : '↕ drag to a desk'}</span>
                      )}
                      {/* The lever, not just the label. Stops on the card so
                          it never opens/collapses the row underneath. */}
                      <span className={`pri pri-${t.priority}`}
                            role={onCyclePriority ? 'button' : undefined}
                            tabIndex={onCyclePriority ? 0 : undefined}
                            title={onCyclePriority ? 'Priority — click to change' : undefined}
                            style={onCyclePriority ? { cursor: 'pointer' } : undefined}
                            onClick={onCyclePriority ? (e)=>{ e.stopPropagation(); onCyclePriority(t.id); } : undefined}
                            onKeyDown={onCyclePriority ? (e)=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); e.stopPropagation(); onCyclePriority(t.id);} } : undefined}
                      >{t.priority.toUpperCase()}</span>
                    </div>
                    {/* Why this card is back in the inbox looking untouched.
                        `stalledNote` was written by the reload scrub and read
                        by NOTHING — I added the write earlier today and never
                        gave it a surface, so the office had an honest
                        explanation for a stalled card and kept it to itself.
                        A card that went back to the inbox without the boss
                        putting it there has to say so on the card; the
                        activity strip scrolls away, this does not. */}
                    {t.stalledNote && t.status !== 'done' && (
                      /* The whole note on the hover, because the cut one
                         is the one that fits, not the one that is true. */
                      <div className="tc-stalled"
                           title={'Why this is sitting in the inbox:\n\n' + String(t.stalledNote)}>
                        ↩ {cardNote(t.stalledNote)}
                      </div>
                    )}
                    {/* Is anybody actually on this? A DOING card used to look
                        identical whether a coworker was mid-run or the job
                        had been abandoned there for hours. §4: `agent.status`
                        is the only authority, so that is what this reads —
                        never the task's own status. */}
                    {(() => {
                      const line = worklogLine(t, a);
                      if (!line) return null;
                      /* Three states now, not two. `is-idle` is reused for a
                         blocked card because it IS not progressing and the
                         muted treatment is right; the glyph and the reason
                         line below carry what is different about it. */
                      const blocked = !!t.blockedReason && t.status === 'doing';
                      const idle = !blocked && line.indexOf('nobody') === 0;
                      return <div className={'tc-worklog' + (blocked || idle ? ' is-idle' : '')}>
                        {blocked ? '✋' : idle ? '⏸' : '⚡'} {line}
                      </div>;
                    })()}
                    {/* The reason the coworker gave, which until now existed
                        only on the record and in a toast that was gone in
                        seconds. Same treatment as `stalledNote` above: the
                        card is the surface that does not scroll away.

                        `!== 'done'`, the same gate `stalledNote` uses, and
                        deliberately not `=== 'doing'`. The reload scrub sends
                        every `doing` task back to `inbox` without touching
                        this field, so a doing-only gate would have hidden a
                        password-protected spreadsheet the moment the boss
                        refreshed — and "start it again" is bad advice for a
                        job that will hit the same wall. Nothing goes stale
                        by staying: the three paths that move a task on from
                        a block — a progress note, a completion, a fresh
                        START — all clear it. */}
                    {t.blockedReason && t.status !== 'done' && (
                      <div className="tc-stalled"
                           title={'What the coworker said they were stuck on:\n\n' + String(t.blockedReason)}>
                        ✋ {cardNote(t.blockedReason)}
                      </div>
                    )}
                    {/* What the coworker has done so far. `progressLog` was
                        the last of the three write-only fields on a task:
                        every `[TASK_PROGRESS: …]` note went into a ten-entry
                        array and reached a toast, and nothing ever read the
                        array back. The worklog line above says a job is
                        moving; this says what moved.

                        Collapsed shows the latest note only, and only while
                        the job is unfinished — once there is a result, the
                        result is the answer and the notes are history. Click
                        the card for all of them. The "+N more" counter is
                        computed from the notes actually hidden, so it can
                        never advertise a history that isn't there. */}
                    {(() => {
                      const log = (t.progressLog || []).filter(p => p && p.note);
                      if (!log.length) return null;
                      const open = !!expanded[t.id];
                      if (!open && t.result) return null;
                      const shown = open ? log : log.slice(-1);
                      return (
                        <div>
                          {shown.map((p, i) => (
                            <div key={p.at || i} className="tc-stalled"
                                 title="A note your coworker left while working">
                              · {String(p.note).slice(0, 160)}
                            </div>
                          ))}
                          {!open && log.length > 1 && (
                            <div className="tc-worklog"
                                 style={{ border: 'none', paddingTop: 0, opacity: 0.7 }}>
                              +{log.length - 1} earlier — click to read
                            </div>
                          )}
                        </div>
                      );
                    })()}
                    {/* What actually came back.

                        `result` is the deliverable — the text the coworker
                        produced — and it was written to the record, spoken
                        once into a chat bubble that scrolls away, and never
                        shown again. The only code that read it was the
                        delete confirmation, which warned the boss they were
                        about to lose work the office had never let them see.
                        A DONE column that cannot show what was done is not
                        an operating business.

                        `tc-detail` is reused deliberately rather than given
                        its own class: it clamps to three lines and un-clamps
                        under `.task-card.expanded`, which is exactly the
                        behaviour this needs — and it gives the card's click
                        something to do. Before this, clicking a card toggled
                        `expanded` and nothing on screen changed unless the
                        title happened to run past two lines. Measured: same
                        height, same text, both sides of the click.

                        The name comes from `completedBy`, not from the
                        assignee, and falls back to no name at all rather
                        than crediting whoever holds the card now — §4's rule
                        that the office reports what it knows. */}
                    {t.result && (() => {
                      const by = agents.find(x => x.id === t.completedBy) || null;
                      const when = finishedLabel(t);
                      /* A result is not a finish. This header keyed off the
                         mere PRESENCE of `t.result`, so a card that came back
                         empty — parked in `doing`, wearing the ✋ snag line
                         and its reason three lines above — still carried
                         `✓ finished` over the very text explaining that it
                         had not. Watched on the board: "✋ hit a snag · just
                         now / ✋ no file reached the cabinet …" and then
                         "✓ finished" directly beneath it.

                         `t.status === 'done'` is the gate the two surfaces
                         above already use, and deliberately not `!== 'doing'`
                         for the reason recorded there: the reload scrub sends
                         doing cards back to `inbox` without clearing this
                         field. When it is not a finish the text is still
                         worth showing — it is what came back — so the label
                         says that instead, and takes the muted treatment its
                         neighbours use for a card that is not progressing. */
                      const finished = t.status === 'done';
                      return (
                        <div>
                          <div className={'tc-worklog' + (finished ? '' : ' is-idle')}>
                            {finished
                              ? `✓ ${by ? `${by.name} finished this` : 'finished'}`
                              : `· ${by ? `${by.name} came back with this` : 'what came back'}`}
                            {when ? ` · ${when}` : ''}
                          </div>
                          <div className="tc-detail" style={{ marginBottom: 0 }}>
                            {String(t.result)}
                          </div>
                        </div>
                      );
                    })()}
                    {/* → CHAT drafts the task as an @mention in the DIRECT
                        thread; 📋 ROOM opens the meeting-create modal
                        pre-populated. Neither starts work — they hand the
                        boss something to review, and the task only moves to
                        DOING once the message is really sent / the room is
                        really created. ▶ START is the explicit act this
                        board was always missing: the assignee dropdown
                        deliberately only names an owner, which left no way
                        to actually put someone to work from here. */}
                    {(onAssignToChat || onMakeRoomFromTask || onStartTask) && t.status !== 'done' && (
                      <div className="tc-actions">
                        {onStartTask && a && (
                          <button
                            className="tc-action-btn start"
                            title={`Put ${a.name} to work on this now`}
                            onClick={(e) => { e.stopPropagation(); onStartTask(t.id, a); }}
                          >▶ START</button>
                        )}
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
                  /* Empty inbox is the other place a blank box would stall a
                     newcomer — offer the same starter outcomes as the
                     first-run sheet. These land unassigned, so the drag-to-a-
                     desk mechanic below still gets taught. */
                  ? (officeIsNew
                    /* "No tasks YET" and the starter cards are ONBOARDING —
                       they belong to an office that has never had a task.
                       Gated only on the INBOX column being empty, they kept
                       showing after the work was done, so the board read
                       "3 of 3" in its header and "No tasks yet — start from
                       one of these" underneath. Both about the same three
                       tasks. An empty column is not a new office. */
                    ? <div className="tb-empty onboard">
                      No tasks yet — start from one of these:
                      {/* No assignee yet, so canSearch asks only the
                          office-level question: is search wired at all. If
                          it isn't, no coworker this card lands on could
                          source anything. */}
                      <StarterCards compact canSearch={CafresoHQModals.canSearchFor(null)} onPick={(starter, subject) => {
                        const t = buildStarterTask(starter, subject, null);
                        if (t) onAdd(t);
                      }} />
                      <span className="tb-empty-hint">Or hit <strong>+ NEW</strong> above. Drag any card onto a coworker's desk to delegate.</span>
                    </div>
                    : <div className="tb-empty">Nothing waiting — hit <strong>+ NEW</strong> to add one.</div>)
                  : <div className="tb-empty">—</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------------- Meeting Room ---------------- */
/* Meeting door picker — the office-floor MEETING ROOM used to seat whoever
   `agents.slice(0, 2)` picked with zero boss input, and the CEO panel's
   mini-office door opened it with whatever `meetingParticipants` happened
   to be left over from the last time (including empty, on a fresh
   session — a "meeting" of nobody but CafresoHQ). Both doors now go
   through this picker instead. Reuses the exact `.meeting-attendee-grid`
   markup the standalone "NEW MEETING ROOM" chat-thread modal
   (modals/collab.jsx) already uses, so seating a team looks the same
   everywhere in the app. Preselects the first two agents so a boss who
   just wants the old one-click behavior can still hit Start Meeting
   immediately without picking anyone. */
function MeetingPicker({ open, agents, onClose, onStart }) {
  const [selectedIds, setSelectedIds] = useSF([]);
  useEF(() => { if (open) setSelectedIds(agents.slice(0, 2).map(a => a.id)); }, [open]);
  if (!open) return null;
  const toggle = (id) => setSelectedIds(prev =>
    prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  const canStart = selectedIds.length >= 1;
  return (
    <OcModal open={open} onClose={onClose} title="🪑 SEAT THE MEETING ROOM" size="md">
      <div className="meeting-modal-body">
        <label>
          Attendees <span style={{opacity:0.5,fontSize:9,marginLeft:4}}>(pick who's in the room)</span>
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
          <button className="px-btn primary" disabled={!canStart} onClick={() => onStart(selectedIds)}>
            Start Meeting · {selectedIds.length} attendee{selectedIds.length === 1 ? '' : 's'}
          </button>
        </div>
      </div>
    </OcModal>
  );
}

function MeetingRoom({ participants, agents, onClose, onRemove, onAdd, onUpdateAgent }) {
  const [msgs, setMsgs] = useSF([]);
  const [input, setInput] = useSF('');
  const [streaming, setStreaming] = useSF(false);
  const [addOpen, setAddOpen] = useSF(false);
  const logRef = useRF(null);
  useEF(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [msgs]);
  /* Whoever's left once seated — the "+ Seat" tile below only shows a
     coworker once, and disappears once everyone hired is already in the
     room. */
  const available = agents.filter(a => !participants.some(p => p.id === a.id));

  const newId = () => 'mtg_' + Math.random().toString(36).slice(2, 8);

  const abortRef = useRF(null);
  const stop = () => { if (abortRef.current) abortRef.current.abort(); };

  const moderate = async () => {
    if (!input.trim() || streaming) return;
    const you = input.trim();
    setInput('');
    setStreaming(true);

    const youMsg = { id: newId(), who: 'You', color: null, text: you };
    /* `let`, not `const` — this is a LIVE round, and each participant needs
       to hear whoever just spoke before them, same as the CEO's synthesis
       needs to hear everyone. A frozen snapshot here means the second
       coworker in a three-person room answers deaf to the first — verified
       live: asked to name who spoke before them, the second coworker
       insisted they were first, because their prompt still held the
       pre-round transcript. Appended after each turn below. */
    let transcript = msgs.map(m => `${m.who}: ${m.text}`).join('\n') + `\nYou: ${you}`;
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
       just gate the update calls themselves to once per frame.

       `.cancel()`: the same missing half of the fix as the stand-up's
       identical gate above (see its comment) — without it, the pending rAF
       scheduled by the stream's last raw token fires a frame after the
       "clean the final text" write just below and overwrites it right back
       with the unstripped buffer. */
    const makeRafGate = (id) => {
      let scheduled = false;
      let cancelled = false;
      let latest = '';
      const fn = (text) => {
        latest = text;
        if (scheduled || cancelled) return;
        scheduled = true;
        requestAnimationFrame(() => { scheduled = false;
          if (cancelled) return;
          updateById(id, { text: latest });
        });
      };
      fn.cancel = () => { cancelled = true; };
      return fn;
    };

    for (const ph of placeholders) {
      let buf = '';
      const update = makeRafGate(ph.id);
      /* A turn is work from the moment it is dispatched, not from the first
         token — the screen event only fires once tokens arrive, which left
         the whole dispatch→first-token wait looking idle. `status` is what
         anyLive and the room plate both read, so it is the honest signal
         for "this coworker is working right now". Cleared in `finally` so
         a failed or stopped turn can never strand them as busy. */
      if (onUpdateAgent) onUpdateAgent(ph.agentRef.id, { status: 'busy', mood: 'thinking' });
      try {
        await HQ.agentStream(
          ph.agentRef,
          `Meeting transcript so far:\n${transcript}\n\nRespond briefly (1-2 sentences) from your role's perspective.`,
          /* A stand-up is real work, and the office used to show none of it:
             participants stood in the meeting room while the building's LIVE
             lamp stayed dark for the whole round. The screen event is exactly
             the "this coworker is streaming" signal, so the floor lights up
             for the turn that is actually happening. */
          tok => { buf += tok; update(buf);
                   floorEmit('screen', { agentId: ph.agentRef.id, tail: buf.slice(-240), phase: 'stream' }); },
          { signal: controller.signal }
        );
        /* Clean the final text, same as every other reply path. A meeting
           turn is a coworker speaking to the whole room, so a stray marker
           lands in the transcript the others then read back as context.
           `.cancel()` first — the gate's pending rAF from the stream's last
           raw token otherwise fires a frame after this and overwrites the
           clean text right back with the unstripped buffer. */
        update.cancel();
        const cleaned = HQ.visibleReply(buf, ph.agentRef && ph.agentRef.name);
        updateById(ph.id, { text: cleaned });
        transcript += `\n${ph.agentRef.name}: ${cleaned}`;
      } catch (err) {
        update.cancel();
        const stopped = (controller.signal && controller.signal.aborted) || err.name === 'AbortError';
        /* §7: no raw error dumps on a user surface. This read
           `⚠ OpenRouter 503: {"error": "openrouter: no API key configured"}`
           — the floor already had one honest sentence for exactly this. */
        updateById(ph.id, {
          text: stopped ? (buf + ' …(stopped)') : '⚠ ' + snagSentence(err && err.message || String(err)),
          error: !stopped,
        });
        if (stopped) break;
      } finally {
        floorEmit('screen', { agentId: ph.agentRef.id, tail: '', phase: 'done' });
        if (onUpdateAgent) onUpdateAgent(ph.agentRef.id, { status: 'idle', mood: 'idle' });
        updateById(ph.id, { streaming: false });
      }
    }

    let buf = '';
    if (!controller.signal.aborted) {
      const update = makeRafGate(ceoPlaceholder.id);
      try {
        await HQ.ceoStream(
          `You are moderating a team meeting. Transcript:\n${transcript}\n\nSynthesize the discussion in 1-2 sentences and state the next action.`,
          tok => { buf += tok; update(buf); },
          { agents: participants, signal: controller.signal }
        );
        /* The CEO's own words reach the boss here, and this set the RAW
           buffer. Same recipe as every other reply path now. */
        updateById(ceoPlaceholder.id, { text: HQ.cleanHarmony(HQ.visibleReply(buf, 'CafresoHQ')) || buf });
      } catch (err) {
        const stopped = (controller.signal && controller.signal.aborted) || err.name === 'AbortError';
        updateById(ceoPlaceholder.id, {
          text: stopped ? (buf + ' …(stopped)') : '⚠ ' + snagSentence(err && err.message || String(err)),
          error: !stopped,
        });
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
          {onAdd && available.length > 0 && (
            <div className="seat seat-add" onClick={() => setAddOpen(o => !o)} title="Seat another coworker">
              <div className="seat-add-plus">+</div>
              <div className="seat-role">Seat someone</div>
              {addOpen && (
                <div className="meeting-attendee-grid seat-add-popover" onClick={e => e.stopPropagation()}>
                  {available.map(a => (
                    <div
                      key={a.id}
                      className="meeting-attendee"
                      onClick={() => { onAdd(a.id); setAddOpen(false); }}
                    >
                      <span style={{fontSize:14}}>{a.elevated ? '🛡' : '👤'}</span>
                      <div style={{display:'flex',flexDirection:'column',lineHeight:1.1,minWidth:0}}>
                        <span className="meeting-attendee-name">{a.name}</span>
                        <span className="meeting-attendee-role">{a.role}</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
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
        ? {...m, text: stopped ? (m.text + ' …(stopped)') : `⚠ ${snagSentence(err && err.message || String(err))}`, error: !stopped}
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
        {/* "quiet room · no distractions" is only true if this shows the
           direct 1:1 alone — chat is the single, app-wide, cross-thread
           array (team-DM relays, project/meeting rooms, etc. all live in
           the same list, tagged only by m.thread), so an unfiltered slice
           surfaced background coworker chatter here right under a "no
           distractions" banner. Same (m.thread || 'direct') convention
           ui/chat.jsx's visibleChat already uses for its own Direct tab. */}
        {chat.filter(m => (m.thread || 'direct') === 'direct').slice(-12).map(m => (
          <div key={m.id} className={`msg ${m.from}`}>
            <div className="who">
              {m.from === 'user'
                ? <div style={{width:22,height:22,background:'var(--accent-sun)',border:'2px solid var(--ink)',display:'grid',placeItems:'center',fontFamily:'Press Start 2P',fontSize:10}}>B</div>
                : m.from === 'ceo'
                  ? <Sprite data="cafresohq" scale={1}/>
                  /* A coworker's own direct-thread reply (e.g. a delegated
                     task) — the CEO's own mascot on it would misattribute
                     someone else's words as "1:1 WITH CAFRESOHQ". */
                  : <div style={{width:22,height:22,background:'var(--paper)',border:'2px solid var(--ink)',display:'grid',placeItems:'center',fontFamily:'Press Start 2P',fontSize:10}}>{(m.name || 'A').charAt(0).toUpperCase()}</div>}
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

function StandupModal({ open, onClose, agents, onArchive, onHire }) {
  const [reports, setReports] = useSF([]);   // [{agentId, name, color, text, streaming, error}]
  const [summary, setSummary] = useSF('');
  /* Why the closing summary is missing, or '' when it landed. Set where the
     failure HAPPENS, not inferred later from the summary string: the record
     built at archive time has to know whether CafresoHQ actually read the
     day, and sniffing for a '⚠' prefix would call a real summary that
     quotes one a failure, and a future failure worded differently a
     success. Two values, both a reason the boss can read: 'stopped' when
     they hit STOP, the snag sentence when the brain could not be reached. */
  const [summaryFail, setSummaryFail] = useSF('');
  const [phase, setPhase] = useSF('idle');   // idle | running | summarizing | done
  const [archived, setArchived] = useSF(false);
  const [copied, setCopied] = useSF(null);   // null | true | false — real result of the last COPY MARKDOWN click
  const [excluded, setExcluded] = useSF(new Set());
  const abortRef = useRF(null);

  /* app.jsx renders <StandupModal> unconditionally (`open` just gates the
     `return null` below) — this component instance never actually unmounts
     while the app is up, so a cleanup tied to unmount would never fire for
     the case that matters. `start()`'s per-agent loop and the closing
     `HQ.ceoStream` call are plain async closures, not tied to React
     lifecycle at all, so closing the modal mid-run (X, Escape, backdrop —
     all of which just flip `open` to false) left the stream running
     invisibly: it kept burning agentStream/ceoStream calls (up to
     STANDUP_TIMEOUT_MS per agent for a stuck local model) with no UI left to
     show or stop it, and reopening the modal got a fresh render of the same
     instance with no way to know a run was still going. Same shape as the
     Terminal PTY zombie-process leak, recurring here — fix is to abort on
     the actual open→false edge, not on an unmount that never happens. */
  useEF(() => {
    if (!open && abortRef.current) { abortRef.current.abort(); abortRef.current = null; }
  }, [open]);

  if (!open) return null;

  const participating = agents.filter(a => !excluded.has(a.id));
  const isLocal = (a) => /^(lmstudio|ollama):/.test(a.model || '');
  const localCount = participating.filter(isLocal).length;

  const start = async () => {
    if (phase === 'running' || phase === 'summarizing') return;
    if (participating.length === 0) return;
    setArchived(false);
    setSummary('');
    setSummaryFail('');
    setReports(participating.map(a => ({ agentId: a.id, name: a.name, color: a.color, role: a.role, text: '', streaming: true, error: false })));
    setPhase('running');
    const controller = new AbortController();
    abortRef.current = controller;

    const finished = [];
    /* rAF gate to batch setReports per-frame — same reason as the chat panel:
       per-token state churn pegs CPU when reports list grows.

       `.cancel()` exists because the LAST raw token of a stream schedules a
       pending rAF write moments before the loop's own "final, cleaned" write
       runs synchronously right after. requestAnimationFrame fires on the
       NEXT paint, after this function returns — so that stale pending
       callback lands AFTER the clean write and overwrites it with the raw
       buffer. Watched live: a real stand-up's checked-in report read "TODAY:
       Saved first note to private memory folder using [MEMORY_WRITE:
       decisions/auth.md]…[/MEMORY_WRITE]." — the exact machine syntax
       `HQ.visibleReply()` two lines below is supposed to strip, verified by
       running that same string through `stripBlocks`'s regex directly: it
       strips cleanly in isolation, so the raw text on screen could only be
       the gate's own late write, not a stripping failure. `HQ.throttleTokens`
       (the chat/task path's equivalent gate) already learned this lesson —
       callers there call `flush.cancel()` before writing final state; this
       local reimplementation, and the meeting room's identical one below,
       never got that half of the fix. */
    const makeReportGate = (agentId) => {
      let scheduled = false;
      let cancelled = false;
      let latest = '';
      const fn = (text) => {
        latest = text;
        if (scheduled || cancelled) return;
        scheduled = true;
        requestAnimationFrame(() => { scheduled = false;
          if (cancelled) return;
          setReports(prev => prev.map(r => r.agentId === agentId ? { ...r, text: latest } : r));
        });
      };
      fn.cancel = () => { cancelled = true; };
      return fn;
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
        await HQ.agentStream(a, STANDUP_PROMPT,
          tok => { buf += tok; updateReport(buf); },
          { signal: perAgent.signal, maxTokens: STANDUP_MAX_TOKENS }
        );
        /* Final non-throttled flush, cleaned. This ran `text: buf` — the raw
           stream — on the one ritual the comment below calls "the whole team
           checking in", so a coworker who emitted a marker checked in with
           machine syntax. The archive gets the same text as the screen;
           they used to be the same only because neither was cleaned.
           `.cancel()` first — see the gate's own comment above — or this
           write wins the race with the stream's last token and then loses
           it to the gate's pending rAF a frame later. */
        updateReport.cancel();
        const said = HQ.visibleReply(buf, a && a.name);
        setReports(prev => prev.map(r => r.agentId === a.id ? { ...r, text: said } : r));
        setReports(prev => prev.map(r => r.agentId === a.id ? { ...r, streaming: false } : r));
        finished.push({ name: a.name, role: a.role, text: said });
      } catch (err) {
        updateReport.cancel();
        const userStopped = controller.signal.aborted;
        const timedOut = !userStopped && perAgent.signal.aborted;
        const label = userStopped ? '…(stopped)' : timedOut ? '…(timed out — model too slow or unloaded)' : null;
        /* Same rule as everywhere else a run can fail (§7): one honest
           sentence, never the raw exception. This row was printing
           `⚠ OpenRouter 503: {"error": "openrouter: no API key
           configured"}` straight through — a status code and a JSON
           blob, on the one ritual meant to feel like the whole team
           checking in. */
        setReports(prev => prev.map(r => r.agentId === a.id
          ? { ...r, streaming: false, error: !label, text: label ? (buf + ' ' + label) : `⚠ ${snagSentence(err && err.message || String(err))}` }
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
      await HQ.ceoStream(
        `End-of-day stand-up reports:\n\n${transcript}\n\nSynthesize this in 2 sentences and call out the single most important next action for the boss.`,
        tok => { buf += tok; setSummary(buf); },
        { agents, signal: controller.signal, maxTokens: 200 }
      );
      /* …and the same for the stand-up's closing summary, which the boss
         reads as the CEO's read of the day. */
      const cleanedSummary = HQ.cleanHarmony(HQ.visibleReply(buf, 'CafresoHQ'));
      if (cleanedSummary && cleanedSummary !== buf) setSummary(cleanedSummary);
    } catch (err) {
      const stopped = controller.signal.aborted;
      // Same raw-dump bug as the per-agent reports above, one function down.
      const snag = snagSentence(err && err.message || String(err));
      setSummary(stopped ? (buf + ' …(stopped)') : `⚠ ${snag}`);
      /* The screen shows the ⚠ and the boss sees it; the ARCHIVE does not
         get to forget it. Everything downstream of here — the heading in
         the filed report, the card's own detail line, the footer offering
         to file — reads this, so the failure survives the trip from the
         modal to the board. */
      setSummaryFail(stopped ? 'stopped' : snag);
    } finally {
      clearTimeout(sumTimeout);
    }
    abortRef.current = null;
    setPhase('done');
  };

  const stop = () => { if (abortRef.current) abortRef.current.abort(); };

  /* How many of the people who were asked actually said something. An error
     row and a silent row are both "did not report" — the reports array keeps
     them so the record shows WHO was asked, and this counts who answered. */
  const reported = () => reports.filter(r => r.text && !r.error).length;

  const fullText = () => {
    const date = new Date().toLocaleDateString(undefined, { weekday:'long', month:'long', day:'numeric' });
    const lines = [`# Stand-up — ${date}`, ''];
    reports.forEach(r => {
      lines.push(`## ${r.name} (${r.role})`);
      lines.push(r.text || '(no report)');
      lines.push('');
    });
    /* The heading names an ACT, so it may only be written over an act that
       happened. This read `## Synthesis (CafresoHQ)` over whatever `summary`
       held — and when the CEO brain was unreachable, `summary` held the snag
       sentence. Filed on a real stand-up, 2026-08-18:

         ## Synthesis (CafresoHQ)
         ⚠ hit a snag — couldn't reach that brain — it looks offline from here

       A heading swearing CafresoHQ read the day, over a sentence saying it
       never did (§5 — and #89, the cabinet note that swore to more than its
       witness saw, is this same shape one surface over). The report is the
       part of a stand-up that outlives the modal: read a week later, the
       heading is what a boss remembers and the small print is what they
       skim.

       So the section says which of the three things happened, and when the
       synthesis is missing it also says what the record IS — the reports,
       whole and unsummarised — because "not written" alone leaves a boss
       wondering whether the rest is trustworthy either. */
    if (summaryFail === 'stopped') {
      lines.push('## Synthesis — stopped part-way');
      lines.push(summary
        ? `${summary}\n\nYou stopped the stand-up before CafresoHQ finished the closing summary. What is above is the whole of it.`
        : 'You stopped the stand-up before CafresoHQ started the closing summary. The reports above are the whole record.');
    } else if (summaryFail) {
      lines.push('## Synthesis — not written');
      /* snagSentence() returns a clause, not a sentence — it is written to
         sit after a "⚠ " on screen, where nothing follows it. Filed, it has
         a sentence on the other side of it, and without this the record read
         "…offline from here The reports above are…". */
      const why = /[.!?]$/.test(summaryFail) ? summaryFail : summaryFail + '.';
      lines.push(`CafresoHQ could not write the closing summary: ${why} The reports above are the whole record — nobody has read them together yet.`);
    } else if (summary) {
      lines.push('## Synthesis (CafresoHQ)');
      lines.push(summary);
    }
    return lines.join('\n');
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(fullText()); setCopied(true); }
    catch (_e) { setCopied(false); }
    setTimeout(() => setCopied(null), 2200);
  };

  const archive = () => {
    if (archived) return;
    onArchive({
      id: 'stu_'+Math.random().toString(36).slice(2,8),
      title: `Stand-up — ${new Date().toLocaleDateString(undefined,{month:'short',day:'numeric'})}`,
      /* The card face, which is all a boss sees on the board a week later.
         A flat 'End-of-day team stand-up.' over a stand-up where nobody
         reported, or where the closing summary never got written, is the
         same claim as the heading this fix just stopped writing — one line
         further out, where it is read more often and opened less. */
      detail: `End-of-day team stand-up — ${reported()} of ${reports.length} reported`
        + (summaryFail === 'stopped' ? '; you stopped it before the summary.'
           : summaryFail ? '; no closing summary.' : '.'),
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
        : phase === 'running' ? 'your team is reporting…'
        : phase === 'summarizing' ? 'CafresoHQ is synthesizing…'
        /* Same rule as the footer hint below: the word "done" over a run
           that did not produce its closing summary is the modal agreeing
           with itself and not with what happened. */
        : summaryFail ? 'reports in — no closing summary'
        : 'done — archive or copy'}
      size="lg"
      footer={
        <>
          {/* "Docs" was a destination the code never wrote to. `archive()`
              builds a DONE TASK carrying the full report and hands it to
              `onArchiveStandup`, which does `setTasks(...)` — nothing goes
              near the vault. Verified on a real stand-up: the modal said
              "✓ archived to Docs" and the cabinet had no `Docs/` folder at
              all. The archive is genuine and the report is readable; only
              the signpost pointed somewhere that doesn't exist.

              Whether an end-of-day report *should* live in the cabinet
              rather than the task board is a product decision, noted in the
              doc rather than made silently here. */}
          {/* The one line under a finished stand-up. It used to offer the
              archive and nothing else, whatever had happened upstairs — so
              a run whose closing summary never got written invited the boss
              to file it with no hint that the thing they opened the modal
              FOR was missing. §7: state it, and name the door. RE-RUN is
              that door and it is already in this footer, so the sentence
              points at it rather than inventing a second one. */}
          <div className="hint" style={{marginRight: 'auto'}}>{
            copied === true ? '✓ copied'
            : copied === false ? 'copy blocked — check browser permission'
            : archived ? '✓ saved to your task board'
            : phase !== 'done' ? ''
            : summaryFail === 'stopped'
              ? 'you stopped this before the summary — RE-RUN for a full one, or ARCHIVE the reports as they are'
            : summaryFail
              ? 'the reports are here; no closing summary — RE-RUN to try again, or ARCHIVE the reports as they are'
            : 'tap ARCHIVE to keep this on your task board'
          }</div>
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
          {/* Nobody hired yet. The preflight below would otherwise read
              "0 of 0 agents · cap 1200 tok/each · 45s timeout" over an
              empty list, with the START button not rendered at all — a
              technical readout about a meeting with nobody in it, and no
              way forward. §7: a block states the reason AND the route.
              Every other empty state on the floor offers the action (a
              vacant room shows "+ HIRE", the empty board shows starter
              cards), so this one does too. */}
          {phase === 'idle' && reports.length === 0 && agents.length === 0 && (
            <div className="standup-preflight">
              <div className="empty-title">No coworkers yet</div>
              <div className="empty-sub">A stand-up is your team reporting back — hire someone first and they'll have something to report.</div>
              {onHire && (
                <button className="px-btn primary" style={{marginTop:10}} onClick={onHire}>+ HIRE YOUR FIRST COWORKER</button>
              )}
            </div>
          )}
          {phase === 'idle' && reports.length === 0 && agents.length > 0 && (
            <div>
              <div className="standup-preflight">
                <div className="empty-title">Run today's stand-up?</div>
                {/* The empty-state branch immediately above was rewritten
                    for §6/§7, and its own comment quotes the string it was
                    replacing: "0 of 0 agents · cap 1200 tok/each · 45s
                    timeout … a technical readout about a meeting with nobody
                    in it". The very next branch — the one that actually runs
                    — was still that readout, word for word. Fixing the empty
                    case and leaving the populated one is the same shape as
                    renaming "iter" on the night-shift card and leaving four
                    siblings standing.

                    Calling your team together should not read like a config
                    dump. The numbers a boss actually needs are who is coming
                    and how long it might take; the exact cap stays in the
                    tooltip for anyone who wants it. */}
                <div className="empty-sub"
                     title={`Each coworker gets up to ${STANDUP_MAX_TOKENS} tokens and ${(STANDUP_TIMEOUT_MS/1000)|0} seconds to report.`}>
                  {participating.length} of {agents.length} coworker{agents.length===1?'':'s'} · a short report from each · up to {(STANDUP_TIMEOUT_MS/1000)|0}s before someone is counted as not reporting
                  {localCount > 0 && <span className="warn"> · ⚠ {localCount} of them run{localCount===1?'s':''} on your own machine, so this may be slow</span>}
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
                          {/* §6, binding: raw model ids never appear outside desktop-mode
                              surfaces and settings. This chip was printing
                              "GOOGLE/GEMMA-3-27B-IT" straight from the id (only the
                              routing prefix stripped) — brainName() is the same
                              formatting-only pass the coworker card already uses. */}
                          {local && <span className="model-chip local">{brainName(a)}</span>}
                          {!local && a.model && <span className="model-chip cloud">{brainName(a)}</span>}
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

/* ── HQ GAZETTE — the Morning Report (Sprint 3) ─────────────────────────────
   Shown once on boot after >4h away: front-page stats, per-agent columns, a
   money box, and REPLAY — which closes the paper and re-enacts the night on
   the office floor by re-dispatching condensed cafresohq:agentTool events.
   Reduced-motion users just read the list. */
function MorningReportModal({ report, onClose, onGoToOffice }) {
  if (!report) return null;
  const fmtT = (ts) => new Date(ts).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  const byAgent = {};
  report.activity.forEach(a => {
    const nm = a.agentName || 'HQ';
    (byAgent[nm] = byAgent[nm] || []).push(a);
  });
  /* Four columns is a layout cap, not a claim that four coworkers were
     active. Nothing said so, and a boss with six hires saw four panels and
     no hint the other two existed — a silent truncation on the one screen
     that exists to summarise the whole night. Same rule this repo already
     applies elsewhere: bound coverage if you must, but say what was
     dropped. (The per-coworker event list caps at 5 and is already
     self-labelling — its header prints the TRUE total, `NAME · 12`.) */
  const allAgents = Object.entries(byAgent);
  const cols = allAgents.slice(0, 4);
  const hiddenAgents = allAgents.length - cols.length;
  const anchored = report.receipts.filter(r => r.verifyUrl);
  const reduced = typeof window !== 'undefined' && window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const replay = () => {
    /* The re-enactment plays on the FLOOR, and closing the paper only
       reveals whatever was behind it. A boss who opened the Gazette from
       Chat, Tasks or the Vault got 15 seconds of animation on a view they
       were not looking at — a button that appears to do nothing. Go to the
       office first, then close. */
    if (onGoToOffice) onGoToOffice();
    onClose();
    const evs = report.activity.slice(0, 24).reverse();
    /* §4: an animation must never claim work that is not happening. This
       re-enactment drives the SAME desk lights and visit lines as a live
       run, and until now it did so with nothing on screen to say so — a
       boss who clicked REPLAY watched their coworkers appear to work on
       jobs that finished hours ago. The floor now shows a band for the
       duration; `end` is scheduled past the last event's own 450ms
       tail so the band outlives the last light. */
    const REPLAY_MS = evs.length * 600 + 700;
    /* MOUNT_MS, and the first cut did not have it. `onGoToOffice()` and
       `onClose()` are React state updates, so the office view is not on
       screen yet when this function continues — dispatching the band's
       start event synchronously fired it into a floor whose listener had
       not mounted, and the band never appeared. Measured: navigation
       landed on OFFICE correctly, band false at 1200ms.

       The same beat matters for the re-enactment itself: the first
       synthetic tool events go out at i * 600, so i = 0 would have been
       swallowed by the same unmounted floor. Delaying the whole sequence
       fixes both. */
    const MOUNT_MS = 350;
    setTimeout(() => {
      try {
        window.dispatchEvent(new CustomEvent('cafresohq:replay', { detail: { phase: 'start' } }));
        setTimeout(() => window.dispatchEvent(
          new CustomEvent('cafresohq:replay', { detail: { phase: 'end' } })), REPLAY_MS);
      } catch (_e) {}
    }, MOUNT_MS);
    evs.forEach((a, i) => {
      setTimeout(() => {
        try {
          window.dispatchEvent(new CustomEvent('cafresohq:agentTool', {
            detail: { phase: 'start', name: (a.action || 'WORK').toUpperCase(), arg: a.text || '', agentId: a.agentId, agentName: a.agentName },
          }));
          setTimeout(() => {
            window.dispatchEvent(new CustomEvent('cafresohq:agentTool', {
              detail: { phase: 'done', name: (a.action || 'WORK').toUpperCase(), arg: a.text || '', agentId: a.agentId, agentName: a.agentName },
            }));
          }, 450);
        } catch (_e) {}
      }, MOUNT_MS + i * 600);
    });
  };
  return (
    <OcModal open onClose={onClose} title="🗞 HQ GAZETTE" subtitle={`morning report · while you were away since ${fmtT(report.since)}`} size="lg"
      footer={
        <>
          {/* "THE NIGHT" is only true when a night shift actually ran. This
              button is gated on activity, not on nightRuns, so on an office
              that has never run one it promised a night that did not
              happen. Say which it is. */}
          {!reduced && report.activity.length > 0 && (
            <button className="px-btn secondary" style={{ marginRight: 'auto' }} onClick={replay}>
              {(report.nightRuns || []).length > 0 ? '▶ REPLAY THE NIGHT' : '▶ REPLAY WHAT HAPPENED'}
            </button>
          )}
          <button className="px-btn primary" onClick={onClose}>TO WORK</button>
        </>
      }>
      {(report.nightRuns || []).length > 0 && (
        <div className="cb-panel" style={{ marginBottom: 'var(--sp-4)' }}>
          <div className="lbl">🌙 NIGHT SHIFT — THE LEAD STORY</div>
          <div className="tiny" style={{ marginTop: 2 }}>
            Your coworkers worked while you were gone: {report.nightRuns.length} run{report.nightRuns.length === 1 ? '' : 's'},
            {' '}{report.nightRuns.reduce((n, r) => n + (r.writes || []).length, 0)} note{report.nightRuns.reduce((n, r) => n + (r.writes || []).length, 0) === 1 ? '' : 's'} written to the vault.
          </div>
          {report.nightRuns.slice(0, 5).map(r => (
            <div key={r.id} style={{ marginTop: 3 }}>
              <div className="tiny">
                {r.lastError ? '⚠' : '✓'} <b>{r.agentName || r.agentId}</b> · {String(r.topic || '').slice(0, 50)} ·
                {' '}{r.iterations} round{r.iterations === 1 ? '' : 's'} · {(r.writes || []).length} notes
                {/* 90, not 60: snagCause/officeCause cap their own sentences at
                    90 (with an ellipsis), so a 60-char slice here truncated the
                    office's OWN honest sentences mid-clause — "that brain isn't
                    signed in yet — add it in Settings, or give" loses the route
                    out, which is the half §7 exists for. A display cap below the
                    producer's cap is a silent editor. */}
                {/* The error goes FIRST, and it is no longer an else-branch of
                    the summary. `run_mission` only refreshes `summary` on a
                    clean round, so a night that worked for five rounds and
                    fabricated on the sixth carries BOTH — and this line used
                    to print the good round's sentence and drop the office's
                    correction entirely. Measured on a seeded run: the boss
                    read "Wrote 1. Next iteration could explore refinery
                    margins…" while `lastError` said "said it saved a note, but
                    nothing reached the vault". One ⚠ was the only difference
                    between that row and the row below it, which was real.
                    The two sibling surfaces that show the same runs — the
                    Night Shift panel and the terminal's `night` listing —
                    have always rendered lastError unconditionally. The
                    Gazette was the one that suppressed it, on the one screen
                    that exists BECAUSE nobody was watching. */}
                {r.lastError ? ` — ${String(r.lastError).slice(0, 90)}`
                  : r.summary ? ` — ${String(r.summary).slice(0, 80)}` : ''}
              </div>
              {/* …and the summary is not thrown away, it is ATTRIBUTED. On the
                  fabrication case the summary IS the false claim, so printing
                  it unlabelled beside the correction just restages the
                  argument. "said" — not "wrote" — because the sentence above
                  it is the office saying nothing was written. */}
              {r.lastError && r.summary && (
                <div className="tiny" style={{ marginLeft: 12, opacity: 0.75 }}>
                  {`${r.agentName || r.agentId} said: "${String(r.summary).slice(0, 80)}"`}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="row" style={{ gap: 'var(--sp-4)', flexWrap: 'wrap', marginBottom: 'var(--sp-4)' }}>
        <div className="cb-panel" style={{ flex: 1, minWidth: 120 }}>
          <div className="lbl">ACTIONS</div>
          {/* `activityTotal`, not `activity.length` — the latter is the
              80-row display slice, so a long absence reported the CAP as
              the count. `??` keeps a replayed older report readable. */}
          <div style={{ fontSize: 22 }}>{report.activityTotal ?? report.activity.length}</div>
          {report.activityHidden > 0 && (
            <div className="tiny">showing the {report.activity.length} most recent below</div>
          )}
        </div>
        {/* DELIVERABLES counted `report.receipts.length` — RECEIPTS, which
            are approval and tool records, not things filed to the cabinet.
            Measured on a real night: six notes landed in `Deliveries/`, the
            activity log held six `artifact` rows, and this tile read **0**.
            The one screen whose whole job is "what did my business produce
            while I was away" reported that it produced nothing.

            Deliveries are `action: 'artifact'`, logged only when
            `fileDelivery` really returned a path. (This comment used to
            claim the Situation Wall's 📦 counter reads the same events. It
            does not — it counts tasks carrying an `artifactPath`. Two
            different sources over two different windows, so the numbers
            are not expected to agree.) The anchored sub-line
            stays on receipts, because that one genuinely is about
            receipts. */}
        <div className="cb-panel" style={{ flex: 1, minWidth: 120 }}>
          <div className="lbl">DELIVERABLES</div>
          <div style={{ fontSize: 22 }}>{report.artifactTotal ?? report.activity.filter(a => a.action === 'artifact').length}</div>
          {anchored.length > 0 && <div className="tiny">⛓ {anchored.length} receipt{anchored.length === 1 ? '' : 's'} anchored on-chain</div>}
        </div>
        <div className="cb-panel" style={{ flex: 1, minWidth: 120 }}>
          <div className="lbl">MONEY</div>
          <div style={{ fontSize: 22 }}>☕{report.tips.length} 💰{report.paydays.length}</div>
          <div className="tiny">tips · paydays</div>
        </div>
      </div>
      {cols.length > 0 && (
        <div className="row" style={{ gap: 'var(--sp-4)', flexWrap: 'wrap', alignItems: 'flex-start' }}>
          {cols.map(([nm, acts]) => (
            <div key={nm} className="cb-panel" style={{ flex: 1, minWidth: 180 }}>
              <div className="lbl">{nm.toUpperCase()} · {acts.length}</div>
              {acts.slice(0, 5).map(a => (
                <div key={a.id} className="tiny" style={{ marginTop: 3 }}>
                  {a.action === 'tip' ? '☕' : a.action === 'payday' ? '💰' : '·'} {String(a.text || a.action || '').slice(0, 70)}
                </div>
              ))}
            </div>
          ))}
          {hiddenAgents > 0 && (
            <div className="tiny" style={{ alignSelf: 'center', opacity: 0.8 }}>
              +{hiddenAgents} more coworker{hiddenAgents === 1 ? '' : 's'} were busy — full log in the Team inbox
            </div>
          )}
        </div>
      )}
      {anchored.length > 0 && (
        <div className="cb-panel" style={{ marginTop: 'var(--sp-4)' }}>
          <div className="lbl">⛓ VERIFIABLE WORK</div>
          {anchored.slice(0, 6).map(r => (
            <div key={r.id} className="tiny" style={{ marginTop: 3 }}>
              {r.title.slice(0, 60)} — <a href={r.verifyUrl} target="_blank" rel="noopener noreferrer">verify #{r.chainId}</a>
            </div>
          ))}
        </div>
      )}
    </OcModal>
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
          <button className="px-btn ghost" style={{fontSize: 'var(--text-9)', marginRight: 'auto'}} onClick={async ()=>{ if (await window.hqConfirm('Clear all receipts? Audit trail is lost.', { danger: true, okLabel: 'Clear all' })) onClear(); }}>CLEAR ALL</button>
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
              {/* What was actually authorised. The title above is the
                  REQUESTER's summary of its own request — an audit trail
                  that keeps only that records the asker's words, not the
                  act. Receipts written before this shipped have no detail
                  and simply omit the box; nothing is invented for them. */}
              {r.detail && <pre className="ap-detail rc-detail">{r.detail}</pre>}
              {/* What the stamp DID. For `publish` the stamp is also the act,
                  and the act has three endings — shipped, preview only,
                  didn't make it out — which the row above cannot tell apart:
                  it says the boss approved, which stays true in all three.
                  The stamp column is left alone for the same reason (it is
                  the boss's ✓, and it was given). Receipts stamped before
                  this shipped carry no outcome and simply omit the line;
                  nothing is guessed for them, same rule as r.detail. */}
              {r.outcomeText && (
                <div className="rc-outcome tiny" style={{
                  margin: '3px 0 4px',
                  color: r.outcome === 'failed' ? 'var(--error)' : 'inherit',
                  opacity: r.outcome === 'failed' ? 1 : 0.85,
                }}>
                  {r.outcome === 'shipped' ? '🚀 ' : (r.outcome === 'preview' ? '🔗 ' : '⚠ ')}
                  {r.outcomeText}
                </div>
              )}
              <div className="rc-meta">
                <span>by {r.by}</span>
                <span>·</span>
                {r.cwd && <><span>in {r.cwd}</span><span>·</span></>}
                <span>{r.kind || (r.amount ? '$'+r.amount : 'action')}</span>
                <span>·</span>
                <span>{fmt(r.decidedAt)}</span>
                {r.verifyUrl && (
                  <>
                    <span>·</span>
                    <a href={r.verifyUrl} target="_blank" rel="noopener noreferrer"
                       title="Publicly verifiable — anchored on the Internet Computer"
                       onClick={(e) => e.stopPropagation()}>⛓ on-chain #{r.chainId}</a>
                  </>
                )}
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
          <div style={{minWidth:0}}>
            <div className="ap-title">{p.elevated ? '🛡 ' : ''}{p.title}</div>
            {/* The actual thing being authorised, verbatim. The title above
                is the REQUESTER's summary of its own request — this gate
                exists to catch a summary that doesn't match the action, so
                the boss has to be able to see both. */}
            {/* The red left rule is tuned for a shell command about to run.
                A hire proposal is not that — it is somebody making a case,
                and colouring it like a hazard tells the boss to be afraid of
                the wrong thing (§5). Inline rather than a new class because
                the only difference is one border colour. */}
            {p.detail && (
              <pre className="ap-detail"
                   style={p.elevated ? undefined : { borderLeftColor: 'var(--ink-3)' }}>
                {p.detail}
              </pre>
            )}
            {/* Who is actually asking for file and shell access.

                Every fact below was already collected at request time under
                a comment reading "Snapshot context for the boss to review",
                and none of it was ever shown. It matters most in the case
                the boss cannot otherwise detect: a TRANSIENT helper — one
                coworker spawned by another, never hired, gone at the end of
                the run — asking for the run of the filesystem. On the old
                card that request was indistinguishable from one made by
                somebody the boss hired themselves. */}
            {p.kind === 'grant-elevation' && p.elevationRequest && (() => {
              const er = p.elevationRequest;
              const tools = (er.currentTools || []).filter(Boolean);
              const senior = er.reportsToName || null;
              return (
                <div className="ap-sub" style={{ marginTop: 2 }}>
                  {er.isTransient
                    ? <span style={{ color: '#c44' }}>
                        ⚠ a temporary helper{senior ? ` ${senior} spawned` : ' spawned'} mid-run
                        {' '}— you did not hire them
                      </span>
                    : er.isAssistant
                      ? <span>an assistant{senior ? ` reporting to ${senior}` : ''}</span>
                      : <span>someone you hired</span>}
                  {' · '}
                  {tools.length
                    ? `already has ${tools.join(', ')}`
                    : 'has no tools yet'}
                </div>
              );
            })()}
            <div className="ap-sub">
              by {p.by} · {p.amount ? '$' + p.amount : p.kind}
              {p.cwd && <span> · in {p.cwd}</span>}
              {p.elevated && <span style={{color:'#c44',marginLeft:6}}>· coworker waiting on your call</span>}
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

const CafresoHQV2 = { TaskBoard, MeetingRoom, MeetingPicker, FocusMode, ApprovalTray, ReceiptTray, ReceiptsModal, MorningReportModal, StandupModal, SEED_TASKS, SEED_MEMORY };

export { CafresoHQV2 };
