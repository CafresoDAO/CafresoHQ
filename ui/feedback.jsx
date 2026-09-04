import { ToastCtx } from './primitives.jsx';
const { useState, useEffect, useLayoutEffect, useRef, useMemo, createContext, useContext } = React;
const TOAST_KINDS = {
  info:    { icon: 'ℹ',  duration: 3500 },
  success: { icon: '✓',  duration: 3500 },
  warn:    { icon: '⚠',  duration: 5000 },
  error:   { icon: '✕',  duration: 6000 },
  action:  { icon: '✦',  duration: 7000 },
};
const TOAST_VISIBLE_MAX = 3;
let _toastSeq = 0;

/* Settings -> Appearance -> "Sound FX · pixel blips on action" persisted a
   real boolean, rendered a real-looking switch, and drove nothing — no
   audio API call existed anywhere in the app. Every toast already funnels
   through this one `push()`, so this is the one choke point that can make
   every existing toast() call site (dozens, across the whole app) actually
   blip, with no call site itself needing to change. No audio assets: a
   short synthesized WebAudio tone, frequency/timbre varying by kind, so
   "something good happened" and "something broke" are distinguishable by
   ear the same way they already are by icon and color. Reads the setting
   fresh from localStorage each time rather than threading React state down
   here, since `sound` lives in app.jsx's top-level useStored and this
   provider has no parent/child relationship to it — it's a cross-cutting
   preference, the same way the persisted key itself is. */
let _blipCtx = null;
const BLIP_TONE = {
  success: { freq: 880, type: 'sine', duration: 0.09 },
  error:   { freq: 180, type: 'square', duration: 0.16 },
  warn:    { freq: 330, type: 'triangle', duration: 0.12 },
  info:    { freq: 520, type: 'sine', duration: 0.07 },
  action:  { freq: 660, type: 'sine', duration: 0.09 },
};
function playToastBlip(kind) {
  try {
    if (typeof window === 'undefined' || typeof localStorage === 'undefined') return;
    const raw = localStorage.getItem('cafresohq_hq_v1:sound');
    if (raw == null || JSON.parse(raw) !== true) return;
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    if (!_blipCtx) _blipCtx = new Ctx();
    if (_blipCtx.state === 'suspended') _blipCtx.resume().catch(() => {});
    const tone = BLIP_TONE[kind] || BLIP_TONE.info;
    const osc = _blipCtx.createOscillator();
    const gain = _blipCtx.createGain();
    osc.type = tone.type;
    osc.frequency.value = tone.freq;
    const now = _blipCtx.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(0.18, now + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + tone.duration);
    osc.connect(gain);
    gain.connect(_blipCtx.destination);
    osc.start(now);
    osc.stop(now + tone.duration + 0.02);
  } catch (_e) { /* autoplay policy, no AudioContext, etc — silent is fine, this is a beep */ }
}

function ToastProvider({ children }) {
  const [stack, setStack] = useState([]);   // visible toasts (max 3)
  const queueRef = useRef([]);              // queued toasts waiting to be shown
  const timersRef = useRef(new Map());      // id → timeout handle
  const dismissingRef = useRef(new Set());  // ids already mid-exit-animation

  const dismiss = React.useCallback((id) => {
    /* The ✕ button (below) never disables itself during the 220ms exit
       animation — `.is-leaving` is CSS-only, no pointer-events:none — so a
       double-click, or a click racing the toast's own auto-dismiss timer,
       calls dismiss() twice for the same id. Both calls used to schedule
       their own setTimeout, and both unconditionally shifted one entry off
       the queue: one user dismissal drained two queued toasts, and the
       second's `[...stack, queued].slice(-TOAST_VISIBLE_MAX)` could evict a
       toast that was still visible with its own auto-dismiss timer still
       running — an active, unread notification disappearing with no
       dismissal of its own. Guard re-entry per id instead. */
    if (dismissingRef.current.has(id)) return;
    dismissingRef.current.add(id);
    setStack(s => {
      const next = s.map(t => t.id === id ? { ...t, leaving: true } : t);
      return next;
    });
    /* clear pending dismiss timer (entry shape: { handle, remaining, … }) */
    const entry = timersRef.current.get(id);
    if (entry) {
      if (entry.handle) clearTimeout(entry.handle);
      timersRef.current.delete(id);
    }
    /* after exit animation, drop it from stack and pull next from queue */
    setTimeout(() => {
      dismissingRef.current.delete(id);
      setStack(s => s.filter(t => t.id !== id));
      const queued = queueRef.current.shift();
      if (queued) {
        setStack(s => [...s, queued].slice(-TOAST_VISIBLE_MAX));
        scheduleAutoDismiss(queued);
        playToastBlip(queued.kind);
      }
    }, 220);
  }, []);

  const scheduleAutoDismiss = React.useCallback((toast) => {
    if (!toast.duration || toast.duration <= 0) return;
    /* Track remaining time so hover-pause can resume cleanly. */
    const startedAt = Date.now();
    const handle = setTimeout(() => dismiss(toast.id), toast.duration);
    timersRef.current.set(toast.id, { handle, remaining: toast.duration, startedAt, paused: false });
  }, [dismiss]);

  const pauseToast = React.useCallback((id) => {
    const entry = timersRef.current.get(id);
    if (!entry || entry.paused) return;
    clearTimeout(entry.handle);
    const elapsed = Date.now() - entry.startedAt;
    entry.remaining = Math.max(200, entry.remaining - elapsed);
    entry.paused = true;
    timersRef.current.set(id, entry);
    setStack(s => s.map(t => t.id === id ? { ...t, paused: true } : t));
  }, []);

  const resumeToast = React.useCallback((id) => {
    const entry = timersRef.current.get(id);
    if (!entry || !entry.paused) return;
    entry.startedAt = Date.now();
    entry.paused = false;
    entry.handle = setTimeout(() => dismiss(id), entry.remaining);
    timersRef.current.set(id, entry);
    setStack(s => s.map(t => t.id === id ? { ...t, paused: false } : t));
  }, [dismiss]);

  const push = React.useCallback((kind, titleOrToast, options) => {
    /* Allow toast.push({...}) with full object, OR toast.info('text', {...}) */
    let t;
    if (typeof titleOrToast === 'object' && titleOrToast !== null) {
      t = { ...titleOrToast, kind: titleOrToast.kind || kind };
    } else {
      t = { ...(options || {}), kind, title: String(titleOrToast ?? '') };
    }
    const defaults = TOAST_KINDS[t.kind] || TOAST_KINDS.info;
    const id = t.id || ('tst-' + (++_toastSeq));
    const finalToast = {
      id,
      kind: t.kind,
      title: t.title,
      detail: t.detail,
      icon: t.icon ?? defaults.icon,
      duration: t.duration ?? defaults.duration,
      actionLabel: t.actionLabel,
      onAction: t.onAction,
      dismissable: t.dismissable !== false,
    };
    setStack(s => {
      if (s.length < TOAST_VISIBLE_MAX) {
        scheduleAutoDismiss(finalToast);
        playToastBlip(finalToast.kind);
        return [...s, finalToast];
      }
      queueRef.current.push(finalToast);
      return s;
    });
    return id;
  }, [scheduleAutoDismiss]);

  const dismissAll = React.useCallback(() => {
    queueRef.current = [];
    stack.forEach(t => dismiss(t.id));
  }, [stack, dismiss]);

  const api = React.useMemo(() => ({
    push,
    info:    (t, o) => push('info', t, o),
    success: (t, o) => push('success', t, o),
    warn:    (t, o) => push('warn', t, o),
    error:   (t, o) => push('error', t, o),
    action:  (t, o) => push('action', t, o),
    dismiss,
    dismissAll,
  }), [push, dismiss, dismissAll]);

  /* Expose imperative entry point for non-React callers (legacy event
     listeners, runners, etc.). Last provider wins. */
  React.useEffect(() => {
    window.cafresohqToast = api;
    return () => { if (window.cafresohqToast === api) delete window.cafresohqToast; };
  }, [api]);

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <ToastStack toasts={stack} onDismiss={dismiss} onPause={pauseToast} onResume={resumeToast} />
      <DialogHost />
    </ToastCtx.Provider>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   DialogHost — in-app replacement for window.confirm / window.prompt.
   Native dialogs break the pixel aesthetic, block the JS thread, and on
   some hosts (iframe sandboxes) are silently disabled. Promise-based:

     const ok   = await window.hqConfirm('Delete "x"?', { danger: true });
     const name = await window.hqPrompt('New folder name:', { value: '' });

   hqConfirm resolves true/false; hqPrompt resolves string | null — the
   same contract as the natives, so call sites only add `await`. Both
   fall back to the native dialog if the host isn't mounted (popouts,
   early boot). Piggybacks ToastProvider's "last provider wins" pattern.
   ───────────────────────────────────────────────────────────────────── */
function DialogHost() {
  const [req, setReq] = useState(null); // {kind, message, opts, resolve}
  const [draft, setDraft] = useState('');
  const inputRef = useRef(null);
  const okRef = useRef(null);

  useEffect(() => {
    const ask = (kind, message, opts) => new Promise(resolve => {
      setDraft(kind === 'prompt' ? String((opts && opts.value) ?? '') : '');
      setReq({ kind, message: String(message ?? ''), opts: opts || {}, resolve });
    });
    const prevConfirm = window.hqConfirm, prevPrompt = window.hqPrompt;
    window.hqConfirm = (m, o) => ask('confirm', m, o);
    window.hqPrompt  = (m, o) => ask('prompt', m, o);
    return () => { window.hqConfirm = prevConfirm; window.hqPrompt = prevPrompt; };
  }, []);

  useEffect(() => {
    if (!req) return;
    const t = setTimeout(() => {
      if (req.kind === 'prompt' && inputRef.current) { inputRef.current.focus(); inputRef.current.select(); }
      else if (okRef.current) okRef.current.focus();
    }, 30);
    return () => clearTimeout(t);
  }, [req]);

  if (!req) return null;
  const done = (result) => { const r = req.resolve; setReq(null); r(result); };
  const cancelValue = req.kind === 'prompt' ? null : false;
  const okValue = () => req.kind === 'prompt' ? draft : true;
  const onKey = (e) => {
    if (e.key === 'Escape') { e.stopPropagation(); done(cancelValue); }
    if (e.key === 'Enter') {
      /* Enter must NOT resolve OK when focus sits on a different button —
         the old `req.kind === 'confirm'` arm made this branch fire for ANY
         Enter in a confirm dialog, so Tab→Cancel→Enter resolved TRUE (the
         keydown bubbles here and settles the promise before the Cancel
         button's own native click can resolve false): the keyboard path to
         declining a danger dialog performed the deletion instead. Let a
         non-OK button's native Enter activation (its onClick) do its job. */
      if (e.target instanceof HTMLButtonElement && e.target !== okRef.current) return;
      e.stopPropagation(); done(okValue());
    }
  };
  const danger = !!req.opts.danger;
  return (
    <div className="backdrop" style={{ zIndex: 'var(--z-modal, 1000)' }} onMouseDown={e => { if (e.target === e.currentTarget) done(cancelValue); }}>
      <div className="modal oc-dialog" role={req.kind === 'confirm' ? 'alertdialog' : 'dialog'} aria-modal="true"
        onKeyDown={onKey} style={{ maxWidth: 420, width: 'min(94vw, 420px)' }}>
        <div className="oc-dialog-msg">{req.message}</div>
        {req.kind === 'prompt' && (
          <input ref={inputRef} className="oc-dialog-in" value={draft}
            onChange={e => setDraft(e.target.value)}
            placeholder={req.opts.placeholder || ''} />
        )}
        <div className="oc-dialog-acts">
          {/* An informational dialog has one way out, and offering "Cancel"
              next to "Got it" asks the boss to choose between two words
              that mean the same thing. Escape and the backdrop still
              resolve, so nothing becomes untrappable. */}
          {!req.opts.hideCancel && (
            <button className="px-btn secondary" onClick={() => done(cancelValue)}>{req.opts.cancelLabel || 'Cancel'}</button>
          )}
          <button ref={okRef} className={'px-btn ' + (danger ? 'danger' : 'primary')} onClick={() => done(okValue())}>
            {req.opts.okLabel || (danger ? 'Delete' : 'OK')}
          </button>
        </div>
      </div>
    </div>
  );
}

/* Fallbacks so `await window.hqConfirm(...)` is always safe to call, even
   before/without a mounted DialogHost (graph popout, boot races). */
if (typeof window !== 'undefined') {
  if (!window.hqConfirm) window.hqConfirm = (m) => Promise.resolve(window.confirm(m));
  if (!window.hqPrompt)  window.hqPrompt  = (m, o) => Promise.resolve(window.prompt(m, (o && o.value) || ''));
}

function ToastStack({ toasts, onDismiss, onPause, onResume }) {
  if (!toasts.length) return null;
  return (
    <div className="oc-toast-stack" role="region" aria-label="Notifications">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`oc-toast kind-${t.kind} ${t.leaving ? 'is-leaving' : ''} ${t.paused ? 'is-paused' : ''}`}
          role={t.kind === 'error' ? 'alert' : 'status'}
          aria-live={t.kind === 'error' ? 'assertive' : 'polite'}
          onMouseEnter={() => onPause && onPause(t.id)}
          onMouseLeave={() => onResume && onResume(t.id)}
        >
          <span className="oc-toast-icon" aria-hidden="true">{t.icon}</span>
          <div className="oc-toast-body">
            <div className="oc-toast-title">{t.title}</div>
            {t.detail && <div className="oc-toast-detail">{t.detail}</div>}
          </div>
          {t.actionLabel && t.onAction && (
            <button
              className="oc-toast-action"
              onClick={() => { try { t.onAction(); } finally { onDismiss(t.id); } }}
            >{t.actionLabel}</button>
          )}
          {t.dismissable && (
            <button
              className="oc-toast-close"
              onClick={() => onDismiss(t.id)}
              aria-label="Dismiss notification"
            >✕</button>
          )}
          {t.duration > 0 && (
            <div
              className="oc-toast-progress"
              style={{ animationDuration: t.duration + 'ms' }}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function useToast() {
  const ctx = React.useContext(ToastCtx);
  if (!ctx) {
    /* If something tries to toast before the provider mounts, fall back to
       the imperative window handle (which may also be missing — return a
       no-op shape so callers don't crash). */
    return window.cafresohqToast || {
      push: () => {}, info: () => {}, success: () => {},
      warn: () => {}, error: () => {}, action: () => {},
      dismiss: () => {}, dismissAll: () => {},
    };
  }
  return ctx;
}

/* ─────────────────────────────────────────────────────────────────────
   Command Palette (Cmd/Ctrl-K)
   <CommandPaletteProvider> wraps the app once and listens for Cmd/Ctrl-K.
   Any view can register commands while mounted via:
       useCommands([
         { id, label, section, icon, run, detail, when, hidden, shortcut }
       ], deps)
   When the view unmounts the commands automatically deregister, so the
   palette only shows actions that make sense in the current context.

   Command shape:
     id        str       stable id (for tracking selection across re-renders)
     label     str       what the user sees
     section   str       group header (e.g. "Navigation", "Agents")
     icon      str|node  optional emoji or icon
     run       fn        invoked when the user picks the command
     detail    str       optional secondary text on the right
     shortcut  str[]     optional kb hint, e.g. ['⌘','S']
     when      fn|bool   show only when fn() is truthy / bool is true
     hidden    bool      pre-filtered out (use for transient cmds)

   Imperative escape hatch:
     window.cafresohqPalette.open()    — open the palette
     window.cafresohqPalette.close()   — close it
     window.cafresohqPalette.run(id)   — invoke a command by id
   ───────────────────────────────────────────────────────────────────── */
const PaletteCtx = React.createContext(null);

function CommandPaletteProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(0);
  /* Keyed registry: each useCommands() call gets a slot, identified by a
     symbol generated by the hook. We store arrays per slot and flatten on read.
     `rev` is bumped on every register/unregister so flatCommands re-computes. */
  const slotsRef = useRef(new Map());      // Map<symbol, command[]>
  const [rev, setRev] = useState(0);
  const bumpRev = React.useCallback(() => setRev(r => r + 1), []);

  const flatCommands = React.useMemo(() => {
    const out = [];
    for (const list of slotsRef.current.values()) for (const c of list) out.push(c);
    return out.filter(c => !c.hidden && (c.when == null || (typeof c.when === 'function' ? c.when() : c.when)));
  }, [open, query, rev]);

  /* Filter + naive fuzzy ranking: prefix > substring > none. */
  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return flatCommands;
    return flatCommands
      .map(c => {
        const lbl = (c.label || '').toLowerCase();
        const sect = (c.section || '').toLowerCase();
        let score = 0;
        // Word-start must be checked BEFORE plain substring: a match at the
        // start of any word is necessarily also a substring match, so with
        // the reverse order the substring branch always fired first and the
        // word-start score (meant to outrank a mid-word substring hit) was
        // unreachable dead code.
        if (lbl.startsWith(q)) score = 100;
        else if (lbl.split(/\s+/).some(w => w.startsWith(q))) score = 80;
        else if (lbl.includes(q)) score = 60;
        else if (sect.includes(q)) score = 30;
        return { c, score };
      })
      .filter(x => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .map(x => x.c);
  }, [flatCommands, query]);

  /* Group by section in display order, but keep search-ranked order intact. */
  const grouped = React.useMemo(() => {
    if (query.trim()) return [{ section: '', items: filtered }];
    const order = [];
    const map = new Map();
    for (const c of filtered) {
      const s = c.section || 'Other';
      if (!map.has(s)) { map.set(s, []); order.push(s); }
      map.get(s).push(c);
    }
    return order.map(s => ({ section: s, items: map.get(s) }));
  }, [filtered, query]);

  const flatVisible = React.useMemo(() => grouped.flatMap(g => g.items), [grouped]);

  React.useEffect(() => {
    if (selectedIdx >= flatVisible.length) setSelectedIdx(0);
  }, [flatVisible.length]);

  const register = React.useCallback((slot, list) => {
    slotsRef.current.set(slot, list);
    bumpRev();
  }, [bumpRev]);
  const unregister = React.useCallback((slot) => {
    slotsRef.current.delete(slot);
    bumpRev();
  }, [bumpRev]);

  const close = React.useCallback(() => {
    setOpen(false);
    setQuery('');
    setSelectedIdx(0);
  }, []);

  const openIt = React.useCallback(() => {
    setQuery('');
    setSelectedIdx(0);
    setOpen(true);
  }, []);

  const runCmd = React.useCallback((cmd) => {
    if (!cmd) return;
    close();
    /* Defer the run() so the palette closes/blurs first — avoids weird
       focus issues when the command opens another modal. */
    setTimeout(() => { try { cmd.run && cmd.run(); } catch (e) { console.error(e); } }, 30);
  }, [close]);

  const runById = React.useCallback((id) => {
    const c = flatCommands.find(x => x.id === id);
    runCmd(c);
  }, [flatCommands, runCmd]);

  /* Global Cmd/Ctrl-K to open. */
  React.useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault();
        if (open) close(); else openIt();
        return;
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, openIt, close]);

  /* Imperative window handle. */
  React.useEffect(() => {
    window.cafresohqPalette = {
      open: openIt, close, run: runById,
      list: () => flatCommands.map(c => ({ id: c.id, label: c.label, section: c.section })),
    };
    return () => { if (window.cafresohqPalette) delete window.cafresohqPalette; };
  }, [openIt, close, runById, flatCommands]);

  const api = React.useMemo(() => ({
    register, unregister, open: openIt, close, run: runById,
  }), [register, unregister, openIt, close, runById]);

  return (
    <PaletteCtx.Provider value={api}>
      {children}
      {open && <PaletteUI
        query={query} setQuery={setQuery}
        selectedIdx={selectedIdx} setSelectedIdx={setSelectedIdx}
        grouped={grouped} flatVisible={flatVisible}
        onPick={runCmd} onClose={close}
      />}
    </PaletteCtx.Provider>
  );
}

function PaletteFab() {
  return (
    <button className="palette-fab" aria-label="Open command palette"
      onClick={() => window.cafresohqPalette && window.cafresohqPalette.open()}>
      <span style={{fontSize: 22, lineHeight: 1}}>🛠️</span>
    </button>
  );
}

function PaletteUI({ query, setQuery, selectedIdx, setSelectedIdx, grouped, flatVisible, onPick, onClose }) {
  const inputRef = useRef(null);
  const isMobile = typeof window !== 'undefined' && window.innerWidth <= 768;
  React.useEffect(() => {
    if (!isMobile) setTimeout(() => inputRef.current && inputRef.current.focus(), 30);
  }, []);

  const handleKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); onClose(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIdx(i => (i + 1) % Math.max(1, flatVisible.length));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIdx(i => (i - 1 + flatVisible.length) % Math.max(1, flatVisible.length));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      onPick(flatVisible[selectedIdx]);
    }
  };

  /* Compute global index across grouped sections so highlighting maps right. */
  let runningIdx = 0;

  return (
    <>
      <div className="oc-palette-backdrop" onClick={onClose} />
      <div
        className="oc-palette"
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onKeyDown={handleKey}
      >
        <div className="oc-palette-header">
          <input
            ref={inputRef}
            className="oc-palette-input"
            placeholder="Search commands…"
            value={query}
            onChange={e => { setQuery(e.target.value); setSelectedIdx(0); }}
            /* No onKeyDown here — the dialog div below already carries
               handleKey, and a native keydown on this input bubbles up to
               it same as it would from anywhere else in the dialog (the
               close button, an empty-state div, etc). Attaching the SAME
               handler here too used to mean every keystroke ran handleKey
               twice per event (input handler, then the bubbled copy at the
               div): ArrowDown/ArrowUp skipped two rows instead of one —
               unreachable via keyboard for a row at an odd offset from the
               current selection whenever the list length made the second
               step land back on an already-visited index — and Enter
               invoked onPick (so cmd.run()) twice, double-firing whatever
               the selected command does (a second confirm dialog, a
               second dispatch, etc). */
          />
          <button className="oc-palette-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="oc-palette-list">
          {flatVisible.length === 0 && <div className="oc-palette-empty">No commands match "{query}"</div>}
          {grouped.map((g, gi) => (
            <React.Fragment key={g.section || gi}>
              {g.section && <div className="oc-palette-section">{g.section}</div>}
              {g.items.map((c) => {
                const isSel = runningIdx === selectedIdx;
                const myIdx = runningIdx;
                runningIdx += 1;
                return (
                  <div
                    key={c.id}
                    className={'oc-palette-row' + (isSel ? ' is-selected' : '')}
                    onMouseEnter={() => setSelectedIdx(myIdx)}
                    onClick={() => onPick(c)}
                    role="option"
                    aria-selected={isSel}
                  >
                    {c.icon && <span className="oc-palette-icon" aria-hidden="true">{c.icon}</span>}
                    <span className="oc-palette-label">{c.label}</span>
                    {c.detail && <span className="oc-palette-detail">{c.detail}</span>}
                    {c.shortcut && (
                      <span className="oc-palette-shortcut">
                        {c.shortcut.map((k, i) => <kbd key={i}>{k}</kbd>)}
                      </span>
                    )}
                  </div>
                );
              })}
            </React.Fragment>
          ))}
        </div>
        <div className="oc-palette-foot">
          <span><kbd>↑</kbd> <kbd>↓</kbd> navigate · <kbd>↵</kbd> run · <kbd>Esc</kbd> close</span>
          <span>{flatVisible.length} command{flatVisible.length === 1 ? '' : 's'}</span>
        </div>
      </div>
    </>
  );
}

/* Hook for components to register commands. Pass an array of command
   objects + a deps array (just like useEffect). The hook deregisters
   on unmount or when deps change.

   Example:
     useCommands([
       { id: 'open-foo', label: 'Open Foo', section: 'Navigation', run: () => …, icon: '📁' },
     ], []);
*/
function useCommands(commands, deps = []) {
  const ctx = React.useContext(PaletteCtx);
  const slot = React.useMemo(() => Symbol('cmd-slot'), []);
  React.useEffect(() => {
    if (!ctx) return;
    ctx.register(slot, commands || []);
    return () => ctx.unregister(slot);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

/* ─────────────────────────────────────────────────────────────────────
   <NotificationBell> + <NotificationCenter>
   Single bell icon in the topbar. Click to open a slide-in side panel
   with the combined feed of: receipts, agent activity, mission updates,
   approvals, system events. Filterable. Replaces the multiple
   floating bottom-right widgets that were colliding (ReceiptsTray,
   agent activity dots, status pills).

   The notifications are passed in as a prop (notifications=[…]) so
   the host app controls the source of truth. Each item:
     { id, kind, msg, ts, unread, source, onClick }

   kinds: 'receipt' | 'agent' | 'mission' | 'approval' | 'system'
   ───────────────────────────────────────────────────────────────────── */

export { CommandPaletteProvider, PaletteFab, ToastProvider, useCommands, useToast };
