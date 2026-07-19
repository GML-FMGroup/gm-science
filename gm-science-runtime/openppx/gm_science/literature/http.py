"""Safe HTTP boundary shared by literature connectors."""

from __future__ import annotations

from typing import Any, Mapping

import httpx

from ..infrastructure import network_policy_from_env


USER_AGENT = "gm-science/0.1 (+local research agent)"


class LiteratureConnectorError(RuntimeError):
    """A stable, credential-safe literature connector failure."""

    def __init__(
        self,
        source: str,
        kind: str,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message)
        self.source = source
        self.kind = kind
        self.status_code = status_code
        self.retry_after = retry_after


def safe_get(
    client: httpx.Client,
    url: str,
    *,
    source: str,
    params: Mapping[str, Any],
    timeout_seconds: float,
) -> httpx.Response:
    """Issue a GET request and convert transport failures to stable errors."""

    decision = network_policy_from_env().evaluate_url(url, purpose=f"{source} request")
    if not decision.allowed:
        raise LiteratureConnectorError(source, "network_blocked", decision.reason)

    try:
        response = client.get(
            url,
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml, application/xml"},
            timeout=timeout_seconds,
        )
    except httpx.TimeoutException as exc:
        raise LiteratureConnectorError(source, "timeout", f"{source} request timed out.") from exc
    except httpx.HTTPError as exc:
        raise LiteratureConnectorError(source, "network_error", f"{source} request failed.") from exc

    if response.status_code == 429:
        raise LiteratureConnectorError(
            source,
            "rate_limited",
            f"{source} rate limit reached.",
            status_code=429,
            retry_after=response.headers.get("Retry-After"),
        )
    if response.status_code >= 400:
        raise LiteratureConnectorError(
            source,
            "http_error",
            f"{source} returned HTTP {response.status_code}.",
            status_code=response.status_code,
        )
    return response


def require_source(config_name: str, *, enabled: bool, api_base: str) -> None:
    """Reject disabled or incomplete connectors before making a request."""

    if not enabled:
        raise LiteratureConnectorError(config_name, "disabled", f"{config_name} is disabled.")
    if not api_base:
        raise LiteratureConnectorError(
            config_name,
            "needs_configuration",
            f"Set science.literature.{config_name}.apiBase.",
        )
