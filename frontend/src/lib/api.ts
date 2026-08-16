/**
 * API client — thin wrapper around fetch with base URL + correlation IDs.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const correlationId = crypto.randomUUID();
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Correlation-ID': correlationId,
      ...(options?.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  health: {
    live: () => apiFetch<{ status: string; uptime_seconds: number; version: string }>('/health'),
    ready: () => apiFetch<{ status: string; database: string; llm_provider: string }>('/health/ready'),
  },
  analytics: {
    summary: () =>
      apiFetch<{
        total_requests: number;
        total_success: number;
        total_failures: number;
        success_rate: number | null;
        total_recovery_attempts: number;
        total_recovered: number;
        recovery_rate: number | null;
        llm_invocations: number;
        llm_escalation_rate: number | null;
      }>('/api/v1/analytics/summary'),
  },
  apis: {
    list: () => apiFetch<Api[]>('/api/v1/apis'),
    create: (payload: ApiCreate) =>
      apiFetch<Api>('/api/v1/apis', { method: 'POST', body: JSON.stringify(payload) }),
  },
  memory: {
    list: (params?: { maturity?: string; limit?: number }) => {
      const q = new URLSearchParams();
      if (params?.maturity) q.set('maturity', params.maturity);
      if (params?.limit) q.set('limit', String(params.limit));
      return apiFetch<RecoveryCase[]>(`/api/v1/recovery-memory?${q}`);
    },
  },
};

export interface Api {
  id: string;
  name: string;
  description: string | null;
  base_url: string;
  registered_host: string;
  is_active: boolean;
}

export interface ApiCreate {
  name: string;
  base_url: string;
  registered_host: string;
  description?: string;
}

export interface RecoveryCase {
  id: string;
  failure_signature: string;
  source: string;
  model_provider: string | null;
  maturity: string;
  confidence: number;
  success_count: number;
  failure_count: number;
  reuse_count: number;
  last_used_at: string | null;
  created_at: string;
}
