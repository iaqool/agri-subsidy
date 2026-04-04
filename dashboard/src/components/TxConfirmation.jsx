const EXPLORER_BASE = 'https://explorer.solana.com/tx';

export default function TxConfirmation({ txSignature, approved }) {
  if (!txSignature) return null;

  const shortSig = `${txSignature.slice(0, 8)}...${txSignature.slice(-6)}`;
  const explorerUrl = `${EXPLORER_BASE}/${txSignature}?cluster=devnet`;

  return (
    <div style={{
      marginTop: 12,
      padding: '12px 14px',
      background: approved ? 'var(--clr-green-dim)' : 'var(--clr-red-dim)',
      border: `1px solid ${approved ? 'rgba(74,222,128,0.20)' : 'rgba(248,113,113,0.20)'}`,
      borderRadius: 10,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 10, flexWrap: 'wrap',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 16 }}>{approved ? '⛓️' : '🚫'}</span>
        <div>
          <p style={{ fontSize: 11, color: 'var(--clr-text-3)', marginBottom: 1 }}>
            {approved ? 'Transaction Submitted' : 'Rejected — No TX'}
          </p>
          {approved && (
            <p className="mono" style={{ fontSize: 12, color: 'var(--clr-green)' }}>
              {shortSig}
            </p>
          )}
        </div>
      </div>

      {approved && (
        <a
          href={explorerUrl}
          target="_blank"
          rel="noreferrer"
          id={`explorer-link-${txSignature?.slice(0, 8)}`}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 5,
            fontSize: 12, fontWeight: 600, color: 'var(--clr-green)',
            textDecoration: 'none', padding: '5px 10px',
            background: 'rgba(74,222,128,0.10)', borderRadius: 6,
            border: '1px solid rgba(74,222,128,0.20)',
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.background = 'rgba(74,222,128,0.20)';
            e.currentTarget.style.transform = 'translateY(-1px)';
          }}
          onMouseLeave={e => {
            e.currentTarget.style.background = 'rgba(74,222,128,0.10)';
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          <span>Solana Explorer</span>
          <span style={{ fontSize: 10 }}>↗</span>
        </a>
      )}
    </div>
  );
}
