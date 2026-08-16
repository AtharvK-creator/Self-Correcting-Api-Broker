"""
Prompt template library — FEAT-021, FEAT-022.

Versioned, parameterized prompt templates for:
- Failure correction (FEAT-021): primary LLM prompt
- Schema analysis (FEAT-022): API schema understanding
- Candidate evaluation (FEAT-022): validate LLM output against evidence

Templates are string-format based (no external deps).
All templates enforce the constraint that secrets must not appear.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


# Template version — increment on any prompt change (tracked for evaluation)
CORRECTION_TEMPLATE_VERSION = "v1.0"
SCHEMA_ANALYSIS_TEMPLATE_VERSION = "v1.0"
CANDIDATE_EVAL_TEMPLATE_VERSION = "v1.0"

# Valid action types — embedded in every template as a hard constraint
VALID_ACTION_TYPES = [
    "parameter_rename",
    "remove_optional_field",
    "retry_after",
    "schema_field_mapping",
    "add_missing_optional_field",
    "normalize_field_type",
]

# ── Template 1: Failure Correction ────────────────────────────────────────────

_CORRECTION_TEMPLATE = """\
You are an API correction specialist. Your role is to suggest structural corrections to a failed API request.

## Failure Details
- Endpoint: {method} {endpoint_path}
- Failure class: {failure_class}
- HTTP status: {http_status}
- Schema signature: {schema_signature}
- Error summary: {error_summary_json}

## Request Schema (sent fields)
{schema_section}

## Similar Historical Cases
{neighborhood_section}

## Your Task
Suggest up to {max_candidates} correction candidates that could fix this failure.

## Output Format
Return ONLY a JSON object with this exact structure — no other text:
{{
  "candidates": [
    {{
      "action_type": "parameter_rename",
      "changes": [{{"field": "customerId", "rename_to": "customer_id", "location": "body"}}],
      "reason": "The API expects snake_case field names based on error message",
      "confidence": 0.85
    }}
  ],
  "template_version": "{template_version}"
}}

## Hard Constraints (NEVER violate these)
- Do NOT suggest host changes, URL changes, or destination changes
- Do NOT suggest disabling TLS or bypassing security checks
- Do NOT include credential values, tokens, passwords, or API keys in any field
- Do NOT suggest expanding authorization scopes
- action_type MUST be one of: {valid_action_types}
- confidence MUST be a float between 0.0 and 1.0
- If you cannot suggest a safe correction, return {{"candidates": []}}
"""

# ── Template 2: Schema Analysis ───────────────────────────────────────────────

_SCHEMA_ANALYSIS_TEMPLATE = """\
You are an API schema specialist. Analyze the given API schema and extract field mapping information.

## API Schema
{schema_json}

## Task
Extract the following information:
1. Required fields and their types
2. Optional fields and their types
3. Common field name variations (camelCase vs snake_case)
4. Deprecated or renamed fields

## Output Format
Return ONLY a JSON object:
{{
  "required_fields": [{{"name": "customer_id", "type": "string", "aliases": ["customerId", "cust_id"]}}],
  "optional_fields": [{{"name": "page", "type": "integer", "default": 1}}],
  "deprecated_fields": [{{"old_name": "user_uid", "new_name": "user_id"}}],
  "template_version": "{template_version}"
}}
"""

# ── Template 3: Candidate Evaluation ─────────────────────────────────────────

_CANDIDATE_EVAL_TEMPLATE = """\
You are a correction quality evaluator. Given a proposed API correction and historical evidence,
assess whether the correction is likely to succeed.

## Proposed Correction
- Action type: {action_type}
- Changes: {changes_json}
- Reason given: {reason}

## Historical Evidence
- Similar cases found: {similar_count}
- Average success rate of similar corrections: {historical_success_rate:.1%}
- Failure class: {failure_class}

## Task
Assess the correction quality. Consider:
1. Is the action type appropriate for this failure class?
2. Are the changes safe and structural (not credential or host changes)?
3. Does the historical evidence support this correction?

## Output Format
Return ONLY a JSON object:
{{
  "quality_score": 0.85,
  "safe": true,
  "assessment": "High confidence: field rename matches known API convention",
  "concerns": [],
  "template_version": "{template_version}"
}}
"""


@dataclass
class RenderedTemplate:
    """A rendered prompt template with metadata."""
    text: str
    template_version: str
    template_type: str
    char_count: int


def render_correction_template(
    *,
    method: str,
    endpoint_path: str,
    failure_class: str,
    http_status: int | None,
    schema_signature: str,
    error_summary: dict[str, Any],
    request_schema: dict[str, Any] | None = None,
    graph_neighborhood: list[dict[str, Any]] | None = None,
    max_candidates: int = 3,
) -> RenderedTemplate:
    """
    Render the failure correction prompt.

    Validates that no secret values are present in error_summary.
    """
    _assert_no_secrets(error_summary, context="error_summary")
    if request_schema:
        _assert_no_secrets(request_schema, context="request_schema")

    schema_section = (
        f"```json\n{_safe_json(request_schema)}\n```"
        if request_schema
        else "(No schema available)"
    )

    neighborhood_section = (
        _safe_json(graph_neighborhood[:5])
        if graph_neighborhood
        else "(No historical cases available)"
    )

    text = _CORRECTION_TEMPLATE.format(
        method=method.upper(),
        endpoint_path=endpoint_path,
        failure_class=failure_class,
        http_status=str(http_status) if http_status is not None else "N/A",
        schema_signature=schema_signature,
        error_summary_json=_safe_json(error_summary),
        schema_section=schema_section,
        neighborhood_section=neighborhood_section,
        max_candidates=max_candidates,
        template_version=CORRECTION_TEMPLATE_VERSION,
        valid_action_types=", ".join(VALID_ACTION_TYPES),
    )
    return RenderedTemplate(
        text=text,
        template_version=CORRECTION_TEMPLATE_VERSION,
        template_type="correction",
        char_count=len(text),
    )


def render_schema_analysis_template(
    *,
    api_schema: dict[str, Any],
) -> RenderedTemplate:
    """Render the schema analysis prompt."""
    _assert_no_secrets(api_schema, context="api_schema")
    text = _SCHEMA_ANALYSIS_TEMPLATE.format(
        schema_json=_safe_json(api_schema),
        template_version=SCHEMA_ANALYSIS_TEMPLATE_VERSION,
    )
    return RenderedTemplate(
        text=text,
        template_version=SCHEMA_ANALYSIS_TEMPLATE_VERSION,
        template_type="schema_analysis",
        char_count=len(text),
    )


def render_candidate_eval_template(
    *,
    action_type: str,
    changes: list[dict],
    reason: str,
    similar_count: int,
    historical_success_rate: float,
    failure_class: str,
) -> RenderedTemplate:
    """Render the candidate evaluation prompt."""
    text = _CANDIDATE_EVAL_TEMPLATE.format(
        action_type=action_type,
        changes_json=_safe_json(changes),
        reason=reason,
        similar_count=similar_count,
        historical_success_rate=historical_success_rate,
        failure_class=failure_class,
        template_version=CANDIDATE_EVAL_TEMPLATE_VERSION,
    )
    return RenderedTemplate(
        text=text,
        template_version=CANDIDATE_EVAL_TEMPLATE_VERSION,
        template_type="candidate_eval",
        char_count=len(text),
    )


# ── Secret detection ──────────────────────────────────────────────────────────

_SECRET_KEYWORDS = frozenset({
    "password", "api_key", "apikey", "secret", "token", "credential",
    "authorization", "auth", "bearer", "private_key", "access_key",
})


def _assert_no_secrets(data: dict | list | Any, context: str = "") -> None:
    """
    Assert that no known secret keys appear in a data structure.

    Raises ValueError if secrets are detected.
    This is a defence-in-depth check — the normalizer should already
    have redacted secrets before they reach this layer.
    """
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, str) and k.lower().replace("-", "_") in _SECRET_KEYWORDS:
                raise ValueError(
                    f"Secret key '{k}' detected in {context}. "
                    "Secrets must be redacted before reaching the prompt layer."
                )
            _assert_no_secrets(v, context=f"{context}.{k}")
    elif isinstance(data, list):
        for item in data:
            _assert_no_secrets(item, context=context)


def _safe_json(obj: Any, indent: int = 2) -> str:
    try:
        return json.dumps(obj, indent=indent, default=str)
    except Exception:
        return str(obj)
