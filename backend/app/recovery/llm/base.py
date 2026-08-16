"""
LLM provider abstraction — FEAT-020.

Abstract base class and factory for LLM providers.
LLM is a candidate generator only — it CANNOT execute requests.
All LLM output is treated as untrusted until safety-validated.

TAD §10, BACKEND_SPEC §8, FINAL_DECISIONS #4.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class LLMCandidate:
    """
    A correction candidate produced by an LLM provider.

    Treated as untrusted input until safety-validated.
    Source is always LLM (never DETERMINISTIC).
    """
    action_type: str
    changes: list[dict[str, Any]]
    reason: str
    confidence: float
    provenance: str = "LLM"
    model_provider: str = ""
    model_version: str = ""
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMInvocationResult:
    """Result of one LLM invocation."""
    candidates: list[LLMCandidate]
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    was_successful: bool
    error: str | None = None
    model_provider: str = ""
    model_version: str = ""


class BaseLLMProvider(ABC):
    """
    Abstract LLM provider interface.

    All providers must implement generate_candidates.
    The LLM is a candidate generator — it cannot execute requests,
    modify state, or make upstream calls.
    """

    @abstractmethod
    async def generate_candidates(
        self,
        *,
        failure_context: dict[str, Any],
        api_schema: dict[str, Any] | None,
        graph_neighborhood: list[dict[str, Any]],
        correlation_id: uuid.UUID,
        max_candidates: int = 3,
    ) -> LLMInvocationResult:
        """
        Generate correction candidates for a failure context.

        The prompt must not include secret values (enforced by normalization layer).
        Returns an LLMInvocationResult with candidates and usage metadata.
        """
        ...

    @abstractmethod
    def get_provider_name(self) -> str:
        ...

    @abstractmethod
    def get_model_version(self) -> str:
        ...


def build_correction_prompt(
    failure_context: dict[str, Any],
    api_schema: dict[str, Any] | None,
    graph_neighborhood: list[dict[str, Any]],
    max_candidates: int = 3,
) -> str:
    """
    Build a structured prompt for the LLM correction generator.

    The prompt is designed to elicit structured JSON output containing
    correction candidates. Secret values are never included.
    """
    schema_section = ""
    if api_schema:
        schema_section = f"""
## Known API Schema
```json
{_safe_json_dump(api_schema)}
```
"""

    neighborhood_section = ""
    if graph_neighborhood:
        neighborhood_section = f"""
## Similar Historical Cases (from contextual graph)
{_safe_json_dump(graph_neighborhood[:5])}
"""

    return f"""You are an API correction specialist. A request to an external API has failed.
Your task is to suggest up to {max_candidates} correction candidates to fix the failure.

## Failure Context
- Endpoint: {failure_context.get('method', 'GET')} {failure_context.get('endpoint_path', '/')}
- Failure class: {failure_context.get('failure_class', 'UNKNOWN')}
- HTTP status: {failure_context.get('http_status', 'N/A')}
- Schema signature: {failure_context.get('schema_signature', 'N/A')}
- Error summary: {_safe_json_dump(failure_context.get('error_summary', {{}}))}
{schema_section}{neighborhood_section}

## Instructions
Return a JSON object with this exact structure:
{{
  "candidates": [
    {{
      "action_type": "parameter_rename",
      "changes": [{{"field": "customerId", "rename_to": "customer_id", "location": "body"}}],
      "reason": "The API expects snake_case field names",
      "confidence": 0.85
    }}
  ]
}}

## Constraints
- Do NOT suggest: host changes, credential changes, TLS disabling, scope expansion
- Only suggest structural changes to request parameters, headers, or body
- Do NOT include secret values in any field
- action_type must be one of: parameter_rename, remove_optional_field, retry_after,
  schema_field_mapping, add_missing_optional_field, normalize_field_type
- confidence must be a float between 0.0 and 1.0
- Respond with ONLY the JSON object, no explanation text
"""


def _safe_json_dump(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, indent=2, default=str)
    except Exception:
        return str(obj)
