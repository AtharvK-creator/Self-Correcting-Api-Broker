/**
 * APIs Registry Page — FEAT-040+.
 * View and register upstream APIs.
 */
'use client';

import { useEffect, useState } from 'react';
import { api, Api } from '@/lib/api';

export default function ApisPage() {
  const [apisList, setApisList] = useState<Api[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [registeredHost, setRegisteredHost] = useState('');
  const [description, setDescription] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function loadApis() {
    try {
      const data = await api.apis.list();
      setApisList(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load APIs');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadApis();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setFormError(null);
    try {
      await api.apis.create({
        name,
        base_url: baseUrl,
        registered_host: registeredHost || new URL(baseUrl).hostname,
        description: description || undefined,
      });
      setName('');
      setBaseUrl('');
      setRegisteredHost('');
      setDescription('');
      await loadApis();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : 'Failed to register API');
    } finally {
      setSubmitting(false);
    }
  }

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
          <span style={{ fontWeight: 600, color: '#f1f5f9' }}>API Registry</span>
        </div>
      </header>

      <main style={{ maxWidth: '1100px', margin: '0 auto', padding: '2rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '1.5rem', color: '#f1f5f9' }}>
          Upstream API Registry
        </h1>

        {/* Create form */}
        <section style={{
          background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
          border: '1px solid #334155',
          borderRadius: '12px',
          padding: '1.5rem',
          marginBottom: '2rem',
        }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>
            Register New Upstream API
          </h2>

          {formError && (
            <div style={{ background: '#7f1d1d22', border: '1px solid #7f1d1d', color: '#fca5a5', padding: '0.75rem', borderRadius: '8px', marginBottom: '1rem', fontSize: '0.85rem' }}>
              {formError}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>API Name</label>
              <input
                type="text"
                required
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. payment-gateway"
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff', fontSize: '0.9rem' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Base URL</label>
              <input
                type="url"
                required
                value={baseUrl}
                onChange={e => setBaseUrl(e.target.value)}
                placeholder="https://api.payments.com"
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff', fontSize: '0.9rem' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Registered Host (SSRF Security Target)</label>
              <input
                type="text"
                value={registeredHost}
                onChange={e => setRegisteredHost(e.target.value)}
                placeholder="api.payments.com (auto-derived if empty)"
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff', fontSize: '0.9rem' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Description</label>
              <input
                type="text"
                value={description}
                onChange={e => setDescription(e.target.value)}
                placeholder="Primary payment provider API"
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff', fontSize: '0.9rem' }}
              />
            </div>

            <div style={{ gridColumn: 'span 2', display: 'flex', justifyContent: 'flex-end' }}>
              <button
                type="submit"
                disabled={submitting}
                style={{
                  background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '0.6rem 1.5rem',
                  fontWeight: 600,
                  cursor: submitting ? 'wait' : 'pointer',
                }}
              >
                {submitting ? 'Registering…' : 'Register API'}
              </button>
            </div>
          </form>
        </section>

        {/* APIs list */}
        <section>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>
            Registered APIs ({apisList.length})
          </h2>

          {loading ? (
            <div style={{ color: '#64748b' }}>Loading APIs…</div>
          ) : apisList.length === 0 ? (
            <div style={{ color: '#64748b', background: '#1e293b55', padding: '2rem', textAlign: 'center', borderRadius: '8px' }}>
              No APIs registered yet. Use the form above to register your first upstream service.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {apisList.map(item => (
                <div key={item.id} style={{
                  background: '#1e293b',
                  border: '1px solid #334155',
                  borderRadius: '8px',
                  padding: '1rem 1.25rem',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}>
                  <div>
                    <div style={{ fontWeight: 600, color: '#f1f5f9', fontSize: '1rem' }}>{item.name}</div>
                    <div style={{ color: '#6366f1', fontSize: '0.85rem', fontFamily: 'monospace' }}>{item.base_url}</div>
                    {item.description && <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '0.25rem' }}>{item.description}</div>}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '0.75rem', color: '#64748b', fontFamily: 'monospace' }}>host: {item.registered_host}</span>
                    <span style={{
                      background: item.is_active ? '#22c55e22' : '#ef444422',
                      color: item.is_active ? '#4ade80' : '#fca5a5',
                      padding: '0.2rem 0.5rem',
                      borderRadius: '4px',
                      fontSize: '0.75rem',
                    }}>
                      {item.is_active ? 'ACTIVE' : 'INACTIVE'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
