const STAT_CONFIGS = [
  {
    key: 'total',
    label: 'Total Farmers',
    icon: '👨‍🌾',
    color: 'var(--clr-info)',
    bg: 'var(--clr-info-dim)',
  },
  {
    key: 'approved',
    label: 'Approved',
    icon: '✅',
    color: 'var(--clr-accent)',
    bg: 'var(--clr-primary-dim)',
  },
  {
    key: 'rejected',
    label: 'Rejected',
    icon: '❌',
    color: 'var(--clr-red)',
    bg: 'var(--clr-red-dim)',
  },
  {
    key: 'total_disbursed_sol',
    label: 'SOL Disbursed',
    icon: '◎',
    color: 'var(--clr-amber)',
    bg: 'var(--clr-amber-dim)',
    format: (v) => `${v?.toFixed(2) ?? '0.00'} SOL`,
  },
];

export default function StatsPanel({ stats, loading }) {
  return (
    <div className="grid-4">
      {STAT_CONFIGS.map((cfg, i) => {
        const raw = stats?.[cfg.key] ?? 0;
        const display = cfg.format ? cfg.format(raw) : raw;

        return (
          <div
            key={cfg.key}
            className="glass fade-in"
            style={{
              padding: '20px 22px',
              animationDelay: `${i * 0.07}s`,
              position: 'relative',
              overflow: 'hidden',
            }}
          >
            {/* Glow blob */}
            <div style={{
              position: 'absolute', top: -20, right: -20,
              width: 80, height: 80, borderRadius: '50%',
              background: cfg.bg,
              filter: 'blur(20px)',
            }} />

            <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', position: 'relative' }}>
              <div>
                <p style={{ fontSize: 12, color: 'var(--clr-text-3)', fontWeight: 500, marginBottom: 6 }}>
                  {cfg.label}
                </p>
                {loading ? (
                  <div className="skeleton" style={{ width: 60, height: 28, marginTop: 4 }} />
                ) : (
                  <p style={{ fontSize: 26, fontWeight: 800, color: cfg.color, lineHeight: 1 }}>
                    {display}
                  </p>
                )}
              </div>
              <div style={{
                width: 38, height: 38,
                background: cfg.bg,
                borderRadius: 10,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 18,
              }}>
                {cfg.icon}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
