import { floorEmit, snagOpener } from './floor.jsx';
import { withRouteOut } from './cast.jsx';   // import-free module — no cycle
import { CafresoHQClient } from '../claude-client.jsx';
const { useState: useStateA, useEffect: useEffectA, useMemo: useMemoA, useRef: useRefA, useCallback: useCallbackA } = React;

/* One-time storage-key migration: legacy openclaw_* / cafresoai. keys -> cafresohq.*
   Copies (never deletes) so existing sessions keep working. Idempotent. */
(function _migrateCafresoHQStorage(){
  try{
    for(const store of [window.localStorage, window.sessionStorage]){
      if(!store) continue;
      for(const k of Object.keys(store)){
        let nk=null;
        if(k.indexOf('openclaw')===0) nk='cafresohq'+k.slice(8);
        else if(k.indexOf('cafresoai.')===0) nk='cafresohq.'+k.slice(10);
        if(nk && store.getItem(nk)===null) store.setItem(nk, store.getItem(k));
      }
    }
  }catch(_){}
})();


/* localStorage-backed useState. Reads on mount; writes are DEBOUNCED so a
   streaming-token burst doesn't hammer JSON.stringify on every frame. The
   `transform` callback lets callers drop runtime-only fields before saving.
   Save failures (quota, private mode, corruption) dispatch a window event so
   the App can surface a toast instead of vanishing silently. */
/* JSON.parse succeeding is NOT the same as the value being usable: a stored
   literal "null" or a schema-drifted scalar parses fine and then explodes at
   the first `.map`/spread — a white-screen boot with nothing in the console
   pointing at the key. Type-check the parsed value against the default's
   shape and fall back when they disagree. */
function _shapeMatches(parsed, base) {
  if (base == null) return true;                    // no opinion to enforce
  if (Array.isArray(base)) return Array.isArray(parsed);
  const t = typeof base;
  if (t === 'object') return parsed != null && typeof parsed === 'object' && !Array.isArray(parsed);
  return typeof parsed === t;
}
function useStored(key, initial, transform) {
  const [v, set] = useStateA(() => {
    const fallback = () => (typeof initial === 'function' ? initial() : initial);
    try {
      const raw = localStorage.getItem(key);
      if (raw == null) return fallback();
      const parsed = JSON.parse(raw);
      const base = fallback();
      return _shapeMatches(parsed, base) ? parsed : base;
    } catch (_e) {
      return fallback();
    }
  });
  /* Cross-tab: absorb another tab's write instead of clobbering it later
     with our stale copy (the `storage` event only fires in OTHER tabs, so
     there's no loop). Only while unfocused — the tab the user is actively
     typing/streaming in keeps its own state authoritative. */
  useEffectA(() => {
    const onStorage = (e) => {
      if (e.key !== key || e.newValue == null) return;
      if (typeof document !== 'undefined' && document.hasFocus && document.hasFocus()) return;
      try {
        const parsed = JSON.parse(e.newValue);
        set(prev => _shapeMatches(parsed, prev) ? parsed : prev);
      } catch (_e) {}
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [key]);
  const timer = useRefA(null);
  useEffectA(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      try {
        const out = transform ? transform(v) : v;
        localStorage.setItem(key, JSON.stringify(out));
      } catch (err) {
        console.warn('[cafresohq] localStorage save failed for', key, err);
        try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key, error: err } })); } catch (_e) {}
      }
    }, 300);
    return () => { if (timer.current) clearTimeout(timer.current); };
  }, [v]);
  return [v, set];
}

/* Like useStored but also syncs to /hq/state or /hq/memory via serve.py.
   `fileScope` is 'state' or 'memory', `fileName` is the key (no .json).
   On mount, fetches the file and merges (file wins over localStorage).
   On change, writes to localStorage immediately AND to the file (debounced 1.5s).
   Pass sensitive:true to skip file persistence (API keys etc). */
/* `transform` runs on the READ paths (boot seed, file adoption) — several
   callers pass load-scrubs (tasksOnLoad, missionsOnLoad) that must NEVER run
   at write time: a scrub that files "the run stopped when the page reloaded"
   is a lie when stamped onto a run that is alive. `persistTransform` is the
   opt-in WRITE filter: what persist() sends to localStorage and to disk goes
   through it, so the durable record never receives what the filter exists to
   keep out of it. The two are separate on purpose — do not unify them. */
function useFileStored(lsKey, fileScope, fileName, initial, transform, { sensitive = false, persistTransform = null, mergeOnDirty = false } = {}) {
  const [val, setVal] = useStateA(() => {
    const fallback = () => (typeof initial === 'function' ? initial() : initial);
    try {
      const raw = localStorage.getItem(lsKey);
      if (raw == null) { const b = fallback(); return transform ? transform(b) : b; }
      let parsed = JSON.parse(raw);
      if (!_shapeMatches(parsed, fallback())) parsed = fallback();
      return transform ? transform(parsed) : parsed;
    } catch (_e) { return fallback(); }
  });

  /* The value this session started with, before anything touched it.
     `dirtyRef` alone cannot tell a real edit from a BOOT-TIME write — a
     normalising effect that calls the setter with the same empty array
     sets it just as surely as the boss hiring someone, and the arriving
     fetch then refuses to adopt the real file. That is the actual wipe:
     not the PUT racing the GET, but the GET being turned away. */
  const seedRef = useRefA(null);
  const valRef = useRefA(val);          // latest value, readable from the fetch callback
  if (seedRef.current === null) { try { seedRef.current = JSON.stringify(val); } catch (_e) { seedRef.current = ''; } }

  const writeRef = useRefA(null);
  // Set as soon as anything in this session mutates the value. The mount fetch
  // below resolves ~100-300ms after first render, so without this flag it
  // overwrites whatever the user typed (or an agent wrote) in that window, and
  // the debounced PUT then pushes the server's stale copy back — losing the
  // edit in both places. Local changes win; the server copy is only adopted
  // when the session hasn't touched it yet.
  const dirtyRef = useRefA(false);

  /* Has the mount fetch settled yet? Until it has, this session has never
     SEEN the file, so nothing it holds is authoritative — the value is just
     `initial`.

     Measured 2026-08-08, and it is data loss on the core entity. An office
     with one hired coworker (file written 08-07 17:10) was opened in a
     FRESH BROWSER CONTEXT. Empty mirror → `val` seeds to []. A boot-time
     mutation set dirtyRef, which both PUT the empty array over the file
     AND made the arriving fetch return early rather than restore it.
     agents.json: 2 bytes, mtime 08-08 08:50. The task from that run still
     names `a_local_ollama` — a coworker who no longer exists.

     I recorded this yesterday as MY testing mistake ("never clear a mirror
     key to reset a file-backed value"). It is not a testing hazard. It is
     what happens to any boss who opens their office in a second browser,
     clears site data, or picks up a different device.

     The fix is narrow: hold the FILE write until the fetch has settled.
     localStorage still updates immediately, so nothing feels laggy, and
     with no edit in that window dirtyRef stays false, the fetch adopts the
     real roster, and the office comes back whole. */
  const hydratedRef = useRefA(false);

  const persist = React.useCallback((v) => {
    /* What goes to disk is not the floor. Measured 2026-08-15: during a
       transient helper's 30-second grace, this wrote the RAW roster —
       `transient: true` and all, a field persistableAgents can never emit —
       into memory/agents.json, and serve.py rendered hq-agents.md listing
       Sub-fact-3j9 as a member of staff. Close the office mid-grace and
       nothing ever takes them off the record. useStored's write path has
       applied its transform all along; this one silently didn't. */
    const out = persistTransform ? persistTransform(v) : v;
    try { localStorage.setItem(lsKey, JSON.stringify(out)); } catch (err) {
      /* Sensitive keys (API keys) have NO file fallback — if this write
         fails (quota, private mode) the key silently doesn't survive a
         reload. Surface it like useStored does instead of swallowing. */
      console.warn('[cafresohq] localStorage save failed for', lsKey, err);
      try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key: lsKey, error: err } })); } catch (_e) {}
    }
    if (sensitive) return;
    /* Never write the file we have not read. See hydratedRef above. */
    if (!hydratedRef.current) return;
    clearTimeout(writeRef.current);
    writeRef.current = setTimeout(() => {
      /* Unlike the localStorage.setItem above, a failed PUT here used to
         vanish into a bare .catch(() => {}) — the UI looked fine (localStorage
         already has the edit) but the on-disk record silently kept its old
         contents, so the NEXT session's mount-fetch above adopts the stale
         file and the edit reverts with zero warning. Surface it the same way
         the localStorage failure a few lines up already does. */
      fetch(`${window._API_BASE || ''}/hq/${fileScope}/${fileName}`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(out),
      }).then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
      }).catch(err => {
        console.warn('[cafresohq] file save failed for', fileScope + '/' + fileName, err);
        try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key: lsKey, error: err, target: 'file' } })); } catch (_e) {}
      });
    }, 1500);
  }, [lsKey, fileScope, fileName, sensitive, persistTransform]);

  useEffectA(() => {
    if (sensitive) return;
    fetch(`${window._API_BASE || ''}/hq/${fileScope}/${fileName}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        hydratedRef.current = true;     // settled: file writes may proceed
        if (data == null) return;
        /* Local edits win — but only REAL ones. If what this session holds
           is still byte-identical to the seed it started with, nobody has
           edited anything; a boot effect just wrote the initial value back.
           Adopt the file in that case, or a fresh browser deletes the
           office's staff.

           `mergeOnDirty` is the one escape hatch from "keep theirs": a plain
           snapshot transform (tasksOnLoad, persistableAgents-shaped, or none)
           has no way to reconcile a fetched file against a live edit, so
           returning here — discarding the fetch outright — is the safe
           choice for those. A log-shaped transform (mergeByIdCap,
           mergeMessages) is different: it already reads the CURRENT in-memory
           value itself (via a ref closure) and unions it with whatever the
           fetch returns, so skipping it here doesn't protect anything — it
           just throws the fetched history away.

           Measured on `activity` (mergeOnDirty not yet wired for it before
           this fix): seed three historical entries on disk, load fresh, fire
           one `cafresohq:agentActivity` event ~200ms in (the same event the
           agent_runner shim dispatches for every vault write) so dirtyRef
           flips true before the mount fetch resolves. The fetch landed with
           the three entries, `untouched` was false (a real edit happened),
           and this `return` fired — `transform` (mergeByIdCap) never ran.
           The three historical entries, one of them an unread ATTENTION row,
           never entered state. The next activity write's debounced PUT then
           overwrote hq-state/activity.json with just the session's own new
           entries — the coworker's unresolved failure was gone from disk,
           silently, with no error anywhere. */
        let untouched = false;
        try { untouched = JSON.stringify(valRef.current) === seedRef.current; } catch (_e) {}
        if (dirtyRef.current && !untouched && !mergeOnDirty) return;   // a real edit, no safe merge — keep theirs
        const merged = transform ? transform(data) : data;
        valRef.current = merged;
        setVal(merged);
        try { localStorage.setItem(lsKey, JSON.stringify(merged)); } catch (_e) {}
        /* A file written by a session that died mid-grace (or by a build
           before the write filter existed) can hold what persist would now
           never write — a transient helper listed as staff. Adopting it
           silently leaves the record lying until some unrelated write
           happens to flush; the only healer today is a no-op-tolerant CLI
           sync that has no idea it owns that job. If the record on disk
           differs from what the write filter would put there, heal it now,
           deterministically. hydratedRef is already true — this is a
           write-back of what was just read, so the boot-wipe hazard the
           flag exists for does not apply. */
        if (persistTransform) {
          try {
            if (JSON.stringify(persistTransform(merged)) !== JSON.stringify(data)) persist(merged);
          } catch (_e) {}
        }
      })
      /* Unreachable server counts as settled too, or an offline office
         could never write to disk again. */
      .catch(() => { hydratedRef.current = true; });
  }, []);  // intentionally runs once on mount

  const setter = React.useCallback((updater) => {
    dirtyRef.current = true;
    setVal(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
      valRef.current = next;
      persist(next);
      return next;
    });
  }, [persist]);

  return [val, setter];
}

const STORE_KEY = 'cafresohq_hq_v1';
const k = (n) => STORE_KEY + ':' + n;
// Per-HQ-container key: scopes a flag by the user's container slug (from the
// /u/<slug>/ API base). Used for onboarding flags so a NEW user/container shows
// the New-User guide, instead of inheriting a "seen" flag from a prior account
// in the same browser. Reads _API_BASE at call time (set before render).
const ks = (n) => {
  let slug = 'local';
  try {
    const m = String((typeof window !== 'undefined' && window._API_BASE) || '')
      .match(/\/u\/([0-9a-f]{8,})/i);
    if (m) slug = m[1];
  } catch (_) {}
  return STORE_KEY + ':' + n + ':' + slug;
};
/* One-time downgrade: windowsEnabled defaulted to true for every boss from
   day one, and useStored's own write effect persists the initial value
   ~300ms after mount even with zero interaction — so almost every browser
   that has ever loaded this app already has an EXPLICIT "true" on disk for
   this key, not an absence useStored's new `false` default would catch.
   That recorded "true" is the old code's default, not a real choice: force
   it off once, gated by a sentinel so a boss who deliberately re-enables it
   afterward (Settings -> Appearance -> Advanced) keeps that choice on the
   next reload instead of being fought back to full-page every time. */
(function _migrateWindowsEnabledDefault(){
  try {
    const SENTINEL = STORE_KEY + ':windowsEnabledDefaultV2';
    if (localStorage.getItem(SENTINEL) != null) return;
    localStorage.setItem(k('windowsEnabled'), JSON.stringify(false));
    localStorage.setItem(SENTINEL, '1');
  } catch (_) {}
})();
// Strip ephemeral fields before persisting agents — runtime status/mood
// reset to a clean baseline on reload so we don't show stale "busy" sprites.
// Also drop transient sub-agents (spawned via [SPAWN_SUBAGENT]) so they
// don't survive a reload — they're meant to live for one task only.
const persistableAgents = (xs) => xs
  .filter(a => !a.transient)
  .map(a => {
    const { status, mood, task, ...rest } = a;
    return { ...rest, status: 'idle', mood: 'idle', task: 'standing by' };
  });
/* Merge the persisted activity file (fetched on mount) with whatever was
   logged in-memory before the fetch landed — dedup by id, in-memory wins
   (fresher unread state), sort newest-first, cap. Historical ROUTINE entries
   load as read so a reload doesn't inflate the attention badge; ATTENTION
   entries stay unread until the user acts on them. */
const mergeByIdCap = (inMem, fetched, cap = 200) => {
  const byId = new Map();
  for (const e of (Array.isArray(fetched) ? fetched : [])) {
    byId.set(e.id, e.priority === 'attention' ? e : { ...e, unread: false });
  }
  for (const e of (Array.isArray(inMem) ? inMem : [])) byId.set(e.id, e);
  return [...byId.values()].sort((a, b) => (b.ts || 0) - (a.ts || 0)).slice(0, cap);
};
/* Evict oldest-first, but never below `floor` entries per thread.
   The chat is ONE array interleaving every room (direct, team, project:*,
   meeting:*, research), and both caps used to be a plain slice(-N) over it —
   so the budget was shared and the noisiest room spent all of it. Measured:
   20 direct messages followed by a project room streaming 90 left the saved
   file with ZERO direct entries; a reload opened onto an empty Direct room
   the boss had been talking in that same morning. The in-memory ceiling did
   the same to the live transcript.

   Fairness here is a floor, not a quota: eviction walks oldest-first and
   skips any message whose thread is already down to its last `floor`
   entries. A busy room still pays first — it is the one over budget — and a
   quiet room keeps enough of its tail to still read as a conversation. The
   total can exceed `max` by at most (threads × floor), which is small and
   bounded by rooms that actually have history. Returns the SAME array when
   nothing needs dropping so React state setters can bail out on reference
   equality. */
const capChatFair = (xs, max, floor = 15) => {
  if (!Array.isArray(xs) || xs.length <= max) return xs;
  const counts = new Map();
  for (const m of xs) {
    const t = m.thread || 'direct';
    counts.set(t, (counts.get(t) || 0) + 1);
  }
  const kept = [];
  /* What each thread lost, so the survivors can say so. Same decision the
     message registry made two functions down, on the surface the boss
     actually reads: a bounded record has to say it is bounded.

     Reproduced 2026-09-03 on a scratch office (127.0.0.1:8897) seeded with
     130 turns in one thread. One reload showed 100, opening on "turn 31";
     localStorage already held 80, opening on "turn 51". A second reload
     brought the screen down to match — fifty turns of conversation gone for
     good — and nothing anywhere on the surface said so. The thread simply
     began at turn 51, which reads exactly like a beginning.

     PER THREAD, not one total. The registry is a flat list, so its count can
     ride on the single oldest survivor; this array interleaves every room
     and the view shows one room at a time, so a Direct thread announcing
     fifty dropped turns that were actually the project room's would be a
     second wrong answer rather than a fix. Carries `droppedBefore` off a
     departing message the same way the registry does, so this is everything
     the thread has ever shed and not the size of the most recent pass. */
  const dropped = new Map();
  let toDrop = xs.length - max;
  for (const m of xs) {
    const t = m.thread || 'direct';
    if (toDrop > 0 && counts.get(t) > floor) {
      counts.set(t, counts.get(t) - 1);
      toDrop--;
      dropped.set(t, (dropped.get(t) || 0) + 1 + (m.droppedBefore || 0));
      continue;
    }
    kept.push(m);
  }
  if (kept.length === xs.length) return xs;
  /* The oldest survivor of each thread that lost something — exactly the
     message the boss is looking at when they scroll to the top and wonder
     whether the room starts where they started talking in it. */
  const stamped = new Set();
  return kept.map(m => {
    const t = m.thread || 'direct';
    if (stamped.has(t) || !dropped.get(t)) return m;
    stamped.add(t);
    return { ...m, droppedBefore: (m.droppedBefore || 0) + dropped.get(t) };
  });
};
// Cap chat history at 80 entries so localStorage doesn't bloat — fairly,
// per thread, so one busy room can't evict another room's history.
const persistableChat = (xs) => capChatFair(xs, 80).map(({ streaming, error, ...rest }) => rest);

/* Desk-screen feed: streams an agent's live output tail onto its office
   monitor (OfficeView listens for 'cafresohq:agentScreen'). Throttled to one
   event per 150ms per agent — token callbacks can fire per-chunk and the
   office must never re-render at token rate. Screen state stays OUT of the
   agents array on purpose; it's ephemeral scenery, not agent state. */
const makeScreenEmitter = (agentId) => {
  let last = 0, trailing = null;
  const send = (tail, phase) => {
    floorEmit('screen', { agentId, tail: String(tail || '').slice(-240), phase });
  };
  return {
    stream(buf) {
      const now = Date.now();
      if (now - last >= 150) {
        last = now;
        if (trailing) { clearTimeout(trailing); trailing = null; }
        send(buf, 'stream');
      } else if (!trailing) {
        trailing = setTimeout(() => { trailing = null; last = Date.now(); send(buf, 'stream'); }, 160);
      }
    },
    done(buf) {
      if (trailing) { clearTimeout(trailing); trailing = null; }
      send(buf, 'done');
    },
    /* Failed/aborted runs must CLOSE the monitor too (§4: never play
       "working" when the driver is erroring). Without this the desk screen
       kept its live glow for the 60s safety window after a crash. */
    error(buf) {
      if (trailing) { clearTimeout(trailing); trailing = null; }
      send(buf || ' ', 'error');
    },
  };
};

/* The chat bubble for a failed run — the THIRD surface that speaks about a
   failure, after the floor bubble and the inbox row, and until now the only
   one still improvising.

   Watching one real failure land on all three at once: the inbox said "that
   brain isn't signed in yet", the floor said the same, and the bubble said
   "The shared Cafreso brain isn't responding right now — it may be waking
   up". Nothing was waking up. There was no key. The bubble guessed, because
   the no-key branch fired on the CONNECTION state and then narrated the
   CAUSE — and it was a guess it made for every failure alike, 429s and
   timeouts included, before appending the raw error in parentheses anyway.
   The other branch just dumped `raw`, which §7 bans outright.

   So: name the cause with the same classifier the other two surfaces use,
   and keep the shared-brain line for what it's genuinely good for — telling
   a zero-config user that BYOK is a way out. Advice, after the diagnosis,
   not instead of it. */
/* …and the classifier is snagCause, because the subject here IS a brain.
   This bubble is the coworker speaking about their OWN failed run.

   It said officeCause for a while, and that was collateral from the census
   that split the two: twelve call sites were pushing file and vault
   failures through snagCause and getting "couldn't reach that brain" for a
   failed delete, so they were moved. This file was on the list and should
   not have been — every one of chatErrorText's three call sites is an
   agent run (dispatch, delegate, task). The fix for a misdiagnosis was
   applied to the one surface that had been diagnosing correctly.

   The two tables disagree on every failure a coworker can actually have.
   Measured against verbatim errors from a live office, bubble vs floor:

     brain unreachable  "the office isn't answering — check it's still
                        running"  ·  vs "couldn't reach that brain — it
                        looks offline from here"
     model not on disk  "the office couldn't find that — it may have been
                        moved or renamed"  ·  vs "that brain isn't
                        installed on this machine — pick another coworker,
                        or install it and try again"
     no key            `Ollama 401: no api key` VERBATIM  ·  vs "that brain
                        isn't signed in yet — add it in Settings"

   The first sends the boss to check the office, which is the one thing on
   their screen that is demonstrably fine. The second describes a lost
   file when nothing was lost — and OFFICE_CAUSES has no model-not-found
   rule at all, because installing models is not something an office does.
   The third falls through to cleanCause and prints a vendor name, an HTTP
   code and the words "api key" — the raw dump §7 forbids and the word §6
   bans, in the surface this comment was written to stop improvising. */
/* `selfId` — the coworker who just failed. handoffHint can only ask whose
   BRAIN is ready, and for a local model that probe says "yes" even when the
   named model is not installed, so it cheerfully offers the coworker that
   just fell over. test_cast.py records this exact trap for one call site:
   "the call site must exclude the coworker who just refused — otherwise a
   failed hand-off answers 'Llama couldn't take it' with 'Llama is still
   working, @mention them'". This is the OTHER call site, and it had the
   defect. Seen live: Pip failed on a missing model and the bubble read
   "Llama and Pip are still working, though — @mention one of them". */
const chatErrorText = (err, agents, selfId) => {
  const others = selfId ? (agents || []).filter(a => a && a.id !== selfId) : agents;
  const raw = (err && err.message) || String(err);
  let out = '⚠ ' + snagOpener(raw);
  try {
    const C = CafresoHQClient;
    /* §7's third route — "pick another coworker" — was the one this never
       offered, and on the failure it fires for most it is the only one that
       works. The CEO runs on the DEFAULT brain; a hired coworker pins their
       own. So the chief of staff being unreachable says nothing about the
       floor, and the office watched a boss get "couldn't reach that brain,
       it looks offline from here" plus a RETRY button that could only fail
       again — while two coworkers sat at their desks on working local
       brains. Naming them is both truer and more useful than repeating the
       diagnosis.

       Same probe as the topbar alarm (agentBrainReady), so the two surfaces
       cannot disagree about who can work. */
    /* The ladder — name a coworker, else hire, else bring a brain — now
       lives in cast.jsx beside handoffHint, because the CEO's own failure
       bubble needed the same one and had only the first rung. It reached
       the end of the ladder with nothing to say and printed a diagnosis
       with no way forward on the first message a new office ever sends.
       `agents` as well as `others`: rung 2 asks who is HIRED, and `others`
       is empty in a one-coworker office the moment that coworker falls
       over. */
    out = withRouteOut(out, others, C, agents);
  } catch (_) {}
  return out;
};

// Cap messages registry at 500 entries (rolling) and strip any runtime-only
// fields before persisting. Messages are durable records of agent ↔ agent
// handoffs — they outlive the chat scrollback so the boss can always answer
// "what happened to the task I sent Selvin?" without scrolling. Keep state
// machine history bounded too — 30 entries per message is plenty.
const MESSAGES_CAP = 500;
const HISTORY_CAP = 30;

/* Trim one record's history, keeping the OPENING entry and counting what
   went.

   `slice(-30)` kept the newest thirty, which is the wrong thirty. The entry
   a handoff gets read FOR — `created`, who asked, and the note saying what
   for — is the first thing out the door. Reproduced 2026-08-16 on a seeded
   office: a 45-event record rendered "history (30 events)" and opened with
   "created · Kip — event 16 of 45". Not "resumed at 16" — `created`, as
   though that were the beginning. Nothing in the list and nothing in the
   count distinguished it from a complete trail.

   `historyDropped` accumulates instead of being recomputed. This runs on
   every read of an already-trimmed record and h[0] survives each pass, so
   what an earlier trim took is no longer countable from h alone. */
const trimHistory = (m) => {
  const h = Array.isArray(m.history) ? m.history : [];
  if (h.length <= HISTORY_CAP) return { ...m, history: h };
  const kept = [h[0], ...h.slice(-(HISTORY_CAP - 1))];
  return {
    ...m,
    history: kept,
    historyDropped: (m.historyDropped || 0) + (h.length - kept.length),
  };
};

const persistableMessages = (xs) => {
  const arr = Array.isArray(xs) ? xs : [];
  let dropped = 0;
  let kept = arr;
  if (arr.length > MESSAGES_CAP) {
    const gone = arr.slice(0, arr.length - MESSAGES_CAP);
    /* Carry whatever marker the departing records were themselves holding,
       so this is everything the registry has ever shed and not the size of
       the most recent trim. */
    dropped = gone.reduce((n, m) => n + 1 + (m.droppedBefore || 0), 0);
    kept = arr.slice(-MESSAGES_CAP);
  }
  const out = kept.map(trimHistory);
  /* The registry is a bare array with nowhere to hang a total, so the count
     rides on the oldest record that survived — which is exactly the row the
     boss is looking at when they wonder whether the list starts where the
     office did. */
  if (dropped && out.length) {
    out[0] = { ...out[0], droppedBefore: (out[0].droppedBefore || 0) + dropped };
  }
  return out;
};

/* Merge the persisted messages file (fetched on mount) with whatever's
   already in memory before the fetch lands — dedup by id, in-memory wins.
   `activity` sits on this exact same useFileStored race (mount fetch vs. a
   debounced 1.5s file write) and was given mergeByIdCap for it; `messages`
   never got the equivalent, so createMessage() could append a message,
   flush it to localStorage, and then lose it outright to a same-tab reload
   that landed inside the debounce window and adopted the still-stale file.
   Unlike mergeByIdCap, this doesn't sort or cap on its own — messages have
   no ts/unread fields to sort by, and the union is handed back through
   persistableMessages (which already caps + prunes history) rather than
   duplicating that logic here. */
const mergeMessages = (inMem, fetched) => {
  const byId = new Map();
  for (const m of (Array.isArray(fetched) ? fetched : [])) byId.set(m.id, m);
  for (const m of (Array.isArray(inMem) ? inMem : [])) byId.set(m.id, m);
  return persistableMessages([...byId.values()]);
};

// Message states form a directed lifecycle. Every transition appends to
// history, and history is capped (see trimHistory) — so the trail is the
// opening entry plus the most recent HISTORY_CAP-1, with the count of what
// was dropped carried on the record. Bounded and said out loud, rather than
// complete: this comment used to promise the trail was never lost, which
// the cap two functions up had been quietly disproving. `terminal` states
// can't be transitioned out of (except via explicit reopen).

export { capChatFair, chatErrorText, k, ks, makeScreenEmitter, mergeByIdCap, mergeMessages, persistableAgents, persistableChat, persistableMessages, useFileStored, useStored };
