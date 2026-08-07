import { CafresoHQChain, CafresoHQClient } from '../claude-client.jsx';
import { SPRITES, Sprite } from '../sprites.jsx';
import { Ico, NAV_ITEMS, useVocab } from './primitives.jsx';
import { deskKit, floorOn, PROP_PLACARD, toolProp } from '../app/floor.jsx';
import { xpLastAttempt, xpLastAttemptText } from '../app/experience.jsx';
import { OFFICE_EFFORT_TIP } from '../app/cast.jsx';
const { useState, useEffect, useLayoutEffect, useRef, useMemo, createContext, useContext } = React;
function Tab({
  value, label, badge, icon, disabled,
  _active = false, _onSelect,
  className = '', style,
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={_active}
      aria-disabled={disabled || undefined}
      tabIndex={_active ? 0 : -1}
      disabled={disabled}
      className={['oc-tab', _active && 'is-active', disabled && 'is-disabled', className].filter(Boolean).join(' ')}
      onClick={() => !disabled && _onSelect && _onSelect()}
      style={style}
    >
      {icon && <span className="oc-tab-icon" aria-hidden="true">{icon}</span>}
      {label && <span>{label}</span>}
      {badge != null && badge !== '' && <span className="oc-tab-badge">{badge}</span>}
    </button>
  );
}

function Rail({ onOpenSettings, onShowCEO, active, setActive, collapsed = false, onToggle, onLaunch, runningViews, onOpenChat, chatOpen = false }) {
  // Brand card doubles as the CEO entry-point — clicking it opens the
  // CEOPanel modal (mini office + arcade + quick actions). Keyboard users
  // get the same behavior via Enter / Space.
  const brandKeyDown = (e) => {
    if (!onShowCEO) return;
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onShowCEO(); }
  };
  return (
    <aside className={`rail${collapsed ? ' collapsed' : ''}`}>
      {onToggle && (
        <button
          className="rail-toggle"
          onClick={onToggle}
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? '»' : '«'}
        </button>
      )}
      <div
        className={'brand' + (onShowCEO ? ' brand-clickable' : '')}
        role={onShowCEO ? 'button' : undefined}
        tabIndex={onShowCEO ? 0 : undefined}
        onClick={onShowCEO || undefined}
        onKeyDown={onShowCEO ? brandKeyDown : undefined}
        title={onShowCEO ? 'Open CEO panel' : undefined}
      >
        <Sprite data={SPRITES.cafresohq} scale={collapsed ? 1 : 2} className="bob" />
        {!collapsed && <div className="title">CAFRESO<br/>HQ</div>}
        {!collapsed && <div className="sub"><span className="dot pixel"></span> CAFRESOHQ · CEO</div>}
      </div>
      <nav>
        {/* Chat sits with the brand, not in NAV_ITEMS, for two reasons.
            NAV_ITEMS drives the 1-8 keyboard shortcuts and the mobile tab
            bar, so inserting into it renumbers every shortcut a boss has
            learned. And more importantly this is the line to the chief of
            staff — it belongs next to their nameplate.

            It exists at all because closing the chat window in desktop mode
            was a ONE-WAY DOOR: measured live, with the window shut there
            were zero visible ways back anywhere in the UI, and `chatWinOpen`
            is persisted, so a single ✕ lost the boss their chief of staff
            across reloads too. */}
        {onOpenChat && (
          <a
            className={'rail-chat' + (chatOpen ? ' active' : '')}
            onClick={onOpenChat}
            title="Talk to CafresoHQ"
            {...pressable(onOpenChat, 'Chat')}
          >
            <span className="rail-ico" aria-hidden="true">💬</span>
            {!collapsed && <span>Chat</span>}
          </a>
        )}
        {NAV_ITEMS.map(([k, label], i) => {
          // In desktop (window) mode the rail is a launcher: clicking opens
          // or raises that app's window instead of switching the full view.
          const running = onLaunch && runningViews && runningViews.indexOf(k) !== -1;
          return (
            <a
              key={k}
              className={(onLaunch ? (running ? 'running' : '') : (active===k?'active':''))}
              onClick={()=> onLaunch ? onLaunch(k) : setActive(k)}
              /* Collapsed, this is the only label the icon has, so it must
                 carry the name AND the key without looking like a count —
                 see the bottom-nav note in app.jsx. */
              /* Past the 9th there is no single-key shortcut, so the label
                 stops offering one — see the note on the keydown handler. */
              title={i >= 9 ? label : collapsed ? `${label} — press ${i + 1}` : `Shortcut: ${i + 1}`}
              aria-current={active===k ? 'page' : undefined}
              {...pressable(()=> onLaunch ? onLaunch(k) : setActive(k), label)}
            >
              <Ico kind={k}/> {!collapsed && label}
            </a>
          );
        })}
      </nav>
      <a
        onClick={onOpenSettings}
        className="door-btn"
        style={{marginTop:8, justifyContent:'center'}}
        title={collapsed ? 'Settings' : undefined}
        {...pressable(()=>onOpenSettings(), 'Settings')}
      >
        <Ico kind="settings"/> {!collapsed && 'SETTINGS'}
      </a>
      <div className="me">
        <div className="avatar">B</div>
        {!collapsed && (
          <div style={{display:'flex',flexDirection:'column'}}>
            <div style={{fontFamily:'Press Start 2P',fontSize:9}}>BOSS</div>
            <div className="tiny">owner</div>
          </div>
        )}
      </div>
    </aside>
  );
}

/* Bottom tab bar — visible only on narrow viewports (CSS @media).
   Chat is the primary mobile entry point; Office, Team, Vault, Projects
   are secondary. Settings lives behind the ⚙ More button. */
function MobileTabBar({ active, setActive, onOpenSettings, onOpenInbox, onOpenStandup, onOpenResearch, onOpenMeeting, onOpenWorkflow, onOpenMemory, onToggleNight, night, inboxCount, missionCount, meetingCount }) {
  const ALL_VIEWS = ['chat','visual','tasks','calendar','memory','vault','team','terminal','projects'];
  const TAB_BOOKMARKS = [
    ['chat',     '💬', 'Chat'],
    ['visual',   '🏢', 'Office'],
    ['team',     '👥', 'Team'],
    ['vault',    '📓', 'Vault'],
    ['projects', '🗂', 'Projects'],
  ];
  const BOOKMARK_IDS = TAB_BOOKMARKS.map(t => t[0]);

  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const touchRef = React.useRef(null);

  // Horizontal swipe on .view-area to cycle through ALL_VIEWS
  React.useEffect(() => {
    const el = document.querySelector('.view-area');
    if (!el || window.innerWidth > 768) return;
    const onStart = (e) => {
      const t = e.touches[0];
      touchRef.current = { x: t.clientX, y: t.clientY, t: Date.now() };
    };
    const onEnd = (e) => {
      if (!touchRef.current) return;
      const t = e.changedTouches[0];
      const dx = t.clientX - touchRef.current.x;
      const dy = t.clientY - touchRef.current.y;
      const dt = Date.now() - touchRef.current.t;
      touchRef.current = null;
      if (Math.abs(dx) < 50 || Math.abs(dy) > Math.abs(dx) * 0.7 || dt > 400) return;
      const idx = ALL_VIEWS.indexOf(active);
      if (idx < 0) return;
      if (dx < 0 && idx < ALL_VIEWS.length - 1) setActive(ALL_VIEWS[idx + 1]);
      if (dx > 0 && idx > 0) setActive(ALL_VIEWS[idx - 1]);
    };
    el.addEventListener('touchstart', onStart, { passive: true });
    el.addEventListener('touchend', onEnd, { passive: true });
    return () => { el.removeEventListener('touchstart', onStart); el.removeEventListener('touchend', onEnd); };
  }, [active, setActive]);

  const toolItems = [
    { icon: '📬', label: 'Inbox',    badge: inboxCount || 0,   action: onOpenInbox },
    { icon: '📁', label: 'Memory',   badge: 0,                  action: onOpenMemory },
    { icon: '🌅', label: 'Stand-up', badge: 0,                  action: onOpenStandup },
    { icon: '🔬', label: 'Research', badge: missionCount || 0,  action: onOpenResearch },
    { icon: '📋', label: 'Meeting',  badge: meetingCount || 0,  action: onOpenMeeting },
    { icon: '⚡', label: 'Workflow', badge: 0,                  action: onOpenWorkflow },
    { icon: night ? '☀' : '☾', label: night ? 'Day' : 'Night', badge: 0, action: onToggleNight },
    { icon: '⚙️', label: 'Settings', badge: 0,                  action: onOpenSettings },
  ];

  const activeIdx = ALL_VIEWS.indexOf(active);

  return (
    <>
      {/* Slide-up tool drawer */}
      {drawerOpen && (
        <div className="mobile-drawer-overlay" onClick={() => setDrawerOpen(false)}>
          <div className="mobile-drawer" onClick={e => e.stopPropagation()}>
            <div className="mobile-drawer-handle" />
            <div className="mobile-drawer-header">
              <div className="mobile-drawer-title">COMMAND CENTER</div>
              <button className="mobile-drawer-close" onClick={() => setDrawerOpen(false)}>
                {'✕'} CLOSE
              </button>
            </div>
            <div className="mobile-drawer-grid">
              {toolItems.map(t => (
                <button key={t.label} className="mobile-drawer-item" onClick={() => { setDrawerOpen(false); if (t.action) t.action(); }}>
                  <span className="mdi-icon">{t.icon}</span>
                  {t.badge > 0 && <span className="mdi-badge">{t.badge}</span>}
                  <span className="mdi-label">{t.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
      <nav className="mobile-tabbar" aria-label="Primary">
        {/* Swipe indicator dots — embedded in tab bar top edge */}
        <div className="mobile-swipe-indicator">
          {ALL_VIEWS.map((v, i) => (
            <span key={v} className={'msi-dot' + (i === activeIdx ? ' active' : '') + (BOOKMARK_IDS.includes(v) ? ' bookmark' : '')} />
          ))}
        </div>
        {TAB_BOOKMARKS.map(([k, icon, label]) => (
          <button
            key={k}
            className={'mtab' + (active === k ? ' active' : '')}
            onClick={() => setActive(k)}
          >
            <span className="mtab-ico" aria-hidden="true">{icon}</span>
            <span className="mtab-label">{label}</span>
          </button>
        ))}
        <button className={'mtab' + (drawerOpen ? ' active' : '')} onClick={() => setDrawerOpen(v => !v)}>
          <span className="mtab-ico" aria-hidden="true">🛠️</span>
          <span className="mtab-label">Tools</span>
        </button>
      </nav>
    </>
  );
}

/* ------------ Office cross-section view ------------ */
const MOOD_ICON = { thinking: '💭', stuck: '!', done: '✓', idle: '·', busy: '⚡', active: '⚡' };

/* Room props say what the occupant may DO, never what they've achieved
   (the papers pile and out-tray carry the earned counts). */
const KIT_TITLE = {
  cabinet:   'can open the filing cabinet',
  bookshelf: 'can use the bookshelf',
  phone:     'can pick up the phone',
};

/* ── Pixel HQ primitives ─────────────────────────────────────────────────
   The floor renders as a GBA-era building cutaway (assets/px/*, generated
   by scripts/gen_pixel_hq.py). Px places one sprite; PxChar is the 7-pose
   character sheet. All art is 1x-scale PNG shown at integer ×2 — no
   fractional scaling, no blur. */
const PX_SIZES = {
  desk_agent: [28, 20], desk_ceo: [36, 19], bookshelf: [20, 20], cabinet: [16, 17],
  plant: [12, 14], cooler: [12, 15], couch: [28, 10], corkboard: [26, 11],
  nightboard: [24, 12], vaultdoor: [26, 18], goldbar: [10, 6], arcade: [18, 18],
  window_day: [18, 12], window_night: [18, 12], clock: [10, 10], mug: [6, 6],
  papers: [10, 7], tray: [12, 6], meetdoor: [16, 17], doors: [24, 16],
  lamp: [10, 18], tree: [20, 17], vending: [14, 14], bush: [14, 6],
  sign_hq: [146, 48], sun: [20, 20], moon: [16, 16], phone: [14, 15],
};

function Px({ n, s = 2, style = {}, className = '', title, onClick, night, ...rest }) {
  // `night` swaps window_day → window_night; anything else ignores it.
  const name = night && n === 'window_day' ? 'window_night' : n;
  const [w, h] = PX_SIZES[n] || [16, 16];
  return (
    <div
      className={`px-sp ${className}`}
      title={title}
      onClick={onClick}
      {...rest}
      style={{
        width: w * s, height: h * s,
        backgroundImage: `url(assets/px/${name}.png)`,
        backgroundSize: '100% 100%',
        ...style,
      }}
    />
  );
}

/* ── Keyboard reach ───────────────────────────────────────────────────────
   Every prop on the floor was a bare <div onClick>: 19 clickable surfaces,
   exactly ONE keyboard-reachable element (an <a href>, and that by
   accident). So the product's primary surface — hire, open a file, read
   the reports, take a delivery, sit with the CEO, answer an approval —
   could not be operated at all without a mouse.

   This turns any prop into a real button for the Tab key and assistive
   tech without moving a pixel: role + tabIndex + Enter/Space, and a focus
   ring drawn as an `outline` (never a border or padding, which would
   reflow the room on focus). stopPropagation matches the click handlers —
   activating the mug must not also open the room behind it. */
function pressable(onActivate, label) {
  return {
    role: 'button',
    tabIndex: 0,
    'aria-label': label,
    onKeyDown: (e) => {
      if (e.key !== 'Enter' && e.key !== ' ' && e.key !== 'Spacebar') return;
      e.preventDefault();       // Space must not scroll the floor
      e.stopPropagation();
      onActivate(e);
    },
  };
}

/* Pose sheet order (gen_pixel_hq.py): back · frontA · frontB · sideA ·
   sideB · stretch · stuck. Working = facing the monitor (back to camera);
   idle = turned toward you. A real state a newcomer reads untaught. */
function PxChar({ color = 'cafresohq', pose = 'front', className = '', style = {}, title, phase = 0 }) {
  const safe = ['cafresohq', 'rose', 'teal', 'sun', 'leaf', 'sky', 'mint', 'blush', 'lavender']
    .indexOf(color) !== -1 ? color : 'cafresohq';
  return (
    <div
      className={`px-char pose-${pose} ${className}`}
      title={title}
      style={{
        backgroundImage: `url(assets/px/char_${safe}.png)`,
        // Negative delay starts the cycle mid-way instead of pausing it.
        ...(phase ? { animationDelay: `${-(phase % 3.6).toFixed(2)}s` } : null),
        ...style,
      }}
    />
  );
}

function chunk2(xs) {
  const out = [];
  for (let i = 0; i < xs.length; i += 2) out.push(xs.slice(i, i + 2));
  return out;
}

/* ── Cross-mount live-state cache ─────────────────────────────────────────
   screens/liveTools/tipRain are deliberately kept OUT of the agents array
   (see their own comments below) so token-rate traffic never triggers
   app-wide re-renders. That locality had a side effect: switching the
   active view away from Office and back fully unmounts OfficeView, wiping
   this state — so a coworker genuinely mid-run rendered as idle on return,
   an §4 honesty violation (the floor claimed nothing was happening while
   real work was in flight). This module-scope cache survives the
   component's mount/unmount (it only resets on an actual page reload,
   which is honest — a fresh reload has no live SSE connections yet
   either). Each entry carries an `_at` timestamp so an entry that's
   ACTUALLY stale (backgrounded well past its own normal lifetime) doesn't
   resurrect on remount looking live. */
const officeLiveCache = { screens: {}, liveTools: {}, tipRain: {} };
const LIVE_CACHE_MAX_AGE = { screens: 65000, liveTools: 46000, tipRain: 4500 };
function freshCacheEntries(bucket) {
  const now = Date.now();
  const maxAge = LIVE_CACHE_MAX_AGE[bucket];
  const src = officeLiveCache[bucket];
  const out = {};
  for (const id in src) {
    if (now - (src[id]._at || 0) <= maxAge) out[id] = src[id];
  }
  return out;
}

function OfficeView({ agents, backendDown = false, onHire, onAgentClick, onCoffee, onInspect, stickies, corkPins = [], onAddSticky, onRemoveSticky, onUnpin, onSitWithCEO, onOpenMemory, onOpenMeeting, onTaskDropOnAgent, tasks = [], onAssignTask, onGoToTasks, onOpenArtifact, maxSlots = 5, ceoBusy = false, attentionCount = 0, onOpenAttention, approvals = [], missions = [], onOpenMissions, meetingActive = false, meetingIds = [], experience = [] }) {

  /* Hierarchy: assistants and transient sub-agents nest visually inside
     their senior's desk rather than getting their own. This keeps the
     office floor uncluttered and shows org structure at a glance. We
     only show standalone desks for SENIOR agents (no reportsTo set) and
     for "free agent" assistants whose senior was dismissed (transferred
     to boss — reportsTo cleared). Transient sub-agents are nested under
     their parentAgentId. Anything we couldn't nest stays visible. */
  const isNested = (a) => !!(a.reportsTo || a.parentAgentId);
  const seniorAgents = agents.filter(a => !isNested(a));
  const subordinatesOf = (seniorId) => agents.filter(a =>
    a.reportsTo === seniorId || a.parentAgentId === seniorId);
  const emptySlots = Math.max(0, maxSlots - seniorAgents.length);
  /* The tower is two units per storey. Vacant units belong in that SAME
     sequence, not in a separate full-width band below it — a leased floor
     and an unleased one are the same architecture, and rendering the
     vacancies as one wide strip made the building change shape halfway
     down. Flowing them through chunk2 also fills the odd slot beside a
     lone coworker, so the facade `filler` block only appears when the
     total unit count is genuinely odd. */
  const units = seniorAgents.map((a, idx) => ({ kind: 'agent', a, idx }))
    .concat(Array.from({ length: emptySlots }, (_, i) => ({ kind: 'vacant', idx: seniorAgents.length + i })));
  const [dropTarget, setDropTarget] = React.useState(null);
  const vocab = useVocab();
  const isMobileOffice = typeof window !== 'undefined' && window.innerWidth <= 768;
  // Inbox tasks = anything sitting in the queue waiting to be delegated.
  // We treat status === 'inbox' OR a task with no assignee as eligible to
  // show in the rail. The drop handler on agent desks moves the task to
  // status:'doing' and sets assignedTo, so it disappears from the rail
  // automatically once delegated.
  // ...but FINISHED work is not waiting for anyone. `!t.assignedTo` catches
  // any unassigned task regardless of status, and the archived end-of-day
  // stand-up is exactly that: `status: 'done'`, `assignedTo: null`. Measured
  // on a populated floor — the strip read "1" waiting and offered to
  // delegate a completed report to Llama or Mika, which would have re-run a
  // finished document as fresh work. A terminal task is never in the queue.
  const inboxTasks = (tasks || []).filter(t =>
    t && t.status !== 'done' && (t.status === 'inbox' || !t.assignedTo));

  /* ── Honest ambient movement ──────────────────────────────────────────
     Walker sprites stroll across the open floor in response to REAL state:
     participants head to the meeting room when a meeting opens, and a truly
     idle agent occasionally visits the water cooler. Purely presentational —
     never mutates agent state. Skipped on mobile + reduced-motion. */
  const ambientOk = !isMobileOffice &&
    !(typeof window !== 'undefined' && window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const meetingIdSet = React.useMemo(() => new Set(meetingActive ? meetingIds : []), [meetingActive, meetingIds.join(',')]);

  // Meeting walkers — fire once on the rising/falling edge of meetingActive.
  const [walkers, setWalkers] = React.useState([]);
  const wasMeetingRef = React.useRef(false);
  React.useEffect(() => {
    if (!ambientOk) { setWalkers([]); wasMeetingRef.current = meetingActive; return; }
    const was = wasMeetingRef.current;
    wasMeetingRef.current = meetingActive;
    if (meetingActive === was) return;
    const parts = (meetingActive ? meetingIds : meetingIds)
      .map(id => agents.find(a => a.id === id)).filter(Boolean);
    if (!parts.length) return;
    const dir = meetingActive ? 'go' : 'return';
    setWalkers(parts.map((a, i) => ({ key: a.id + '-' + dir + '-' + i, color: a.color, dir, delay: i * 1.2 })));
    const t = setTimeout(() => setWalkers([]), 3600 + parts.length * 1200);
    return () => clearTimeout(t);
  }, [meetingActive, ambientOk]);

  /* §4 "done" beat: the stretch is a TRANSITION, not a status — mood stays
     'done' upstream until the agent's next run starts, which used to leave
     the sprite frozen arms-up indefinitely (the `.pop` keyframe is a 0.7s
     one-shot; nothing ever moved the pose off 'stretch'). Play it once on
     the rising edge of mood==='done', same edge-timer shape as trayDrop/
     tipRain below. Clearing on ANY mood change (not just after the timer)
     keeps it interruptible per §4. */
  const [stretching, setStretching] = React.useState({});
  const prevMoodRef = React.useRef({});
  const moodSig = agents.map(a => a.id + ':' + a.mood).join(',');
  React.useEffect(() => {
    const timers = [];
    agents.forEach(a => {
      const prev = prevMoodRef.current[a.id];
      if (a.mood === 'done' && prev !== 'done') {
        setStretching(s => ({ ...s, [a.id]: true }));
        timers.push(setTimeout(() => setStretching(s => {
          if (!s[a.id]) return s;
          const n = { ...s }; delete n[a.id]; return n;
        }), 900));
      } else if (a.mood !== 'done' && prev === 'done') {
        setStretching(s => { if (!s[a.id]) return s; const n = { ...s }; delete n[a.id]; return n; });
      }
      prevMoodRef.current[a.id] = a.mood;
    });
    return () => timers.forEach(clearTimeout);
  }, [moodSig]);

  /* Just-leased beat. A hire is the single biggest state change in the
     product, and the ONLY feedback on the floor was the lobby walk — which
     is ambientOk-gated, so mobile and reduced-motion users watched a room
     appear out of nowhere with no cue that it was theirs. The room itself
     now marks itself newly-leased for ~2.6s, ungated, on the same
     principle as trayDrop: this reports real state, it doesn't decorate.
     The lobby WALK stays gated — that one is genuinely ambient. */
  const [movedIn, setMovedIn] = React.useState(null);
  React.useEffect(() => {
    let clearT;
    const onNewHire = (e) => {
      const id = (e.detail || {}).id;
      if (!id) return;
      setMovedIn(id);
      clearTimeout(clearT);
      clearT = setTimeout(() => setMovedIn(null), 2600);
    };
    const off = floorOn('walkIn', onNewHire);
    return () => { off(); clearTimeout(clearT); };
  }, []);

  // New-hire walk-in — the coworker literally walks onto the floor when
  // hired (app.jsx onHire dispatches 'cafresohq:walkIn'). One-shot, ~2s.
  const [arrival, setArrival] = React.useState(null);
  React.useEffect(() => {
    if (!ambientOk) return;
    let clearT;
    const onWalkIn = (e) => {
      setArrival({ key: 'arr-' + Date.now(), color: (e.detail || {}).color || 'cafresohq' });
      clearTimeout(clearT);
      clearT = setTimeout(() => setArrival(null), 2200);
    };
    const off = floorOn('walkIn', onWalkIn);
    return () => { off(); clearTimeout(clearT); };
  }, [ambientOk]);

  /* Artifact landing (OFFICE_AS_INTERFACE §4: `artifact` → "carries a
     document to the out-tray"). app.jsx fires this once the deliverable is
     genuinely in the cabinet, so the beat can never play for work that
     wasn't actually filed. Keyed by agent id; the desk's tray plays a
     one-shot drop. NOT ambientOk-gated the way the walkers are — this one
     reports a real state change rather than decorating the floor, so a
     reduced-motion user still gets the (CSS-shortened) cue. */
  /* §4 "tool_call (needs approval) → walks to YOUR desk and asks": the
     first pending approval whose coworker is on the floor stands them at
     the boss desk with the ask in a speech bubble. Clicking answers it
     (opens the attention surface). Real state — never ambientOk-gated. */
  const askingApproval = React.useMemo(
    () => (approvals || []).find(p => p && p.agentId && agents.some(a => a.id === p.agentId)) || null,
    [approvals, agents]);
  const askingAgent = askingApproval ? agents.find(a => a.id === askingApproval.agentId) : null;

  /* Night Shift board (§1: scheduled missions → the bulletin board). Only
     hangs on the wall once missions EXIST — an empty board on a fresh HQ
     would be set dressing pretending to be state (the out-tray rule). */
  const nightMissions = (missions || []).filter(m => m && (m.status === 'running' || m.status === 'paused'));
  const nightRunning = nightMissions.filter(m => m.status === 'running').length;

  const [trayDrop, setTrayDrop] = React.useState({});
  React.useEffect(() => {
    const timers = new Map();
    const onArtifact = (e) => {
      const id = (e.detail || {}).agentId;
      if (!id) return;
      setTrayDrop(prev => ({ ...prev, [id]: (prev[id] || 0) + 1 }));
      clearTimeout(timers.get(id));
      timers.set(id, setTimeout(() => {
        setTrayDrop(prev => { const next = { ...prev }; delete next[id]; return next; });
      }, 1800));
    };
    const off = floorOn('artifact', onArtifact);
    return () => { off(); timers.forEach(t => clearTimeout(t)); };
  }, []);

  /* Coffee beat — the mug clears context and kills any in-flight run, and
     until now the only sign at the desk was the glow going out (and none
     at all if they were idle). One-shot steam, ~1.3s. Same class as
     trayDrop: it reports a real state change the boss just caused, so it
     is NOT ambientOk-gated — reduced-motion gets the CSS-shortened cue. */
  const [coffeeSteam, setCoffeeSteam] = React.useState({});
  React.useEffect(() => {
    const timers = new Map();
    const onCoffeeEvt = (e) => {
      const id = (e.detail || {}).agentId;
      if (!id) return;
      setCoffeeSteam(prev => ({ ...prev, [id]: (prev[id] || 0) + 1 }));
      clearTimeout(timers.get(id));
      timers.set(id, setTimeout(() => {
        setCoffeeSteam(prev => { const next = { ...prev }; delete next[id]; return next; });
      }, 1300));
    };
    const off = floorOn('coffee', onCoffeeEvt);
    return () => { off(); timers.forEach(t => clearTimeout(t)); };
  }, []);

  // Idle water-cooler visit — pick one genuinely-idle senior every few minutes.
  const [coolerVisitor, setCoolerVisitor] = React.useState(null);
  React.useEffect(() => {
    if (!ambientOk) return;
    let timer, clearV;
    const schedule = () => {
      timer = setTimeout(() => {
        const idle = seniorAgents.filter(a => a.status === 'idle' && !a.task);
        if (idle.length) {
          const pick = idle[Math.floor((Date.now() / 1000) % idle.length)];
          setCoolerVisitor(pick.id);
          clearV = setTimeout(() => setCoolerVisitor(null), 20000);
        }
        schedule();
      }, 240000 + (Date.now() % 120000));   // 4–6 min, deterministic-ish
    };
    schedule();
    return () => { clearTimeout(timer); clearTimeout(clearV); };
  }, [ambientOk, seniorAgents.length]);
  // Cancel a cooler visit early if that agent stops being idle.
  React.useEffect(() => {
    if (!coolerVisitor) return;
    const a = agents.find(x => x.id === coolerVisitor);
    if (a && (a.status !== 'idle' || a.task)) setCoolerVisitor(null);
  }, [agents, coolerVisitor]);
  const coolerVisitorAgent = coolerVisitor ? agents.find(a => a.id === coolerVisitor) : null;

  /* ── Live-work layer ──────────────────────────────────────────────────
     Desk monitors light up while their agent is REALLY running a tool
     (cafresohq:agentTool events carry agentId since the Open Floor pass).
     'done' lingers ~1.6s so the glow reads; a 45s safety clear covers
     error paths where 'done' never fires. */
  const [liveTools, setLiveToolsState] = React.useState(() => freshCacheEntries('liveTools'));
  const setLiveTools = (updater) => setLiveToolsState(prev => {
    const next = typeof updater === 'function' ? updater(prev) : updater;
    officeLiveCache.liveTools = next;
    return next;
  });
  React.useEffect(() => {
    const timers = new Map();
    const clearLater = (id, ms) => {
      const t = timers.get(id); if (t) clearTimeout(t);
      timers.set(id, setTimeout(() => {
        setLiveTools(prev => { if (!(id in prev)) return prev; const n = { ...prev }; delete n[id]; return n; });
      }, ms));
    };
    const onTool = (e) => {
      const d = e.detail || {};
      if (!d.agentId) return;
      if (d.phase === 'start') {
        // §4: the tool decides the prop — cabinet for files, bookshelf for
        // search, phone for the web; null keeps them at the desk.
        setLiveTools(prev => ({ ...prev, [d.agentId]: { name: d.name, prop: toolProp(d.name), _at: Date.now() } }));
        clearLater(d.agentId, 45000);
      } else if (d.phase === 'done') {
        clearLater(d.agentId, 1600);
      }
    };
    const off = floorOn('tool', onTool);
    return () => { off(); timers.forEach(clearTimeout); };
  }, []);

  /* §4 prop walk — arrival edge. The transit animation is a fixed 0.8s
     regardless of how long the tool actually runs; this flag just flips the
     pose from "walking" to "working at the furniture" once they get there,
     so a long tool call reads as standing at the cabinet, not jogging in
     place for 40 seconds. */
  const [propArrived, setPropArrived] = React.useState({});
  const propSig = Object.keys(liveTools)
    .map(id => id + ':' + ((liveTools[id] || {}).prop || '')).join(',');
  React.useEffect(() => {
    const timers = [];
    Object.keys(liveTools).forEach(id => {
      if ((liveTools[id] || {}).prop && !propArrived[id]) {
        timers.push(setTimeout(
          () => setPropArrived(s => (s[id] ? s : { ...s, [id]: true })), 800));
      }
    });
    // Drop arrivals for anyone no longer at a prop, so the next trip walks.
    setPropArrived(s => {
      let changed = false;
      const n = { ...s };
      for (const id in s) {
        if (!(liveTools[id] || {}).prop) { delete n[id]; changed = true; }
      }
      return changed ? n : s;
    });
    return () => timers.forEach(clearTimeout);
  }, [propSig]);


  /* ── Desk screens — each monitor shows the tail of its agent's REAL output
     stream (cafresohq:agentScreen from the app-level run paths, throttled at
     the source). phase 'stream' scrolls; 'done' freezes the last line ~8s
     then fades. Kept in local state (never on the agents array) so token
     traffic can't trigger app-wide re-renders. */
  const [screens, setScreensState] = React.useState(() => freshCacheEntries('screens'));
  const setScreens = (updater) => setScreensState(prev => {
    const next = typeof updater === 'function' ? updater(prev) : updater;
    officeLiveCache.screens = next;
    return next;
  });
  React.useEffect(() => {
    const timers = new Map();
    const onScreen = (e) => {
      const d = e.detail || {};
      if (!d.agentId) return;
      const terminal = d.phase === 'done' || d.phase === 'error';
      /* A caller closing its monitor has nothing left to show, and the old
         `!d.tail` guard dropped that event on the floor — so the desk kept
         a stale monitor lit until the 60s backstop swept it. A terminal
         event with no tail closes the monitor now. (Found when the meeting
         room started emitting screen events: its turn-end close was a
         silent no-op.) */
      if (!d.tail) {
        if (!terminal) return;
        const t0 = timers.get(d.agentId); if (t0) clearTimeout(t0);
        setScreens(prev => {
          if (!(d.agentId in prev)) return prev;
          const n = { ...prev }; delete n[d.agentId]; return n;
        });
        return;
      }
      setScreens(prev => ({ ...prev, [d.agentId]: { tail: d.tail, phase: d.phase, _at: Date.now() } }));
      const t = timers.get(d.agentId); if (t) clearTimeout(t);
      // Run paths now close their monitor explicitly on failure (phase
      // 'error' — cleared fast, §4 forbids a "working" glow on a dead run);
      // the 60s sweep stays as the backstop for anything that dies silently.
      timers.set(d.agentId, setTimeout(() => {
        setScreens(prev => { if (!(d.agentId in prev)) return prev; const n = { ...prev }; delete n[d.agentId]; return n; });
      }, d.phase === 'done' ? 8000 : d.phase === 'error' ? 2500 : 60000));
    };
    const off = floorOn('screen', onScreen);
    return () => { off(); timers.forEach(clearTimeout); };
  }, []);

  /* The rooftop LIVE lamp and the per-desk screen glow must agree on what
     "live" means. anyLive counted tool calls ONLY, so a coworker visibly
     streaming a reply lit their desk while the roof stayed dark — two
     lights, two definitions. A finished/failed screen lingers on purpose
     (§4 lets 'done' read for 8s) and must NOT keep the roof lit. */
  /* One definition of "live", third pass. This counted only tool calls and
     open streams — both EVENT-driven — so a coworker who was genuinely
     running lit their own desk while the rooftop stayed dark for the whole
     stretch between dispatch and first token. Caught by watching a real
     run: the room read status-busy and the lamp read nothing.
     `agent.status` is the authoritative answer to "is anyone working", so
     it belongs here alongside the events. A finished screen still doesn't
     count — a lingering result must never keep the building claiming work
     is in progress. */
  const anyLive = Object.keys(liveTools).length > 0 ||
    agents.some(a => a && (a.status === 'busy' || a.status === 'active')) ||
    Object.keys(screens).some(id => {
      const s = screens[id];
      return s && s.phase !== 'done' && s.phase !== 'error';
    });

  /* ── Tip Rain — money events land as coins on the earning agent's desk.
     Fed by the app-level tip watcher via cafresohq:moneyEvent. Reduced-motion
     users get a static "+X TOKEN" chip instead (CSS side). */
  const [tipRain, setTipRainState] = React.useState(() => freshCacheEntries('tipRain'));
  const setTipRain = (updater) => setTipRainState(prev => {
    const next = typeof updater === 'function' ? updater(prev) : updater;
    officeLiveCache.tipRain = next;
    return next;
  });
  React.useEffect(() => {
    const timers = new Map();
    const onMoney = (e) => {
      const d = e.detail || {};
      if (!d.agentId || (d.kind !== 'tip' && d.kind !== 'payday' && d.kind !== 'furnish')) return;
      setTipRain(prev => ({ ...prev, [d.agentId]: { amount: d.amount, token: d.token, kind: d.kind, _at: Date.now() } }));
      const t = timers.get(d.agentId); if (t) clearTimeout(t);
      timers.set(d.agentId, setTimeout(() => {
        setTipRain(prev => { if (!(d.agentId in prev)) return prev; const n = { ...prev }; delete n[d.agentId]; return n; });
      }, 4200));
    };
    window.addEventListener('cafresohq:moneyEvent', onMoney);
    return () => { window.removeEventListener('cafresohq:moneyEvent', onMoney); timers.forEach(clearTimeout); };
  }, []);

  /* ── Wall P&L board — agent wallet spend/cap (on-chain policy, one bridge
     call). Only when the Wallet ICP-Service is installed AND we're inside
     the shell that can reach the chain. */
  const walletServiceOn = (() => {
    try {
      if (!(window.hqMoneyOn && window.hqMoneyOn())) return false; // money module off → no P&L board
      const s = CafresoHQClient.getSettings();
      return !!(s.icpServices && s.icpServices.wallet) &&
             !!(CafresoHQChain && CafresoHQChain.isAvailable());
    } catch (_e) { return false; }
  })();
  const [plWallets, setPlWallets] = React.useState(null);
  // Sprint 2: EARNED (paid payouts, + tips/paydays seen live) vs SPENT
  // (lifetime on-chain spendTotals) → NET per agent. Advisory display only —
  // the caps + allowance remain the enforcement.
  const [plTotals, setPlTotals] = React.useState(null); // agentId -> {token, earnedRaw, spentRaw} (BigInt)
  React.useEffect(() => {
    if (!walletServiceOn || isMobileOffice) return;
    let dead = false;
    (async () => {
      try {
        const chain = CafresoHQChain;
        const [ws, totals, payouts] = await Promise.all([
          chain.wallet.list(),
          chain.wallet.totals ? chain.wallet.totals().catch(() => ({})) : {},
          chain.payroll ? chain.payroll.payouts().catch(() => []) : [],
        ]);
        if (dead) return;
        setPlWallets(ws || []);
        const t = {};
        for (const w of ws || []) {
          const tok = w.token || 'ICP';
          let earned = BigInt(0);
          for (const po of payouts || []) {
            if (po.agentId === w.agentId && po.token === tok && po.status === 'paid') earned += BigInt(po.amount);
          }
          t[w.agentId] = { token: tok, earnedRaw: earned, spentRaw: BigInt((totals[w.agentId] && totals[w.agentId][tok]) || 0) };
        }
        setPlTotals(t);
      } catch (_e) { if (!dead) setPlWallets([]); }
    })();
    const onMoney = (e) => {
      const d = e.detail || {};
      if (!d.agentId || !d.amountRaw) return;
      setPlTotals(prev => {
        if (!prev || !prev[d.agentId]) return prev;
        const cur = prev[d.agentId];
        if (d.token !== cur.token) return prev;
        return { ...prev, [d.agentId]: { ...cur, earnedRaw: cur.earnedRaw + BigInt(d.amountRaw) } };
      });
    };
    window.addEventListener('cafresohq:moneyEvent', onMoney);
    return () => { dead = true; window.removeEventListener('cafresohq:moneyEvent', onMoney); };
  }, [walletServiceOn]);
  const PL_DECIMALS = { ICP: 8, ckUSDT: 6, ckUNI: 18, sGLDT: 8, nanas: 8, BANK: 8 };
  const plFmt = (raw, token) => {
    try {
      const dec = PL_DECIMALS[token] != null ? PL_DECIMALS[token] : 8;
      const n = Number(BigInt(raw)) / Math.pow(10, dec);
      return n >= 100 ? n.toFixed(0) : n >= 1 ? n.toFixed(2) : n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
    } catch (_e) { return '0'; }
  };

  /* ── Situation Wall — real ops telemetry as wall furniture ────────────
     Everything here reads data that already exists behind Settings:
       · backendHealth() → container lamp (poll 30s, cheap /health)
       · braveProbe()    → Search Network bars. Runs a REAL Brave search, so
                           it fires ONCE on mount + manual click only.
       · agentsStatus()  → crew dial (installed CLI runtimes)
       · Σ agents.tokens → office fuel bar (same math as TokenHUD)
       · Σ sGLDT wallets → treasury tile (exposed as goldTreasury for the
                           Vault Room to reuse — fetch once, cache 60s) */
  const [wallHealth, setWallHealth] = React.useState(null);   // null checking | true | false
  const [wallSearch, setWallSearch] = React.useState(null);   // null unknown | {ok}
  const [wallCrew, setWallCrew] = React.useState(null);       // {installed, total} | null
  const [goldTreasury, setGoldTreasury] = React.useState(null); // BigInt raw e8s | null
  React.useEffect(() => {
    if (isMobileOffice) return;
    const client = CafresoHQClient;
    if (!client) return;
    let dead = false;
    const checkHealth = async () => {
      try { const ok = await client.backendHealth(); if (!dead) setWallHealth(!!ok); }
      catch (_e) { if (!dead) setWallHealth(false); }
    };
    checkHealth();
    const t = setInterval(() => { if (!document.hidden) checkHealth(); }, 30000);
    (async () => {
      try { const p = await client.braveProbe(); if (!dead) setWallSearch(p); }
      catch (_e) { if (!dead) setWallSearch({ ok: false }); }
    })();
    (async () => {
      try {
        const s = await client.agentsStatus();
        const list = (s && s.agents) || [];
        if (!dead) setWallCrew({ installed: list.filter(x => x.installed).length, total: list.length });
      } catch (_e) {}
    })();
    return () => { dead = true; clearInterval(t); };
  }, [isMobileOffice]);
  React.useEffect(() => {
    if (!walletServiceOn || isMobileOffice || !plWallets || !plWallets.length) return;
    let dead = false;
    (async () => {
      try {
        const chain = CafresoHQChain;
        const per = await Promise.all(plWallets.map(w =>
          chain.wallet.balances(w.agentId, ['sGLDT']).catch(() => ({}))));
        if (dead) return;
        let sum = BigInt(0);
        for (const b of per) { try { sum += BigInt((b && b.sGLDT) || 0); } catch (_e) {} }
        setGoldTreasury(sum);
      } catch (_e) {}
    })();
    return () => { dead = true; };
  }, [walletServiceOn, isMobileOffice, plWallets]);
  const officeTokens = agents.reduce((s, a) => s + (a.tokens || 0), 0);
  /* Deliveries that really reached the cabinet — see the wall row below. */
  const filedCount = (tasks || []).filter(t => t && t.artifactPath).length;
  const busyCount = agents.filter(a => a.status === 'busy').length;

  /* ── Vault Room data — BANK prestige balance (read-only, feature-detected:
     older shells don't know chain:bank:balance and the case just stays
     empty). Gold bars reuse goldTreasury from the Situation Wall fetch. */
  const [bankBalance, setBankBalance] = React.useState(null);   // BigInt | null
  React.useEffect(() => {
    if (!walletServiceOn || isMobileOffice) return;
    let dead = false;
    (async () => {
      try {
        const chain = CafresoHQChain;
        if (!chain || !chain.bank) return;
        const raw = await chain.bank.balance();
        if (!dead && raw !== null) setBankBalance(raw);
      } catch (_e) { /* old shell / no BANK — case stays empty */ }
    })();
    return () => { dead = true; };
  }, [walletServiceOn, isMobileOffice]);
  // Prestige tier from real BANK holdings (display-only, never gameable).
  const bankTier = bankBalance === null ? null
    : bankBalance >= BigInt(100e8) ? 'gold'
    : bankBalance >= BigInt(10e8) ? 'silver'
    : bankBalance > BigInt(0) ? 'bronze' : null;
  // 1-8 gold bars: log-ish scale so early treasuries still show something.
  const goldBars = goldTreasury === null ? 0
    : goldTreasury <= BigInt(0) ? 0
    : Math.min(8, 1 + Math.floor(Math.log10(Number(goldTreasury) / 1e8 + 1) * 3));

  return (
    <div className="office pxhq-root">
      {/* Task rail — slim strip of draggable cards above the rooms.
          - Desktop: drag a card onto a senior agent's desk to delegate.
          - Mobile: tap the assignee dropdown inside the card; drag-and-drop
            is unreliable on touch so the picker is the primary affordance.
          The header `tag` already explains the gesture; this rail provides
          the actual drag source the office was designed around. */}
      <div className="office-task-rail" aria-label="Inbox tasks">
        <div className="otr-head">
          <span className="otr-title">📋 Inbox</span>
          {/* One empty-state line, and a true one.

              There were three: this hint, an `.otr-empty` body reading
              "All clear. Drop something here from the Tasks tab to
              delegate.", and the `0` count beside them — the same nothing,
              said three ways, holding a full row of the floor open on the
              one surface where vertical space IS the product.

              The body line was also FALSE. There is no drop handler on this
              rail; the only onDrop in the office is on an agent's desk. It
              told the boss to perform a gesture that does nothing. Gone —
              the hint below already names the real next action. */}
          <span className="otr-hint">
            {inboxTasks.length === 0
              ? 'No tasks waiting — add one in the Tasks tab.'
              : (isMobileOffice
                  ? 'tap the picker to assign'
                  : 'drag a card onto an agent\'s desk')}
          </span>
          <span className="otr-count">{inboxTasks.length}</span>
          {attentionCount > 0 && onOpenAttention && (
            <button className="otr-attn" onClick={onOpenAttention}
              title="Open the Team inbox — items that need you">
              ⚠ {attentionCount} need{attentionCount === 1 ? 's' : ''} you →
            </button>
          )}
          {onGoToTasks && (
            <button className="otr-more" onClick={onGoToTasks} title="Open the full task board">
              Board →
            </button>
          )}
        </div>
        {inboxTasks.length === 0 ? null : (
          <div className="otr-scroll">
            {inboxTasks.map(t => (
              <div key={t.id}
                   className={`otr-card pri-${t.priority || 'med'}`}
                   draggable
                   onDragStart={(e) => {
                     e.dataTransfer.setData('task', t.id);
                     e.dataTransfer.effectAllowed = 'move';
                   }}
                   title="Drag to a coworker's desk to delegate">
                <div className="otr-card-row">
                  <span className={`otr-pri pri-${t.priority || 'med'}`}>{t.priority || 'med'}</span>
                  <div className="otr-card-title">{t.title}</div>
                </div>
                {t.detail && <div className="otr-card-detail">{t.detail}</div>}
                {/* §5, derived: the card says who already tried and snagged,
                    so the obvious next move isn't handing it straight back
                    to the coworker it just defeated. A fact, not advice. */}
                {(() => {
                  const line = xpLastAttemptText(xpLastAttempt(experience, t.id, agents));
                  return line ? <div className="otr-card-lastry">⚠ {line}</div> : null;
                })()}
                <div className="otr-card-foot">
                  <span className="otr-grip" aria-hidden="true">⋮⋮</span>
                  {onAssignTask ? (
                    <select className="otr-assign"
                            value={t.assignedTo || ''}
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => {
                              const id = e.target.value;
                              if (!id) return;
                              const a = agents.find(x => x.id === id);
                              if (a && onTaskDropOnAgent) onTaskDropOnAgent(t.id, a);
                              else if (onAssignTask) onAssignTask(t.id, id);
                            }}
                            title="Assign to a coworker">
                      <option value="">Assign to…</option>
                      {agents.map(a => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                  ) : (
                    <span className="otr-unassigned">↕ drag to a desk</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      {/* Mobile: horizontal scrollable agent avatar strip */}
      {isMobileOffice && (
        <div className="mobile-agent-strip">
          <div className="mas-scroll">
            <div className="mas-item" onClick={onSitWithCEO} title="CafresoHQ CEO">
              <div className="sprite-wrap"><Sprite data="ceo" scale={1.5}/></div>
              <span className="mas-name">CafresoHQ</span>
            </div>
            {agents.map(a => (
              <div key={a.id} className="mas-item" onClick={() => onInspect && onInspect(a)} title={a.name}>
                <div className="sprite-wrap" style={{ position: 'relative' }}>
                  <Sprite data={a.sprite || a.name} scale={1.5}/>
                  <span className="mas-status" style={{
                    background: a.status === 'busy' || a.status === 'active' ? 'var(--live)' : 'var(--ink-3)',
                    position: 'absolute', bottom: 0, right: 0,
                  }}/>
                </div>
                <span className="mas-name">{a.name}</span>
                <span style={{ fontSize: 10 }}>{MOOD_ICON[a.mood] || ''}</span>
              </div>
            ))}
            <div className="mas-plus" onClick={onHire} title="Hire a coworker">+</div>
          </div>
        </div>
      )}
      {/* ════════ PIXEL HQ — the CafresoHQ building, GBA-era cutaway ════════
          Sky → skyline → building (rooftop sign / CEO penthouse / agent
          floors / vacancies / vault / lobby) → street. Every live surface
          from the old floor survives with identical wiring; only the paint
          changed. Day/night pairs (sun+moon, window day+night) both render
          and body.night picks one in CSS. */}
      <div className="pxhq">
        <div className="px-sky" aria-hidden="true" />
        <div className="px-stars" aria-hidden="true" />
        <Px n="sun" s={3} className="px-sun" />
        <Px n="moon" s={3} className="px-moon" />
        <div className="px-cloud c1" aria-hidden="true" />
        <div className="px-cloud c2" aria-hidden="true" />
        <div className="px-skyline far" aria-hidden="true" />
        <div className="px-skyline near" aria-hidden="true" />
        {/* Nearest parallax layer — an out-of-focus branch framing the tower. */}
        <div className="px-canopy left" aria-hidden="true" />
        <div className="px-canopy right" aria-hidden="true" />

        {/* HUD — Situation Wall + Agent P&L as game menu boxes. Same live
            data and gating as the old wall furniture. */}
        {!isMobileOffice && walletServiceOn && plWallets && plWallets.length > 0 && (
          <div className="px-hud left pl-frame" title="Your team's books — ▲ earned (tips + payroll) · ▼ spent (on-chain metering) · net">
            <div className="pl-title">◈ AGENT P&L</div>
            {plWallets.slice(0, 3).map(w => {
              const who = agents.find(x => x.id === w.agentId);
              const name = (who ? who.name : w.agentId).slice(0, 8);
              const t = plTotals && plTotals[w.agentId];
              if (!t) {
                return (
                  <div key={w.agentId} className="pl-row">
                    {name} {plFmt(w.windowSpent, w.token)}/{plFmt(w.spendCap, w.token)} {w.token}
                  </div>
                );
              }
              const net = t.earnedRaw - t.spentRaw;
              return (
                <div key={w.agentId} className="pl-row">
                  {name} ▲{plFmt(t.earnedRaw, t.token)} ▼{plFmt(t.spentRaw, t.token)} ={net < BigInt(0) ? '-' : ''}{plFmt(net < BigInt(0) ? -net : net, t.token)} {t.token}
                </div>
              );
            })}
          </div>
        )}
        {/* The Situation Wall is the business's instrument panel — is the
            container up, is search reachable, how many are working, what's
            in the treasury. It was `!isMobileOffice`-gated alongside the
            clouds and the dog, which put a phone in the position of not
            being able to tell a healthy office from a dead one. It renders
            everywhere now; CSS lays it out as a strip on narrow screens
            instead of a floating box. */}
        <div className="px-hud right sit-wall" title="Situation Wall — live office telemetry">
            <div className="sw-title">◉ SITUATION</div>
            {/* `backendDown` is the app-level probe and it wins when true.
                This row polls on its own 30s clock, so during a real outage
                it went on saying "Container healthy" while the topbar chip
                had already flipped to OFFLINE — the boss reading both saw
                the office contradict itself about whether it was reachable.
                The local poll still drives the healthy/checking states; it
                just can no longer out-vote a known outage. */}
            <div className="sw-row" title={backendDown ? 'Container unreachable' : wallHealth === null ? 'Checking container…' : wallHealth ? 'Container healthy' : 'Container unreachable'}>
              <span className={`sw-lamp ${backendDown ? 'red' : wallHealth === null ? 'amber' : wallHealth ? 'green' : 'red'}`}/> HQ
            </div>
            {wallSearch !== null && (
              <div className="sw-row" title={`Search network: ${wallSearch.ok ? (wallSearch.detail || 'up') : 'unavailable'} — click to re-check`}
                   style={{cursor:'pointer'}}
                   onClick={async (e) => {
                     e.stopPropagation();
                     setWallSearch(null);
                     try { setWallSearch(await CafresoHQClient.braveProbe()); }
                     catch (_e) { setWallSearch({ ok: false }); }
                   }}
                   {...pressable(async () => {
                     setWallSearch(null);
                     try { setWallSearch(await CafresoHQClient.braveProbe()); }
                     catch (_e) { setWallSearch({ ok: false }); }
                   }, `Search network ${wallSearch.ok ? 'is up' : 'is unavailable'} — check again`)}>
                <span className={`sw-bars ${wallSearch.ok ? 'up' : 'down'}`} aria-hidden="true"><i/><i/><i/></span> SEARCH
              </div>
            )}
            {wallCrew && wallCrew.total > 0 && (
              <div className="sw-row" title={`${wallCrew.installed}/${wallCrew.total} agent runtimes installed · ${busyCount} working now`}>
                ⚒ {wallCrew.installed}/{wallCrew.total}{busyCount > 0 ? ` · ${busyCount} busy` : ''}
              </div>
            )}
            {/* What the office has actually SHIPPED. The wall reported
                infrastructure — search reachable, runtimes installed, work
                done — and nothing about the business. A boss glancing at
                their own control room could not see whether anything had
                come out the other end.

                Counted from `task.artifactPath`, which is set only when a
                file really landed in the cabinet (fileDelivery returns the
                path or null), so this cannot claim a delivery that isn't
                on disk. Hidden at zero rather than showing `📦 0`: a fresh
                office has shipped nothing, and saying so on the wall is
                noise, not news. */}
            {/* It counts TASKS carrying an artifactPath — the office's
                record of what its team produced, NOT an inventory of the
                cabinet. Those diverge: deleting a task orphans its file,
                which stays on disk. Measured on a lived-in floor — six
                notes in `Deliveries/`, three surviving task records, and
                this row (written in an earlier pass) claimed "3
                deliverables filed to the cabinet". Under-claiming, but
                still a claim about the wrong thing. The Vault view is the
                inventory; this row is the scoreboard. */}
            {filedCount > 0 && (
              <div className="sw-row" title={`${filedCount} deliver${filedCount === 1 ? 'y' : 'ies'} your team filed · open the Vault to browse the cabinet itself`}>
                📦 {filedCount}
              </div>
            )}
            {officeTokens > 0 && (
              /* §6 names the floor explicitly: never "tokens" here. Same
                 number, office words — and no invented unit ("words" would
                 overstate it), just what the figure means. */
              <div className="sw-row" title={OFFICE_EFFORT_TIP}>
                {/* Was a FUEL bar filling toward a hardcoded 1,000,000.
                    Nothing sets that ceiling and nothing enforces it, so
                    the gauge read "4% used" of a tank that does not exist —
                    and "FUEL" implies depletion on top of it. Its
                    neighbours on this wall all show a real quantity; now
                    this one does too. */}
                ⚡ {officeTokens >= 1000 ? (officeTokens/1000).toFixed(1) + 'K' : officeTokens}
              </div>
            )}
            {goldTreasury !== null && goldTreasury > BigInt(0) && (
              <div className="sw-row" title={`Office treasury — ${plFmt(goldTreasury, 'sGLDT')} sGLDT across every coworker's wallet`}>
                ◈ {plFmt(goldTreasury, 'sGLDT')} GOLD
              </div>
            )}
        </div>

        <div className="px-scene">
          <div className="px-building">
            {/* Rooftop — the logo sign. The lamp beside it is the honest
                LIVE surface: lit only while an agent is really working. */}
            <div className="px-rooftop">
              <div className="px-antenna" aria-hidden="true" />
              <div className="px-tank" aria-hidden="true" />
              <Px n="sign_hq" s={2} className="px-sign" />
              {anyLive && (
                <span className="px-livelamp" title="Someone is working right now">
                  ● {vocab.live}
                </span>
              )}
            </div>

            {/* CEO penthouse */}
            <div className="px-floor is-ceo">
              <div className="px-room ceo">
                <div className="px-plate">
                  <span>{vocab.corner} · CAFRESOHQ</span>
                  <span className="pip" />
                </div>
                <div className="px-int">
                  <Px n="window_day" className="px-win d" style={{ left: '8%', top: 8 }} />
                  <Px n="window_night" className="px-win n" style={{ left: '8%', top: 8 }} />
                  <Px n="window_day" className="px-win d" style={{ right: '30%', top: 8 }} />
                  <Px n="window_night" className="px-win n" style={{ right: '30%', top: 8 }} />
                  <Px n="clock" className="px-clock" title="Wall clock" style={{ left: '25%', top: 4 }} />

                  {/* Bulletin corkboard — pinned memory & receipts (live). */}
                  <div className="px-cork" title="Bulletin board — pinned memory & receipts">
                    {corkPins.length === 0 && <div className="px-cork-empty">📌 pin memory here</div>}
                    {corkPins.slice(0, 4).map(p => (
                      <div key={p.id} className={`px-pin kind-${p.kind}`} title={p.text}>
                        <span className="px-pin-text">{p.text}</span>
                        <button className="px-pin-x" onClick={(e)=>{ e.stopPropagation(); onUnpin && onUnpin(p.id); }}>✕</button>
                      </div>
                    ))}
                    {corkPins.length > 4 && <div className="px-pin more">+{corkPins.length - 4}</div>}
                  </div>

                  {/* Night Shift board (§1 bulletin board) — only once missions exist. */}
                  {nightMissions.length > 0 && (
                    <div className={'px-nsb' + (nightRunning ? ' is-live' : '')}
                         title={nightRunning
                           ? `Night Shift — ${nightRunning} mission${nightRunning === 1 ? '' : 's'} running right now · click to open the board`
                           : `Night Shift — ${nightMissions.length} paused · click to open the board`}
                         onClick={(e)=>{ e.stopPropagation(); onOpenMissions && onOpenMissions(); }}
                         {...pressable(()=>onOpenMissions && onOpenMissions(), 'Open the night shift board')}>
                      <div className="px-nsb-title">🌙 NIGHT SHIFT</div>
                      <div className="px-nsb-line">
                        {nightRunning ? `${nightRunning} on shift` : `${nightMissions.length} paused`}
                      </div>
                      <div className="px-nsb-topic">{String(nightMissions[0].topic || '').slice(0, 20)}</div>
                    </div>
                  )}

                  {/* Sticky notes — pinned context. */}
                  <div className="px-stickies">
                    {stickies.slice(0, 3).map(s => (
                      <div key={s.id} className="px-sticky" title="Pinned context">
                        <span className="px-sticky-x" onClick={(e)=>{e.stopPropagation(); onRemoveSticky(s.id);}}
                            {...pressable(()=>onRemoveSticky(s.id), 'Remove this note')}>✕</span>
                        {s.text}
                      </div>
                    ))}
                    <div className="px-sticky add" onClick={(e)=>{ e.stopPropagation(); onAddSticky(); }}
                         {...pressable(()=>onAddSticky(), 'Pin a new note to the CEO desk')}>+ NOTE</div>
                  </div>

                  <Px n="bookshelf" className="px-deco" style={{ left: '2%', bottom: 14 }} />
                  <Px n="cabinet" className="px-cab clickable" title="Browse CafresoHQ's memory"
                      onClick={(e)=>{ e.stopPropagation(); onOpenMemory(); }}
                      {...pressable(()=>onOpenMemory(), 'Open the memory cabinet')}
                      style={{ left: '14%', bottom: 12 }} />
                  <div className="px-label" style={{ left: '13%', bottom: 2 }}>MEMORY</div>

                  <Px n="couch" className="px-couch clickable" title="Sit down with CafresoHQ — 1:1"
                      onClick={(e)=>{ e.stopPropagation(); onSitWithCEO(); }}
                      {...pressable(()=>onSitWithCEO(), 'Sit down with CafresoHQ for a one-to-one')}
                      style={{ left: '27%', bottom: 8 }} />
                  <div className="px-label" style={{ left: '29%', bottom: 2 }}>1:1 SOFA</div>

                  <a className="px-arcadelink" href="https://ai.cafreso.com/workspaces"
                     title="ARCADE · Boot up Cafreso Workspaces"
                     aria-label="Arcade — boot up Cafreso Workspaces"
                     onClick={(e)=>e.stopPropagation()}>
                    <Px n="arcade" className="px-arcade" style={{}} />
                  </a>

                  <div className="px-deskset ceo">
                    {ceoBusy ? <div className="px-bubble">replying to you…</div> : null}
                    <PxChar color="cafresohq" pose={ceoBusy ? 'back' : 'front'}
                            className={ceoBusy ? '' : 'idle-anim'} title="CafresoHQ · CEO" />
                    <Px n="desk_ceo" className="px-desk" />
                  </div>

                  {askingAgent && (
                    <div className="px-asking"
                         title={`${askingAgent.name} is waiting for your go-ahead — click to answer`}
                         onClick={(e) => { e.stopPropagation(); if (onOpenAttention) onOpenAttention(); }}
                         {...pressable(()=>onOpenAttention && onOpenAttention(), 'Answer the request waiting at your desk')}>
                      <div className="px-bubble ask">
                        {askingAgent.name} asks: {String(askingApproval.title || 'may I?').slice(0, 40)}
                      </div>
                      <PxChar color={askingAgent.color} pose="front" className="idle-anim" />
                      <span className="px-alert" aria-hidden="true">!</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Agent floors — two rooms per storey. */}
            {chunk2(units).map((pair, ri) => (
              <div className="px-floor" key={'f' + ri}>
                {pair.map((u, ci) => {
                  if (u.kind === 'vacant') return (
                    <div className="px-room vacant" key={'v' + u.idx}
                         onClick={onHire} title={vocab.hireTitle}
                         {...pressable(()=>onHire(), `Unit ${u.idx + 1} is vacant — ${vocab.hireTitle}`)}>
                      <div className="px-plate">
                        <span>UNIT {u.idx + 1} · {vocab.vacant}</span>
                        <span className="pip" />
                      </div>
                      <div className="px-int vacant">
                        <Px n="window_day" className="px-win d" style={{ left: 10, top: 8 }} />
                        <Px n="window_night" className="px-win n" style={{ left: 10, top: 8 }} />
                        <span className="px-vacant-plus">+ {vocab.hire}</span>
                      </div>
                    </div>
                  );
                  const a = u.a;
                  const i = u.idx;
                  const subs = subordinatesOf(a.id);
                  const awayMeeting = ambientOk && meetingIdSet.has(a.id);
                  const awayCooler = ambientOk && coolerVisitor === a.id;
                  const liveTool = liveTools[a.id];
                  const awayAsking = (approvals || []).some(p => p && p.agentId === a.id);
                  const propVisit = !awayAsking && !awayMeeting && !awayCooler &&
                    !!(liveTool && liveTool.prop);
                  // §4: a prop visit keeps them in the room — they WALK to the
                  // furniture. Only meeting/cooler/asking take them off the floor,
                  // and only those get a placard standing in for a missing body.
                  const away = awayMeeting || awayCooler || awayAsking;
                  const screen = screens[a.id];
                  const paperCount = Math.min((a.journal || []).length, 5);
                  const myArtifacts = (tasks || []).filter(t => t.assignedTo === a.id && t.artifactPath);
                  const trayCount = myArtifacts.length;
                  const latestArtifact = trayCount ? myArtifacts[myArtifacts.length - 1].artifactPath : null;
                  const busy = a.status === 'busy' || a.status === 'active';
                  const pose = stretching[a.id] ? 'stretch'
                    : a.mood === 'stuck' ? 'stuck'
                    : busy ? 'back' : 'front';
                  return (
                    <div key={a.id}
                         className={`px-room status-${a.status || 'idle'}${dropTarget === a.id ? ' drop-target' : ''}${a.elevated ? ' elevated' : ''}${liveTool ? ' tool-live' : ''}${away ? ' is-away' : ''}${movedIn === a.id ? ' just-leased' : ''}`}
                         onClick={() => onInspect(a)}
                         role="group"
                         aria-label={`${a.name}, ${a.role} — ${a.status || 'idle'}${a.task ? ', ' + a.task : ''}`}
                         style={{ cursor: 'pointer' }}
                         onDragOver={e=>{e.preventDefault(); setDropTarget(a.id);}}
                         onDragLeave={()=>setDropTarget(null)}
                         onDrop={e=>{
                           const taskId = e.dataTransfer.getData('task');
                           setDropTarget(null);
                           if (taskId && onTaskDropOnAgent) onTaskDropOnAgent(taskId, a);
                         }}>
                      <div className="px-plate">
                        {/* The plate used to print only the role's LAST word,
                            which turned "Coding Agent" into "AGENT" and (before
                            the front desk stopped saying it) "Local Model · your
                            hardware" into "HARDWARE". Show the real role and let
                            the existing ellipsis handle a long one — truncation
                            is honest, word-picking guesses. */}
                        <span title={`${a.name} · ${a.role} — open their file`}
                              {...pressable(()=>onInspect(a), `${a.name}, ${a.role} — open their file`)}>{a.elevated ? '🛡 ' : ''}{a.name.toUpperCase()} · {String(a.role || '').toUpperCase()}</span>
                        {/* The word carries the beat where the animation
                            can't — a reduced-motion or mobile boss still
                            sees WHICH unit just became theirs. */}
                        {movedIn === a.id && <span className="px-leased">MOVED IN</span>}
                        {subs.length > 0 && (
                          <span className="px-subct" title={`${subs.length} subordinate${subs.length === 1 ? '' : 's'}`}>
                            +{subs.length}
                          </span>
                        )}
                        <span className={`pip ${a.status}`} />
                      </div>
                      <div className="px-int">
                        <Px n="window_day" className="px-win d" style={{ left: 10, top: 8 }} />
                        <Px n="window_night" className="px-win n" style={{ left: 10, top: 8 }} />
                        {deskKit(a.tools).map((prop, ki) => (
                          <Px key={prop} n={prop} className="px-deco"
                              title={KIT_TITLE[prop]}
                              style={{ right: 8 + ki * 26, bottom: 14 }} />
                        ))}
                        <Px n="plant" className="px-plant" style={{ left: 8, bottom: 10 }} />

                        <div className="px-deskset">
                          {away
                            ? <div className="px-placard">
                                {awayMeeting ? 'in the meeting room'
                                  : awayCooler ? 'stretching legs'
                                  : 'at your desk, asking'}
                              </div>
                            : (a.task && !propVisit ? <div className="px-bubble">{a.task}</div> : null)}
                          {!away && !propVisit && (
                            <div className="px-charwrap">
                              <PxChar color={a.color} pose={pose}
                                      className={pose === 'front' ? 'idle-anim' : pose === 'stretch' ? 'pop' : ''}
                                      phase={i * 0.83} title={a.name} />
                              <div className={`px-mood ${a.mood || 'idle'}`} title={a.mood || 'idle'}>{MOOD_ICON[a.mood || 'idle']}</div>
                            </div>
                          )}
                          <Px n="desk_agent" className="px-desk" />
                          {(screen || liveTool) && !away && <span className="px-glow" aria-hidden="true" />}
                          <Px n="mug" className={'px-mug clickable' + (coffeeSteam[a.id] ? ' is-fresh' : '')}
                              title={`Send ${a.name} for coffee — stops anything running and clears their desk`}
                              onClick={(e)=>{e.stopPropagation(); onCoffee(a);}}
                              {...pressable(()=>onCoffee(a), `Send ${a.name} for coffee — stops anything running and clears their desk`)} />
                          {coffeeSteam[a.id] ? <span className="px-steam" aria-hidden="true" /> : null}
                          {/* The pile grows with the real filed-report count
                              (capped at 5 sheets so a busy desk stays legible)
                              — this counter was already computed and thrown
                              away, rendering one sheet for 1 report or 30. */}
                          {/* "filed reports" was an over-claim, and the desk
                              contradicted itself out loud: this pile read
                              "5 filed reports" while the out-tray beside it
                              read "2 deliveries filed". Measured — Llama's
                              journal held 5 entries, of which 2 were tasks
                              and 3 were chat replies.

                              §5 already settled this for jobs: "a chat reply
                              or a DM is not a job, same as it is not an
                              artifact", which is why `agent.tasksDone` left
                              the cards. The journal is a legitimate work LOG
                              and chat belongs in it — the count was never
                              wrong, the WORD was. Only the out-tray may say
                              "filed", because only it counts files that
                              exist. */}
                          {paperCount > 0 && (
                            <div className="px-paperstack clickable"
                                 title={`${(a.journal || []).length} note${(a.journal || []).length === 1 ? '' : 's'} in ${a.name}'s work log — click to read`}
                                 onClick={(e)=>{ e.stopPropagation(); onInspect(a); }}
                                 {...pressable(()=>onInspect(a), `${a.name}'s work log, ${(a.journal || []).length} notes — open`)}>
                              {Array.from({ length: paperCount }).map((_, pi) => (
                                <Px key={pi} n="papers"
                                    style={{ position: 'absolute', left: (pi % 2) * 2, bottom: pi * 3 }} />
                              ))}
                            </div>
                          )}
                          {trayCount > 0 && (
                            <Px n="tray" className={'px-tray clickable' + (trayDrop[a.id] ? ' is-landing' : '')}
                                /* Says whose. The screen-reader label below
                                   already named the coworker; the hover text
                                   didn't, so the two diverged by accident and
                                   the mouse got the worse sentence. On a floor
                                   of several desks, "whose out-tray" is the
                                   whole point of the tray being ON a desk. */
                                title={`${trayCount} deliver${trayCount === 1 ? 'y' : 'ies'} filed by ${a.name} — click to open the latest`}
                                onClick={(e)=>{ e.stopPropagation();
                                  if (latestArtifact && onOpenArtifact) onOpenArtifact(latestArtifact); }}
                                {...pressable(()=>{ if (latestArtifact && onOpenArtifact) onOpenArtifact(latestArtifact); },
                                  `${trayCount} deliveries filed by ${a.name} — open the latest`)} />
                          )}
                        </div>

                        {/* §4 "tool_call → walks to the relevant prop". They
                            stay in the room; the furniture is a real
                            destination now that deskKit put it there. */}
                        {propVisit && (
                          <div className={'px-propvisit is-' + liveTool.prop}
                               title={`${a.name} is ${PROP_PLACARD[liveTool.prop]}`}>
                            <PxChar color={a.color}
                                    pose={propArrived[a.id] ? 'back' : 'walk'}
                                    className={propArrived[a.id] ? 'idle-anim' : ''} />
                          </div>
                        )}
                        {screen && !away && (
                          <div className={`px-screen ${screen.phase === 'done' ? 'is-done' : screen.phase === 'error' ? 'is-error' : 'is-live'}`} aria-hidden="true">
                            {screen.tail}
                          </div>
                        )}
                        {liveTool && !away && (
                          <div className="px-toolchip" aria-hidden="true">
                            ⚙ {String(liveTool.name || '').replace(/_/g, ' ').toLowerCase()}
                          </div>
                        )}
                        {tipRain[a.id] && (
                          <div className="px-tiprain" aria-hidden="true">
                            {Array.from({ length: 6 }, (_, ci2) => (
                              <span key={ci2} className="px-coin" style={{ left: `${10 + ci2 * 15}%`, animationDelay: `${ci2 * 0.18}s` }} />
                            ))}
                            <div className="px-tipamount">
                              {tipRain[a.id].kind === 'payday' ? '💰 PAYDAY ' : ''}+{tipRain[a.id].amount} {tipRain[a.id].token}
                            </div>
                          </div>
                        )}
                        {subs.length > 0 && (
                          <div className="px-subs">
                            {subs.map((s) => (
                              <div key={s.id}
                                   className={`px-sub ${s.transient ? 'transient' : 'assistant'}`}
                                   onClick={(e)=>{ e.stopPropagation(); onInspect(s); }}
                                   {...pressable(()=>onInspect(s), `${s.name}, ${s.role} — open their file`)}
                                   title={`${s.name} · ${s.role}${s.transient ? ' (transient sub)' : ' (assistant)'}${s.task ? ' · ' + s.task : ''}`}>
                                <PxChar color={s.color}
                                        pose={s.status === 'busy' || s.status === 'active' ? 'back' : 'front'}
                                        className={(s.status === 'busy' || s.status === 'active') ? '' : 'idle-anim'} />
                                <span className="px-sub-name">{s.name}<span className={`pip ${s.status || 'idle'}`}/></span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
                {pair.length === 1 && <div className="px-room filler" aria-hidden="true" />}
              </div>
            ))}

            {/* Vault — real on-chain balances, display only (unchanged gating). */}
            {!isMobileOffice && walletServiceOn && (goldTreasury !== null || bankBalance !== null) && (
              <div className="px-floor is-vault" title="Vault Room — real balances, display only">
                <div className="px-room vault">
                  <div className="px-plate"><span>VAULT · TREASURY</span><span className="pip idle" /></div>
                  <div className="px-int vault">
                    <Px n="vaultdoor" className="px-vaultdoor" style={{ left: 12, bottom: 8 }} />
                    {goldTreasury !== null && (
                      <div className="px-goldstack" title={`${plFmt(goldTreasury, 'sGLDT')} sGLDT across every coworker's wallet`}>
                        {Array.from({ length: goldBars }).map((_, gi) => (
                          <Px key={gi} n="goldbar" style={{ position: 'absolute', left: (gi % 4) * 16, bottom: Math.floor(gi / 4) * 9 }} />
                        ))}
                        <div className="px-goldlabel">{plFmt(goldTreasury, 'sGLDT')} sGLDT</div>
                      </div>
                    )}
                    {bankBalance !== null && (
                      <div className={`px-bankcase ${bankTier || 'empty'}`}
                           title={`BANK — Banking Brave · ${plFmt(bankBalance, 'BANK')} held${bankTier ? ` · ${bankTier} tier` : ''}`}>
                        <div className="px-bankcoin">◈</div>
                        <div className="px-banklabel">{plFmt(bankBalance, 'BANK')} BANK</div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Lobby — doors, meeting room, water cooler; ambient walkers
                commute across this floor (same gating as before). */}
            <div className="px-lobby">
              <div className="px-awning" aria-hidden="true" />
              <Px n="cooler" className="px-lobbycooler" title="Water cooler" style={{ left: 18, bottom: 10 }} />
              <Px n="doors" className="px-doors" />
              {/* The label below was '…— start a stand-up'. The office
                  banner was corrected for exactly this (the door seats the
                  team in the MEETING ROOM; the stand-up is a separate modal
                  behind 🌅 STAND-UP / `u`) — but the fix landed on the
                  banner and never on this control's own label, so the wrong
                  sentence kept shipping to screen readers, the one audience
                  that cannot see the banner that replaced it. Same shape as
                  fixing a toast and leaving the state it described. */}
              <Px n="meetdoor" className="px-meetdoor clickable" title="Open meeting room"
                  onClick={(e)=>{e.stopPropagation(); onOpenMeeting();}}
                  {...pressable(()=>onOpenMeeting(), 'Open the meeting room — seats the team')}
                  style={{ right: 24, bottom: 10 }} />
              <div className="px-label" style={{ right: 20, bottom: 2 }}>MEETING</div>
              {ambientOk && meetingActive && meetingIds.length > 0 && (
                <div className="px-meetcluster" title="In a meeting" aria-hidden="true">
                  {meetingIds.map(id => {
                    const a = agents.find(x => x.id === id);
                    return a ? <PxChar key={id} color={a.color} pose="front" className="idle-anim" /> : null;
                  })}
                </div>
              )}
              {ambientOk && walkers.map(w => (
                <div key={w.key} className={'px-walker' + (w.dir === 'return' ? ' ret' : '')}
                     style={{ ['--wd']: w.delay + 's' }} aria-hidden="true">
                  <PxChar color={w.color} pose="walk" />
                </div>
              ))}
              {ambientOk && coolerVisitorAgent && (
                <div className="px-walker at-cooler" aria-hidden="true">
                  <PxChar color={coolerVisitorAgent.color} pose="front" className="idle-anim" />
                </div>
              )}
              {ambientOk && arrival && (
                <div key={arrival.key} className="px-walker arriving" aria-hidden="true">
                  <PxChar color={arrival.color} pose="walk" />
                </div>
              )}
            </div>
          </div>

          {/* Street — the Japan-town ground floor of the scene. */}
          <div className="px-street">
            <Px n="tree" className="px-streetsp" style={{ left: '2%', bottom: 14 }} />
            <Px n="lamp" className="px-streetlamp" style={{ left: '16%', bottom: 14 }} />
            <Px n="bush" className="px-streetsp" style={{ left: '24%', bottom: 12 }} />
            <Px n="vending" className="px-streetsp" title="Vending machine" style={{ right: '14%', bottom: 14 }} />
            <Px n="lamp" className="px-streetlamp" style={{ right: '5%', bottom: 14 }} />
            <Px n="tree" className="px-streetsp" style={{ right: '0%', bottom: 14 }} />
            {ambientOk && (
              <div className="px-dog" aria-label="Maximus" title="Maximus" />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------ Live ticker ------------ */

/* Market quotes for the Trading Floor theme — NAS100 / US30 / SPX / GOLD from
   the companion backend's cached /market/quotes proxy (Yahoo Finance upstream;
   stock indices have no CORS-open free API the browser could hit directly).
   Hosts without the backend just never populate — the ticker degrades to
   activity-only, same as every other companion-backed feature. */
const MARKET_CACHE_KEY = 'cafresohq_hq_v1:marketQuotes';

function useMarketQuotes(enabled) {
  const [quotes, setQuotes] = useState(() => {
    try { return JSON.parse(localStorage.getItem(MARKET_CACHE_KEY) || '[]'); }
    catch (_e) { return []; }
  });
  useEffect(() => {
    if (!enabled) return;
    let dead = false;
    const pull = async () => {
      try {
        const r = await fetch(`${window._API_BASE || ''}/market/quotes`);
        if (!r.ok) return;                 // no backend / upstream down → keep last-good quotes
        const d = await r.json();
        const fresh = (d.quotes || []).filter(q => q && Number.isFinite(q.last));
        if (dead || !fresh.length) return;
        setQuotes(fresh);
      } catch (_e) { /* offline → keep last-good quotes */ }
    };
    pull();
    /* Interval skips while the tab is hidden; a visibilitychange pull
       refreshes immediately when the user comes back. */
    const t = setInterval(() => { if (!document.hidden) pull(); }, 60000);
    const onVis = () => { if (!document.hidden) pull(); };
    document.addEventListener('visibilitychange', onVis);
    return () => { dead = true; clearInterval(t); document.removeEventListener('visibilitychange', onVis); };
  }, [enabled]);
  useEffect(() => {
    try { localStorage.setItem(MARKET_CACHE_KEY, JSON.stringify(quotes)); } catch (_e) {}
  }, [quotes]);
  return enabled ? quotes : [];
}

function fmtQuote(q) {
  const price = q.last >= 1000
    ? Math.round(q.last).toLocaleString('en-US')
    : q.last.toLocaleString('en-US', { maximumFractionDigits: q.last >= 10 ? 2 : 3 });
  const pct = q.pct == null ? '' : ` ${q.pct >= 0 ? '▲' : '▼'}${Math.abs(q.pct).toFixed(1)}%`;
  return { price, pct, up: (q.pct || 0) >= 0 };
}

function Ticker({ items }) {
  const vocab = useVocab();
  const quotes = useMarketQuotes(!!vocab.marketTicker);
  /* The scroll keyframes translate -50%, so the line must be two identical
     halves: segment = quotes + activity, rendered twice. */
  const segment = (half) => (
    <React.Fragment key={half}>
      {quotes.map((q) => {
        const f = fmtQuote(q);
        return (
          <span key={half + q.sym}>
            <span className="kw">{q.sym}</span>
            <span className={f.up ? 'mkt-up' : 'mkt-down'}>{f.price}{f.pct}</span>
            <span className="sep">•</span>
          </span>
        );
      })}
      {items.map((it, i) => (
        <span key={half + '_' + i}>
          <span className="kw">{it.agent}</span>
          <span>· {it.msg}</span>
          <span className="sep">•</span>
        </span>
      ))}
    </React.Fragment>
  );
  return (
    <div className="ticker">
      <span className="badge">{vocab.live}</span>
      <div className="ticker-track">
        <div className="line">
          {segment('a')}
          {segment('b')}
        </div>
      </div>
    </div>
  );
}

/* ------------ CEO Chat monitor ------------ */

export { MobileTabBar, OfficeView, Rail, Tab, Ticker };
