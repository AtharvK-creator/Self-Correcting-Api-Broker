/**
 * Broker Console Page — FEAT-040+.
 * Interactive request runner: send API requests through the self-correcting broker.
 */
'use client';

import { useEffect, useState } from 'react';
import { api, Api } from '@/lib/api';

export default function BrokerConsolePage() {
  const [apis, setApis] = useState<Api[]>([]);
  const [selectedApiId, setSelectedApiId] = useState('');
  const [endpointPath, setEndpointPath] = useState('/v1/test');
  const [method, setMethod] = useState('GET');
  const [headersJson, setHeadersJson] = useState('{\n  "Accept": "application/json"\n}');
  const [bodyJson, setBodyJson] = useState('{\n  "customerId": "12345"\n}');
  const [recoveryMode, setRecoveryMode] = useState('auto');

  const [executing, setExecuting] = useState(false);
  const [response, setResponse] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.apis.list().then(data => {
      setApis(data);
      if (data.length > 0) setSelectedApiId(data[0].id);
    }).catch(() => {});
  }, []);

  async function handleExecute(e: React.FormEvent) {
    e.preventDefault();
    setExecuting(true);
    setError(null);
    setResponse(null);

    let parsedHeaders = {};
    let parsedBody = null;

    try {
      if (headersJson.trim()) parsedHeaders = JSON.parse(headersJson);
      if (bodyJson.trim() && method !== 'GET') parsedBody = JSON.parse(bodyJson);
    } catch (err) {
      setError('Invalid JSON in headers or body');
      setExecuting(false);
      return;
    }

    try {
      const correlationId = crypto.randomUUID();
      const res = await fetch('http://localhost:8000/api/v1/broker/execute', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Correlation-ID': correlationId,
        },
        body: JSON.stringify({
          api_id: selectedApiId,
          endpoint_path: endpointPath,
          method,
          headers: parsedHeaders,
          query_params: {},
          body: parsedBody,
          recovery_mode: recoveryMode,
        }),
      });

      const data = await res.json();
      setResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Execution failed');
    } finally {
      setExecuting(false);
    }
  }

  return (
    <div style={{ minHeight: '100vh', background: '#0f1117', color: '#e2e8f0', fontFamily: "'Inter', system-ui, sans-serif" }}>
      <header style={{
        borderBottom: '1px solid #1e293b',
        padding: '1rem 2rem',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'rgba(15,17,23,0.95)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <a href="/dashboard" style={{ color: '#6366f1', textDecoration: 'none', fontWeight: 700 }}>⚡ API Broker</a>
          <span style={{ color: '#475569' }}>/</span>
          <span style={{ fontWeight: 600, color: '#f1f5f9' }}>Broker Console</span>
        </div>
      </header>

      <main style={{ maxWidth: '1100px', margin: '0 auto', padding: '2rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem', color: '#f1f5f9' }}>
          Interactive Broker Console
        </h1>
        <p style={{ color: '#64748b', fontSize: '0.9rem', marginBottom: '2rem' }}>
          Execute API requests through the Self-Correcting Broker pipeline. Failures are automatically classified, graph-analyzed, and recovered.
        </p>

        <form onSubmit={handleExecute} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
          {/* Request Config */}
          <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '12px', padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9' }}>Request Configuration</h2>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Target Upstream API</label>
              <select
                value={selectedApiId}
                onChange={e => setSelectedApiId(e.target.value)}
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff' }}
              >
                {apis.map(a => (
                  <option key={a.id} value={a.id}>{a.name} ({a.base_url})</option>
                ))}
              </select>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <select
                value={method}
                onChange={e => setMethod(e.target.value)}
                style={{ padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#6366f1', fontWeight: 700 }}
              >
                {['GET', 'POST', 'PUT', 'DELETE', 'PATCH'].map(m => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <input
                type="text"
                value={endpointPath}
                onChange={e => setEndpointPath(e.target.value)}
                placeholder="/v1/endpoint"
                style={{ flex: 1, padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff', fontFamily: 'monospace' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Recovery Mode</label>
              <select
                value={recoveryMode}
                onChange={e => setRecoveryMode(e.target.value)}
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff' }}
              >
                <option value="auto">auto — Full Graph + Memory + Safety Recovery</option>
                <option value="manual">manual — Policy / Approval Required Only</option>
                <option value="disabled">disabled — Passthrough Only (No Recovery)</option>
              </select>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Body (JSON)</label>
              <textarea
                rows={5}
                value={bodyJson}
                onChange={e => setBodyJson(e.target.value)}
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#4ade80', fontFamily: 'monospace', fontSize: '0.85rem' }}
              />
            </div>

            <button
              type="submit"
              disabled={executing || !selectedApiId}
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', color: '#fff', border: 'none', borderRadius: '6px', padding: '0.75rem', fontWeight: 600, cursor: 'pointer' }}
            >
              {executing ? 'Executing Request & Recovery…' : '⚡ Execute Through Broker'}
            </button>

            {error && <div style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{error}</div>}
          </div>

          {/* Response Output */}
          <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '12px', padding: '1.5rem' }}>
            <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>Broker Response</h2>

            {!response && !executing && (
              <div style={{ color: '#64748b', textAlign: 'center', padding: '4rem 0' }}>
                Fill out the configuration and click Execute to see the broker result.
              </div>
            )}

            {executing && (
              <div style={{ color: '#a78bfa', textAlign: 'center', padding: '4rem 0' }}>
                Executing upstream request & processing self-correction pipeline…
              </div>
            )}

            {response && (
              <div>
                <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
                  <span style={{
                    background: response.status === 'success' ? '#22c55e22' : response.status === 'recovered' ? '#6366f122' : '#ef444422',
                    color: response.status === 'success' ? '#4ade80' : response.status === 'recovered' ? '#818cf8' : '#fca5a5',
                    padding: '0.25rem 0.75rem',
                    borderRadius: '9999px',
                    fontWeight: 700,
                    fontSize: '0.8rem',
                  }}>
                    {response.status.toUpperCase()}
                  </span>
                  {response.http_status && (
                    <span style={{ background: '#334155', color: '#fff', padding: '0.25rem 0.5rem', borderRadius: '4px', fontSize: '0.8rem', fontFamily: 'monospace' }}>
                      HTTP {response.http_status}
                    </span>
                  )}
                </div>

                <pre style={{ background: '#0f172a', padding: '1rem', borderRadius: '8px', color: '#e2e8f0', overflowX: 'auto', fontSize: '0.85rem' }}>
                  {JSON.stringify(response, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </form>
      </main>
    </div>
  );
}
