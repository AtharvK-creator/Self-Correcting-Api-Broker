/**
 * Graph Explorer Page — FEAT-040+.
 * Contextual failure graph node visualization & search.
 */
'use client';

import { useState } from 'react';

export default function GraphExplorerPage() {
  const [nodeId, setNodeId] = useState('');
  const [nodeData, setNodeData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!nodeId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/graph/nodes/${nodeId.trim()}`);
      if (!res.ok) {
        throw new Error(`Node ${nodeId} not found`);
      }
      const data = await res.json();
      setNodeData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Node search failed');
      setNodeData(null);
    } finally {
      setLoading(false);
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
          <span style={{ fontWeight: 600, color: '#f1f5f9' }}>Graph Explorer</span>
        </div>
      </header>

      <main style={{ maxWidth: '1100px', margin: '0 auto', padding: '2rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem', color: '#f1f5f9' }}>
          Contextual Failure Graph
        </h1>
        <p style={{ color: '#64748b', fontSize: '0.9rem', marginBottom: '2rem' }}>
          Explore contextual graph nodes (API, ENDPOINT, ERROR_TYPE, ERROR_SIGNATURE, REQUEST_CONTEXT) and Node2Vec embeddings.
        </p>

        {/* Search */}
        <section style={{
          background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
          border: '1px solid #334155',
          borderRadius: '12px',
          padding: '1.5rem',
          marginBottom: '2rem',
        }}>
          <form onSubmit={handleSearch} style={{ display: 'flex', gap: '1rem' }}>
            <input
              type="text"
              placeholder="Enter Node ID (UUID)"
              value={nodeId}
              onChange={e => setNodeId(e.target.value)}
              style={{ flex: 1, padding: '0.75rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff', fontSize: '0.9rem', fontFamily: 'monospace' }}
            />
            <button
              type="submit"
              disabled={loading}
              style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', color: '#fff', border: 'none', borderRadius: '6px', padding: '0.75rem 1.5rem', fontWeight: 600, cursor: 'pointer' }}
            >
              {loading ? 'Searching…' : 'Inspect Node'}
            </button>
          </form>

          {error && <div style={{ color: '#fca5a5', marginTop: '1rem', fontSize: '0.85rem' }}>{error}</div>}
        </section>

        {/* Results */}
        {nodeData && (
          <section style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '12px', padding: '1.5rem' }}>
            <h2 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>Node Details</h2>
            <pre style={{ background: '#0f172a', padding: '1rem', borderRadius: '8px', color: '#4ade80', overflowX: 'auto', fontSize: '0.85rem' }}>
              {JSON.stringify(nodeData, null, 2)}
            </pre>
          </section>
        )}
      </main>
    </div>
  );
}
