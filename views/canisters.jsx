/* The page's own React, not a second copy from npm. Importing 'react' here
   bundled a private React whose hooks have no renderer behind them, so
   opening this view threw "Cannot read properties of null (reading
   'useState')" and took the whole office down with it. */
const { useState, useEffect } = React;
import { Btn } from '../ui/primitives.jsx';

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
