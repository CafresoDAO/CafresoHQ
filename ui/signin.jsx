import { CafresoHQClient } from '../claude-client.jsx';
/* ==========================================================================
   Sign in with the subscription you already pay for (#434 → #435).

   One control, wherever the office says a coworker "needs a sign-in":
   the front desk's FOUND card (modals/hire.jsx) and Settings → Connections
   → ON THIS MACHINE (modals/settings.jsx). #434 built it into the front
   desk only; Settings kept reading "found · needs a sign-in before its
   first task" with nothing to press, and a hired desk's status line still
   sent the boss to a terminal. A sentence that names a need and offers no
   door is the thing §2 says the office never does — so the control is
   lifted here and both surfaces mount it.

   serve.py runs the CLI's OWN sign-in (`claude auth login --claudeai`,
   `codex login`) in a pseudo-terminal; this polls for the link it printed,
   a code to paste (headless), and the moment the CLI writes its credential
   — then calls `onSignedIn` so the caller re-probes and its own sentence
   flips. Words: subscription, sign in; never the protocol's.
   ========================================================================== */

const { useState, useEffect, useRef } = React;

export const SIGNIN_LABEL = {
  'claude-code': 'Sign in with your Claude subscription',
  'codex': 'Sign in with your ChatGPT subscription',
};

/* "Sign in again…" when the credential file is there but the CLI no longer
   honours it (the driver's `auth === 'expired'`). */
export const signinLabel = (id, expired) =>
  expired ? SIGNIN_LABEL[id].replace('Sign in', 'Sign in again') : SIGNIN_LABEL[id];

/* The sign-in's state machine, per agent id: idle → running (url, code,
   needsCode) → done | error. `onSignedIn` fires once the CLI's credential
   is honoured; `isAlive` lets a host that unmounts its surface without
   unmounting itself (a closed modal) stop the polls. */
export function useAgentSignin({ onSignedIn, isAlive } = {}) {
  const [signin, setSignin] = useState({});
  const timers = useRef({});
  const mounted = useRef(true);
  const alive = () => mounted.current && (!isAlive || isAlive());
  const patch = (id, p) => setSignin(prev => ({ ...prev, [id]: { ...(prev[id] || {}), ...p } }));
  const stop = (id) => { clearInterval(timers.current[id]); delete timers.current[id]; };
  const poll = (id) => {
    stop(id);
    timers.current[id] = setInterval(async () => {
      let st;
      try { st = await CafresoHQClient.agentLoginStatus(id); } catch (_e) { return; }
      if (!alive()) { stop(id); return; }
      if (st.authenticated) {
        stop(id);
        patch(id, { status: 'done', authenticated: true, url: st.url, needsCode: false });
        if (onSignedIn) onSignedIn(id);
        return;
      }
      patch(id, { status: st.status, url: st.url || '', code: st.code || '', needsCode: !!st.needsCode, error: st.error || '' });
      if (st.status !== 'running') stop(id);
    }, 1500);
  };
  const start = async (id) => {
    patch(id, { status: 'running', url: '', code: '', needsCode: false, error: '', text: '' });
    let r;
    try { r = await CafresoHQClient.agentLogin(id); } catch (e) { patch(id, { status: 'error', error: String(e && e.message || e) }); return; }
    if (r.httpStatus === 404) { patch(id, { status: 'error', error: 'that coworker is not on this machine any more' }); return; }
    if (r.status === 'done' && r.authenticated) {
      patch(id, { status: 'done', authenticated: true });
      if (onSignedIn) onSignedIn(id);
      return;
    }
    poll(id);
  };
  const sendCode = async (id) => {
    const text = String((signin[id] || {}).text || '').trim();
    if (!text) return;
    await CafresoHQClient.agentLoginInput(id, text);
    patch(id, { text: '', needsCode: false });
  };
  const cancel = async (id) => {
    stop(id);
    try { await CafresoHQClient.agentLoginCancel(id); } catch (_e) { /* it may already be gone */ }
    patch(id, { status: 'idle', error: '' });
  };
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; Object.keys(timers.current).forEach(stop); };
  }, []);
  return { signin, patch, start, sendCode, cancel };
}

/* The control itself. Class names are the front desk's (#434) on purpose:
   one stylesheet block, one selector in the suites, and `data-where` says
   which surface mounted it. It sits inside clickable rows and cards, so it
   stops its own clicks. */
export function AgentSignin({ id, expired, ctl, onLookAgain, where = 'frontdesk' }) {
  if (!SIGNIN_LABEL[id]) return null;
  const L = ctl.signin[id] || { status: 'idle' };
  const stopEv = (e) => { e.stopPropagation(); };
  return (
    <div className="frontdesk-signin" data-signin={id} data-where={where} onClick={stopEv} onKeyDown={stopEv}>
      {(!L.status || L.status === 'idle' || L.status === 'none') && (
        <button type="button" className="px-btn" onClick={() => ctl.start(id)}>
          {signinLabel(id, expired)}
        </button>
      )}
      {L.status === 'running' && (
        <>
          <div className="frontdesk-signin-line">Opening your browser to sign in…</div>
          {L.url && (
            <a className="frontdesk-signin-link" href={L.url} target="_blank" rel="noopener noreferrer">
              If nothing opened, use this link ↗
            </a>
          )}
          {L.code && <div className="frontdesk-signin-line">Your code: <code>{L.code}</code></div>}
          {L.needsCode && (
            <div className="frontdesk-signin-code">
              <input type="text" value={L.text || ''} placeholder="Paste the code from that page"
                     aria-label="Paste the code from that page"
                     onChange={(e) => ctl.patch(id, { text: e.target.value })}
                     onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); ctl.sendCode(id); } }} />
              <button type="button" className="px-btn" onClick={() => ctl.sendCode(id)}>Done</button>
            </div>
          )}
          <button type="button" className="px-btn ghost" onClick={() => ctl.cancel(id)}>Cancel</button>
        </>
      )}
      {L.status === 'error' && (
        <div className="frontdesk-signin-line">
          That sign-in did not finish{L.error ? ` — ${L.error}` : ''}.{' '}
          <button type="button" className="px-btn ghost" onClick={() => ctl.start(id)}>Try again</button>
        </div>
      )}
      {L.status === 'done' && !L.authenticated && (
        <div className="frontdesk-signin-line">
          The sign-in finished but no sign-in was found here yet.{' '}
          {onLookAgain && <button type="button" className="px-btn ghost" onClick={onLookAgain}>Look again</button>}
        </div>
      )}
    </div>
  );
}
