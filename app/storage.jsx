import { floorEmit, snagCause } from './floor.jsx';
import { handoffHint, withHandoff } from './cast.jsx';   // import-free module — no cycle
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
function useFileStored(lsKey, fileScope, fileName, initial, transform, { sensitive = false } = {}) {
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

  const writeRef = useRefA(null);
  // Set as soon as anything in this session mutates the value. The mount fetch
  // below resolves ~100-300ms after first render, so without this flag it
  // overwrites whatever the user typed (or an agent wrote) in that window, and
  // the debounced PUT then pushes the server's stale copy back — losing the
  // edit in both places. Local changes win; the server copy is only adopted
  // when the session hasn't touched it yet.
  const dirtyRef = useRefA(false);

  const persist = React.useCallback((v) => {
    try { localStorage.setItem(lsKey, JSON.stringify(v)); } catch (err) {
      /* Sensitive keys (API keys) have NO file fallback — if this write
         fails (quota, private mode) the key silently doesn't survive a
         reload. Surface it like useStored does instead of swallowing. */
      console.warn('[cafresohq] localStorage save failed for', lsKey, err);
      try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key: lsKey, error: err } })); } catch (_e) {}
    }
    if (sensitive) return;
    clearTimeout(writeRef.current);
    writeRef.current = setTimeout(() => {
      fetch(`${window._API_BASE || ''}/hq/${fileScope}/${fileName}`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(v),
      }).catch(() => {});
    }, 1500);
  }, [lsKey, fileScope, fileName, sensitive]);

  useEffectA(() => {
    if (sensitive) return;
    fetch(`${window._API_BASE || ''}/hq/${fileScope}/${fileName}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data == null) return;
        if (dirtyRef.current) return;   // the user got there first — keep theirs
        const merged = transform ? transform(data) : data;
        setVal(merged);
        try { localStorage.setItem(lsKey, JSON.stringify(merged)); } catch (_e) {}
      })
      .catch(() => {});
  }, []);  // intentionally runs once on mount

  const setter = React.useCallback((updater) => {
    dirtyRef.current = true;
    setVal(prev => {
      const next = typeof updater === 'function' ? updater(prev) : updater;
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
// Cap chat history at 80 entries so localStorage doesn't bloat.
const persistableChat = (xs) => xs.slice(-80).map(({ streaming, error, ...rest }) => rest);

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
const chatErrorText = (err, agents) => {
  const raw = (err && err.message) || String(err);
  const because = snagCause(raw);
  let out = '⚠ ' + because.charAt(0).toUpperCase() + because.slice(1);
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
    const hint = handoffHint(agents, C);
    const close = () => { if (!/[.!?…]$/.test(out)) out += '.'; };
    if (hint) {
      out = withHandoff(out, agents, C);   // closes the clause for us
    } else if (C && C.hasUsableKey && !C.hasUsableKey()) {
      close();
      out += ' You’re on the shared Cafreso brain — you can add your own AI key ' +
             'in Settings → Keys to run independently of it.';
    }
  } catch (_) {}
  return out;
};

// Cap messages registry at 500 entries (rolling) and strip any runtime-only
// fields before persisting. Messages are durable records of agent ↔ agent
// handoffs — they outlive the chat scrollback so the boss can always answer
// "what happened to the task I sent Selvin?" without scrolling. Keep state
// machine history bounded too — 30 entries per message is plenty.
const persistableMessages = (xs) => (Array.isArray(xs) ? xs.slice(-500) : []).map(m => ({
  ...m,
  history: Array.isArray(m.history) ? m.history.slice(-30) : [],
}));

// Message states form a directed lifecycle. All transitions append to
// history so we never lose the audit trail. `terminal` states can't be
// transitioned out of (except via explicit reopen).

export { chatErrorText, k, ks, makeScreenEmitter, mergeByIdCap, persistableAgents, persistableChat, persistableMessages, useFileStored, useStored };
