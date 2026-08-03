from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Protocol

from portfolio_intelligence.domain.prices import Dividend, PriceBar, Quote, StockSplit
from portfolio_intelligence.providers.market_data.errors import (
    InvalidResponseError,
    MissingAPIKeyError,
    ProviderAuthenticationError,
    RateLimitError,
    UnsupportedSymbolError,
    redact_secret,
)
from portfolio_intelligence.providers.market_data.http import HttpResponse, JsonHttpClient
from portfolio_intelligence.providers.market_data.validation import (
    normalize_dividends,
    normalize_price_bars,
    normalize_splits,
)

BASE_URL = "https://www.alphavantage.co/query"
_UTC = timezone.utc  # noqa: UP017 - keep local test environments on Python 3.10 working.


class AlphaVantageHttpClient(Protocol):
    def get_json(self, url: str, params: dict[str, str]) -> HttpResponse: ...


class AlphaVantageProvider:
    name = "alphavantage"

    def __init__(
        self,
        api_key: str | None,
        *,
        timeout_seconds: int = 15,
        max_retries: int = 3,
        http_client: AlphaVantageHttpClient | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("ALPHA_VANTAGE_API_KEY is required for Alpha Vantage")
        self.api_key = api_key
        self.http_client = http_client or JsonHttpClient(
            timeout_seconds=timeout_seconds, max_retries=max_retries
        )

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        payload = self._daily_adjusted(symbol)
        series = _series(payload)
        metadata = _metadata(payload)
        response_symbol = str(metadata.get("2. Symbol", symbol)).upper()
        if response_symbol != symbol.upper():
            raise InvalidResponseError("Alpha Vantage returned a different symbol")
        retrieval_timestamp = datetime.now(_UTC)
        bars = [
            PriceBar(
                symbol=symbol.upper(),
                trading_date=date.fromisoformat(day),
                open=_float(value, "1. open"),
                high=_float(value, "2. high"),
                low=_float(value, "3. low"),
                close=_float(value, "4. close"),
                adjusted_close=_float(value, "5. adjusted close"),
                volume=_int(value.get("6. volume", 0)),
                data_source=self.name,
                retrieval_timestamp=retrieval_timestamp,
            )
            for day, value in series.items()
            if isinstance(value, dict)
        ]
        return normalize_price_bars(symbol, bars, start=start, end=end)

    def get_latest_quote(self, symbol: str) -> Quote:
        payload = self._get(
            {
                "function": "GLOBAL_QUOTE",
                "symbol": symbol.upper(),
                "apikey": self.api_key,
            }
        )
        self._raise_for_vendor_error(payload)
        quote = payload.get("Global Quote")
        if not isinstance(quote, dict) or not quote:
            raise InvalidResponseError("Alpha Vantage response is missing quote")
        response_symbol = str(quote.get("01. symbol", "")).upper()
        if response_symbol != symbol.upper():
            raise InvalidResponseError("Alpha Vantage returned a different quote symbol")
        return Quote(
            symbol=symbol.upper(),
            price=_float(quote, "05. price"),
            as_of=date.fromisoformat(str(quote["07. latest trading day"])),
            source=self.name,
            retrieval_timestamp=datetime.now(_UTC),
        )

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Dividend]:
        payload = self._daily_adjusted(symbol)
        series = _series(payload)
        retrieval_timestamp = datetime.now(_UTC)
        dividends = [
            Dividend(
                symbol=symbol.upper(),
                ex_date=date.fromisoformat(day),
                amount=_float(value, "7. dividend amount"),
                data_source=self.name,
                retrieval_timestamp=retrieval_timestamp,
            )
            for day, value in series.items()
            if isinstance(value, dict) and _safe_float(value.get("7. dividend amount")) > 0
        ]
        return normalize_dividends(symbol, dividends, start=start, end=end)

    def get_splits(self, symbol: str, start: date, end: date) -> list[StockSplit]:
        payload = self._daily_adjusted(symbol)
        series = _series(payload)
        retrieval_timestamp = datetime.now(_UTC)
        splits = []
        for day, value in series.items():
            if not isinstance(value, dict):
                continue
            coefficient = _safe_float(value.get("8. split coefficient"))
            if coefficient and coefficient != 1.0:
                splits.append(
                    StockSplit(
                        symbol=symbol.upper(),
                        split_date=date.fromisoformat(day),
                        from_factor=1.0,
                        to_factor=coefficient,
                        data_source=self.name,
                        retrieval_timestamp=retrieval_timestamp,
                    )
                )
        return normalize_splits(symbol, splits, start=start, end=end)

    def _daily_adjusted(self, symbol: str) -> dict[str, Any]:
        payload = self._get(
            {
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": symbol.upper(),
                "outputsize": "full",
                "apikey": self.api_key,
            }
        )
        self._raise_for_vendor_error(payload)
        return payload

    def _get(self, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self.http_client.get_json(BASE_URL, params)
        except Exception as exc:
            message = redact_secret(str(exc), [self.api_key])
            if message != str(exc):
                raise type(exc)(message) from exc
            raise
        if not isinstance(response.payload, dict):
            raise InvalidResponseError("Alpha Vantage returned a non-object JSON response")
        return response.payload

    def _raise_for_vendor_error(self, payload: dict[str, Any]) -> None:
        if "Error Message" in payload:
            message = str(payload["Error Message"])
            if "invalid api call" in message.lower():
                raise UnsupportedSymbolError("Alpha Vantage does not support the requested symbol")
            raise InvalidResponseError(redact_secret(message, [self.api_key]))
        if "Information" in payload:
            message = str(payload["Information"])
            lowered = message.lower()
            if "rate" in lowered or "frequency" in lowered or "limit" in lowered:
                raise RateLimitError("Alpha Vantage rate limit reached")
            raise InvalidResponseError(redact_secret(message, [self.api_key]))
        if "Note" in payload:
            raise RateLimitError("Alpha Vantage rate limit reached")
        if "Invalid API call" in payload:
            raise UnsupportedSymbolError("Alpha Vantage does not support the requested symbol")
        if "premium" in str(payload).lower():
            raise ProviderAuthenticationError("Alpha Vantage entitlement does not allow this data")


def _metadata(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("Meta Data")
    if not isinstance(value, dict):
        raise InvalidResponseError("Alpha Vantage response is missing metadata")
    return value


def _series(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("Time Series (Daily)")
    if not isinstance(value, dict) or not value:
        raise InvalidResponseError("Alpha Vantage response is missing daily time series")
    return value


def _float(value: dict[str, Any], key: str) -> float:
    try:
        return float(value[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidResponseError(f"provider response is missing {key}") from exc


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError) as exc:
        raise InvalidResponseError("provider response has invalid volume") from exc
