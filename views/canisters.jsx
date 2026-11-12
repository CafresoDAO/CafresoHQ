import { CafresoHQChain } from '../claude-client.jsx';
/* The page's own React, not a second copy from npm. Importing 'react' here
   bundled a private React whose hooks have no renderer behind them, so
   opening this view threw "Cannot read properties of null (reading
   'useState')" and took the whole office down with it. */
const { useState, useEffect } = React;
import { Btn } from '../ui/primitives.jsx';

/* PUBLISHED — everything this office has put on the public internet. The
   stamp on a publish used to be the last anyone heard of it: the link went
   past in chat and nothing in the office listed what was live. The list
   comes from the shell that holds the boss's identity (it owns the public
   host), so outside that shell this says where to go instead of pretending
   to be empty. */
function sizeWords(n) {
  n = Number(n) || 0;
  if (n >= 1000000) return (n / 1000000).toFixed(1) + ' MB';
  if (n >= 1000) return Math.round(n / 1000) + ' KB';
  return n + ' bytes';
}
function PublishedList({ active }) {
  const [sites, setSites] = useState(null);     // null = loading · [] = none
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');
  const inShell = !!(CafresoHQChain && CafresoHQChain.isAvailable && CafresoHQChain.isAvailable());
  const load = async () => {
    if (!inShell) { setSites([]); return; }
    setError('');
    try {
      const list = await CafresoHQChain.sites.list();
      setSites((list || []).slice().sort((a, b) => Number(b.updatedAt || 0) - Number(a.updatedAt || 0)));
    } catch (e) { setError((e && e.message) || 'no answer'); setSites([]); }
  };
  useEffect(() => { if (active === 'canisters') load(); }, [active]);
  const copy = async (url) => {
    try { await navigator.clipboard.writeText(url); setCopied(url); setTimeout(() => setCopied(''), 1600); } catch (_e) {}
  };
  return (
    <section className="pub-section" aria-label="Published">
      <div className="section-title">
        <span>Published</span>
        <span className="tag">sites and files your office has put on the public internet</span>
      </div>
      {!inShell ? (
        <div className="empty-state">
          <div className="empty-title">Publishing needs your Cafreso sign-in</div>
          <div className="empty-sub">Open this office at hq.cafreso.com and sign in. A coworker can then publish a site, a PDF, a Word document or a deck, and it is listed here with its link.</div>
        </div>
      ) : sites === null ? (
        <div className="can-note" role="status">Checking what is published…</div>
      ) : error ? (
        <div className="can-note is-error" role="alert">Couldn’t list what is published — {error}</div>
      ) : sites.length === 0 ? (
        <div className="empty-state">
          <div className="empty-title">Nothing published yet</div>
          <div className="empty-sub">Ask a coworker to publish something they made — “publish that report as a PDF” — and stamp the request. It goes live on the Internet Computer and shows up here.</div>
        </div>
      ) : (
        <div className="can-list">
          {sites.map((s) => (
            <div key={s.project} className="can-card">
              <div className="can-card-top">
                <strong className="can-name">{s.project}</strong>
                <span className="can-net">LIVE</span>
              </div>
              {s.url ? <a className="pub-link" href={s.url} target="_blank" rel="noopener noreferrer">{s.url}</a> : null}
              <div className="can-card-foot">
                <span>{Number(s.files) || 0} file{Number(s.files) === 1 ? '' : 's'} · {sizeWords(s.bytes || s.totalBytes)}</span>
                {s.url ? (
                  <button type="button" className="px-btn secondary sz-sm" onClick={() => copy(s.url)}>
                    {copied === s.url ? 'Copied' : 'Copy link'}
                  </button>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function CanistersView({ active }) {
  const [canisters, setCanisters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchCanisters = async () => {
    setLoading(true);
    setError(null);
    try {
      const base = window._API_BASE || '';
      const res = await fetch(base + '/canister/status', { credentials: 'include' });
      const data = await res.json();
      if (data.canisters) {
        setCanisters(data.canisters);
      } else if (data.error) {
        setError(data.error);
      }
    } catch (err) {
      setError(err.message);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (active === 'canisters') {
      fetchCanisters();
    }
  }, [active]);

  if (active !== 'canisters') return null;

  return (
    <div className="view-canisters scroll-y">
      <PublishedList active={active} />
      <div className="section-title">
        <span>Canisters</span>
        <span className="tag">what your coworkers have deployed to the Internet Computer</span>
      </div>

      {loading ? (
        <div className="can-note" role="status">Checking each canister…</div>
      ) : error ? (
        <div className="can-note is-error" role="alert">Couldn’t check your canisters — {error}</div>
      ) : canisters.length === 0 ? (
        <div className="empty-state">
          <div className="empty-title">No canisters yet</div>
          <div className="empty-sub">When a coworker deploys something, it shows up here with its status and cycles.</div>
        </div>
      ) : (
        <div className="can-list">
          {canisters.map((c, i) => {
            const running = String(c.status || '').includes('Running');
            return (
              <div key={i} className="can-card">
                <div className="can-card-top">
                  <strong className="can-name">{c.name}</strong>
                  <span className="can-net">{String(c.network || '').toUpperCase()}</span>
                </div>
                <code className="can-id">{c.id}</code>
                <div className="can-card-foot">
                  <span><span className={`sn-dot ${running ? 'ok' : 'warn'} can-dot`}/>{c.status}</span>
                  <span>Cycles <strong>{c.balance}</strong></span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="can-actions">
        <Btn onClick={fetchCanisters} disabled={loading}>{loading ? 'Checking…' : 'Check again'}</Btn>
      </div>
    </div>
  );
}

export { CanistersView };
