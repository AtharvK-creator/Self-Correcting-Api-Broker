/**
 * Evaluation Page — FEAT-043+.
 * Run and compare experimental evaluation baselines (B0-B3 vs P1).
 */
'use client';

import { useEffect, useState } from 'react';

export default function EvaluationPage() {
  const [runs, setRuns] = useState<any[]>([]);
  const [baseline, setBaseline] = useState('P1');
  const [name, setName] = useState('P1 Graph+Memory Benchmark');
  const [creating, setCreating] = useState(false);

  async function loadRuns() {
    try {
      const res = await fetch('http://localhost:8000/api/v1/evaluation/runs/latest');
      if (res.ok) {
        const data = await res.json();
        setRuns([data]);
      }
    } catch {}
  }

  useEffect(() => {
    loadRuns();
  }, []);

  async function handleCreateAndRun(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      // 1. Create run
      const createRes = await fetch('http://localhost:8000/api/v1/evaluation/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          baseline,
          scenario_set: 'scenario_lab_v1',
          model_version: 'gemini-2.0-flash-exp',
          graph_version: 'node2vec-v1',
        }),
      });
      const run = await createRes.json();

      // 2. Trigger execution
      const execRes = await fetch(`http://localhost:8000/api/v1/evaluation/runs/${run.id}/execute`, {
        method: 'POST',
      });
      const completed = await execRes.json();
      setRuns(prev => [completed, ...prev]);
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
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
          <span style={{ fontWeight: 600, color: '#f1f5f9' }}>Evaluation Framework</span>
        </div>
      </header>

      <main style={{ maxWidth: '1100px', margin: '0 auto', padding: '2rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.5rem', color: '#f1f5f9' }}>
          Experimental Evaluation Lab
        </h1>
        <p style={{ color: '#64748b', fontSize: '0.9rem', marginBottom: '2rem' }}>
          Run controlled benchmarks comparing baselines (B0: Client, B1: Retry, B2: Rules, B3: LLM-Only) vs P1 (Proposed Graph + Memory + Safety).
        </p>

        {/* Experiment trigger */}
        <section style={{
          background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
          border: '1px solid #334155',
          borderRadius: '12px',
          padding: '1.5rem',
          marginBottom: '2rem',
        }}>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>Trigger New Experiment</h2>

          <form onSubmit={handleCreateAndRun} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Run Name</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff' }}
              />
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.25rem' }}>Baseline / System</label>
              <select
                value={baseline}
                onChange={e => setBaseline(e.target.value)}
                style={{ width: '100%', padding: '0.6rem', background: '#0f172a', border: '1px solid #334155', borderRadius: '6px', color: '#fff' }}
              >
                <option value="B0">B0 — Ordinary Client (No Recovery)</option>
                <option value="B1">B1 — Static Exponential Retry</option>
                <option value="B2">B2 — Rule-Based Mappings Only</option>
                <option value="B3">B3 — LLM-Only (No Safety/Memory)</option>
                <option value="P1">P1 — Proposed (Graph + Safety + Memory)</option>
              </select>
            </div>

            <div style={{ display: 'flex', alignItems: 'flex-end' }}>
              <button
                type="submit"
                disabled={creating}
                style={{ width: '100%', background: 'linear-gradient(135deg, #6366f1, #8b5cf6)', color: '#fff', border: 'none', borderRadius: '6px', padding: '0.6rem', fontWeight: 600, cursor: 'pointer' }}
              >
                {creating ? 'Running Scenario Lab…' : '🚀 Run Experiment'}
              </button>
            </div>
          </form>
        </section>

        {/* Results */}
        <section>
          <h2 style={{ fontSize: '1rem', fontWeight: 600, color: '#f1f5f9', marginBottom: '1rem' }}>Experiment Results</h2>

          {runs.length === 0 ? (
            <div style={{ color: '#64748b', background: '#1e293b55', padding: '3rem', textAlign: 'center', borderRadius: '8px' }}>
              No evaluation runs completed yet. Click &quot;Run Experiment&quot; above to execute the benchmark scenario suite.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {runs.map(run => (
                <div key={run.id} style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: '12px', padding: '1.5rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                    <span style={{ color: '#f1f5f9', fontWeight: 700 }}>{run.name || run.id}</span>
                    <span style={{ color: '#4ade80', fontSize: '0.85rem', fontWeight: 600 }}>{run.status}</span>
                  </div>
                  <pre style={{ background: '#0f172a', padding: '1rem', borderRadius: '8px', color: '#60a5fa', fontSize: '0.85rem', overflowX: 'auto' }}>
                    {JSON.stringify(run.results, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
