import { useState, useEffect, useCallback } from 'react';
import './index.css';

import Header       from './components/Header';
import StatsPanel   from './components/StatsPanel';
import FarmerCard   from './components/FarmerCard';
import AILogStream  from './components/AILogStream';
import ScoreGauge   from './components/ScoreGauge';
import { useSSE, api } from './hooks/useSSE';

const REFRESH_INTERVAL = 5000;

export default function App() {
  const [farmers, setFarmers]           = useState([]);
  const [stats, setStats]               = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [loadingDemo, setLoadingDemo]   = useState(false);
  const [selectedWallet, setSelectedWallet] = useState(null);
  const [evalId, setEvalId]             = useState(null);
  const [evaluating, setEvaluating]     = useState(false);

  // SSE hook for AI log streaming
  const { logs, done, result } = useSSE(evalId);

  // ── Data fetching ──────────────────────────────────────────────
  const fetchFarmers = useCallback(async () => {
    try {
      const data = await api.getFarmers();
      setFarmers(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to fetch farmers:', e);
    }
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      setStatsLoading(true);
      const data = await api.getStats();
      setStats(data);
    } catch (e) {
      console.error('Failed to fetch stats:', e);
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchFarmers();
    fetchStats();
  }, [fetchFarmers, fetchStats]);

  // Auto-refresh
  useEffect(() => {
    const id = setInterval(() => {
      fetchFarmers();
      fetchStats();
    }, REFRESH_INTERVAL);
    return () => clearInterval(id);
  }, [fetchFarmers, fetchStats]);

  // When SSE stream finishes – refresh data
  useEffect(() => {
    if (done) {
      setEvaluating(false);
      setTimeout(() => {
        fetchFarmers();
        fetchStats();
      }, 800);
    }
  }, [done, fetchFarmers, fetchStats]);

  // ── Handlers ───────────────────────────────────────────────────
  const handleSeedDemo = useCallback(async () => {
    setLoadingDemo(true);
    try {
      await api.seedDemo();
      await fetchFarmers();
      await fetchStats();
    } finally {
      setLoadingDemo(false);
    }
  }, [fetchFarmers, fetchStats]);

  const handleEvaluate = useCallback(async (farmer) => {
    setSelectedWallet(farmer.wallet);
    setEvalId(null);
    setEvaluating(true);

    try {
      const res = await api.evaluate(farmer.wallet, farmer.lat, farmer.lon);
      setEvalId(res.evaluation_id);
    } catch (e) {
      console.error('Evaluation failed:', e);
      setEvaluating(false);
    }
  }, []);

  // ── Selected farmer lookup ─────────────────────────────────────
  const selectedFarmer = farmers.find(f => f.wallet === selectedWallet);

  return (
    <div className="app-layout">
      <Header onSeedDemo={handleSeedDemo} loading={loadingDemo} />

      {/* Headline */}
      <div style={{ marginBottom: 28 }}>
        <h2 style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.02em' }}>
          🌾 Subsidy Dashboard
        </h2>
        <p style={{ fontSize: 13, color: 'var(--clr-text-3)', marginTop: 4 }}>
          AI-powered agricultural subsidy oracle · Powered by GPT-4o + Solana
        </p>
      </div>

      {/* Stats */}
      <StatsPanel stats={stats} loading={statsLoading} />

      <div style={{ height: 28 }} />

      {/* No farmers placeholder */}
      {farmers.length === 0 ? (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', gap: 14, padding: '60px 0',
          color: 'var(--clr-text-3)',
        }}>
          <span style={{ fontSize: 48 }}>🌱</span>
          <p style={{ fontSize: 15, fontWeight: 600 }}>No farmers registered yet</p>
          <p style={{ fontSize: 13 }}>Click <strong style={{ color: 'var(--clr-green)' }}>Load Demo</strong> to seed 5 demo farmer profiles</p>
        </div>
      ) : (
        <>
          <h3 style={{ fontSize: 15, fontWeight: 700, marginBottom: 16, color: 'var(--clr-text-2)' }}>
            Registered Farmers ({farmers.length})
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginBottom: 28 }}>
            {farmers.map(farmer => (
              <FarmerCard
                key={farmer.wallet}
                farmer={farmer}
                selected={selectedWallet === farmer.wallet}
                onSelect={setSelectedWallet}
                onEvaluate={handleEvaluate}
                evaluating={evaluating}
              />
            ))}
          </div>
        </>
      )}

      {/* AI Log Stream & Result Panel */}
      {(evalId || logs.length > 0) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 20, alignItems: 'start' }}>

          {/* Left: AI log */}
          <AILogStream logs={logs} done={done} running={evaluating || !done} />

          {/* Right: Verdict Card */}
          {result && (
            <div className="glass fade-in" style={{ padding: 22 }}>
              <p style={{ fontWeight: 700, fontSize: 14, marginBottom: 16 }}>
                {result.approved ? '✅ Subsidy Approved' : '❌ Subsidy Rejected'}
              </p>

              {/* Score */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 18 }}>
                <ScoreGauge size={90} score={result.score} />
                <div>
                  <p style={{ fontSize: 12, color: 'var(--clr-text-3)' }}>Composite Score</p>
                  <p style={{ fontSize: 13, fontWeight: 600, color: result.approved ? 'var(--clr-green)' : 'var(--clr-red)' }}>
                    Threshold: 55/100
                  </p>
                  {result.is_fallback && (
                    <p style={{ fontSize: 10, color: 'var(--clr-amber)', marginTop: 4 }}>
                      ⚡ Fallback mode
                    </p>
                  )}
                </div>
              </div>

              {/* Reasoning */}
              <div style={{
                padding: '12px 14px',
                background: 'var(--clr-surface)',
                borderRadius: 10,
                border: '1px solid var(--clr-border)',
              }}>
                <p style={{ fontSize: 11, color: 'var(--clr-text-3)', marginBottom: 6 }}>AI Reasoning</p>
                <p style={{ fontSize: 12, lineHeight: 1.7, color: 'var(--clr-text-1)' }}>
                  {result.reasoning}
                </p>
              </div>

              {/* TX for selected farmer */}
              {selectedFarmer?.tx_signature && (
                <div style={{ marginTop: 14 }}>
                  <p style={{ fontSize: 11, color: 'var(--clr-text-3)', marginBottom: 6 }}>Blockchain Record</p>
                  <a
                    href={`https://explorer.solana.com/tx/${selectedFarmer.tx_signature}?cluster=devnet`}
                    target="_blank"
                    rel="noreferrer"
                    style={{
                      display: 'flex', alignItems: 'center', gap: 6,
                      padding: '9px 12px', borderRadius: 8,
                      background: 'var(--clr-green-dim)',
                      border: '1px solid rgba(74,222,128,0.20)',
                      color: 'var(--clr-green)', fontSize: 12, fontWeight: 600,
                      textDecoration: 'none',
                    }}
                  >
                    <span>⛓️</span>
                    <span className="mono" style={{ fontSize: 11 }}>
                      {selectedFarmer.tx_signature.slice(0, 16)}...
                    </span>
                    <span style={{ marginLeft: 'auto', fontSize: 10 }}>↗ Explorer</span>
                  </a>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Footer */}
      <footer style={{
        marginTop: 60, paddingTop: 24,
        borderTop: '1px solid var(--clr-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 8,
        fontSize: 12, color: 'var(--clr-text-3)',
      }}>
        <span>🌾 AgriSubsidy · AI Oracle for Solana · Hackathon MVP</span>
        <div style={{ display: 'flex', gap: 16 }}>
          <a href="http://127.0.0.1:8080/docs" target="_blank" rel="noreferrer"
            style={{ color: 'var(--clr-text-3)', textDecoration: 'none' }}>API Docs</a>
          <a href="https://explorer.solana.com/?cluster=devnet" target="_blank" rel="noreferrer"
            style={{ color: 'var(--clr-text-3)', textDecoration: 'none' }}>Solana Devnet</a>
        </div>
      </footer>
    </div>
  );
}
