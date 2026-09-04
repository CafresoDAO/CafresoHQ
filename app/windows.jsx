const { useState: useStateA, useEffect: useEffectA, useMemo: useMemoA, useRef: useRefA, useCallback: useCallbackA } = React;
const MSG_STATES = {
  queued:       { label: 'Queued',       color: '#a89070', terminal: false },
  delivered:    { label: 'Delivered',    color: '#7d9bb5', terminal: false },
  in_progress:  { label: 'In progress',  color: '#7db5b5', terminal: false },
  blocked:      { label: 'Blocked',      color: '#d9a857', terminal: false },
  awaiting_reply:{label: 'Awaiting reply',color:'#9d9bb5', terminal: false },
  completed:    { label: 'Completed',    color: '#78b25f', terminal: true  },
  failed:       { label: 'Failed',       color: '#d95757', terminal: true  },
  cancelled:    { label: 'Cancelled',    color: '#888888', terminal: true  },
};

/* How far the navigation rail reaches, or 0 when it is not in the layout.
   The rail is `display: none` below the 768px breakpoint, so the only
   honest way to ask is to measure it rather than to re-derive the media
   query here and let the two drift.

   A floating window whose left edge starts before this line is sitting on
   the only route to nine of the ten views. Windows may cover the board;
   they may not cover the way out of it. */
function _railRight() {
  if (typeof document === 'undefined') return 0;
  const el = document.querySelector('aside.rail');
  if (!el) return 0;
  const r = el.getBoundingClientRect();
  return (r.width > 0 && r.height > 0) ? Math.round(r.right) : 0;
}

/* How far down a FRESH window's default y may start, so it does not open
   already sitting on top of the first row of controls in whatever view is
   showing underneath.

   Measured live on the Tasks board (2026-09-03), on a plain 1280x720
   session with no stored geometry — the single most common "brand new
   boss" starting point. `_chatAnchor`'s stock formula put the window at
   y=180; the Task Board's own "+ NEW" add-task row (opened, the ADD button
   spanning y≈191-224) sits directly under that. A real click on ADD at
   its rendered coordinates hit the chat window's drag handle instead —
   `elementFromPoint` confirmed it, a fixed/z-index:300 div — and the task
   was never created: no error, no visual break, the input just sat there
   un-submitted. Only a `.click()` called directly on the button element
   (bypassing hit-testing) actually filed the task. 235 clears that row
   with a little room to spare; it only binds at all on viewports short
   enough for the 460px-tall default to reach that high (below ~763px
   tall) — the 800px-tall fixture in
   test_a_window_never_covers_the_way_out.py never notices it, because
   800 - 460 - 80 = 260 already clears 235 on its own.

   Deliberately NOT threaded into `_chatGeometryStale` or `_chatClamp`:
   both of those also govern a position the boss chose by dragging, and
   `test_a_window_never_covers_the_way_out.py` pins that a deliberate
   placement clear of the rail (x=300, y=120) must never be moved again —
   "the boss's choice is final" for every axis this file does not treat as
   a hard floor. Adding this term there would silently re-open that
   contract for y. So this covers every FRESH session from here on; a
   geometry already saved under the old formula is left where the boss (or
   the old bug) put it, same as any other position on this axis. */
const CHAT_TOP_FLOOR = 235;

/* The three geometry decisions the chat window makes, kept as pure functions
   of (viewport, rail) so they can be exercised without a browser — the
   regression suite runs THESE, not a copy of them.

   `_chatAnchor` — where a fresh or re-anchored window goes. Where a 400px
   panel cannot clear the rail it gives up width before it gives up the
   navigation. With no rail in the layout the width term is
   `Math.min(400, VW - 32)` and the x term `Math.max(8, VW - w - 24)`, which
   is the bottom-right default this has always had. The y term is floored
   the same way at `CHAT_TOP_FLOOR` — see the comment on that constant. */
function _chatAnchor(VW, VH, rail) {
  const w = Math.min(400, Math.max(280, VW - rail - 32));
  const h = Math.min(460, VH - 24);
  return { x: Math.max(rail + 8, VW - w - 24), y: Math.max(CHAT_TOP_FLOOR, VH - h - 80), w, h };
}

/* `_chatGeometryStale` — whether a stored geometry has to be thrown away.
   Oversized (a past resize, a smaller screen, a corrupted value) makes the
   chat fill the screen; `x < rail` means it is sitting on the navigation;
   non-finite x/y would render as `NaNpx` and put the window nowhere at all. */
function _chatGeometryStale(g, VW, VH, rail) {
  if (!g || !(g.w > 0) || !(g.h > 0)) return true;
  if (!Number.isFinite(g.x) || !Number.isFinite(g.y)) return true;
  return g.w > VW - 12 || g.h > VH - 12 || g.x < rail;
}

/* `_chatClamp` — the per-render clamp. Keeps the window on screen, and keeps
   it off the navigation.

   The width cap is the interesting half, and the suite caught it: capping at
   `VW - 16` lets a window the boss resized almost to full width survive the
   stale check (it is not bigger than the viewport) and then leaves the
   on-screen clamp no room to place it anywhere but x=8, back on the rail. A
   floating window's room is the space beside the navigation, not the whole
   viewport, so that is what it is capped to — and with no rail in the layout
   the cap is `VW - 16` again, unchanged. */
function _chatClamp(g, VW, VH, rail) {
  const w = Math.max(280, Math.min(g.w, Math.max(280, VW - rail - 16)));
  const h = Math.max(220, Math.min(g.h, VH - 16));
  const hi = Math.max(8, VW - w - 8);
  return {
    x: Math.max(Math.min(Math.max(rail, 8), hi), Math.min(g.x, hi)),
    y: Math.max(8, Math.min(g.y, VH - h - 8)),
    w, h,
  };
}

/* `_frameClamp` — WindowFrame's on-screen clamp, lifted out of the render
   for the same reason `_chatClamp` exists: the gesture that MOVES a window
   has to start from the geometry the boss is looking at, and the only way
   to guarantee that is for both to call one function.

   Persisted geometry and rendered geometry are not the same number.
   `openWindows` is file-backed (app.jsx) and rides along in saved
   workspaces, so a window laid out on a 2560px monitor and restored on a
   1440px laptop arrives with x/w the viewport cannot hold; the render has
   always clamped it. What the gesture recorded as its origin was the RAW
   stored value, so the first pixel of a drag rewrote `left`/`top` from a
   position the window was never actually drawn at — the window jumped
   hundreds of px away from the cursor on mousedown, and mouseup committed
   the jump. Same shape in ChatWindow, whose stored geometry only has to
   clear `_chatGeometryStale` (w > VW-12 / h > VH-12 / x < rail) to survive,
   while `_chatClamp` caps width at the space beside the rail and y at
   VH-h-8 — a perfectly "fresh" geometry can still render far from where it
   is stored. */
function _frameClamp(g, VW, VH) {
  const w = Math.max(280, Math.min(g.w, VW - 16));
  const h = Math.max(200, Math.min(g.h, VH - 16));
  return {
    x: Math.max(8, Math.min(g.x, VW - w - 8)),
    y: Math.max(8, Math.min(g.y, VH - h - 8)),
    w, h,
  };
}

/* ─────────────────────────────────────────────────────────────────────
   WindowFrame — generic draggable + resizable window (the desktop "app
   window"). Same drag/resize engine as ChatWindow, generalized so any HQ
   view can mount in one. Drag the title bar to move; drag any edge/corner
   to resize. Geometry (x,y,w,h) commits to the caller's setGeometry once
   on mouseup. Move/up listeners attach only WHILE a gesture is active, so
   N mounted windows add ZERO idle listeners (preserves the perf contract).
   zIndex is injected by the window manager so clicking raises the window.
   ───────────────────────────────────────────────────────────────────── */
function WindowFrame({
  title, icon, geometry, setGeometry, zIndex, focused,
  onClose, onMinimize, onFocus, onToggleMax, maximized, headerExtra, children,
  minW = 320, minH = 240, hint,
}) {
  const winRef  = useRefA(null);
  const dragRef = useRefA(null);
  /* Work area = viewport minus topbar + dock strip. Drives maximize and
     left/right edge-snap (drag a window to a screen edge to tile it). */
  const _workArea = () => {
    const W = typeof window !== 'undefined' ? window.innerWidth  : 1280;
    const H = typeof window !== 'undefined' ? window.innerHeight : 720;
    const TOP = 54, BOTTOM = 86, SIDE = 8;
    return { x: SIDE, y: TOP, w: W - SIDE * 2, h: H - TOP - BOTTOM };
  };

  /* Esc closes (unless an input/textarea is focused — don't lose typing).
     Only the TOPMOST window responds — every mounted WindowFrame hears the
     same keydown, so without the `focused` gate one Esc would close them all. */
  React.useEffect(() => {
    if (!focused) return;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (e.__hqEscClaimed) return;
      const t = e.target, tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) return;
      e.__hqEscClaimed = true;
      onClose && onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, focused]);

  const _CURSORS = {
    move: 'grabbing',
    'resize-n': 'ns-resize',  'resize-s': 'ns-resize',
    'resize-e': 'ew-resize',  'resize-w': 'ew-resize',
    'resize-nw': 'nwse-resize', 'resize-se': 'nwse-resize',
    'resize-ne': 'nesw-resize', 'resize-sw': 'nesw-resize',
  };
  /* Clamp the (possibly stale/oversized) saved geometry to the viewport so
     a window can never exceed the screen or get lost off-screen. Computed
     HERE, above `startGesture`, so the gesture can take its origin from the
     same numbers the render below draws with — see `_frameClamp`. */
  const VW = typeof window !== 'undefined' ? window.innerWidth  : 1280;
  const VH = typeof window !== 'undefined' ? window.innerHeight : 720;
  const _shown = _frameClamp(geometry || { x: 80, y: 80, w: 480, h: 420 }, VW, VH);

  const startGesture = (e, mode) => {
    if (e.button !== 0) return;
    if (maximized) return; // no drag/resize while maximized — use restore first
    e.preventDefault();
    const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;
    const g = _shown;
    dragRef.current = { mode, startX: e.clientX, startY: e.clientY, origX: g.x, origY: g.y, origW: g.w, origH: g.h, lastX: e.clientX, lastY: e.clientY };
    document.body.style.userSelect = 'none';
    document.body.style.cursor     = _CURSORS[mode] || 'default';
    const onMove = (ev) => {
      const ds = dragRef.current, el = winRef.current;
      if (!ds || !el) return;
      ds.lastX = ev.clientX; ds.lastY = ev.clientY;
      const dx = ev.clientX - ds.startX, dy = ev.clientY - ds.startY;
      const W = window.innerWidth, H = window.innerHeight;
      if (ds.mode === 'move') {
        el.style.left = clamp(ds.origX + dx, -ds.origW + 80, W - 80) + 'px';
        el.style.top  = clamp(ds.origY + dy, 0, H - 40) + 'px';
        return;
      }
      const edges = ds.mode.slice('resize-'.length);
      let x = ds.origX, y = ds.origY, w = ds.origW, h = ds.origH;
      if (edges.includes('e')) w = clamp(ds.origW + dx, minW, W - ds.origX - 4);
      if (edges.includes('w')) { const shift = clamp(dx, -ds.origX, ds.origW - minW); x = ds.origX + shift; w = ds.origW - shift; }
      if (edges.includes('s')) h = clamp(ds.origH + dy, minH, H - ds.origY - 4);
      if (edges.includes('n')) { const shift = clamp(dy, -ds.origY, ds.origH - minH); y = ds.origY + shift; h = ds.origH - shift; }
      el.style.left = x + 'px'; el.style.top = y + 'px'; el.style.width = w + 'px'; el.style.height = h + 'px';
    };
    const onUp = () => {
      const ds = dragRef.current, el = winRef.current;
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = ''; document.body.style.cursor = '';
      if (!ds || !el) { dragRef.current = null; return; }
      // `|| fallback` would discard a legitimate 0 (dragged flush to the
      // viewport's left/top edge, which the clamp ranges above allow) —
      // parseFloat('0px') === 0 is falsy, so the window would silently
      // snap back to its pre-drag position on release. Number.isFinite
      // treats 0 as a real value and only falls back on a genuine parse
      // failure (NaN).
      const _px = v => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
      const next = {
        x: _px(el.style.left)   ?? ds.origX,
        y: _px(el.style.top)    ?? ds.origY,
        w: _px(el.style.width)  ?? ds.origW,
        h: _px(el.style.height) ?? ds.origH,
      };
      // Edge-snap on drop (move gestures only): top → maximize,
      // left/right → tile to that half of the work area.
      if (ds.mode === 'move' && ds.lastX != null) {
        const W = window.innerWidth;
        const wa = _workArea();
        if (ds.lastY <= 4 && onToggleMax) { dragRef.current = null; onToggleMax(); return; }
        if (ds.lastX <= 4) { dragRef.current = null; setGeometry && setGeometry({ x: wa.x, y: wa.y, w: Math.floor((wa.w - 6) / 2), h: wa.h }); return; }
        if (ds.lastX >= W - 4) { dragRef.current = null; setGeometry && setGeometry({ x: wa.x + Math.ceil((wa.w + 6) / 2), y: wa.y, w: Math.floor((wa.w - 6) / 2), h: wa.h }); return; }
      }
      dragRef.current = null;
      setGeometry && setGeometry(next);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  let { x, y, w, h } = _shown;
  if (maximized) { const wa = _workArea(); x = wa.x; y = wa.y; w = wa.w; h = wa.h; }

  return (
    <div
      ref={winRef}
      onMouseDownCapture={() => onFocus && onFocus()}
      className={'hq-window' + (focused ? ' focused' : '')}
      style={{
        position: 'fixed', left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px',
        zIndex: zIndex || 'var(--z-window)',
        background: 'var(--paper)', border: '2px solid var(--ink)', borderRadius: 6,
        boxShadow: focused ? '0 18px 48px rgba(0,0,0,0.34)' : '0 8px 24px rgba(0,0,0,0.20)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}
    >
      <div
        onMouseDown={(e) => startGesture(e, 'move')}
        onDoubleClick={onToggleMax ? () => onToggleMax() : undefined}
        className="hq-window-titlebar"
        style={{
          cursor: maximized ? 'default' : 'grab', display: 'flex', alignItems: 'center', gap: 8,
          padding: '7px 10px', borderBottom: '2px solid var(--ink)',
          background: 'var(--paper-2)', flexShrink: 0, userSelect: 'none',
        }}
      >
        {icon && <span style={{ display: 'inline-flex', pointerEvents: 'none' }}>{icon}</span>}
        <span style={{ fontSize: 12, fontWeight: 700, letterSpacing: 1, color: 'var(--ink)', pointerEvents: 'none' }}>{title}</span>
        {headerExtra}
        <span style={{ flex: 1, alignSelf: 'stretch' }} />
        {hint && !maximized && <span style={{ fontSize: 9, opacity: 0.5, letterSpacing: 1, pointerEvents: 'none' }}>{hint}</span>}
        {onMinimize && (
          <button onMouseDown={(e) => e.stopPropagation()} onClick={onMinimize} title="Minimize to dock"
            style={{ background: 'transparent', border: '1px solid var(--rule)', borderRadius: 4, color: 'var(--ink)', cursor: 'pointer', fontSize: 13, lineHeight: '14px', padding: '2px 8px', position: 'relative', zIndex: 4 }}>–</button>
        )}
        {onToggleMax && (
          <button onMouseDown={(e) => e.stopPropagation()} onClick={() => onToggleMax()} title={maximized ? 'Restore' : 'Maximize (or drag to top / double-click)'}
            style={{ background: 'transparent', border: '1px solid var(--rule)', borderRadius: 4, color: 'var(--ink)', cursor: 'pointer', fontSize: 11, lineHeight: '14px', padding: '2px 8px', position: 'relative', zIndex: 4 }}>{maximized ? '❐' : '▢'}</button>
        )}
        {onClose && (
          <button onMouseDown={(e) => e.stopPropagation()} onClick={onClose} title="Close (Esc)"
            style={{ background: 'transparent', border: '1px solid var(--rule)', borderRadius: 4, color: 'var(--ink)', cursor: 'pointer', fontSize: 12, padding: '2px 8px', position: 'relative', zIndex: 4 }}>✕</button>
        )}
      </div>
      <div className="hq-window-body" style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column' }}>
        {children}
      </div>
      {!maximized && <>
      <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-n'); }} style={{ position: 'absolute', left: 14, right: 14, top: 0, height: 6, cursor: 'ns-resize', zIndex: 2 }} />
      <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-s'); }} style={{ position: 'absolute', left: 14, right: 14, bottom: 0, height: 6, cursor: 'ns-resize', zIndex: 2 }} />
      <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-w'); }} style={{ position: 'absolute', top: 14, bottom: 14, left: 0, width: 6, cursor: 'ew-resize', zIndex: 2 }} />
      <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-e'); }} style={{ position: 'absolute', top: 14, bottom: 14, right: 0, width: 6, cursor: 'ew-resize', zIndex: 2 }} />
      <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-nw'); }} style={{ position: 'absolute', top: 0, left: 0, width: 14, height: 14, cursor: 'nwse-resize', zIndex: 3 }} />
      <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-ne'); }} style={{ position: 'absolute', top: 0, right: 0, width: 14, height: 14, cursor: 'nesw-resize', zIndex: 3 }} />
      <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-sw'); }} style={{ position: 'absolute', bottom: 0, left: 0, width: 14, height: 14, cursor: 'nesw-resize', zIndex: 3 }} />
      <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-se'); }} title="Drag to resize"
        style={{ position: 'absolute', right: 0, bottom: 0, width: 18, height: 18, cursor: 'nwse-resize', display: 'grid', placeItems: 'center', color: 'var(--ink-3)', userSelect: 'none', fontSize: 12, lineHeight: 1, zIndex: 3 }}>⋰</div>
      </>}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   ChatWindow
   Floating draggable + resizable popover used by Projects and Vault.
   Drag the title bar to move; drag the bottom-right corner to resize.
   Open/closed and geometry (x, y, w, h) persist in localStorage.

   Performance note: during drag/resize we mutate the DOM directly via
   ref, NOT React state. State commit happens once on mouseup. Without
   this the old drawer was triggering ~60 React re-renders/sec, which
   stalls the chat list (long virtualized history) and feels laggy.
   ───────────────────────────────────────────────────────────────────── */
function ChatWindow({ open, setOpen, geometry, setGeometry, messageCount, chatPanel, rosterPanel, agents }) {
  const [tab, setTab] = useStateA('chat'); // 'chat' | 'roster'
  const winRef    = useRefA(null);
  const dragRef   = useRefA(null); // active drag/resize state during gesture
  const isTouch   = typeof window !== 'undefined' &&
    window.matchMedia('(hover: none) and (pointer: coarse)').matches;
  // Full-screen the chat ONLY on small touch screens (phones). iPads/tablets are
  // touch but load the DESKTOP layout (>768px); there the chat must stay a
  // floating window so it doesn't cover the rail/topbar ("chat takes over").
  const fullScreen = isTouch && typeof window !== 'undefined' && window.innerWidth <= 768;

  /* Esc closes the window (unless an input is focused — don't lose typing).
     __hqEscClaimed: the focused WindowFrame listens on the same keydown; the
     claim flag ensures one Esc press closes exactly one window, not both. */
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      if (e.__hqEscClaimed) return;
      const t = e.target, tag = t && t.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || (t && t.isContentEditable)) return;
      e.__hqEscClaimed = true;
      setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  /* Global mousemove/mouseup driving the drag/resize. Single effect mounted
     once; reads dragRef.current to know what (if any) gesture is active.
     Resize modes are encoded as 'resize-<edges>' where <edges> is some
     subset of n/s/e/w (e.g. 'nw' = top-left corner, 'e' = right edge).
     Each character contributes a delta to one axis: n/s adjust top+height,
     e/w adjust left+width. Combining gives all 8 directions plus 'move'. */
  React.useEffect(() => {
    if (!open) return;
    const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;
    const MIN_W = 320, MIN_H = 260;
    const onMove = (e) => {
      const ds = dragRef.current;
      const el = winRef.current;
      if (!ds || !el) return;
      const dx = e.clientX - ds.startX;
      const dy = e.clientY - ds.startY;
      const W = window.innerWidth, H = window.innerHeight;
      if (ds.mode === 'move') {
        // Allow window to be moved fully within the viewport, leaving at
        // least 80px of header peeking back so it can't be lost off-screen.
        const nx = clamp(ds.origX + dx, -ds.origW + 80, W - 80);
        const ny = clamp(ds.origY + dy, 0, H - 40);
        el.style.left = nx + 'px';
        el.style.top  = ny + 'px';
        return;
      }
      // resize-<edges>
      const edges = ds.mode.slice('resize-'.length);
      let x = ds.origX, y = ds.origY, w = ds.origW, h = ds.origH;
      if (edges.includes('e')) {
        // Right edge: width grows with dx.
        w = clamp(ds.origW + dx, MIN_W, W - ds.origX - 4);
      }
      if (edges.includes('w')) {
        // Left edge: x moves with dx, width shrinks. Pin against viewport
        // and respect MIN_W by capping how far x can move right.
        const maxLeftShift = ds.origW - MIN_W;
        const shift = clamp(dx, -ds.origX, maxLeftShift);
        x = ds.origX + shift;
        w = ds.origW - shift;
      }
      if (edges.includes('s')) {
        h = clamp(ds.origH + dy, MIN_H, H - ds.origY - 4);
      }
      if (edges.includes('n')) {
        const maxTopShift = ds.origH - MIN_H;
        const shift = clamp(dy, -ds.origY, maxTopShift);
        y = ds.origY + shift;
        h = ds.origH - shift;
      }
      el.style.left   = x + 'px';
      el.style.top    = y + 'px';
      el.style.width  = w + 'px';
      el.style.height = h + 'px';
    };
    const onUp = () => {
      const ds = dragRef.current;
      const el = winRef.current;
      if (!ds || !el) return;
      // Snapshot current DOM geometry → commit to React state (single render).
      // `|| fallback` would discard a legitimate 0 (dragged flush to the
      // viewport's left/top edge, which the clamp ranges above allow) —
      // parseFloat('0px') === 0 is falsy, so the window would silently
      // snap back to its pre-drag position on release. Number.isFinite
      // treats 0 as a real value and only falls back on a genuine parse
      // failure (NaN).
      const _px = v => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
      const next = {
        x: _px(el.style.left)   ?? ds.origX,
        y: _px(el.style.top)    ?? ds.origY,
        w: _px(el.style.width)  ?? ds.origW,
        h: _px(el.style.height) ?? ds.origH,
      };
      dragRef.current = null;
      document.body.style.userSelect = '';
      document.body.style.cursor     = '';
      setGeometry(next);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup',   onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup',   onUp);
    };
  }, [open]);

  /* Repair: a persisted geometry bigger than the viewport (from a past resize,
     a smaller screen, or a corrupted value) makes the chat fill the whole
     screen. Reset it to the compact bottom-right default so the window is a
     sane floating panel again.

     `geometry.x < rail` is the second, worse case. Measured (#148) on a fresh
     office opened at 560x620: below the 768px breakpoint the rail is
     `display: none`, so this anchored the window at x=136 against a viewport
     with no navigation in it, and persisted that. Widening past 768 brought
     the rail back at 232px, and nothing recomputed the anchor — the clamp in
     the render below keeps a window on SCREEN, but its only lower bound was
     8, so it will hold one on top of the nav indefinitely. Reproduced further
     down the same path (a first mount at ≤432px wide anchors at x=8): six of
     the ten destinations were then unclickable at every sample point, with
     nothing on screen to say why.

     Hence the resize listener: the rail comes and goes with the breakpoint,
     and a window covering the nav is never a state worth preserving. It moves
     the window ONLY out of that state, so a position the boss chose anywhere
     else is left exactly where they put it. */
  React.useEffect(() => {
    if (isTouch) return;
    const repair = () => {
      const VW = typeof window !== 'undefined' ? window.innerWidth  : 1280;
      const VH = typeof window !== 'undefined' ? window.innerHeight : 720;
      const rail = _railRight();
      if (!_chatGeometryStale(geometry, VW, VH, rail)) return;
      setGeometry(_chatAnchor(VW, VH, rail));
    };
    repair();
    window.addEventListener('resize', repair);
    return () => window.removeEventListener('resize', repair);
  }, [geometry, isTouch]);

  /* Cursor lookup keyed by the 4-edge subset. Mirrors the standard CSS
     cursors so the arrow shape matches what the user is dragging. */
  const _CURSORS = {
    move: 'grabbing',
    'resize-n': 'ns-resize',  'resize-s': 'ns-resize',
    'resize-e': 'ew-resize',  'resize-w': 'ew-resize',
    'resize-nw': 'nwse-resize', 'resize-se': 'nwse-resize',
    'resize-ne': 'nesw-resize', 'resize-sw': 'nesw-resize',
  };
  const startGesture = (e, mode) => {
    if (e.button !== 0) return;
    e.preventDefault();
    /* The origin is where the window IS, which is the clamped geometry the
       render below drew — not the raw stored value. `_chatGeometryStale`
       lets through geometries that `_chatClamp` still moves (a window wider
       than the space beside the rail, or one whose y sits below VH-h-8), so
       reading `geometry` here made the first pixel of a drag teleport the
       window to a position it was never drawn at. */
    const VW = typeof window !== 'undefined' ? window.innerWidth  : 1280;
    const VH = typeof window !== 'undefined' ? window.innerHeight : 720;
    const g = _chatClamp(geometry, VW, VH, _railRight());
    dragRef.current = {
      mode,
      startX: e.clientX, startY: e.clientY,
      origX: g.x, origY: g.y, origW: g.w, origH: g.h,
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor     = _CURSORS[mode] || 'default';
  };

  const busyCount = (agents || []).filter(a => a.status === 'busy' || a.status === 'active').length;

  /* Closed state: small floating pill anchored bottom-right. */
  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        title="Open chat (Esc to close)"
        style={{
          position: 'fixed', bottom: 56, right: 16, zIndex: 'var(--z-window)',
          background: 'var(--paper)', color: 'var(--ink)',
          border: '2px solid var(--ink)',
          borderRadius: 999,
          padding: '8px 14px',
          fontSize: 11, fontWeight: 700, letterSpacing: 1,
          cursor: 'pointer',
          boxShadow: '0 6px 18px rgba(0,0,0,0.22)',
          display: 'flex', alignItems: 'center', gap: 8,
        }}
      >
        <span>💬</span>
        <span>CHAT</span>
        {messageCount > 0 && (
          <span style={{
            background: 'var(--accent-rose)', color: 'var(--ink)',
            borderRadius: 999, padding: '1px 7px', fontSize: 10,
          }}>{messageCount}</span>
        )}
        {busyCount > 0 && (
          <span style={{
            background: 'var(--accent-teal)', color: 'var(--ink)',
            borderRadius: 999, padding: '1px 7px', fontSize: 10,
          }}>● {busyCount}</span>
        )}
      </button>
    );
  }

  const tabBtn = (key, label, count) => (
    <button
      onMouseDown={(e) => e.stopPropagation()}
      onClick={() => setTab(key)}
      style={{
        background: tab === key ? 'var(--paper)' : 'transparent',
        border: '1px solid ' + (tab === key ? 'var(--ink)' : 'var(--rule)'),
        color: 'var(--ink)',
        fontSize: 11, fontWeight: 600, letterSpacing: 1,
        padding: '3px 9px', borderRadius: 4, cursor: 'pointer',
        position: 'relative', zIndex: 4,    // sit above corner resize handles
      }}
    >{label}{count != null && <span style={{opacity:0.55,marginLeft:4}}>{count}</span>}</button>
  );

  /* Open state: floating window on desktop, full-screen on touch. */
  return (
    <div
      ref={winRef}
      style={{
        position: 'fixed',
        ...(fullScreen
          ? { left: 0, top: 0, right: 0, bottom: 0, width: '100%', height: '100%' }
          : (() => {
              // Clamp the (possibly stale/oversized) saved geometry to the
              // current viewport so the window can never exceed the screen —
              // fixes a persisted geometry larger than the viewport rendering
              // the chat near-fullscreen, and keeps it on-screen after resizes.
              const VW = typeof window !== 'undefined' ? window.innerWidth  : 1280;
              const VH = typeof window !== 'undefined' ? window.innerHeight : 720;
              const { x, y, w, h } = _chatClamp(geometry, VW, VH, _railRight());
              return { left: x + 'px', top: y + 'px', width: w + 'px', height: h + 'px' };
            })()),
        zIndex: 'var(--z-window)',
        background: 'var(--paper)',
        border: '2px solid var(--ink)',
        borderRadius: fullScreen ? 0 : 6,
        boxShadow: fullScreen ? 'none' : '0 12px 36px rgba(0,0,0,0.28)',
        display: 'flex', flexDirection: 'column',
        overflow: 'hidden',
      }}
    >
      {/* Title bar — drag to move on desktop; static header on touch. The bar's EMPTY area is below the
          resize handles (so the very edges of the title bar are
          resize-zones); the bar's interactive children (tab buttons,
          close button) get position:relative + z-index:4 so they pop
          back above the corner handles and stay clickable. */}
      <div
        onMouseDown={isTouch ? undefined : (e) => startGesture(e, 'move')}
        style={{
          cursor: isTouch ? 'default' : 'grab',
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 12px',
          borderBottom: '2px solid var(--ink)',
          background: 'var(--paper-2)',
          flexShrink: 0,
          userSelect: 'none',
          minHeight: isTouch ? 52 : 'auto',
        }}
      >
        <span style={{fontSize: 12, fontWeight: 700, letterSpacing: 1, color: 'var(--ink)'}}>💬 CHAT</span>
        {tabBtn('chat',   'Chat',   messageCount > 0 ? messageCount : null)}
        {tabBtn('roster', 'Roster', (agents || []).length)}
        <span style={{flex: 1, alignSelf: 'stretch'}} />
        {!isTouch && <span style={{fontSize: 9, opacity: 0.55, letterSpacing: 1, pointerEvents: 'none'}}>drag · esc to close</span>}
        <button
          onMouseDown={(e) => e.stopPropagation()}
          onClick={() => setOpen(false)}
          title="Close (Esc)"
          style={{
            background: 'transparent',
            border: '1px solid var(--rule)', borderRadius: 4,
            color: 'var(--ink)', cursor: 'pointer',
            fontSize: 12, padding: '2px 8px',
            flexShrink: 0,
            position: 'relative', zIndex: 4,    // above corner resize handles
          }}
        >✕</button>
      </div>
      {/* Body — a flex COLUMN, not a block.
          As a block it gave .monitor no height to flex against, so the chat
          pane sized to its content: measured 10,144px tall inside a 417px
          window, which put the composer at y=10,401 in a 900px viewport.
          .screen was already doing everything right (overflow-y:auto,
          flex:1 1 0, min-height:0) — `flex:1` against an unbounded parent
          just resolves to "as tall as the messages".

          This scales with USE. A fresh install has three messages and looks
          fine; the pane grows with every exchange until the box you type
          into is a thousand scrolls below the window. The way you talk to
          your team is the one thing that must not degrade the more you use
          the office. Same shape as the note on .px-scene in styles.css: a
          pane must FILL its container, never grow past it. */}
      <div style={{flex: 1, overflow: 'auto', padding: 8, minHeight: 0, display: 'flex', flexDirection: 'column'}}>
        {tab === 'chat' ? chatPanel : rosterPanel}
      </div>
      {/* Resize handles — desktop / pointer devices only */}
      {!isTouch && <>
        {/* North edge */}
        <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-n'); }}
          style={{position:'absolute', left:14, right:14, top:0, height:6, cursor:'ns-resize', zIndex:2}}/>
        {/* South edge */}
        <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-s'); }}
          style={{position:'absolute', left:14, right:14, bottom:0, height:6, cursor:'ns-resize', zIndex:2}}/>
        {/* West edge */}
        <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-w'); }}
          style={{position:'absolute', top:14, bottom:14, left:0, width:6, cursor:'ew-resize', zIndex:2}}/>
        {/* East edge */}
        <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-e'); }}
          style={{position:'absolute', top:14, bottom:14, right:0, width:6, cursor:'ew-resize', zIndex:2}}/>
        {/* North-West corner */}
        <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-nw'); }}
          style={{position:'absolute', top:0, left:0, width:14, height:14, cursor:'nwse-resize', zIndex:3}}/>
        {/* North-East corner */}
        <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-ne'); }}
          style={{position:'absolute', top:0, right:0, width:14, height:14, cursor:'nesw-resize', zIndex:3}}/>
        {/* South-West corner */}
        <div onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-sw'); }}
          style={{position:'absolute', bottom:0, left:0, width:14, height:14, cursor:'nesw-resize', zIndex:3}}/>
        {/* South-East corner — keeps the visible "⋰" glyph as an affordance */}
        <div
          onMouseDown={(e) => { e.stopPropagation(); startGesture(e, 'resize-se'); }}
          title="Drag any edge or corner to resize"
          style={{
            position: 'absolute', right: 0, bottom: 0,
            width: 18, height: 18,
            cursor: 'nwse-resize',
            display: 'grid', placeItems: 'center',
            color: 'var(--ink-3)', userSelect: 'none',
            fontSize: 12, lineHeight: 1,
            zIndex: 3,
          }}
        >⋰</div>
      </>}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   Elevated-model auto-downgrade for non-elevated agents.

   Sub-agents and assistants are deliberately non-elevated for safety
   (no shell, no file write). But they often inherit their spawner /
   senior's model. If that model lives in an elevation-only provider
   (`cafresohq:` or `codex:`), the upstream stream() refuses the request:
     "CafresoHQ provider requires the agent to be elevated."

   Rather than fail, we swap to the closest non-elevated equivalent:
     cafresohq:claude-sonnet-4-5  → claudecode:claude-sonnet-4-5
     codex:gpt-5.5               → oca:oca/gpt-5.5
   If no clean swap exists (or settings are missing), fall back to
   the user's globally-configured anthropic / claudecode model, then
   to bare 'haiku' as last resort.

   Returns { model, swapped, why }. `swapped: false` means the input
   was already non-elevated and is returned unchanged. Caller decides
   how prominently to surface the swap (system chat note, toast, etc).
   ───────────────────────────────────────────────────────────────────── */

/* `_chatAnchor` and `_railRight` are exported too, alongside the component —
   not for the test suite (scripts/test_a_window_never_covers_the_way_out.py
   lifts them from source text on purpose, precisely so it runs the SHIPPED
   arithmetic even if this export list is ever trimmed) but for `app.jsx`,
   which used to carry its OWN copy of this exact formula as the lazy
   initial value for the persisted `chatWinGeoV2` state — the value a fresh
   session (nothing in localStorage yet) actually gets, before `ChatWindow`'s
   own repair effect ever runs. Two implementations of "where does the chat
   window start" is exactly the shape #148 was about; this one hid because
   `_chatGeometryStale` had no complaint about the duplicate's OUTPUT (a
   well-formed-looking `{x:856,y:180,w:400,h:460}` clears every existing
   staleness check), so the repair effect never fired to paper over it. */
export { ChatWindow, MSG_STATES, WindowFrame, _chatAnchor, _railRight };
