from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from portfolio_intelligence.providers.market_data.errors import (
    ProviderAuthenticationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
)


@dataclass(frozen=True)
class HttpResponse:
    status_code: int
    headers: dict[str, str]
    payload: dict[str, Any] | list[Any]


class JsonHttpClient:
    def __init__(self, *, timeout_seconds: int, max_retries: int) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def get_json(self, url: str, params: dict[str, str]) -> HttpResponse:
        query = urlencode(params)
        request_url = f"{url}?{query}" if query else url
        attempt = 0
        while True:
            try:
                request = Request(request_url, headers={"Accept": "application/json"})
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                    payload = json.loads(raw) if raw else {}
                    headers = {key.lower(): value for key, value in response.headers.items()}
                    return HttpResponse(response.status, headers, payload)
            except HTTPError as exc:
                headers = {key.lower(): value for key, value in exc.headers.items()}
                if exc.code == 429:
                    raise RateLimitError(
                        "provider rate limit reached",
                        retry_after_seconds=_retry_after(headers),
                    ) from exc
                if exc.code in {401, 403}:
                    raise ProviderAuthenticationError("provider authentication failed") from exc
                if 500 <= exc.code < 600 and attempt < self.max_retries:
                    _sleep(attempt)
                    attempt += 1
                    continue
                raise ProviderUnavailableError(f"provider returned HTTP {exc.code}") from exc
            except TimeoutError as exc:
                if attempt < self.max_retries:
                    _sleep(attempt)
                    attempt += 1
                    continue
                raise ProviderTimeoutError("provider request timed out") from exc
            except URLError as exc:
                reason = getattr(exc, "reason", exc)
                if isinstance(reason, TimeoutError):
                    error: Exception = ProviderTimeoutError("provider request timed out")
                else:
                    error = ProviderUnavailableError("provider is unavailable")
                if attempt < self.max_retries:
                    _sleep(attempt)
                    attempt += 1
                    continue
                raise error from exc
            except json.JSONDecodeError as exc:
                raise ProviderUnavailableError("provider returned non-JSON response") from exc


def _retry_after(headers: dict[str, str]) -> int | None:
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _sleep(attempt: int) -> None:
    time.sleep(min(2.0, 0.25 * (2**attempt)))
