/**
 * Recovery Memory Page — FEAT-040+.
 * Displays validated recovery memory cases and maturity progression.
 */
'use client';

import { useEffect, useState } from 'react';
import { api, RecoveryCase } from '@/lib/api';

export default function RecoveryMemoryPage() {
  const [cases, setCases] = useState<RecoveryCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [maturityFilter, setMaturityFilter] = useState<string>('');

  async function loadMemory() {
    setLoading(true);
    try {
      const data = await api.memory.list({
        maturity: maturityFilter || undefined,
        limit: 50,
      });
      setCases(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load recovery memory');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadMemory();
  }, [maturityFilter]);

  const maturityColors: Record<string, { bg: string; text: string }> = {
    PROPOSED: { bg: '#6366f122', text: '#818cf8' },
    VALIDATED: { bg: '#3b82f622', text: '#60a5fa' },
    ESTABLISHED: { bg: '#22c55e22', text: '#4ade80' },
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0f1117', color: '#e2e8f0', fontFamily: "'Inter', system-ui, sans-serif" }}>
      {/* Header */}
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
          <span style={{ fontWeight: 600, color: '#f1f5f9' }}>Recovery Memory</span>
        </div>
      </header>

      <main style={{ maxWidth: '1100px', margin: '0 auto', padding: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: '#f1f5f9', marginBottom: '0.25rem' }}>
              Accumulated Recovery Memory
            </h1>
            <p style={{ color: '#64748b', fontSize: '0.85rem' }}>
              Validated correction knowledge base that enables deterministic reuse and reduces LLM escalation.
            </p>
          </div>

          {/* Filter */}
          <select
            value={maturityFilter}
            onChange={e => setMaturityFilter(e.target.value)}
            style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', color: '#fff', padding: '0.5rem 1rem', fontSize: '0.85rem' }}
          >
            <option value="">All Maturities</option>
            <option value="PROPOSED">PROPOSED (LLM source)</option>
            <option value="VALIDATED">VALIDATED (Confirmed reuse)</option>
            <option value="ESTABLISHED">ESTABLISHED (High confidence)</option>
          </select>
        </div>

        {loading ? (
          <div style={{ color: '#64748b' }}>Loading memory cases…</div>
        ) : error ? (
          <div style={{ background: '#7f1d1d22', border: '1px solid #7f1d1d', color: '#fca5a5', padding: '1rem', borderRadius: '8px' }}>{error}</div>
        ) : cases.length === 0 ? (
          <div style={{ color: '#64748b', background: '#1e293b55', padding: '3rem', textAlign: 'center', borderRadius: '8px' }}>
            No recovery cases found for filter &quot;{maturityFilter || 'all'}&quot;.
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
            {cases.map(item => {
              const colors = maturityColors[item.maturity] || { bg: '#334155', text: '#94a3b8' };
              return (
                <div key={item.id} style={{
                  background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
                  border: '1px solid #334155',
                  borderRadius: '10px',
                  padding: '1.25rem',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                }}>
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                      <span style={{
                        background: colors.bg,
                        color: colors.text,
                        borderRadius: '4px',
                        padding: '0.2rem 0.5rem',
                        fontSize: '0.75rem',
                        fontWeight: 700,
                      }}>
                        {item.maturity}
                      </span>
                      <span style={{ color: '#64748b', fontSize: '0.75rem', fontFamily: 'monospace' }}>
                        src: {item.source}
                      </span>
                    </div>

                    <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.5rem' }}>
                      Signature Hash:
                    </div>
                    <div style={{
                      background: '#0f172a',
                      borderRadius: '4px',
                      padding: '0.4rem',
                      fontFamily: 'monospace',
                      fontSize: '0.75rem',
                      color: '#a78bfa',
                      wordBreak: 'break-all',
                      marginBottom: '1rem',
                    }}>
                      {item.failure_signature}
                    </div>
                  </div>

                  <div style={{ borderTop: '1px solid #334155', paddingTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: '#94a3b8' }}>
                    <div>
                      Success: <strong style={{ color: '#22c55e' }}>{item.success_count}</strong> / Fail: <strong style={{ color: '#ef4444' }}>{item.failure_count}</strong>
                    </div>
                    <div>
                      Confidence: <strong style={{ color: '#f1f5f9' }}>{(item.confidence * 100).toFixed(0)}%</strong>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
}
