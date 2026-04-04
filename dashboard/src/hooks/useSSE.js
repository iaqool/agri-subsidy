import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = 'http://127.0.0.1:8080';

/**
 * Custom hook for Server-Sent Events streaming.
 * Connects to /api/stream/{evaluationId} and collects AI log entries.
 */
export function useSSE(evaluationId) {
  const [logs, setLogs]       = useState([]);
  const [done, setDone]       = useState(false);
  const [result, setResult]   = useState(null);
  const [error, setError]     = useState(null);
  const esRef = useRef(null);

  useEffect(() => {
    if (!evaluationId) return;

    // Reset state
    setLogs([]);
    setDone(false);
    setResult(null);
    setError(null);

    const es = new EventSource(`${API_BASE}/api/stream/${evaluationId}`);
    esRef.current = es;

    es.onmessage = (e) => {
      try {
        const entry = JSON.parse(e.data);
        setLogs(prev => [...prev, { ...entry, id: Date.now() + Math.random() }]);
      } catch {
        // ignore malformed
      }
    };

    es.addEventListener('done', (e) => {
      try {
        const res = JSON.parse(e.data);
        setResult(res);
      } catch {}
      setDone(true);
      es.close();
    });

    es.addEventListener('error', (e) => {
      try {
        const errData = JSON.parse(e.data);
        setError(errData.error || 'Unknown error');
      } catch {
        // Connection error – not a streamed error message
        if (es.readyState === EventSource.CLOSED) {
          setDone(true);
        }
      }
      es.close();
    });

    return () => {
      es.close();
    };
  }, [evaluationId]);

  const close = useCallback(() => esRef.current?.close(), []);

  return { logs, done, result, error, close };
}

/**
 * Main API helper functions
 */
export const api = {
  async seedDemo() {
    const r = await fetch(`${API_BASE}/api/demo/seed`, { method: 'POST' });
    return r.json();
  },

  async getFarmers() {
    const r = await fetch(`${API_BASE}/api/farmers`);
    return r.json();
  },

  async getStats() {
    const r = await fetch(`${API_BASE}/api/stats`);
    return r.json();
  },

  async evaluate(wallet, lat, lon) {
    const r = await fetch(`${API_BASE}/api/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet_address: wallet, lat, lon }),
    });
    return r.json();
  },
};
