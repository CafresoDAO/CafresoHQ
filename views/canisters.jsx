import React, { useState, useEffect } from 'react';
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
    <div className="view-canisters scroll-y" style={{ padding: '24px' }}>
      <h2 style={{ fontFamily: '"Press Start 2P", monospace', fontSize: '14px', marginBottom: '24px' }}>
        ICP Canister Management
      </h2>
      
      <p style={{ marginBottom: '24px', opacity: 0.8, maxWidth: '600px', lineHeight: '1.5' }}>
        Agents automatically deploy logic and assets to the Internet Computer. 
        Track their active cycles balances and status directly via the network replica below.
      </p>

      {loading ? (
        <div>Pinging ICP Network for live cycle balances...</div>
      ) : error ? (
        <div style={{ color: 'var(--red)' }}>Error fetching canisters: {error}</div>
      ) : canisters.length === 0 ? (
        <div className="empty-title">
          No canisters deployed yet. Agent deployments will appear here.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {canisters.map((c, i) => (
            <div key={i} style={{
              padding: '16px', 
              border: '2px solid var(--ink)', 
              background: 'var(--bg-card, #fff)', 
              boxShadow: 'var(--shadow-hard, 4px 4px 0px 0px rgba(0,0,0,1))'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                <strong style={{ fontSize: '16px' }}>{c.name}</strong>
                <span style={{ fontSize: '12px', background: 'var(--accent)', color: '#fff', padding: '4px 8px', borderRadius: '4px' }}>
                  {c.network.toUpperCase()}
                </span>
              </div>
              <div style={{ fontFamily: 'monospace', opacity: 0.9, marginBottom: '8px' }}>
                ID: {c.id}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                <span>Status: <strong style={{ color: c.status.includes('Running') ? 'var(--live, #39ff14)' : 'inherit' }}>{c.status}</strong></span>
                <span>Cycles Balance: <strong>{c.balance}</strong></span>
              </div>
            </div>
          ))}
        </div>
      )}
      
      <div style={{ marginTop: '24px' }}>
        <Btn onClick={fetchCanisters}>Refresh Network Status</Btn>
      </div>
    </div>
  );
}

export { CanistersView };
