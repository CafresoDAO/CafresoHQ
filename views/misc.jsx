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
    <div className="view-terminal">
      {/* Header — same frame as every other view. The dark band it used to
          wear belonged to no other screen in the office. */}
      <div className="term-head">
        <div className="section-title">
          <span>Terminal</span>
          <span className="tag">
            {/* Must list every session type the "+" menu in ProjectTerminal
                actually offers (terminal.jsx's addSession menu). */}
            Hermes · Claude Code · Codex · Gemini · hqsh
          </span>
        </div>
        <span className="term-hint">+ adds a session · × ends one</span>
      </div>
      {/* Terminal panel fills remaining space */}
      <div className="term-body">
        <ProjectTerminal project={HQ_PROJECT} visible={true} />
      </div>
    </div>
  );
}


export { TerminalView };
