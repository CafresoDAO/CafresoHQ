/* ==========================================================================
   CafresoHQ — main app components (chat, office, cards, modals)
   ========================================================================== */

const { useState, useEffect, useLayoutEffect, useRef, useMemo, createContext, useContext } = React;

/* ------------ Theme vocabulary system ------------ */
const THEME_VOCAB = {
  default:      { agent: 'Agent',   agents: 'Agents',   office: 'Office',        corner: 'CEO',           hire: 'HIRE',     vacant: 'VACANT', live: 'LIVE',     hireTitle: 'Hire a sub-agent' },
  sepia:        null,
  solarized:    null,
  dracula:      null,
  highcontrast: null,
  coffeeshop:   { agent: 'Barista', agents: 'Baristas', office: 'Coffee Shop',   corner: 'ESPRESSO BAR',  hire: 'RECRUIT', vacant: 'OPEN',   live: 'ORDERS',  hireTitle: 'Recruit a barista' },
  wallstreet:   { agent: 'Broker',  agents: 'Brokers',  office: 'Trading Floor', corner: 'CORNER SUITE',  hire: 'RECRUIT', vacant: 'OPEN',   live: 'MARKET',  hireTitle: 'Recruit a broker', marketTicker: true },
};
const VocabCtx = createContext(THEME_VOCAB.default);
function useVocab() { return useContext(VocabCtx); }
function getVocab(theme) { return THEME_VOCAB[theme] || THEME_VOCAB.default; }

/* ------------ Icon helpers: tiny pixel SVGs (simple primitives only) ------------ */
function Ico({ kind, size=16 }) {
  const common = { width: size, height: size, viewBox: '0 0 16 16', shapeRendering: 'crispEdges' };
  const K = '#3b2e2a';
  if (kind === 'tasks') return (<svg {...common}><rect x="2" y="3" width="12" height="2" fill={K}/><rect x="2" y="7" width="8" height="2" fill={K}/><rect x="2" y="11" width="10" height="2" fill={K}/></svg>);
  if (kind === 'content') return (<svg {...common}><rect x="3" y="2" width="9" height="12" fill="none" stroke={K} strokeWidth="2"/><rect x="5" y="5" width="5" height="1" fill={K}/><rect x="5" y="8" width="5" height="1" fill={K}/></svg>);
  if (kind === 'calendar') return (<svg {...common}><rect x="2" y="3" width="12" height="11" fill="none" stroke={K} strokeWidth="2"/><rect x="2" y="3" width="12" height="3" fill={K}/><rect x="5" y="1" width="2" height="3" fill={K}/><rect x="9" y="1" width="2" height="3" fill={K}/></svg>);
  if (kind === 'projects') return (<svg {...common}><rect x="2" y="5" width="12" height="9" fill="none" stroke={K} strokeWidth="2"/><rect x="2" y="3" width="6" height="3" fill={K}/></svg>);
  if (kind === 'memory') return (<svg {...common}><circle cx="8" cy="8" r="5" fill="none" stroke={K} strokeWidth="2"/><rect x="7" y="4" width="2" height="5" fill={K}/></svg>);
  if (kind === 'vault') return (<svg {...common}><rect x="3" y="2" width="9" height="12" fill="none" stroke={K} strokeWidth="2"/><rect x="5" y="5" width="5" height="1" fill={K}/><rect x="5" y="8" width="5" height="1" fill={K}/><rect x="5" y="11" width="5" height="1" fill={K}/><rect x="2" y="2" width="2" height="12" fill={K}/></svg>);
  if (kind === 'graph') return (<svg {...common}><circle cx="4" cy="4" r="2" fill={K}/><circle cx="12" cy="4" r="2" fill={K}/><circle cx="4" cy="12" r="2" fill={K}/><circle cx="12" cy="12" r="2" fill={K}/><circle cx="8" cy="8" r="2" fill={K}/><line x1="4" y1="4" x2="8" y2="8" stroke={K} strokeWidth="1"/><line x1="12" y1="4" x2="8" y2="8" stroke={K} strokeWidth="1"/><line x1="4" y1="12" x2="8" y2="8" stroke={K} strokeWidth="1"/><line x1="12" y1="12" x2="8" y2="8" stroke={K} strokeWidth="1"/></svg>);
  if (kind === 'team') return (<svg {...common}><circle cx="5" cy="6" r="2" fill={K}/><circle cx="11" cy="6" r="2" fill={K}/><path d="M2 13 Q5 9 8 13" stroke={K} strokeWidth="2" fill="none"/><path d="M8 13 Q11 9 14 13" stroke={K} strokeWidth="2" fill="none"/></svg>);
  if (kind === 'visual') return (<svg {...common}><rect x="2" y="4" width="12" height="8" fill="none" stroke={K} strokeWidth="2"/><rect x="5" y="6" width="2" height="2" fill={K}/><rect x="9" y="6" width="2" height="2" fill={K}/></svg>);
  if (kind === 'workflows') return (<svg {...common}><rect x="1" y="3" width="4" height="3" fill={K}/><rect x="6" y="3" width="4" height="3" fill={K}/><rect x="11" y="3" width="4" height="3" fill={K}/><rect x="3" y="6" width="1" height="3" fill={K}/><rect x="3" y="9" width="10" height="1" fill={K}/><rect x="13" y="6" width="1" height="3" fill={K}/><rect x="7" y="6" width="2" height="3" fill={K}/><rect x="2" y="10" width="4" height="3" fill={K}/><rect x="6" y="10" width="4" height="3" fill={K}/><rect x="10" y="10" width="4" height="3" fill={K}/></svg>);
  if (kind === 'terminal') return (<svg {...common}><rect x="2" y="3" width="12" height="10" fill="none" stroke={K} strokeWidth="2"/><polyline points="4,7 6,9 4,11" fill="none" stroke={K} strokeWidth="1.5"/><rect x="8" y="10" width="4" height="1.5" fill={K}/></svg>);
  if (kind === 'settings') return (<svg {...common}><rect x="7" y="2" width="2" height="12" fill={K}/><rect x="2" y="7" width="12" height="2" fill={K}/></svg>);
  if (kind === 'send') return (<svg {...common}><polygon points="2,2 14,8 2,14 5,8" fill={K}/></svg>);
  if (kind === 'delegate') return (<svg {...common}><rect x="2" y="7" width="8" height="2" fill={K}/><polygon points="8,4 13,8 8,12" fill={K}/></svg>);
  return null;
}

/* ------------ Sidebar rail ------------ */
const NAV_ITEMS = [
  ['visual', 'Office'],
  ['tasks', 'Tasks'],
  ['calendar', 'Calendar'],
  ['memory', 'Memory'],
  ['vault', 'Vault'],
  ['team', 'Team'],
  ['terminal', 'Terminal'],
  ['projects', 'Workspace'],
];

/* ─────────────────────────────────────────────────────────────────────
   <Btn>
   The single button component for the app. Wraps the existing .px-btn
   styles so existing markup keeps working — but adds:
     · loading state (spinner inside, label hidden, click disabled)
     · disabled handled visually + behaviorally
     · size variants (sm | md | lg) using token-driven padding/text size
     · icon before/after label slots
     · full-width option

   Why a thin wrapper? The pixel-art identity lives in CSS already; we
   don't need a fresh DOM. We just want the JSX surface to be uniform.

   Variants:    primary | secondary | ghost | danger
   Sizes:       sm | md (default) | lg
   States:      default | hover (CSS) | active (CSS) | disabled | loading
   Props:
     variant      str   default 'secondary'
     size         str   default 'md'
     loading      bool  swaps label for spinner; locks click
     disabled     bool  visually + behaviorally disabled
     icon         node  rendered before the label
     iconAfter    node  rendered after the label
     full         bool  width:100%
     onClick      fn
     title        str   tooltip
     className    str   extra classes
     style        obj
     children     node  label
   Use <Btn type="submit"> in <form> contexts; defaults to "button" so
   nothing accidentally submits.
   ───────────────────────────────────────────────────────────────────── */
function Btn({
  variant = 'secondary',
  size = 'md',
  loading = false,
  disabled = false,
  icon = null,
  iconAfter = null,
  full = false,
  onClick,
  title,
  className = '',
  style,
  type = 'button',
  children,
  ...rest
}) {
  const isDisabled = disabled || loading;
  const cls = [
    'px-btn',
    variant,
    size && `sz-${size}`,
    full && 'full',
    loading && 'is-loading',
    isDisabled && !loading && 'is-disabled',
    className,
  ].filter(Boolean).join(' ');
  return (
    <button
      type={type}
      className={cls}
      onClick={isDisabled ? undefined : onClick}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      title={title}
      style={style}
      {...rest}
    >
      {icon && <span className="btn-icon" aria-hidden="true">{icon}</span>}
      {children}
      {iconAfter && <span className="btn-icon-after" aria-hidden="true">{iconAfter}</span>}
    </button>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   <Card>
   Layout primitive for any "boxed group of stuff" — agent cards, doc
   cards, calendar items, project list rows, vault info pills, etc.
   Variants control elevation/border emphasis. Sizes control padding.

   Composition:
     <Card>
       <Card.Header>…</Card.Header>     (optional)
       <Card.Body>…</Card.Body>
       <Card.Footer>…</Card.Footer>     (optional)
     </Card>
   You can also pass children directly without slots — they render
   inside a default-padded body.

   Variants:    default | raised | inset | outline | interactive
   Sizes:       sm | md (default) | lg
   States:      default | hover (interactive only) | active (interactive only) | selected
   Props:
     variant     str   default 'default'
     size        str   padding scale, default 'md'
     selected    bool  applies the .oc-card--selected outline
     onClick     fn    if present, automatically adds `interactive` variant
     as          str   element tag, default 'div' — pass 'button' or 'a' for native semantics
     header      node  shorthand for Card.Header
     footer      node  shorthand for Card.Footer
     className   str
     style       obj
     children    node
   ───────────────────────────────────────────────────────────────────── */
function Card({
  variant,
  size = 'md',
  selected = false,
  onClick,
  as: Tag = 'div',
  header,
  footer,
  className = '',
  style,
  children,
  ...rest
}) {
  const v = variant || (onClick ? 'interactive' : 'default');
  const cls = [
    'oc-card',
    'oc-card--' + v,
    selected && 'oc-card--selected',
    className,
  ].filter(Boolean).join(' ');

  /* If header/footer slots are used, pad them separately and put children
     into a body container with size-padded inset. Otherwise the children
     render directly inside the card with its outer padding. */
  const usingSlots = header != null || footer != null;
  const bodyPadCls = 'oc-card-pad-' + size;

  return (
    <Tag
      className={cls}
      onClick={onClick}
      style={style}
      {...(Tag === 'button' ? { type: 'button' } : null)}
      {...rest}
    >
      {header && <div className="oc-card-head">{header}</div>}
      {usingSlots
        ? <div className={`oc-card-body ${bodyPadCls}`}>{children}</div>
        : <div className={bodyPadCls} style={{display:'flex',flexDirection:'column',minHeight:0,flex:1}}>{children}</div>}
      {footer && <div className="oc-card-foot">{footer}</div>}
    </Tag>
  );
}
Card.Header = function CardHeader({ children, actions, className = '', ...rest }) {
  return (
    <div className={`oc-card-head ${className}`} {...rest}>
      {children}
      {actions && <div className="oc-card-head-actions">{actions}</div>}
    </div>
  );
};
Card.Body = function CardBody({ size = 'md', className = '', children, ...rest }) {
  return <div className={`oc-card-body oc-card-pad-${size} ${className}`} {...rest}>{children}</div>;
};
Card.Footer = function CardFooter({ className = '', children, ...rest }) {
  return <div className={`oc-card-foot ${className}`} {...rest}>{children}</div>;
};

/* ─────────────────────────────────────────────────────────────────────
   Input primitives — <Field>, <TextField>, <TextArea>, <Select>,
   <Checkbox>, <Toggle>, <SearchField>

   <Field> is the shared wrapper that renders label / hint / error around
   any control. The other components compose Field + a styled HTML input.

   Common props:
     label      str/node   — visible label rendered above the control
     hint       str/node   — helper text below the control
     error      str/node   — error text (overrides hint when set)
     required   bool       — adds a red asterisk to the label
     id         str        — auto-generated if not provided

   See DESIGN_SYSTEM.md for full API.
   ───────────────────────────────────────────────────────────────────── */

let _ocFieldId = 0;
function useFieldId(provided) {
  const ref = React.useRef(null);
  if (ref.current == null) ref.current = provided || ('oc-fld-' + (++_ocFieldId));
  return ref.current;
}

function Field({ id, label, hint, error, required, children, className = '', style }) {
  return (
    <div className={`oc-field ${className}`} style={style}>
      {label && (
        <label htmlFor={id} className="oc-field-label">
          {label}{required && <span className="oc-field-required">*</span>}
        </label>
      )}
      {children}
      {error
        ? <div className="oc-field-error" role="alert"><span aria-hidden="true">⚠</span> {error}</div>
        : hint ? <div className="oc-field-hint">{hint}</div> : null}
    </div>
  );
}

function TextField({
  label, hint, error, required, id,
  value, onChange, onEnter, onKeyDown,
  placeholder, type = 'text', size = 'md',
  icon, iconAfter,
  disabled, autoFocus,
  className = '', style, inputClassName = '', inputStyle,
  ...rest
}) {
  const fid = useFieldId(id);
  const cls = ['oc-input', `sz-${size}`, error && 'oc-input--error', inputClassName].filter(Boolean).join(' ');
  const wrapCls = ['oc-input-wrap', icon && 'has-icon-l', iconAfter && 'has-icon-r'].filter(Boolean).join(' ');
  const handleKey = (e) => {
    if (onKeyDown) onKeyDown(e);
    if (e.key === 'Enter' && onEnter && !e.shiftKey) onEnter(e);
  };
  return (
    <Field id={fid} label={label} hint={hint} error={error} required={required} className={className} style={style}>
      <div className={wrapCls}>
        {icon && <span className="oc-input-icon left" aria-hidden="true">{icon}</span>}
        <input
          id={fid}
          type={type}
          className={cls}
          value={value ?? ''}
          onChange={onChange}
          onKeyDown={handleKey}
          placeholder={placeholder}
          disabled={disabled}
          autoFocus={autoFocus}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={error ? fid + '-err' : (hint ? fid + '-hint' : undefined)}
          style={inputStyle}
          {...rest}
        />
        {iconAfter && <span className="oc-input-icon right" aria-hidden="true">{iconAfter}</span>}
      </div>
    </Field>
  );
}

function TextArea({
  label, hint, error, required, id,
  value, onChange, onEnter, onKeyDown,
  placeholder, rows = 4,
  resize = 'vertical', mono = false,
  disabled, autoFocus,
  className = '', style, inputClassName = '', inputStyle,
  ...rest
}) {
  const fid = useFieldId(id);
  const cls = [
    'oc-input',
    error && 'oc-input--error',
    mono && 'oc-input--mono',
    resize === 'none' && 'resize-none',
    inputClassName,
  ].filter(Boolean).join(' ');
  const handleKey = (e) => {
    if (onKeyDown) onKeyDown(e);
    if (e.key === 'Enter' && onEnter && !e.shiftKey) {
      e.preventDefault();
      onEnter(e);
    }
  };
  return (
    <Field id={fid} label={label} hint={hint} error={error} required={required} className={className} style={style}>
      <textarea
        id={fid}
        className={cls}
        value={value ?? ''}
        onChange={onChange}
        onKeyDown={handleKey}
        placeholder={placeholder}
        rows={rows}
        disabled={disabled}
        autoFocus={autoFocus}
        aria-invalid={error ? 'true' : undefined}
        style={inputStyle}
        {...rest}
      />
    </Field>
  );
}

function Select({
  label, hint, error, required, id,
  value, onChange, options = [], children,
  size = 'md',
  disabled, placeholder,
  className = '', style, inputClassName = '', inputStyle,
  ...rest
}) {
  const fid = useFieldId(id);
  const cls = ['oc-input', `sz-${size}`, error && 'oc-input--error', inputClassName].filter(Boolean).join(' ');
  return (
    <Field id={fid} label={label} hint={hint} error={error} required={required} className={className} style={style}>
      <select
        id={fid}
        className={cls}
        value={value ?? ''}
        onChange={onChange}
        disabled={disabled}
        aria-invalid={error ? 'true' : undefined}
        style={inputStyle}
        {...rest}
      >
        {placeholder && <option value="">{placeholder}</option>}
        {options.length
          ? options.map((o, i) => (
              typeof o === 'string'
                ? <option key={o} value={o}>{o}</option>
                : <option key={o.value ?? i} value={o.value} disabled={o.disabled}>{o.label}</option>
            ))
          : children}
      </select>
    </Field>
  );
}

function Checkbox({
  label, hint, id,
  checked, onChange, disabled,
  className = '', style,
  ...rest
}) {
  const fid = useFieldId(id);
  const cls = ['oc-check', disabled && 'is-disabled', className].filter(Boolean).join(' ');
  return (
    <label className={cls} style={style} htmlFor={fid}>
      <input
        id={fid}
        type="checkbox"
        checked={!!checked}
        onChange={onChange}
        disabled={disabled}
        {...rest}
      />
      <span style={{display:'flex',flexDirection:'column',gap:2,minWidth:0}}>
        {label && <span style={{fontSize:'var(--text-12)',color:'var(--ink)'}}>{label}</span>}
        {hint && <span style={{fontSize:'var(--text-10)',color:'var(--ink-3)'}}>{hint}</span>}
      </span>
    </label>
  );
}

function Toggle({
  label, hint, id,
  checked, onChange, disabled,
  className = '', style,
  ...rest
}) {
  const fid = useFieldId(id);
  const handleToggle = () => { if (!disabled && onChange) onChange(!checked); };
  const handleKey = (e) => {
    if (disabled) return;
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); handleToggle(); }
  };
  const knob = (
    <span
      role="switch"
      tabIndex={disabled ? -1 : 0}
      aria-checked={!!checked}
      aria-disabled={disabled || undefined}
      aria-labelledby={label ? fid + '-lbl' : undefined}
      className={['oc-toggle', checked && 'is-on', disabled && 'is-disabled'].filter(Boolean).join(' ')}
      onClick={handleToggle}
      onKeyDown={handleKey}
      style={style}
      {...rest}
    >
      <span className="oc-toggle-knob" />
    </span>
  );
  if (!label && !hint) return knob;
  return (
    <div
      className={['oc-toggle-row', disabled && 'is-disabled', className].filter(Boolean).join(' ')}
      onClick={handleToggle}
    >
      <div className="oc-toggle-label">
        {label && <div id={fid + '-lbl'}>{label}</div>}
        {hint && <div style={{fontSize:'var(--text-10)',color:'var(--ink-3)'}}>{hint}</div>}
      </div>
      {knob}
    </div>
  );
}

/* SearchField — TextField with a magnifier icon and an optional onClear
   that surfaces an inline ✕ button when there's text. */
function SearchField({
  value, onChange, onClear, onEnter,
  placeholder = 'Search…',
  size = 'md',
  className = '', style,
  ...rest
}) {
  return (
    <TextField
      type="search"
      value={value}
      onChange={onChange}
      onEnter={onEnter}
      placeholder={placeholder}
      size={size}
      icon="🔍"
      iconAfter={value && (onClear || onChange) ? (
        <button
          type="button"
          className="oc-search-clear"
          onClick={() => onClear ? onClear() : onChange && onChange({ target: { value: '' } })}
          aria-label="Clear search"
          style={{pointerEvents:'auto', cursor:'pointer'}}
        >✕</button>
      ) : null}
      className={className}
      style={style}
      {...rest}
    />
  );
}

/* ─────────────────────────────────────────────────────────────────────
   <Tabs> + <Tab>
   Uniform tab strip used across the app — chat panel sub-tabs, gear-panel
   color modes, mission modal mode picker, ChatWindow header tabs, etc.

   Modes (variant):
     'default'    — bordered rectangles with shadow on active (matches button identity)
     'underline'  — flat, underline-bar active style (cleaner inside modals)
     'pill'       — rounded pills (compact toolbars)

   Sub-API:
     <Tabs value onChange variant stretched>
       <Tab value="x" label="…" badge={n} icon={…} disabled />
     </Tabs>

   Or via array:
     <Tabs value onChange items={[{value, label, badge, icon}, …]} />
   ───────────────────────────────────────────────────────────────────── */
function Tabs({
  value, onChange,
  variant = 'default',
  stretched = false,
  className = '', style,
  items = null,
  children,
  ariaLabel,
}) {
  const tabs = items
    ? items.map((it, i) => (
        <Tab key={it.value ?? i}
             value={it.value} label={it.label} badge={it.badge}
             icon={it.icon} disabled={it.disabled} />
      ))
    : children;
  const handleKey = (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    const tabEls = Array.from(e.currentTarget.querySelectorAll('.oc-tab:not(.is-disabled)'));
    const idx = tabEls.findIndex(t => t.classList.contains('is-active'));
    if (idx < 0) return;
    const next = e.key === 'ArrowRight' ? (idx + 1) % tabEls.length : (idx - 1 + tabEls.length) % tabEls.length;
    tabEls[next].click();
    tabEls[next].focus();
  };
  /* Inject the active value/onChange into each Tab via cloneElement so
     callers don't have to wire them up manually. */
  const cloned = React.Children.map(tabs, (child, i) => {
    if (!child || !React.isValidElement(child)) return child;
    return React.cloneElement(child, {
      _active: child.props.value === value,
      _onSelect: () => onChange && onChange(child.props.value),
    });
  });
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className={['oc-tabs', `variant-${variant}`, stretched && 'is-stretched', className].filter(Boolean).join(' ')}
      style={style}
      onKeyDown={handleKey}
    >
      {cloned}
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────
   Toast / status system
   <ToastProvider> wraps the app root once. Inside React, call:
       const toast = useToast();
       toast.info('Saved.');
       toast.success('Created Inbox/idea.md', { duration: 4000 });
       toast.error('Save failed', { detail: err.message });
       toast.warn('No path between selected nodes');
       toast.action('Build complete', { actionLabel: 'Open', onAction: openLog });
   The hook returns: { info, success, warn, error, action, push, dismiss, dismissAll }.

   For non-React code (event listeners, setInterval handlers, etc.) call
   the global imperative escape hatch:
       window.cafresohqToast.info('Hello from outside React');

   Implementation: a tiny pub/sub backed by a ref'd queue. Each toast has an
   id, kind, title, optional detail, optional action button, and a duration.
   The provider renders up to 3 simultaneously (newest at the bottom of the
   visible stack). Older toasts wait in the queue and auto-promote on dismiss.
   ───────────────────────────────────────────────────────────────────── */

const ToastCtx = React.createContext(null);
const TOAST_KINDS = {
  info:    { icon: 'ℹ',  duration: 3500 },
  success: { icon: '✓',  duration: 3500 },
  warn:    { icon: '⚠',  duration: 5000 },
  error:   { icon: '✕',  duration: 6000 },
  action:  { icon: '✦',  duration: 7000 },
};
const TOAST_VISIBLE_MAX = 3;
let _toastSeq = 0;

function ToastProvider({ children }) {
  const [stack, setStack] = useState([]);   // visible toasts (max 3)
  const queueRef = useRef([]);              // queued toasts waiting to be shown
  const timersRef = useRef(new Map());      // id → timeout handle

  const dismiss = React.useCallback((id) => {
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
      setStack(s => s.filter(t => t.id !== id));
      const queued = queueRef.current.shift();
      if (queued) {
        setStack(s => [...s, queued].slice(-TOAST_VISIBLE_MAX));
        scheduleAutoDismiss(queued);
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
    if (e.key === 'Enter' && (req.kind === 'prompt' || e.target === okRef.current || req.kind === 'confirm')) {
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
          <button className="px-btn secondary" onClick={() => done(cancelValue)}>{req.opts.cancelLabel || 'Cancel'}</button>
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
        if (lbl.startsWith(q)) score = 100;
        else if (lbl.includes(q)) score = 60;
        else if (sect.includes(q)) score = 30;
        else if (lbl.split(/\s+/).some(w => w.startsWith(q))) score = 80;
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
            onKeyDown={handleKey}
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
  { value: 'agent',    label: 'Agents' },
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
   window.CafresoHQClient.hermesSetOpenRouterKey() (server-side container env
   when the endpoint exists; otherwise local settings — see client helper).
   Styled with the same tokens as the rest of the tour card.
   ───────────────────────────────────────────────────────────────────── */
function OnboardingKeyStep() {
  const C = window.CafresoHQClient;
  const existing = (C && C.getSettings && C.getSettings().openrouterKey) || '';
  const [key, setKey] = useState(existing);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(existing ? 'have' : null); // 'have' | 'ok' | 'local' | 'err'

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
          aria-label="OpenRouter API key"
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
        {!saved            && 'Free · unique to you · you can change it anytime in Settings → API.'}
      </div>
      <div style={{ marginTop: 'var(--sp-2)', fontSize: 'var(--text-9)', color: 'var(--ink-3)' }}>
        Want stronger output? Plug in your own Claude, GPT or paid key —{' '}
        <button
          type="button"
          onClick={() => window.dispatchEvent(new CustomEvent('cafresohq:openSettings', { detail: { tab: 'keys' } }))}
          style={{ background: 'none', border: 'none', padding: 0, font: 'inherit', cursor: 'pointer', ...linkStyle }}
        >bring your own key →</button>
      </div>
    </div>
  );
}

/* Persistent getting-started checklist. Unlike the one-shot tour, this survives
   a tour-skip and stays until every step is done (or the user dismisses it), so
   a new user is never left at a dead end (e.g. agents that error with no key).
   Steps auto-check from live app state passed in as props. */
function GettingStarted({ hasKey, hired, chatted, assigned, built, sawWork, onAddKey, onHire, onChat, onTasks, onProjects, onWatch, onDismiss }) {
  const [collapsed, setCollapsed] = useState(false);
  const steps = [
    { k: 'key',   done: !!hasKey,   n: 1, label: 'Add your AI key',          hint: 'Free OpenRouter key — powers every agent.',         act: onAddKey, cta: 'Add key' },
    { k: 'hire',  done: !!hired,    n: 2, label: 'Hire your first specialist', hint: 'Click an empty desk (or press H) — or seed a swarm.', act: onHire,  cta: 'Hire' },
    { k: 'chat',  done: !!chatted,  n: 3, label: 'Chat with your team',      hint: 'Say hi to your CEO — ask for anything.',            act: onChat,  cta: 'Open chat' },
    { k: 'task',  done: !!assigned, n: 4, label: 'Give them a task',          hint: 'Add a task, then drop it on a desk to delegate.',    act: onTasks, cta: 'Open tasks' },
    { k: 'build', done: !!built,    n: 5, label: 'Create your first Project',  hint: 'Agents build docs, decks, code & sites here — preview them live.', act: onProjects, cta: 'New Project' },
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
    position: 'fixed', left: 14, bottom: 14, zIndex: 40, width: 274, maxWidth: 'calc(100vw - 28px)',
    background: 'rgba(24,20,14,0.95)', backdropFilter: 'blur(8px)',
    border: '1px solid rgba(245,210,93,0.28)', borderRadius: 12, padding: '12px 13px',
    color: '#e9e2d4', font: '12px Inter, system-ui, sans-serif', boxShadow: '0 14px 44px rgba(0,0,0,0.42)',
  };
  if (collapsed) {
    return React.createElement('button', {
      onClick: () => setCollapsed(false),
      style: { position: 'fixed', left: 14, bottom: 14, zIndex: 40, cursor: 'pointer', border: '1px solid rgba(245,210,93,0.3)', borderRadius: 20, padding: '7px 12px', background: 'rgba(24,20,14,0.95)', color: '#F5D25D', font: '600 12px Inter, system-ui, sans-serif', boxShadow: '0 10px 30px rgba(0,0,0,0.4)' },
      title: 'Getting started',
    }, '✦ Getting started · ' + doneCount + '/' + steps.length);
  }
  return React.createElement('div', { style: card },
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
              onClick={() => { if (window.confirm('Clear all notifications? Audit trail is lost.')) onClear(); }}
            >CLEAR ALL</button>
          </div>
        )}
      </aside>
    </>
  );
}

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

  /* ── Tip Rain — money events land as coins on the earning agent's desk.
     Fed by the app-level tip watcher via cafresohq:moneyEvent. Reduced-motion
     users get a static "+X TOKEN" chip instead (CSS side). */
  const [tipRain, setTipRain] = React.useState({});   // agentId -> {amount, token, kind}
  React.useEffect(() => {
    const timers = new Map();
    const onMoney = (e) => {
      const d = e.detail || {};
      if (!d.agentId || (d.kind !== 'tip' && d.kind !== 'payday')) return;
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
      const s = window.CafresoHQClient.getSettings();
      return !!(s.icpServices && s.icpServices.wallet) &&
             !!(window.CafresoHQChain && window.CafresoHQChain.isAvailable());
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
        const chain = window.CafresoHQChain;
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
  const PL_DECIMALS = { ICP: 8, ckUSDT: 6, ckUNI: 18, sGLDT: 8, nanas: 8 };
  const plFmt = (raw, token) => {
    try {
      const dec = PL_DECIMALS[token] != null ? PL_DECIMALS[token] : 8;
      const n = Number(BigInt(raw)) / Math.pow(10, dec);
      return n >= 100 ? n.toFixed(0) : n >= 1 ? n.toFixed(2) : n.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
    } catch (_e) { return '0'; }
  };

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

        {/* Senior agent desks (drop-targetable for tasks).
            Assistants + transient sub-agents render NESTED inside their
            senior's interior, not as separate top-level desks. */}
        {seniorAgents.map((a, i) => {
          const subs = subordinatesOf(a.id);
          const awayMeeting = ambientOk && meetingIdSet.has(a.id);
          const awayCooler = ambientOk && coolerVisitor === a.id;
          const liveTool = liveTools[a.id];
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
              {/* Per-desk decor — deterministic by index so each office looks
                  distinct but stable across renders. One rotating wall piece +
                  a colored rug, desk lamp, and keyboard. Decorative only. */}
              {(() => { const W = ['mini-window','poster','wall-shelf','pin-note','poster p1','mini-window']; const w = W[i % W.length]; return <div className={w} aria-hidden="true">{w.startsWith('mini-window') ? <span className="sun"/> : null}</div>; })()}
              <div className="room-rug" data-variant={i % 3} aria-hidden="true"/>
              <div className="plant" style={{left: 6}}/>
              <div className="coffee" title={`Refresh ${a.name}'s context`}
                onClick={(e)=>{e.stopPropagation(); onCoffee(a);}} />
              <div className="desk" />
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
                  <Sprite data={a.color} scale={2} className={`bob ${i%2?'slow':'fast'}`}/>
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
const THREADS = [
  { id: 'direct',   label: 'DIRECT',   icon: '📞', desc: 'You & CafresoHQ' },
  { id: 'team',     label: 'TEAM',     icon: '💬', desc: 'Sub-agents talking to each other' },
  { id: 'research', label: 'RESEARCH', icon: '🔬', desc: 'Research mission iterations' },
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

function ChatPanel({ agents, chat, setChat, projects = [], meetings = [], setMeetings, onDelegate, onCeoUsage, onApprovalRequest, onDispatchToAgent, onPinAsTask, onInferTaskAssignment }) {
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [showDelegate, setShowDelegate] = useState(false);
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
     threads) re-engages. Runs after every render so streaming tokens are
     followed too — a single scrollIntoView no-op when not stuck. */
  const stickRef = useRef(true);
  useEffect(() => {
    const el = screenRef.current;
    if (!el) return;
    const onScroll = () => {
      stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    };
    el.addEventListener('scroll', onScroll, { passive: true });
    return () => el.removeEventListener('scroll', onScroll);
  }, []);
  useLayoutEffect(() => { stickRef.current = true; }, [activeThread]);
  useLayoutEffect(() => {
    if (stickRef.current && bottomRef.current)
      bottomRef.current.scrollIntoView({ block: 'end' });
  });

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    /* If the boss is composing inside a project or meeting room, the default
       behavior is "send to everyone in the room" — fan out in parallel,
       both/all replies stream into THIS thread. The boss can still narrow
       the recipient list with explicit @mentions (those are honoured below
       via extractAllMentions and respect the active thread). */
    if (activeRoom && activeRoom.participants.length) {
      // Explicit @mentions inside a room override the default "send to all"
      const explicit = HQ.extractAllMentions(text);
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
        setStreaming(true);
        try {
          await Promise.all(recipients.map(a =>
            onDispatchToAgent(a, body, {
              suppressUserEcho: true,
              threadOverride: activeThread,
              coParticipants: recipients.filter(o => o.id !== a.id).map(o => ({ name: o.name, role: o.role })),
            }).catch(err => {
              setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
                text: `(${a.name} bowed out: ${err && err.message || err})`, thread: activeThread }]);
            })
          ));
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
      setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
        text: `🧠 Brainstorm: "${topic}" — broadcasting to ${agents.length} agent${agents.length === 1 ? '' : 's'}. They will DM each other once and synthesize.`,
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
                text: `(${a.name} bowed out: ${err && err.message || err})`, thread: 'team' }]);
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
    const mentionAll = HQ.extractAllMentions(text);
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
              suppressUserEcho: true,
              threadOverride: targetThread,
              coParticipants: dedup.filter(o => o.id !== a.id).map(o => ({ name: o.name, role: o.role })),
            }).catch(err => {
              setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
                text: `(${a.name} bowed out: ${err && err.message || err})`, thread: targetThread }]);
            })
          ));
        } finally {
          setStreaming(false);
        }
        return;
      }
      // No matches at all — fall through to CEO so they can clarify.
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
      setStreaming(true);
      try {
        await onDispatchToAgent(handoffAgent, text, {
          suppressUserEcho: true,
          threadOverride: activeThread,
        });
      } catch (err) {
        setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
          text: `(${handoffAgent.name} bowed out: ${err && err.message || err})`, thread: activeThread }]);
      } finally {
        setStreaming(false);
      }
      return;
    }

    const userMsg = { id: HQ.uid('m'), from: 'user', name: 'You', text };
    const pendingChat = [...chat, userMsg];
    setChat(pendingChat);
    setStreaming(true);
    const ceoId = HQ.uid('m');
    setChat(prev => [...prev, { id: ceoId, from: 'ceo', name: 'CafresoHQ', text: '', streaming: true }]);
    const controller = new AbortController();
    abortRef.current = controller;
    const flush = HQ.throttleTokens(setChat, ceoId);
    /* Track DMs and handoff that CafresoHQ emits during the stream so the
       host can dispatch to specialists / switch the active responder after
       the orchestrator finishes its turn. */
    const ceoDms = [];
    let ceoHandoff = null;
    const onTool = (ev) => {
      if (ev.phase === 'dm') ceoDms.push({ to: ev.arg, body: ev.body });
      else if (ev.phase === 'handoff') ceoHandoff = { to: ev.arg, body: ev.body };
    };
    try {
      await HQ.ceoStream(text, flush, { chat: pendingChat, agents, signal: controller.signal,
           onUsage: u => onCeoUsage && onCeoUsage(u),
           onTool,
           onHint: flush.note });
      flush.flushNow();
    } catch (err) {
      const stopped = err.name === 'AbortError';
      setChat(prev => prev.map(m => m.id === ceoId
        ? {...m, text: stopped ? (m.text + ' …(stopped)') : `⚠ ${err.message}`, error: !stopped}
        : m));
    }
    abortRef.current = null;
    let finalText = '';
    setChat(prev => {
      const next = prev.map(m => m.id === ceoId ? {...m, streaming: false} : m);
      const ceoMsg = next.find(m => m.id === ceoId);
      finalText = ceoMsg?.text || '';
      return next;
    });
    const approvalDesc = HQ.extractApproval(finalText);
    if (approvalDesc && onApprovalRequest) {
      onApprovalRequest({ title: approvalDesc, by: 'CafresoHQ', kind: 'awaiting stamp' });
    }
    setStreaming(false);

    /* Strip raw routing markers from the rendered CEO bubble so the user sees
       a clean reply, not bracket syntax. The markers were already captured
       above via onTool. */
    if (ceoHandoff || ceoDms.length) {
      setChat(prev => prev.map(m => {
        if (m.id !== ceoId) return m;
        let cleaned = String(m.text || '')
          .replace(/\[\s*HANDOFF_TO\s*:\s*[^\]\n]+\][\s\S]*?\[\s*\/\s*HANDOFF_TO\s*\]/gi, '')
          .replace(/\[\s*DM_TO\s*:\s*[^\]\n]+\][\s\S]*?\[\s*\/\s*DM_TO\s*\]/gi, '');
        cleaned = cleaned.replace(/\n{3,}/g, '\n\n').trim();
        return { ...m, text: cleaned };
      }));
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
          });
        } catch (err) {
          setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
            text: `(${target.name} couldn't take the handoff: ${err && err.message || err})`,
            thread: activeThread }]);
        }
      } else {
        setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
          text: `(CafresoHQ tried to hand off to "${ceoHandoff.to}" but no such teammate is hired)`,
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
            }).catch(err => {
              setChat(prev => [...prev, { id: HQ.uid('m'), from: 'system', name: 'HQ',
                text: `(${t.agent.name} bowed out: ${err && err.message || err})`,
                thread: activeThread }]);
            })
          ));

          /* Synthesis pass — combine specialist outputs into one tight CEO reply.
             Only do this for 2+ specialists (single DMs should have been a
             HANDOFF_TO per the orchestrator prompt). Captures the latest reply
             from each delegated specialist by scanning chat history after the
             fan-out completed. */
          if (targets.length >= 2) {
            let synthChat = [];
            setChat(prev => { synthChat = prev; return prev; });
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
                `\n\nNow synthesize ONE tight combined response for the boss (2-4 sentences). Don't paste the raw outputs — extract what matters, note any disagreement, and cite vault paths if any were saved. Do NOT emit DM_TO or HANDOFF_TO markers in this turn.`;
              const synthId = HQ.uid('m');
              setChat(prev => [...prev, { id: synthId, from: 'ceo', name: 'CafresoHQ', text: '', streaming: true, thread: activeThread }]);
              const synthFlush = HQ.throttleTokens(setChat, synthId);
              try {
                await HQ.ceoStream(synthPrompt, synthFlush, { chat: synthChat, agents, signal: controller.signal,
                     onUsage: u => onCeoUsage && onCeoUsage(u),
                     onHint: synthFlush.note });
                synthFlush.flushNow();
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
  };

  const stop = () => { if (abortRef.current) abortRef.current.abort(); };

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
              <span key={a.id} className="room-chip" title={`${a.role}${a.elevated ? ' · elevated' : ''}`}>
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
            {activeThread === 'team'     && <>No team chatter yet. When sub-agents DM each other (via <code>[DM_TO: name]</code> blocks), the conversations land here so the main thread stays clean.</>}
            {activeThread === 'research' && <>No research yet. Click 🔬 RESEARCH in the topbar to start a long-running research mission. Each iteration's output lands here.</>}
            {activeRoom && activeRoom.kind === 'project' && <>No messages in this project room yet. Type below to message all assigned agents at once, or @-mention a subset.</>}
            {activeRoom && activeRoom.kind === 'meeting' && <>No messages in this meeting yet. Type below to send to all attendees, or @-mention specific people.</>}
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
          const quoteReply = () => {
            const quoted = String(m.text).split('\n').map(l => '> ' + l).join('\n');
            setInput((prev) => (prev ? prev + '\n\n' : '') + quoted + '\n\n');
            if (composerRef.current) composerRef.current.focus();
          };
          const startDM = () => {
            if (m.name && m.from !== 'user') {
              setInput((prev) => (prev ? prev + ' ' : '') + `@${m.name} `);
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
              : (m.name || 'Agent');
          const msgContent = (
            <div key={m.id} className={`msg ${m.from}${m.pinned ? ' pinned' : ''}`}>
              <div className="who" title={_whoLabel}>
                <span className="who-name">{_whoLabel}</span>
                {m.target ? <span className="who-target">→ @{m.target}</span> : null}
                {m.pinned ? <span className="msg-pinned-badge" title="pinned">📌</span> : null}
              </div>
              <div className="bubble">
                <div className="msg-body">
                  <MessageBody text={m.text} />
                  {m.streaming ? <span className="typing"><span/><span/><span/></span> : null}
                </div>
                {!m.streaming && m.text ? (
                  <>
                    {_isMobileChat && (
                      <button className="msg-actions-toggle" onClick={() => setOpenActionsId(prev => prev === m.id ? null : m.id)} title="Actions">{'···'}</button>
                    )}
                    <div className={'msg-actions' + (_isMobileChat && openActionsId === m.id ? ' msg-actions-open' : '')}>
                      <button title="Copy" onClick={() => {
                        try { navigator.clipboard.writeText(m.text); }
                        catch(_e) {}
                        if (window.cafresohqToast) window.cafresohqToast.success('Copied');
                      }}>📋</button>
                      <button title="Quote-reply" onClick={quoteReply}>↩</button>
                      {m.from !== 'user' ? (
                        <>
                          <button title="Re-run this prompt" onClick={() => {
                            const idx = chat.findIndex(x => x.id === m.id);
                            for (let i = idx - 1; i >= 0; i--) {
                              if (chat[i].from === 'user') {
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
          <button className="composer-mini composer-mini--ghost" onClick={()=>setShowDelegate(s=>!s)} title="Hand off to a sub-agent">
            <Ico kind="delegate" size={11}/> Delegate
          </button>
          {streaming
            ? <button className="composer-mini composer-mini--danger" onClick={stop} title="Stop streaming">■ Stop</button>
            : <button className="composer-mini composer-mini--primary" onClick={send} title="Send (Enter)">Send ↵</button>}
        </div>
        <textarea
          ref={composerRef}
          placeholder="Message CafresoHQ… (@ mention · ↵ send · /brainstorm for team)"
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
            {agents.length === 0 && <div className="muted" style={{padding:'6px',fontSize:15}}>No sub-agents yet.</div>}
            {agents.map(a => (
              <div key={a.id} className="item" onClick={()=>{ onDelegate(a); setShowDelegate(false); }}>
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
          {activeThread === 'research' && '🔬 research feed — start or manage missions from the topbar'}
        </div>
      )}
      <div className="thread-tabs">
        {allTabs.map(t => (
          <button key={t.id}
            className={`thread-tab ${activeThread === t.id ? 'active' : ''}${t.kind === 'meeting' ? ' meeting-tab' : ''}${t.kind === 'project' ? ' project-tab' : ''}`}
            onClick={() => setActiveThread(t.id)}
            title={t.desc}>
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
  const copy = () => {
    try { navigator.clipboard.writeText(body); }
    catch (_) {}
    if (window.cafresohqToast) window.cafresohqToast.success('Copied');
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
   sits in the message text). */
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
    ? <img key={'img'+i} src={b.src} alt={b.alt || 'screenshot'} className="msg-image" loading="lazy"/>
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
      <button className="room-invite-btn" onClick={() => setOpen(o => !o)} title="Invite another agent">
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
          {a.elevated && <div className="elevated-badge" title="Computer access (elevated session)">🛡</div>}
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

window.CafresoHQUI = {
  Rail, MobileTabBar, OfficeView, Ticker, ChatPanel, AgentCards, Ico, NAV_ITEMS,
  Btn, Card,
  Field, TextField, TextArea, Select, Checkbox, Toggle, SearchField,
  Tabs, Tab,
  ToastProvider, useToast,
  CommandPaletteProvider, useCommands,
  NotificationBell, NotificationCenter,
  OnboardingTour, OnboardingKeyStep, GettingStarted,
  VocabCtx, getVocab,
  PaletteFab,
};

/* ------------ Inspect / Performance Review panel ------------ */
/* Lightweight server-status fetch — shows the *real* tool/dir allowlist
   for elevated agents. Cached for 30s so reopening the inspector doesn't
   re-poll. The data comes from /codex/status (works whether Codex or
   CafresoHQ is the elevated backend — both share the CAFRESOHQ_ALLOWED_*
   env vars). */
const _elevatedStatusCache = { at: 0, data: null };
function ElevatedToolkit() {
  const [status, setStatus] = useState(null);
  useEffect(() => {
    let cancelled = false;
    const now = Date.now();
    if (_elevatedStatusCache.data && (now - _elevatedStatusCache.at) < 30000) {
      setStatus(_elevatedStatusCache.data);
      return;
    }
    fetch('/codex/status')
      .then(r => r.ok ? r.json() : null)
      .then(j => {
        if (cancelled) return;
        _elevatedStatusCache.at = Date.now();
        _elevatedStatusCache.data = j;
        setStatus(j);
      })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);
  if (!status) return null;
  const tools = (status.allowedTools || []);
  const dirs = (status.allowedDirs || []);
  return (
    <div className="elevated-toolkit">
      <div className="elevated-toolkit-row">
        <span className="elevated-toolkit-label">TOOLS</span>
        <div className="elevated-toolkit-pills">
          {tools.length === 0
            ? <span className="elevated-toolkit-empty">none</span>
            : tools.map(t => <span key={t} className="elevated-toolkit-pill">{t}</span>)}
        </div>
      </div>
      <div className="elevated-toolkit-row">
        <span className="elevated-toolkit-label">DIRS</span>
        <div className="elevated-toolkit-dirs">
          {dirs.length === 0
            ? <span className="elevated-toolkit-empty">none configured</span>
            : dirs.map(d => <code key={d} className="elevated-toolkit-dir" title={d}>{d.split(/[\\/]/).pop()}</code>)}
        </div>
      </div>
    </div>
  );
}

const INSPECT_ACT_ICON = {
  hired: '✦', assigned: '📋', dm: '✉', tool: '⚙', progress: '…',
  done: '✓', failed: '⚠', attention: '⚠', coffee: '☕', meeting: '👥', vault: '✎',
};
function InspectPanel({ agent, activity = [], onClose, onUpdate, onDismiss, onMessage }) {
  if (!agent) return null;
  /* Live activity for THIS agent, straight from the canonical log — replaces
     the old static `agent.recent` string with what the agent actually did. */
  const mine = React.useMemo(
    () => (activity || []).filter(e => e.agentId === agent.id).slice(0, 8),
    [activity, agent.id]);
  const ago = (ts) => {
    const dt = Date.now() - (ts || 0);
    if (dt < 60_000) return Math.max(0, Math.floor(dt / 1000)) + 's';
    if (dt < 3_600_000) return Math.floor(dt / 60_000) + 'm';
    if (dt < 86_400_000) return Math.floor(dt / 3_600_000) + 'h';
    return Math.floor(dt / 86_400_000) + 'd';
  };
  return (
    <div className="inspect">
      <div className="head">
        <div>
          <div className="title">{agent.name.toUpperCase()}</div>
          <div className="sub">Performance review</div>
        </div>
        <button className="px-btn ghost" style={{color:'#fff8ee',borderColor:'#fff8ee',fontSize:8}} onClick={onClose}>✕</button>
      </div>
      <div className="body">
        <div style={{display:'flex',alignItems:'center',gap:10}}>
          <Sprite data={agent.color} scale={2}/>
          <div style={{flex:1}}>
            <div style={{fontFamily:'Press Start 2P',fontSize:10}}>{agent.elevated ? '🛡 ' : ''}{agent.name}</div>
            <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)'}}>{agent.role}</div>
          </div>
          <div className={`mood ${agent.mood||'idle'}`} style={{position:'static'}}>{(agent.mood||'idle')[0].toUpperCase()}</div>
        </div>
        {agent.elevated && (
          <div className="elevated-banner">
            🛡 <b>ELEVATED</b> — backed by a CafresoHQ / Codex session with computer access. Every tool call is logged to Receipts.
            <ElevatedToolkit />
          </div>
        )}
        <div className="stat"><span className="lbl">Tokens (session)</span><span>{agent.tokens?.toLocaleString() || '0'}</span></div>
        <div className="stat"><span className="lbl">Cost</span><span>${((agent.tokens||0)*0.0000015).toFixed(4)}</span></div>
        <div className="stat"><span className="lbl">Tasks done</span><span>{agent.tasksDone || 0}</span></div>
        <div className="stat"><span className="lbl">Model</span><span>{agent.model}</span></div>
        <div>
          <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)',marginBottom:5}}>Tools used</div>
          <div className="tools-used">
            {(agent.tools||[]).map(t => <span key={t}>{t.toUpperCase()}</span>)}
          </div>
        </div>
        <div>
          <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)',marginBottom:5}}>Live activity</div>
          {mine.length > 0 ? (
            <div className="inspect-activity">
              {mine.map(e => (
                <div key={e.id} className={'ia-row' + (e.priority === 'attention' ? ' is-attn' : '')}>
                  <span className="ia-icon" aria-hidden="true">{INSPECT_ACT_ICON[e.action] || '✦'}</span>
                  <span className="ia-text">{e.text}</span>
                  <span className="ia-ago">{ago(e.ts)}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="recent">
              {agent.recent || 'No activity logged yet. Drag a task onto this desk or message the team.'}
            </div>
          )}
        </div>
        {agent.journal && agent.journal.length > 0 && (
          <div>
            <div style={{fontFamily:'Inter',fontSize:10,textTransform:'uppercase',letterSpacing:'0.1em',color:'var(--ink-2)',marginBottom:5}}>Work journal · last {Math.min(8, agent.journal.length)}</div>
            <div className="journal">
              {agent.journal.slice(0, 8).map((e, i) => (
                <div key={i} className="jrow">
                  <span className="jdate">{e.date || new Date(e.at||0).toISOString().slice(0,10)}</span>
                  <span className="jsum">{e.summary}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div style={{display:'flex',gap:6,marginTop:4}}>
          {onMessage && <button className="px-btn primary" style={{fontSize:8,flex:1}} onClick={()=>onMessage(agent)}>💬 MESSAGE</button>}
          <button className="px-btn secondary" style={{fontSize:8,flex:1}} onClick={()=>onUpdate(agent.id, { tokens: 0, recent: 'context cleared ☕' })}>☕ REFRESH CTX</button>
          <button className="px-btn danger" style={{fontSize:8}} onClick={()=>{onDismiss(agent.id); onClose();}}>LET GO</button>
        </div>
      </div>
    </div>
  );
}

/* ------------ Token HUD (persistent) ------------ */
function TokenHUD({ tokens, budget=1000000, className='' }) {
  const pct = Math.min(100, (tokens/budget)*100);
  return (
    <div className={`token-hud${className ? ' '+className : ''}`} title={`${tokens.toLocaleString()} tokens · $${(tokens*0.0000015).toFixed(2)} est.`}>
      <span>⛽</span>
      <span>{(tokens/1000).toFixed(1)}K</span>
      <div className="bar"><div className="fill" style={{width: pct+'%'}}/></div>
      <span>${(tokens*0.0000015).toFixed(2)}</span>
    </div>
  );
}

/* ------------ Shortcut HUD ------------ */
function ShortcutHud({ open, setOpen }) {
  return (
    <div className="shortcut-hud">
      {open && (
        <div className="shortcut-panel">
          <h5>⌨ SHORTCUTS</h5>
          <div className="kbrow">
            <kbd>⌘K</kbd><span>Toggle shortcuts</span>
            <kbd>H</kbd><span>Hire sub-agent</span>
            <kbd>S</kbd><span>Open settings</span>
            <kbd>M</kbd><span>Memory shelf</span>
            <kbd>N</kbd><span>Add sticky note</span>
            <kbd>U</kbd><span>End-of-day stand-up</span>
            <kbd>F</kbd><span>1:1 with CafresoHQ</span>
            <kbd>D</kbd><span>Day / night</span>
            <kbd>/</kbd><span>Focus chat</span>
          </div>
        </div>
      )}
      <div className="floppy-btn" title="Keyboard shortcuts" onClick={()=>setOpen(!open)}/>
    </div>
  );
}

/* ------------ Toast ------------ */
function Toast({ msg }) {
  if (!msg) return null;
  return <div className="toast"><span className="kw">{msg.kind || 'HQ'}</span><span>{msg.text}</span></div>;
}

/* ──────────────────────────────────────────────────────────────────────
   CEOPanel — modal that opens when the user clicks the CafresoHQ-CEO
   sidebar card. Shows a mini diorama of the CEO office (with a live
   Pac-Man cabinet) plus quick-action buttons (Settings, Sit 1:1,
   Memory, Meeting, Workspaces). Pattern mirrors InspectPanel but with a
   dedicated layout because the orchestrator's view is richer than a
   sub-agent's stat sheet.
   ──────────────────────────────────────────────────────────────────── */
function CEOPanel({ open, onClose, onOpenSettings, onSitWithCEO, onOpenMemory, onOpenMeeting }) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;
  const fire = (fn) => () => { if (typeof fn === 'function') fn(); onClose(); };
  return (
    <div className="ceo-panel-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label="CafresoHQ-CEO panel">
      <div className="ceo-panel" onClick={(e) => e.stopPropagation()}>
        <header className="ceo-panel-head">
          <div className="ceo-panel-identity">
            <Sprite data={SPRITES.cafresohq} scale={2}/>
            <div>
              <div className="ceo-panel-title">CafresoHQ-CEO</div>
              <div className="ceo-panel-sub">Orchestrator · Cafreso HQ</div>
            </div>
          </div>
          <button className="ceo-panel-close" onClick={onClose} aria-label="Close">✕</button>
        </header>
        {/* The .office wrapper scopes pixel-art rendering + Press Start 2P
            font so the mini diorama looks the same as the Office tab. */}
        <div className="ceo-panel-stage office">
          <div className="ceo-panel-room">
            <div className="interior">
              {/* Office furnishings — run first so they sit behind the
                  interactive pieces (corkboard, arcade, desk, etc.). */}
              <div className="ceo-ceiling-light" aria-hidden="true"/>
              <div className="office-carpet" aria-hidden="true"/>
              <div className="wall-photo" title="Cafreso skyline" aria-hidden="true"/>
              <div className="corkboard">📌 pin memory or receipts here</div>
              <div className="window">
                <div className="sun"/>
                <div className="cloud cloud-a"/>
                <div className="cloud cloud-b"/>
              </div>
              <div className="wall-clock" title="Wall clock">
                <span className="wc-hand wc-hour"/>
                <span className="wc-hand wc-min"/>
                <span className="wc-pin"/>
              </div>
              <div className="whiteboard" title="Strategy whiteboard">
                <span className="wb-line">Q3 — SHIP HQ</span>
                <span className="wb-line wb-r">★ ECOSYSTEM</span>
                <span className="wb-line">DAO · CHAIN · AI</span>
              </div>
              <div className="bookshelf" title="Quarterly binders" aria-hidden="true">
                <div className="shelf"><i className="book b1"/><i className="book b2"/><i className="book b3"/><i className="book b4"/><i className="book b5"/></div>
                <div className="shelf"><i className="book b3"/><i className="book b1"/><i className="book b5"/><i className="book b2"/></div>
                <div className="shelf"><i className="book b4"/><i className="book b3"/><i className="book b1"/></div>
              </div>
              <div className="plant"/>
              <div className="coffee-mug" aria-hidden="true"><span className="cm-steam"/></div>
              <div className="desk-keyboard" aria-hidden="true"/>
              <div className="desk-mouse" aria-hidden="true"/>
              <div className="desk-phone" title="Desk phone" aria-hidden="true"/>
              <div className="trash-bin" title="Trash" aria-hidden="true"/>
              <a className="arcade clickable"
                 href="https://ai.cafreso.com/workspaces"
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
              <div className="filing clickable" title="Memory shelf"
                   onClick={fire(onOpenMemory)}>
                <span/><span/><span/>
              </div>
              <div className="guest-chair" title="Sit 1:1 with the CEO"
                   onClick={fire(onSitWithCEO)}/>
              <div className="meeting-door" title="Meeting room"
                   onClick={fire(onOpenMeeting)}/>
              <div className="desk"/>
              <div className="office-chair" aria-hidden="true"/>
              <div className="sprite-slot">
                <Sprite data={SPRITES.cafresohq} scale={1}/>
              </div>
            </div>
          </div>
        </div>
        <div className="ceo-panel-actions">
          <button className="ceo-panel-action" onClick={fire(onOpenSettings)}>
            <span className="ceo-panel-icon"><Ico kind="settings" size={16}/></span>
            <span>Settings</span>
          </button>
          <button className="ceo-panel-action" onClick={fire(onSitWithCEO)}>
            <span className="ceo-panel-icon" aria-hidden="true">☕</span>
            <span>Sit 1:1</span>
          </button>
          <button className="ceo-panel-action" onClick={fire(onOpenMemory)}>
            <span className="ceo-panel-icon" aria-hidden="true">🗂</span>
            <span>Memory</span>
          </button>
          <button className="ceo-panel-action" onClick={fire(onOpenMeeting)}>
            <span className="ceo-panel-icon" aria-hidden="true">🚪</span>
            <span>Meeting</span>
          </button>
          <a className="ceo-panel-action ceo-panel-action--workspaces"
             href="https://ai.cafreso.com/workspaces"
             onClick={onClose}>
            <span className="ceo-panel-icon" aria-hidden="true">🕹</span>
            <span>Workspaces</span>
          </a>
        </div>
      </div>
    </div>
  );
}

window.CafresoHQUI.CEOPanel = CEOPanel;
window.CafresoHQUI.InspectPanel = InspectPanel;
window.CafresoHQUI.TokenHUD = TokenHUD;
window.CafresoHQUI.ShortcutHud = ShortcutHud;
window.CafresoHQUI.Toast = Toast;
