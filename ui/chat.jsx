import { Ico } from './primitives.jsx';
import { HQ } from '../hq-runtime.jsx';
import { Sprite } from '../sprites.jsx';
import { attachVisit, snagCause, snagOpener, snagSentence } from '../app/floor.jsx';
import { withHandoff, withRouteOut } from '../app/cast.jsx';
import { CafresoHQClient } from '../claude-client.jsx';
const { useState, useEffect, useLayoutEffect, useRef, useMemo, createContext, useContext } = React;
const THREADS = [
  { id: 'direct',   label: 'DIRECT',   icon: '📞', desc: 'You & CafresoHQ' },
  { id: 'team',     label: 'TEAM',     icon: '💬', desc: 'Your coworkers talking to each other' },
  { id: 'research', label: 'RESEARCH', icon: '🔬', desc: 'Research mission rounds' },
];

/* ---- Swipe-to-reply/DM wrapper for mobile chat messages ---- */
function SwipeMessage({ children, onReply, onDM, agentName }) {
  const ref = React.useRef(null);
  const touchRef = React.useRef(null);
  const [offset, setOffset] = React.useState(0);
  const [showActions, setShowActions] = React.useState(false);
  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768;

  // All hooks above — safe to conditionally render below
  if (!isMobile) return children;

  const onStart = (e) => {
    const t = e.touches[0];
    touchRef.current = { x: t.clientX, y: t.clientY };
    setShowActions(false);
  };
  const onMove = (e) => {
    if (!touchRef.current) return;
    const dx = e.touches[0].clientX - touchRef.current.x;
    const dy = e.touches[0].clientY - touchRef.current.y;
    if (Math.abs(dy) > Math.abs(dx)) { touchRef.current = null; setOffset(0); return; }
    if (dx < 0) { e.preventDefault(); setOffset(Math.max(dx, -100)); }
  };
  const onEnd = () => {
    if (offset < -50) { setShowActions(true); setOffset(-80); }
    else { setOffset(0); setShowActions(false); }
    touchRef.current = null;
  };

  return (
    <div className="msg-swipe-wrapper">
      <div className="msg-swipe-actions" style={{ opacity: showActions ? 1 : Math.min(1, Math.abs(offset) / 60) }}>
        {onReply && <button className="msg-swipe-btn" onClick={() => { setOffset(0); setShowActions(false); onReply(); }} title="Reply">↩</button>}
        {onDM && agentName && <button className="msg-swipe-btn" onClick={() => { setOffset(0); setShowActions(false); onDM(); }} title={`DM ${agentName}`}>💬</button>}
      </div>
      <div style={{ transform: `translateX(${offset}px)`, transition: touchRef.current ? 'none' : 'transform 0.2s ease' }}
        onTouchStart={onStart} onTouchMove={onMove} onTouchEnd={onEnd} ref={ref}>
        {children}
      </div>
    </div>
  );
}

/* `onOpenResearch` is the missions door, handed in the same way `onHire`
   hands in the front desk. Without it this panel could only ever DESCRIBE
   the way to start a mission, and what it described was a button called
   "🔬 RESEARCH in the topbar" that no viewport has ever rendered: the
   topbar carries LIVE / WORKING / HIRED / 📬 INBOX / ⌗ ROOMS ▾ / 🔔, and
   the missions door lives one level down inside ROOMS. The research
   thread is read-only, so that door was the only way to start a mission
   and the office was naming it wrong. */
function ChatPanel({ agents, chat, setChat, projects = [], meetings = [], setMeetings, onDelegate, onCeoUsage, onApprovalRequest, onDispatchToAgent, onPinAsTask, onInferTaskAssignment, backendDown = false, onStopTurn = null, onHire = null, onOpenResearch = null, turnEpochRef = null, onBossAsk = null, onBossAskSettled = null }) {
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [showDelegate, setShowDelegate] = useState(false);
  /* A brain has gone quiet past the point where dots alone stay honest.
     claude-client fires this from inside the stream-head wait; it clears
     itself so a bubble that starts flowing stops apologising. */
  const [brainSlow, setBrainSlow] = useState(false);
  useEffect(() => {
    let clearTimer = null;
    const onSlow = () => {
      setBrainSlow(true);
      clearTimeout(clearTimer);
      /* Long enough to outlive the local budget, so the notice doesn't
         blink off while the model is genuinely still loading. */
      clearTimer = setTimeout(() => setBrainSlow(false), 120000);
    };
    window.addEventListener('cafresohq:brainSlow', onSlow);
    return () => { window.removeEventListener('cafresohq:brainSlow', onSlow); clearTimeout(clearTimer); };
  }, []);
  /* activeThread persists across reloads / view switches so navigating away
     from chat and back doesn't dump the user into the 'direct' thread. */
  const _ACTIVE_THREAD_KEY = 'cafresohq_chat_active_thread_v1';
  const [activeThread, _setActiveThread] = useState(() => {
    try {
      const saved = localStorage.getItem(_ACTIVE_THREAD_KEY);
      return saved && saved.length ? saved : 'direct';
    } catch (_e) { return 'direct'; }
  });
  const setActiveThread = React.useCallback((next) => {
    _setActiveThread(prev => {
      const value = typeof next === 'function' ? next(prev) : next;
      try { localStorage.setItem(_ACTIVE_THREAD_KEY, String(value || 'direct')); } catch (_e) {}
      return value;
    });
  }, []);

  /* Handoff mode: when CafresoHQ emits [HANDOFF_TO: name], the user converses
     directly with that specialist until they say "back to CafresoHQ" or click
     the Return button. Persisted per-thread so navigation/reload doesn't drop
     the boss back to the orchestrator mid-conversation. */
  const _HANDOFF_KEY = 'cafresohq_chat_handoffs_v1';
  const [handoffMap, _setHandoffMap] = useState(() => {
    try { return JSON.parse(localStorage.getItem(_HANDOFF_KEY) || '{}') || {}; }
    catch (_e) { return {}; }
  });
  const setHandoffFor = React.useCallback((thread, agentName) => {
    _setHandoffMap(prev => {
      const next = { ...prev };
      if (agentName) next[thread] = agentName;
      else delete next[thread];
      try { localStorage.setItem(_HANDOFF_KEY, JSON.stringify(next)); } catch (_e) {}
      return next;
    });
  }, []);
  const handoffAgentName = handoffMap[activeThread] || null;
  const handoffAgent = handoffAgentName
    ? agents.find(a => a.name.toLowerCase() === handoffAgentName.toLowerCase()) || null
    : null;
  const returnToCEO = React.useCallback(() => {
    if (handoffAgentName) {
      setHandoffFor(activeThread, null);
      setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
        text: `(returned to CafresoHQ from ${handoffAgentName})`, thread: activeThread }]);
    }
  }, [activeThread, handoffAgentName, setHandoffFor, setChat]);
  const screenRef = useRef(null);
  const bottomRef = useRef(null);
  const abortRef = useRef(null);
  /* The current chat, readable from an async continuation.

     The `chat` prop is captured per render, so a handler that has awaited
     a dispatch is holding a snapshot from before the coworkers answered.
     The send path works around that with `setChat(prev => { captured =
     prev; return … })` — and that only reads back because React happens
     to run the FIRST updater of a fresh event eagerly. The synthesis pass
     used the same line after a stream's worth of queued updates, where it
     does not: measured on 2026-08-15, `immediate=0, afterTick=20`. The
     capture was read one tick before it was written, every time.

     A ref written on every render has no such window. */
  const chatRef = useRef(chat);
  chatRef.current = chat;

  const [searchQuery, setSearchQuery] = useState('');
  const [openActionsId, setOpenActionsId] = useState(null);
  const _isMobileChat = typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;

  /* @-autocomplete state.
       mention: { active, prefix, start, hits, idx } | null
     - active: popup is showing
     - prefix: chars typed after the @ (lower-case for fuzzy match)
     - start: index in `input` where the @ lives, so we can splice
     - hits: filtered agents matching the prefix
     - idx: highlighted hit (arrow keys cycle, Enter/Tab inserts). */
  const [mention, setMention] = useState(null);
  const composerRef = useRef(null);

  /* Cross-component bridge: anyone can dispatch
       window.dispatchEvent(new CustomEvent('cafresohq:set-active-thread', { detail: 'meeting:xxx' }))
     to switch the chat panel to a specific thread. Used by the meeting
     create modal and the project assignment UI to jump straight into a
     newly-opened room. */
  useEffect(() => {
    const onSet = (e) => {
      const target = e && e.detail;
      if (typeof target === 'string' && target) setActiveThread(target);
    };
    /* Sister bridge: prefill the composer with text. Used by the Tasks
       view's "→ ASSIGN" button to drop a task into chat ready to send. */
    const onPrefill = (e) => {
      const text = e && e.detail;
      if (typeof text !== 'string') return;
      setInput(text);
      requestAnimationFrame(() => {
        if (composerRef.current) {
          composerRef.current.focus();
          // Cursor at end so the boss can edit before sending.
          const end = text.length;
          composerRef.current.selectionStart = composerRef.current.selectionEnd = end;
        }
      });
    };
    window.addEventListener('cafresohq:set-active-thread', onSet);
    window.addEventListener('cafresohq:prefill-composer', onPrefill);
    return () => {
      window.removeEventListener('cafresohq:set-active-thread', onSet);
      window.removeEventListener('cafresohq:prefill-composer', onPrefill);
    };
  }, []);

  /* Filter visible messages by active thread. Untagged messages default to
     'direct' for back-compat with chat persisted before threading existed.
     project:<id> and meeting:<id> are dynamic per-room threads. */
  const visibleChat = chat.filter(m => {
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      return (m.text || '').toLowerCase().includes(q);
    }
    const t = m.thread || 'direct';
    return t === activeThread;
  });

  /* Thread message counts so the user can see at a glance where activity is.
     Per-room threads (project:<id>, meeting:<id>) get their own counter; the
     static threads roll up like before. */
  const threadCounts = {};
  for (const m of chat) {
    const t = m.thread || 'direct';
    threadCounts[t] = (threadCounts[t] || 0) + 1;
  }

  /* Dynamic thread tabs: static tabs first, then any project that has at
     least one assigned agent, then every meeting (meetings only exist when
     intentionally created so all of them get a tab). Filtering by
     "has assigned agents" keeps the strip from filling up with empty
     project tabs the user never used for collaboration. */
  const dynamicProjectTabs = (projects || [])
    .filter(p => Array.isArray(p.agentIds) && p.agentIds.length > 0)
    .map(p => ({
      id: 'project:' + p.id, label: p.name.toUpperCase().slice(0, 14),
      icon: '📁', desc: `Project: ${p.name} · ${p.agentIds.length} assigned`,
      kind: 'project', refId: p.id,
    }));
  const dynamicMeetingTabs = (meetings || []).map(mt => ({
    id: 'meeting:' + mt.id, label: mt.name.toUpperCase().slice(0, 14),
    icon: '📋', desc: `Meeting: ${mt.name} · ${(mt.agentIds || []).length} attendees`,
    kind: 'meeting', refId: mt.id,
  }));
  const allTabs = [...THREADS, ...dynamicProjectTabs, ...dynamicMeetingTabs];

  /* If the active thread's tab disappeared (meeting deleted, project's last
     agent unassigned), fall back to DIRECT instead of stranding the user on a
     blank chat with no visible tab. */
  const tabIdsKey = allTabs.map(t => t.id).join('|');
  useEffect(() => {
    if (!allTabs.some(t => t.id === activeThread)) setActiveThread('direct');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeThread, tabIdsKey]);

  /* Resolve participant agents for the active thread. Used both to fan out
     a sent message and to render the participant chips at the top of the
     thread so the boss can see who's in the room at a glance. */
  const activeRoom = (() => {
    if (activeThread.startsWith('project:')) {
      const pid = activeThread.slice('project:'.length);
      const p = (projects || []).find(p => p.id === pid);
      if (!p) return null;
      const ids = p.agentIds || [];
      return {
        kind: 'project', name: p.name, refId: pid,
        participants: agents.filter(a => ids.includes(a.id)),
      };
    }
    if (activeThread.startsWith('meeting:')) {
      const mid = activeThread.slice('meeting:'.length);
      const m = (meetings || []).find(m => m.id === mid);
      if (!m) return null;
      const ids = m.agentIds || [];
      return {
        kind: 'meeting', name: m.name, refId: mid,
        participants: agents.filter(a => ids.includes(a.id)),
        topic: m.topic, createdAt: m.createdAt,
      };
    }
    return null;
  })();

  /* Stick-to-bottom scrolling. Follow the stream only while the user is
     already at (or near) the bottom; scrolling up to read scrollback pauses
     auto-scroll instead of fighting it, and scrolling back down (or switching
     threads) re-engages.

     Pinning writes screenRef.scrollTop directly rather than
     bottomRef.scrollIntoView() — scrollIntoView walks up the ancestor chain
     and can also nudge the window/parent, which is what made the older
     version drift off the newest message. A direct scrollTop write stays
     contained to the chat viewport. */
  const stickRef = useRef(true);
  const pinToBottom = React.useCallback(() => {
    const el = screenRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);
  useEffect(() => {
    const el = screenRef.current;
    if (!el) return;
    const onScroll = () => {
      stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);
  /* Switching threads always re-engages stick and jumps to the newest
     message — you never land mid-scrollback in a thread you just opened. */
  useLayoutEffect(() => { stickRef.current = true; pinToBottom(); }, [activeThread]);
  /* Follow content growth via a MutationObserver instead of a render-only
     effect. New messages, streamed tokens, AND late layout shifts (markdown
     or images resolving height after first paint) all mutate the scroll
     subtree — a render-only effect misses the async ones and leaves the view
     stranded a few lines above the true bottom. rAF-coalesced so a burst of
     streamed tokens collapses into one scroll. */
  useEffect(() => {
    const el = screenRef.current;
    if (!el || typeof MutationObserver === 'undefined') return;
    let raf = 0;
    const follow = () => { raf = 0; if (stickRef.current) el.scrollTop = el.scrollHeight; };
    const schedule = () => { if (!raf) raf = requestAnimationFrame(follow); };
    const mo = new MutationObserver(schedule);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    return () => { mo.disconnect(); if (raf) cancelAnimationFrame(raf); };
  }, []);

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;
    /* Hard gate, not just the banner: with no live container every path
       below silently no-ops (the POST hits a dead origin and streams zero
       tokens), so the user watched an empty bubble appear. Refuse loudly
       and keep their draft in the composer. */
    if (backendDown) {
      if (window.cafresohqToast) window.cafresohqToast.error('Your office is offline — reconnecting…');
      return;
    }

    /* Decided ONCE per boss turn, above every route, and deliberately not
       on each reply. The boss asked to put a page live; publishing is real,
       implemented, and switched off, so no coworker on any route was going
       to be handed the tool. Attaching this to replies instead would print
       it three times on a two-way fan-out — the CEO's and both
       specialists' — which is the shape of #64. The turn is the thing that
       is true here, not any one participant's answer.

       It goes on screen only. Unlike the stray-name note it explains
       nothing about routing, so the coworker does not need it, and telling
       a model its own tools are missing is an invitation to narrate the
       absence rather than do the rest of the job.

       DECIDED here, EMITTED after the boss's own bubble on whichever route
       this turn takes. The first draft decided AND emitted down at the
       @mention block, which sits below two routes that return before it
       (a populated room, and /brainstorm) and above every user echo. Both
       halves of that placement were wrong, and both were measured: in a
       meeting room the note never fired at all, and on the @mention path
       it printed above the request it answers, so on screen the office
       said "nothing can go live from here yet" directly under the PREVIOUS
       reply. A note above its own question points at the wrong exchange. */
    const doorNoteText = HQ.publishDoorNote
      ? HQ.publishDoorNote(text, HQ.icpPublishEnabled && HQ.icpPublishEnabled())
      : null;
    const emitDoorNote = (thread) => {
      if (!doorNoteText) return;
      setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
        text: doorNoteText, thread }]);
    };

    /* If the boss is composing inside a project or meeting room, the default
       behavior is "send to everyone in the room" — fan out in parallel,
       both/all replies stream into THIS thread. The boss can still narrow
       the recipient list with explicit @mentions (those are honoured below
       via extractAllMentions and respect the active thread). */
    if (activeRoom && activeRoom.participants.length) {
      // Explicit @mentions inside a room override the default "send to all"
      const explicit = HQ.extractAllMentions(text, activeRoom.participants.map(a => a.name));
      const recipients = explicit
        ? activeRoom.participants.filter(a => explicit.targetNames.some(n => n.toLowerCase() === a.name.toLowerCase()))
        : activeRoom.participants;
      if (recipients.length) {
        const body = explicit ? explicit.body : text;
        setInput('');
        const targetLabel = recipients.map(a => '@' + a.name).join(' ');
        setChat(prev => [...prev, {
          id: HQ.uid('m'), from: 'user', name: 'You',
          text, target: targetLabel, thread: activeThread,
        }]);
        emitDoorNote(activeThread);
        setStreaming(true);
        /* `userText` existed for exactly this and no caller ever set it, so
           every downstream surface that wanted "what the boss asked" had to
           slice the ASSEMBLED prompt instead. Here the boss's own words are
           right there.

           The catch clause is §7, same sweep as the standup/missions fixes:
           it used to read "(Miko bowed out: OpenRouter 503: {"error": …})",
           a raw dump introducing itself as a parenthetical system note.
           snagCause() supplies the clause; "bowed out" is already the
           subject+verb. Six call sites in this file had independently
           copy-pasted the same raw ${err.message}. */
        const bowOut = (a, err) => setChat(prev => [...prev, {
          id: HQ.uid('m'), from: 'system', name: 'HQ',
          text: `(${a.name} bowed out — ${snagCause(err && err.message || String(err))})`,
          thread: activeThread }]);
        try {
          if (activeRoom.kind === 'meeting') {
            /* A meeting takes turns. The seating modal promises attendees
               "they'll all see each other's replies", and until now that was
               simply false: all three were dispatched inside 19ms of each
               other, every prompt was assembled before anybody had spoken,
               and each one was told the others were "receiving the SAME
               request in parallel". Three monologues stacked in one thread
               is not a meeting, and the office said it was one at the exact
               moment the boss was choosing who to invite.
               Sequential costs wall-clock — that is what a meeting costs —
               and it buys the thing the room is for: attendee two can
               disagree with attendee one BY NAME, and the boss watches the
               room fill in turn instead of three bubbles racing. */
            const heardSoFar = [];
            /* Turn-taking is exactly what makes this loop leak past a
               stop: aborting attendee two's stream does nothing to stop
               the loop from DISPATCHING attendee three — a brand-new run,
               launched after the boss said stop. The epoch is read at the
               top of every turn; a bump means the sweep ran and the
               meeting adjourns with the truth about who never spoke.

               The TURN epoch, which the office sweep bumps as well, so
               both buttons still adjourn: a meeting is the boss's turn,
               and ■ Stop is now scoped to exactly that. */
            const turnEpochAtStart = turnEpochRef ? turnEpochRef.current : null;
            for (const [turnIdx, a] of recipients.entries()) {
              if (turnEpochRef && turnEpochRef.current !== turnEpochAtStart) {
                const left = recipients.length - turnIdx;
                setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
                  text: `(meeting adjourned — you stopped it. ${left} attendee${left === 1 ? '' : 's'} never got their turn.)`,
                  thread: activeThread }]);
                break;
              }
              try {
                const said = await onDispatchToAgent(a, body, {
                  userText: body,
                  suppressUserEcho: true,
                  threadOverride: activeThread,
                  coParticipants: recipients.filter(o => o.id !== a.id).map(o => ({ name: o.name, role: o.role })),
                  heardSoFar: heardSoFar.slice(),
                  meetingTurn: true,
                });
                /* Only what they actually SAID gets passed on. A turn that
                   failed, or came back empty, must not enter the transcript
                   as a silent gap the next speaker is asked to build on. */
                if (said && String(said).trim()) {
                  heardSoFar.push({ name: a.name, role: a.role, text: String(said) });
                }
              } catch (err) {
                bowOut(a, err);
              }
            }
          } else {
            await Promise.all(recipients.map(a =>
              onDispatchToAgent(a, body, {
                userText: body,
                suppressUserEcho: true,
                threadOverride: activeThread,
                coParticipants: recipients.filter(o => o.id !== a.id).map(o => ({ name: o.name, role: o.role })),
              }).catch(err => bowOut(a, err))
            ));
          }
        } finally {
          setStreaming(false);
        }
        return;
      }
      // Mentions referenced names not in this room — fall through with a
      // hint so the boss knows why nothing fired.
      setChat(prev => [...prev, {
        id: HQ.uid('m'), from: 'system', name: 'HQ',
        text: `(none of those mentions are in this room — participants: ${activeRoom.participants.map(a => '@' + a.name).join(' ')})`,
        thread: activeThread,
      }]);
      return;
    }

    /* /brainstorm <topic>  — broadcast topic to ALL hired agents and let
       them DM each other for one round. Uses the existing dispatch chain. */
    if (text.toLowerCase().startsWith('/brainstorm')) {
      const topic = text.replace(/^\/brainstorm\s*/i, '').trim();
      if (!topic) {
        setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ', text: 'Usage: /brainstorm <topic>', thread: 'direct' }]);
        return;
      }
      setInput('');
      setChat(prev => [...prev, { id: HQ.uid('m'), from: 'user', name: 'You', text, thread: 'team' }]);
      emitDoorNote('team');
      setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
        text: `🧠 Brainstorm: "${topic}" — asking ${agents.length} coworker${agents.length === 1 ? '' : 's'}. They will DM each other once and synthesize.`,
        thread: 'team' }]);
      const brainPrompt =
        `BRAINSTORM TOPIC: ${topic}\n\n` +
        `Open with your initial take in 2-3 sentences. ` +
        `Then DM at most ONE coworker (using [DM_TO: name]…[/DM_TO]) whose perspective you most want — ask a sharp follow-up. ` +
        `Do not chain further; one DM is the cap. Keep responses tight.`;
      setStreaming(true);
      try {
        // Fire all dispatches in parallel — each agent's DM chain is bounded
        // by the existing dmDepth check so this can't loop infinitely.
        await Promise.all(agents.map(a =>
          onDispatchToAgent && onDispatchToAgent(a, brainPrompt, { userText: null })
            .catch(err => {
              setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
                text: `(${a.name} bowed out — ${snagCause(err && err.message || String(err))})`, thread: 'team' }]);
            })
        ));
      } finally {
        setStreaming(false);
      }
      return;
    }

    /* @mention routing: "@kip pull X" goes straight to Kip; "@kip @plato …"
       fans out to BOTH (and any number of mentioned agents) in parallel,
       with both replies streaming inline into the SAME thread. Saves
       round-trips when the boss already knows who they want, and lets two
       agents weigh in on the same prompt without manually re-asking. */
    // The roster is what lets a coworker whose name has a space in it be
    // addressed at all — the front desk hires one called "Local Brain".
    const mentionAll = HQ.extractAllMentions(text, agents.map(a => a.name));
    /* Declared out here because it is written in the @mention block and
       read on the CEO path below — the two are the same turn. */
    let strayNote = null;

    if (mentionAll && onDispatchToAgent) {
      const matched = [];
      const unknown = [];
      for (const nm of mentionAll.targetNames) {
        const t = agents.find(a => a.name.toLowerCase() === nm.toLowerCase());
        if (t) matched.push(t); else unknown.push(nm);
      }
      // Drop dupes (case-folded) so a user who types @plato @plato by accident
      // doesn't get two streams.
      const dedup = []; const seenIds = new Set();
      for (const a of matched) { if (!seenIds.has(a.id)) { seenIds.add(a.id); dedup.push(a); } }

      if (dedup.length) {
        // Echo the user's message ONCE so the thread reads naturally.
        const targetThread = (typeof activeThread === 'string'
          && (activeThread === 'direct' || activeThread.startsWith('project:') || activeThread.startsWith('meeting:')))
          ? activeThread : 'direct';
        const targetLabel = dedup.map(a => '@' + a.name).join(' ');
        setInput('');
        setChat(prev => [...prev, {
          id: HQ.uid('m'), from: 'user', name: 'You',
          text, target: targetLabel, thread: targetThread,
        }]);
        emitDoorNote(targetThread);
        /* If this chat message originated from "→ CHAT" on a task card,
           the prefilled text includes a `_(from task TKID)_` footer. When
           the user actually @-mentions an agent and sends, infer the
           assignment and update the source task — solves the long-standing
           "I @-mentioned them but the task still says unassigned" bug. */
        if (onInferTaskAssignment) {
          const taskRef = String(text).match(/_\(from task ([\w-]+)\)_/);
          if (taskRef && taskRef[1] && dedup[0]) {
            // First-mentioned agent wins (matches the "primary recipient"
            // intuition when fanning out to multiple agents).
            onInferTaskAssignment(taskRef[1], dedup[0].id);
          }
        }
        if (unknown.length) {
          setChat(prev => [...prev, {
            id: HQ.uid('m'), from: 'system', name: 'HQ',
            text: `(unknown teammate${unknown.length > 1 ? 's' : ''}: ${unknown.map(n => '@' + n).join(', ')})`,
            thread: targetThread,
          }]);
        }
        setStreaming(true);
        try {
          // Fan-out in parallel; both agents stream into the same thread.
          // Each agent gets a coParticipants list so they know who else is
          // in the room and can write a complementary (not duplicate) reply.
          await Promise.all(dedup.map(a =>
            onDispatchToAgent(a, mentionAll.body, {
              userText: mentionAll.body,        // see the note on the sibling call
              suppressUserEcho: true,
              threadOverride: targetThread,
              coParticipants: dedup.filter(o => o.id !== a.id).map(o => ({ name: o.name, role: o.role })),
            }).catch(err => {
              setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
                text: `(${a.name} bowed out — ${snagCause(err && err.message || String(err))})`, thread: targetThread }]);
            })
          ));
        } finally {
          setStreaming(false);
        }
        return;
      }
      /* No matches at all — fall through to CEO so they can clarify, but
         SAY SO first. The `unknown` note above lives inside `if
         (dedup.length)`, so it only ever ran when some OTHER mention had
         matched: the one case where the boss most needs telling — they
         addressed somebody by name and nobody by that name exists — was
         the one case that said nothing and quietly handed the message to
         the CEO. Measured: "@Local In one sentence, disagree" to a roster
         holding "Local Brain", answered by the CEO, with no line anywhere
         saying the addressee had been changed. The CEO cannot clarify what
         it was never told, and the boss reads a reply to a question they
         believe went to a coworker. */
      if (unknown.length) {
        const targetThread = (typeof activeThread === 'string'
          && (activeThread === 'direct' || activeThread.startsWith('project:') || activeThread.startsWith('meeting:')))
          ? activeThread : 'direct';
        const team = agents.map(a => '@' + a.name).join(', ');
        /* Built once and kept, because it goes to TWO readers. On screen it
           is the line telling the boss their addressee was changed. In the
           CEO's context it is the only thing that explains why a message
           addressed to somebody else has arrived — and the comment above
           says exactly that: "The CEO cannot clarify what it was never
           told." It used to be told nothing, because this bubble only
           existed in state. */
        strayNote = {
          id: HQ.uid('m'), from: 'system', name: 'HQ',
          text: `(nobody here is called ${unknown.map(n => '@' + n).join(' or ')}`
                + (team ? ` — the team is ${team}` : ' — nobody is hired yet')
                + `. Sending this to CafresoHQ instead.)`,
          thread: targetThread,
        };
        setChat(prev => [...prev, strayNote]);
      }
    }

    setInput('');

    /* If a handoff is active for this thread, the user is talking to the
       specialist directly — skip CafresoHQ entirely. Magic phrase "back to
       CafresoHQ" returns control. */
    if (handoffAgent) {
      const lower = text.toLowerCase();
      if (lower.includes('back to cafresohq') || lower.includes('back to cafresohq') || lower.includes('back to ceo')) {
        returnToCEO();
        return;
      }
      setChat(prev => [...prev, {
        id: HQ.uid('m'), from: 'user', name: 'You',
        text, target: '@' + handoffAgent.name, thread: activeThread,
      }]);
      emitDoorNote(activeThread);
      setStreaming(true);
      try {
        await onDispatchToAgent(handoffAgent, text, {
          suppressUserEcho: true,
          threadOverride: activeThread,
        });
      } catch (err) {
        setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
          text: `(${handoffAgent.name} bowed out — ${snagCause(err && err.message || String(err))})`, thread: activeThread }]);
      } finally {
        setStreaming(false);
      }
      return;
    }

    /* Thread-stamp BOTH sides of the CEO exchange. Without it they defaulted
       to 'direct', so a user typing in an empty project/meeting room (zero
       participants falls through to this path) watched their message vanish
       from the room they were looking at.
       The state write is an APPEND — `[...chat, userMsg]` from a stale
       closure used to replace the whole array, erasing anything that had
       landed since the last render (agent DMs, research lines). An append
       cannot do that, whatever it is holding.

       What the CEO is SENT is built separately, from the ref. It used to
       be captured out of the updater above — `setChat(prev => { pendingChat
       = [...prev, userMsg]; return pendingChat; })` — which reads back only
       while this hook's queue is untouched, because React evaluates that
       first updater eagerly. The stray-name branch pushes to chat a few
       lines up, and on that path the queue is not untouched: `pendingChat`
       stayed `[]` and `chatToMessages([])` is `[]`, so the chief of staff
       was asked to reply to a conversation with nothing in it — no history
       and not even the boss's question. Reproduced on 2026-08-15 with
       "@Dana can you follow up on that margin thread?" against a roster of
       Vera and Kip: the request that left the office carried exactly one
       message, the system prompt. On screen it looked ordinary — the note,
       the question, a confident answer to neither.

       `setInput('')` above is not the same hazard: it is a different hook,
       and eager evaluation is per queue. That is precisely why this held
       for so long and then failed on one branch. */
    const userMsg = { id: HQ.uid('m'), from: 'user', name: 'You', text, thread: activeThread };
    const pendingChat = [...chatRef.current, ...(strayNote ? [strayNote] : []), userMsg];
    setChat(prev => [...prev, userMsg]);
    emitDoorNote(activeThread);
    /* File the ask. Below every early return above, because those paths
       (@mentions, the meeting room, /brainstorm, a live hand-off) each
       dispatch through onDispatchToAgent and are filed there — this is the
       one turn nothing else records. See recordBossAsk in app.jsx for what
       the registry looked like without it.

       `askId` is what everything the chief of staff does next chains onto,
       so one question stays one thread however many people it reaches. */
    const askId = onBossAsk ? onBossAsk(text) : null;
    /* Written by the CEO catch below, read at the end of the turn. The
       catch does not rethrow — it puts the snag in the bubble and lets the
       fan-out block run — so a try/finally around the whole turn would
       settle this record as if nothing had gone wrong. */
    let askErr = null;
    setStreaming(true);
    const ceoId = HQ.uid('m');
    setChat(prev => [...prev, { id: ceoId, from: 'ceo', name: 'CafresoHQ', text: '', streaming: true, thread: activeThread }]);
    const controller = new AbortController();
    abortRef.current = controller;
    const flush = HQ.throttleTokens(setChat, ceoId);
    /* Track DMs and handoff that CafresoHQ emits during the stream so the
       host can dispatch to specialists / switch the active responder after
       the orchestrator finishes its turn. */
    const ceoDms = [];
    let ceoHandoff = null;
    /* The fourth collection site, and the comment at the first one asked
       whoever added it to carry `failed` — a page that answered 403 and a
       page that was read are not the same visit, and `unverifiedSources`
       is the guard that has to tell them apart. */
    const ceoVisits = [];
    const onTool = (ev) => {
      if (ev.echo) ceoVisits.push({ name: ev.name, arg: ev.arg, echo: ev.echo, failed: !!ev.failed });
      if (ev.phase === 'dm') ceoDms.push({ to: ev.arg, body: ev.body });
      else if (ev.phase === 'handoff') ceoHandoff = { to: ev.arg, body: ev.body };
      /* The visit rides on the message, not in its text — see floor.jsx.
         The CEO looks things up too, and its bubble was the one where a
         forged visit was first caught. */
      else if (ev.phase === 'done') attachVisit(setChat, ceoId, ev);
    };
    try {
      await HQ.ceoStream(text, flush, { chat: pendingChat, agents, signal: controller.signal,
           onUsage: u => onCeoUsage && onCeoUsage(u),
           onTool,
           onHint: flush.note });
      flush.flushNow();
    } catch (err) {
      /* Kill any rAF flush scheduled just before the abort — it would fire
         AFTER this rewrite and overwrite the "(stopped)" marker with the
         raw truncated text. */
      flush.cancel();
      askErr = err;
      const stopped = err.name === 'AbortError';
      // Same raw-dump bug fixed everywhere else a run can fail this session (§7).
      setChat(prev => prev.map(m => m.id === ceoId
        /* §7 wants try again / ask differently / PICK ANOTHER COWORKER, and
           this is the surface where the third route matters most: it is the
           CEO failing, i.e. the front door, and the CEO's brain is the one
           thing a working floor tells you nothing about. Verified by driving
           the real failure — the boss got "couldn't reach that brain" and a
           RETRY that could only fail again, with Llama and Mika idle and
           working two feet away.

           Caught only because I reproduced the failure instead of assuming
           my edit to chatErrorText covered it: agent dispatches and the CEO
           stream have always been two different error-copy paths.

           …and being two paths cost a second time, on the emptiest office
           there is. Driven on a genuine first run — nobody hired, no key —
           the boss's first ever message came back as

             ⚠ hit a snag — couldn't reach that brain — it looks offline
               from here

           and ended there. withHandoff only ever offered rung one, so with
           an empty floor there was nobody to name and the sentence simply
           stopped: no route, and a diagnosis that promises a brain will be
           back when none was ever configured — two bubbles under the same
           office saying "We don't have a shared brain here". withRouteOut
           carries the rest of the ladder (hire, or bring a brain), and both
           paths now climb the same one.

           The spine goes too. snagSentence gives "hit a snag — <cause>",
           which is the INBOX's shape: those rows read "Kenji hit a snag —
           …" and need the verb because the name is already there. Here the
           bubble IS the CEO speaking, so the subject was missing and the
           result read as a log line with two dashes in it. The coworker
           bubble has always used the bare capitalised clause; the front
           door now matches its own floor. */
        ? {...m, text: stopped ? (m.text + ' …(stopped)')
             : withRouteOut(`⚠ ${snagOpener(err && err.message || String(err))}`,
                            agents, CafresoHQClient, agents),
           error: !stopped}
        : m));
    }
    /* Deliberately NOT clearing abortRef here — the DM fan-out and synthesis
       below reuse this controller's signal, and nulling it early made the
       Stop button dead for exactly the phases that run longest. It's cleared
       at the end of the CEO turn. */
    let finalText = '';
    setChat(prev => {
      const next = prev.map(m => m.id === ceoId ? {...m, streaming: false} : m);
      const ceoMsg = next.find(m => m.id === ceoId);
      finalText = ceoMsg?.text || '';
      return next;
    });
    const approvalDesc = HQ.extractApproval(flush.raw ? flush.raw() : finalText);
    if (approvalDesc && onApprovalRequest) {
      /* Cleaned the same way the bubble below is, and for the same reason:
         `finalText` is the pre-strip stream, so handing it over raw would
         put routing markers on the one card the boss has to read closely. */
      onApprovalRequest({ title: approvalDesc, by: 'CafresoHQ', kind: 'awaiting stamp',
        detail: HQ.approvalBody(
          HQ.cleanHarmony(HQ.visibleReply(String(finalText || ''), 'CafresoHQ'))) });
    }
    setStreaming(false);

    /* Strip raw routing markers from the rendered CEO bubble so the user sees
       a clean reply, not bracket syntax. The markers were already captured
       above via onTool. */
    /* The CEO is a reply path too, and it was the one nobody counted.
       This ran ONLY when the CEO had emitted a handoff or a DM, and even
       then it stripped exactly two marker types with a local regex pair.
       Every other marker the office defines — an ACK, a VAULT_NEW, an
       orphaned tool tag, the echoed speaker label — reached the boss as
       raw syntax in the bubble of the coworker they talk to most.

       It went unnoticed because the reply-hygiene census enumerates
       `agentStream` callers, and the CEO runs on `ceoStream`. A census is
       only as wide as the entry point it knows to look for.

       Now the same `visibleReply` + `cleanHarmony` recipe as the other six
       paths, run unconditionally. Guarded so a reply that is nothing but
       markers is left alone rather than blanked — the same trap
       `visibleReply` documents internally. */
    setChat(prev => prev.map(m => {
      if (m.id !== ceoId) return m;
      const cleaned = HQ.cleanHarmony(HQ.visibleReply(String(m.text || ''), 'CafresoHQ'));
      return (cleaned && cleaned !== m.text) ? { ...m, text: cleaned } : m;
    }));

    /* …and the honesty guards, which the same census missed one function
       over. The paragraph above records that the CEO is a reply path
       nobody counted, because "the reply-hygiene census enumerates
       `agentStream` callers, and the CEO runs on `ceoStream`". That pass
       fixed the STRIPPING and stopped there. `honestyNotes` is called on
       all three coworker dispatch paths in app.jsx and was called on none
       of them here — so the one participant whose entire job is delegation
       was the one whose delegation claims nobody checked.

       Reproduced 2026-08-15 (office 9261, canned brain 9236) with Vera and
       Kip hired. Asked "what margin are we running?", the chief of staff
       replied, and the boss saw this verbatim:

         I've got this covered — I pulled Vera and Kip in on it.

         [Vera → Kip]: I'll take the vendor research, you handle the margin
         numbers.
         [Kip → Vera]: Numbers are done — we're at 34% margin on the
         current mix.

         So: 34% margin. Want me to have them write it up?

       Neither coworker ran. The 34% is invented. Running `fabricatedRelay`
       on that exact text returns the correction it should have shown —
       the guard was right, it was simply never asked.

       Scans `flush.raw()`, not the bubble: the strip above has already
       removed the markers these guards look for, and scanning the cleaned
       text is how the approval tray went blind (see `ontok.raw`). */
    if (HQ.honestyNotes && flush.note) {
      const rawCeo = flush.raw ? flush.raw() : finalText;
      for (const n of HQ.honestyNotes(rawCeo, {
        delivered: ceoDms.length,
        roster: agents.map(a => a.name),
        /* The office's own name. `unsentHandoff` skips a DM addressed to
           `self`, and without this the chief of staff writing [DM_TO:
           CafresoHQ] would be told its own handoff never went out. */
        self: 'CafresoHQ',
        visits: ceoVisits,
      })) flush.note(n);
    }

    /* HANDOFF_TO — switch the active responder to the specialist and have
       them open the conversation with the boss directly. */
    if (ceoHandoff && onDispatchToAgent) {
      const target = agents.find(a => a.name.toLowerCase() === ceoHandoff.to.toLowerCase());
      if (target) {
        setHandoffFor(activeThread, target.name);
        setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
          text: `↪ Handed off to ${target.name}. Talk to them directly — say "back to CafresoHQ" to return.`,
          thread: activeThread }]);
        try {
          await onDispatchToAgent(target, ceoHandoff.body || text, {
            suppressUserEcho: true,
            threadOverride: activeThread,
            /* CafresoHQ chose this hand-off and wrote the brief, so the
               record says so and hangs off the question that caused it. */
            parentMessageId: askId,
            dispatchAs: HQ.CHIEF_OF_STAFF,
          });
        } catch (err) {
          /* §7: the work is now stuck and the boss did not ask for it to be
             — CafresoHQ chose this hand-off. Saying only what went wrong
             leaves them holding a job with nowhere to put it.

             The failed target is filtered OUT of the hint. handoffHint only
             checks whose brain is ready, so without this the office would
             answer "Llama couldn't take the handoff" with "Llama is still
             working, though — @mention them", which is worse than silence. */
          setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
            text: withHandoff(
              `(${target.name} couldn't take the handoff — ${snagCause(err && err.message || String(err))})`,
              agents.filter(a => a.id !== target.id), CafresoHQClient),
            thread: activeThread }]);
        }
      } else {
        /* Nobody was excluded here: the named teammate was never hired, so
           everyone on the roster is still a candidate. The hint names who
           actually is. */
        setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
          text: withHandoff(
            `(CafresoHQ tried to hand off to "${ceoHandoff.to}" but no such teammate is hired)`,
            agents, CafresoHQClient),
          thread: activeThread }]);
      }
    } else if (ceoDms.length && onDispatchToAgent) {
      /* Parallel DM_TO fan-out from the orchestrator. Dispatch each in parallel;
         specialists stream into the same thread with coParticipants context.
         When 2+ specialists reply, CafresoHQ synthesizes one combined response. */
      const targets = ceoDms.map(d => ({
        agent: agents.find(a => a.name.toLowerCase() === d.to.toLowerCase()),
        body: d.body,
      })).filter(d => d.agent);
      const unknown = ceoDms.filter(d => !agents.find(a => a.name.toLowerCase() === d.to.toLowerCase()));
      for (const u of unknown) {
        setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
          text: `(CafresoHQ tried to DM "${u.to}" but no such teammate is hired)`,
          thread: activeThread }]);
      }
      if (targets.length) {
        setStreaming(true);
        try {
          await Promise.all(targets.map(t =>
            onDispatchToAgent(t.agent, t.body, {
              suppressUserEcho: true,
              threadOverride: activeThread,
              coParticipants: targets.filter(o => o.agent.id !== t.agent.id).map(o => ({ name: o.agent.name, role: o.agent.role })),
              /* Same parent for every leg, so a fan-out reads as one
                 question answered by several people rather than several
                 unrelated questions the boss appears to have asked. */
              parentMessageId: askId,
              dispatchAs: HQ.CHIEF_OF_STAFF,
            }).catch(err => {
              setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
                text: `(${t.agent.name} bowed out — ${snagCause(err && err.message || String(err))})`,
                thread: activeThread }]);
            })
          ));

          /* Synthesis pass — combine specialist outputs into one tight CEO reply.
             Only do this for 2+ specialists (single DMs should have been a
             HANDOFF_TO per the orchestrator prompt). Captures the latest reply
             from each delegated specialist by scanning chat history after the
             fan-out completed.

             It read `chatRef`, not a `setChat(prev => …)` capture, and the
             difference is the whole feature. With the capture this block
             scanned an EMPTY array on every run, found nought replies,
             failed `replies.length >= 2`, and returned — so the combined
             answer the boss is meant to get after a two-way fan-out has
             never once been produced. Not degraded: absent, silently, for
             as long as the code has existed. Measured on 2026-08-15 with
             both specialists back and `targets=2`: `synthChat=0`, and
             `asked.jsonl` on the brain shows no synthesis request at all.
             See the note on `chatRef` for why the same line works 250
             lines up and not here. */
          if (targets.length >= 2) {
            const synthChat = chatRef.current;
            const targetNames = new Set(targets.map(t => t.agent.name.toLowerCase()));
            const replies = [];
            for (let i = synthChat.length - 1; i >= 0 && replies.length < targets.length; i--) {
              const m = synthChat[i];
              if (m.from !== 'agent' || !m.text || m.thread !== activeThread) continue;
              const speakerName = String(m.name || '').split(' · ')[0].trim().toLowerCase();
              if (!targetNames.has(speakerName)) continue;
              if (replies.find(r => r.from === speakerName)) continue;
              replies.unshift({ from: speakerName, text: m.text });
            }
            if (replies.length >= 2) {
              const synthPrompt = `The boss asked: "${text}"\n\nYou delegated to ${targets.map(t => t.agent.name).join(', ')} in parallel. Here are their replies:\n\n` +
                replies.map(r => `[${r.from}]:\n${r.text}`).join('\n\n---\n\n') +
                `\n\nNow synthesize ONE tight combined response for the boss (2-4 sentences). Don't paste the raw outputs — extract what matters, note any disagreement, and cite Library paths if any were saved. Do NOT emit DM_TO or HANDOFF_TO markers in this turn.`;
              const synthId = HQ.uid('m');
              setChat(prev => [...prev, { id: synthId, from: 'ceo', name: 'CafresoHQ', text: '', streaming: true, thread: activeThread }]);
              const synthFlush = HQ.throttleTokens(setChat, synthId);
              /* The fifth collection site. Same rule as the other four:
                 gated on an echo, carrying `failed`, because a page that
                 answered 403 and a page that was read are not the same
                 visit. */
              const synthVisits = [];
              try {
                /* No `chat:` — see ceoStream, where passing it discards the
                   prompt. `synthPrompt` is written to stand alone anyway: it
                   restates the boss's question and quotes both replies in
                   full, because summarising is the whole job here and the
                   room's earlier turns are what it must NOT paste back. */
                await HQ.ceoStream(synthPrompt, synthFlush, { agents, signal: controller.signal,
                     onUsage: u => onCeoUsage && onCeoUsage(u),
                     onTool: ev => {
                       if (ev.echo) synthVisits.push({ name: ev.name, arg: ev.arg, echo: ev.echo, failed: !!ev.failed });
                       if (ev.phase === 'done') attachVisit(setChat, synthId, ev);
                     },
                     onHint: synthFlush.note });
                synthFlush.flushNow();
                /* throttleTokens runs cleanHarmony but NOT visibleReply, so
                   markers survived into this bubble. Same recipe as the
                   main CEO reply above. */
                setChat(prev => prev.map(m => {
                  if (m.id !== synthId) return m;
                  const c = HQ.cleanHarmony(HQ.visibleReply(String(m.text || ''), 'CafresoHQ'));
                  return (c && c !== m.text) ? { ...m, text: c } : m;
                }));
                /* …and the guards, for the same reason the reply above them
                   has them — with one line of extra weight here. This is the
                   only prompt in the office that ASKS for a file path: "cite
                   vault paths if any were saved". `unfiledPath` is the guard
                   for a named path nothing wrote, and turning this feature on
                   without it would have shipped, on its first working run,
                   precisely the defect it exists to catch.

                   `delivered: targets.length` — the DMs on this run really
                   did go out, which is what keeps fabricatedRelay and
                   unsentHandoff quiet about a fan-out that actually
                   happened. */
                if (HQ.honestyNotes && synthFlush.note) {
                  const rawSynth = synthFlush.raw ? synthFlush.raw() : '';
                  for (const n of HQ.honestyNotes(rawSynth, {
                    delivered: targets.length,
                    roster: agents.map(a => a.name),
                    self: 'CafresoHQ',
                    visits: synthVisits,
                  })) synthFlush.note(n);
                }
              } catch (_synthErr) {
                /* Best-effort — if synthesis fails, the raw specialist replies
                   are already visible in the thread. */
              }
              setChat(prev => prev.map(m => m.id === synthId ? {...m, streaming: false} : m));
            }
          }
        } finally {
          setStreaming(false);
        }
      }
    }
    /* Settled at the END of the turn, not when ceoStream returns: the
       hand-off and the fan-out below it are part of what the boss asked
       for, and a record that reads `completed` while two specialists are
       still typing is the Inbox answering a question it hasn't finished. */
    if (onBossAskSettled) onBossAskSettled(askId, askErr);
    if (abortRef.current === controller) abortRef.current = null;
  };

  /* Stop reaches BOTH abort surfaces: the panel's own CEO controller and the
     per-agent controllers that dispatchToAgent registers in the host (room /
     @-mention / brainstorm / handoff sends run through those) — but only the
     ones THIS TURN started. `onStopAll` used to be wired here, which made the
     little button the office-wide emergency brake without the brake's confirm
     or its accounting: see abortTurnAgentRuns in app.jsx for the run where it
     killed a delegated job the boss had not asked it to touch. */
  const stop = () => {
    if (abortRef.current) abortRef.current.abort();
    if (onStopTurn) onStopTurn();
  };

  /* When the user types @, scan backwards from the caret to see if we're
     inside a fresh mention token (preceded by start-of-input or whitespace).
     If so, open the popup and filter agents by the partial prefix. Closes
     when the user types a space, navigates away, or Esc. */
  const updateMentionState = (val, caretPos) => {
    // Walk back from caret to find the most recent @ that starts a mention.
    let i = caretPos - 1;
    let foundAt = -1;
    while (i >= 0) {
      const ch = val[i];
      if (ch === '@') {
        // Validate that the @ starts a fresh token: previous char must be
        // start-of-input or whitespace.
        if (i === 0 || /\s/.test(val[i - 1])) foundAt = i;
        break;
      }
      // Mention tokens are letters/digits/_/- only; bail if we cross
      // anything else (including spaces, punctuation).
      if (!/[A-Za-z0-9_-]/.test(ch)) break;
      i--;
    }
    if (foundAt < 0) {
      if (mention) setMention(null);
      return;
    }
    const prefix = val.slice(foundAt + 1, caretPos);
    // Match by prefix (case-insensitive, name-substring fallback).
    const lc = prefix.toLowerCase();
    const hits = agents
      .filter(a => !lc || a.name.toLowerCase().startsWith(lc) || a.name.toLowerCase().includes(lc))
      .slice(0, 8);
    setMention({ active: hits.length > 0, prefix, start: foundAt, hits, idx: 0 });
  };

  const insertMention = (agent) => {
    if (!mention) return;
    // Replace `@<prefix>` with `@<Name> ` and put caret right after the space.
    const before = input.slice(0, mention.start);
    const afterCaret = composerRef.current ? composerRef.current.selectionStart : (mention.start + 1 + mention.prefix.length);
    const after = input.slice(afterCaret);
    const inserted = '@' + agent.name + ' ';
    const next = before + inserted + after;
    setInput(next);
    setMention(null);
    requestAnimationFrame(() => {
      if (composerRef.current) {
        const caret = (before + inserted).length;
        composerRef.current.focus();
        composerRef.current.selectionStart = composerRef.current.selectionEnd = caret;
      }
    });
  };

  const onKey = (e) => {
    // When the popup is open, hijack arrows + tab/enter for selection.
    if (mention && mention.active && mention.hits.length) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setMention(m => ({ ...m, idx: (m.idx + 1) % m.hits.length }));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setMention(m => ({ ...m, idx: (m.idx - 1 + m.hits.length) % m.hits.length }));
        return;
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault();
        insertMention(mention.hits[mention.idx]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setMention(null);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  /* Handle typing — update both the input AND the mention popup. */
  const onInputChange = (e) => {
    const v = e.target.value;
    setInput(v);
    updateMentionState(v, e.target.selectionStart);
  };
  const onInputClickOrKeyMove = () => {
    if (!composerRef.current) return;
    updateMentionState(composerRef.current.value, composerRef.current.selectionStart);
  };

  const activeThreadDef = allTabs.find(t => t.id === activeThread) || THREADS[0];
  // Project/meeting rooms are NOT read-only — the boss can send to them and
  // it fans out to participants. Only the team/research feeds remain
  // observe-only.
  const isReadOnly = activeThread === 'team' || activeThread === 'research';

  return (
    <div className="monitor">
      <div className="bezel">
        <div className="left">
          <div className="avatar-mini"><Sprite data={activeThread === 'direct' ? 'cafresohq' : 'teal'} scale={1} /></div>
          <div className="ceo-label">
            {activeThreadDef.label}<br/>
            <span className="sub">{activeThreadDef.desc}</span>
          </div>
        </div>
        <div className="dots"><span className="on"/><span/><span/></div>
      </div>
      {/* Chat history search — filters across ALL threads when active. */}
      <div style={{
        padding: 'var(--sp-2) var(--sp-3)',
        borderBottom: '1px solid var(--rule)',
        background: 'var(--paper-2)',
        display: 'flex', alignItems: 'center', gap: 'var(--sp-2)',
      }}>
        <span aria-hidden="true" style={{fontSize: 'var(--text-11)', color: 'var(--ink-3)'}}>🔍</span>
        <input
          type="search"
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          placeholder="Search messages…"
          style={{
            flex: 1, minWidth: 0,
            background: 'transparent',
            border: 'none', outline: 'none',
            font: 'inherit', fontSize: 'var(--text-12)',
            color: 'var(--ink)',
            padding: 'var(--sp-2) 0',
          }}
        />
        {searchQuery && (
          <>
            <span style={{fontSize: 'var(--text-9)', color: 'var(--ink-3)'}}>
              {visibleChat.length} match{visibleChat.length === 1 ? '' : 'es'}
            </span>
            <button
              onClick={() => setSearchQuery('')}
              style={{
                background: 'transparent', border: 'none',
                color: 'var(--ink-3)', cursor: 'pointer',
                fontSize: 'var(--text-13)', padding: 0,
              }}
              aria-label="Clear search"
            >✕</button>
          </>
        )}
      </div>
      {/* Room banner — visible only when in a project/meeting thread.
          Shows the room name, participant chips, and an action to invite
          another agent on the fly. */}
      {activeRoom && (
        <div className="room-banner">
          <div className="room-banner-head">
            <span className="room-banner-icon">{activeRoom.kind === 'meeting' ? '📋' : '📁'}</span>
            <span className="room-banner-name">{activeRoom.name}</span>
            <span className="room-banner-kind">{activeRoom.kind === 'meeting' ? 'MEETING' : 'PROJECT ROOM'}</span>
            {activeRoom.topic && <span className="room-banner-topic" title={activeRoom.topic}>· {activeRoom.topic}</span>}
          </div>
          <div className="room-banner-participants">
            {activeRoom.participants.length === 0 && (
              <span className="room-banner-empty">No participants yet — assign agents to this {activeRoom.kind}</span>
            )}
            {activeRoom.participants.map(a => (
              <span key={a.id} className="room-chip" title={`${a.role}${a.elevated ? ' · has file and shell access' : ''}`}>
                {a.elevated ? '🛡' : '👤'} {a.name}
                {activeRoom.kind === 'meeting' && setMeetings && activeRoom.participants.length > 1 && (
                  <span className="room-chip-x"
                    title={`Remove ${a.name} from this meeting`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setMeetings(prev => prev.map(m => m.id === activeRoom.refId
                        ? { ...m, agentIds: (m.agentIds || []).filter(id => id !== a.id) }
                        : m));
                    }}
                  >✕</span>
                )}
              </span>
            ))}
            {activeRoom.kind === 'meeting' && setMeetings && (
              <RoomInvite
                allAgents={agents}
                currentIds={activeRoom.participants.map(a => a.id)}
                onInvite={(id) => setMeetings(prev => prev.map(m => m.id === activeRoom.refId
                  ? { ...m, agentIds: [...(m.agentIds || []), id] }
                  : m))}
              />
            )}
          </div>
        </div>
      )}
      {handoffAgent && (
        <div className="handoff-banner" style={{
          display:'flex', alignItems:'center', gap:8,
          padding:'8px 12px',
          background:'linear-gradient(90deg, var(--accent-sun-10, rgba(218,165,32,0.12)) 0%, transparent 100%)',
          borderBottom:'2px solid var(--accent-sun, #d4a017)',
          fontSize:12, fontWeight:600,
        }}>
          <span style={{fontSize:14}}>↪</span>
          <span style={{flex:1}}>
            Talking to <strong>{handoffAgent.name}</strong> · <span style={{opacity:0.7, fontWeight:400}}>{handoffAgent.role}</span>
          </span>
          <button onClick={returnToCEO} className="px-btn ghost" style={{
            fontSize:10, padding:'4px 10px',
            background:'var(--paper-2)', border:'1.5px solid var(--ink)',
            borderRadius:6, cursor:'pointer', fontWeight:700, letterSpacing:'0.04em',
          }}>
            ← BACK TO CAFRESOHQ
          </button>
        </div>
      )}
      <div className="screen" ref={screenRef}>
        {visibleChat.length === 0 && !searchQuery && (
          <div className="thread-empty">
            {activeThread === 'direct'   && <>No messages yet — type below to message CafresoHQ.</>}
            {activeThread === 'team'     && <>No team chatter yet. When coworkers DM each other (via <code>[DM_TO: name]</code> blocks), the conversations land here so the main thread stays clean.</>}
            {activeThread === 'research' && <>
              No research yet. A research mission runs in rounds on its own and drops each round's output here.
              {onOpenResearch
                /* The door itself, not directions to it. This thread has no
                   composer, so a boss who reads this and cannot find the
                   control has no second way to try. */
                ? <> <button className="px-btn secondary" style={{fontSize:10, marginTop:8, display:'block'}}
                        onClick={onOpenResearch}>🔬 START A RESEARCH MISSION</button></>
                : <> Open one from <strong>⌗ ROOMS ▾ → 🔬 Research missions</strong> in the topbar.</>}
            </>}
            {activeRoom && activeRoom.kind === 'project' && <>No messages in this project room yet. Type below to message everyone assigned at once, or @-mention just some of them.</>}
            {activeRoom && activeRoom.kind === 'meeting' && <>No messages in this meeting yet. Type below to send to all attendees, or @-mention specific people.</>}
          </div>
        )}
        {/* The same courtesy the inbox pays its own cap, on the surface the
            boss reads far more often. Measured on a scratch office seeded
            with 130 turns: one reload showed 100 opening on "turn 31", the
            saved copy already held 80 opening on "turn 51", and a second
            reload brought the screen down to match. Fifty turns gone for
            good, and the thread simply began at turn 51 — which reads
            exactly like a beginning.

            Above the list, not below it, for the reason the inbox states:
            the dropped ones are the OLDEST, and the top is where someone
            scrolling back stops and concludes they have seen everything.

            Read off `visibleChat[0]` rather than a total, because
            `capChatFair` stamps the oldest survivor of EACH thread and this
            view shows one thread at a time. Suppressed while searching:
            `visibleChat` then spans every room and is ordered by the chat
            array, so its first row is not this thread's oldest survivor and
            the count would be answering a question nobody asked. */}
        {!searchQuery && visibleChat.length > 0 && visibleChat[0].droppedBefore > 0 && (
          <div className="msg-system" style={{opacity:0.65,fontStyle:'italic'}}>
            ⋯ {visibleChat[0].droppedBefore} older message{visibleChat[0].droppedBefore === 1 ? '' : 's'} rolled
            out of this room to keep the office small. This is not where the
            conversation started; anything above is gone for good.
          </div>
        )}
        {visibleChat.length === 0 && searchQuery && (
          <div className="thread-empty">No messages match "{searchQuery}".</div>
        )}
        {visibleChat.map(m => {
          if (m.from === 'system') {
            return <div key={m.id} className="msg-system">{m.text}</div>;
          }
          // Agent-to-agent DM: render as a quieter envelope so the user can
          // see overhearing without it dominating the thread.
          if (m.from === 'agent-dm') {
            return (
              <div key={m.id} className="msg msg-dm">
                <div className="dm-head">📨 {m.name}</div>
                <MessageBody text={m.text} />
              </div>
            );
          }
          /* Search (line ~200) deliberately looks across ALL threads, so a
             hit here can belong to a thread other than `activeThread` — the
             same reason "Ask this again" above scopes its own walk to
             `m.thread || 'direct'` rather than the chat array's interleaved
             order. quoteReply/startDM used to skip that scoping entirely:
             they populated the composer without ever switching threads, so
             a reply to a search hit from project:acme (found while browsing
             DIRECT) silently sent as `thread: activeThread` — i.e. DIRECT —
             landing nowhere near the message it was replying to, with no
             error and no visible sign of the mismatch. `switchToMessageThread`
             below is the fix both handlers now share: snap to the hit's own
             thread (and drop the search filter, since leaving it active
             would keep showing the cross-thread result list instead of the
             thread the user just landed in) before touching the composer —
             or refuse outright if that thread has no composer at all
             (`team`/`research` are read-only; see `isReadOnly` below). */
          const switchToMessageThread = () => {
            const targetThread = m.thread || 'direct';
            if (targetThread === 'team' || targetThread === 'research') {
              if (window.cafresohqToast) window.cafresohqToast.warn(
                "That message is in a read-only thread — there's no composer there to reply from.");
              return false;
            }
            if (targetThread !== activeThread) { setActiveThread(targetThread); setSearchQuery(''); }
            return true;
          };
          const quoteReply = () => {
            if (!switchToMessageThread()) return;
            const quoted = String(m.text).split('\n').map(l => '> ' + l).join('\n');
            setInput((prev) => (prev ? prev + '\n\n' : '') + quoted + '\n\n');
            if (composerRef.current) composerRef.current.focus();
          };
          const startDM = () => {
            if (m.name && m.from !== 'user') {
              if (!switchToMessageThread()) return;
              const target = agents.find(a => a.id === m.agentId);
              const bareName = target ? target.name : String(m.name).split(' · ')[0];
              setInput((prev) => (prev ? prev + ' ' : '') + `@${bareName} `);
              if (composerRef.current) composerRef.current.focus();
            }
          };
          // Display label for the message author. CEO messages always show
          // "CafresoHQ-CEO" so the role is unmistakable in the chat thread.
          // The hyphen gives the browser a natural wrap point in the narrow
          // `.who` column.
          const _whoLabel = m.from === 'user'
            ? 'You'
            : m.from === 'ceo'
              ? 'CafresoHQ-CEO'
              : (m.name || 'A coworker');
          /* A failed stream marks its bubble `error: true` (all three
             dispatch catches do), but nothing ever read the flag — a dead
             run rendered exactly like a healthy reply, and the only retry
             lived in the Inbox modal behind a filter. The class gives it a
             face; the RETRY affordance below gives it a next step. */
          const msgContent = (
            <div key={m.id} className={`msg ${m.from}${m.pinned ? ' pinned' : ''}${m.error ? ' msg-error' : ''}`}>
              <div className="who" title={_whoLabel}>
                <span className="who-name">{_whoLabel}</span>
                {/* m.target already carries its own @ prefix(es) — prefixing
                    again rendered "→ @@kip". */}
                {m.target ? <span className="who-target">→ {String(m.target).startsWith('@') ? m.target : '@' + m.target}</span> : null}
                {m.pinned ? <span className="msg-pinned-badge" title="pinned">📌</span> : null}
              </div>
              <div className="bubble" style={m.error ? {borderLeft:'3px solid var(--danger, #c0504d)'} : undefined}>
                <div className="msg-body">
                  <MessageBody text={m.text} />
                  {m.streaming ? <span className="typing"><span/><span/><span/></span> : null}
                  {/* Still waiting on the first byte. Only ever shown on a
                      bubble that is streaming AND has produced no text yet,
                      so the sentence is true of THIS message regardless of
                      which run was slow — a bubble with nothing in it
                      really is still waiting. Three dots alone read as
                      broken once a cold local brain starts loading
                      gigabytes off disk. */}
                  {m.streaming && !m.text && brainSlow ? (
                    <span className="msg-waiting">still waiting on that brain — it may be warming up</span>
                  ) : null}
                  {/* What the office actually did, rendered as office
                      chrome. This used to be text spliced into the bubble,
                      which meant a coworker could WRITE one — and one did,
                      inventing a result and a vault path for a lookup that
                      returned nothing. Structured data can't be typed. */}
                  {(m.visits || []).map((v, i) => (
                    <div className={'msg-visit' + (v.failed ? ' failed' : '')} key={i}>
                      <div className="msg-visit-head">
                        <span className="msg-visit-icon" aria-hidden="true">{v.icon}</span>
                        {v.head}
                      </div>
                      {v.body ? <div className="msg-visit-body">{v.body}</div> : null}
                    </div>
                  ))}
                  {/* RETRY refills the composer with the ask that failed —
                      it does NOT auto-send, because the bubble above it
                      usually names a cause (a key, a rate limit) the boss
                      may need to fix first. Scan scoped to THIS thread,
                      same as "Ask this again" below. */}
                  {m.error && !m.streaming ? (
                    <div className="msg-retry-row" style={{marginTop:6,display:'flex',alignItems:'center',gap:8}}>
                      <span style={{fontSize:10,opacity:0.7}}>⚠ this run failed</span>
                      <button className="px-btn ghost" style={{fontSize:9,padding:'2px 8px'}}
                        title="Put the ask that failed back in the composer"
                        onClick={() => {
                          const mThread = m.thread || 'direct';
                          const idx = chat.findIndex(x => x.id === m.id);
                          for (let i = idx - 1; i >= 0; i--) {
                            if (chat[i].from === 'user' && (chat[i].thread || 'direct') === mThread) {
                              setInput(chat[i].text);
                              if (composerRef.current) composerRef.current.focus();
                              break;
                            }
                          }
                        }}>↻ RETRY</button>
                    </div>
                  ) : null}
                </div>
                {!m.streaming && m.text ? (
                  <>
                    {_isMobileChat && (
                      <button className="msg-actions-toggle" onClick={() => setOpenActionsId(prev => prev === m.id ? null : m.id)} title="Actions">{'···'}</button>
                    )}
                    <div className={'msg-actions' + (_isMobileChat && openActionsId === m.id ? ' msg-actions-open' : '')}>
                      <button title="Copy" onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(m.text);
                          if (window.cafresohqToast) window.cafresohqToast.success('Copied');
                        } catch (_e) {
                          if (window.cafresohqToast) window.cafresohqToast.error("Couldn't copy — try selecting the text instead");
                        }
                      }}>📋</button>
                      <button title="Quote-reply" onClick={quoteReply}>↩</button>
                      {m.from !== 'user' ? (
                        <>
                          <button title="Ask this again" onClick={() => {
                            /* Scan only THIS message's thread — the chat array
                               interleaves all threads, so an unscoped walk could
                               grab a user prompt from a different room. */
                            const mThread = m.thread || 'direct';
                            const idx = chat.findIndex(x => x.id === m.id);
                            for (let i = idx - 1; i >= 0; i--) {
                              if (chat[i].from === 'user' && (chat[i].thread || 'direct') === mThread) {
                                setInput(chat[i].text);
                                break;
                              }
                            }
                          }}>↻</button>
                          <button title={`DM ${m.name}`} onClick={startDM}>💬</button>
                        </>
                      ) : null}
                      <button title={m.pinned ? 'Unpin' : 'Pin'} onClick={() => {
                        setChat(prev => prev.map(x => x.id === m.id ? { ...x, pinned: !x.pinned } : x));
                      }}>{m.pinned ? '📍' : '📌'}</button>
                      {onPinAsTask && (
                        <button title="Pin as a task in the backlog" onClick={() => {
                          onPinAsTask({ msg: m });
                          if (window.cafresohqToast) window.cafresohqToast.success('Pinned to Tasks');
                        }}>📋+</button>
                      )}
                    </div>
                  </>
                ) : null}
              </div>
            </div>
          );
          return (
            <SwipeMessage key={m.id} onReply={quoteReply} onDM={m.from !== 'user' ? startDM : null} agentName={m.name}>
              {msgContent}
            </SwipeMessage>
          );
        })}
        <div ref={bottomRef} style={{height:0,overflow:'hidden'}} aria-hidden="true"/>
      </div>
      {!isReadOnly ? (
      <div className="composer" style={{position:'relative'}}>
        {/* Action row — sits ABOVE the textarea so it doesn't squeeze the
            input. Small pills that respect their content width; they push
            to the right via flex auto. */}
        <div className="actions">
          <button className="composer-mini composer-mini--ghost" onClick={()=>setShowDelegate(s=>!s)} title="Hand this to one of your coworkers">
            <Ico kind="delegate" size={11}/> Delegate
          </button>
          {backendDown && !streaming && (
            <span className="composer-offline" title="Chat needs your office running — reconnecting automatically">
              ⚠ offline — reconnecting…
            </span>
          )}
          {streaming
            ? <button className="composer-mini composer-mini--danger" onClick={stop} title="Take back this turn — the reply being written and anyone it pulled in. Coworkers on other jobs keep going; ■ STOP ALL up top stops everything.">■ Stop</button>
            : <button className="composer-mini composer-mini--primary" onClick={send} disabled={backendDown}
                title={backendDown ? 'Your office is offline' : 'Send (Enter)'}>Send ↵</button>}
        </div>
        <textarea
          ref={composerRef}
          /* Name who is actually going to read this. There are three states
             where the next message does NOT go to CafresoHQ, and the box
             claimed it did in all three.

             In a project or meeting room it goes to everyone seated, while
             the banner directly above listed three other people and the
             room's own empty state said "type below to send to all
             attendees" — the composer was the only thing in the room
             disagreeing.

             During a hand-off it goes to the specialist. That one is worse,
             because the office had just said, in its own voice, "Handed off
             to Nova. Talk to them directly" — and then labelled the box you
             talk to them in with somebody else's name. */
          placeholder={handoffAgent
            ? `Message ${handoffAgent.name}… (say "back to CafresoHQ" to return · ↵ send)`
            : activeRoom && activeRoom.participants.length
              ? `Message ${activeRoom.participants.length === 1
                  ? activeRoom.participants[0].name
                  : `all ${activeRoom.participants.length} in ${activeRoom.name}`}… (@ mention to narrow · ↵ send)`
              : 'Message CafresoHQ… (@ mention · ↵ send · /brainstorm for team)'}
          value={input}
          onChange={onInputChange}
          onKeyDown={onKey}
          onClick={onInputClickOrKeyMove}
          onKeyUp={(e) => {
            // Arrow keys / Home / End move the caret without firing
            // onChange — re-evaluate mention state in those cases.
            if (['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) onInputClickOrKeyMove();
          }}
        />
        {/* @-autocomplete popup. Anchored above the composer. Filtered as
            the user types; arrow keys navigate, Tab/Enter inserts. */}
        {mention && mention.active && mention.hits.length > 0 && (
          <div className="mention-pop" role="listbox">
            <div className="mention-pop-head">
              MENTION · {mention.hits.length} match{mention.hits.length === 1 ? '' : 'es'}
              <span className="mention-pop-hint">↑↓ Tab ⏎</span>
            </div>
            {mention.hits.map((a, i) => (
              <div
                key={a.id}
                className={'mention-pop-item' + (i === mention.idx ? ' active' : '')}
                onMouseEnter={() => setMention(m => ({ ...m, idx: i }))}
                onMouseDown={(e) => { e.preventDefault(); insertMention(a); }}
                role="option"
                aria-selected={i === mention.idx}
              >
                <Sprite data={a.color} scale={1}/>
                <div style={{display:'flex',flexDirection:'column',lineHeight:1.15,minWidth:0,flex:1}}>
                  <span className="mention-pop-name">
                    {a.elevated ? '🛡 ' : ''}{a.name}
                    {a.status === 'busy' && <span className="mention-pop-busy">· busy</span>}
                  </span>
                  <span className="mention-pop-role">{a.role}</span>
                </div>
              </div>
            ))}
          </div>
        )}
        {showDelegate && (
          <div className="delegate-pop">
            <div className="title">HAND OFF TO…</div>
            {/* §7: this is the ONE empty state the boss reaches by
                actively trying to delegate — they opened a hand-off picker.
                It used to say "No coworkers yet." and stop, which is the
                worst place in the office to be told no and offered nothing.
                The stand-up sheet already had the right shape (a line that
                explains, then the button that fixes it); this now matches
                it. */}
            {agents.length === 0 && (
              <div className="muted" style={{padding:'6px',fontSize:15}}>
                Nobody to hand off to yet.
                {onHire && (
                  <button className="px-btn primary" style={{marginTop:8,width:'100%'}}
                          onClick={()=>{ setShowDelegate(false); onHire(); }}>
                    + HIRE YOUR FIRST COWORKER
                  </button>
                )}
              </div>
            )}
            {agents.map(a => (
              <div key={a.id} className="item" onClick={async ()=>{
                /* A declined hand-off (onDelegate → false: the coworker was
                   mid-reply and the boss chose "Let them finish") puts the
                   typed text back — the gesture was cancelled, not spent. */
                const typed = input; setShowDelegate(false); setInput('');
                const ok = await onDelegate(a, typed, activeThread);
                if (ok === false) setInput(typed);
              }}>
                <Sprite data={a.color} scale={1}/>
                <div style={{display:'flex',flexDirection:'column',lineHeight:1.1}}>
                  <span>{a.name}</span>
                  <span className="tiny">{a.role}</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      ) : (
        <div className="thread-readonly">
          {activeThread === 'team'     && '👀 watching team chatter — switch to DIRECT to send a message'}
          {/* This banner replaces the composer, so it is the only thing in
              the boss's way when they want to act on what they are reading.
              "from the topbar" was true of a button that is not there. */}
          {activeThread === 'research' && (onOpenResearch
            ? <>🔬 research feed — <button className="px-btn ghost" style={{fontSize:10, padding:'2px 8px'}}
                  onClick={onOpenResearch}>MANAGE MISSIONS</button></>
            : <>🔬 research feed — start or manage missions from <strong>⌗ ROOMS ▾ → 🔬 Research missions</strong></>)}
        </div>
      )}
      <div className="thread-tabs">
        {allTabs.map(t => (
          <button key={t.id}
            className={`thread-tab ${activeThread === t.id ? 'active' : ''}${t.kind === 'meeting' ? ' meeting-tab' : ''}${t.kind === 'project' ? ' project-tab' : ''}`}
            onClick={() => setActiveThread(t.id)}
            /* The count is EVERY message in the thread, not unread ones —
               and a number badged on a tab reads as unread by every
               convention there is. The tooltip explained the thread ("You
               & CafresoHQ") and never the number, so 33 sat there looking
               like 33 things wanting attention when it was the whole
               conversation, most of it read hours ago. Say which. */
            title={threadCounts[t.id] > 0
              ? `${t.desc} · ${threadCounts[t.id]} message${threadCounts[t.id] === 1 ? '' : 's'} in this thread, read and unread`
              : t.desc}>
            <span className="tt-icon">{t.icon}</span>
            <span className="tt-label">{t.label}</span>
            {threadCounts[t.id] > 0 && <span className="tt-count">{threadCounts[t.id]}</span>}
            {t.kind === 'meeting' && setMeetings && (
              <span
                className="tt-close"
                title="End meeting"
                onClick={(e) => {
                  e.stopPropagation();
                  setMeetings(prev => prev.filter(m => m.id !== t.refId));
                  if (activeThread === t.id) setActiveThread('direct');
                }}
              >✕</span>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

/* Render chat message text with light Markdown-ish polish:
     - ``` fenced code blocks → monospace box with a click-to-copy button
       and basic regex-based syntax tinting (keywords, strings, numbers,
       comments). Languages tagged on the fence are honoured for the
       label; tinting is heuristic and shared across languages.
     - inline `code` → monospace span
     - long lines (200+ char) inside code blocks aren't wrapped — they
       scroll horizontally to preserve indentation
     - long code blocks (>14 lines) collapse behind a "[+ N lines]"
       disclosure so a 400-line diff doesn't dominate the thread.
   No external lib — keeps the no-build philosophy intact and avoids
   shipping a 200KB highlighter for what's mostly snippets.
*/
const _CODE_FENCE_RE = /```([a-zA-Z0-9_+\-]*)\n([\s\S]*?)```/g;
const _INLINE_CODE_RE = /`([^`\n]+)`/g;

/* Token-level highlighter — language-agnostic, errs on under-highlighting.
   Order matters (comments before strings before keywords). Returns React
   children that preserve whitespace inside a <pre>. */
function tintCode(src) {
  const parts = [];
  let i = 0;
  // Single regex with alternation; we walk matches in order.
  const re = /(\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`)|\b(0x[0-9a-fA-F]+|\d+(?:\.\d+)?)\b|\b(function|const|let|var|if|else|for|while|return|class|extends|new|this|import|export|from|async|await|try|catch|throw|true|false|null|undefined|def|lambda|pass|None|True|False|elif|fn|pub|use|impl|struct|enum|match|trait|mut|self|fn|in|not|and|or|is)\b/g;
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

function CodeBlock({ lang, body }) {
  const [expanded, setExpanded] = useState(false);
  const lines = body.replace(/\n$/, '').split('\n');
  const COLLAPSE_AFTER = 14;
  const showAll = expanded || lines.length <= COLLAPSE_AFTER;
  const visibleLines = showAll ? lines : lines.slice(0, COLLAPSE_AFTER);
  const hidden = lines.length - visibleLines.length;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(body);
      if (window.cafresohqToast) window.cafresohqToast.success('Copied');
    } catch (_) {
      if (window.cafresohqToast) window.cafresohqToast.error("Couldn't copy — try selecting the text instead");
    }
  };
  return (
    <div className="cb-wrap">
      <div className="cb-head">
        <span className="cb-lang">{lang || 'code'}</span>
        <span className="cb-meta">{lines.length} line{lines.length === 1 ? '' : 's'}</span>
        <button className="cb-copy" onClick={copy} title="Copy">📋</button>
      </div>
      <pre className="cb-pre"><code>{tintCode(visibleLines.join('\n'))}</code></pre>
      {hidden > 0 && (
        <button className="cb-expand" onClick={() => setExpanded(true)}>
          + show {hidden} more line{hidden === 1 ? '' : 's'}
        </button>
      )}
      {expanded && lines.length > COLLAPSE_AFTER && (
        <button className="cb-expand" onClick={() => setExpanded(false)}>
          − collapse
        </button>
      )}
    </div>
  );
}

/* Render a chat message body — splits on fenced code blocks and renders
   the prose between them as paragraphs (with inline `code` styling). */
function MessageBody({ text }) {
  if (!text) return null;
  // Walk fences in order; everything between is plain text.
  const out = [];
  let last = 0;
  let m;
  _CODE_FENCE_RE.lastIndex = 0;
  while ((m = _CODE_FENCE_RE.exec(text)) !== null) {
    if (m.index > last) {
      out.push(<MessageProse key={'t'+last} text={text.slice(last, m.index)} />);
    }
    out.push(<CodeBlock key={'cb'+m.index} lang={m[1]} body={m[2]} />);
    last = m.index + m[0].length;
  }
  if (last < text.length) {
    out.push(<MessageProse key={'t'+last} text={text.slice(last)} />);
  }
  return <>{out}</>;
}

/* Inline-code-aware paragraph renderer. Splits on backticks and wraps
   the inner runs in <code>; everything else preserves newlines via
   white-space: pre-wrap. Also renders ![alt](url) markdown image embeds
   inline — used by BROWSER_SCREENSHOT to surface PNGs (the data: URL
   sits in the message text).

   .msg-image has always shipped with `cursor: zoom-in` and a CSS comment
   promising "click to open at full size in a new tab" (styles.css, since
   the very first commit) — but the <img> itself never carried an onClick.
   A screenshot capped to the chat column's width by max-width:100% had no
   way to be seen at native resolution; the cursor just lied. Wired here so
   the click actually does what the affordance has always claimed. */
const _MD_IMAGE_RE = /!\[([^\]]*)\]\((data:image\/[a-z]+;base64,[A-Za-z0-9+/=]+|https?:\/\/[^)\s]+)\)/g;
function MessageProse({ text }) {
  if (!text) return null;
  // First pass: split on image embeds. The text BETWEEN images is then
  // run through the inline-code splitter; images render as <img>.
  const blocks = [];
  let cursor = 0;
  let im;
  _MD_IMAGE_RE.lastIndex = 0;
  while ((im = _MD_IMAGE_RE.exec(text)) !== null) {
    if (im.index > cursor) blocks.push({ kind: 'text', value: text.slice(cursor, im.index) });
    blocks.push({ kind: 'img', alt: im[1], src: im[2] });
    cursor = im.index + im[0].length;
  }
  if (cursor < text.length) blocks.push({ kind: 'text', value: text.slice(cursor) });
  const renderText = (s, key) => {
    const parts = [];
    let last = 0; let m;
    _INLINE_CODE_RE.lastIndex = 0;
    while ((m = _INLINE_CODE_RE.exec(s)) !== null) {
      if (m.index > last) parts.push(s.slice(last, m.index));
      parts.push(<code key={key+'ic'+m.index} className="msg-icode">{m[1]}</code>);
      last = m.index + m[0].length;
    }
    if (last < s.length) parts.push(s.slice(last));
    return <p key={key} style={{whiteSpace:'pre-wrap', margin:0}}>{parts}</p>;
  };
  return <>{blocks.map((b, i) => b.kind === 'img'
    ? <img key={'img'+i} src={b.src} alt={b.alt || 'screenshot'} className="msg-image" loading="lazy"
        onClick={() => window.open(b.src, '_blank', 'noopener,noreferrer')}/>
    : renderText(b.value, 'b'+i))}</>;
}

/* Inline "+ invite" pill used inside meeting room banners. Pops a small
   menu of agents not yet in the room; clicking one adds them. Closes
   on outside click. */
function RoomInvite({ allAgents, currentIds, onInvite }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => { if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);
  const remaining = (allAgents || []).filter(a => !currentIds.includes(a.id));
  return (
    <span className="room-invite-wrap" ref={wrapRef}>
      <button className="room-invite-btn" onClick={() => setOpen(o => !o)} title="Invite another coworker">
        + invite
      </button>
      {open && (
        <div className="room-invite-pop">
          {remaining.length === 0 && <div className="room-invite-empty">Everyone's already here.</div>}
          {remaining.map(a => (
            <div key={a.id} className="room-invite-item"
              onClick={() => { onInvite(a.id); setOpen(false); }}>
              <Sprite data={a.color} scale={1}/>
              <div style={{display:'flex',flexDirection:'column',lineHeight:1.1}}>
                <span>{a.name}{a.elevated ? ' 🛡' : ''}</span>
                <span className="tiny">{a.role}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </span>
  );
}

/* ------------ Agent status cards row ------------ */
function AgentCards({ agents, onHire, onClick, onDismiss }) {
  return (
    <div className="agents-bar">
      {agents.map(a => (
        <div key={a.id} className={`agent-card ${a.elevated ? 'elevated' : ''}`} onClick={()=>onClick(a)}>
          <div className={`status-pill ${a.status}`}>{a.status.toUpperCase()}</div>
          {a.elevated && <div className="elevated-badge" title="Has file and shell access">🛡</div>}
          <div className="sprite-box"><Sprite data={a.color} scale={2} className="bob"/></div>
          <div className="name">{a.name}</div>
          <div className="role">{a.role}</div>
          {(a.lastRun || a.nextRun) ? (
            <div className="meta">
              {a.lastRun && <span>last: {a.lastRun}</span>}
              {a.lastRun && a.nextRun && <span>·</span>}
              {a.nextRun && <span>next: {a.nextRun}</span>}
            </div>
          ) : (
            <div className="meta"><span>just hired</span><span>·</span><span>on demand</span></div>
          )}
        </div>
      ))}
      <div className="agent-card hire-tile" onClick={onHire}>
        <div className="plus">+<br/>HIRE</div>
      </div>
    </div>
  );
}


export { AgentCards, ChatPanel };
