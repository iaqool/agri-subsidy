import ScoreGauge from './ScoreGauge';
import TxConfirmation from './TxConfirmation';

// Country/region labels for demo farmer wallets
const REGION_NAMES = {
  '4pMnsypmRtd94bK94LXjFPWghpXN5WfCcLvnJhoUdX5z': { name: 'Kostanay Region', flag: '🇰🇿', crop: 'Wheat' },
  'EeqwDr7kNxp4y9vj4MaQijv4BmgAm3WXArzZM5WikD6U': { name: 'North Kazakhstan', flag: '🇰🇿', crop: 'Wheat' },
  'CHaGvsfMx5YKE3mYq7huQM6keRN2UUsfhwAZMypWw7KC': { name: 'Akmola Region', flag: '🇰🇿', crop: 'Wheat' },
  'FZA62o7rNFBmx5g1hFyCmpRYWhpxAHTiqnYUaRd7EGfL': { name: 'Aktobe Region', flag: '🇰🇿', crop: 'Wheat' },
  '8jm7bVG8CiqxDmohHUuMk5R3WZkucTrXPUDsDhzvLQ3p': { name: 'Almaty Region', flag: '🇰🇿', crop: 'Corn' },
};

function getRegionInfo(wallet) {
  return REGION_NAMES[wallet] ?? { name: `${wallet.slice(0, 12)}...`, flag: '🌍', crop: 'Mixed' };
}

function StatusBadge({ status }) {
  const map = {
    approved: { cls: 'badge-approved', label: '✓ Approved' },
    rejected: { cls: 'badge-rejected', label: '✗ Rejected' },
    pending:  { cls: 'badge-pending',  label: '◷ Pending' },
  };
  const cfg = map[status] ?? map.pending;
  return <span className={`badge ${cfg.cls}`}>{cfg.label}</span>;
}

export default function FarmerCard({ farmer, selected, onSelect, onEvaluate, evaluating }) {
  const region = getRegionInfo(farmer.wallet);
  const isEvaluating = evaluating && selected;

  const cardStyle = {
    padding: '20px',
    cursor: 'pointer',
    position: 'relative',
    overflow: 'hidden',
    transition: 'all 0.25s ease',
    background: 'linear-gradient(160deg, rgba(99,102,241,.08), rgba(12,12,24,.66))',
    ...(selected ? {
      borderColor: 'rgba(99,102,241,0.5)',
      boxShadow: '0 0 0 1px rgba(99,102,241,0.22), 0 8px 32px rgba(0,0,0,0.4)',
    } : {}),
  };

  return (
    <div
      id={`farmer-card-${farmer.wallet.slice(0, 8)}`}
      className="glass fade-in"
      style={cardStyle}
      onClick={() => onSelect(farmer.wallet)}
    >
      {/* Selection indicator */}
      {selected && (
        <div style={{
          position: 'absolute', top: 0, left: 0, right: 0, height: 2,
          background: 'linear-gradient(90deg, transparent, var(--clr-primary), transparent)',
        }} />
      )}

      {/* Top row: flag + status */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{
            width: 42, height: 42, borderRadius: 12, fontSize: 22,
            background: 'var(--clr-surface-2)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            {region.flag}
          </div>
          <div>
            <p style={{ fontWeight: 700, fontSize: 13, lineHeight: 1.2 }}>{region.name}</p>
            <p style={{ fontSize: 11, color: 'var(--clr-text-3)', marginTop: 2 }}>🌱 {region.crop}</p>
          </div>
        </div>
        <StatusBadge status={farmer.status} />
      </div>

      {/* Wallet address */}
      <p className="mono" style={{ fontSize: 10, color: 'var(--clr-text-3)', marginBottom: 14 }}>
        {farmer.wallet.slice(0, 20)}...
      </p>

      {/* Coords */}
      <div style={{
        display: 'flex', gap: 10, marginBottom: 16,
        fontSize: 11, color: 'var(--clr-text-3)',
      }}>
        <span>📍 {farmer.lat}°N</span>
        <span>⟷ {farmer.lon}°E</span>
      </div>

      {/* Score gauge if available */}
      {farmer.score != null && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 14 }}>
          <ScoreGauge score={farmer.score} size={72} />
          <div>
            <p style={{ fontSize: 11, color: 'var(--clr-text-3)' }}>AI Score</p>
            <p style={{ fontSize: 12, color: farmer.status === 'approved' ? 'var(--clr-accent)' : 'var(--clr-red)', fontWeight: 600 }}>
              {farmer.status === 'approved' ? 'Relief approved' : 'Relief denied'}
            </p>
          </div>
        </div>
      )}

      {/* TX Link */}
      <TxConfirmation txSignature={farmer.tx_signature} approved={farmer.status === 'approved'} />

      {/* Evaluate button */}
      <button
        id={`evaluate-btn-${farmer.wallet.slice(0, 8)}`}
        className="btn btn-primary"
        style={{ width: '100%', marginTop: 12, justifyContent: 'center' }}
        onClick={(e) => {
          e.stopPropagation();
          onEvaluate(farmer);
        }}
        disabled={isEvaluating || farmer.status === 'approved'}
      >
        {isEvaluating ? (
          <><span className="spinner" /> Evaluating...</>
        ) : farmer.status === 'approved' ? (
          '✓ Complete'
        ) : (
          '🔍 Evaluate'
        )}
      </button>
    </div>
  );
}
