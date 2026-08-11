import { CafresoHQChain, CafresoHQClient } from '../claude-client.jsx';
import { HQ } from '../hq-runtime.jsx';
import { Sprite } from '../sprites.jsx';
import { Modal, ModelPicker } from './base.jsx';
const { useState: useStateM, useEffect: useEffectM, useRef: useRefM } = React;
const SETTINGS_TABS = [
  { id: 'account',     ico: '⭐', label: 'ACCOUNT',     desc: 'plan · hosting · usage' },
  /* Self-hosted installs only (filtered out when health.managed) — see
     ConnectionsPanel for why this is status-and-instructions, not a form. */
  { id: 'connections', ico: '🔌', label: 'CONNECTIONS', desc: 'brains found · cloud keys' },
  { id: 'agents',      ico: '👥', label: 'ROSTER',      desc: 'per-agent config' },
  { id: 'icp-services',ico: '🧩', label: 'MODULES',     desc: 'optional add-ons · money · publish' },
  { id: 'appearance',  ico: '🖥', label: 'APPEARANCE',  desc: 'theme · vocab · ambience' },
];
// old/removed id → canonical id, so deep-links (openSettings('keys') from the
// old "add a key" chip, saved last-tab values, tour buttons) never dead-end.
/* `keys` and `agentcli` point at CONNECTIONS now that it exists. Both were
   parked on 'account' only because there was nowhere better to send them:
   the ⚠ ADD AI KEY chip's own tooltip has been promising "Settings →
   Connections" the whole time, and the onboarding checklist's FIRST step
   ("Your AI brain") lands here too — the two places a boss with no working
   brain is most likely to click. `agentcli` was the old CODE AGENTS tab,
   which is precisely the new "on this machine" panel.
   A managed install has no CONNECTIONS tab; SettingsModal's activeTab
   fallback catches that and lands on the first visible tab instead. */
const SETTINGS_TAB_ALIAS = {
  global: 'appearance', modules: 'icp-services',
  keys: 'connections', system: 'account', agentcli: 'connections', media: 'appearance',
};

/* Search index — one entry per meaningful control so "key", "model", "dark"
   etc. jump straight to the right drawer. kw = extra match terms. */
const SETTINGS_INDEX = [
  { tab:'account', label:'Plan & hosting', hint:'managed cloud or self-hosted — see which one this is', kw:'plan premium account subscription container backend health status gateway api runtime connected self-hosted' },
  { tab:'connections', label:'Brains found on this machine', hint:'which coworkers this box can already run', kw:'connections claude codex gemini ollama lmstudio cli detected found local brain' },
  { tab:'connections', label:'Cloud provider keys', hint:'OpenRouter · Groq · Gemini — set as environment variables', kw:'connections key api openrouter groq gemini google env environment variable byok self-hosted' },
  { tab:'account', label:'Usage this session', hint:'tokens your crew has spent since load', kw:'usage tokens spend cost billing' },
  { tab:'account', label:'Copy diagnostics', hint:'one-click support snapshot', kw:'diagnostics debug support copy help' },
  { tab:'account', label:'Reset onboarding', hint:'replay the new-user guide', kw:'onboarding tour guide reset replay' },
  { tab:'icp-services', label:'Modules', hint:'optional add-ons — the OS works the same with all of them off', kw:'modules add-ons addons optional capabilities icp internet computer dfinity service catalog install marketplace on-chain blockchain' },
  { tab:'icp-services', label:'Money & payments (optional)', hint:'master switch for wallets, payroll, tips — off by default', kw:'money payments wallet payroll tips icrc icp ckusdt ckuni token balance fund send cap spend agent crypto enable disable optional' },
  { tab:'icp-services', label:'Agent wallet', hint:'per-agent on-chain wallet + spend cap', kw:'wallet icp ckusdt ckuni token balance fund send cap spend agent money crypto' },
  { tab:'icp-services', label:'Publish to canister', hint:'ship a site to a *.icp0.io URL', kw:'publish canister deploy site url icp0 web hosting' },
  { tab:'agents', label:'Agent model & temperature', hint:'per-agent brain settings', kw:'roster model temperature creativity' },
  { tab:'agents', label:'Agent tools', hint:'which tools each agent may use', kw:'tools catalog permissions' },
  { tab:'agents', label:'Tool call format', hint:'JSON vs bracket fallback', kw:'json bracket format' },
  { tab:'agents', label:'File and shell access', hint:'file/shell access per agent', kw:'elevated computer shell files access security' },
  { tab:'agents', label:'Dismiss an agent', hint:'remove a hire from the roster', kw:'dismiss fire let go remove' },
  { tab:'appearance', label:'Theme & vocabulary', hint:'reskin the whole OS — office, coffee shop, trading floor…', kw:'theme skin vocabulary preset sepia solarized dracula high contrast coffeeshop wallstreet barista broker customize personalize' },
  { tab:'appearance', label:'Density', hint:'compact · comfortable · spacious', kw:'density compact comfortable spacious spacing size' },
  { tab:'appearance', label:'Scanline overlay', hint:'soft CRT shimmer', kw:'scanlines crt overlay' },
  { tab:'appearance', label:'Sound FX', hint:'pixel blips on action', kw:'sound audio blips mute' },
  { tab:'appearance', label:'Night mode', hint:'dark pixel theme', kw:'night dark theme day light' },
];

/* ── Modules ───────────────────────────────────────────────────────────────
   Optional capabilities, like enabling an MCP server. CafresoHQ is a
   deploy-agnostic agent OS: every module is OPT-IN and the OS works identically
   with all of them off. Money is deliberately just one module — nobody should
   have to think about tokens to use their agents. The MODULES tab renders each
   card inline (see the 'icp-services' tab below); there is no catalog array.

   Money master switch = settings.moneyEnabled (window.hqMoneyOn(), gates every
   money surface: wallet cards, payroll, P&L board, tip watcher, WALLET_* agent
   tools). When the shell bridge is present, enabling also flips the on-chain
   service flag in cafresohq_state; the flag mirrors to settings.icpServices so
   agent-tool gating stays synchronous. Turning money OFF never touches funds:
   balances live on-chain under the user's Internet Identity — the module hides
   them and pauses agent spending, nothing more. */

/* ── Self-host connections (north-star §1: "bring the subscriptions you
   already have") ───────────────────────────────────────────────────────
   The gap this closes: the front desk only shows a cloud provider's card
   when detect.authenticated is true (modals/hire.jsx — "a card that would
   fail its first task is worse than no card", which is right). But when
   the key ISN'T set the card is simply absent, so a self-hosted boss is
   never told those coworkers exist, let alone how to enable them. Silence,
   not a wrong answer — and silence on the one path north-star §1 names
   first.

   Why this is a read-only status panel and NOT a key-entry form: the
   drivers treat keys as env/operator config on purpose.
   drivers/local_http.py's configure() actively REFUSES runtime settings
   ("this driver has no runtime settings", 400), and hire.jsx's own note
   says the key "lives server-side, so … keys never reach the browser".
   A browser form would need a new secret-accepting endpoint — fighting a
   deliberate security posture rather than filling a gap. So: show what is
   connected, and for what isn't, name the exact environment variable and
   where to get the key. The boss sets it where secrets belong.

   Managed installs never see this tab (gated on health.managed in
   SettingsModal) — there the container already holds the keys. */
const SELF_HOST_PROVIDERS = [
  { id: 'openrouter', label: 'OpenRouter', env: 'OPENROUTER_API_KEY',
    where: 'openrouter.ai/keys', note: 'free open-weights models · no card needed to start' },
  { id: 'groq', label: 'Groq', env: 'GROQ_API_KEY',
    where: 'console.groq.com/keys', note: 'fastest free tier' },
  { id: 'gemini-api', label: 'Google Gemini', env: 'GEMINI_API_KEY',
    where: 'aistudio.google.com/apikey', note: 'generous free tier' },
];

function ConnectionsPanel() {
  const [drivers, setDrivers] = useStateM(null);   // null = still probing
  const [err, setErr] = useStateM('');
  useEffectM(() => {
    let dead = false;
    (async () => {
      try {
        const r = await CafresoHQClient.agentDrivers(true);
        if (!dead) setDrivers((r && r.drivers) || []);
      } catch (e) { if (!dead) { setErr(String((e && e.message) || e)); setDrivers([]); } }
    })();
    return () => { dead = true; };
  }, []);
  const detectOf = (id) => {
    const d = (drivers || []).find(x => x.id === id);
    return (d && d.detect) || null;
  };
  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>ON THIS MACHINE</h4>
        <div className="muted" style={{ lineHeight: 1.6, marginBottom: 8 }}>
          Coworkers run on brains you already have. Anything found here can be
          hired at the front desk.
        </div>
        {drivers === null && <div className="muted">Checking…</div>}
        {err && <div className="tiny" style={{ color: '#c44' }}>Couldn’t check: {err}</div>}
        {drivers !== null && ['claude-code', 'codex', 'gemini', 'ollama', 'lmstudio'].map(id => {
          const det = detectOf(id);
          if (!det) return null;
          /* A local daemon counts as live only on a real probe
             (detect.version === 'reachable') — hire.jsx uses the same rule,
             because `installed` is true for these from the default URL
             alone. But "not found on this machine" is the wrong SENTENCE
             for that state: LM Studio may well be installed and simply not
             running, and telling someone their software is absent when it
             is merely closed sends them to a download page for something
             they already have. Say which it is. */
          const isDaemon = id === 'ollama' || id === 'lmstudio';
          const live = isDaemon ? det.version === 'reachable' : !!det.installed;
          const label = { 'claude-code': 'Claude Code', codex: 'Codex', gemini: 'Gemini CLI',
                          ollama: 'Ollama', lmstudio: 'LM Studio' }[id];
          const offText = isDaemon
            ? (det.installed ? 'not answering — start it and reopen this' : 'not running on this machine')
            : 'not found on this machine';
          return (
            <div className="row-knob" key={id}>
              <div>
                <div className="lbl">{label}</div>
                <div className="sub">
                  {live
                    ? (det.authenticated ? 'found · signed in' : 'found · needs a sign-in before its first task')
                    : offText}
                </div>
              </div>
              <span className="tiny">
                {live ? (det.authenticated ? '● ready' : '● sign in') : (isDaemon ? '○ offline' : '○ absent')}
              </span>
            </div>
          );
        })}
      </div>
      <div className="cb-panel">
        <h4>CLOUD KEYS</h4>
        <div className="muted" style={{ lineHeight: 1.6, marginBottom: 8 }}>
          Optional. Set one as an environment variable where you start HQ, then
          restart it — the key stays on your machine and never passes through
          this page.
        </div>
        {SELF_HOST_PROVIDERS.map(p => {
          const det = detectOf(p.id);
          const on = !!(det && det.authenticated);
          return (
            <div className="row-knob" key={p.id} style={{ alignItems: 'flex-start' }}>
              <div>
                <div className="lbl">{p.label}</div>
                <div className="sub" style={{ maxWidth: 300 }}>
                  {on
                    ? 'connected — hire them at the front desk'
                    : <>set <code>{p.env}</code> · key from {p.where}<br/>{p.note}</>}
                </div>
              </div>
              <span className="tiny" style={{ whiteSpace: 'nowrap' }}>{on ? '● connected' : '○ not set'}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* Tool chips shown in Hire + Roster. The wallet tool only appears when the
   Money module is on — with money off, agents shouldn't even be offerable a
   wallet (the runtime gate in hq-runtime.jsx enforces the same rule). */
const visibleToolsCatalog = () =>
  HQ.TOOLS_CATALOG.filter(t => t.id !== 'wallet' || (window.hqMoneyOn && window.hqMoneyOn()));

const WALLET_TOKEN_DECIMALS = { ICP: 8, ckUSDT: 6, ckUNI: 18, sGLDT: 8, nanas: 8 };
function toBaseUnits(whole, decimals) {
  const s = String(whole == null ? '' : whole).trim();
  if (!s || isNaN(Number(s))) return '0';
  const neg = s.startsWith('-'); const body = neg ? s.slice(1) : s;
  const [i, f = ''] = body.split('.');
  const frac = (f + '0'.repeat(decimals)).slice(0, decimals);
  const digits = ((i || '0') + frac).replace(/^0+(?=\d)/, '') || '0';
  return (neg ? '-' : '') + digits;
}
function fromBaseUnits(raw, decimals) {
  try {
    const n = BigInt(raw);
    const base = BigInt(10) ** BigInt(decimals);
    const int = n / base; const frac = n % base;
    const fracStr = frac.toString().padStart(decimals, '0').replace(/0+$/, '');
    return fracStr ? `${int}.${fracStr}` : `${int}`;
  } catch { return '0'; }
}

function AgentWalletCard({ agent }) {
  const [policy, setPolicy] = useStateM(null);
  const [bals, setBals] = useStateM(null);
  const [busy, setBusy] = useStateM('');
  const [msg, setMsg] = useStateM('');
  const [capTok, setCapTok] = useStateM('ICP');
  const [capAmt, setCapAmt] = useStateM('0.1');
  const [capHrs, setCapHrs] = useStateM('24');
  const [fundTok, setFundTok] = useStateM('ICP');
  const [fundAmt, setFundAmt] = useStateM('0.05');
  const chain = () => CafresoHQChain;
  const agentId = agent.id || agent.name;

  // Payroll (Sprint 2): a standing salary/refill the state canister's timer
  // pays from the user's main account under the signed ICRC-2 budget below.
  const [sal, setSal] = useStateM(null);
  const [payMode, setPayMode] = useStateM('salary');
  const [payAmt, setPayAmt] = useStateM('0.01');
  const [payTok, setPayTok] = useStateM('ICP');
  const [payHrs, setPayHrs] = useStateM('24');
  const [payWm, setPayWm] = useStateM('0.05');

  const load = async () => {
    try {
      const p = await chain().wallet.policy(agentId);
      setPolicy(p || null);
      if (p) {
        setCapTok(p.token);
        setCapAmt(fromBaseUnits(p.spendCap, WALLET_TOKEN_DECIMALS[p.token] ?? 8));
        setCapHrs(String(Math.round((p.windowSecs || 0) / 3600) || 24));
      }
    } catch (_e) { /* not deployed / not signed in — leave defaults */ }
    try {
      const pr = await chain().payroll.list();
      const s = (pr.salaries || []).find(x => x.agentId === agentId) || null;
      setSal(s);
      if (s) {
        const dec = WALLET_TOKEN_DECIMALS[s.token] ?? 8;
        setPayTok(s.token); setPayMode(s.mode);
        setPayAmt(fromBaseUnits(s.amount, dec));
        setPayHrs(String(Math.round(s.periodSecs / 3600) || 24));
        setPayWm(fromBaseUnits(s.lowWatermark, dec));
      }
    } catch (_e) { /* canister not upgraded yet — payroll row still usable later */ }
  };
  useEffectM(() => { load(); }, []);

  const refreshBalances = async () => {
    setBusy('bal'); setMsg('');
    try { setBals(await chain().wallet.balances(agentId, Object.keys(WALLET_TOKEN_DECIMALS))); }
    catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const saveCap = async () => {
    setBusy('cap'); setMsg('');
    try {
      const dec = WALLET_TOKEN_DECIMALS[capTok] ?? 8;
      await chain().wallet.put({
        agentId, token: capTok, spendCap: toBaseUnits(capAmt, dec),
        windowSecs: Math.max(0, Math.round(parseFloat(capHrs || '0') * 3600)),
        paused: policy?.paused || false,
      });
      setMsg('Saved.'); await load();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const fund = async () => {
    // Real money leaves the user's main account here — restate the exact
    // amount and destination and make them say yes.
    const amt = String(fundAmt || '').trim();
    if (!amt || isNaN(Number(amt)) || Number(amt) <= 0) { setMsg('Enter a valid amount first.'); return; }
    if (!(await window.hqConfirm(
      `Send ${amt} ${fundTok} from YOUR main account to ${agent.name}'s agent wallet?\n\nThis is a real on-chain transfer.`,
      { okLabel: `Send ${amt} ${fundTok}` }))) return;
    // Ledger transfers take a few seconds — say so, or the click feels dead.
    setBusy('fund'); setMsg('Funding — waiting for the ledger…');
    try {
      // Tell the tip watcher this credit is OURS before it can land on-chain —
      // a self-funded top-up must not rain coins as a "tip".
      try { window.dispatchEvent(new CustomEvent('cafresohq:walletLocalMove', { detail: { agentId } })); } catch (_e) {}
      const r = await chain().wallet.fund(agentId, fundTok, fundAmt);
      setMsg(r && r.ok != null ? `Funded (block ${r.ok}).` : (r && r.err ? `Fund failed: ${r.err}` : 'Fund sent.'));
      await refreshBalances();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const togglePause = async () => {
    setBusy('pause');
    try {
      const dec = WALLET_TOKEN_DECIMALS[policy?.token || capTok] ?? 8;
      await chain().wallet.put({
        agentId, token: policy?.token || capTok,
        spendCap: policy?.spendCap || toBaseUnits(capAmt, dec),
        windowSecs: policy?.windowSecs || Math.round(parseFloat(capHrs || '0') * 3600),
        paused: !(policy?.paused),
      });
      await load();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };

  const savePay = async () => {
    setBusy('pay'); setMsg('');
    try {
      await chain().payroll.put({
        agentId, token: payTok, amount: parseFloat(payAmt) || 0,
        periodSecs: Math.max(60, Math.round(parseFloat(payHrs || '0') * 3600)),
        lowWatermark: payMode === 'refill' ? (parseFloat(payWm) || 0) : 0,
        mode: payMode, active: true,
      });
      setMsg('Payroll saved — first run in one period. Make sure a payroll budget is signed below.');
      await load();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const payNow = async () => {
    if (!(await window.hqConfirm(
      `Run payroll for ${agent.name} right now?\n\nPays ${payAmt} ${payTok} from your signed payroll budget (the budget cap still applies).`,
      { okLabel: 'Pay now' }))) return;
    setBusy('paynow'); setMsg('Running payroll — waiting for the chain…');
    try {
      const r = await chain().payroll.run(agentId);
      setMsg(`Payroll run: ${r}`);
      await load(); await refreshBalances();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const stopPay = async () => {
    if (!(await window.hqConfirm(
      `Stop payroll for ${agent.name}?\n\nNo further automatic payments will run. The agent's balance is untouched.`,
      { okLabel: 'Stop payroll', danger: true }))) return;
    setBusy('paystop'); setMsg('');
    try { await chain().payroll.remove(agentId); setSal(null); setMsg('Payroll stopped.'); }
    catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };

  const toks = Object.keys(WALLET_TOKEN_DECIMALS);
  return (
    <div className="cb-panel icp-wallet-card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="lbl">👛 {agent.name} <span className="tiny">· {agent.role}</span></span>
        {policy && (
          <button className={`px-btn ${policy.paused ? 'primary' : 'secondary'}`} style={{ fontSize: 8 }} disabled={busy === 'pause'} onClick={togglePause}>
            {policy.paused ? '▶ RESUME' : '⏸ PAUSE'}
          </button>
        )}
      </div>
      {!policy && <div className="sub" style={{ marginTop: 4 }}>No wallet yet — set a spend cap to create one.</div>}
      <div className="stack" style={{ marginTop: 6 }}>
        <div className="row-knob icp-in-row">
          <span className="lbl">Spend cap</span>
          <input className="icp-in" style={{ width: 66 }} value={capAmt} onChange={e => setCapAmt(e.target.value)} />
          <select value={capTok} onChange={e => setCapTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
          <span className="tiny">per</span>
          <input className="icp-in" style={{ width: 40 }} value={capHrs} onChange={e => setCapHrs(e.target.value)} />
          <span className="tiny">h</span>
          <button className="px-btn primary" style={{ fontSize: 8 }} disabled={busy === 'cap'} onClick={saveCap}>{policy ? 'SAVE' : 'CREATE'}</button>
        </div>
        <div className="row-knob icp-in-row">
          <span className="lbl">Fund</span>
          <input className="icp-in" style={{ width: 66 }} value={fundAmt} onChange={e => setFundAmt(e.target.value)} />
          <select value={fundTok} onChange={e => setFundTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
          <button className="px-btn" style={{ fontSize: 8 }} disabled={busy === 'fund'} onClick={fund}>⬆ FUND</button>
        </div>
        <div className="row-knob">
          <span className="lbl">Balances</span>
          <button className="px-btn secondary" style={{ fontSize: 8 }} disabled={busy === 'bal'} onClick={refreshBalances}>↻ REFRESH</button>
        </div>
        {bals && (
          <div className="tiny icp-bal-grid">
            {toks.map(t => <div key={t}>{t}: <b>{bals[t] == null ? '—' : fromBaseUnits(bals[t], WALLET_TOKEN_DECIMALS[t])}</b></div>)}
          </div>
        )}
        <div className="row-knob icp-in-row" style={{ flexWrap: 'wrap' }}>
          <span className="lbl">Payroll</span>
          <select value={payMode} onChange={e => setPayMode(e.target.value)}>
            <option value="salary">salary</option>
            <option value="refill">refill</option>
          </select>
          <input className="icp-in" style={{ width: 56 }} value={payAmt} onChange={e => setPayAmt(e.target.value)} />
          <select value={payTok} onChange={e => setPayTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
          <span className="tiny">per</span>
          <input className="icp-in" style={{ width: 40 }} value={payHrs} onChange={e => setPayHrs(e.target.value)} />
          <span className="tiny">h</span>
          {payMode === 'refill' && (<>
            <span className="tiny">below</span>
            <input className="icp-in" style={{ width: 56 }} value={payWm} onChange={e => setPayWm(e.target.value)} />
          </>)}
          <button className="px-btn primary" style={{ fontSize: 8 }} disabled={busy === 'pay'} onClick={savePay}>{sal ? 'SAVE' : 'START'}</button>
          {sal && <button className="px-btn" style={{ fontSize: 8 }} disabled={busy === 'paynow'} onClick={payNow}>⚡ NOW</button>}
          {sal && <button className="px-btn danger" style={{ fontSize: 8 }} disabled={busy === 'paystop'} onClick={stopPay}>✕ STOP</button>}
        </div>
        {sal && sal.stalledSince && (
          <div className="tiny" style={{ color: '#c44' }}>
            ⚠ PAYROLL STALLED ({sal.lastResult}) — sign or top up the payroll budget below, then ⚡ NOW.
          </div>
        )}
        {sal && !sal.stalledSince && sal.lastResult && (
          <div className="tiny" style={{ opacity: .7 }}>payroll: {sal.lastResult} · {sal.mode}</div>
        )}
        {msg && <div className="tiny" style={{ color: 'var(--accent-leaf)' }}>{msg}</div>}
      </div>
    </div>
  );
}

/* Payroll budget = the ONE real signature (icrc2_approve, spender = the state
   canister). It is the hard ceiling on everything the payroll timer can move;
   the shell shows a confirm dialog before signing. Start tiny (0.05 ICP). */
function PayrollBudgetPanel() {
  const [allow, setAllow] = useStateM(null);
  const [rows, setRows] = useStateM([]);
  const [paused, setPaused] = useStateM(false);
  const [tok, setTok] = useStateM('ICP');
  const [amt, setAmt] = useStateM('0.05');
  const [days, setDays] = useStateM('30');
  const [busy, setBusy] = useStateM('');
  const [msg, setMsg] = useStateM('');
  const chain = () => CafresoHQChain;

  const load = async () => {
    try {
      const [a, po, pr] = await Promise.all([
        chain().payroll.allowance(tok),
        chain().payroll.payouts(),
        chain().payroll.list(),
      ]);
      setAllow(a || null);
      setRows((po || []).slice(-6).reverse());
      setPaused(!!pr.paused);
    } catch (_e) { /* canister not upgraded yet */ }
  };
  useEffectM(() => { load(); }, [tok]);

  const approve = async () => {
    setBusy('appr'); setMsg('');
    try {
      const r = await chain().payroll.approve(tok, parseFloat(amt) || 0, parseInt(days, 10) || 0);
      setMsg(r.status === 'ok' ? `Budget signed (block ${r.block}).`
        : r.status === 'declined' ? 'Declined in the shell.'
        : `Failed: ${r.error || '?'}`);
      await load();
    } catch (e) { setMsg(String(e.message || e)); }
    setBusy('');
  };
  const togglePause = async () => {
    try { await chain().payroll.pause(!paused); setPaused(!paused); }
    catch (e) { setMsg(String(e.message || e)); }
  };

  const dec = (t) => WALLET_TOKEN_DECIMALS[t] ?? 8;
  const toks = Object.keys(WALLET_TOKEN_DECIMALS);
  return (
    <div className="cb-panel icp-wallet-card">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center' }}>
        <span className="lbl">🏦 PAYROLL BUDGET</span>
        <button className={`px-btn ${paused ? 'primary' : 'secondary'}`} style={{ fontSize: 8 }} onClick={togglePause}>
          {paused ? '▶ RESUME PAYROLL' : '⏸ PAUSE PAYROLL'}
        </button>
      </div>
      <div className="sub" style={{ marginTop: 4 }}>
        One signature caps everything payroll can move. Allowance left:{' '}
        <b>{allow ? `${fromBaseUnits(allow.allowance, dec(tok))} ${tok}` : '— none signed —'}</b>
        {allow?.expiresAtNs ? <span className="tiny"> (expires {new Date(Number(BigInt(allow.expiresAtNs) / BigInt(1000000))).toLocaleDateString()})</span> : null}
      </div>
      <div className="row-knob icp-in-row" style={{ marginTop: 6 }}>
        <span className="lbl">Approve</span>
        <input className="icp-in" style={{ width: 66 }} value={amt} onChange={e => setAmt(e.target.value)} />
        <select value={tok} onChange={e => setTok(e.target.value)}>{toks.map(t => <option key={t} value={t}>{t}</option>)}</select>
        <span className="tiny">for</span>
        <input className="icp-in" style={{ width: 40 }} value={days} onChange={e => setDays(e.target.value)} />
        <span className="tiny">days</span>
        <button className="px-btn primary" style={{ fontSize: 8 }} disabled={busy === 'appr'} onClick={approve}>✍ SIGN</button>
      </div>
      <div className="tiny" style={{ opacity: .7, marginTop: 2 }}>
        Replaces the previous budget. Each payout also burns one ledger fee of allowance — size it as pay + runs × fee.
      </div>
      {rows.length > 0 && (
        <div className="stack" style={{ marginTop: 6 }}>
          <span className="lbl">Recent payouts</span>
          {rows.map(p => (
            <div key={p.key} className="tiny">
              {p.status === 'paid' ? '✓' : p.status === 'pending' ? '…' : '✗'}{' '}
              {p.agentId} · {fromBaseUnits(p.amount, dec(p.token))} {p.token} · {p.status}
              {p.blockIndex != null ? ` · block ${p.blockIndex}` : ''}
            </div>
          ))}
        </div>
      )}
      {msg && <div className="tiny" style={{ color: 'var(--accent-leaf)' }}>{msg}</div>}
    </div>
  );
}

function IcpServicesPanel({ agents }) {
  const [installed, setInstalled] = useStateM(() => {
    try { return CafresoHQClient.getSettings().icpServices || {}; } catch (_e) { return {}; }
  });
  const [moneyOn, setMoneyOn] = useStateM(() => !!(window.hqMoneyOn && window.hqMoneyOn()));
  const [available, setAvailable] = useStateM(false);
  const [pausedAll, setPausedAll] = useStateM(false);
  const [loading, setLoading] = useStateM(true);
  const [err, setErr] = useStateM('');
  const chain = () => CafresoHQChain;

  const load = async () => {
    setLoading(true); setErr('');
    const avail = !!(chain() && chain().isAvailable());
    setAvailable(avail);
    if (!avail) { setLoading(false); return; }
    try {
      const flags = await chain().services.list();
      const map = { ...installed }; (flags || []).forEach(f => { map[f.serviceId] = !!f.enabled; });
      setInstalled(map);
      CafresoHQClient.setSettings({ icpServices: map });
      setPausedAll(await chain().wallet.pausedAll());
    } catch (e) { setErr(String(e.message || e)); }
    setLoading(false);
  };
  useEffectM(() => { load(); }, []);

  /* Money master switch. Both directions confirm in plain language; disabling
     ALSO best-effort-pauses all agent spending so nothing moves while the UI
     is hidden. Funds are never touched — the on-chain install flag stays set
     so re-enabling restores everything exactly as it was. */
  const toggleMoney = async () => {
    if (!moneyOn) {
      const ok = await window.hqConfirm(
        'Turn on Money & Payments?\n\n'
        + 'How it stays safe:\n'
        + '• Agents can NEVER take your funds — every allowance is signed by you, in your wallet.\n'
        + '• Each agent spends only within a cap you set; anything over asks you first.\n'
        + '• One global pause switch stops all agent spending instantly.\n'
        + '• Turning this off later hides money features and pauses spending — balances stay yours, on-chain.\n\n'
        + 'Tip: start tiny (0.05 ICP) until you trust the flow.',
        { okLabel: 'Turn on', cancelLabel: 'Not now' });
      if (!ok) return;
      CafresoHQClient.setSettings({ moneyEnabled: true });
      setMoneyOn(true);
      if (available) {
        try {
          await chain().services.set('wallet', true, '');
          const map = { ...installed, wallet: true };
          setInstalled(map);
          CafresoHQClient.setSettings({ icpServices: map });
        } catch (e) { setErr(String(e.message || e)); }
      }
      return;
    }
    const ok = await window.hqConfirm(
      'Turn off Money & Payments?\n\n'
      + '• All agent spending is paused immediately.\n'
      + '• Balances are NOT deleted — they stay on-chain under your Internet Identity and reappear when you turn this back on.\n'
      + '• Scheduled payroll stops running.',
      { okLabel: 'Turn off', cancelLabel: 'Keep on' });
    if (!ok) return;
    if (available) {
      try { await chain().wallet.pauseAll(true); setPausedAll(true); } catch (_e) { /* best-effort */ }
    }
    CafresoHQClient.setSettings({ moneyEnabled: false });
    setMoneyOn(false);
  };

  const togglePublish = async () => {
    const next = !installed.publish;
    const map = { ...installed, publish: next };
    // Publish works without the bridge (container /fs path) — always store
    // locally; flip the on-chain flag too when the shell is reachable.
    setInstalled(map);
    CafresoHQClient.setSettings({ icpServices: map });
    if (available) {
      try { await chain().services.set('publish', next, ''); }
      catch (e) { setErr(String(e.message || e)); }
    }
  };

  const togglePauseAll = async () => {
    try { const n = !pausedAll; await chain().wallet.pauseAll(n); setPausedAll(n); }
    catch (e) { setErr(String(e.message || e)); }
  };

  const walletAgents = (agents || []).filter(a => (a.tools || []).includes('wallet'));

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>MODULES · OPTIONAL ADD-ONS</h4>
        <div className="sub" style={{ lineHeight: 1.6, marginBottom: 6 }}>
          Your HQ runs the same everywhere — laptop, cloud, or on-chain. Modules
          add capabilities on top; everything below is opt-in and off by default.
        </div>
        {err && <div className="tiny" style={{ color: '#c44' }}>{err}</div>}
        {loading && available && <div className="muted">Loading…</div>}
        <div className="stack">
          {/* Money — the master switch, styled as a first-class module card */}
          <div className="row-knob" style={{ alignItems: 'flex-start' }}>
            <div style={{ maxWidth: 300 }}>
              <div className="lbl">💰 Money &amp; Payments <span className="tiny" style={{ opacity: .7 }}>{moneyOn ? '· ON' : '· OFF'}</span></div>
              <div className="sub" style={{ marginTop: 2 }}>
                Agents can hold tokens (ICP, ckUSDT, …), earn tips and payroll, and spend
                within caps you set. Entirely optional — HQ works the same without it.
              </div>
              <div className="tiny" style={{ marginTop: 3, opacity: .75 }}>
                🔒 Non-custodial: you sign every allowance; agents can only request.
                Turning off pauses spending and hides money UI — funds are never touched.
              </div>
            </div>
            <div className={`pxswitch ${moneyOn ? 'on' : ''}`} role="switch" aria-checked={moneyOn} onClick={toggleMoney}><div className="nub" /></div>
          </div>

          <div className="row-knob" style={{ alignItems: 'flex-start' }}>
            <div style={{ maxWidth: 300 }}>
              <div className="lbl">🚀 Publish to Web <span className="tiny" style={{ opacity: .7 }}>{installed.publish ? '· ON' : '· OFF'}</span></div>
              <div className="sub" style={{ marginTop: 2 }}>
                Agents publish sites they build and hand back a verifiable link your users can click.
              </div>
            </div>
            <div className={`pxswitch ${installed.publish ? 'on' : ''}`} role="switch" aria-checked={!!installed.publish} onClick={togglePublish}><div className="nub" /></div>
          </div>
        </div>
      </div>

      {moneyOn && !available && (
        <div className="cb-panel">
          <h4>💰 MONEY &amp; PAYMENTS</h4>
          <div className="muted" style={{ lineHeight: 1.6 }}>
            The module is on, but balances and sends need your Internet Identity, which
            lives in the CafresoHQ shell. Open your HQ at <b>ai.cafreso.com</b> to manage
            wallets, caps, and payroll. Until then agents cannot move any funds.
          </div>
        </div>
      )}

      {moneyOn && available && (
        <div className="cb-panel">
          <h4>💰 AGENT WALLETS</h4>
          <div className="row-knob">
            <div><div className="lbl">Pause all agent spending</div><div className="sub">Global kill switch — blocks every agent send</div></div>
            <div className={`pxswitch ${pausedAll ? 'on' : ''}`} role="switch" aria-checked={pausedAll} onClick={togglePauseAll}><div className="nub" /></div>
          </div>
          {pausedAll && <div className="tiny" style={{ color: '#a9710f' }}>⏸ Everything is paused — no agent can spend until you resume.</div>}
          <PayrollBudgetPanel />
          {walletAgents.length === 0
            ? <div className="muted" style={{ marginTop: 6 }}>Grant an agent the <b>ICP Wallet</b> tool in <b>Roster</b> to give it a wallet.</div>
            : walletAgents.map(a => <AgentWalletCard key={a.id} agent={a} />)}
        </div>
      )}
    </div>
  );
}

/* Theme presets — color skins + "vocabulary" reskins that rename the whole
   OS metaphor (agents→baristas/brokers). Kept in sync with the command
   palette entries in app.jsx and THEME_VOCAB in ui.jsx. */
const THEME_PRESETS = [
  { id: 'default',      name: '🏢 Pixel Office',   sub: 'the classic HQ' },
  { id: 'sepia',        name: '📜 Sepia',          sub: 'warm parchment tones' },
  { id: 'solarized',    name: '🌊 Solarized',      sub: 'cool teal & amber' },
  { id: 'dracula',      name: '🦇 Dracula',        sub: 'dark purple neon' },
  { id: 'highcontrast', name: '◐ High Contrast',   sub: 'maximum legibility' },
  { id: 'coffeeshop',   name: '☕ Coffee Shop',     sub: 'agents become baristas' },
  { id: 'wallstreet',   name: '📈 Trading Floor',  sub: 'agents become brokers' },
];
const DENSITY_PRESETS = [
  { id: 'compact',     name: 'Compact' },
  { id: 'comfortable', name: 'Comfortable' },
  { id: 'spacious',    name: 'Spacious' },
];

function SettingsModal({ open, onClose, agents, onDismiss, onUpdateAgent, scanlines, setScanlines, sound, setSound, night, setNight, theme, setTheme, density, setDensity, initialTab, usageTokens = 0 }) {
  // Last-used tab survives reopen (and reload) — small thing, big QoL.
  const [tab, _setTab] = useStateM(() => {
    try {
      const t = localStorage.getItem('hq:settingsTab');
      if (t && SETTINGS_TABS.some(x => x.id === t)) return t;
    } catch (_e) {}
    return SETTINGS_TABS[0].id;
  });
  const setTab = (t) => {
    const id = SETTINGS_TAB_ALIAS[t] || t;
    _setTab(id);
    try { localStorage.setItem('hq:settingsTab', id); } catch (_e) {}
  };
  const [q, setQ] = useStateM('');
  const [selected, setSelected] = useStateM(agents[0]?.id || null);
  const sel = agents.find(a => a.id === selected) || agents[0];

  // Live status for the nav rail: provider key state, CLI install count,
  // backend reachability. Refetched each time the modal opens.
  const [navStat, setNavStat] = useStateM({});
  /* null until /health answers. CONNECTIONS is for self-hosted installs
     only — on a managed container Cafreso holds the keys, so a panel about
     setting env vars would be noise at best and misleading at worst.
     Starts null (not false) so the tab doesn't flash in and out on a
     managed box during the probe. */
  const [managed, setManaged] = useStateM(null);
  useEffectM(() => {
    if (!open) return;
    let live = true;
    const C = CafresoHQClient;
    (async () => {
      // Managed premium: the only live status the nav needs is "is my
      // container up" — provider keys and CLI installs are Cafreso's job now.
      const stat = {};
      try { stat.backend = !!(await C.backendHealth()); } catch (_e) { stat.backend = false; }
      /* backendHealth() answers a BOOLEAN (reachable or not) — it does not
         hand back the body. The managed flag needs the body, so fetch it
         separately; AccountTab already does exactly this for the same
         reason. Leave `managed` null on any failure so a box we cannot
         classify never gets shown a panel aimed at the other kind. */
      let mg = null;
      try {
        const r = await fetch((window._API_BASE || '') + '/health',
          { cache: 'no-store', credentials: 'include' });
        const j = r.ok ? await r.json().catch(() => null) : null;
        if (j && typeof j === 'object') mg = !!j.managed;
      } catch (_e) { mg = null; }
      if (live) { setNavStat(stat); setManaged(mg); }
    })();
    return () => { live = false; };
  }, [open]);
  const visibleTabs = SETTINGS_TABS.filter(t => t.id !== 'connections' || managed === false);
  /* A managed box whose last-used tab was CONNECTIONS (self-hosted before,
     or the flag flipped) would land on a hidden tab and render an empty
     body — no nav item lit, nothing shown, no way to tell what went wrong.
     Fall back to the first visible tab instead. */
  const activeTab = visibleTabs.some(t => t.id === tab) ? tab : visibleTabs[0].id;

  // Deep-link: jump to a requested tab each time the modal is (re)opened
  // (e.g. the "no API key" chip opens straight to CONNECTIONS).
  const prevOpenRef = useRefM(false);
  useEffectM(() => {
    if (open && !prevOpenRef.current && initialTab) setTab(initialTab);
    prevOpenRef.current = open;
  }, [open, initialTab]);

  if (!open) return null;

  const update = (patch) => {
    if (!sel) return;
    onUpdateAgent(sel.id, patch);
  };

  // All query terms must match label+hint+kw (case-insensitive).
  const terms = q.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const hits = terms.length
    ? SETTINGS_INDEX.filter(e => {
        const hay = (e.label + ' ' + e.hint + ' ' + e.kw).toLowerCase();
        return terms.every(t => hay.includes(t));
      })
    : [];

  const navDot = (t) => {
    if (t.id === 'account' && navStat.backend !== undefined)
      return <span className={`sn-dot ${navStat.backend ? 'ok' : 'err'}`} title={navStat.backend ? 'office online' : 'office offline'}/>;
    return null;
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="SETTINGS"
      subtitle="preferences · connections · runtime"
      size="xl"
      footer={
        <>
          <div className="hint" style={{marginRight: 'auto'}}>Changes save automatically.</div>
          <button className="px-btn primary" onClick={onClose}>DONE</button>
        </>
      }
    >
      <div className="settings-shell">
        <aside className="settings-nav">
          <input className="settings-search" type="search" placeholder="🔍 search settings…"
            value={q} onChange={e => setQ(e.target.value)} aria-label="Search settings"/>
          {visibleTabs.map(t => (
            <button key={t.id} className={`sn-item ${activeTab===t.id && !terms.length ? 'active' : ''}`}
              onClick={() => { setQ(''); setTab(t.id); }}>
              <span className="sn-ico">{t.ico}</span>
              <span className="sn-txt">
                <span className="sn-label">{t.label}</span>
                <span className="sn-desc">{t.desc}</span>
              </span>
              {navDot(t)}
            </button>
          ))}
        </aside>
        <div className="settings-body">
          {terms.length > 0 && (
            <div className="cb-panel">
              <h4>SEARCH · {hits.length} RESULT{hits.length === 1 ? '' : 'S'}</h4>
              {hits.length === 0 && <div className="muted">Nothing matches “{q}”.</div>}
              {hits.map((e, i) => {
                const t = SETTINGS_TABS.find(x => x.id === e.tab);
                return (
                  <div key={i} className="row-knob" style={{cursor:'pointer'}}
                    onClick={() => { setQ(''); setTab(e.tab); }}>
                    <div>
                      <div className="lbl">{t ? t.ico : ''} {e.label}</div>
                      <div className="sub">{e.hint}</div>
                    </div>
                    <span className="tiny" style={{whiteSpace:'nowrap'}}>{t ? t.label : e.tab} →</span>
                  </div>
                );
              })}
            </div>
          )}

          {!terms.length && activeTab === 'icp-services' && (
            <IcpServicesPanel agents={agents} />
          )}

          {!terms.length && activeTab === 'agents' && (
            <div className="control-board">
              <div className="cb-panel">
                <h4>ROSTER</h4>
                <div className="stack">
                  {agents.length === 0 && <div className="muted">No coworkers hired.</div>}
                  {agents.map(a => (
                    <div key={a.id} className={`row`} style={{
                      padding: '6px 8px',
                      background: selected===a.id ? 'var(--accent-sun)' : 'transparent',
                      border: '2px solid ' + (selected===a.id?'var(--ink)':'transparent'),
                      cursor: 'pointer',
                    }} onClick={()=>setSelected(a.id)}>
                      <Sprite data={a.color} scale={1.5}/>
                      <div className="grow" style={{display:'flex',flexDirection:'column',lineHeight:1.1}}>
                        <span style={{fontFamily:'Press Start 2P',fontSize:9}}>{a.name}</span>
                        <span className="tiny">{a.role}</span>
                      </div>
                      <button className="px-btn danger" style={{fontSize:8,padding:'6px 8px'}} onClick={(e)=>{e.stopPropagation(); onDismiss(a.id);}}>LET GO</button>
                    </div>
                  ))}
                </div>
              </div>
              <div className="cb-panel">
                <h4>{sel ? `${sel.name.toUpperCase()} · CONFIG` : 'NO AGENT'}</h4>
                {sel && (
                  <div className="stack">
                    <div className="row-knob">
                      <span className="lbl">Model</span>
                      <ModelPicker value={sel.model} onChange={v=>update({model:v})}/>
                    </div>
                    <div className="row-knob" style={{flexDirection:'column',alignItems:'stretch',gap:4}}>
                      <div className="row" style={{justifyContent:'space-between'}}><span className="lbl">Temperature</span><span className="sub">{sel.temperature?.toFixed(2)}</span></div>
                      <input type="range" className="pxslider" min="0" max="1" step="0.05" value={sel.temperature||0} onChange={e=>update({temperature:parseFloat(e.target.value)})}/>
                    </div>
                    <div style={{marginTop:6}}>
                      <div className="sub" style={{marginBottom:6}}>TOOLS</div>
                      <div className="tool-grid">
                        {visibleToolsCatalog().map(t => (
                          <div key={t.id} className={`tool-chk ${sel.tools.includes(t.id)?'on':''}`}
                               onClick={()=>update({tools: sel.tools.includes(t.id)?sel.tools.filter(x=>x!==t.id):[...sel.tools,t.id]})}>
                            <div className="box"/><span>{t.label}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div className="row-knob" style={{marginTop:6}}>
                      <div>
                        <div className="lbl">Tool call format</div>
                        <div className="sub">JSON = reliable for capable models; bracket = fallback for local OSS</div>
                      </div>
                      <select value={sel.toolFormat || 'auto'} onChange={e => update({ toolFormat: e.target.value })}>
                        <option value="auto">Auto-detect</option>
                        <option value="json">JSON ({"<<<TOOL>>>"})</option>
                        <option value="bracket">Bracket [TOOL: arg]</option>
                      </select>
                    </div>
                    <div className={`row-knob elevated-opt ${sel.elevated ? 'on' : ''}`} style={{marginTop:8,alignItems:'flex-start'}}>
                      <div>
                        <div className="lbl" style={{color: sel.elevated ? '#c44' : 'inherit'}}>🛡 File &amp; shell access</div>
                        <div className="sub" style={{maxWidth:240,marginTop:2}}>
                          Has file and shell access. DMs blocked, missions opt-in, every action logged.
                        </div>
                      </div>
                      <div className={`pxswitch ${sel.elevated?'on':''}`} onClick={async ()=>{
                        if (!sel.elevated) {
                          if (!(await window.hqConfirm(
                            `Grant ${sel.name} COMPUTER ACCESS?\n\n` +
                            `They will be backed by an elevated CafresoHQ session that can read/write files and run shell commands on this machine. ` +
                            `DMs from other agents will be blocked, missions require explicit authorization, and every tool call is logged.\n\n` +
                            `Continue?`, { danger: true }
                          ))) return;
                        }
                        update({ elevated: !sel.elevated });
                      }}><div className="nub"/></div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          {!terms.length && activeTab === 'appearance' && (
            <div className="control-board">
              {setTheme && (
                <div className="cb-panel">
                  <h4>MAKE IT YOURS</h4>
                  <div className="sub" style={{ lineHeight: 1.6, marginBottom: 6 }}>
                    Reskin the whole OS — some presets change the vocabulary too
                    (your agents become baristas or brokers, the office becomes their floor).
                  </div>
                  <div className="tool-grid">
                    {THEME_PRESETS.map(t => (
                      <div key={t.id} className={`tool-chk ${theme === t.id ? 'on' : ''}`}
                           role="radio" aria-checked={theme === t.id}
                           onClick={() => setTheme(t.id)} title={t.sub}>
                        <div className="box" /><span>{t.name}</span>
                      </div>
                    ))}
                  </div>
                  <div className="tiny" style={{ marginTop: 4, opacity: .7 }}>
                    {(THEME_PRESETS.find(t => t.id === theme) || THEME_PRESETS[0]).sub}
                  </div>
                  {setDensity && (
                    <div className="row-knob" style={{ marginTop: 8 }}>
                      <div><div className="lbl">Density</div><div className="sub">how much breathing room the UI gets</div></div>
                      <div className="ws-seg">
                        {DENSITY_PRESETS.map(d => (
                          <button key={d.id} className={density === d.id ? 'on' : ''} onClick={() => setDensity(d.id)}>{d.name}</button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
              <div className="cb-panel">
                <h4>AMBIENCE</h4>
                <div className="row-knob">
                  <div><div className="lbl">Scanline overlay</div><div className="sub">soft CRT shimmer</div></div>
                  <div className={`pxswitch ${scanlines?'on':''}`} onClick={()=>setScanlines(!scanlines)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">Sound FX</div><div className="sub">pixel blips on action</div></div>
                  <div className={`pxswitch ${sound?'on':''}`} onClick={()=>setSound(!sound)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">{night ? '☀ Day Mode' : '☾ Night Mode'}</div><div className="sub">{night ? 'switch to warm pastels' : 'switch to dark pixel theme'}</div></div>
                  <div className={`pxswitch ${night?'on':''}`} onClick={()=>setNight(v=>!v)}><div className="nub"/></div>
                </div>
                <div className="row-knob">
                  <div><div className="lbl">Keyboard shortcuts</div><div className="sub">1–8 switch views · S settings · D theme · Ctrl+K palette</div></div>
                  <span className="tiny">press Ctrl+K</span>
                </div>
              </div>
            </div>
          )}

          {!terms.length && activeTab === 'account' && <AccountTab usageTokens={usageTokens} />}
          {/* managed === false, not just falsy: null means /health hasn't
              answered yet, and a managed box must never flash this panel. */}
          {!terms.length && activeTab === 'connections' && managed === false && <ConnectionsPanel />}
        </div>
      </div>
    </Modal>
  );
}

/* System tab — live backend/runtime visibility so "is it the key, the
   container, or the gateway?" is answerable from inside the app instead of
   the browser devtools. Read-only except the two action buttons. */
/* ACCOUNT — the managed-premium replacement for SYSTEM. Same /health probe,
   but speaks in plan/container/usage language instead of gateway internals.
   Everything a premium user might need when something feels off: is my HQ
   up, what brain am I on, what have I spent this session, and a one-click
   diagnostics copy for support. */
function AccountTab({ usageTokens = 0 }) {
  const [health, setHealth] = useStateM(null);   // null=loading · false=down · object=ok
  const [note, setNote] = useStateM('');
  const apiBase = (window._API_BASE || '');

  const load = async () => {
    try {
      const ctl = new AbortController();
      const t = setTimeout(() => ctl.abort(), 3000);
      let r;
      try { r = await fetch(apiBase + '/health', { cache: 'no-store', credentials: 'include', signal: ctl.signal }); }
      finally { clearTimeout(t); }
      const j = r.ok ? await r.json().catch(() => null) : null;
      setHealth(j && typeof j === 'object' ? j : false);
    } catch (_e) { setHealth(false); }
  };
  useEffectM(() => { load(); }, []);

  const copyDiag = async () => {
    const diag = {
      when: new Date().toISOString(),
      apiBase: apiBase || '(same origin)',
      health: health || 'unreachable',
      usageTokensSinceHire: usageTokens,   // NOT per-session — see the label above
      ua: navigator.userAgent,
      url: location.href.split('?')[0],
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(diag, null, 2));
      setNote('✓ diagnostics copied — paste into a support chat');
    } catch (_e) { setNote('copy failed — clipboard blocked'); }
  };

  const resetOnboarding = async () => {
    if (!(await window.hqConfirm('Replay the new-user guide on next reload?'))) return;
    try {
      const kill = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && /tourseen|gettingstarted|gsdismissed/i.test(k)) kill.push(k);
      }
      kill.forEach(k => localStorage.removeItem(k));
      setNote(`✓ onboarding reset (${kill.length} flag${kill.length === 1 ? '' : 's'} cleared) — reload to replay`);
    } catch (_e) { setNote('reset failed'); }
  };

  const dot = (on) => <span className={`sn-dot ${on ? 'ok' : 'err'}`} style={{position:'static', marginRight:6}}/>;
  const uptime = health && health.uptime_seconds
    ? (health.uptime_seconds >= 3600
        ? `${Math.floor(health.uptime_seconds / 3600)}h ${Math.floor((health.uptime_seconds % 3600) / 60)}m`
        : `${Math.floor(health.uptime_seconds / 60)}m`)
    : null;
  const fmtTokens = (n) => n >= 1000 ? `${(n / 1000).toFixed(1)}K` : String(n);

  /* "Cafreso HQ Premium ... active" was hardcoded here with no gate at
     all — shown identically whether /health said managed:true or
     managed:false. A bare `python3 serve.py` self-host (health.managed
     false, health.brain null — confirmed live) got told it had an ACTIVE
     PAID plan with a brain "included", which is the exact fabricated-
     state failure this panel had already been caught doing twice before
     (see the "false span" note below, on Usage) — just not here yet.
     Self-hosted installs are the audience north-star §1 names first
     ("bring your own subscriptions"), so this is the first tab many of
     them will ever open. */
  const managed = !!(health && health.managed);
  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>YOUR PLAN</h4>
        {managed ? (
          <>
            <div className="row-knob">
              <div><div className="lbl">Cafreso HQ Premium</div><div className="sub">managed cloud — hosting, brain & updates included</div></div>
              <span className="tiny">{dot(true)}active</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">AI brain</div><div className="sub">included — no keys to manage</div></div>
              <span className="tiny">{health && health.brain && health.brain.model ? health.brain.model : 'not set yet'}</span>
            </div>
          </>
        ) : (
          <>
            <div className="row-knob plan-selfhosted">
              <div><div className="lbl">Self-hosted</div><div className="sub">running on your own machine — bring your own subscriptions or keys</div></div>
              <span className="tiny">{dot(!!health)}{health ? 'running' : 'unreachable'}</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">AI brain</div><div className="sub">whatever your coworkers are configured with — see Roster</div></div>
              <span className="tiny">{health && health.brain && health.brain.model ? health.brain.model : 'no shared brain — per-coworker'}</span>
            </div>
          </>
        )}
        <div className="row-knob">
          {/* Third place this false span has been found today, after the
              roster card and the Situation Wall. `usageTokens` is
              app.jsx's `totalTokens` — ceoTokens plus the sum of every
              coworker's `tokens`, all of which live in the file-backed
              roster record and survive a reload byte for byte. It was
              labelled "this session", and the sub-line narrowed the lie
              further to "since this tab loaded".

              "tokens" stays: Settings is the config surface where naming
              the real unit is the point, the same reasoning that leaves
              raw model IDs visible here and banned on the floor. Only the
              SPAN was wrong, and it was wrong in both lines. */}
          <div><div className="lbl">Usage so far</div><div className="sub">tokens your crew has spent since you hired them</div></div>
          <span className="tiny">{fmtTokens(usageTokens || 0)} tokens</span>
        </div>
      </div>
      <div className="cb-panel">
        <h4>YOUR OFFICE</h4>
        <div className="row-knob">
          <div><div className="lbl">Status</div><div className="sub">{health === null ? 'checking…' : health ? 'online' : 'unreachable — we auto-reconnect'}</div></div>
          <span>{health === null ? '…' : dot(!!health)}</span>
        </div>
        {health && uptime && (
          <div className="row-knob">
            <div><div className="lbl">Up for</div><div className="sub">since your office last started</div></div>
            <span className="tiny">{uptime}</span>
          </div>
        )}
        <div className="row-knob">
          <div><div className="lbl">Diagnostics</div><div className="sub">snapshot for support — no keys included</div></div>
          <button className="px-btn" style={{fontSize:9,padding:'8px 10px'}} onClick={copyDiag}>COPY</button>
        </div>
        <div className="row-knob">
          <div><div className="lbl">New-user guide</div><div className="sub">replay the onboarding tour</div></div>
          <button className="px-btn" style={{fontSize:9,padding:'8px 10px'}} onClick={resetOnboarding}>RESET</button>
        </div>
        {note && <div className="hint" style={{marginTop:8}}>{note}</div>}
      </div>
    </div>
  );
}

function SystemTab() {
  const [health, setHealth] = useStateM(null);   // null=loading · false=down · object=ok
  const [prov, setProv] = useStateM(null);
  const [busy, setBusy] = useStateM(false);
  const [note, setNote] = useStateM('');
  const apiBase = (window._API_BASE || '');

  const load = async () => {
    setBusy(true);
    try {
      const r = await fetch(apiBase + '/health');
      setHealth(r.ok ? await r.json() : false);
    } catch (_e) { setHealth(false); }
    try {
      const C = CafresoHQClient;
      if (C.hermesGetProvider) setProv(await C.hermesGetProvider());
    } catch (_e) { setProv(null); }
    setBusy(false);
  };
  useEffectM(() => { load(); }, []);

  const copyDiag = async () => {
    const diag = {
      when: new Date().toISOString(),
      apiBase: apiBase || '(same origin)',
      health: health || 'unreachable',
      provider: prov || 'unknown',
      ua: navigator.userAgent,
      url: location.href.split('?')[0],
    };
    try {
      await navigator.clipboard.writeText(JSON.stringify(diag, null, 2));
      setNote('✓ diagnostics copied — paste into a support chat');
    } catch (_e) { setNote('copy failed — clipboard blocked'); }
  };

  // Agent-config portability (Hermes setup travels; keys never do).
  const importInputRef = useRefM(null);
  const [importBusy, setImportBusy] = useStateM(false);
  const exportConfig = async () => {
    try {
      const C = CafresoHQClient;
      const data = await C.hermesExportConfig();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'cafresohq-hermes-config.json';
      a.click();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      setNote('✓ config exported (keys not included)');
    } catch (e) { setNote('export failed: ' + e.message); }
  };
  const importConfig = async (e) => {
    const file = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!file) return;
    setImportBusy(true); setNote('');
    try {
      const text = await file.text();
      const C = CafresoHQClient;
      const r = await C.hermesImportConfig(text);
      setNote(r.restarted
        ? '✓ config imported — agent reloading (~10s). Re-enter your key in Connections if needed.'
        : '✓ config written (gateway restart pending)');
      load();
    } catch (er) { setNote('import failed: ' + er.message); }
    setImportBusy(false);
  };

  const resetOnboarding = async () => {
    if (!(await window.hqConfirm('Replay the new-user guide on next reload?'))) return;
    try {
      const kill = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && /tourseen|gettingstarted|gsdismissed/i.test(k)) kill.push(k);
      }
      kill.forEach(k => localStorage.removeItem(k));
      setNote(`✓ onboarding reset (${kill.length} flag${kill.length === 1 ? '' : 's'} cleared) — reload to replay`);
    } catch (_e) { setNote('reset failed'); }
  };

  const dot = (on) => (
    <span className={`sn-dot ${on ? 'ok' : 'err'}`} style={{position:'static', marginRight:6}}/>
  );
  const yn = (v) => v ? 'yes' : 'no';

  return (
    <div className="control-board">
      <div className="cb-panel">
        <h4>OFFICE CONNECTION</h4>
        <div className="row-knob">
          <div><div className="lbl">API base</div><div className="sub">where this UI sends requests</div></div>
          <span className="tiny" style={{maxWidth:220, textAlign:'right', wordBreak:'break-all'}}>{apiBase || '(same origin)'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Status</div><div className="sub">{health === null ? 'checking…' : health ? 'serving' : 'unreachable'}</div></div>
          <span>{health === null ? '…' : dot(!!health)}</span>
        </div>
        {health && (
          <>
            <div className="row-knob">
              <div><div className="lbl">Runtime</div><div className="sub">where it's running</div></div>
              <span className="tiny">{health.runtime_env || 'unknown'}{health.auth_required ? ' · key-gated' : ''}</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">Hermes gateway</div><div className="sub">the built-in brain service</div></div>
              <span className="tiny">{dot(!!health.hermes)}{yn(!!health.hermes)}</span>
            </div>
            <div className="row-knob">
              <div><div className="lbl">Gemini CLI</div><div className="sub">installed here</div></div>
              <span className="tiny">{dot(!!health.gemini)}{yn(!!health.gemini)}</span>
            </div>
          </>
        )}
        <div className="row-knob">
          <div><div className="lbl">Re-check</div><div className="sub">probe /health again</div></div>
          <button className="px-btn secondary" disabled={busy} onClick={load}>{busy ? '…' : 'REFRESH'}</button>
        </div>
      </div>
      <div className="cb-panel">
        <h4>HERMES PROVIDER</h4>
        <div className="row-knob">
          <div><div className="lbl">Service</div><div className="sub">what Hermes is using right now</div></div>
          <span className="tiny">{prov ? prov.provider : '…'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Model</div><div className="sub">current default</div></div>
          <span className="tiny" style={{maxWidth:200, textAlign:'right', wordBreak:'break-all'}}>{prov ? (prov.model || 'unknown') : '…'}</span>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Key configured</div><div className="sub">set one in Connections if not</div></div>
          <span className="tiny">{prov === null ? '…' : <>{dot(!!(prov && prov.configured))}{yn(!!(prov && prov.configured))}</>}</span>
        </div>
      </div>
      <div className="cb-panel">
        <h4>AGENT CONFIG</h4>
        <div className="row-knob">
          <div><div className="lbl">Export setup</div><div className="sub">download your Hermes agent config (keys NOT included)</div></div>
          <button className="px-btn secondary" onClick={exportConfig}>EXPORT</button>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Import setup</div><div className="sub">apply an exported file or a raw ~/.hermes/config.yaml</div></div>
          <button className="px-btn secondary" disabled={importBusy}
            onClick={() => importInputRef.current && importInputRef.current.click()}>
            {importBusy ? '…' : 'IMPORT'}
          </button>
          <input ref={importInputRef} type="file" accept=".json,.yaml,.yml,.txt" style={{display:'none'}}
            onChange={importConfig}/>
        </div>
        <div className="hint">Moving between HQs (or from a local Hermes install)? Export here, import there — then re-enter your key in Connections.</div>
      </div>
      <div className="cb-panel">
        <h4>SUPPORT</h4>
        <div className="row-knob">
          <div><div className="lbl">Copy diagnostics</div><div className="sub">health + provider snapshot, no keys included</div></div>
          <button className="px-btn secondary" onClick={copyDiag}>COPY</button>
        </div>
        <div className="row-knob">
          <div><div className="lbl">Reset onboarding</div><div className="sub">replay the new-user tour & checklist</div></div>
          <button className="px-btn secondary" onClick={resetOnboarding}>RESET</button>
        </div>
        {note && <div className="hint" style={{marginTop:6}}>{note}</div>}
      </div>
    </div>
  );
}

// Hermes backend services the user can pick (the free LLM behind Hermes). Each
// row adapts the key field's label / placeholder / "get a free key" link. Gemini
// direct is the most reliable free tier (≈15 RPM / 1500 per day) — the fix for
// OpenRouter :free's 20 RPM / 50-per-day throttling. Mirrors serve.py
// _HERMES_PROVIDERS + claude-client HERMES_PROVIDER_KEY_FIELD.

export { SettingsModal, visibleToolsCatalog };
