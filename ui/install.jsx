import { CafresoHQClient } from '../claude-client.jsx';
/* ==========================================================================
   Install the CLI from where the office says it is missing (#436).

   Settings → Connections → ON THIS MACHINE read "not found on this machine"
   (or "installed, but it will not start") and offered nothing — while
   serve.py has had an allow-listed installer (`POST /agents/install`, npm
   for the three Node CLIs) since the fleet work, reachable from no button.
   The office's own Terminal tab spawns a CLI, not a shell, so "open the
   command in the terminal" is not a door it has; this is: one button that
   has the office run the install itself, the exact command it will run
   said out loud, and a copy for anyone who would rather run it in their
   own terminal. When the install lands the caller re-probes and the row's
   own sentence flips — for Claude and Codex, to the sign-in control.
   ========================================================================== */

const { useState, useEffect, useRef } = React;

/* For display only. The command the office actually runs is serve.py's
   AGENT_NPM allowlist; a suite pins the two to the same packages. */
export const INSTALL_CMD = {
  'claude-code': 'npm install -g @anthropic-ai/claude-code@latest',
  'codex':       'npm install -g @openai/codex@latest',
  'gemini':      'npm install -g @google/gemini-cli@latest',
};
export const INSTALL_NAME = { 'claude-code': 'Claude Code', codex: 'Codex', gemini: 'Gemini CLI' };

export function useAgentInstall({ onInstalled } = {}) {
  const [install, setInstall] = useState({});
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const patch = (id, p) => setInstall(prev => ({ ...prev, [id]: { ...(prev[id] || {}), ...p } }));
  const start = async (id) => {
    patch(id, { status: 'running', error: '', copied: false });
    let r;
    try {
      /* agentsInstall resolves when the background job settles (202 + poll). */
      r = await CafresoHQClient.agentsInstall(id);
    } catch (e) {
      if (mounted.current) patch(id, { status: 'error', error: String(e && e.message || e) });
      return;
    }
    if (!mounted.current) return;
    if (r && r.installed && !r.probeError) {
      patch(id, { status: 'done', installed: true, version: r.version || '' });
      if (onInstalled) onInstalled(id);
    } else {
      /* npm exiting 0 does not mean the thing it wrote can run (serve.py
         carries the probe's verdict) — say that, never "installed". */
      patch(id, { status: 'error', error: r && r.probeError
        ? `it installed, but it ${r.probeError}`
        : 'the install finished but nothing runnable was found' });
    }
  };
  const copy = async (id) => {
    try {
      await navigator.clipboard.writeText(INSTALL_CMD[id]);
      patch(id, { copied: true });
      setTimeout(() => { if (mounted.current) patch(id, { copied: false }); }, 1600);
    } catch (_e) { patch(id, { copied: false }); }
  };
  return { install, patch, start, copy };
}

/* Same face as the sign-in control (one stylesheet block), `data-install`
   instead of `data-signin`. Sits inside a row, so it stops its own clicks. */
export function AgentInstall({ id, broken, ctl, onLookAgain, where = 'settings' }) {
  if (!INSTALL_CMD[id]) return null;
  const L = ctl.install[id] || { status: 'idle' };
  const stopEv = (e) => { e.stopPropagation(); };
  const verb = broken ? 'Reinstall' : 'Install';
  const copyBtn = (
    <button type="button" className="px-btn ghost" onClick={() => ctl.copy(id)}
            title="Copy the command, to run it in a terminal of your own">
      {L.copied ? 'Copied' : 'Copy command'}
    </button>
  );
  return (
    <div className="frontdesk-signin agent-install" data-install={id} data-where={where} onClick={stopEv} onKeyDown={stopEv}>
      {(!L.status || L.status === 'idle') && (
        <>
          <button type="button" className="px-btn" onClick={() => ctl.start(id)}>{verb} {INSTALL_NAME[id]}</button>
          {copyBtn}
          <div className="frontdesk-signin-line">Runs <code>{INSTALL_CMD[id]}</code> on this machine.</div>
        </>
      )}
      {L.status === 'running' && (
        <div className="frontdesk-signin-line">Installing {INSTALL_NAME[id]} — a minute or so. You can close this; it keeps going.</div>
      )}
      {L.status === 'error' && (
        <div className="frontdesk-signin-line">
          That install did not finish — {L.error}.{' '}
          <button type="button" className="px-btn ghost" onClick={() => ctl.start(id)}>Try again</button>{' '}
          {copyBtn}
        </div>
      )}
      {L.status === 'done' && (
        <div className="frontdesk-signin-line">
          Installed{L.version ? ` — ${L.version}` : ''}.{' '}
          {onLookAgain && <button type="button" className="px-btn ghost" onClick={onLookAgain}>Look again</button>}
        </div>
      )}
    </div>
  );
}
