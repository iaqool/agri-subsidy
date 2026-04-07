import { useState } from 'react';

export default function Header({ onSeedDemo, loading }) {
  const [seeded, setSeeded] = useState(false);

  const handleSeed = async () => {
    const ok = await onSeedDemo();
    if (ok) {
      setSeeded(true);
      setTimeout(() => setSeeded(false), 3000);
    }
  };

  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '20px 0 28px',
      borderBottom: '1px solid var(--clr-border)',
      marginBottom: '32px',
      flexWrap: 'wrap',
      gap: '16px',
    }}>
      {/* Logo + Title */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
        <div style={{
          width: 44, height: 44,
          borderRadius: 12,
          background: 'linear-gradient(135deg, var(--clr-primary), #4338ca)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 22,
          boxShadow: '0 0 20px rgba(99,102,241,0.35)',
        }}>
          ◈
        </div>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h1 style={{ fontSize: 22, fontWeight: 500, letterSpacing: '-0.03em', fontFamily: 'Bricolage Grotesque, sans-serif' }}>
              Dala Network
            </h1>
            <span style={{
              fontSize: 10, fontWeight: 700, letterSpacing: '0.1em',
              background: 'var(--clr-primary-dim)', color: 'var(--clr-accent)',
              padding: '2px 7px', borderRadius: 100, textTransform: 'uppercase',
            }}>
              oracle
            </span>
          </div>
          <p style={{ fontSize: 12, color: 'var(--clr-text-3)', marginTop: 1 }}>
            On-chain climate intelligence · Solana Devnet
          </p>
        </div>
      </div>

      {/* Right Controls */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* Live indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--clr-text-3)' }}>
          <span style={{
            width: 7, height: 7, borderRadius: '50%',
            background: 'var(--clr-primary)',
            display: 'inline-block',
            animation: 'pulse-dot 2s infinite',
          }} />
          Solana Devnet
        </div>

        <button
          id="seed-demo-btn"
          className="btn btn-secondary"
          onClick={handleSeed}
          disabled={loading}
          style={{ fontSize: 13 }}
        >
          {loading ? <span className="spinner" /> : '🌱'}
          {seeded ? 'Seeds loaded!' : 'Load Demo'}
        </button>

        <a
          href="https://github.com/iaqool/agri-subsidy"
          target="_blank"
          rel="noreferrer"
          className="btn btn-secondary"
          style={{ fontSize: 13 }}
        >
          📚 Read Docs
        </a>
      </div>
    </header>
  );
}
