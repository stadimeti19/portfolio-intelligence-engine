from __future__ import annotations


class MarketDataError(RuntimeError):
    """Base class for provider and cache failures safe for CLI display."""


class MissingAPIKeyError(MarketDataError):
    pass


class ProviderAuthenticationError(MarketDataError):
    pass


class RateLimitError(MarketDataError):
    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(MarketDataError):
    pass


class ProviderTimeoutError(MarketDataError):
    pass


class InvalidResponseError(MarketDataError):
    pass


class IncompleteHistoryError(MarketDataError):
    pass


class CacheCorruptionError(MarketDataError):
    pass


class UnsupportedSymbolError(MarketDataError):
    pass


def redact_secret(value: str, secrets: list[str | None]) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted
