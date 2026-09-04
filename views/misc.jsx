import { ProjectTerminal } from './terminal.jsx';

/* ================================================================
   TerminalView — full-screen standalone terminal
   A permanent HQ-global terminal that starts Hermes and lets you
   add Claude Code / Codex / Gemini tabs once they are installed.
   Uses the same ProjectTerminal machinery but with a fixed project
   context (id='hq-global-terminal', path='') so sessions persist.
   ================================================================ */
function TerminalView() {
  // A non-empty path is required — the embedded PTY bails on a falsy project.path
  // (that's why the standalone Terminal tab loaded blank while Projects worked).
  // /root/Documents is the container's code-agent sandbox dir (created in the
  // Dockerfile); local runs override via CAFRESOHQ_TERMINAL_CWD if they want.
  const HQ_PROJECT = React.useMemo(() => ({
    id: 'hq-global-terminal',
    path: (typeof window !== 'undefined' && window._TERMINAL_CWD) || '/root/Documents',
  }), []);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', background: '#0a0a10' }}>
      {/* Header */}
      <div style={{
        padding: '10px 16px',
        borderBottom: '1px solid rgba(124,107,255,0.18)',
        background: '#0f0f1a',
        flexShrink: 0,
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.06em', color: '#7c6bff', fontFamily: "'JetBrains Mono', monospace" }}>
          ☼ TERMINAL
        </span>
        <span style={{ fontSize: 10, color: 'rgba(212,216,232,0.45)', fontFamily: "'JetBrains Mono', monospace" }}>
          {/* Must list every session type the "+" menu in ProjectTerminal
              actually offers (terminal.jsx's addSession menu) — this was
              missing hqsh (the HQ chain shell) since the day this view was
              split out, understating what a new tab here can be. */}
          Hermes · Claude Code · Codex · Gemini · hqsh
        </span>
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: 9, color: 'rgba(212,216,232,0.3)', fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.04em' }}>
          + to add session · × to close tab
        </span>
      </div>
      {/* Terminal panel fills remaining space */}
      <div style={{ flex: 1, overflow: 'hidden', minHeight: 0 }}>
        <ProjectTerminal project={HQ_PROJECT} visible={true} />
      </div>
    </div>
  );
}


export { TerminalView };
