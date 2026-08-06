import { CafresoHQChain, CafresoHQClient } from '../claude-client.jsx';
import { SPRITES, Sprite } from '../sprites.jsx';
import { Ico, NAV_ITEMS, useVocab } from './primitives.jsx';
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

function Rail({ onOpenSettings, onShowCEO, active, setActive, collapsed = false, onToggle, onLaunch, runningViews }) {
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
        {NAV_ITEMS.map(([k, label], i) => {
          // In desktop (window) mode the rail is a launcher: clicking opens
          // or raises that app's window instead of switching the full view.
          const running = onLaunch && runningViews && runningViews.indexOf(k) !== -1;
          return (
            <a
              key={k}
              className={(onLaunch ? (running ? 'running' : '') : (active===k?'active':''))}
              onClick={()=> onLaunch ? onLaunch(k) : setActive(k)}
              title={collapsed ? `${label} (${i + 1})` : `Shortcut: ${i + 1}`}
              aria-current={active===k ? 'page' : undefined}
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

function OfficeView({ agents, onHire, onAgentClick, onCoffee, onInspect, stickies, corkPins = [], onAddSticky, onRemoveSticky, onUnpin, onSitWithCEO, onOpenMemory, onOpenMeeting, onTaskDropOnAgent, tasks = [], onAssignTask, onGoToTasks, maxSlots = 5, ceoBusy = false, attentionCount = 0, onOpenAttention, meetingActive = false, meetingIds = [] }) {

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
  const [dropTarget, setDropTarget] = React.useState(null);
  const vocab = useVocab();
  const isMobileOffice = typeof window !== 'undefined' && window.innerWidth <= 768;
  // Inbox tasks = anything sitting in the queue waiting to be delegated.
  // We treat status === 'inbox' OR a task with no assignee as eligible to
  // show in the rail. The drop handler on agent desks moves the task to
  // status:'doing' and sets assignedTo, so it disappears from the rail
  // automatically once delegated.
  const inboxTasks = (tasks || []).filter(t => t && (t.status === 'inbox' || !t.assignedTo));

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
    window.addEventListener('cafresohq:walkIn', onWalkIn);
    return () => { window.removeEventListener('cafresohq:walkIn', onWalkIn); clearTimeout(clearT); };
  }, [ambientOk]);

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
  const [liveTools, setLiveTools] = React.useState({});   // agentId -> {name}
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
        setLiveTools(prev => ({ ...prev, [d.agentId]: { name: d.name } }));
        clearLater(d.agentId, 45000);
      } else if (d.phase === 'done') {
        clearLater(d.agentId, 1600);
      }
    };
    window.addEventListener('cafresohq:agentTool', onTool);
    return () => { window.removeEventListener('cafresohq:agentTool', onTool); timers.forEach(clearTimeout); };
  }, []);
  const anyLive = Object.keys(liveTools).length > 0;

  /* ── Desk screens — each monitor shows the tail of its agent's REAL output
     stream (cafresohq:agentScreen from the app-level run paths, throttled at
     the source). phase 'stream' scrolls; 'done' freezes the last line ~8s
     then fades. Kept in local state (never on the agents array) so token
     traffic can't trigger app-wide re-renders. */
  const [screens, setScreens] = React.useState({});   // agentId -> {tail, phase}
  React.useEffect(() => {
    const timers = new Map();
    const onScreen = (e) => {
      const d = e.detail || {};
      if (!d.agentId || !d.tail) return;
      setScreens(prev => ({ ...prev, [d.agentId]: { tail: d.tail, phase: d.phase } }));
      const t = timers.get(d.agentId); if (t) clearTimeout(t);
      // Streams that die mid-run (error/abort) never send 'done' — a 60s
      // safety clear keeps monitors from showing stale text forever.
      timers.set(d.agentId, setTimeout(() => {
        setScreens(prev => { if (!(d.agentId in prev)) return prev; const n = { ...prev }; delete n[d.agentId]; return n; });
      }, d.phase === 'done' ? 8000 : 60000));
    };
    window.addEventListener('cafresohq:agentScreen', onScreen);
    return () => { window.removeEventListener('cafresohq:agentScreen', onScreen); timers.forEach(clearTimeout); };
  }, []);

  /* ── Tip Rain — money events land as coins on the earning agent's desk.
     Fed by the app-level tip watcher via cafresohq:moneyEvent. Reduced-motion
     users get a static "+X TOKEN" chip instead (CSS side). */
  const [tipRain, setTipRain] = React.useState({});   // agentId -> {amount, token, kind}
  React.useEffect(() => {
    const timers = new Map();
    const onMoney = (e) => {
      const d = e.detail || {};
      if (!d.agentId || (d.kind !== 'tip' && d.kind !== 'payday' && d.kind !== 'furnish')) return;
      setTipRain(prev => ({ ...prev, [d.agentId]: { amount: d.amount, token: d.token, kind: d.kind } }));
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
    <div className="office">
      {/* Task rail — slim strip of draggable cards above the rooms.
          - Desktop: drag a card onto a senior agent's desk to delegate.
          - Mobile: tap the assignee dropdown inside the card; drag-and-drop
            is unreliable on touch so the picker is the primary affordance.
          The header `tag` already explains the gesture; this rail provides
          the actual drag source the office was designed around. */}
      <div className="office-task-rail" aria-label="Inbox tasks">
        <div className="otr-head">
          <span className="otr-title">📋 Inbox</span>
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
        {inboxTasks.length === 0 ? (
          <div className="otr-empty">All clear. Drop something here from the Tasks tab to delegate.</div>
        ) : (
          <div className="otr-scroll">
            {inboxTasks.map(t => (
              <div key={t.id}
                   className={`otr-card pri-${t.priority || 'med'}`}
                   draggable
                   onDragStart={(e) => {
                     e.dataTransfer.setData('task', t.id);
                     e.dataTransfer.effectAllowed = 'move';
                   }}
                   title="Drag to an agent's desk to delegate">
                <div className="otr-card-row">
                  <span className={`otr-pri pri-${t.priority || 'med'}`}>{t.priority || 'med'}</span>
                  <div className="otr-card-title">{t.title}</div>
                </div>
                {t.detail && <div className="otr-card-detail">{t.detail}</div>}
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
                            title="Assign to an agent">
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
            <div className="mas-plus" onClick={onHire} title="Hire agent">+</div>
          </div>
        </div>
      )}
      <div className="wall-line" />
      <div className="floor" />
      {/* Open-floor "lounge" — couch + water cooler frame the room, a floor mat
          announces the HQ. Decorative only (pointer-events:none), desktop-only. */}
      {!isMobileOffice && (
        <div className="floor-decor" aria-hidden="true">
          <div className="meeting-table" />
          <div className="floor-zone fz-meeting">MEETING</div>
          <div className="floor-mat">CAFRESO HQ</div>
          <div className="lounge-couch" />
          <div className="water-cooler"><span className="wc-bubble" /></div>
          <div className="floor-zone fz-kitchen">KITCHEN</div>
        </div>
      )}
      <div className="pet" aria-label="Maximus"><Sprite data="maximus" scale={2}/></div>

      {/* Ambient walkers — meeting commute + idle cooler visit. Children of
          .office so their left% keyframes ride the open floor like .pet. */}
      {ambientOk && walkers.map(w => (
        <div key={w.key} className={'walker' + (w.dir === 'return' ? ' return' : '')}
             style={{ ['--wd']: w.delay + 's' }} aria-hidden="true">
          <Sprite data={w.color} scale={2} />
        </div>
      ))}
      {ambientOk && coolerVisitorAgent && (
        <div className="walker cooler" aria-hidden="true">
          <Sprite data={coolerVisitorAgent.color} scale={2} />
        </div>
      )}
      {ambientOk && arrival && (
        <div key={arrival.key} className="walker arriving" aria-hidden="true">
          <Sprite data={arrival.color} scale={2} />
        </div>
      )}
      {/* Meeting cluster — participants grouped at the meeting door while the
          meeting is in session (this is the P5 "proximity" surface). */}
      {ambientOk && meetingActive && meetingIds.length > 0 && (
        <div className="meeting-cluster" title="In a meeting" aria-hidden="true">
          {meetingIds.map(id => {
            const a = agents.find(x => x.id === id);
            return a ? <Sprite key={id} data={a.color} scale={1.4} /> : null;
          })}
        </div>
      )}

      <div className="rooms">
        {/* Wall fixtures — zone chip, LIVE pip, wallet P&L board */}
        {!isMobileOffice && (
          <>
            <span className="wall-zone" style={{ left: '42%' }} aria-hidden="true">TEAM FLOOR</span>
            {anyLive && <span className="wall-live" title="An agent is working right now">● {vocab.live}</span>}
            {walletServiceOn && plWallets && plWallets.length > 0 && (
              <div className="pl-frame" title="Agent P&L — ▲ earned (tips + payroll) · ▼ spent (on-chain metering) · net">
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
            {/* Situation Wall — the office's ops board. Live data only;
                tiles that can't know their answer (standalone mode, no
                wallet service) simply don't render. */}
            <div className="sit-wall" title="Situation Wall — live office telemetry">
              <div className="sw-title">◉ SITUATION</div>
              <div className="sw-row" title={wallHealth === null ? 'Checking container…' : wallHealth ? 'Container healthy' : 'Container unreachable'}>
                <span className={`sw-lamp ${wallHealth === null ? 'amber' : wallHealth ? 'green' : 'red'}`}/> HQ
              </div>
              {wallSearch !== null && (
                <div className="sw-row" title={`Search network: ${wallSearch.ok ? (wallSearch.detail || 'up') : 'unavailable'} — click to re-check`}
                     style={{cursor:'pointer'}}
                     onClick={async (e) => {
                       e.stopPropagation();
                       setWallSearch(null);
                       try { setWallSearch(await CafresoHQClient.braveProbe()); }
                       catch (_e) { setWallSearch({ ok: false }); }
                     }}>
                  <span className={`sw-bars ${wallSearch.ok ? 'up' : 'down'}`} aria-hidden="true"><i/><i/><i/></span> SEARCH
                </div>
              )}
              {wallCrew && wallCrew.total > 0 && (
                <div className="sw-row" title={`${wallCrew.installed}/${wallCrew.total} agent runtimes installed · ${busyCount} working now`}>
                  ⚒ {wallCrew.installed}/{wallCrew.total}{busyCount > 0 ? ` · ${busyCount} busy` : ''}
                </div>
              )}
              {officeTokens > 0 && (
                <div className="sw-row" title={`≈ ${(officeTokens/1000).toFixed(0)}k tokens spent this session (~$${(officeTokens*0.0000015).toFixed(2)})`}>
                  <span className="sw-fuel"><i style={{width:`${Math.min(100,(officeTokens/1000000)*100)}%`}}/></span> FUEL
                </div>
              )}
              {goldTreasury !== null && goldTreasury > BigInt(0) && (
                <div className="sw-row" title={`Office treasury — ${plFmt(goldTreasury, 'sGLDT')} sGLDT across all agent wallets`}>
                  ◈ {plFmt(goldTreasury, 'sGLDT')} GOLD
                </div>
              )}
            </div>
          </>
        )}
        {/* CEO office */}
        <div className="room ceo">
          <div className="nameplate">
            <span>{vocab.corner} · CAFRESOHQ</span>
            <span className="pip" />
          </div>
          <div className="interior">
            {/* Office furnishings — overhead light, rug, framed photo on the
                back wall. These run first so they sit BEHIND the interactive
                pieces (corkboard, arcade, desk, etc.). */}
            <div className="ceo-ceiling-light" aria-hidden="true"/>
            <div className="office-carpet" aria-hidden="true"/>
            <div className="wall-photo" title="Cafreso skyline" aria-hidden="true"/>
            <div className="corkboard" title="Bulletin board — pinned memory & receipts">
              {corkPins.length === 0 && (
                <div className="cork-empty">📌 pin memory or receipts here</div>
              )}
              {corkPins.slice(0, 9).map(p => (
                <div key={p.id} className={`cork-pin kind-${p.kind}`} title={p.text}>
                  <span className="cp-text">{p.text}</span>
                  <button className="cp-x" onClick={(e)=>{ e.stopPropagation(); onUnpin && onUnpin(p.id); }}>✕</button>
                </div>
              ))}
            </div>
            <div className="window">
              <div className="sun"/>
              <div className="cloud cloud-a"/>
              <div className="cloud cloud-b"/>
            </div>
            {/* Wall clock — analog, ticking minute hand */}
            <div className="wall-clock" title="Wall clock">
              <span className="wc-hand wc-hour"/>
              <span className="wc-hand wc-min"/>
              <span className="wc-pin"/>
            </div>
            {/* Mini strategy whiteboard on the right wall */}
            <div className="whiteboard" title="Strategy whiteboard">
              <span className="wb-line">Q3 — SHIP HQ</span>
              <span className="wb-line wb-r">★ ECOSYSTEM</span>
              <span className="wb-line">DAO · CHAIN · AI</span>
            </div>
            {/* Bookshelf with colored binder spines — slots into the gap above
                the floor between the arcade and the desk. */}
            <div className="bookshelf" title="Quarterly binders" aria-hidden="true">
              <div className="shelf"><i className="book b1"/><i className="book b2"/><i className="book b3"/><i className="book b4"/><i className="book b5"/></div>
              <div className="shelf"><i className="book b3"/><i className="book b1"/><i className="book b5"/><i className="book b2"/></div>
              <div className="shelf"><i className="book b4"/><i className="book b3"/><i className="book b1"/></div>
            </div>
            <div className="plant" />
            {/* Coffee mug on the desk top */}
            <div className="coffee-mug" title="CEO's coffee" aria-hidden="true">
              <span className="cm-steam"/>
            </div>
            {/* Desk peripherals — keyboard, mouse, phone */}
            <div className="desk-keyboard" aria-hidden="true"/>
            <div className="desk-mouse" aria-hidden="true"/>
            <div className="desk-phone" title="Desk phone" aria-hidden="true"/>
            {/* Trash bin between desk and filing cabinet */}
            <div className="trash-bin" title="Trash" aria-hidden="true"/>
            {/* Clickable filing cabinet → memory shelf */}
            <div className="filing clickable" title="Browse CafresoHQ's memory" onClick={(e)=>{e.stopPropagation(); onOpenMemory();}}>
              <span/><span/><span/>
              <div className="tag">MEMORY</div>
            </div>
            {/* Guest chair — click to start 1:1 */}
            <div className="guest-chair" title="Sit down with CafresoHQ" onClick={(e)=>{e.stopPropagation(); onSitWithCEO();}}/>
            <div className="guest-chair-label">↑ 1:1 CHAIR</div>
            {/* Meeting room door */}
            <div className="meeting-door" title="Open meeting room" onClick={(e)=>{e.stopPropagation(); onOpenMeeting();}}/>
            <div className="meeting-door-label">MEETING →</div>
            {/* Pac-Man arcade — clickable easter egg that boots Cafreso Workspaces */}
            <a className="arcade clickable" href="https://ai.cafreso.com/workspaces"
               title="PAC-MAN · Boot up Cafreso Workspaces"
               onClick={(e)=>e.stopPropagation()}>
              <span className="arcade-marquee">PAC-MAN</span>
              <span className="arcade-bezel">
                <span className="arcade-screen">
                  <i className="dot"/><i className="dot"/><i className="dot"/><i className="dot"/>
                  <i className="pac"/>
                  <i className="ghost blinky"/>
                  <i className="ghost pinky"/>
                  <i className="ghost inky"/>
                </span>
              </span>
              <span className="arcade-coin"/>
              <span className="arcade-controls">
                <i className="joystick"/>
                <i className="btn-red"/>
                <i className="btn-red"/>
              </span>
              <span className="arcade-base"/>
            </a>
            <div className="sticky-stack">
              {stickies.map(s => (
                <div key={s.id} className="sticky" title="Pinned context">
                  <span className="x" onClick={(e)=>{e.stopPropagation(); onRemoveSticky(s.id);}}>✕</span>
                  {s.text}
                </div>
              ))}
              <div className="add-sticky" onClick={onAddSticky}>+ NOTE</div>
            </div>
            <div className="desk" />
            {/* Office chair behind the CEO — the backrest pokes up
                behind the sprite so it reads as "sitting at the desk". */}
            <div className="office-chair" aria-hidden="true"/>
            <div className="sprite-slot">
              {ceoBusy ? <div className="bubble t-body">replying to you…</div> : null}
              <Sprite data="cafresohq" scale={2} className="bob slow"/>
            </div>
          </div>
        </div>

        {/* Vault Room — the office's treasury, mirroring REAL on-chain
            balances. Display-only by design: no transfer UI in this room.
            Gold bars scale with aggregate sGLDT across agent wallets; the
            glass case shows the boss's BANK holdings (prestige, not spend).
            The capped pipe is minegold.brave — plumbed, not yet flowing. */}
        {!isMobileOffice && walletServiceOn && (goldTreasury !== null || bankBalance !== null) && (
          <div className="room vault" title="Vault Room — real balances, display only">
            <div className="nameplate">
              <span>VAULT · TREASURY</span>
              <span className="pip idle" />
            </div>
            <div className="interior">
              <div className="vault-door" aria-hidden="true"/>
              {goldTreasury !== null && (
                <div className="gold-stack" title={`${plFmt(goldTreasury, 'sGLDT')} sGLDT across all agent wallets`}>
                  {Array.from({ length: goldBars }).map((_, gi) => (
                    <span key={gi} className="gold-bar" style={{ left: (gi % 4) * 14, bottom: Math.floor(gi / 4) * 8 }}/>
                  ))}
                  <div className="gold-label">{plFmt(goldTreasury, 'sGLDT')} sGLDT</div>
                </div>
              )}
              {bankBalance !== null && (
                <div className={`bank-case ${bankTier || 'empty'}`}
                     title={`BANK — Banking Brave · ${plFmt(bankBalance, 'BANK') } held${bankTier ? ` · ${bankTier} tier` : ''}`}>
                  <div className="bank-coin">◈</div>
                  <div className="bank-label">{plFmt(bankBalance, 'BANK')} BANK</div>
                </div>
              )}
              <div className="gold-pipe" title="minegold.brave — coming soon" aria-hidden="true"/>
            </div>
          </div>
        )}

        {/* Senior agent desks (drop-targetable for tasks).
            Assistants + transient sub-agents render NESTED inside their
            senior's interior, not as separate top-level desks. */}
        {seniorAgents.map((a, i) => {
          const subs = subordinatesOf(a.id);
          const awayMeeting = ambientOk && meetingIdSet.has(a.id);
          const awayCooler = ambientOk && coolerVisitor === a.id;
          const liveTool = liveTools[a.id];
          const screen = screens[a.id];
          const paperCount = Math.min((a.journal || []).length, 5);
          return (
          <div key={a.id}
               className={`room status-${a.status || 'idle'} ${dropTarget===a.id?'drop-target':''} ${a.elevated ? 'elevated' : ''}${subs.length ? ' has-subordinates' : ''}${awayMeeting ? ' away-meeting' : ''}${awayCooler ? ' away-cooler' : ''}${liveTool ? ' tool-live' : ''}`}
               onClick={() => onInspect(a)}
               style={{cursor:'pointer', zIndex: 2 + i}}
               onDragOver={e=>{e.preventDefault(); setDropTarget(a.id);}}
               onDragLeave={()=>setDropTarget(null)}
               onDrop={e=>{
                 const taskId = e.dataTransfer.getData('task');
                 setDropTarget(null);
                 if (taskId && onTaskDropOnAgent) onTaskDropOnAgent(taskId, a);
               }}>
            <div className="nameplate">
              <span>{a.elevated ? '🛡 ' : ''}{a.name.toUpperCase()} · {a.role.split(' ').slice(-1)[0].toUpperCase()}</span>
              {subs.length > 0 && (
                <span className="subord-count" title={`${subs.length} subordinate${subs.length === 1 ? '' : 's'}`}
                      style={{fontSize:9,opacity:0.65,marginLeft:6}}>
                  +{subs.length}
                </span>
              )}
              <span className={`pip ${a.status}`} />
            </div>
            <div className="interior">
              {/* Per-desk decor — the agent's OWN furnishings when bought in
                  the Furnish Shop (a.decor, persisted on the agent record);
                  falls back to the original index-deterministic pick so
                  unfurnished offices look exactly like they always did. */}
              {(() => { const W = ['mini-window','poster','wall-shelf','pin-note','poster p1','mini-window']; const w = (a.decor && a.decor.wall) || W[i % W.length]; return <div className={w} aria-hidden="true">{w.startsWith('mini-window') ? <span className="sun"/> : null}</div>; })()}
              <div className="room-rug" data-variant={(a.decor && a.decor.rug != null) ? a.decor.rug : i % 3} aria-hidden="true"/>
              <div className="plant" style={{left: 6}}/>
              <div className="coffee" title={`Refresh ${a.name}'s context`}
                onClick={(e)=>{e.stopPropagation(); onCoffee(a);}} />
              <div className="desk" />
              {/* Live monitor: the tail of this agent's REAL output stream.
                  Dark when idle (no element), scrolling text while running,
                  frozen last line briefly after 'done'. */}
              {screen && !awayMeeting && !awayCooler && (
                <div className={`desk-screen ${screen.phase === 'done' ? 'is-done' : 'is-live'}`} aria-hidden="true">
                  {screen.tail}
                </div>
              )}
              {/* Filed reports pile up as papers; click opens the journal. */}
              {paperCount > 0 && (
                <div className="desk-papers"
                     title={`${(a.journal || []).length} filed report${(a.journal || []).length === 1 ? '' : 's'} — click to read`}
                     onClick={(e)=>{ e.stopPropagation(); onInspect(a); }}>
                  {Array.from({ length: paperCount }).map((_, pi) => (
                    <span key={pi} className="desk-paper" style={{ bottom: pi * 3, left: pi % 2 ? 1 : 0 }}/>
                  ))}
                </div>
              )}
              <div className="mini-keys" aria-hidden="true"/>
              <div className="desk-lamp" aria-hidden="true"/>
              {liveTool && !awayMeeting && !awayCooler && (
                <div className="tool-chip" aria-hidden="true">
                  ⚙ {String(liveTool.name || '').replace(/_/g, ' ').toLowerCase()}
                </div>
              )}
              {tipRain[a.id] && (
                <div className="tip-rain" aria-hidden="true">
                  {Array.from({ length: 7 }, (_, ci) => (
                    <span key={ci} className="tip-coin" style={{ left: `${8 + ci * 13}%`, animationDelay: `${ci * 0.18}s` }}>◉</span>
                  ))}
                  <div className="tip-amount">
                    {tipRain[a.id].kind === 'payday' ? '💰 PAYDAY ' : ''}+{tipRain[a.id].amount} {tipRain[a.id].token}
                  </div>
                </div>
              )}
              <div className="sprite-slot">
                {(awayMeeting || awayCooler)
                  ? <div className="away-placard">{awayMeeting ? 'in the meeting room' : 'stretching legs'}</div>
                  : (a.task ? <div className="bubble t-body">{a.task}</div> : null)}
                <div style={{position:'relative'}}>
                  {/* Bob speed tracks real effort — fast only while the agent
                      is actually running, not by desk-index parity. */}
                  <Sprite data={a.color} scale={2} className={`bob ${a.status === 'busy' ? 'fast' : 'slow'}`}/>
                  <div className={`mood ${a.mood || 'idle'}`} title={a.mood || 'idle'}>{MOOD_ICON[a.mood||'idle']}</div>
                </div>
              </div>
              {/* Subordinates — assistants sit at their own mini desks
                  in the background of the senior's office. */}
              {subs.length > 0 && (
                <div className="subord-bg">
                  {subs.map((s) => (
                    <div key={s.id}
                         className={`subord-desk ${s.transient ? 'transient' : 'assistant'}`}
                         onClick={(e)=>{ e.stopPropagation(); onInspect(s); }}
                         title={`${s.name} · ${s.role}${s.transient ? ' (transient sub)' : ' (assistant)'}${s.task ? ' · ' + s.task : ''}`}>
                      <div className="subord-sprite-slot">
                        <Sprite data={s.color} scale={1.6} className="bob slow"/>
                      </div>
                      <div className="subord-mini-desk"/>
                      <div className="subord-name">
                        {s.name}
                        <span className={`pip ${s.status || 'idle'}`}/>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );})}

        {/* Empty hireable desks */}
        {Array.from({length: emptySlots}).map((_, i) => (
          <div key={'e'+i} className="room empty" onClick={onHire} title={vocab.hireTitle}
               style={{ zIndex: 2 + seniorAgents.length + i }}>
            <div className="nameplate">
              <span style={{color:'#9a8a80'}}>{vocab.vacant}</span>
              <span className="pip idle" />
            </div>
            <div className="interior">
              <div className="hire-sign" aria-hidden="true">FOR HIRE</div>
              <div className="desk" style={{opacity:0.6}}/>
              <div className="hire">
                <div className="plus">+</div>
                <div className="label">{vocab.hire}</div>
              </div>
            </div>
          </div>
        ))}
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
