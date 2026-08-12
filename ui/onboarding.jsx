import { CafresoHQClient } from '../claude-client.jsx';
const { useState, useEffect, useLayoutEffect, useRef, useMemo, createContext, useContext } = React;
const NOTIF_KIND_ICON = {
  receipt:  '📋',
  agent:    '✦',
  mission:  '🔬',
  approval: '⚖',
  system:   'ℹ',
};
const NOTIF_FILTERS = [
  { value: 'all',      label: 'All' },
  { value: 'approval', label: 'Approvals' },
  { value: 'receipt',  label: 'Receipts' },
  { value: 'agent',    label: 'Coworkers' },
  { value: 'mission',  label: 'Missions' },
  { value: 'system',   label: 'System' },
];

function fmtRelative(ts) {
  if (!ts) return '';
  const dt = Date.now() - ts;
  if (dt < 60_000)  return 'just now';
  if (dt < 3_600_000) return Math.floor(dt / 60_000) + 'm ago';
  if (dt < 86_400_000) return Math.floor(dt / 3_600_000) + 'h ago';
  return Math.floor(dt / 86_400_000) + 'd ago';
}

/* ─────────────────────────────────────────────────────────────────────
   <OnboardingTour>
   First-launch coach marks. Each step is { id, title, body, target?, action? }.
     - target: optional CSS selector or DOMRect getter — if present, a
       spotlight ring draws around the element and the card anchors near it.
     - action: optional fn invoked when the step is shown (e.g. switch view).
   Skippable; "Don't show again" persists to localStorage.

   Props:
     open       bool
     steps      array of step objects
     onClose    fn (called on Skip / Finish)
     onComplete fn — called when finishing successfully (vs skipping)
   ───────────────────────────────────────────────────────────────────── */
function OnboardingTour({ open, steps = [], onClose, onComplete }) {
  const [idx, setIdx] = useState(0);
  const [spotlight, setSpotlight] = useState(null);

  const step = steps[idx];

  React.useEffect(() => {
    if (!open || !step) { setSpotlight(null); return; }
    if (step.action) try { step.action(); } catch (_e) {}
    if (step.target) {
      /* Compute spotlight rect; retry briefly because target may need a
         frame after the action fires. */
      let attempts = 0;
      const compute = () => {
        const el = typeof step.target === 'string'
          ? document.querySelector(step.target)
          : (typeof step.target === 'function' ? step.target() : null);
        if (el && el.getBoundingClientRect) {
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) {
            setSpotlight({
              left: r.left - 6, top: r.top - 6,
              width: r.width + 12, height: r.height + 12,
            });
            return;
          }
        }
        if (++attempts < 6) setTimeout(compute, 80);
      };
      compute();
    } else {
      setSpotlight(null);
    }
  }, [open, idx]);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose && onClose();
      if (e.key === 'ArrowRight' || e.key === 'Enter') next();
      if (e.key === 'ArrowLeft') back();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, idx, steps.length]);

  if (!open || !step) return null;

  const next = () => {
    if (idx >= steps.length - 1) {
      onComplete && onComplete();
      onClose && onClose();
    } else {
      setIdx(i => i + 1);
    }
  };
  const back = () => setIdx(i => Math.max(0, i - 1));

  /* Anchor card position: mobile → bottom sheet above tab bar;
     desktop → anchored near spotlight or centered. */
  const isMobileTour = typeof window !== 'undefined' && window.innerWidth <= 768;
  const cardStyle = isMobileTour
    ? { bottom: 'calc(72px + env(safe-area-inset-bottom))', left: '8px', right: '8px', top: 'auto', transform: 'none' }
    : spotlight ? (() => {
      const cardW = 420, cardH = 220;
      const margin = 16;
      const W = window.innerWidth, H = window.innerHeight;
      const below = spotlight.top + spotlight.height + margin + cardH < H;
      let top = below
        ? spotlight.top + spotlight.height + margin
        : spotlight.top - cardH - margin;
      if (top < margin) top = margin;
      let left = spotlight.left + spotlight.width / 2 - cardW / 2;
      if (left < margin) left = margin;
      if (left + cardW > W - margin) left = W - cardW - margin;
      return { top: top + 'px', left: left + 'px', transform: 'none' };
    })() : { top: '50%', left: '50%', transform: 'translate(-50%, -50%)' };

  return (
    <>
      <div className="oc-tour-backdrop" onClick={onClose} />
      {spotlight && <div className="oc-tour-spotlight" style={spotlight} aria-hidden="true" />}
      <div
        className={'oc-tour-card' + (spotlight ? ' is-anchored' : '')}
        style={cardStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="oc-tour-title"
      >
        <div className="oc-tour-step">Step {idx + 1} of {steps.length}</div>
        <div className="oc-tour-title" id="oc-tour-title">{step.title}</div>
        <div className="oc-tour-body">{step.body}</div>
        <div className="oc-tour-foot">
          <div className="oc-tour-progress" aria-hidden="true">
            {steps.map((_, i) => (
              <span key={i} className={i === idx ? 'is-active' : i < idx ? 'is-done' : ''} />
            ))}
          </div>
          <button
            className="px-btn ghost"
            style={{fontSize: 'var(--text-9)'}}
            onClick={onClose}
          >Skip</button>
          {idx > 0 && (
            <button
              className="px-btn secondary"
              style={{fontSize: 'var(--text-10)'}}
              onClick={back}
            >Back</button>
          )}
          <button
            className="px-btn primary"
            style={{fontSize: 'var(--text-10)'}}
            onClick={next}
          >{idx >= steps.length - 1 ? 'Finish' : 'Next →'}</button>
        </div>
      </div>
    </>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   <OnboardingKeyStep>
   The "Get your free AI key" body used inside a tour step. Walks the user
   through creating a free OpenRouter key and pasting it in. Persists via
   CafresoHQClient.hermesSetOpenRouterKey() (server-side container env
   when the endpoint exists; otherwise local settings — see client helper).
   Styled with the same tokens as the rest of the tour card.
   ───────────────────────────────────────────────────────────────────── */
function OnboardingKeyStep() {
  const C = CafresoHQClient;
  const existing = (C && C.getSettings && C.getSettings().openrouterKey) || '';
  const [key, setKey] = useState(existing);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(existing ? 'have' : null); // 'have' | 'ok' | 'local' | 'err'
  // Trial brain: when this deployment ships a shared free key, a brand-new HQ
  // ALREADY works with no signup — so this step is an optional upgrade, not a
  // gate. Fetch the live status so the copy tells the truth for THIS container.
  const [trial, setTrial] = useState(null); // null=unknown, {active, remaining, cap}
  useEffect(() => {
    let dead = false;
    fetch((window._API_BASE || '') + '/hermes/trial-status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (!dead && d) setTrial(d); })
      .catch(() => {});
    return () => { dead = true; };
  }, []);
  const onTrial = !!(trial && trial.active) && !existing;

  const save = async () => {
    const trimmed = (key || '').trim();
    if (!trimmed || saving) return;
    setSaving(true); setSaved(null);
    try {
      const r = (C && C.hermesSetOpenRouterKey)
        ? await C.hermesSetOpenRouterKey(trimmed)
        : { ok: true, serverStored: false };
      setSaved(r && r.serverStored ? 'ok' : 'local');
    } catch (_e) {
      setSaved('err');
    } finally { setSaving(false); }
  };

  const rowStyle = { display: 'flex', gap: 'var(--sp-2)', marginTop: 'var(--sp-3)' };
  const linkStyle = { color: 'var(--accent-rose, #c45)', fontWeight: 700, textDecoration: 'underline' };

  return (
    <div>
      {onTrial ? (
        <p style={{ margin: '0 0 var(--sp-3)' }}>
          <strong>You're already set.</strong> Your HQ runs on Cafreso's free shared
          brain out of the box — hire an agent and it works right now, no signup.
          {typeof trial.remaining === 'number' && (
            <span style={{ color: 'var(--ink-3)' }}>{' '}({trial.remaining} of {trial.cap} free
            messages left today.)</span>
          )}{' '}Want your own model, faster replies, or higher limits? Add a free key
          below — totally optional.
        </p>
      ) : (
        <>
          <p style={{ margin: '0 0 var(--sp-3)' }}>
            Your HQ runs on a free, open-weights AI brain — but it needs <strong>your own
            free key</strong> from OpenRouter. It takes about a minute and stays unique to you.
          </p>
          <ol style={{ margin: '0 0 var(--sp-3)', paddingLeft: '1.2em', lineHeight: 'var(--lh-normal)' }}>
            <li>Open{' '}
              <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" style={linkStyle}>
                openrouter.ai/keys
              </a>{' '}and sign up (it's free).</li>
            <li>Click <strong>Create Key</strong>, give it any name.</li>
            <li>Copy the key (starts with <code>sk-or-…</code>).</li>
            <li>Paste it below and hit <strong>Save</strong>.</li>
          </ol>
        </>
      )}
      <div style={rowStyle}>
        <input
          type="password"
          className="oc-input sz-sm"
          placeholder="sk-or-v1-…"
          value={key}
          onChange={e => { setKey(e.target.value); setSaved(null); }}
          onKeyDown={e => { if (e.key === 'Enter') save(); }}
          style={{ flex: 1, fontSize: 'var(--text-11)' }}
          autoComplete="off"
          spellCheck={false}
          /* "OpenRouter key", not "OpenRouter API key": §6 bans the latter
             on onboarding by name, and the visible copy around this input
             never used it anyway — it says "Copy the key (starts with
             sk-or-…)". So the accessible name was the ONLY place the banned
             phrase appeared, which also meant a screen-reader user heard
             different vocabulary than a sighted user read. Now they match.

             The larger question §6 really asks of this step — whether a
             newcomer should be pasting a key at all rather than signing in —
             is a content decision about the bring-your-own path, not
             something to settle by editing an aria-label. */
          aria-label="OpenRouter key"
        />
        <button className="px-btn secondary" style={{ fontSize: 'var(--text-10)' }}
          onClick={save} disabled={saving || !(key || '').trim()}>
          {saving ? '…' : 'Save'}
        </button>
      </div>
      <div style={{ marginTop: 'var(--sp-2)', fontSize: 'var(--text-9)', minHeight: '1.2em',
        color: saved === 'err' ? 'var(--danger, #c33)' : 'var(--ink-3)' }}>
        {saved === 'ok'    && '✓ Key saved to your container. You\'re ready.'}
        {saved === 'local' && '✓ Key saved. (Stored in this browser — your container will pick it up.)'}
        {saved === 'have'  && '✓ A key is already set. Paste a new one to replace it.'}
        {saved === 'err'   && '✕ Couldn\'t save — check the key and try again.'}
        {!saved && (onTrial
          ? 'Optional — your own key gives unlimited use and lets you pick the model.'
          : 'Free · unique to you · you can change it anytime in Settings → API.')}
      </div>
      <div style={{ marginTop: 'var(--sp-2)', fontSize: 'var(--text-9)', color: 'var(--ink-3)' }}>
        Want stronger output? Plug in your own Claude, GPT or paid key —{' '}
        <button
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent('cafresohq:openSettings', { detail: { tab: 'keys' } }))}
          style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', cursor: 'pointer', ...linkStyle }}
        >bring your own brain →</button>
      </div>
    </div>
  );
}

/* Persistent getting-started checklist. Unlike the one-shot tour, this survives
   a tour-skip and stays until every step is done (or the user dismisses it), so
   a new user is never left at a dead end (e.g. agents that error with no key).
   Steps auto-check from live app state passed in as props. */
/* `onCollapsedChange` exists because this card is not the only bottom-anchored
   onboarding surface: app.jsx also renders a coach-mark pill, and the pill
   only exists while this checklist is undismissed — so on a phone they are
   ALWAYS both on screen at once. Measured at 375×812: the pill covered this
   card by 155px, its entire height. The owner of that collision is app.jsx
   (it renders both), so it needs to know whether this card is expanded.
   Still local state — this only reports, never obeys. */
function GettingStarted({ hasKey, hired, chatted, assigned, built, sawWork, onAddKey, onHire, onChat, onTasks, onProjects, onWatch, onDismiss, onCollapsedChange }) {
  const [collapsed, setCollapsedState] = useState(false);
  const setCollapsed = (v) => {
    setCollapsedState(v);
    if (onCollapsedChange) onCollapsedChange(v);
  };
  const steps = [
    // Managed containers include Cafreso's Gemma 4 brain — this step self-
    // completes on those, and stays actionable only for standalone setups.
    { k: 'key',   done: !!hasKey,   n: 1, label: 'Your AI brain',            hint: 'Gemma 4 by Cafreso is included — bring your own brain anytime.', act: onAddKey, cta: 'Brain settings' },
    { k: 'hire',  done: !!hired,    n: 2, label: 'Hire your first specialist', hint: 'Click an empty desk (or press H) — or seed a swarm.', act: onHire,  cta: 'Hire' },
    { k: 'chat',  done: !!chatted,  n: 3, label: 'Chat with your team',      hint: 'Say hi to your CEO — ask for anything.',            act: onChat,  cta: 'Open chat' },
    { k: 'task',  done: !!assigned, n: 4, label: 'Give them a task',          hint: 'Add a task, then drop it on a desk to delegate.',    act: onTasks, cta: 'Open tasks' },
    { k: 'build', done: !!built,    n: 5, label: 'Create your first Project',  hint: 'Your coworkers build docs, decks, code & sites here — preview them live.', act: onProjects, cta: 'New Project' },
    { k: 'watch', done: !!sawWork,  n: 6, label: 'Watch them work',           hint: 'Desks light up; the Team inbox logs every action.', act: onWatch, cta: 'Open office' },
  ];
  const doneCount = steps.filter(s => s.done).length;
  const allDone = doneCount === steps.length;

  // When the last step completes, celebrate briefly then dismiss on the
  // user's behalf — a finished checklist shouldn't sit on screen forever.
  useEffect(() => {
    if (!allDone || !onDismiss) return;
    const t = setTimeout(onDismiss, 6000);
    return () => clearTimeout(t);
  }, [allDone]);

  const card = {
    /* No `left` or `bottom` here on purpose — .gs-coach in styles.css owns
       both, so each offset stays next to the thing it has to clear. See the
       notes there: at left:14 this sat squarely on the rail's SETTINGS
       button, and at bottom:14 it ran underneath the mobile tab bar. An
       inline value would silently outrank the breakpoint override that
       fixes either one. */
    position: 'fixed', zIndex: 40, width: 274, maxWidth: 'calc(100vw - 28px)',
    background: 'rgba(24,20,14,0.95)', backdropFilter: 'blur(8px)',
    border: '1px solid rgba(245,210,93,0.28)', borderRadius: 12, padding: '12px 13px',
    color: '#e9e2d4', font: '12px Inter, system-ui, sans-serif', boxShadow: '0 14px 44px rgba(0,0,0,0.42)',
  };
  if (collapsed) {
    return React.createElement('button', {
      onClick: () => setCollapsed(false),
      // gs-coach-mini so the mobile stylesheet can tell the collapsed pill
      // (fixed 44px, always single-line) from the expanded card — the coach
      // mark stacks on top of this exact height. See styles.css.
      className: 'gs-coach gs-coach-mini',
      // `left`/`bottom` come from .gs-coach in styles.css — see the card below.
      style: { position: 'fixed', zIndex: 40, cursor: 'pointer', border: '1px solid rgba(245,210,93,0.3)', borderRadius: 20, padding: '7px 12px', background: 'rgba(24,20,14,0.95)', color: '#F5D25D', font: '600 12px Inter, system-ui, sans-serif', boxShadow: '0 10px 30px rgba(0,0,0,0.4)' },
      title: 'Getting started',
    }, '✦ Getting started · ' + doneCount + '/' + steps.length);
  }
  return React.createElement('div', { className: 'gs-coach', style: card },
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 } },
      React.createElement('div', { style: { fontWeight: 700, color: '#F5D25D', flex: 1 } }, allDone ? "You're all set 🎉" : 'Getting started'),
      React.createElement('span', { style: { color: '#8f8676' } }, doneCount + '/' + steps.length),
      React.createElement('button', { onClick: () => setCollapsed(true), title: 'Collapse', style: { cursor: 'pointer', background: 'none', border: 'none', color: '#8f8676', fontSize: 14, lineHeight: 1, padding: 2 } }, '–'),
      React.createElement('button', { onClick: onDismiss, title: 'Dismiss', style: { cursor: 'pointer', background: 'none', border: 'none', color: '#8f8676', fontSize: 14, lineHeight: 1, padding: 2 } }, '✕'),
    ),
    steps.map((s) => React.createElement('div', { key: s.k, style: { display: 'flex', alignItems: 'flex-start', gap: 9, padding: '6px 0', borderTop: '1px solid rgba(255,255,255,0.05)' } },
      React.createElement('span', { style: { flex: '0 0 auto', width: 18, height: 18, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, marginTop: 1, background: s.done ? 'rgba(165,196,161,0.25)' : 'rgba(245,210,93,0.14)', color: s.done ? '#A5C4A1' : '#F5D25D', border: '1px solid ' + (s.done ? 'rgba(165,196,161,0.5)' : 'rgba(245,210,93,0.4)') } }, s.done ? '✓' : s.n),
      React.createElement('div', { style: { flex: 1, minWidth: 0 } },
        React.createElement('div', { style: { fontWeight: 600, textDecoration: s.done ? 'line-through' : 'none', color: s.done ? '#8f8676' : '#e9e2d4' } }, s.label),
        !s.done && React.createElement('div', { style: { color: '#9b938a', fontSize: 11, lineHeight: 1.35, margin: '1px 0 4px' } }, s.hint),
        !s.done && s.act && React.createElement('button', { onClick: s.act, style: { cursor: 'pointer', border: '1px solid rgba(245,210,93,0.4)', borderRadius: 6, padding: '3px 9px', background: 'rgba(245,210,93,0.12)', color: '#F5D25D', font: '600 11px Inter, system-ui, sans-serif' } }, s.cta + ' →'),
      ),
    )),
    allDone && React.createElement('button', { onClick: onDismiss, style: { marginTop: 9, width: '100%', cursor: 'pointer', border: '1px solid rgba(165,196,161,0.45)', borderRadius: 7, padding: '6px', background: 'rgba(165,196,161,0.14)', color: '#A5C4A1', font: '600 12px Inter, system-ui, sans-serif' } }, 'Dismiss'),
  );
}

function NotificationBell({ unreadCount = 0, onClick, title }) {
  return (
    <button
      type="button"
      className="oc-notif-bell"
      onClick={onClick}
      title={title || `${unreadCount} unread notification${unreadCount === 1 ? '' : 's'}`}
      aria-label={`Notifications (${unreadCount} unread)`}
    >
      <span aria-hidden="true">🔔</span>
      {unreadCount > 0 && <span className="oc-notif-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>}
    </button>
  );
}

function NotificationCenter({
  open, onClose,
  notifications = [],
  onMarkAllRead,
  onClear,
  emptyHint = 'You\'re all caught up.',
}) {
  const [filter, setFilter] = useState('all');

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const filtered = notifications.filter(n =>
    filter === 'all' ? true : n.kind === filter
  );
  const filteredSorted = filtered.slice().sort((a, b) => (b.ts || 0) - (a.ts || 0));
  const unreadCount = notifications.filter(n => n.unread).length;

  return (
    <>
      <div className="oc-notif-backdrop" onClick={onClose} />
      <aside
        className="oc-notif-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Notification center"
      >
        <div className="oc-notif-head">
          <span aria-hidden="true">🔔</span>
          <span className="oc-notif-title">Notifications</span>
          {unreadCount > 0 && (
            <button
              className="px-btn ghost"
              style={{fontSize: 'var(--text-9)'}}
              onClick={onMarkAllRead}
              title="Mark all as read"
            >Mark all read</button>
          )}
          <button
            className="px-btn ghost"
            onClick={onClose}
            aria-label="Close notification center"
            title="Close (Esc)"
          >✕</button>
        </div>
        <div className="oc-notif-filters" role="tablist">
          {NOTIF_FILTERS.map(f => {
            const count = f.value === 'all'
              ? notifications.length
              : notifications.filter(n => n.kind === f.value).length;
            if (f.value !== 'all' && count === 0) return null;
            return (
              <button
                key={f.value}
                className={'oc-notif-filter' + (filter === f.value ? ' is-active' : '')}
                onClick={() => setFilter(f.value)}
              >{f.label} {count > 0 && <span style={{opacity:0.7}}>· {count}</span>}</button>
            );
          })}
        </div>
        <div className="oc-notif-list">
          {filteredSorted.length === 0 && (
            <div className="oc-notif-empty">
              {filter === 'all' ? emptyHint : `No ${filter} notifications.`}
            </div>
          )}
          {filteredSorted.map(n => (
            <div
              key={n.id}
              className={'oc-notif-row' + (n.unread ? ' is-unread' : '')}
              onClick={() => n.onClick && n.onClick(n)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter' && n.onClick) n.onClick(n); }}
            >
              <span className="oc-notif-icon" aria-hidden="true">
                {n.icon || NOTIF_KIND_ICON[n.kind] || '·'}
              </span>
              <div className="oc-notif-body">
                <div className="oc-notif-msg">{n.msg}</div>
                <div className="oc-notif-meta">
                  {n.source && <span>{n.source}</span>}
                  {n.source && n.ts && <span>·</span>}
                  {n.ts && <span>{fmtRelative(n.ts)}</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
        {(notifications.length > 0 && onClear) && (
          <div className="oc-notif-foot">
            <span>{notifications.length} total</span>
            <button
              className="px-btn ghost"
              style={{fontSize: 'var(--text-9)'}}
              onClick={async () => { if (await window.hqConfirm('Clear all notifications? Audit trail is lost.', { danger: true })) onClear(); }}
            >CLEAR ALL</button>
          </div>
        )}
      </aside>
    </>
  );
}


export { GettingStarted, NotificationBell, NotificationCenter, OnboardingKeyStep, OnboardingTour };
