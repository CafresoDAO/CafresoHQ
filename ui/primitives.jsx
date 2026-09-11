import { Tab } from './office.jsx';
/* ==========================================================================
   CafresoHQ — main app components (chat, office, cards, modals)
   ========================================================================== */

const { useState, useEffect, useLayoutEffect, useRef, useMemo, createContext, useContext } = React;

/* ------------ Theme vocabulary system ------------ */
const THEME_VOCAB = {
  default:      { agent: 'Agent',   agents: 'Agents',   office: 'Office',        corner: 'CEO',           hire: 'HIRE',     vacant: 'VACANT', live: 'LIVE',     hireTitle: 'Hire a coworker' },
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
  /* The hiring hall: a hall with a roof and two doors — the room you walk
     into to hire from the network (views/market.jsx). */
  if (kind === 'market') return (<svg {...common}><polygon points="2,7 8,2 14,7" fill={K}/><rect x="3" y="7" width="10" height="7" fill="none" stroke={K} strokeWidth="2"/><rect x="5" y="9" width="2" height="5" fill={K}/><rect x="9" y="9" width="2" height="5" fill={K}/></svg>);
  return null;
}

/* ------------ Sidebar rail ------------ */
const NAV_ITEMS = [
  ['visual', 'Office'],
  ['tasks', 'Tasks'],
  ['calendar', 'Calendar'],
  ['memory', 'Memory'],
  ['vault', 'Library'],
  ['team', 'Team'],
  ['terminal', 'Terminal'],
  /* One destination had two names. The mobile tab bar, the command
     palette's own `nav.projects` entry, and the onboarding step all say
     "Projects"; this rail and the palette's view-switch list said
     "Workspace" — and `commands.jsx` managed both, for the same id, sixty
     lines apart.

     Worse, "Workspace" is ALSO one of the two layout modes INSIDE this
     view ("Workspace | Classic"), so a desktop boss clicked Workspace and
     landed somewhere offering to switch them to Workspace.

     Settled on Projects: it matches the majority of surfaces, it is what
     the onboarding tells a new boss they are making, and it frees
     "Workspace" to mean the one thing it already names in there. */
  ['projects', 'Projects'],
  /* The hiring hall — "Network" on the rail because that is what a boss
     is reaching for (a coworker from the network); the room's own sign
     says HIRING HALL (VIEW_LABELS). views/market.jsx. */
  ['market', 'Network'],
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

export { Btn, Card, Checkbox, Field, Ico, NAV_ITEMS, SearchField, Select, Tabs, TextArea, TextField, ToastCtx, Toggle, VocabCtx, getVocab, useVocab };
