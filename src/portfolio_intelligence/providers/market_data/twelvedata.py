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

BASE_URL = "https://api.twelvedata.com"
_UTC = timezone.utc  # noqa: UP017 - keep local test environments on Python 3.10 working.


class TwelveDataHttpClient(Protocol):
    def get_json(self, url: str, params: dict[str, str]) -> HttpResponse: ...


class TwelveDataProvider:
    name = "twelvedata"

    def __init__(
        self,
        api_key: str | None,
        *,
        timeout_seconds: int = 15,
        max_retries: int = 3,
        http_client: TwelveDataHttpClient | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("TWELVE_DATA_API_KEY is required for Twelve Data")
        self.api_key = api_key
        self.http_client = http_client or JsonHttpClient(
            timeout_seconds=timeout_seconds, max_retries=max_retries
        )

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        payload = self._get(
            "/time_series",
            {
                "symbol": symbol.upper(),
                "interval": "1day",
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "adjust": "all",
                "order": "ASC",
                "apikey": self.api_key,
            },
        )
        self._raise_for_vendor_error(payload)
        meta = _dict(payload.get("meta"))
        if meta.get("symbol", "").upper() != symbol.upper():
            raise InvalidResponseError("Twelve Data returned a different symbol")
        values = payload.get("values")
        if not isinstance(values, list):
            raise InvalidResponseError("Twelve Data response is missing price values")
        retrieval_timestamp = datetime.now(_UTC)
        bars = [
            PriceBar(
                symbol=symbol.upper(),
                trading_date=_parse_date(value.get("datetime")),
                open=_float(value, "open"),
                high=_float(value, "high"),
                low=_float(value, "low"),
                close=_float(value, "close"),
                adjusted_close=_float(value, "close"),
                volume=_int(value.get("volume", 0)),
                data_source=self.name,
                currency=_optional_str(meta.get("currency")),
                exchange=_optional_str(meta.get("exchange")),
                retrieval_timestamp=retrieval_timestamp,
            )
            for value in values
            if isinstance(value, dict)
        ]
        return normalize_price_bars(symbol, bars, start=start, end=end)

    def get_latest_quote(self, symbol: str) -> Quote:
        payload = self._get("/quote", {"symbol": symbol.upper(), "apikey": self.api_key})
        self._raise_for_vendor_error(payload)
        if str(payload.get("symbol", "")).upper() != symbol.upper():
            raise InvalidResponseError("Twelve Data returned a different quote symbol")
        as_of = _parse_date(payload.get("datetime") or date.today().isoformat())
        price = _float(payload, "close")
        return Quote(
            symbol=symbol.upper(),
            price=price,
            as_of=as_of,
            source=self.name,
            currency=_optional_str(payload.get("currency")),
            exchange=_optional_str(payload.get("exchange")),
            retrieval_timestamp=datetime.now(_UTC),
        )

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Dividend]:
        payload = self._get(
            "/dividends",
            {
                "symbol": symbol.upper(),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "apikey": self.api_key,
            },
        )
        self._raise_for_vendor_error(payload)
        meta = _dict(payload.get("meta"))
        items = payload.get("dividends", [])
        if not isinstance(items, list):
            raise InvalidResponseError("Twelve Data response is missing dividends")
        retrieval_timestamp = datetime.now(_UTC)
        dividends = [
            Dividend(
                symbol=symbol.upper(),
                ex_date=_parse_date(item.get("ex_date")),
                amount=_float(item, "amount"),
                currency=_optional_str(meta.get("currency")),
                data_source=self.name,
                retrieval_timestamp=retrieval_timestamp,
            )
            for item in items
            if isinstance(item, dict)
        ]
        return normalize_dividends(symbol, dividends, start=start, end=end)

    def get_splits(self, symbol: str, start: date, end: date) -> list[StockSplit]:
        payload = self._get(
            "/splits",
            {
                "symbol": symbol.upper(),
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "apikey": self.api_key,
            },
        )
        self._raise_for_vendor_error(payload)
        items = payload.get("splits", [])
        if not isinstance(items, list):
            raise InvalidResponseError("Twelve Data response is missing splits")
        retrieval_timestamp = datetime.now(_UTC)
        splits = [
            StockSplit(
                symbol=symbol.upper(),
                split_date=_parse_date(item.get("date")),
                from_factor=_float(item, "from_factor"),
                to_factor=_float(item, "to_factor"),
                data_source=self.name,
                retrieval_timestamp=retrieval_timestamp,
            )
            for item in items
            if isinstance(item, dict)
        ]
        return normalize_splits(symbol, splits, start=start, end=end)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        try:
            response = self.http_client.get_json(f"{BASE_URL}{path}", params)
        except Exception as exc:
            message = redact_secret(str(exc), [self.api_key])
            if message != str(exc):
                raise type(exc)(message) from exc
            raise
        return response.payload

    def _raise_for_vendor_error(self, payload: dict[str, Any]) -> None:
        status = str(payload.get("status", "")).lower()
        code = int(payload.get("code", 0) or 0)
        message = redact_secret(str(payload.get("message", "provider error")), [self.api_key])
        if status in {"error", "failed"} or code >= 400:
            lowered = message.lower()
            if "api key" in lowered or "apikey" in lowered:
                raise ProviderAuthenticationError("Twelve Data authentication failed")
            if "limit" in lowered or code == 429:
                raise RateLimitError("Twelve Data rate limit reached")
            if "symbol" in lowered:
                raise UnsupportedSymbolError(message)
            raise InvalidResponseError(message)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _parse_date(value: Any) -> date:
    if not value:
        raise InvalidResponseError("provider response is missing a date")
    return date.fromisoformat(str(value).split(" ")[0])


def _float(value: dict[str, Any], key: str) -> float:
    try:
        return float(value[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise InvalidResponseError(f"provider response is missing {key}") from exc


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError) as exc:
        raise InvalidResponseError("provider response has invalid volume") from exc


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
