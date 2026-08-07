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
  const startGesture = (e, mode) => {
    if (e.button !== 0) return;
    if (maximized) return; // no drag/resize while maximized — use restore first
    e.preventDefault();
    const clamp = (v, lo, hi) => v < lo ? lo : v > hi ? hi : v;
    const g = geometry || { x: 80, y: 80, w: 480, h: 420 };
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
      const next = {
        x: parseFloat(el.style.left)   || ds.origX,
        y: parseFloat(el.style.top)    || ds.origY,
        w: parseFloat(el.style.width)  || ds.origW,
        h: parseFloat(el.style.height) || ds.origH,
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

  /* Clamp the (possibly stale/oversized) saved geometry to the viewport so
     a window can never exceed the screen or get lost off-screen. */
  const VW = typeof window !== 'undefined' ? window.innerWidth  : 1280;
  const VH = typeof window !== 'undefined' ? window.innerHeight : 720;
  const g = geometry || { x: 80, y: 80, w: 480, h: 420 };
  let w = Math.max(280, Math.min(g.w, VW - 16));
  let h = Math.max(200, Math.min(g.h, VH - 16));
  let x = Math.max(8, Math.min(g.x, VW - w - 8));
  let y = Math.max(8, Math.min(g.y, VH - h - 8));
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
      const next = {
        x: parseFloat(el.style.left)   || ds.origX,
        y: parseFloat(el.style.top)    || ds.origY,
        w: parseFloat(el.style.width)  || ds.origW,
        h: parseFloat(el.style.height) || ds.origH,
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

  /* One-time repair: a persisted geometry bigger than the viewport (from a past
     resize, a smaller screen, or a corrupted value) makes the chat fill the
     whole screen. Reset it to the compact bottom-right default so the window is
     a sane floating panel again. Runs once on mount. */
  React.useEffect(() => {
    if (isTouch) return;
    const VW = typeof window !== 'undefined' ? window.innerWidth  : 1280;
    const VH = typeof window !== 'undefined' ? window.innerHeight : 720;
    const bad = !geometry || !(geometry.w > 0) || !(geometry.h > 0)
      || geometry.w > VW - 12 || geometry.h > VH - 12;
    if (bad) {
      const w = Math.min(400, VW - 24), h = Math.min(460, VH - 24);
      setGeometry({ x: Math.max(8, VW - w - 24), y: Math.max(8, VH - h - 80), w, h });
    }
  }, []);

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
    const g = geometry;
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
              const w = Math.max(280, Math.min(geometry.w, VW - 16));
              const h = Math.max(220, Math.min(geometry.h, VH - 16));
              const x = Math.max(8, Math.min(geometry.x, VW - w - 8));
              const y = Math.max(8, Math.min(geometry.y, VH - h - 8));
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

export { ChatWindow, MSG_STATES, WindowFrame };
