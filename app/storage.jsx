import { CHAT_CUT_NOTE, CHAT_GONE_NOTE, floorEmit, snagOpener } from './floor.jsx';
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
/* `transform` is the WRITE filter; `onLoad` is the READ scrub, and they are
   separate here for the same reason useFileStored keeps them apart: a scrub
   that says "this reply stopped when the page reloaded" is a lie the moment
   it runs at write time, on a run that is still going. onLoad runs once, on
   the value this page found in storage — nothing this session produced ever
   passes through it. The cross-tab absorber below is deliberately NOT on
   this path: a record another tab is writing right now belongs to a live
   run, and nothing there is finished enough to narrate. */
function useStored(key, initial, transform, onLoad) {
  const [v, set] = useStateA(() => {
    const fallback = () => (typeof initial === 'function' ? initial() : initial);
    try {
      const raw = localStorage.getItem(key);
      if (raw == null) return fallback();
      const parsed = JSON.parse(raw);
      const base = fallback();
      if (!_shapeMatches(parsed, base)) return base;
      return onLoad ? onLoad(parsed) : parsed;
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
  /* #418's option, read from the SAME options object in its own statement:
     the destructure above is pinned verbatim by the early-activity guard
     (`mergeOnDirty = false` must be its last name), so a fourth name there
     fails the suite. Same options bag for the caller; one more line here.
     No brace of either kind may appear in this comment: three guards lift
     this function by counting braces, comments included. */
  const { absorb = null } = arguments[5] || {};
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
  /* The debounced file write that has been scheduled but not yet paid. See
     persist() below and the unload flush under it. */
  const pendingRef = useRefA(null);
  const paidRef = useRefA(null);
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

  /* Does this BROWSER still owe disk a write it never managed to pay?
     `pendingRef` is the debt within one page; this is the debt across a
     reload, and until now nothing carried it.

     Measured 2026-09-05 against a real `python3 serve.py` on a scratch
     office, driving this exact hook headlessly (test_durability_retry.py
     said "the hook cannot be driven headlessly" — it can, see
     scripts/test_an_edit_made_while_the_office_was_down_is_not_deleted.py).
     File on disk: one task, "yesterday". The boss adds "the thing I just
     did" while the office is restarting. The 1500ms PUT fires into a dead
     port and fails; localStorage holds both tasks; the toast fires. The
     office comes back. The boss reloads — and a freshly reloaded tab has
     `dirtyRef` false, so the mount fetch below adopts the STALE file,
     mirrors it back over localStorage at 331, and the next write PUTs it.
     Measured `afterReload` and `fileAfterReload`: `[{"id":"old"}]`. The
     edit is gone from BOTH halves, and the one surface that ever mentioned
     it died with the page that showed it.

     The toast was the whole remedy, and a toast cannot survive the reload
     it is warning you about. So the failure leaves a NOTE instead — a
     sibling key in the same store as the value, so the two are cleared
     together and can never disagree — and the mount fetch reads it as
     "local is newer than the file", heals disk, and clears it. Read once,
     on the first render, before anything this session does can clear it. */
  const unpaidKey = lsKey + '::unpaid';
  const unpaidRef = useRefA(null);
  if (unpaidRef.current === null) {
    try { unpaidRef.current = localStorage.getItem(unpaidKey) != null; }
    catch (_e) { unpaidRef.current = false; }
  }

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
    /* What the debounce below still OWES disk, and when it was promised.
       A tab that closes inside the 1500ms window takes the pending PUT with
       it — React never unmounts on a tab close, so there is no cleanup to
       lean on — and the file keeps the contents it had before the boss's
       last action. That would be survivable if localStorage were the winner
       next time, but it is not: the mount fetch above adopts the FILE
       whenever this session hasn't edited anything yet, which is exactly
       what a freshly reloaded tab looks like. So the stale file is written
       back over the newer local copy and the last thing the boss did is
       gone from BOTH halves, silently. `at` is what lets the unload flush
       tell a promise still owed from one already paid, without touching the
       write body below. */
    pendingRef.current = { scope: fileScope, name: fileName, body: JSON.stringify(out), at: Date.now() };
    clearTimeout(writeRef.current);
    clearTimeout(paidRef.current);
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
        /* Paid. The note comes off, so the next boot adopts the file
           normally instead of paying a redundant PUT forever. */
        try { localStorage.removeItem(lsKey + '::unpaid'); } catch (_e) {}
      }).catch(err => {
        /* The bytes did not land, and localStorage is now the ONLY copy of
           this edit. Write the note before the toast — the toast dies with
           the page, the note is what the next mount reads. */
        try { localStorage.setItem(lsKey + '::unpaid', '1'); } catch (_e) {}
        console.warn('[cafresohq] file save failed for', fileScope + '/' + fileName, err);
        try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key: lsKey, error: err, target: 'file' } })); } catch (_e) {}
      });
    }, 1500);
    /* The debt is settled the moment the timer above runs, and a tab switch
       must not then re-send it — thirteen file-backed stores would each pay a
       redundant PUT every time the boss looked at another tab. A SECOND timer,
       armed right after the write one and for the same delay, clears the note:
       equal-deadline timers fire in the order they were registered, so this
       lands immediately after the write. Kept separate rather than folded into
       the callback above so that write body stays byte-for-byte what it was.
       The `at` stamp in the flush is the backstop if the ordering ever fails
       us — the cost of a miss is one duplicate PUT of identical content, never
       a lost one. */
    paidRef.current = setTimeout(() => { pendingRef.current = null; }, 1500);
  }, [lsKey, fileScope, fileName, sensitive, persistTransform]);

  /* Pay what the debounce still owes before the page goes away.
     `pagehide` is the close/navigate signal that actually fires (`unload`
     does not, on a bfcache-eligible page), and `visibilitychange` to hidden
     covers the phone/tab-switch route that often never comes back. The PUT
     goes out with `keepalive` so the browser finishes it after the document
     is gone. No toast on failure here — there is no surface left to show one
     on, and localStorage still holds the value either way.
     Only ever fires while a write is genuinely outstanding: `at` is stamped
     when the 1500ms timer is armed, so anything older than that window has
     already been written by the timer itself and a tab switch costs nothing.
     Deliberately does not touch the timer body above — that body is the
     error-reporting path, and this one is the last-gasp path. */
  useEffectA(() => {
    if (sensitive) return;
    const flush = () => {
      const p = pendingRef.current;
      if (!p || (Date.now() - p.at) > 1500) return;
      pendingRef.current = null;
      clearTimeout(writeRef.current);
      clearTimeout(paidRef.current);
      /* Pessimistic on purpose, and the one place in this file that is.
         The document is going away; the response usually never gets back to
         a handler that still exists, so "did it land?" is unanswerable here.
         Assume NOT, and let the next boot decide with evidence it can
         actually read. A wrong guess costs one redundant PUT of byte-
         identical content; the other direction costs the boss's last action,
         which is the loss this whole note exists to stop. */
      try { localStorage.setItem(lsKey + '::unpaid', '1'); } catch (_e) {}
      try {
        fetch(`${window._API_BASE || ''}/hq/${p.scope}/${p.name}`, {
          method: 'PUT',
          headers: { 'content-type': 'application/json' },
          body: p.body,
          keepalive: true,
        }).then(r => {
          if (r && r.ok) { try { localStorage.removeItem(lsKey + '::unpaid'); } catch (_e) {} }
        }).catch(() => {});
      } catch (_e) {}
    };
    const onHidden = () => {
      if (typeof document === 'undefined' || document.visibilityState === 'hidden') flush();
    };
    const w = (typeof window !== 'undefined' && window.addEventListener) ? window : null;
    const d = (typeof document !== 'undefined' && document.addEventListener) ? document : null;
    if (w) w.addEventListener('pagehide', flush);
    if (d) d.addEventListener('visibilitychange', onHidden);
    return () => {
      if (w) w.removeEventListener('pagehide', flush);
      if (d) d.removeEventListener('visibilitychange', onHidden);
    };
  }, [sensitive, lsKey]);

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
        /* We are about to keep theirs, not adopt the fetch — but any edit
           that landed in the pre-hydration window had persist() bail on the
           file PUT (hydratedRef.current was still false at write time), so
           the file never got it. hydratedRef is true now: flush that held
           write, or the edit lives in localStorage forever and the next
           session on a different browser/device never sees it. */
        if (dirtyRef.current && !untouched && !mergeOnDirty) persist(valRef.current);
        if (dirtyRef.current && !untouched && !mergeOnDirty) return;   // a real edit, no safe merge — keep theirs
        /* #408 — the SECOND way local can be ahead of the file, and the one
           the two lines above cannot see. They test `dirtyRef`, which is a
           fact about THIS page: did someone edit since it loaded. The debt
           outlives the page. An edit an EARLIER page made whose PUT was
           refused (office restarting, disk full, laptop asleep) lives only
           in localStorage, and a freshly reloaded tab is `untouched` and
           not `dirty` by construction — so without the unpaid note that
           edit is indistinguishable from "this browser knows nothing" and
           the stale file wins, then gets mirrored back over it at 331.

           A separate statement rather than a wider condition on those two
           on purpose: seven suites (#177's, #232's, #379's) string-match
           them verbatim as the wiring they guard, and the flush-then-return
           shape is theirs. This adds a case; it does not restate one. */
        if (unpaidRef.current && !mergeOnDirty) { persist(valRef.current); return; }
        const merged = transform ? transform(data) : data;
        valRef.current = merged;
        setVal(merged);
        /* The adoption mirror. #397: this was the ONE setItem in this file
           that swallowed — three lines from persist()'s (174) and thirteen
           from useStored's (84), both of which dispatch. What it fails to
           mirror is the file's own content, so the value itself survives
           (the next mount fetches it again) — but the FAILURE is the
           boss's to know about, and this is the earliest moment anything
           can tell them. A restricted or full quota throws on every write,
           and a session that only reads never reaches persist() at all:
           the office would look perfectly healthy right up until the first
           edit of the day quietly failed to survive a reload. Same event,
           same wording, as its two siblings. */
        try { localStorage.setItem(lsKey, JSON.stringify(merged)); } catch (err) {
          console.warn('[cafresohq] localStorage save failed for', lsKey, err);
          try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key: lsKey, error: err } })); } catch (_e) {}
        }
        /* The held-write flush, for the OTHER half of the same edit.
           #232 taught the keep-theirs branch above to replay a pre-hydration
           edit — persist() had bailed on the PUT while hydratedRef was still
           false, so without a replay the edit lived in localStorage forever.
           That fix was written with `!mergeOnDirty` on it, which is exactly
           backwards for the stores that carry the flag: `messages` and
           `activity` do NOT return there, they fall through to here, and
           nothing on this path ever calls persist() either. Same held write,
           same never released, on the two collections the office calls its
           system-of-record.

           Trace it on `activity`, whose early write is not a rare race — the
           agent_runner shim dispatches `cafresohq:agentActivity` on every
           vault write, routinely inside the ~300ms before the mount fetch
           resolves. That setter flips dirtyRef and its PUT is skipped. The
           fetch lands, mergeByIdCap unions the file with the new entry, state
           and localStorage both get the union — and hq-state/activity.json
           keeps only what it already had. Close the tab there and the entry
           is gone from disk; open the office on a second browser or device
           and the row the boss watched appear was never there.

           Only reachable when mergeOnDirty is set: every other store took
           the return above, so this cannot turn a plain adoption into a
           write. `merged`, not valRef.current — the union is what state and
           localStorage now hold, so it is what disk should hold too. */
        if (dirtyRef.current && !untouched) persist(merged);
        /* #408, the mergeOnDirty half. The union already rescued the refused
           edit into state and localStorage above — but disk was never
           healed, so the loss just moved to the next browser. `else if`, so
           a store that is both dirty and unpaid pays exactly one PUT. */
        else if (unpaidRef.current) persist(merged);
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

  /* #418 — the other tab. `useStored` absorbed another tab's write on the
     `storage` event (which fires in every tab EXCEPT the one that wrote);
     this hook did not, so `## 413`'s move of the chat onto it traded that
     for file durability. Measured with two tabs over one localStorage map
     and one stub file: B sends m4, its PUT lands; A sends m5, its PUT
     writes A's copy — [m1,m2,m3,m5] — over the file, localStorage and every
     tab that reloads. Last writer wins, and the loser's message is gone.

     `absorb(theirs, mine)` is the caller's merge, handed the parsed event
     value and the value THIS hook holds right now (valRef, not a render-old
     ref: a send this tab made a moment ago and has not rendered yet is in
     valRef and nowhere else). It is opt-in for the same reason mergeOnDirty
     is: a snapshot store has no safe union with another tab's copy, and
     replacing it wholesale while the boss is mid-edit is the clobber
     useStored's `hasFocus` guard existed to avoid. A log-shaped store can
     union, so it does — focused or not, because the union keeps ours.

     Set into state, NEVER persisted: localStorage already holds theirs (it
     is what fired the event), disk is theirs or about to be, and a persist
     here would fire the same event back at them and the two tabs would
     re-announce each other forever. The union reaches disk on this tab's
     next real edit, which is exactly the write that used to erase it. */
  const absorbRef = useRefA(absorb);
  absorbRef.current = absorb;
  useEffectA(() => {
    if (!absorb) return;
    const onStorage = (e) => {
      if (!e || e.key !== lsKey || e.newValue == null || !absorbRef.current) return;
      try {
        const theirs = JSON.parse(e.newValue);
        if (!_shapeMatches(theirs, valRef.current)) return;
        const merged = absorbRef.current(theirs, valRef.current);
        valRef.current = merged;
        setVal(merged);
      } catch (_e) {}
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [lsKey, !!absorb]);

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
/* `streaming` is translated, not dropped. Dropping it is right for the flag
   itself — a spinner restored on load belongs to a run that died with the
   last page and would blink forever — but the FACT it carried is the only
   thing that tells a finished reply from one the page outlived, and the
   write path was throwing that fact away.

   Measured 2026-09-05 against a real `python3 serve.py` and a real local
   brain: ask a coworker something, kill and restart the server mid-answer,
   reload. `useStored`'s 300ms debounce is re-armed by every token frame, so
   nothing of the answer is ever written while it streams — the record on
   disk is still the placeholder the dispatcher seeded, `text: ''`. With
   `streaming` gone it is an ordinary message, and the transcript comes back
   as `<div class="msg-body"></div>` under KIP · DEEP RESEARCH: the coworker's
   name over a blank bubble, no error, no note, nothing anywhere saying the
   answer was cut off. Tasks (tasksOnLoad), missions (missionsOnLoad) and the
   roster (persistableAgents) all learned this; the chat did not.

   `interrupted` is a durable marker and never a live one: chatOnLoad below
   spends it on the way in, and the finalize (`streaming: false`) that ends
   every real reply re-persists the record without it. */
const persistableChat = (xs) => capChatFair(xs, 80)
  .map(({ streaming, error, ...rest }) => (streaming ? { ...rest, interrupted: true } : rest));

/* Load-scrub for the chat, the read-side twin of the marker above. A reply
   the page outlived is said out loud, in the same voice tasksOnLoad uses for
   the run that died with it, and the marker is spent here so a later write
   cannot re-stamp it onto a bubble that is fine.

   Two endings because there are two: nothing had streamed at all (the common
   one — the debounce means the placeholder is usually all that reached
   disk), and something had. Neither invents an answer; both say what is
   missing and offer the way back.

   Both sentences are OFFICE VOICE and live in app/floor.jsx beside the visit
   templates, which is what keeps them out of the model's context: the note
   is written into `text`, and `text` is what `chatToMessages` sends as that
   coworker's own `assistant` turn. Measured under node on this exact chain,
   an interrupted reply that contributed nothing to the envelope before #348
   arrived at the brain as `{ role: 'assistant', content: '_(nothing came
   back — … Ask again when you want it.)_' }` — a turn the coworker never
   spoke, in the slot every chat API reads as "you said this". They are
   stripped at the choke point now (#349); say them on the screen, never in
   the prompt. */
const chatOnLoad = (xs) => (Array.isArray(xs) ? xs : []).map(m => {
  if (!m || !m.interrupted) return m;
  const { interrupted, ...rest } = m;
  const body = String(rest.text || '');
  return { ...rest, text: body ? body + '\n\n' + CHAT_CUT_NOTE : CHAT_GONE_NOTE };
});

/* #413 — the union that lets the conversation be file-backed at all.
   `chat` moved from useStored to useFileStored, and useFileStored's mount
   fetch has a "keep theirs" guard that is right for a snapshot (tasks,
   agents) and catastrophic for a log. Measured on the swap before this
   function existed: a fresh browser, the real conversation on disk, and the
   boss types one word inside the ~300ms before the fetch resolves. dirtyRef
   is true and the value is no longer the seed, so the fetch was discarded —
   and #232's replay then PUT the one-message local chat OVER the file.
   Every conversation the office had ever held, deleted by the first
   keystroke on a new device. `mergeOnDirty: true` plus this transform is
   what makes the swap safe, exactly as it is for `messages` and `activity`.

   Concatenation order, not a sort: the streaming placeholder
   (ui/chat.jsx:806) carries no `ts` at all, so a ts sort would file every
   live reply at the top of the transcript. The file is the older half and
   the in-memory list is the newer one, so file-order-then-new-arrivals is
   the chronology. In-memory wins on a shared id — it is the fresher copy of
   a reply that is still being written.

   `chatOnLoad` runs on the FETCHED side only. It spends the `interrupted`
   marker into a sentence, and a record this session is streaming right now
   has not been interrupted by anything. The cap is 100 to match the
   in-memory ceiling at app.jsx:1738 rather than persistableChat's 80 — the
   union is what state holds, and the write filter caps it again on the way
   to disk. */
const mergeChat = (inMem, fetched) => {
  const live = Array.isArray(inMem) ? inMem : [];
  const seen = new Map();
  for (const m of live) if (m && m.id) seen.set(m.id, m);
  const out = [];
  const placed = new Set();
  for (const m of chatOnLoad(fetched)) {
    if (!m) continue;
    const mine = m.id && seen.get(m.id);
    out.push(mine || m);
    if (m.id) placed.add(m.id);
  }
  for (const m of live) if (m && (!m.id || !placed.has(m.id))) out.push(m);
  return capChatFair(out, 100);
};

/* #418 — the cross-tab half of mergeChat, for useFileStored's `absorb`.
   `theirs` is what another tab just wrote to localStorage: persistableChat's
   output, so a reply THAT tab is streaming arrives here as `interrupted:
   true` with no `streaming`. Two things differ from the mount union above.

   Shared id: theirs wins, unless ours is `streaming`. At mount the in-memory
   copy is the fresher one by construction; across tabs the fresher copy is
   whichever tab is writing the record, and only the streaming tab writes
   it. Letting ours win unconditionally froze the other tab's reply at the
   first absorbed frame; letting theirs win unconditionally replaced a live
   reply with a copy of itself stamped cut-off. Ours-while-streaming is the
   one rule that is right in both directions, and it is what lets the
   finished reply reach the other tab on the finalize write.

   No chatOnLoad: the marker on the other tab's live reply is a durable fact
   for a reload to spend, not a sentence to append while the reply is still
   arriving over there. It is carried through untouched, so a tab that dies
   mid-stream still leaves the note for the next boot. Order is theirs-then-
   ours, as the mount union orders file-then-live, for the same reason. */
const absorbChat = (inMem, theirs) => {
  const live = Array.isArray(inMem) ? inMem : [];
  const mine = new Map();
  for (const m of live) if (m && m.id) mine.set(m.id, m);
  const out = [];
  const placed = new Set();
  for (const m of (Array.isArray(theirs) ? theirs : [])) {
    if (!m) continue;
    const ours = m.id && mine.get(m.id);
    out.push(ours && ours.streaming ? ours : m);
    if (m.id) placed.add(m.id);
  }
  for (const m of live) if (m && (!m.id || !placed.has(m.id))) out.push(m);
  return capChatFair(out, 100);
};

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

export { absorbChat, capChatFair, chatErrorText, chatOnLoad, k, ks, makeScreenEmitter, mergeByIdCap, mergeChat, mergeMessages, persistableAgents, persistableChat, persistableMessages, useFileStored, useStored };
