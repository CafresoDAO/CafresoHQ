import { CafresoHQClient } from '../claude-client.jsx';
/* ==========================================================================
   CafresoHQ — modals (Hire / Settings)
   ========================================================================== */

const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;

/* Single source of truth for settings — subscribes to the client's pub/sub so
   any component using this hook re-renders whenever setSettings() is called,
   even from a different component tree. */
function useSettingsStore() {
  const [s, setS] = useStateM(() => CafresoHQClient.getSettings());
  useEffectM(() => {
    return CafresoHQClient.onSettingsChange(fresh => setS({ ...fresh }));
  }, []);
  return [s, patch => CafresoHQClient.setSettings(patch)];
}

/* Live model picker — loads all providers from localModelOptions(), which now
   has per-fetch AbortController timeouts on slow local services (LM Studio,
   Ollama) so it resolves quickly. Falls back to static lists only if the
   whole function rejects (shouldn't happen in normal use). */
function ModelPicker({ value, onChange, refreshKey }) {
  const [groups, setGroups] = useStateM([]);
  const [loading, setLoading] = useStateM(true);
  const [error, setError] = useStateM(false);
  /* `refreshKey` is a prop, and NONE of ModelPicker's three call sites
     (hire, providers, settings) passes it — so it is permanently undefined
     and this effect could only ever run once. The refresh affordance existed
     in the code and could never fire. An internal nonce so the picker owns
     its own retry rather than depending on a caller that does not cooperate. */
  const [retryNonce, setRetryNonce] = useStateM(0);
  useEffectM(() => {
    let live = true;
    setLoading(true);
    setError(false);
    CafresoHQClient.localModelOptions()
      .then(g => {
        if (!live) return;
        setGroups(g);
        setLoading(false);
      })
      .catch(() => {
        if (!live) return;
        /* Last-resort fallback — all static model lists so the picker
           is never blank. Static lists only. */
        const s = CafresoHQClient.getSettings();
        /* Same ordering rule as the live list (§3.3: "the default backend
           is whatever the user ALREADY HAS"): anything that might already
           be on their machine first, the buy-a-key services after. This
           list is a SECOND place the order is decided, and it used to
           disagree with the first — Anthropic, then Google, then Codex —
           so the principle held right up until the proxy went down, which
           is exactly when a boss is least in the mood to be sold
           something. Static lists only; nothing here is detected, so the
           CLI goes first on the chance that it is there. */
        const fallback = [
          { label: 'Codex CLI', provider: 'codex',
            options: CafresoHQClient.CODEX_MODELS.map(m => ({ id: 'codex:' + m, label: m })) },
          { label: 'Anthropic (Claude API)', provider: 'anthropic',
            options: CafresoHQClient.ANTHROPIC_MODELS.map(m => ({ id: 'anthropic:' + m, label: m })) },
          { label: 'Google (Gemini API)', provider: 'google',
            options: CafresoHQClient.GEMINI_MODELS.map(m => ({ id: 'google:' + m, label: m })) },
        ];
        setGroups(fallback);
        setLoading(false);
        setError(true);
      });
    return () => { live = false; };
  }, [refreshKey, retryNonce]);

  const flat = groups.flatMap(g => g.options);
  const known = flat.some(o => o.id === value);
  /* The fallback is a SUBSTITUTION, and it used to be announced only in a
     `title` tooltip — which does not exist on touch and which almost nobody
     hovers. What actually happened: detection failed, so the list stopped
     being "what you already have" (§3.3) and became a static guess that
     omits the boss's own running Ollama, while looking exactly like a
     detected list. A picker quietly showing a different set of options than
     it claims to is the same fault as a verdict about a graph with no shape.
     Said out loud now, with the way back next to it. */
  return (
    <>
      <select value={known ? value : ''} onChange={e => onChange(e.target.value)}>
        {!known && <option value="">{loading ? 'loading…' : (value || '— pick a model —')}</option>}
        {groups.map(g => (
          <optgroup key={g.provider} label={g.label}>
            {g.options.map(o => <option key={o.id} value={o.id}>{o.label}</option>)}
          </optgroup>
        ))}
      </select>
      {error && (
        <div className="tiny" style={{ color: '#c44', display: 'flex', flexWrap: 'wrap',
                                       alignItems: 'center', gap: 6, marginTop: 4 }}>
          <span>Couldn’t check this machine, so this is a standard list — anything
                you already run may be missing from it.</span>
          <button type="button" className="px-btn" style={{ fontSize: 8, padding: '4px 7px' }}
            disabled={loading} onClick={() => setRetryNonce(n => n + 1)}>
            {loading ? 'CHECKING…' : '↻ CHECK AGAIN'}
          </button>
        </div>
      )}
    </>
  );
}

const TEMPLATES_KEY = 'cafresohq_hire_templates_v1';
function loadTemplates() {
  try { return JSON.parse(localStorage.getItem(TEMPLATES_KEY) || '[]'); }
  catch (_e) { return []; }
}
function saveTemplates(ts) {
  try { localStorage.setItem(TEMPLATES_KEY, JSON.stringify(ts)); }
  catch (err) {
    console.warn('[cafresohq] saveTemplates failed:', err);
    try { window.dispatchEvent(new CustomEvent('cafresohq:storage-error', { detail: { key: TEMPLATES_KEY, error: err } })); } catch (_e) {}
  }
}

/* ─────────────────────────────────────────────────────────────────────
   <Modal>
   Reusable shell for every dialog in the app. Provides:
     · Backdrop with click-to-close
     · Esc to close (skips when typing in inputs/textareas)
     · Focus trap — first focusable element auto-focused; Tab/Shift-Tab
       cycle within the modal; focus returns to the trigger on close
     · Scroll lock on <body>
     · Animated entry/exit using motion tokens
     · Header with title/subtitle + optional `headerActions` slot
     · Body and optional `footer` slots
     · `size` controls width: sm/md/lg/xl/fullscreen

   Migration note: existing modals can keep their .modal-head and .modal-body
   CSS classes — we render with `data-modal-shell` so old per-modal styles still
   apply, but the new shell handles a11y and motion uniformly.

   Props:
     open         (bool)              — render or null
     onClose      (fn)                 — invoked by ✕ / Esc / backdrop
     title        (node)               — main heading
     subtitle     (node, optional)     — kicker line below title
     headerActions (node, optional)    — extra buttons in the header right side
     footer       (node, optional)     — sticky footer area below body
     size         (str, default 'md')  — 'sm' | 'md' | 'lg' | 'xl' | 'fullscreen'
     dismissable  (bool, default true) — set false to prevent backdrop/Esc close
     children     (node)               — body content
   ───────────────────────────────────────────────────────────────────── */
const MODAL_SIZE_MAX_WIDTH = { sm: 420, md: 560, lg: 760, xl: 980, fullscreen: '100vw' };

function Modal({ open, onClose, title, subtitle, headerActions, footer, size = 'md', dismissable = true, children }) {
  const dialogRef = useRefM(null);
  const triggerRef = useRefM(null);
  /* True only while a mouse press that STARTED on the backdrop is in flight.
     Guards against drag-select closes: selecting text in the modal and
     releasing over the backdrop fires a click on the backdrop, which used to
     dismiss the modal and eat the draft. */
  const backdropPressRef = useRefM(false);
  const [entered, setEntered] = useStateM(false);

  /* Capture the focused element when opening so we can restore on close. */
  useEffectM(() => {
    if (open) {
      triggerRef.current = document.activeElement;
      // animate in next frame
      requestAnimationFrame(() => setEntered(true));
    } else {
      setEntered(false);
      // restore focus to whatever opened us
      if (triggerRef.current && typeof triggerRef.current.focus === 'function') {
        triggerRef.current.focus();
      }
      triggerRef.current = null;
    }
  }, [open]);

  /* Body scroll lock while open. */
  useEffectM(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  /* Esc to close + focus trap. */
  useEffectM(() => {
    if (!open) return;
    const node = dialogRef.current;
    if (!node) return;

    /* Auto-focus the first focusable thing in the dialog. */
    const focusables = () => Array.from(node.querySelectorAll(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]):not([type=hidden]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(el => el.offsetParent !== null || el === document.activeElement);

    const firstFocus = setTimeout(() => {
      const list = focusables();
      if (list.length) list[0].focus();
      else node.focus();
    }, 30);

    const onKey = (e) => {
      if (e.key === 'Escape' && dismissable) {
        /* The contract at the top of this component — "skips when typing in
           inputs/textareas" — was documented and never implemented: Escape
           closed unconditionally, so a boss half-way through a JOB
           DESCRIPTION who pressed Esc (IME cancel, autocomplete dismiss,
           muscle memory) lost the whole draft with no confirm and no way
           back. Only text-entry targets are skipped: a checkbox, radio,
           range or button is not "typing", and Esc from those still closes. */
        const t = e.target;
        const typing = !!t && (
          t.tagName === 'TEXTAREA' ||
          t.isContentEditable === true ||
          (t.tagName === 'INPUT' &&
           !/^(checkbox|radio|range|button|submit|reset|file|color)$/i.test(t.type || 'text')));
        if (typing) return;
        e.stopPropagation();
        onClose && onClose();
        return;
      }
      if (e.key === 'Tab') {
        const list = focusables();
        if (list.length === 0) { e.preventDefault(); node.focus(); return; }
        const first = list[0];
        const last  = list[list.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault(); last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault(); first.focus();
        }
      }
    };
    node.addEventListener('keydown', onKey);
    return () => {
      clearTimeout(firstFocus);
      node.removeEventListener('keydown', onKey);
    };
  }, [open, dismissable]);

  if (!open) return null;

  const maxW = MODAL_SIZE_MAX_WIDTH[size] || MODAL_SIZE_MAX_WIDTH.md;
  const isFull = size === 'fullscreen';

  return (
    <div
      className="backdrop"
      data-modal-shell
      onMouseDown={(e) => { backdropPressRef.current = e.target === e.currentTarget; }}
      onMouseUp={(e) => {
        const started = backdropPressRef.current;
        backdropPressRef.current = false;
        if (started && e.target === e.currentTarget && dismissable && onClose) onClose();
      }}
      style={{
        zIndex: 'var(--z-modal)',
        opacity: entered ? 1 : 0,
        transition: 'opacity var(--motion-base) var(--ease-out)',
      }}
    >
      <div
        className="modal"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? 'oc-modal-title' : undefined}
        tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: isFull ? '100vw' : (typeof maxW === 'number' ? maxW + 'px' : maxW),
          width:    isFull ? '100vw' : 'min(94vw, ' + (typeof maxW === 'number' ? maxW + 'px' : maxW) + ')',
          height:   isFull ? '100vh' : undefined,
          maxHeight: isFull ? '100vh' : '90vh',
          transform: entered ? 'translateY(0) scale(1)' : 'translateY(8px) scale(0.985)',
          transition: 'transform var(--motion-base) var(--ease-out)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {(title || subtitle || headerActions) && (
          <div className="modal-head">
            <div>
              {title && <div className="title" id="oc-modal-title">{title}</div>}
              {subtitle && <div className="sub">{subtitle}</div>}
            </div>
            <div style={{display: 'flex', gap: 'var(--sp-3)', alignItems: 'center'}}>
              {headerActions}
              {dismissable && (
                <button
                  className="px-btn ghost"
                  onClick={() => onClose && onClose()}
                  style={{color: '#fff8ee', borderColor: '#fff8ee'}}
                  aria-label="Close dialog"
                  title="Close (Esc)"
                >CLOSE ✕</button>
              )}
            </div>
          </div>
        )}
        <div className="modal-body" style={{flex: 1, minHeight: 0}}>
          {children}
        </div>
        {footer && (
          <div className="modal-foot" style={{
            padding: 'var(--sp-4) var(--sp-6)',
            borderTop: '1px solid var(--rule)',
            background: 'var(--paper-2)',
            display: 'flex',
            gap: 'var(--sp-3)',
            justifyContent: 'flex-end',
            flexShrink: 0,
          }}>{footer}</div>
        )}
      </div>
    </div>
  );
}


export { Modal, ModelPicker, loadTemplates, saveTemplates, useSettingsStore };
