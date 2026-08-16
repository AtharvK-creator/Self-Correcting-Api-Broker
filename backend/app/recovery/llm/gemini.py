"""
Gemini provider implementation — FEAT-023.

Uses google-genai SDK (Interactions API).
Model: gemini-2.0-flash-exp (configurable).
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
)
from app.recovery.llm.templates import render_correction_template

logger = structlog.get_logger(__name__)

# Valid action types — LLM output is validated against this set
_VALID_ACTION_TYPES = frozenset(
    {
        "parameter_rename",
        "remove_optional_field",
        "retry_after",
        "schema_field_mapping",
        "add_missing_optional_field",
        "normalize_field_type",
    }
)


class GeminiProvider(BaseLLMProvider):
    """
    Google Gemini provider.

    Uses the google-genai SDK with structured output (JSON mode).
    Falls back to raw text parsing if JSON mode fails.
    """

    def __init__(self):
        self._client = None
        self._settings = get_settings()

    def _get_client(self):
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self._settings.gemini_api_key)
            except ImportError:
                raise RuntimeError(
                    "google-genai package not installed. "
                    "Add 'google-genai' to requirements.txt."
                )
        return self._client

    def get_provider_name(self) -> str:
        return "gemini"

    def get_model_version(self) -> str:
        return "gemini-2.0-flash-exp"

    async def generate_candidates(
        self,
        *,
        failure_context: dict[str, Any],
        api_schema: dict[str, Any] | None,
        graph_neighborhood: list[dict[str, Any]],
        correlation_id: uuid.UUID,
        max_candidates: int = 3,
    ) -> LLMInvocationResult:
        rendered = render_correction_template(
            method=failure_context.get("method", "GET"),
            endpoint_path=failure_context.get("endpoint_path", "/"),
            failure_class=failure_context.get("failure_class", "UNKNOWN"),
            http_status=failure_context.get("http_status"),
            schema_signature=failure_context.get("schema_signature", ""),
            error_summary=failure_context.get("error_summary", {}),
            request_schema=api_schema,
            graph_neighborhood=graph_neighborhood,
            max_candidates=max_candidates,
        )
        prompt = rendered.text

        start_ms = time.monotonic()
        try:
            client = self._get_client()
            response = await _call_gemini(
                client=client,
                prompt=prompt,
                model=self.get_model_version(),
                max_tokens=self._settings.llm_max_tokens,
            )
            latency_ms = (time.monotonic() - start_ms) * 1000
            candidates = _parse_candidates(response["text"], provider=self.get_provider_name(), model=self.get_model_version())
            logger.info(
                "llm_gemini_success",
                correlation_id=str(correlation_id),
                candidates=len(candidates),
                latency_ms=round(latency_ms, 1),
            )
            return LLMInvocationResult(
                candidates=candidates,
                prompt_tokens=response.get("prompt_tokens", 0),
                completion_tokens=response.get("completion_tokens", 0),
                latency_ms=latency_ms,
                was_successful=True,
                model_provider=self.get_provider_name(),
                model_version=self.get_model_version(),
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - start_ms) * 1000
            logger.error(
                "llm_gemini_error",
                correlation_id=str(correlation_id),
                error=str(exc),
                latency_ms=round(latency_ms, 1),
            )
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


async def _call_gemini(
    client: Any,
    prompt: str,
    model: str,
    max_tokens: int,
) -> dict[str, Any]:
    """Make the Gemini API call using the Interactions API."""
    from google.genai import types

    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=max_tokens,
        ),
    )
    text = response.text or ""
    usage = response.usage_metadata
    return {
        "text": text,
        "prompt_tokens": getattr(usage, "prompt_token_count", 0) if usage else 0,
        "completion_tokens": getattr(usage, "candidates_token_count", 0) if usage else 0,
    }


def _parse_candidates(text: str, provider: str, model: str) -> list[LLMCandidate]:
    """Parse JSON response into validated LLMCandidate list."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("llm_parse_error", text_preview=text[:200])
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
            logger.warning("llm_invalid_action_type", action_type=action_type)
            continue
        confidence = float(raw.get("confidence", 0.5))
        confidence = max(0.0, min(confidence, 1.0))
        results.append(LLMCandidate(
            action_type=action_type,
            changes=raw.get("changes", []),
            reason=str(raw.get("reason", "")),
            confidence=confidence,
            model_provider=provider,
            model_version=model,
            raw_response=raw,
        ))
    return results
