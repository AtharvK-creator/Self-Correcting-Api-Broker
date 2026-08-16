/**
 * Dashboard page — FEAT-040.
 * Displays system health, analytics, recent APIs, and recovery memory.
 */
'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

interface HealthData {
  status: string;
  uptime_seconds: number;
  version: string;
}

interface AnalyticsData {
  total_requests: number;
  total_success: number;
  total_failures: number;
  success_rate: number | null;
  total_recovery_attempts: number;
  total_recovered: number;
  recovery_rate: number | null;
  llm_invocations: number;
  llm_escalation_rate: number | null;
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div style={{
      background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
      border: '1px solid #334155',
      borderRadius: '12px',
      padding: '1.5rem',
      minWidth: '180px',
    }}>
      <div style={{ color: '#64748b', fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '0.5rem' }}>
        {label}
      </div>
      <div style={{ color: '#f1f5f9', fontSize: '2rem', fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </div>
      {sub && <div style={{ color: '#475569', fontSize: '0.75rem', marginTop: '0.25rem' }}>{sub}</div>}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    ok: '#22c55e',
    ready: '#22c55e',
    degraded: '#f59e0b',
    error: '#ef4444',
  };
  return (
    <span style={{
      background: colors[status] || '#6366f1',
      color: '#fff',
      borderRadius: '9999px',
      padding: '0.2rem 0.75rem',
      fontSize: '0.75rem',
      fontWeight: 600,
    }}>
      {status.toUpperCase()}
    </span>
  );
}

export default function DashboardPage() {
  const [health, setHealth] = useState<HealthData | null>(null);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const [h, a] = await Promise.all([
          api.health.live(),
          api.analytics.summary(),
        ]);
        setHealth(h);
        setAnalytics(a);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    }
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, []);

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
        backdropFilter: 'blur(8px)',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            width: '32px', height: '32px',
            background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
            borderRadius: '8px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '1rem',
          }}>⚡</div>
          <span style={{ fontWeight: 700, fontSize: '1rem', color: '#f1f5f9' }}>API Broker</span>
          {health && <StatusBadge status={health.status} />}
        </div>
        <nav style={{ display: 'flex', gap: '1.5rem' }}>
          {[
            { href: '/dashboard', label: 'Dashboard' },
            { href: '/apis', label: 'APIs' },
            { href: '/recovery-memory', label: 'Memory' },
            { href: '/graph', label: 'Graph' },
            { href: '/evaluation', label: 'Evaluation' },
          ].map(({ href, label }) => (
            <a key={href} href={href} style={{ color: '#94a3b8', textDecoration: 'none', fontSize: '0.9rem', transition: 'color 0.2s' }}
              onMouseEnter={e => (e.currentTarget.style.color = '#f1f5f9')}
              onMouseLeave={e => (e.currentTarget.style.color = '#94a3b8')}
            >{label}</a>
          ))}
        </nav>
      </header>

      <main style={{ maxWidth: '1200px', margin: '0 auto', padding: '2rem' }}>
        <div style={{ marginBottom: '2rem' }}>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: '#f1f5f9', marginBottom: '0.5rem' }}>
            System Dashboard
          </h1>
          <p style={{ color: '#64748b', fontSize: '0.9rem' }}>
            Real-time monitoring for the Self-Correcting API Broker
            {health && ` · v${health.version} · uptime ${Math.floor(health.uptime_seconds / 60)}m`}
          </p>
        </div>

        {loading && (
          <div style={{ color: '#64748b', padding: '2rem 0' }}>Loading metrics…</div>
        )}

        {error && (
          <div style={{
            background: '#1e0a0a', border: '1px solid #7f1d1d',
            borderRadius: '8px', padding: '1rem', marginBottom: '1.5rem', color: '#fca5a5',
          }}>
            ⚠ {error} — Is the backend running?
          </div>
        )}

        {analytics && (
          <>
            {/* Key metrics */}
            <section style={{ marginBottom: '2rem' }}>
              <h2 style={{ fontSize: '0.875rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '1rem' }}>
                Request Metrics
              </h2>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem' }}>
                <StatCard label="Total Requests" value={analytics.total_requests.toLocaleString()} />
                <StatCard
                  label="Success Rate"
                  value={analytics.success_rate != null ? `${(analytics.success_rate * 100).toFixed(1)}%` : '—'}
                  sub={`${analytics.total_success.toLocaleString()} successes`}
                />
                <StatCard label="Total Failures" value={analytics.total_failures.toLocaleString()} />
                <StatCard
                  label="Recovery Rate"
                  value={analytics.recovery_rate != null ? `${(analytics.recovery_rate * 100).toFixed(1)}%` : '—'}
                  sub={`${analytics.total_recovered} / ${analytics.total_recovery_attempts} attempts`}
                />
                <StatCard
                  label="LLM Invocations"
                  value={analytics.llm_invocations.toLocaleString()}
                  sub={analytics.llm_escalation_rate != null ? `${(analytics.llm_escalation_rate * 100).toFixed(1)}% escalation rate` : undefined}
                />
              </div>
            </section>

            {/* Recovery breakdown */}
            <section style={{ marginBottom: '2rem' }}>
              <h2 style={{ fontSize: '0.875rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '1rem' }}>
                Recovery Pipeline
              </h2>
              <div style={{
                background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
                border: '1px solid #334155',
                borderRadius: '12px',
                padding: '1.5rem',
              }}>
                <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
                  <div>
                    <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: '0.25rem' }}>Recovery Attempts</div>
                    <div style={{ color: '#f1f5f9', fontSize: '1.5rem', fontWeight: 700 }}>{analytics.total_recovery_attempts}</div>
                  </div>
                  <div>
                    <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: '0.25rem' }}>Recovered</div>
                    <div style={{ color: '#22c55e', fontSize: '1.5rem', fontWeight: 700 }}>{analytics.total_recovered}</div>
                  </div>
                  <div>
                    <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: '0.25rem' }}>LLM Escalations</div>
                    <div style={{ color: '#a78bfa', fontSize: '1.5rem', fontWeight: 700 }}>{analytics.llm_invocations}</div>
                  </div>
                  <div>
                    <div style={{ color: '#64748b', fontSize: '0.75rem', marginBottom: '0.25rem' }}>Unrecovered</div>
                    <div style={{ color: '#ef4444', fontSize: '1.5rem', fontWeight: 700 }}>
                      {analytics.total_recovery_attempts - analytics.total_recovered}
                    </div>
                  </div>
                </div>

                {/* Visual bar */}
                {analytics.total_recovery_attempts > 0 && (
                  <div style={{ marginTop: '1rem' }}>
                    <div style={{ height: '6px', background: '#1e293b', borderRadius: '9999px', overflow: 'hidden' }}>
                      <div style={{
                        height: '100%',
                        width: `${(analytics.total_recovered / analytics.total_recovery_attempts) * 100}%`,
                        background: 'linear-gradient(90deg, #22c55e, #4ade80)',
                        borderRadius: '9999px',
                        transition: 'width 0.5s ease',
                      }} />
                    </div>
                    <div style={{ color: '#475569', fontSize: '0.7rem', marginTop: '0.25rem' }}>
                      Recovery fill
                    </div>
                  </div>
                )}
              </div>
            </section>
          </>
        )}

        {/* Quick links */}
        <section>
          <h2 style={{ fontSize: '0.875rem', color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '1rem' }}>
            Quick Access
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '1rem' }}>
            {[
              { href: '/apis', icon: '🔌', label: 'API Registry', desc: 'Register and manage upstream APIs' },
              { href: '/recovery-memory', icon: '🧠', label: 'Recovery Memory', desc: 'Validated correction knowledge base' },
              { href: '/graph', icon: '🕸', label: 'Graph Explorer', desc: 'Contextual failure graph nodes' },
              { href: '/evaluation', icon: '📊', label: 'Evaluation', desc: 'Baseline comparison experiments' },
              { href: '/broker', icon: '⚡', label: 'Broker Console', desc: 'Execute and test API calls' },
            ].map(({ href, icon, label, desc }) => (
              <a key={href} href={href} style={{
                background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
                border: '1px solid #334155',
                borderRadius: '12px',
                padding: '1.25rem',
                textDecoration: 'none',
                display: 'block',
                transition: 'border-color 0.2s, transform 0.2s',
              }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.borderColor = '#6366f1';
                  (e.currentTarget as HTMLElement).style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.borderColor = '#334155';
                  (e.currentTarget as HTMLElement).style.transform = 'translateY(0)';
                }}
              >
                <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>{icon}</div>
                <div style={{ color: '#f1f5f9', fontWeight: 600, marginBottom: '0.25rem' }}>{label}</div>
                <div style={{ color: '#64748b', fontSize: '0.8rem' }}>{desc}</div>
              </a>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
