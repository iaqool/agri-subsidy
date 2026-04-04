import { useEffect, useRef } from 'react';

/**
 * SVG circular gauge displaying score 0–100.
 * Color transitions: red → amber → green based on score.
 */
export default function ScoreGauge({ score, size = 120 }) {
  const prevRef = useRef(0);
  const displayRef = useRef(null);

  // Clamp score
  const safeScore = Math.min(100, Math.max(0, score ?? 0));

  // SVG geometry
  const cx = size / 2;
  const cy = size / 2;
  const r  = (size - 16) / 2;
  const circumference = 2 * Math.PI * r;
  const arc = (safeScore / 100) * circumference;
  const offset = circumference - arc;

  // Dynamic colour based on score
  const getColor = (s) => {
    if (s >= 70) return '#4ade80'; // green
    if (s >= 45) return '#fbbf24'; // amber
    return '#f87171';              // red
  };
  const color = getColor(safeScore);

  // Animate count-up
  useEffect(() => {
    const start = prevRef.current;
    const end = safeScore;
    const duration = 800;
    const startTime = performance.now();

    const tick = (now) => {
      const progress = Math.min((now - startTime) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      const current = Math.round(start + (end - start) * eased);
      if (displayRef.current) displayRef.current.textContent = current;
      if (progress < 1) requestAnimationFrame(tick);
      else prevRef.current = end;
    };
    requestAnimationFrame(tick);
  }, [safeScore]);

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        {/* Background track */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={8}
        />
        {/* Progress arc */}
        <circle
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke={color}
          strokeWidth={8}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{
            transition: 'stroke-dashoffset 0.8s cubic-bezier(0.34,1.56,0.64,1), stroke 0.4s ease',
            filter: `drop-shadow(0 0 6px ${color}80)`,
          }}
        />
      </svg>

      {/* Center label */}
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <span
          ref={displayRef}
          style={{ fontSize: size * 0.22, fontWeight: 800, color, lineHeight: 1 }}
        >
          {safeScore}
        </span>
        <span style={{ fontSize: size * 0.10, color: 'var(--clr-text-3)', marginTop: 2 }}>
          /100
        </span>
      </div>
    </div>
  );
}
