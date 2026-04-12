import { useState, useEffect, useRef, useCallback } from 'react';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8080').replace(/\/$/, '');

async function requestJson(path, options) {
  let response;

  try {
    response = await fetch(`${API_BASE}${path}`, options);
  } catch (error) {
    throw new Error(
      `Dala API is offline. Check VITE_API_BASE_URL or start backend on ${API_BASE}.`,
    );
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    const message =
      payload?.detail ||
      payload?.message ||
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return payload;
}

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
    return requestJson('/api/demo/seed', { method: 'POST' });
  },

  async getFarmers() {
    return requestJson('/api/farmers');
  },

  async getStats() {
    return requestJson('/api/stats');
  },

  async evaluate(wallet, lat, lon) {
    return requestJson('/api/evaluate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet_address: wallet, lat, lon }),
    });
  },
};
