"""
Upstream execution engine — FEAT-005.

HTTPX-based execution with:
- timeout,
- redirect controls (max redirects, host re-validation),
- SSRF protections (SECURITY_ACCESS §6),
- TLS verification always enabled,
- telemetry (correlation ID, latency).

FR-003: Execute upstream request.
NFR-001: Successful requests bypass recovery pipeline.
"""

from __future__ import annotations

import ipaddress
import socket
import time
import uuid
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

# Private/reserved IP ranges that are blocked by default (SSRF protection)
_BLOCKED_IP_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 ULA
    ipaddress.ip_network("169.254.0.0/16"),    # link-local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space
    ipaddress.ip_network("198.18.0.0/15"),     # benchmarking
    ipaddress.ip_network("240.0.0.0/4"),       # reserved
]


class SSRFError(Exception):
    """Raised when a destination URL fails SSRF validation."""


class UpstreamExecutionError(Exception):
    """Raised when the upstream request fails with a transport-level error."""

    def __init__(self, message: str, original: Exception | None = None):
        super().__init__(message)
        self.original = original


class UpstreamResponse:
    """Normalized upstream response."""

    def __init__(
        self,
        *,
        status_code: int,
        headers: dict[str, str],
        body: Any,
        latency_ms: float,
        is_success: bool,
        correlation_id: uuid.UUID,
    ):
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.latency_ms = latency_ms
        self.is_success = is_success
        self.correlation_id = correlation_id


def _validate_host_ssrf(url: str, registered_host: str | None = None) -> None:
    """
    Validate that the target URL is not a private/loopback/SSRF-risky address.

    1. If registered_host is provided, the URL hostname must match it exactly.
    2. Resolve the hostname and reject private/reserved IP ranges.

    Raises SSRFError on any violation.
    """
    settings = get_settings()
    parsed = urlparse(url)
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError(f"Cannot determine hostname from URL: {url!r}")

    # Rule 1: If a registered host is known, enforce exact match
    if registered_host and hostname.lower() != registered_host.lower():
        raise SSRFError(
            f"Hostname {hostname!r} does not match registered host {registered_host!r}"
        )

    # Rule 2: If allowed_hosts list is configured, enforce it
    allowed = settings.allowed_upstream_hosts
    if allowed and hostname.lower() not in [h.lower() for h in allowed]:
        raise SSRFError(
            f"Hostname {hostname!r} is not in the allowed upstream hosts list"
        )

    # Rule 3: Resolve and block private ranges
    try:
        resolved_ips = {r[4][0] for r in socket.getaddrinfo(hostname, None)}
    except socket.gaierror as exc:
        raise SSRFError(f"Cannot resolve hostname {hostname!r}: {exc}") from exc

    for ip_str in resolved_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        for blocked in _BLOCKED_IP_RANGES:
            if ip in blocked:
                raise SSRFError(
                    f"Hostname {hostname!r} resolves to private/reserved address {ip_str}"
                )


async def execute_upstream(
    *,
    url: str,
    method: str,
    headers: dict[str, str],
    query_params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    correlation_id: uuid.UUID,
    registered_host: str | None = None,
    skip_ssrf_check: bool = False,
) -> UpstreamResponse:
    """
    Execute an HTTP request to the upstream API.

    Security:
    - TLS verification is always enabled (SECURITY_ACCESS §6).
    - SSRF validation is performed before any network call.
    - Redirects are limited and redirect destinations are re-validated.
    - Secrets must be stripped from headers before calling this function
      (normalization is caller's responsibility).

    Returns an UpstreamResponse.
    Raises SSRFError if the destination fails SSRF validation.
    Raises UpstreamExecutionError on transport-level failure.
    """
    settings = get_settings()

    if not skip_ssrf_check:
        _validate_host_ssrf(url, registered_host=registered_host)

    request_headers = {
        "X-Correlation-ID": str(correlation_id),
        **headers,
    }

    start_ms = time.monotonic()

    try:
        async with httpx.AsyncClient(
            verify=settings.upstream_verify_tls,
            timeout=settings.upstream_timeout_seconds,
            follow_redirects=False,  # we handle redirects manually for SSRF re-validation
        ) as client:
            response = await _execute_with_redirect_policy(
                client=client,
                method=method.upper(),
                url=url,
                headers=request_headers,
                params=query_params,
                json=body,
                max_redirects=settings.upstream_max_redirects,
                registered_host=registered_host,
                correlation_id=correlation_id,
            )
    except SSRFError:
        raise
    except httpx.TimeoutException as exc:
        latency_ms = (time.monotonic() - start_ms) * 1000
        logger.warning(
            "upstream_timeout",
            url=url,
            correlation_id=str(correlation_id),
            latency_ms=round(latency_ms, 1),
        )
        raise UpstreamExecutionError("Upstream request timed out", original=exc) from exc
    except httpx.RequestError as exc:
        latency_ms = (time.monotonic() - start_ms) * 1000
        logger.warning(
            "upstream_connection_error",
            url=url,
            correlation_id=str(correlation_id),
            error=str(exc),
        )
        raise UpstreamExecutionError(f"Upstream connection error: {exc}", original=exc) from exc

    latency_ms = (time.monotonic() - start_ms) * 1000

    try:
        body_json = response.json()
    except Exception:
        body_json = response.text

    is_success = response.status_code < 400

    logger.info(
        "upstream_response",
        url=url,
        status=response.status_code,
        latency_ms=round(latency_ms, 1),
        is_success=is_success,
        correlation_id=str(correlation_id),
    )

    return UpstreamResponse(
        status_code=response.status_code,
        headers=dict(response.headers),
        body=body_json,
        latency_ms=latency_ms,
        is_success=is_success,
        correlation_id=correlation_id,
    )


async def _execute_with_redirect_policy(
    *,
    client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict[str, str],
    params: dict | None,
    json: dict | None,
    max_redirects: int,
    registered_host: str | None,
    correlation_id: uuid.UUID,
) -> httpx.Response:
    """
    Execute with manual redirect handling.

    Each redirect destination is SSRF-validated before following.
    Maximum redirects enforced.
    """
    current_url = url
    remaining_redirects = max_redirects

    while True:
        response = await client.request(
            method=method,
            url=current_url,
            headers=headers,
            params=params,
            json=json,
        )
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        if remaining_redirects <= 0:
            logger.warning(
                "upstream_max_redirects_exceeded",
                url=current_url,
                correlation_id=str(correlation_id),
            )
            return response

        redirect_url = response.headers.get("Location")
        if not redirect_url:
            return response

        # SSRF re-validate the redirect target
        _validate_host_ssrf(redirect_url, registered_host=registered_host)

        current_url = redirect_url
        remaining_redirects -= 1

        # POST → GET on 303 (standard behavior)
        if response.status_code == 303:
            method = "GET"
            json = None
            params = None
