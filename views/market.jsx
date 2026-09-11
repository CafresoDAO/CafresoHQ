/* views/market.jsx — the Hiring Hall.

   North Star §6 Phase C: "Hire from the network." A boss hires a coworker
   they do not run for ONE job, the money waits in escrow on-chain until they
   accept the work, and every coworker in the hall has a résumé — jobs done,
   bosses served, re-hires, rating, disputes — that can be read before a
   single token moves. The other side of the same room: a boss can offer one
   of their own coworkers to the network and get paid for jobs it does.

   Everything on-chain goes through CafresoHQChain.market (the shell at
   ai.cafreso.com holds the identity and signs; see docs/AGENT_MARKETPLACE.md).
   The container-side worker — the loop that lets an OFFERED coworker take
   jobs while this tab is closed — is driven through serve.py's
   /marketplace/worker/* doors.

   Jargon table (OFFICE_AS_INTERFACE §6) is binding: coworker, job, boss,
   brain; never model/driver/API key on this surface. */
import { CafresoHQChain } from '../claude-client.jsx';
import { Btn } from '../ui/primitives.jsx';
import { brainName } from '../app/cast.jsx';
const { useState: useSM, useEffect: useEM, useRef: useRM } = React;

const toast = (k, m) => { if (window.cafresohqToast && window.cafresohqToast[k]) window.cafresohqToast[k](m); };
const API = () => window._API_BASE || '';
const hallReachable = () => { try { return !!(CafresoHQChain && CafresoHQChain.isAvailable && CafresoHQChain.isAvailable()); } catch (_e) { return false; } };
const mkt = () => CafresoHQChain.market;

/* ── money, as text ───────────────────────────────────────────────────── */
const BI = (v) => BigInt(String(v || '0'));
const pow10 = (d) => BigInt(10) ** BigInt(d);
function decimalsOf(token, tokens) { const t = tokens && tokens[token]; return t && Number.isFinite(Number(t.decimals)) ? Number(t.decimals) : 8; }
function symbolOf(token, tokens) { const t = tokens && tokens[token]; return (t && t.symbol) || token || ''; }
/* raw base units → "0.25 ICP" (six places at most, trailing zeros dropped) */
function fmtAmount(raw, token, tokens) {
  try {
    const d = decimalsOf(token, tokens); const n = BI(raw); const base = pow10(d);
    const whole = (n / base).toString();
    const frac = (n % base).toString().padStart(d, '0').slice(0, 6).replace(/0+$/, '');
    return `${whole}${frac ? '.' + frac : ''} ${symbolOf(token, tokens)}`;
  } catch (_e) { return `${raw} ${token}`; }
}
/* "0.25" → raw base units as a string, or null when it is not an amount */
function toRaw(text, token, tokens) {
  const d = decimalsOf(token, tokens); const s = String(text || '').trim();
  if (!/^\d+(\.\d*)?$|^\.\d+$/.test(s)) return null;
  const [w = '0', f = ''] = s.split('.');
  if (f.length > d) return null;
  try { return (BI(w || '0') * pow10(d) + BI((f + '0'.repeat(d)).slice(0, d) || '0')).toString(); } catch (_e) { return null; }
}
const short = (p) => { const s = String(p || ''); return s.length > 18 ? s.slice(0, 8) + '…' + s.slice(-5) : s; };
const ago = (ns) => {
  const ms = Number(BI(ns) / BigInt(1000000)); if (!ms) return '';
  const s = Math.max(0, (Date.now() - ms) / 1000);
  if (s < 90) return 'just now'; if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`; return `${Math.round(s / 86400)} d ago`;
};

/* ── the résumé, in one line ──────────────────────────────────────────── */
function resumeLine(r) {
  if (!r || !r.jobsDone) return r && r.jobsFailed ? `no jobs finished yet · ${r.jobsFailed} snag${r.jobsFailed === 1 ? '' : 's'}` : 'new here — no jobs on record yet';
  const p = [`${r.jobsDone} job${r.jobsDone === 1 ? '' : 's'} done`, `${r.bosses} boss${r.bosses === 1 ? '' : 'es'}`];
  if (r.rehires) p.push(`${r.rehires} re-hire${r.rehires === 1 ? '' : 's'}`);
  if (r.ratingCount) p.push(`★ ${(r.ratingSum / r.ratingCount).toFixed(1)} (${r.ratingCount})`);
  if (r.disputes) p.push(`${r.disputes} dispute${r.disputes === 1 ? '' : 's'}`);
  if (r.jobsFailed) p.push(`${r.jobsFailed} snag${r.jobsFailed === 1 ? '' : 's'}`);
  return p.join(' · ');
}
const STATUS_WORDS = {
  posted: 'written down — not funded yet', funded: 'waiting for the coworker', claimed: 'on their desk',
  delivered: 'delivered — your call', accepted: 'accepted · paid', disputed: 'in dispute',
  refunded: 'refunded', cancelled: 'cancelled', failed: 'failed — refund on its way',
};
const KINDS = [['brief', 'a brief'], ['research', 'research'], ['draft', 'a draft'], ['page', 'a page'], ['code', 'code'], ['task', 'something else']];
const DEADLINES = [[3600, '1 hour'], [14400, '4 hours'], [86400, '1 day'], [259200, '3 days'], [604800, 'a week']];
/* which local brain works network jobs — from the coworker's own brain id */
const DRIVER_OF = { claudecode: 'claude-code', codex: 'codex', gemini: 'gemini', 'gemini-api': 'gemini-api',
                    lmstudio: 'lmstudio', ollama: 'ollama', openrouter: 'openrouter', groq: 'groq', hermes: 'hermes' };
const driverOf = (model) => DRIVER_OF[String(model || '').split(':')[0]] || '';

const Lbl = ({ children }) => <label style={{ fontFamily: 'Inter', fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-2)' }}>{children}</label>;
const inputStyle = { font: 'inherit', fontSize: 13, padding: '6px 8px', border: '2px solid var(--ink)', background: 'var(--paper)', color: 'var(--ink)' };
const Note = ({ children, tone }) => (
  <div className="market-note" style={{ fontFamily: 'Inter', fontSize: 12, lineHeight: 1.45, color: tone === 'warn' ? 'var(--error)' : 'var(--ink-2)' }}>{children}</div>
);

/* ── the room ─────────────────────────────────────────────────────────── */
function MarketView({ agents = [] }) {
  const [tab, setTab] = useSM('hire');
  const [info, setInfo] = useSM(null);      // null = asking; false = no shell; object = the hall
  const [why, setWhy] = useSM('');
  useEM(() => {
    let dead = false;
    if (!hallReachable()) { setInfo(false); return undefined; }
    mkt().info().then(i => { if (!dead) setInfo(i || false); })
      .catch(e => { if (!dead) { setInfo(false); setWhy((e && e.message) || String(e)); } });
    return () => { dead = true; };
  }, []);

  const header = (
    <div className="section-title" style={{ display: 'flex', alignItems: 'baseline', gap: 12, flexWrap: 'wrap' }}>
      <span>🏛 HIRING HALL</span>
      <span style={{ fontFamily: 'Inter', fontSize: 11, textTransform: 'none', letterSpacing: 0, color: 'var(--ink-2)', fontWeight: 400 }}>
        hire a coworker from the network for one job — the money waits in escrow until you accept the work
      </span>
    </div>
  );
  if (info === null) return <div className="view-market">{header}<div className="empty-state"><div className="empty-title">Opening the hall…</div></div></div>;
  if (info === false) {
    return (
      <div className="view-market">{header}
        <div className="empty-state">
          <div className="empty-title">The hall is behind the Cafreso sign-in</div>
          <div className="empty-sub">Hiring from the network moves real money, so it needs the Cafreso app that holds your identity. Open this office at ai.cafreso.com and the hall is here.{why ? ` (${why})` : ''}</div>
        </div>
      </div>
    );
  }
  if (!info.configured) {
    return (
      <div className="view-market">{header}
        <div className="empty-state">
          <div className="empty-title">The hall is not open yet</div>
          <div className="empty-sub">Its canister has not been deployed. Once it is, coworkers from the network will be listed here with their résumés.</div>
        </div>
      </div>
    );
  }
  const tabs = [['hire', 'Hire from the network'], ['jobs', 'Your jobs'], ['offer', 'Offer a coworker']];
  return (
    <div className="view-market" style={{ display: 'flex', flexDirection: 'column', gap: 12, minHeight: 0, height: '100%' }}>
      {header}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
        {tabs.map(([k, l]) => (
          <button key={k} className={`px-btn sz-sm ${tab === k ? 'primary' : 'ghost'}`} data-market-tab={k} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
        {tab === 'hire' && <HireTab info={info} onPosted={() => setTab('jobs')} />}
        {tab === 'jobs' && <JobsTab info={info} />}
        {tab === 'offer' && <OfferTab info={info} agents={agents} />}
      </div>
    </div>
  );
}

/* ── Hire: browse the résumés, post one job to one coworker ───────────── */
function HireTab({ info, onPosted }) {
  const [cards, setCards] = useSM(null);
  const [hiring, setHiring] = useSM(null);
  const load = () => mkt().browse(0, 50).then(setCards).catch(e => { setCards([]); toast('error', `Could not read the hall — ${e.message || e}`); });
  useEM(() => { load(); }, []);
  if (cards === null) return <div className="empty-state"><div className="empty-title">Reading the résumés…</div></div>;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {hiring && <HireForm card={hiring} info={info} onDone={() => { setHiring(null); onPosted(); }} onCancel={() => setHiring(null)} />}
      {!cards.length && (
        <div className="empty-state">
          <div className="empty-title">Nobody is listed yet</div>
          <div className="empty-sub">The hall opens with the first coworker someone offers. You can offer one of yours from the "Offer a coworker" tab.</div>
        </div>
      )}
      <div className="team-grid">
        {cards.map(c => (
          <div key={c.listing.id} className="team-card" data-listing={c.listing.id} style={{ cursor: 'default' }} onClick={() => {}}>
            <div className={`status-pill ${c.online ? 'idle' : 'off'}`} title={c.online ? 'their coworker checked in within the last ten minutes' : 'no check-in for ten minutes or more'}>
              {c.online ? 'AT THEIR DESK' : 'AWAY'}
            </div>
            <div className="name">{c.listing.name}</div>
            <div className="role">{c.listing.role || 'coworker'}</div>
            {c.listing.pitch && <Note>{c.listing.pitch}</Note>}
            <div className="team-stats">
              <div><span className="lbl">Brain</span><span className="val">{c.listing.brain || 'not stated'}</span></div>
              <div><span className="lbl">Per job</span><span className="val">{fmtAmount(c.listing.price, c.listing.token, info.tokens)}</span></div>
              <div><span className="lbl">Takes</span><span className="val">{(c.listing.tags || []).join(', ') || 'anything'}</span></div>
            </div>
            <Note>{resumeLine(c.resume)}</Note>
            <Btn variant="primary" size="sm" onClick={() => setHiring(c)} disabled={!c.listing.token}
                 title={c.listing.token ? '' : 'paid in a token this office does not know'}>Hire for a job</Btn>
          </div>
        ))}
      </div>
    </div>
  );
}

function HireForm({ card, info, onDone, onCancel }) {
  const l = card.listing;
  const [title, setTitle] = useSM('');
  const [brief, setBrief] = useSM('');
  const [kind, setKind] = useSM('brief');
  const [deadline, setDeadline] = useSM(86400);
  const [price, setPrice] = useSM(fmtAmount(l.price, l.token, info.tokens).split(' ')[0]);
  const [busy, setBusy] = useSM('');
  const raw = toRaw(price, l.token, info.tokens);
  const belowAsk = raw !== null && BI(raw) < BI(l.price);
  const canPost = title.trim() && brief.trim() && raw !== null && !belowAsk && !busy;
  const submit = async () => {
    setBusy('posting');
    let id;
    try {
      const r = await mkt().post({ title: title.trim(), brief: brief.trim(), kind, tags: [], listing: l.id, token: l.token, price: raw, deadlineSecs: deadline });
      id = r && r.id;
      if (!id) throw new Error('no job id came back');
    } catch (e) { setBusy(''); toast('error', `Could not post the job — ${e.message || e}`); return; }
    setBusy('funding');
    try {
      const f = await mkt().fund(id, l.token, raw);
      if (f.status === 'ok' || f.status === 'duplicate') toast('success', `Funded — ${l.name} can pick it up now. It is in Your jobs.`);
      else if (f.status === 'declined') toast('info', 'Posted, not funded — nobody can take it until you fund it from Your jobs.');
      else toast('error', `Posted, but the escrow did not fund — ${f.error || 'unknown'}. Fund it from Your jobs.`);
    } catch (e) { toast('error', `Posted, but funding failed — ${e.message || e}. Fund it from Your jobs.`); }
    setBusy('');
    onDone();
  };
  return (
    <div className="team-card" style={{ cursor: 'default', gap: 10 }} data-hire-form>
      <div className="name">Hire {l.name}</div>
      <Note>{l.role || 'coworker'} · {l.brain || 'brain not stated'} · asks {fmtAmount(l.price, l.token, info.tokens)} per job · {resumeLine(card.resume)}</Note>
      <div className="form-row"><Lbl>What is the job called?</Lbl>
        <input style={inputStyle} value={title} maxLength={200} onChange={e => setTitle(e.target.value)} placeholder="e.g. Competitor brief on three hardware wallets" /></div>
      <div className="form-row"><Lbl>The brief — everything they need, because it is all they get</Lbl>
        <textarea style={{ ...inputStyle, minHeight: 120 }} value={brief} maxLength={16000} onChange={e => setBrief(e.target.value)}
                  placeholder="They have no access to your files or library. Paste what they need here." /></div>
      <Note tone="warn">Only this brief leaves your office. The coworker cannot see your library, your files or your other coworkers.</Note>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 10 }}>
        <div className="form-row"><Lbl>It is</Lbl>
          <select style={inputStyle} value={kind} onChange={e => setKind(e.target.value)}>{KINDS.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></div>
        <div className="form-row"><Lbl>They have</Lbl>
          <select style={inputStyle} value={deadline} onChange={e => setDeadline(Number(e.target.value))}>{DEADLINES.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></div>
        <div className="form-row"><Lbl>You pay ({symbolOf(l.token, info.tokens)})</Lbl>
          <input style={inputStyle} value={price} onChange={e => setPrice(e.target.value)} inputMode="decimal" /></div>
      </div>
      {raw === null && price && <Note tone="warn">That is not an amount this token can hold.</Note>}
      {belowAsk && <Note tone="warn">Below their asking price of {fmtAmount(l.price, l.token, info.tokens)}.</Note>}
      <Note>Posting writes the job down; funding then asks you to sign for exactly the price plus the ledger fee, and the hall holds it until you accept the delivery.</Note>
      <div style={{ display: 'flex', gap: 8 }}>
        <Btn variant="primary" onClick={submit} disabled={!canPost} loading={!!busy}>{busy === 'funding' ? 'Funding…' : 'Post and fund'}</Btn>
        <Btn variant="ghost" onClick={onCancel} disabled={!!busy}>Never mind</Btn>
      </div>
    </div>
  );
}

/* ── Your jobs: the boss's side of every job they posted ──────────────── */
function JobsTab({ info }) {
  const [jobs, setJobs] = useSM(null);
  const [names, setNames] = useSM({});
  const [open, setOpen] = useSM({});
  const [reason, setReason] = useSM({});
  const [rating, setRating] = useSM({});
  const [busy, setBusy] = useSM({});
  const timer = useRM(null);
  const load = async () => {
    try { const js = await mkt().myJobs(); js.sort((a, b) => Number(BI(b.createdAt) - BI(a.createdAt)) > 0 ? 1 : -1); setJobs(js); }
    catch (e) { if (jobs === null) setJobs([]); toast('error', `Could not read your jobs — ${e.message || e}`); }
  };
  useEM(() => { load(); timer.current = setInterval(load, 15000); return () => clearInterval(timer.current); }, []);
  useEM(() => {
    if (!jobs) return;
    const want = [...new Set(jobs.map(j => j.workerListing || j.listing).filter(Boolean))].filter(id => !(id in names));
    want.forEach(id => mkt().listing(id).then(c => setNames(n => ({ ...n, [id]: c && c.listing ? c.listing.name : `coworker #${id}` }))).catch(() => {}));
  }, [jobs]);
  const act = async (id, label, fn) => {
    setBusy(b => ({ ...b, [id]: label }));
    try {
      const r = await fn();
      if (r && r.status === 'error') toast('error', `${label} did not go through — ${r.error}`);
      else if (r && r.status === 'declined') toast('info', `${label}: you declined the signature.`);
      else toast('success', `${label} — done.`);
    } catch (e) { toast('error', `${label} did not go through — ${e.message || e}`); }
    setBusy(b => ({ ...b, [id]: '' }));
    load();
  };
  if (jobs === null) return <div className="empty-state"><div className="empty-title">Reading your jobs…</div></div>;
  if (!jobs.length) return <div className="empty-state"><div className="empty-title">No jobs posted yet</div><div className="empty-sub">Hire someone from the network and the job shows up here — funded, on their desk, delivered, paid.</div></div>;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {jobs.map(j => {
        const who = names[j.workerListing || j.listing] || (j.listing ? `coworker #${j.listing}` : 'anyone who fits');
        const b = busy[j.id] || '';
        return (
          <div key={j.id} className="team-card" style={{ cursor: 'default' }} data-job={j.id} data-status={j.status}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
              <div className="name">{j.title}</div>
              <div className={`status-pill ${j.status === 'delivered' ? 'busy' : j.status === 'accepted' ? 'idle' : 'off'}`}>{(STATUS_WORDS[j.status] || j.status).toUpperCase()}</div>
            </div>
            <Note>{who} · {fmtAmount(j.price, j.token, info.tokens)} · posted {ago(j.createdAt)}{j.attempts ? ` · ${j.attempts} snag${j.attempts === 1 ? '' : 's'}` : ''}</Note>
            {j.status === 'claimed' && <Progress id={j.id} />}
            {(j.status === 'delivered' || j.status === 'accepted' || j.status === 'disputed') && (
              <>
                <Note><b>They wrote:</b> {j.summary}</Note>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <Btn size="sm" variant="secondary" onClick={() => setOpen(o => ({ ...o, [j.id]: !o[j.id] }))}>{open[j.id] ? 'Fold it away' : 'Read the whole thing'}</Btn>
                  <Btn size="sm" variant="ghost" onClick={() => { try { navigator.clipboard.writeText(j.body); toast('success', 'Copied.'); } catch (_e) { toast('error', 'Could not copy.'); } }}>Copy it</Btn>
                </div>
                {open[j.id] && <pre style={{ whiteSpace: 'pre-wrap', fontFamily: 'Inter', fontSize: 12, lineHeight: 1.5, maxHeight: 360, overflow: 'auto', margin: 0, padding: 8, border: '1px dashed var(--ink-2)' }}>{j.body}</pre>}
              </>
            )}
            {j.note && j.status !== 'delivered' && <Note>{j.note}</Note>}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              {j.status === 'posted' && (
                <>
                  <Btn size="sm" variant="primary" loading={b === 'Funding'} onClick={() => act(j.id, 'Funding', () => mkt().fund(j.id, j.token, j.price))}>Fund it</Btn>
                  <Btn size="sm" variant="ghost" loading={b === 'Cancelling'} onClick={() => act(j.id, 'Cancelling', () => mkt().cancel(j.id, 'withdrawn before funding'))}>Take it back</Btn>
                </>
              )}
              {j.status === 'funded' && (
                <Btn size="sm" variant="ghost" loading={b === 'Cancelling'} onClick={() => act(j.id, 'Cancelling', () => mkt().cancel(j.id, 'withdrawn before anyone took it'))}>Take it back (refund)</Btn>
              )}
              {j.status === 'delivered' && (
                <>
                  <select style={inputStyle} value={rating[j.id] ?? 5} onChange={e => setRating(r => ({ ...r, [j.id]: Number(e.target.value) }))}>
                    {[5, 4, 3, 2, 1].map(n => <option key={n} value={n}>{'★'.repeat(n)}</option>)}
                  </select>
                  <Btn size="sm" variant="primary" loading={b === 'Accepting'} onClick={() => act(j.id, 'Accepting', () => mkt().accept(j.id, rating[j.id] ?? 5))}>Accept and pay</Btn>
                  <input style={{ ...inputStyle, minWidth: 180 }} placeholder="if not — say why" value={reason[j.id] || ''} onChange={e => setReason(r => ({ ...r, [j.id]: e.target.value }))} />
                  <Btn size="sm" variant="danger" disabled={!(reason[j.id] || '').trim()} loading={b === 'Rejecting'} onClick={() => act(j.id, 'Rejecting', () => mkt().reject(j.id, reason[j.id]))}>Reject</Btn>
                </>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Progress({ id }) {
  const [note, setNote] = useSM('');
  useEM(() => { let dead = false; mkt().progress(id).then(n => { if (!dead) setNote(n); }).catch(() => {}); return () => { dead = true; }; }, [id]);
  return <Note>On their desk{note ? ` · "${note}"` : ''}</Note>;
}

/* ── Offer: list one of your coworkers, put its key on duty ───────────── */
function OfferTab({ info, agents }) {
  const [listings, setListings] = useSM(null);
  const [worker, setWorker] = useSM(null);      // serve.py's /marketplace/worker/status
  const [jobs, setJobs] = useSM([]);
  const [pick, setPick] = useSM('');
  const [name, setName] = useSM('');
  const [role, setRole] = useSM('');
  const [brain, setBrain] = useSM('');
  const [pitch, setPitch] = useSM('');
  const [tags, setTags] = useSM('brief, research, draft');
  const [token, setToken] = useSM('ICP');
  const [price, setPrice] = useSM('0.25');
  const [driver, setDriver] = useSM('');
  const [model, setModel] = useSM('');
  const [busy, setBusy] = useSM('');
  const timer = useRM(null);
  const loadWorker = () => fetch(`${API()}/marketplace/worker/status`, { cache: 'no-store' }).then(r => r.ok ? r.json() : null).then(setWorker).catch(() => setWorker(null));
  const loadListings = () => Promise.all([mkt().myListings(), mkt().operatorJobs()]).then(([ls, js]) => { setListings(ls); setJobs(js); })
    .catch(e => { setListings([]); toast('error', `Could not read your listings — ${e.message || e}`); });
  useEM(() => { loadListings(); loadWorker(); timer.current = setInterval(loadWorker, 10000); return () => clearInterval(timer.current); }, []);
  const post = async (path, body) => {
    const r = await fetch(`${API()}${path}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body || {}) });
    if (!r.ok) throw new Error(`${path} answered ${r.status}`);
    const j = await r.json(); setWorker(j); return j;
  };
  const choose = (id) => {
    setPick(id);
    const a = agents.find(x => x.id === id);
    if (!a) return;
    setName(a.name || ''); setRole(a.role || ''); setBrain(brainName(a));
    setDriver(driverOf(a.model)); setModel(String(a.model || ''));
  };
  const raw = toRaw(price, token, info.tokens);
  const canList = name.trim() && raw !== null && BI(raw) > BI(0) && driver && !busy;
  const principal = worker && worker.principal;
  const list = async () => {
    setBusy('listing');
    try {
      const r = await mkt().putListing({ name: name.trim(), role: role.trim(), pitch: pitch.trim(), brain: brain.trim(),
                                         tags: tags.split(',').map(s => s.trim()).filter(Boolean), token, price: raw, active: true });
      if (principal) await mkt().linkWorker(r.id, principal);
      await post('/marketplace/worker/config', { canister: info.canister, host: info.host, driver, model, enabled: true });
      toast('success', principal ? `${name.trim()} is listed and on duty.` : `${name.trim()} is listed — link the key once this office's worker answers.`);
      setName(''); setPitch(''); setPick('');
      loadListings();
    } catch (e) { toast('error', `Could not list them — ${e.message || e}`); }
    setBusy('');
  };
  const link = async (l) => {
    if (!principal) { toast('error', 'This office\'s worker has no key yet — is the office running?'); return; }
    setBusy(`link-${l.id}`);
    try { await mkt().linkWorker(l.id, principal); await post('/marketplace/worker/config', { canister: info.canister, host: info.host }); toast('success', `Linked — ${l.name} works from this office now.`); loadListings(); }
    catch (e) { toast('error', `Could not link — ${e.message || e}`); }
    setBusy('');
  };
  const toggleActive = async (l) => {
    setBusy(`active-${l.id}`);
    try { await mkt().putListing({ id: l.id, name: l.name, role: l.role, pitch: l.pitch, brain: l.brain, tags: l.tags, token: l.token, price: l.price, payoutSub: l.payoutSub, active: !l.active }); loadListings(); }
    catch (e) { toast('error', `Could not change that — ${e.message || e}`); }
    setBusy('');
  };
  const onDuty = worker && worker.running;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* the worker: this office's key and whether it is on duty */}
      <div className="team-card" style={{ cursor: 'default' }} data-worker-card>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
          <div className="name">This office on the network</div>
          <div className={`status-pill ${onDuty ? 'busy' : 'off'}`}>{worker === null ? 'NOT ANSWERING' : onDuty ? 'ON DUTY' : 'OFF DUTY'}</div>
        </div>
        {worker === null && <Note tone="warn">Could not reach this office's worker door. The listing can still be made; link the key once the office answers.</Note>}
        {worker && (
          <>
            <Note>Its key: <code style={{ fontSize: 11 }} title={worker.principal}>{short(worker.principal)}</code> — the hall lets this key claim, deliver and fail jobs for a listing it is linked to, and nothing else. The key never leaves this office.</Note>
            {worker.config && worker.config.driver && <Note>Works network jobs with: <b>{brainName({ model: worker.config.model })}</b> · checks the hall every {worker.config.pollSecs}s{worker.config.allowWeb ? ' · may search the web' : ' · no tools, no files'}</Note>}
            {worker.current && <Note>On its desk now: <b>{worker.current.title}</b></Note>}
            <Note>Jobs done from here: {worker.jobsDone || 0}{worker.jobsFailed ? ` · snags: ${worker.jobsFailed}` : ''}{worker.lastError ? ` · last snag: ${worker.lastError}` : ''}</Note>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {onDuty
                ? <Btn size="sm" variant="ghost" onClick={() => post('/marketplace/worker/stop').catch(e => toast('error', String(e.message || e)))}>Take it off duty</Btn>
                : <Btn size="sm" variant="primary" disabled={!worker.configured || !worker.config || !worker.config.driver}
                       title={worker.configured ? '' : 'list a coworker first — that points this office at the hall'}
                       onClick={() => post('/marketplace/worker/start').catch(e => toast('error', String(e.message || e)))}>Put it on duty</Btn>}
              <Btn size="sm" variant="ghost" onClick={() => post('/marketplace/worker/config', { allowWeb: !(worker.config && worker.config.allowWeb) }).catch(e => toast('error', String(e.message || e)))}>
                {worker.config && worker.config.allowWeb ? 'Stop letting it search the web' : 'Let it search the web for jobs'}
              </Btn>
            </div>
          </>
        )}
      </div>

      {/* listings */}
      {listings === null ? <div className="empty-state"><div className="empty-title">Reading your listings…</div></div> : listings.map(l => {
        const mine = jobs.filter(j => j.workerListing === l.id);
        const earned = mine.filter(j => j.status === 'accepted').reduce((s, j) => s + BI(j.price), BI(0));
        return (
          <div key={l.id} className="team-card" style={{ cursor: 'default' }} data-my-listing={l.id}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap', alignItems: 'baseline' }}>
              <div className="name">{l.name}</div>
              <div className={`status-pill ${l.active ? 'idle' : 'off'}`}>{l.active ? 'LISTED' : 'PAUSED'}</div>
            </div>
            <Note>{l.role || 'coworker'} · {l.brain || 'brain not stated'} · asks {fmtAmount(l.price, l.token, info.tokens)} · takes {(l.tags || []).join(', ') || 'anything'}</Note>
            <Note>{l.worker ? (principal && l.worker === principal ? 'Key: this office' : `Key: ${short(l.worker)} (another office)`) : 'No key linked — nobody can take jobs for this listing yet'}
              {' · '}{mine.length} job{mine.length === 1 ? '' : 's'} on record · earned {fmtAmount(earned.toString(), l.token, info.tokens)}</Note>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {(!l.worker || (principal && l.worker !== principal)) && <Btn size="sm" variant="primary" loading={busy === `link-${l.id}`} onClick={() => link(l)}>Link this office's key</Btn>}
              <Btn size="sm" variant="ghost" loading={busy === `active-${l.id}`} onClick={() => toggleActive(l)}>{l.active ? 'Pause the listing' : 'List again'}</Btn>
            </div>
            {mine.filter(j => j.status === 'claimed' || j.status === 'delivered').map(j => (
              <Note key={j.id}>· "{j.title}" — {STATUS_WORDS[j.status]}</Note>
            ))}
          </div>
        );
      })}

      {/* offer one */}
      <div className="team-card" style={{ cursor: 'default', gap: 10 }} data-offer-form>
        <div className="name">Offer a coworker</div>
        <Note>Pick one of yours. Jobs from the network run on that coworker's brain, with no tools and no access to your files; only the boss's brief goes in and only the reply comes out. You are paid per job into your own account once the boss accepts.</Note>
        <div className="form-row"><Lbl>Which coworker</Lbl>
          <select style={inputStyle} value={pick} onChange={e => choose(e.target.value)}>
            <option value="">— choose —</option>
            {agents.map(a => <option key={a.id} value={a.id}>{a.name} · {a.role}{driverOf(a.model) ? '' : ' (no brain this office can run for others)'}</option>)}
          </select></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
          <div className="form-row"><Lbl>Listed as</Lbl><input style={inputStyle} value={name} maxLength={80} onChange={e => setName(e.target.value)} /></div>
          <div className="form-row"><Lbl>Role</Lbl><input style={inputStyle} value={role} maxLength={80} onChange={e => setRole(e.target.value)} /></div>
          <div className="form-row"><Lbl>Brain (as shown to bosses)</Lbl><input style={inputStyle} value={brain} maxLength={80} onChange={e => setBrain(e.target.value)} /></div>
        </div>
        <div className="form-row"><Lbl>What they are good at — one line</Lbl><input style={inputStyle} value={pitch} maxLength={500} onChange={e => setPitch(e.target.value)} placeholder="e.g. Crisp research briefs with sources, under an hour" /></div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 10 }}>
          <div className="form-row"><Lbl>Takes (comma-separated)</Lbl><input style={inputStyle} value={tags} onChange={e => setTags(e.target.value)} /></div>
          <div className="form-row"><Lbl>Paid in</Lbl>
            <select style={inputStyle} value={token} onChange={e => setToken(e.target.value)}>{Object.keys(info.tokens || { ICP: 1 }).map(k => <option key={k} value={k}>{symbolOf(k, info.tokens)}</option>)}</select></div>
          <div className="form-row"><Lbl>Asking price per job</Lbl><input style={inputStyle} value={price} inputMode="decimal" onChange={e => setPrice(e.target.value)} /></div>
        </div>
        {pick && !driver && <Note tone="warn">This coworker's brain is not one this office can run on someone else's behalf. Pick one on a brain this machine runs.</Note>}
        <div style={{ display: 'flex', gap: 8 }}>
          <Btn variant="primary" disabled={!canList} loading={busy === 'listing'} onClick={list}>List them and put this office on duty</Btn>
        </div>
      </div>
    </div>
  );
}

export { MarketView, fmtAmount, toRaw, resumeLine, driverOf };
