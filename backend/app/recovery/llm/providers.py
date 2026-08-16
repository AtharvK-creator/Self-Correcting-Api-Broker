"""
Groq provider — FEAT-024.
Mock provider for testing.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import structlog

from app.config import get_settings
from app.recovery.llm.base import (
    BaseLLMProvider,
    LLMCandidate,
    LLMInvocationResult,
    build_correction_prompt,
)

logger = structlog.get_logger(__name__)

_VALID_ACTION_TYPES = frozenset({
    "parameter_rename", "remove_optional_field", "retry_after",
    "schema_field_mapping", "add_missing_optional_field", "normalize_field_type",
})


class GroqProvider(BaseLLMProvider):
    """Groq (llama-3.3-70b-versatile) provider."""

    def __init__(self):
        self._client = None
        self._settings = get_settings()

    def _get_client(self):
        if self._client is None:
            try:
                from groq import AsyncGroq
                self._client = AsyncGroq(api_key=self._settings.groq_api_key)
            except ImportError:
                raise RuntimeError("groq package not installed. Add 'groq' to requirements.txt.")
        return self._client

    def get_provider_name(self) -> str:
        return "groq"

    def get_model_version(self) -> str:
        return "llama-3.3-70b-versatile"

    async def generate_candidates(
        self,
        *,
        failure_context: dict[str, Any],
        api_schema: dict[str, Any] | None,
        graph_neighborhood: list[dict[str, Any]],
        correlation_id: uuid.UUID,
        max_candidates: int = 3,
    ) -> LLMInvocationResult:
        prompt = build_correction_prompt(
            failure_context=failure_context,
            api_schema=api_schema,
            graph_neighborhood=graph_neighborhood,
            max_candidates=max_candidates,
        )
        start_ms = time.monotonic()
        try:
            client = self._get_client()
            chat_completion = await client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are an API correction specialist. Always respond with valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                model=self.get_model_version(),
                max_tokens=self._settings.llm_max_tokens,
                response_format={"type": "json_object"},
            )
            latency_ms = (time.monotonic() - start_ms) * 1000
            text = chat_completion.choices[0].message.content or ""
            candidates = _parse_groq_candidates(text, model=self.get_model_version())
            usage = chat_completion.usage
            return LLMInvocationResult(
                candidates=candidates,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
                was_successful=True,
                model_provider=self.get_provider_name(),
                model_version=self.get_model_version(),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start_ms) * 1000
            logger.error("llm_groq_error", correlation_id=str(correlation_id), error=str(exc))
            return LLMInvocationResult(
                candidates=[],
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                was_successful=False,
                error=str(exc),
                model_provider=self.get_provider_name(),
                model_version=self.get_model_version(),
            )


def _parse_groq_candidates(text: str, model: str) -> list[LLMCandidate]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    raw_candidates = data.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return []
    results = []
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        action_type = str(raw.get("action_type", "")).strip()
        if action_type not in _VALID_ACTION_TYPES:
            continue
        confidence = max(0.0, min(float(raw.get("confidence", 0.5)), 1.0))
        results.append(LLMCandidate(
            action_type=action_type,
            changes=raw.get("changes", []),
            reason=str(raw.get("reason", "")),
            confidence=confidence,
            model_provider="groq",
            model_version=model,
            raw_response=raw,
        ))
    return results


class MockLLMProvider(BaseLLMProvider):
    """
    Mock provider for testing and development.
    Returns deterministic candidates without LLM calls.
    """

    def get_provider_name(self) -> str:
        return "mock"

    def get_model_version(self) -> str:
        return "mock-v1"

    async def generate_candidates(
        self,
        *,
        failure_context: dict[str, Any],
        api_schema: dict[str, Any] | None,
        graph_neighborhood: list[dict[str, Any]],
        correlation_id: uuid.UUID,
        max_candidates: int = 3,
    ) -> LLMInvocationResult:
        failure_class = failure_context.get("failure_class", "UNKNOWN")
        candidates = []

        if failure_class == "UNKNOWN_PARAMETER":
            candidates.append(LLMCandidate(
                action_type="parameter_rename",
                changes=[{"field": "customerId", "rename_to": "customer_id", "location": "body"}],
                reason="Mock: likely camelCase→snake_case mismatch",
                confidence=0.70,
                model_provider="mock",
                model_version="mock-v1",
            ))
        elif failure_class in ("RATE_LIMIT", "UPSTREAM_5XX", "CONNECTION_FAILURE"):
            candidates.append(LLMCandidate(
                action_type="retry_after",
                changes=[{"action": "wait_and_retry", "retry_after_seconds": 1}],
                reason="Mock: transient error; retry",
                confidence=0.65,
                model_provider="mock",
                model_version="mock-v1",
            ))

        return LLMInvocationResult(
            candidates=candidates,
            prompt_tokens=100,
            completion_tokens=50,
            latency_ms=5.0,
            was_successful=True,
            model_provider="mock",
            model_version="mock-v1",
        )


def get_llm_provider(provider_name: str | None = None) -> BaseLLMProvider:
    """Factory function — returns the configured LLM provider."""
    from app.config import get_settings
    settings = get_settings()
    name = provider_name or settings.llm_provider

    if name == "gemini":
        return GeminiProvider()
    elif name == "groq":
        return GroqProvider()
    elif name == "mock":
        return MockLLMProvider()
    else:
        logger.warning("unknown_llm_provider", provider=name, fallback="mock")
        return MockLLMProvider()
