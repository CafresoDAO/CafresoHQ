import { CafresoHQChain } from '../claude-client.jsx';
import { useStoredV } from './core.jsx';
import { CafresoHQClient } from '../claude-client.jsx';
const { useState: useSV, useMemo: useMV, useRef: useRV } = React;
function EmbeddedTerminal({ project, cli, sessionId, visible }) {
  const containerRef = React.useRef(null);
  const termRef      = React.useRef(null);
  const wsRef        = React.useRef(null);
  const fitRef       = React.useRef(null);

  /* Copy/paste + URL capture. The CLIs (claude/codex/gemini login) print OAuth
     URLs the user must open in a browser — before this, nothing in the PTY was
     copyable, which blocked authenticating AI subscriptions entirely. */
  const [lastUrl, setLastUrl] = React.useState('');
  const [flash, setFlash]     = React.useState('');
  const flashTimer = React.useRef(null);
  const doFlash = (msg) => {
    setFlash(msg);
    clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlash(''), 2200);
  };
  const copyText = async (text) => {
    try { await navigator.clipboard.writeText(text); doFlash('✓ copied'); }
    catch (_e) { doFlash('copy blocked — check browser permission'); }
  };
  const copySelectionOrUrl = () => {
    const sel = termRef.current && termRef.current.getSelection();
    if (sel && sel.trim()) return copyText(sel.trim());
    if (lastUrl) return copyText(lastUrl);
    doFlash('select text first');
  };
  const pasteClipboard = async () => {
    try {
      const t = await navigator.clipboard.readText();
      if (t && wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(t); doFlash('✓ pasted');
      } else if (!t) doFlash('clipboard is empty');
      else doFlash('terminal not connected');
    } catch (_e) { doFlash('paste blocked — use Ctrl+V or grant clipboard access'); }
  };

  React.useEffect(() => {
    if (!containerRef.current || !project?.path) return;
    const TermClass = window.Terminal;
    const FitClass  = window.FitAddon?.FitAddon ?? window.FitAddon;
    if (!TermClass || !FitClass) {
      containerRef.current.textContent = 'xterm.js not loaded';
      return;
    }

    const term = new TermClass({
      theme: {
        background: '#0c0c14', foreground: '#d4d8e8',
        cursor: '#7c6bff', cursorAccent: '#0c0c14',
        selectionBackground: 'rgba(124,107,255,0.25)',
        black: '#0c0c14', brightBlack: '#3a3555',
      },
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      fontSize: 13, lineHeight: 1.4,
      cursorBlink: true, scrollback: 5000,
    });
    const fit = new FitClass();
    term.loadAddon(fit);
    term.open(containerRef.current);
    termRef.current = term;
    fitRef.current  = fit;

    let cancelled = false;
    let urlTail = '';   // rolling output tail for login-URL capture

    // Registered once — always routes input to the current ws.
    term.onData(data => {
      if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(data);
    });

    // Ctrl/Cmd+C copies when text is selected (and does NOT send SIGINT over a
    // selection); Ctrl+Shift+C always copies. Ctrl+V is deliberately left to the
    // browser's native paste path — xterm's hidden textarea routes it through
    // onData, and that works in every browser (clipboard.readText does not).
    term.attachCustomKeyEventHandler((ev) => {
      if (ev.type !== 'keydown') return true;
      const key = (ev.key || '').toLowerCase();
      if (key === 'c' && (ev.ctrlKey || ev.metaKey) &&
          (ev.shiftKey || term.hasSelection())) {
        const sel = term.getSelection();
        if (sel && sel.trim()) {
          copyText(sel.trim());
          term.clearSelection();
          return false;
        }
      }
      return true;
    });

    // Terminal convention: releasing a mouse selection copies it. This is the
    // one-gesture path for grabbing an OAuth URL off the screen.
    const onMouseUp = () => {
      const sel = term.getSelection();
      if (sel && sel.trim()) copyText(sel.trim());
    };
    containerRef.current.addEventListener('mouseup', onMouseUp);

    /* Reconnect backoff. This was a flat setTimeout(connect, 2000) with no
       cap and no ceiling: with the terminal service genuinely down, an open
       Terminal retried 30 times a minute forever and wrote "[reconnecting…]"
       into the pane on every single attempt, so the transcript filled with
       one repeated line and the boss was never told it had settled into a
       state rather than being about to succeed.

       Backoff to a 30s ceiling instead, and say so ONCE. A service that
       comes back (serve.py restarting, which is the common case) is still
       picked up within half a minute; a service that is not coming back
       stops shouting about it. */
    let attempt = 0;
    const RETRY_MS = [2000, 4000, 8000, 15000, 30000];
    const nextDelay = () => RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)];

    /* connect() is async — the readyState guard below runs BEFORE the nonce
       fetch, and wsRef only becomes CONNECTING after it. So two overlapping
       calls (the onclose retry timer + the visibilitychange handler are
       independent triggers) could both pass the guard during that await and
       open TWO sockets for one session_id. The server hands the PTY to
       whichever attaches last, while wsRef keeps whichever connect() resumed
       last — when they disagree, keystrokes and output ride different
       sockets, and after the next drop the client refuses to reconnect
       because the orphan still reads OPEN: a silently frozen terminal.
       A synchronous in-flight flag closes the gap. */
    let connecting = false;

    const connect = async () => {
      if (cancelled || connecting) return;
      // Skip if already open or mid-handshake.
      const rs = wsRef.current?.readyState;
      if (rs === WebSocket.OPEN || rs === WebSocket.CONNECTING) return;
      connecting = true;
      term.writeln('\x1b[2m[connecting…]\x1b[0m');

      // Fetch nonce — /terminal/nonce is same-origin-only so cross-origin
      // pages can't obtain it and therefore can't open a PTY.
      let ptyNonce = '';
      try {
        const _nr = await fetch((window._API_BASE || '') + '/terminal/nonce');
        if (_nr.ok) { const _nd = await _nr.json(); ptyNonce = _nd.nonce || ''; }
      } catch (_) {}

      if (cancelled) { connecting = false; return; }

      // Target the BACKEND base (window._API_BASE = the gateway when the UI is
      // served cross-origin from the asset canister), NOT the page origin — an
      // ICP asset canister can't serve WebSockets, so the PTY socket must go to
      // the gateway. Falls back to same-origin when _API_BASE is empty (local).
      let _wsBase;
      try { _wsBase = new URL((window._API_BASE || '/').replace(/\/?$/, '/'), window.location.href); }
      catch (_) { _wsBase = new URL('/', window.location.href); }
      const _wsProto = _wsBase.protocol === 'https:' ? 'wss:' : 'ws:';
      const _wsHost  = _wsBase.host;
      const _wsPath  = _wsBase.pathname.replace(/\/$/, '');   // strip trailing slash
      const _wsParams = new URLSearchParams({
        cli, cwd: project.path,
        cols: String(term.cols), rows: String(term.rows),
        ...(sessionId ? { session_id: sessionId } : {}),
      }).toString() + (ptyNonce ? `&nonce=${encodeURIComponent(ptyNonce)}` : '');

      const ws = new WebSocket(`${_wsProto}//${_wsHost}${_wsPath}/terminal/pty?${_wsParams}`);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;
      connecting = false;   // wsRef is CONNECTING now — the readyState guard takes over

      // Always send init frame immediately on open — even with no BYOK keys.
      // The server waits up to 2 s for this frame before spawning the PTY;
      // sending it right away eliminates the 2-second blank-screen delay.
      ws.onopen = async () => {
        attempt = 0;                       // connected — start the ladder over
        const oc = CafresoHQClient;
        let ak = '', ok = '', gk = '';
        if (oc?.getAgentKey) {
          ak = await oc.getAgentKey('anthropic').catch(() => '');
          ok = await oc.getAgentKey('openai').catch(() => '');
          gk = await oc.getAgentKey('google').catch(() => '');   // Gemini CLI
        }
        ws.send(JSON.stringify({
          type: 'init',
          ...(ak ? { anthropic_key: ak } : {}),
          ...(ok ? { openai_key:    ok } : {}),
          ...(gk ? { gemini_key:    gk } : {}),
        }));
      };

      ws.onmessage = e => {
        const data = e.data instanceof ArrayBuffer
          ? new TextDecoder().decode(e.data) : e.data;
        term.write(data);
        // Capture the most recent URL from the raw PTY stream (login flows
        // print OAuth URLs the user must open in a browser). Keep a rolling
        // tail so URLs split across frames still match; strip ANSI first —
        // OSC-8 hyperlinks keep their target, colors/cursor codes drop.
        urlTail = (urlTail + data).slice(-6000);
        const clean = urlTail
          .replace(/\x1b\]8;;([^\x07\x1b]*)(?:\x07|\x1b\\)/g, ' $1 ')
          .replace(/\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)/g, ' ')
          .replace(/\x1b\[[0-9;?]*[A-Za-z]/g, '')
          .replace(/[\r\x07]/g, '\n');
        const m = clean.match(/https?:\/\/[^\s'"<>\x00-\x1f)\]]+/g);
        if (m && m.length) {
          const u = m[m.length - 1].replace(/[.,;:!?]+$/, '');
          if (u.length > 12) setLastUrl(u);
        }
      };

      ws.onerror = () => {
        /* Was "[connection error — is serve.py running?]" — an internal
           filename on a user surface (§6), and pointing at the one thing
           that cannot be the cause: this page was served BY serve.py, so
           if it weren't running there'd be nothing to read the message on.
           What actually failed is the terminal's own socket. Say that, and
           say what happens next — the onclose handler below is already
           retrying, so the boss doesn't have to do anything. */
        term.writeln('\r\n\x1b[31m[couldn\'t reach the terminal service — retrying]\x1b[0m');
      };

      ws.onclose = () => {
        if (cancelled) return;
        if (document.visibilityState === 'visible') {
          const wait = nextDelay();
          /* Announce the first retry, and the moment it settles at the
             ceiling — not the twenty in between. */
          if (attempt === 0) {
            term.writeln('\r\n\x1b[2m[reconnecting…]\x1b[0m');
          } else if (attempt === RETRY_MS.length - 1) {
            term.writeln('\r\n\x1b[2m[still trying every ' + (wait / 1000) +
                         's — it will pick up on its own if the service comes back]\x1b[0m');
          }
          attempt++;
          setTimeout(() => { if (!cancelled) connect(); }, wait);
        }
        // If hidden, visibilitychange below will reconnect when the user returns.
      };
    };

    const sendResize = () => {
      try { fit.fit(); } catch (_) {}
      if (wsRef.current?.readyState === WebSocket.OPEN)
        wsRef.current.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
    };
    const ro = new ResizeObserver(sendResize);
    if (containerRef.current) ro.observe(containerRef.current);
    window.addEventListener('resize', sendResize);

    // Reconnect when the user returns from another app / tab.
    const handleVisibility = () => {
      if (document.visibilityState === 'visible' && !cancelled) {
        const rs = wsRef.current?.readyState;
        if (rs !== WebSocket.OPEN && rs !== WebSocket.CONNECTING) {
          term.writeln('\r\n\x1b[2m[reconnecting…]\x1b[0m');
          connect();
        }
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    requestAnimationFrame(() => {
      if (!cancelled) {
        try { fit.fit(); } catch (_) {}
        connect();
      }
    });

    const containerEl = containerRef.current;
    return () => {
      cancelled = true;
      ro.disconnect();
      window.removeEventListener('resize', sendResize);
      document.removeEventListener('visibilitychange', handleVisibility);
      if (containerEl) containerEl.removeEventListener('mouseup', onMouseUp);
      clearTimeout(flashTimer.current);
      try { if (wsRef.current) wsRef.current.close(); } catch (_) {}
      try { term.dispose(); } catch (_) {}
      termRef.current = wsRef.current = fitRef.current = null;
    };
  }, [project?.id, project?.path, cli]);

  React.useEffect(() => {
    if (visible && fitRef.current) {
      // Double rAF: the first frame after un-hiding can still have the pane at
      // its collapsed size (mobile toggles height 0 → flex), so a single-frame
      // fit() measures a 0-height box and renders a 1-row terminal.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        try { fitRef.current && fitRef.current.fit(); } catch (_) {}
        // Land the keyboard in the terminal the moment it's shown — a terminal
        // you have to click into first isn't ready for typing.
        try { termRef.current && termRef.current.focus(); } catch (_) {}
      }));
    }
  }, [visible]);

  const tbBtn = {
    fontSize: 9, fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em',
    color: 'rgba(212,216,232,0.75)', background: 'rgba(124,107,255,0.10)',
    border: '1px solid rgba(124,107,255,0.30)', borderRadius: 4,
    padding: '3px 8px', cursor: 'pointer', flexShrink: 0,
  };
  return (
    <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', minHeight: 0 }}>
      {/* Copy/paste toolbar + login-URL chip. Touch users have no Ctrl+C/V and
          no mouse selection — these buttons are their only clipboard path. */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 6, padding: '3px 8px',
        flexShrink: 0, background: '#0a0a12', minHeight: 26,
        borderBottom: '1px solid rgba(124,107,255,0.12)',
      }}>
        <button style={tbBtn} title="Copy selection (or the last URL)" onClick={copySelectionOrUrl}>⧉ COPY</button>
        <button style={tbBtn} title="Paste clipboard into the terminal" onClick={pasteClipboard}>⇩ PASTE</button>
        {flash && <span style={{ fontSize: 10, color: '#8fd18f', fontFamily: "'JetBrains Mono', monospace" }}>{flash}</span>}
        {lastUrl && (
          <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4, minWidth: 0 }}>
            <span title={lastUrl} style={{
              fontSize: 10, color: 'rgba(212,216,232,0.55)', fontFamily: "'JetBrains Mono', monospace",
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: 240, direction: 'rtl',
            }}>🔗 {lastUrl}</span>
            <button style={tbBtn} title="Copy this URL" onClick={() => copyText(lastUrl)}>COPY</button>
            <button style={tbBtn} title="Open in a new browser tab"
              onClick={() => window.open(lastUrl, '_blank', 'noopener,noreferrer')}>OPEN ↗</button>
            <button style={{ ...tbBtn, padding: '3px 5px' }} title="Dismiss" onClick={() => setLastUrl('')}>✕</button>
          </span>
        )}
      </div>
      <div ref={containerRef} style={{
        flex: 1, minHeight: 0, width: '100%',
        overflow: 'hidden', padding: '4px 0 0 6px', boxSizing: 'border-box',
      }} />
    </div>
  );
}

function TerminalSession({ project, cli, sessionId, visible, ptySupported, spawnSupported }) {
  /* Persistent state keyed on project.id + sessionId. Survives project switches
     and full reloads — so users can resume a CLI conversation without losing
     context. msgs are the visible chat history; the backend gets sessionId in
     the request so the orchestrator can attach long-running context too. */
  const pid = project?.id || project?.path || '';
  const sKey = (suffix) => pid && sessionId ? `cafresohq_terminal:${suffix}:${pid}:${sessionId}` : null;

  /* Every CLI is now dual-mode: a conversational Chat view and the raw PTY.
     - claude / codex / gemini stream Chat via their CLI's non-interactive
       mode (`--print` / `exec --json` / `--prompt`), scoped to the project dir
       and using the CLI's own login — so chat is file-aware and matches PTY.
     - hermes streams Chat through its always-on OpenAI-compatible gateway
       (/hermes/v1/chat/completions); no key needed (server-side auth).
     Default to Chat, not PTY: a fresh tab must always land somewhere that
     just works full-page in the app. PTY needs a live backend PTY bridge
     (ptySupported) or, failing that, a native OS terminal window — a "small
     window" outside the app that's now an opt-in advanced setting (see
     popoutAllowed below), not something a brand-new tab should dead-end
     into. Chat has neither dependency and stays one click away regardless. */
  const [termModeRaw, setTermMode] = useStoredV(sKey('mode'), 'chat');  // 'chat' | 'spawn'
  /* Native OS terminal windows (Terminal.app/gnome-terminal/Windows Terminal
     via /terminal/spawn) are the "small window" path — useful for desktop
     users who want to multitask across real OS windows, but not what a
     default tab should offer. Off by default; flipped on in Settings →
     Appearance → Advanced. Global key (not session-scoped) so it matches
     whatever the Settings toggle last wrote. */
  const [popoutAllowed] = useStoredV('cafresohq_terminal:popoutAllowed', false);
  /* The PTY tab earns its place when it can do something Chat can't: the
     embedded in-app terminal (ptySupported) is always worth it — it's
     full-page, not a popup. Without that, its only offer is a native OS
     window, which now requires the advanced setting; with neither, showing
     the tab would dead-end into "launch a popup" behind a control that
     isn't there. A session persisted at 'spawn' from before this setting
     existed falls back to 'chat' rather than rendering a tab that's gone. */
  const ptyTabVisible = spawnSupported && (ptySupported || popoutAllowed);
  const termMode = (termModeRaw === 'spawn' && !ptyTabVisible) ? 'chat' : termModeRaw;
  /* Chat and PTY used to be a plain ternary — switching tabs unmounted
     whichever side you left, so leaving PTY and coming back tore down and
     rebuilt the WebSocket and the xterm.js display every time, even though
     the underlying shell (session_id, keyed server-side) usually survived.
     Session tabs and desktop windows both dodge this by staying mounted
     and toggling visibility instead; PTY now does the same. Gated behind
     "opened at least once" so a tab that only ever uses Chat never pays
     for an idle background shell it doesn't need. */
  const [ptyEverOpened, setPtyEverOpened] = React.useState(termMode === 'spawn');
  React.useEffect(() => {
    if (termMode === 'spawn') setPtyEverOpened(true);
  }, [termMode]);
  // Cap persisted history like the main chat's 80-cap — an unbounded
  // orchestrator conversation eventually hits quota and then silently
  // stops persisting anything new.
  const [msgs,      setMsgs]      = useStoredV(sKey('msgs'),  [], xs => xs.slice(-120));
  const [input,     setInput]     = useSV('');
  const [busy,      setBusy]      = useSV(false);
  const [err,       setErr]       = useSV(null);
  const [model,     setModel]     = useStoredV(sKey('model'), '');
  // 'subscription' = CLI's own OAuth login, 'apikey' = BYOK API key. Claude and
  // Gemini default to their subscription/OAuth login; codex defaults to apikey.
  const [authMethod, setAuthMethod] = useStoredV(sKey('auth'), (cli === 'claude' || cli === 'gemini') ? 'subscription' : 'apikey');
  const [keyPanel,  setKeyPanel]  = useSV(false);
  const [keyInput,  setKeyInput]  = useSV('');
  const [keyStored, setKeyStored] = useSV({});
  const [spawnMsg,  setSpawnMsg]  = useSV('');
  const bottomRef = React.useRef(null);
  const inputRef  = React.useRef(null);
  const ctrlRef   = React.useRef(null);

  React.useEffect(() => {
    const oc = CafresoHQClient;
    if (!oc || !oc.hasAgentKey) return;
    setKeyStored({
      anthropic: oc.hasAgentKey('anthropic'),
      openai:    oc.hasAgentKey('openai'),
      google:    oc.hasAgentKey('google'),
    });
  }, [cli]);

  // Which stored BYOK key this CLI uses (hermes needs none — server-side auth).
  const provider    = cli === 'claude' ? 'anthropic' : cli === 'gemini' ? 'google' : cli === 'hermes' ? null : 'openai';
  const keyIsStored = !!(provider && keyStored[provider]);

  React.useEffect(() => {
    if (bottomRef.current) bottomRef.current.scrollIntoView({ behavior: 'smooth' });
  }, [msgs]);

  const stop = () => {
    if (ctrlRef.current) { ctrlRef.current.abort(); ctrlRef.current = null; }
    setBusy(false);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || busy || !project) return;
    const userMsg = { role: 'user', content: text };
    const history = [...msgs, userMsg];
    setMsgs(history);
    setInput('');
    setBusy(true);
    setErr(null);

    const asstIdx = history.length;
    const asstMsg = { role: 'assistant', segs: [] };
    setMsgs([...history, asstMsg]);

    const ctrl = new AbortController();
    ctrlRef.current = ctrl;

    // Append a streamed chunk to the in-flight assistant message, coalescing
    // consecutive chunks of the same kind ('text'|'tool'|'error') into one seg.
    const appendChunk = (content, type) => {
      setMsgs(prev => {
        const next = [...prev];
        const last = next[asstIdx];
        if (!last || last.role !== 'assistant') return prev;
        const segs = [...(last.segs || [])];
        if (segs.length > 0 && segs[segs.length - 1].type === type) {
          segs[segs.length - 1] = { ...segs[segs.length - 1], text: segs[segs.length - 1].text + content };
        } else {
          segs.push({ text: content, type });
        }
        next[asstIdx] = { ...last, segs };
        return next;
      });
    };

    const wireMessages = history.map(m => ({
      role: m.role,
      content: m.segs ? m.segs.map(s => s.text).join('') : (m.content || ''),
    }));

    try {
      if (cli === 'hermes') {
        // Hermes Chat streams through its always-on OpenAI-compatible gateway
        // (/hermes/v1/chat/completions). Model is server-configured; passing the
        // 'hermes:' prefix forces the provider without overriding the model.
        await CafresoHQClient.stream({
          model: model.trim() ? 'hermes:' + model.trim() : 'hermes:',
          messages: wireMessages,
          signal: ctrl.signal,
          onToken: (t) => appendChunk(t, 'text'),
        });
      } else {
        // claude / codex / gemini → the CLI's non-interactive mode, scoped to
        // the project dir, using the CLI's own login (subscription) or BYOK.
        await CafresoHQClient.terminalStream({
          messages: wireMessages,
          cli,
          cwd: project.path,
          model: model.trim() || undefined,
          projectName: project.name,
          projectId: project.id,
          sessionId,
          authMethod,
          signal: ctrl.signal,
          onData: appendChunk,
        });
      }
    } catch (e) {
      if (e.name !== 'AbortError') setErr(e.message || String(e));
    }
    ctrlRef.current = null;
    setBusy(false);
    if (inputRef.current) inputRef.current.focus();
  };

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
  };

  const clear = () => { setMsgs([]); setErr(null); };

  const launchTerminal = async () => {
    const oc = CafresoHQClient;
    if (!oc || !oc.spawnTerminal) return;
    setSpawnMsg(''); setErr(null);
    try {
      await oc.spawnTerminal({ cli, cwd: project.path });
      setSpawnMsg(`${cli === 'hermes' ? 'Hermes' : cli === 'claude' ? 'Claude Code' : cli === 'gemini' ? 'Gemini' : 'Codex'} launched in a new terminal window.`);
    } catch (e) {
      setErr(e.message || String(e));
    }
  };

  const saveKey = async () => {
    const oc = CafresoHQClient;
    if (!oc || !oc.setAgentKey) return;
    await oc.setAgentKey(provider, keyInput.trim());
    setKeyStored(prev => ({ ...prev, [provider]: !!keyInput.trim() }));
    setKeyInput('');
    setKeyPanel(false);
  };

  const clearKey = async () => {
    const oc = CafresoHQClient;
    if (!oc || !oc.setAgentKey) return;
    await oc.setAgentKey(provider, '');
    setKeyStored(prev => ({ ...prev, [provider]: false }));
    setKeyPanel(false);
  };

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100%',
      background: 'var(--paper)', fontFamily: "'JetBrains Mono', monospace",
      fontSize: 13, color: 'var(--ink)',
    }}>
      {/* Mode + controls — single unified bar */}
      <div style={{
        display: 'flex', alignItems: 'center', flexShrink: 0,
        borderBottom: '1px solid var(--rule)', background: 'var(--paper-2)',
        minHeight: 44,
      }}>
        {([['chat', '💬', 'Chat'], ...(ptyTabVisible ? [['spawn', '⚡', 'PTY']] : [])]
        ).map(([mode, ico, label]) => (
          <button key={mode} onClick={() => { setTermMode(mode); setErr(null); setSpawnMsg(''); }}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '0 16px', height: 44, display: 'flex', alignItems: 'center', gap: 6,
              fontSize: 12, fontWeight: 700,
              fontFamily: "'JetBrains Mono', monospace",
              color: termMode === mode ? '#7c6bff' : 'var(--ink-3)',
              borderBottom: termMode === mode ? '2px solid #7c6bff' : '2px solid transparent',
              whiteSpace: 'nowrap', flexShrink: 0,
            }}
          ><span>{ico}</span><span>{label}</span></button>
        ))}
        {!ptyTabVisible && (
          <span style={{ fontSize: 9, color: 'var(--ink-3)', paddingLeft: 10 }}>chat only</span>
        )}
        <span style={{ flex: 1 }} />
        {termMode === 'chat' ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingRight: 10 }}>
            {cli !== 'hermes' && (
            <select value={model} onChange={e => setModel(e.target.value)} disabled={busy}
              style={{
                background: 'var(--paper)', color: 'var(--ink)', border: '1px solid var(--rule)',
                borderRadius: 4, fontSize: 11, padding: '3px 6px',
                fontFamily: 'inherit', cursor: 'pointer',
              }}
            >
              {cli === 'claude' ? (
                <>
                  <option value="">model (default)</option>
                  <option value="claude-sonnet-4-6">Sonnet 4.6</option>
                  <option value="claude-opus-4-7">Opus 4.7</option>
                  <option value="claude-haiku-4-5-20251001">Haiku 4.5</option>
                  <option value="claude-sonnet-4-5-20250514">Sonnet 4.5</option>
                </>
              ) : cli === 'gemini' ? (
                <>
                  <option value="">model (default)</option>
                  <option value="gemini-2.5-pro">Gemini 2.5 Pro</option>
                  <option value="gemini-2.5-flash">Gemini 2.5 Flash</option>
                  <option value="gemini-1.5-pro">Gemini 1.5 Pro</option>
                  <option value="gemini-1.5-flash">Gemini 1.5 Flash</option>
                </>
              ) : (
                <>
                  <option value="">model (default)</option>
                  <option value="o3">o3</option>
                  <option value="o4-mini">o4-mini</option>
                  <option value="gpt-4.1">GPT-4.1</option>
                  <option value="gpt-4.1-mini">GPT-4.1 Mini</option>
                </>
              )}
            </select>
            )}
            {cli === 'hermes' && (
              <span style={{ fontSize: 9, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
                {/* SYSTEM is a removed tab id (alias → account); the Hermes
                    model selector lives in ConnectionsPanel/BrowserKeysTab. */}
                model in Settings → Connections
              </span>
            )}
            {(cli === 'claude' || cli === 'gemini') && (
              <select value={authMethod} onChange={e => { setAuthMethod(e.target.value); setKeyPanel(false); }}
                title={authMethod === 'subscription'
                  ? (cli === 'gemini' ? 'Using your Google login via the gemini CLI' : 'Using Claude Pro/Max subscription via CLI login')
                  : `Using your own ${cli === 'gemini' ? 'Google' : 'Anthropic'} API key`}
                style={{
                  background: authMethod === 'subscription' ? 'rgba(124,107,255,0.10)' : 'var(--paper)',
                  color: authMethod === 'subscription' ? '#7c6bff' : 'var(--ink)',
                  border: `1px solid ${authMethod === 'subscription' ? '#7c6bff' : 'var(--rule)'}`,
                  borderRadius: 4, fontSize: 10, padding: '3px 6px',
                  fontFamily: 'inherit', cursor: 'pointer',
                }}
              >
                <option value="subscription">{cli === 'gemini' ? '⚡ Login' : '⚡ Subscription'}</option>
                <option value="apikey">🔑 API Key</option>
              </select>
            )}
            {provider && (cli !== 'claude' && cli !== 'gemini' ? true : authMethod === 'apikey') && (
              <button onClick={() => { setKeyPanel(p => !p); setKeyInput(''); }}
                title={keyIsStored ? `${provider} key stored (AES-256-GCM)` : `Set ${provider} API key`}
                style={{
                  background: keyIsStored ? 'rgba(111,168,111,0.15)' : 'transparent',
                  color: keyIsStored ? 'var(--live)' : 'var(--ink-3)',
                  border: `1px solid ${keyIsStored ? 'var(--live)' : 'var(--rule)'}`,
                  borderRadius: 4, fontSize: 12, padding: '3px 8px', cursor: 'pointer',
                  fontFamily: 'inherit',
                }}
              >{keyIsStored ? '🔒' : '🔓'}</button>
            )}
            {busy ? (
              <button onClick={stop} style={{
                background: 'rgba(201,112,112,0.12)', color: 'var(--error)', border: '1px solid var(--error)',
                borderRadius: 4, fontSize: 10, padding: '3px 10px', cursor: 'pointer', fontFamily: 'inherit',
              }}>■ STOP</button>
            ) : (
              <button onClick={clear} style={{
                background: 'transparent', color: 'var(--ink-3)', border: '1px solid var(--rule)',
                borderRadius: 4, fontSize: 10, padding: '3px 8px', cursor: 'pointer', fontFamily: 'inherit',
              }}>CLEAR</button>
            )}
          </div>
        ) : (
          <span style={{ fontSize: 10, color: 'var(--ink-3)', paddingRight: 12, fontFamily: "'JetBrains Mono', monospace", opacity: 0.7 }}>
            {project.name}
          </span>
        )}
      </div>

      {keyPanel && authMethod === 'apikey' && (
        <div style={{
          background: 'var(--paper-2)', borderBottom: '1px solid var(--rule)',
          padding: '8px 12px', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0,
        }}>
          <span style={{ fontSize: 10, color: '#7c6bff', whiteSpace: 'nowrap' }}>
            {provider === 'anthropic' ? 'ANTHROPIC_API_KEY' : provider === 'google' ? 'GEMINI_API_KEY' : 'OPENAI_API_KEY'}
          </span>
          <input
            type="password"
            value={keyInput}
            onChange={e => setKeyInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && saveKey()}
            placeholder={keyIsStored ? '••••••• (replace)' : 'sk-…'}
            autoFocus
            style={{
              flex: 1, background: 'var(--paper)', color: 'var(--ink)',
              border: '1px solid var(--rule-2)', borderRadius: 4, fontSize: 11,
              padding: '4px 8px', fontFamily: 'inherit',
            }}
          />
          <button onClick={saveKey} disabled={!keyInput.trim()} style={{
            background: 'var(--carpet)', color: 'var(--ink)', border: '1px solid var(--carpet-dk)',
            borderRadius: 4, fontSize: 10, padding: '3px 10px', cursor: 'pointer',
            fontFamily: 'inherit',
          }}>SAVE</button>
          {keyIsStored && (
            <button onClick={clearKey} style={{
              background: 'transparent', color: 'var(--error)', border: '1px solid var(--error)',
              borderRadius: 4, fontSize: 10, padding: '3px 8px', cursor: 'pointer',
              fontFamily: 'inherit',
            }}>CLEAR KEY</button>
          )}
          <span style={{ fontSize: 9, color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
            AES-256-GCM · device key
          </span>
        </div>
      )}

      <div style={{ display: termMode === 'chat' ? 'flex' : 'none', flexDirection: 'column', flex: 1, minHeight: 0 }}>
          {/* Claude Desktop-style chat messages */}
          <div style={{
            flex: 1, overflowY: 'auto', padding: '20px 20px 8px',
            display: 'flex', flexDirection: 'column', gap: 18,
            background: 'var(--paper)',
          }}>
            {msgs.length === 0 && (
              <div style={{
                flex: 1, display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center',
                gap: 10, paddingTop: 40,
              }}>
                <div style={{ fontSize: 30, opacity: 0.35 }}>
                  {cli === 'claude' ? '✦' : cli === 'hermes' ? '☼' : cli === 'gemini' ? '✧' : '◈'}
                </div>
                <div style={{ textAlign: 'center', fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.6 }}>
                  <strong>{cli === 'claude' ? 'Claude Code' : cli === 'hermes' ? 'Hermes' : cli === 'gemini' ? 'Gemini' : 'OpenAI Codex'}</strong>
                  <br/>
                  <span style={{ fontSize: 10, color: 'var(--ink-3)' }}>
                    {cli === 'hermes'
                      ? 'via gateway · server-side auth'
                      : `${project.name} · ${(cli === 'claude' || cli === 'gemini') && authMethod === 'subscription' ? '⚡ login' : 'BYOK supported'}`}
                  </span>
                </div>
              </div>
            )}
            {msgs.map((m, i) => (
              m.role === 'user' ? (
                /* User — right-aligned bubble */
                <div key={i} style={{ display: 'flex', justifyContent: 'flex-end' }}>
                  <div style={{
                    background: '#7c6bff', color: '#fff',
                    padding: '10px 14px', borderRadius: '16px 16px 4px 16px',
                    maxWidth: '80%', fontSize: 13, lineHeight: 1.5,
                    whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    boxShadow: '0 1px 6px rgba(124,107,255,0.22)',
                    fontFamily: 'Inter, system-ui, sans-serif',
                  }}>
                    {m.content}
                  </div>
                </div>
              ) : (
                /* Assistant — left-aligned with avatar */
                <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <div style={{
                    width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
                    background: 'var(--accent-lav)', color: 'var(--ink)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 13, marginTop: 1, border: '1px solid var(--rule)',
                  }}>
                    {cli === 'claude' ? '✦' : cli === 'hermes' ? '☼' : cli === 'gemini' ? '✧' : '◈'}
                  </div>
                  <div style={{ flex: 1, fontSize: 13, lineHeight: 1.65, color: 'var(--ink)', minWidth: 0, fontFamily: 'Inter, system-ui, sans-serif' }}>
                    {(m.segs || []).map((seg, si) => {
                      if (seg.type === 'tool') return (
                        <div key={si} style={{
                          background: 'var(--paper-2)', border: '1px solid var(--rule)',
                          borderRadius: 6, padding: '5px 10px', margin: '4px 0',
                          fontSize: 11, color: 'var(--ink-2)',
                          fontFamily: "'JetBrains Mono', monospace",
                        }}>⚙ {seg.text}</div>
                      );
                      if (seg.type === 'error') return (
                        <div key={si} style={{
                          background: 'rgba(201,112,112,0.08)', border: '1px solid var(--error)',
                          borderRadius: 6, padding: '6px 10px', margin: '4px 0',
                          color: 'var(--error)', fontSize: 12,
                        }}>⚠ {seg.text}</div>
                      );
                      return (
                        <span key={si} style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
                          {seg.text}
                        </span>
                      );
                    })}
                    {busy && i === msgs.length - 1 && (
                      <span style={{
                        display: 'inline-block', width: 7, height: 13,
                        background: '#7c6bff', borderRadius: 1, marginLeft: 2,
                        verticalAlign: 'text-bottom',
                        animation: 'term-blink 1s step-end infinite',
                      }}/>
                    )}
                  </div>
                </div>
              )
            ))}
            {err && (
              <div style={{
                background: 'rgba(201,112,112,0.08)', border: '1px solid var(--error)',
                borderRadius: 8, padding: '10px 14px', color: 'var(--error)', fontSize: 12,
              }}>⚠ {err}</div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Claude Desktop-style input */}
          <div style={{
            padding: '12px 16px 14px', borderTop: '1px solid var(--rule)',
            background: 'var(--paper-2)', flexShrink: 0,
          }}>
            <div style={{
              display: 'flex', gap: 8, alignItems: 'flex-end',
              background: 'var(--paper)', border: '1px solid var(--rule)',
              borderRadius: 12, padding: '8px 8px 8px 14px',
              boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
            }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={onKey}
                disabled={busy}
                placeholder={`Message ${cli === 'claude' ? 'Claude Code' : cli === 'hermes' ? 'Hermes' : cli === 'gemini' ? 'Gemini' : 'Codex'}…`}
                rows={2}
                style={{
                  flex: 1, background: 'transparent', color: 'var(--ink)',
                  border: 'none', resize: 'none', fontFamily: 'Inter, system-ui, sans-serif',
                  fontSize: 13, padding: 0, outline: 'none',
                  lineHeight: 1.5, caretColor: '#7c6bff',
                }}
              />
              <button
                onClick={busy ? stop : send}
                disabled={!busy && (!input.trim() || !project)}
                style={{
                  width: 32, height: 32, borderRadius: 8, border: 'none',
                  background: busy ? 'rgba(201,112,112,0.15)' : (input.trim() ? '#7c6bff' : 'var(--paper-2)'),
                  color: busy ? 'var(--error)' : (input.trim() ? '#fff' : 'var(--ink-3)'),
                  fontSize: 15, cursor: (busy || input.trim()) ? 'pointer' : 'default',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, transition: 'background 0.15s, color 0.15s',
                  boxShadow: input.trim() && !busy ? '0 2px 6px rgba(124,107,255,0.3)' : 'none',
                }}
              >{busy ? '■' : '↑'}</button>
            </div>
            <div style={{ fontSize: 9, color: 'var(--ink-3)', marginTop: 5, paddingLeft: 4 }}>
              Enter to send · Shift+Enter for newline
            </div>
          </div>
      </div>
      {/* Embedded PTY terminal panel — mounted once opened, then kept alive
          (not unmounted) so switching back from Chat reattaches instantly
          instead of reconnecting from scratch. */}
      <div style={{ display: termMode === 'chat' ? 'none' : 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }}>
          {ptyEverOpened && (ptySupported ? (
            <EmbeddedTerminal project={project} cli={cli} sessionId={sessionId} visible={visible && termMode === 'spawn'} />
          ) : (
            /* Fallback: launch button */
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 32, gap: 16, background: 'var(--paper)' }}>
              <div style={{ textAlign: 'center', fontSize: 11, color: 'var(--ink-3)', lineHeight: 1.7 }}>
                Opens a new <strong style={{ color: 'var(--ink)' }}>terminal window</strong> running<br/>
                <code style={{ color: '#7c6bff' }}>{cli}</code> in <code style={{ color: '#7c6bff', opacity: 0.75 }}>{project.path}</code>
              </div>
              {spawnMsg && (
                <div style={{ background: 'rgba(111,168,111,0.12)', border: '1px solid var(--live)', borderRadius: 6, padding: '8px 16px', color: 'var(--live)', fontSize: 11 }}>
                  ✓ {spawnMsg}
                </div>
              )}
              {err && (
                <div style={{ background: 'rgba(201,112,112,0.08)', border: '1px solid var(--error)', borderRadius: 6, padding: '8px 16px', color: 'var(--error)', fontSize: 11 }}>⚠ {err}</div>
              )}
              <button onClick={launchTerminal} style={{
                background: '#7c6bff', color: '#fff', border: 'none',
                borderRadius: 8, fontFamily: 'inherit', fontSize: 12, fontWeight: 700,
                padding: '10px 28px', cursor: 'pointer',
                boxShadow: '0 2px 8px rgba(124,107,255,0.3)',
              }}>▶ LAUNCH {cli.toUpperCase()} IN TERMINAL</button>
            </div>
          ))}
          {/* Pop-out footer — dark to blend with terminal. Native OS window,
              so it stays behind the same advanced setting as the fallback
              panel's launch button, even though the embedded terminal above
              it needs no such gate (it's in-app, not a popup). */}
          {ptySupported && popoutAllowed && (
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', background: '#0a0a10', padding: '3px 12px', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', flexShrink: 0 }}>
              <button onClick={launchTerminal} title="Open in separate terminal window" style={{
                background: 'transparent', color: '#3a3555', border: 'none',
                fontSize: 9, fontFamily: 'inherit', cursor: 'pointer', letterSpacing: 0.5,
              }}>⬡ pop out</button>
              {spawnMsg && <span style={{ fontSize: 9, color: '#4ade80', marginLeft: 8 }}>✓ launched</span>}
            </div>
          )}
        </div>
    </div>
  );
}

/* Tab ids must be minted against the RESTORED session list, not a module
   counter — the counter reset to 0 on reload while ids like "s3" were
   persisted, so the next new tab minted a duplicate "s1" and two tabs
   started acting in lockstep (same React key, same activeId match). */
const _nextSessionId = (existing) => {
  let n = 0;
  for (const s of (existing || [])) {
    const m = /^s(\d+)$/.exec(String((s && s.id) || ''));
    if (m) n = Math.max(n, parseInt(m[1], 10));
  }
  return `s${n + 1}`;
};
/* _uuid() requires a secure context (HTTPS / localhost).
   On plain HTTP over LAN IP it's undefined, so we polyfill. */
const _uuid = () =>
  typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = (crypto.getRandomValues(new Uint8Array(1))[0] & 15) >> (c === 'x' ? 0 : 2);
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
      });
/* ── hqsh — the HQ canister shell ────────────────────────────────────────────
   A REPL session type inside the Terminal (NOT a PTY): canister reads/writes
   need the Internet Identity, which lives browser-side behind the
   CafresoHQChain bridge — so `hq` commands resolve here, never in the
   container shell. Commands live in an extensible registry so later sprints
   (payroll, receipts, night shift) just append entries. */
const HQSH_DECIMALS = { ICP: 8, ckUSDT: 6, ckUNI: 18, sGLDT: 8, nanas: 8 };
function _hqshFmt(raw, token) {
  try {
    const dec = HQSH_DECIMALS[token] ?? 8;
    const s = BigInt(raw).toString().padStart(dec + 1, '0');
    const whole = s.slice(0, -dec) || '0';
    const frac = s.slice(-dec).replace(/0+$/, '');
    return (frac ? `${whole}.${frac}` : whole) + ` ${token}`;
  } catch (_e) { return `${raw} ${token} (raw)`; }
}
const HQSH_COMMANDS = {
  help: {
    help: 'help — list commands',
    run: async () => Object.values(HQSH_COMMANDS).map(c => '  hq ' + c.help).join('\n'),
  },
  whoami: {
    help: 'whoami — your Internet Identity principal',
    run: async (chain) => await chain.whoami(),
  },
  wallets: {
    help: 'wallets — agent wallet policies (cap / spent / paused)',
    run: async (chain) => {
      const ws = await chain.wallet.list();
      if (!ws.length) return '(no agent wallets — Settings → ICP Services → Agent Wallet)';
      return ws.map(w =>
        `  ${w.agentId}  ${_hqshFmt(w.windowSpent, w.token)} spent / ${_hqshFmt(w.spendCap, w.token)} cap` +
        `  window ${w.windowSecs}s${w.paused ? '  [PAUSED]' : ''}`).join('\n');
    },
  },
  balance: {
    help: 'balance <agentId> — all token balances for an agent wallet',
    run: async (chain, args) => {
      if (!args[0]) return 'usage: hq balance <agentId>   (ids: hq wallets)';
      const bals = await chain.wallet.balances(args[0]);
      const lines = Object.entries(bals).map(([t, v]) => `  ${t}: ${v == null ? '—' : _hqshFmt(v, t)}`);
      return lines.join('\n') || '(no balances)';
    },
  },
  address: {
    help: 'address <agentId> — every shareable address for an agent wallet',
    run: async (chain, args) => {
      if (!args[0]) return 'usage: hq address <agentId>';
      const a = await chain.wallet.address(args[0]);
      return [
        `  ICRC-1 account : ${a.accountText || '—'}`,
        `  legacy acct id : ${a.legacyAccountId || '—'}  (exchanges — ICP only)`,
        `  principal      : ${a.owner}`,
        `  subaccount     : ${a.subaccountHex}`,
      ].join('\n');
    },
  },
  fund: {
    help: 'fund <agentId> <token> <amount> — top up from your main account',
    run: async (chain, args) => {
      const [id, token, amt] = args;
      if (!amt) return 'usage: hq fund <agentId> <token> <amount>';
      try { window.dispatchEvent(new CustomEvent('cafresohq:walletLocalMove', { detail: { agentId: id } })); } catch (_e) {}
      const r = await chain.wallet.fund(id, token, amt);
      return r && r.ok != null ? `funded (block ${r.ok})` : `fund failed: ${(r && r.err) || 'unknown'}`;
    },
  },
  send: {
    help: 'send <agentId> <token> <amount> <to> [memo] — spend from an agent wallet (cap-gated)',
    run: async (chain, args) => {
      const [id, token, amt, to, ...memo] = args;
      if (!to) return 'usage: hq send <agentId> <token> <amount> <to-principal> [memo]';
      const r = await chain.wallet.send(id, token, amt, to, memo.join(' '));
      return r.status === 'ok' ? `sent (block ${r.block})` : `send: ${r.status}${r.reason ? ' — ' + r.reason : ''}`;
    },
  },
  'pause-all': {
    help: 'pause-all on|off — freeze/unfreeze all agent spending',
    run: async (chain, args) => {
      if (args[0] !== 'on' && args[0] !== 'off') return 'usage: hq pause-all on|off';
      await chain.wallet.pauseAll(args[0] === 'on');
      return `spending ${args[0] === 'on' ? 'PAUSED' : 'resumed'} for all agents`;
    },
  },
  sites: {
    help: 'sites — your published sites on the state canister',
    run: async (chain) => {
      const sites = await chain.sites.list();
      if (!sites.length) return '(no published sites yet — agents publish with [PUBLISH_SITE: dir])';
      return sites.map(s => `  ${s.project}  ${s.files} file(s), ${s.bytes} bytes`).join('\n');
    },
  },
  docs: {
    help: 'docs — your HQ docs stored on-chain',
    run: async (chain) => {
      const docs = await chain.docs.list();
      if (!docs.length) return '(no on-chain docs yet)';
      return docs.map(d => `  ${d.name}  v${d.version}`).join('\n');
    },
  },
  status: {
    help: 'status — canister id, cycles, signed-in principal',
    run: async (chain) => {
      const s = await chain.status();
      return [
        `  principal : ${s.principal}`,
        `  canister  : ${s.stateCanister || '—'} (${s.configured ? 'configured' : 'NOT configured'})`,
        `  cycles    : ${s.cycles == null ? '—' : s.cycles}`,
      ].join('\n');
    },
  },
  payroll: {
    help: 'payroll [run <agentId> | pause on|off | payouts] — canister-timer salaries',
    run: async (chain, args) => {
      if (args[0] === 'run') {
        if (!args[1]) return 'usage: hq payroll run <agentId>';
        return `payroll run → ${await chain.payroll.run(args[1])}`;
      }
      if (args[0] === 'pause') {
        if (args[1] !== 'on' && args[1] !== 'off') return 'usage: hq payroll pause on|off';
        await chain.payroll.pause(args[1] === 'on');
        return `payroll ${args[1] === 'on' ? 'PAUSED' : 'resumed'}`;
      }
      if (args[0] === 'payouts') {
        const po = await chain.payroll.payouts();
        if (!po.length) return '(no payouts yet)';
        return po.slice(-12).reverse().map(p =>
          `  ${p.status === 'paid' ? '✓' : p.status === 'pending' ? '…' : '✗'} ${p.agentId}  ${_hqshFmt(p.amount, p.token)}  ${p.status}` +
          (p.blockIndex != null ? `  block ${p.blockIndex}` : '')).join('\n');
      }
      const pr = await chain.payroll.list();
      const allow = await chain.payroll.allowance('ICP').catch(() => null);
      const head = `  budget    : ${allow ? _hqshFmt(allow.allowance, 'ICP') + ' allowance left' : '— none signed (Settings → ICP Services → Payroll Budget)'}` +
        `\n  paused    : ${pr.paused ? 'YES' : 'no'}`;
      if (!pr.salaries || !pr.salaries.length) return head + '\n  (no salaries — set one on an agent wallet card)';
      return head + '\n' + pr.salaries.map(s =>
        `  ${s.agentId}  ${_hqshFmt(s.amount, s.token)} / ${Math.round(s.periodSecs / 3600)}h  ${s.mode}` +
        `${s.active ? '' : '  [inactive]'}${s.stalledSince ? '  [STALLED: ' + s.lastResult + ']' : s.lastResult ? '  (' + s.lastResult + ')' : ''}`).join('\n');
    },
  },
  night: {
    help: 'night [list | schedule <agentId> <topic…> | cancel <id> | runs | chain] — container night shift',
    run: async (_chain, args) => {
      const base = (CafresoHQClient && CafresoHQClient.backendBase()) || '';
      const j = (p, o) => fetch(base + p, { credentials: 'include', ...(o || {}) }).then(r => r.json());
      const fmtT = (ms) => ms ? new Date(ms).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '—';
      if (args[0] === 'chain') {
        // MVP-2 wake mirror — the state canister's copy, used only to wake
        // STOPPED containers (dark until the admin sets wake config on-chain).
        const chain = CafresoHQChain;
        if (!chain || !chain.isAvailable()) return 'chain bridge unavailable (open HQ through the shell)';
        const [st, rows] = await Promise.all([chain.missions.wakeStatus(), chain.missions.list()]);
        const head = `wake: ${st.enabled ? 'ENABLED' : 'dark (disabled)'} · gateway ${st.urlSet ? 'set' : '—'} · secret ${st.secretSet ? 'set' : '—'}`;
        if (!rows.length) return head + '\n  (no mirrored schedules)';
        return head + '\n' + rows.map(m =>
          `  ${m.enabled ? '🌙' : '·'} ${m.id}  ${m.agentId} · ${String(m.topic).slice(0, 40)}` +
          `  ${m.recurrence} · next ${fmtT(m.nextRunAtMs)}${m.lastWakeResult ? ' · wake ' + m.lastWakeResult : ''}`).join('\n');
      }
      if (args[0] === 'runs') {
        const { runs } = await j('/missions/runs');
        if (!runs || !runs.length) return '(no night runs yet)';
        // Twin of missions.jsx's RECENT NIGHT RUNS list — finishedAt is 0
        // for the whole duration of a run, so an in-flight mission read
        // identically to a finished one here too.
        return runs.slice(-10).reverse().map(r => {
          const inFlight = !r.finishedAt;
          return `  ${inFlight ? '▶' : (r.lastError ? '⚠' : '✓')} ${fmtT(r.startedAt)}  ${r.agentName || r.agentId} · ${String(r.topic).slice(0, 40)}` +
            `  ${r.iterations} rounds · ${(r.writes || []).length} notes${inFlight ? ' · still running' : (r.lastError ? ' · ' + String(r.lastError).slice(0, 50) : '')}`;
        }).join('\n');
      }
      if (args[0] === 'cancel') {
        if (!args[1]) return 'usage: hq night cancel <scheduleId>';
        const res = await j(`/missions/scheduled/${args[1]}`, { method: 'DELETE' });
        if (res.existed) {
          const c = CafresoHQChain;
          if (c && c.isAvailable()) c.missions.remove(args[1]).catch(() => {});
        }
        return res.existed ? `cancelled ${args[1]}` : `no schedule ${args[1]}`;
      }
      if (args[0] === 'schedule') {
        const [, agentId, ...rest] = args;
        const topic = rest.join(' ').trim();
        if (!agentId || !topic) return 'usage: hq night schedule <agentId> <topic…>   (starts within ~30s)';
        const res = await j('/missions/schedule', {
          method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ agentId, agentName: agentId, topic, startAt: 0, recurrence: 'once', durationMs: 3600000, intervalMs: 600000 }),
        });
        return res.error ? `error: ${res.error}` : `scheduled ${res.schedule.id} — first run within ~30s, 1h @ 10m. Cancel: hq night cancel ${res.schedule.id}`;
      }
      const { schedules, running } = await j('/missions/scheduled');
      if (!schedules || !schedules.length) return '(no night schedules — hq night schedule <agentId> <topic>)';
      return schedules.map(s =>
        `  ${running.includes(s.id) ? '● RUNNING' : s.enabled ? '🌙' : '·'} ${s.id}  ${s.agentName || s.agentId} · ${String(s.topic).slice(0, 40)}` +
        `  ${s.recurrence} · ${s.enabled ? 'next ' + fmtT(s.nextRunAt) : 'done'}`).join('\n');
    },
  },
  receipts: {
    help: 'receipts — on-chain work receipts with public verify URLs',
    run: async (chain) => {
      const rs = await chain.receipt.list();
      if (!rs.length) return '(no on-chain receipts yet — headline deliverables anchor automatically)';
      return rs.slice(-10).reverse().map(r =>
        `  #${r.id} ${r.agentName} · ${r.tool} — ${r.title.slice(0, 48)}\n      ${r.verifyUrl || '(verify url unavailable)'}`).join('\n');
    },
  },
  pnl: {
    help: 'pnl — earned vs spent per agent (payroll + on-chain metering)',
    run: async (chain) => {
      const [ws, totals, payouts] = await Promise.all([
        chain.wallet.list(),
        chain.wallet.totals().catch(() => ({})),
        chain.payroll.payouts().catch(() => []),
      ]);
      if (!ws.length) return '(no agent wallets)';
      return ws.map(w => {
        const tok = w.token || 'ICP';
        let earned = BigInt(0);
        for (const p of payouts) if (p.agentId === w.agentId && p.token === tok && p.status === 'paid') earned += BigInt(p.amount);
        const spent = BigInt((totals[w.agentId] && totals[w.agentId][tok]) || 0);
        const net = earned - spent;
        return `  ${w.agentId}  earned ${_hqshFmt(earned, tok)}  spent ${_hqshFmt(spent, tok)}  net ${net < BigInt(0) ? '-' : ''}${_hqshFmt(net < BigInt(0) ? -net : net, tok)}`;
      }).join('\n') + '\n  (earned counts payroll payouts; live tips add in the office P&L frame)';
    },
  },
};

function HqShell({ sessionId, visible }) {
  const histKey = `cafresohq_hqsh:history:${sessionId}`;
  const [lines, setLines] = React.useState(() => ([
    { kind: 'out', text: 'hqsh — CafresoHQ canister shell. Type "hq help".' },
  ]));
  const [input, setInput] = React.useState('');
  const [hist, setHist] = React.useState(() => {
    try { return JSON.parse(localStorage.getItem(histKey) || '[]'); } catch (_e) { return []; }
  });
  const [histIx, setHistIx] = React.useState(-1);
  const [busy, setBusy] = React.useState(false);
  const scrollRef = React.useRef(null);
  const inputRef = React.useRef(null);
  React.useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [lines]);
  React.useEffect(() => { if (visible && inputRef.current) inputRef.current.focus(); }, [visible]);

  const print = (kind, text) => setLines(prev => [...prev.slice(-400), ...String(text).split('\n').map(t => ({ kind, text: t }))]);

  const runLine = async (raw) => {
    const cmdline = raw.trim();
    if (!cmdline) return;
    print('in', 'hq> ' + cmdline);
    const nextHist = [cmdline, ...hist.filter(h => h !== cmdline)].slice(0, 50);
    setHist(nextHist); setHistIx(-1);
    try { localStorage.setItem(histKey, JSON.stringify(nextHist)); } catch (_e) {}

    const words = cmdline.replace(/^hq\s+/i, '').split(/\s+/).filter(Boolean);
    const name = (words[0] || '').toLowerCase();
    if (name === 'clear') { setLines([]); return; }
    const cmd = HQSH_COMMANDS[name];
    if (!cmd) { print('err', `unknown command: ${name || '(empty)'} — try "hq help"`); return; }
    const chain = CafresoHQChain;
    // 'night' talks to the container backend, not the chain — allow it standalone.
    if (name !== 'help' && name !== 'night' && !(chain && chain.isAvailable && chain.isAvailable())) {
      print('err', 'Not inside the shell — open the HQ at ai.cafreso.com and sign in with Internet Identity to reach the chain.');
      return;
    }
    setBusy(true);
    try { print('out', await cmd.run(chain, words.slice(1))); }
    catch (e) { print('err', String((e && e.message) || e)); }
    setBusy(false);
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !busy) { const v = input; setInput(''); runLine(v); }
    else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const ix = Math.min(histIx + 1, hist.length - 1);
      if (ix >= 0 && hist[ix] != null) { setHistIx(ix); setInput(hist[ix]); }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      const ix = histIx - 1;
      setHistIx(ix);
      setInput(ix >= 0 ? hist[ix] : '');
    }
  };

  const C = { in: '#8ee6a1', out: '#d4d8e8', err: '#ff8a8a' };
  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0d0d16', minHeight: 0 }}
         onClick={() => inputRef.current && inputRef.current.focus()}>
      <div ref={scrollRef} style={{ flex: 1, overflowY: 'auto', padding: '10px 12px',
        fontFamily: "'JetBrains Mono', 'VT323', monospace", fontSize: 12, lineHeight: 1.55 }}>
        {lines.map((l, i) => (
          <div key={i} style={{ color: C[l.kind] || C.out, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{l.text}</div>
        ))}
        {busy && <div style={{ color: '#7c6bff' }}>…</div>}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
        borderTop: '1px solid rgba(124,107,255,0.25)', flexShrink: 0 }}>
        <span style={{ color: '#7c6bff', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }}>hq&gt;</span>
        <input ref={inputRef} value={input} disabled={busy}
          onChange={e => setInput(e.target.value)} onKeyDown={onKeyDown}
          placeholder='wallets · balance <agent> · sites · status · help'
          style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none',
            color: '#d4d8e8', fontFamily: "'JetBrains Mono', monospace", fontSize: 12 }} />
      </div>
    </div>
  );
}

function ProjectTerminal({ project, visible }) {
  /* Sessions persist per-project so closing the project (or reloading) doesn't
     wipe the user's terminal tabs. Keyed on project.id; if the project has no
     id (shouldn't happen but be defensive) we fall back to in-memory only. */
  const pid = project?.id || project?.path || null;
  const sessKey = pid ? `cafresohq_terminal:sessions:${pid}` : null;
  const activeKey = pid ? `cafresohq_terminal:active:${pid}` : null;

  const [sessions, setSessions] = useStoredV(sessKey, () => {
    return [{ id: 's1', cli: 'hermes', sessionId: _uuid() }];
  });
  const [activeId, setActiveId] = useStoredV(activeKey, () => sessions[0]?.id);

  /* Defensive — if persisted activeId points to a session that no longer exists,
     snap to the first available session. */
  React.useEffect(() => {
    if (sessions.length === 0) {
      const fresh = [{ id: 's1', cli: 'hermes', sessionId: _uuid() }];
      setSessions(fresh);
      setActiveId(fresh[0].id);   // was a bare `id` — ReferenceError when this path ran
      return;
    }
    if (!sessions.find(s => s.id === activeId)) {
      setActiveId(sessions[0].id);
    }
  }, [sessions, activeId]);

  const [spawnSupported, setSpawnSupported] = React.useState(true);
  const [ptySupported, setPtySupported]     = React.useState(false);
  const [addMenuOpen, setAddMenuOpen]       = React.useState(false);
  const [addMenuPos,  setAddMenuPos]        = React.useState({ top: 0, left: 0 });
  const addBtnRef = React.useRef(null);
  const addMenuRef = React.useRef(null);

  React.useEffect(() => {
    fetch((window._API_BASE || '') + '/terminal/status')
      .then(r => r.json())
      .then(j => {
        setSpawnSupported(!!j.spawn_supported);
        setPtySupported(!!j.pty_supported);
      })
      .catch(() => { setSpawnSupported(false); setPtySupported(false); });
  }, []);

  React.useEffect(() => {
    if (!addMenuOpen) return;
    const close = (e) => {
      // The menu is portaled to <body>, so it's NOT inside addBtnRef — check both.
      if (addBtnRef.current && addBtnRef.current.contains(e.target)) return;
      if (addMenuRef.current && addMenuRef.current.contains(e.target)) return;
      setAddMenuOpen(false);
    };
    const closeNow = () => setAddMenuOpen(false);
    document.addEventListener('mousedown', close);
    document.addEventListener('touchstart', close);
    window.addEventListener('scroll', closeNow, true);
    window.addEventListener('resize', closeNow);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('touchstart', close);
      window.removeEventListener('scroll', closeNow, true);
      window.removeEventListener('resize', closeNow);
    };
  }, [addMenuOpen]);

  const addSession = (cli) => {
    const id = _nextSessionId(sessions);
    setSessions(prev => {
      // Stable per-CLI ordinal, assigned once at creation. Deriving the label
      // from the array index made "Claude #3" silently become "Claude #2" when
      // a middle tab closed — labels must never renumber under the user.
      const n = prev.filter(s => s.cli === cli).reduce((m, s) => Math.max(m, s.n || 0), 0) + 1;
      return [...prev, { id, cli, sessionId: _uuid(), n }];
    });
    setActiveId(id);
    setAddMenuOpen(false);
  };

  const closeSession = (id) => {
    // Closing the LAST tab is allowed — the sessions.length===0 effect above
    // respawns a fresh default session, which is what "close" means there.
    const closing = sessions.find(s => s.id === id);
    const next = sessions.filter(s => s.id !== id);
    // Side effects MUST stay OUTSIDE the setState updater — calling setActiveId()
    // from inside the setSessions(prev => …) updater is the React anti-pattern
    // that blanked the whole page when a tab was closed.
    setSessions(next);
    if (activeId === id && next.length) setActiveId(next[next.length - 1].id);
    /* "End session" used to only close the client socket, which the
       backend treats as a disconnect, not a kill (_PTY_SESSION_TTL keeps
       the PTY alive for up to 5 minutes so a dropped connection can
       reconnect). That's right for a network blip; it's wrong for an
       explicit close click, which has no way back to this tab anyway —
       so ask the backend to end the process now instead of leaving it
       to the reaper. Best-effort: a session that was never PTY-backed
       (e.g. a plain hqsh tab) just gets a harmless 200 back. */
    if (closing && closing.sessionId) {
      fetch((window._API_BASE || '') + '/terminal/kill?session_id=' + encodeURIComponent(closing.sessionId))
        .catch(() => {});
    }
    /* Clear this session's persistent state so localStorage doesn't bloat over
       time. msgs can be hundreds of KB after a long conversation. */
    if (closing && pid) {
      try {
        ['mode', 'msgs', 'model', 'auth'].forEach(suffix => {
          localStorage.removeItem(`cafresohq_terminal:${suffix}:${pid}:${closing.sessionId}`);
        });
      } catch (_e) {}
    }
  };

  const cliName = (cli) => cli === 'hermes' ? 'Hermes' : cli === 'claude' ? 'Claude' : cli === 'gemini' ? 'Gemini' : cli === 'hqsh' ? 'hqsh' : 'Codex';
  const cliIcon = (cli) => cli === 'hermes' ? '☼' : cli === 'claude' ? '✦' : cli === 'gemini' ? '✧' : cli === 'hqsh' ? '⛓' : '◈';

  const getLabel = (session) => {
    const name = cliName(session.cli);
    const same = sessions.filter(s => s.cli === session.cli);
    if (same.length <= 1) return name;
    // Prefer the stable creation ordinal; sessions persisted before `n`
    // existed fall back to array position.
    return `${name} #${session.n || same.indexOf(session) + 1}`;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Session tab bar */}
      <div style={{
        display: 'flex', alignItems: 'center',
        borderBottom: '1px solid var(--rule)', flexShrink: 0,
        background: 'var(--paper-2)', padding: '0 6px',
        overflowX: 'auto', WebkitOverflowScrolling: 'touch',
        scrollbarWidth: 'none', gap: 2, minHeight: 44,
      }}>
        {sessions.map(s => {
          const active = s.id === activeId;
          const icon = cliIcon(s.cli);
          return (
            <div key={s.id}
              onClick={() => setActiveId(s.id)}
              onAuxClick={e => { if (e.button === 1) { e.preventDefault(); closeSession(s.id); } }}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '0 4px 0 12px', cursor: 'pointer', whiteSpace: 'nowrap',
                minHeight: 44, fontSize: 12, fontWeight: 600,
                fontFamily: "'JetBrains Mono', monospace",
                color: active ? '#7c6bff' : 'var(--ink-3)',
                borderBottom: active ? '2px solid #7c6bff' : '2px solid transparent',
                background: active ? 'rgba(124,107,255,0.06)' : 'transparent',
                borderRadius: '6px 6px 0 0',
                transition: 'background 0.15s, color 0.15s',
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 13 }}>{icon}</span>
              <span>{getLabel(s)}</span>
              {(
                <button
                  onClick={e => { e.stopPropagation(); closeSession(s.id); }}
                  title={sessions.length > 1 ? 'End session' : 'End session (a fresh one opens)'}
                  style={{
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'inherit', opacity: active ? 0.7 : 0.35,
                    fontSize: 16, lineHeight: 1, padding: '0 8px', margin: 0,
                    minWidth: 32, minHeight: 32, display: 'flex', alignItems: 'center',
                    justifyContent: 'center', borderRadius: 4,
                    transition: 'opacity 0.15s, background 0.1s',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = 1; e.currentTarget.style.background = 'rgba(124,107,255,0.1)'; }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = active ? 0.7 : 0.35; e.currentTarget.style.background = 'none'; }}
                >×</button>
              )}
            </div>
          );
        })}
        {/* Add session */}
        <div ref={addBtnRef} style={{ position: 'relative', flexShrink: 0, marginLeft: 4 }}>
          <button
            onClick={() => {
              if (!addMenuOpen && addBtnRef.current) {
                const r = addBtnRef.current.getBoundingClientRect();
                // Open DOWNWARD from the button. The portal escapes the tab bar's
                // overflow clip, so the menu is no longer hidden under the terminal
                // — and downward avoids running off the top of the screen on mobile
                // (the tab bar sits at the very top there). Clamp left so the 170px
                // menu never runs off a narrow/iPad edge.
                const MENU_W = 170;
                const left = Math.max(8, Math.min(r.left, window.innerWidth - MENU_W - 8));
                const top = r.bottom + 6;
                setAddMenuPos({ top, left });
              }
              setAddMenuOpen(p => !p);
            }}
            title="New CLI session"
            style={{
              background: addMenuOpen ? 'rgba(124,107,255,0.12)' : 'transparent',
              border: '1px solid var(--rule)',
              borderRadius: 6, color: addMenuOpen ? '#7c6bff' : 'var(--ink-3)',
              fontSize: 20, lineHeight: 1,
              width: 36, height: 36, cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'background 0.15s, color 0.15s', flexShrink: 0,
            }}
          >+</button>
          {addMenuOpen && ReactDOM.createPortal(
            <div ref={addMenuRef} style={{
              position: 'fixed', top: addMenuPos.top, left: addMenuPos.left, zIndex: 'var(--z-dropdown)',
              background: '#12121e', border: '1px solid rgba(124,107,255,0.25)',
              borderRadius: 10, boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
              padding: 6, minWidth: 170,
            }}>
              {[['hermes', '☼', 'Hermes', true], ['claude', '✦', 'Claude Code', false], ['codex', '◈', 'Codex CLI', false], ['gemini', '✧', 'Gemini CLI', false], ['hqsh', '⛓', 'hqsh — HQ chain shell', false]].map(([c, ico, label, isDefault]) => (
                <div key={c}
                  onClick={() => addSession(c)}
                  style={{
                    padding: '10px 14px', cursor: 'pointer', fontSize: 12,
                    borderRadius: 6, display: 'flex', alignItems: 'center', gap: 10,
                    fontFamily: "'JetBrains Mono', monospace",
                    color: '#d4d8e8', transition: 'background 0.1s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.background = 'rgba(124,107,255,0.18)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <span style={{ fontSize: 15, color: '#7c6bff' }}>{ico}</span>
                  <span>{label}</span>
                  {isDefault && (
                    <span style={{
                      marginLeft: 'auto', fontSize: 9, fontWeight: 700, letterSpacing: '0.04em',
                      color: '#7c6bff', background: 'rgba(124,107,255,0.16)',
                      borderRadius: 4, padding: '2px 6px',
                    }}>DEFAULT</span>
                  )}
                </div>
              ))}
            </div>,
            document.body
          )}
        </div>
      </div>

      {/* Session panels — all stay mounted, only active is visible */}
      {sessions.map(s => (
        <div key={s.id} style={{
          flex: 1, overflow: 'hidden',
          display: s.id === activeId ? 'flex' : 'none',
          flexDirection: 'column',
        }}>
          {s.cli === 'hqsh' ? (
            /* hqsh is a browser-side canister REPL — no PTY spawn. */
            <HqShell sessionId={s.sessionId} visible={visible && s.id === activeId} />
          ) : (
            <TerminalSession
              project={project}
              cli={s.cli}
              sessionId={s.sessionId}
              visible={visible && s.id === activeId}
              ptySupported={ptySupported}
              spawnSupported={spawnSupported}
            />
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Universal artifact preview ──────────────────────────────────────────────
   Renders a file by type so users can SEE what an agent built — HTML pages/decks,
   PDFs, images, markdown, CSV — right beside the editor. Text types render from the
   already-read content (works anywhere); binary types (image/PDF) stream from
   serve.py's /fs/file endpoint. The headline of the "agentic workspace" — view the
   doc/site as the agent writes it. */

export { ProjectTerminal };
