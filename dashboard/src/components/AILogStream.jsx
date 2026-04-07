import { useEffect, useRef } from 'react';

const STEP_ICONS = {
  '🌍': '#22d3ee',
  '🌤️': '#22d3ee',
  '🛰️': '#22d3ee',
  '🌿': '#818cf8',
  '⚙️': '#94a3b8',
  '📊': '#fbbf24',
  '🤖': '#a78bfa',
  '🔌': '#a78bfa',
  '📡': '#22d3ee',
  '✅': '#818cf8',
  '❌': '#f87171',
  '⚠️': '#fbbf24',
  '🔄': '#fbbf24',
  '⛓️': '#818cf8',
  '🚫': '#f87171',
};

function getStepColor(step) {
  for (const [emoji, color] of Object.entries(STEP_ICONS)) {
    if (step?.startsWith(emoji)) return color;
  }
  return 'var(--clr-text-2)';
}

export default function AILogStream({ logs, done, running }) {
  const bottomRef = useRef(null);
  const containerRef = useRef(null);

  // Auto-scroll to bottom as new logs arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs.length]);

  return (
    <div className="glass" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        padding: '16px 20px',
        borderBottom: '1px solid var(--clr-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 17 }}>🤖</span>
          <div>
            <p style={{ fontWeight: 700, fontSize: 14 }}>AI Reasoning Log</p>
            <p style={{ fontSize: 11, color: 'var(--clr-text-3)' }}>OpenAI chain-of-thought · real-time stream</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          {running && !done && (
            <>
              <span className="spinner" style={{ width: 12, height: 12 }} />
              <span style={{ fontSize: 11, color: 'var(--clr-teal)' }}>Streaming...</span>
            </>
          )}
          {done && (
            <span style={{ fontSize: 11, color: 'var(--clr-accent)' }}>● Complete</span>
          )}
          {!running && !done && (
            <span style={{ fontSize: 11, color: 'var(--clr-text-3)' }}>Idle</span>
          )}
        </div>
      </div>

      {/* Log area */}
      <div
        ref={containerRef}
        id="ai-log-stream"
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '16px 20px',
          minHeight: 300,
          maxHeight: 480,
          display: 'flex',
          flexDirection: 'column',
          gap: 0,
        }}
      >
        {logs.length === 0 && !running ? (
          <div style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexDirection: 'column', gap: 10, color: 'var(--clr-text-3)',
          }}>
            <span style={{ fontSize: 32 }}>🌱</span>
            <p style={{ fontSize: 13 }}>Select a farmer and click <strong style={{ color: 'var(--clr-text-2)' }}>Evaluate</strong> to start</p>
          </div>
        ) : (
          logs.map((entry, i) => {
            const color = getStepColor(entry.step);
            return (
              <div
                key={entry.id ?? i}
                style={{
                  padding: '10px 12px',
                  marginBottom: 6,
                  borderRadius: 8,
                  background: 'var(--clr-surface)',
                  border: '1px solid var(--clr-border)',
                  borderLeft: `3px solid ${color}`,
                  animation: 'fadeInUp 0.25s ease both',
                }}
              >
                <p style={{ fontSize: 11, fontWeight: 700, color, marginBottom: 3, letterSpacing: '0.02em' }}>
                  {entry.step}
                </p>
                <p className="mono" style={{ fontSize: 12, color: 'var(--clr-text-1)', lineHeight: 1.6 }}>
                  {entry.content}
                </p>
              </div>
            );
          })
        )}

        {/* Blinking cursor while streaming */}
        {running && !done && logs.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 12px' }}>
            <span style={{
              display: 'inline-block',
              width: 8, height: 14,
              background: 'var(--clr-primary)',
              borderRadius: 2,
              animation: 'pulse-dot 0.9s infinite',
            }} />
            <span style={{ fontSize: 11, color: 'var(--clr-text-3)' }}>Processing...</span>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
