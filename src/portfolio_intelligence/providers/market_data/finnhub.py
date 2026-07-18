from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any, Protocol

from portfolio_intelligence.domain.prices import Dividend, PriceBar, Quote, StockSplit
from portfolio_intelligence.providers.market_data.errors import (
    IncompleteHistoryError,
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

BASE_URL = "https://finnhub.io/api/v1"
_UTC = timezone.utc  # noqa: UP017 - keep local test environments on Python 3.10 working.


class FinnhubHttpClient(Protocol):
    def get_json(self, url: str, params: dict[str, str]) -> HttpResponse: ...


class FinnhubProvider:
    name = "finnhub"

    def __init__(
        self,
        api_key: str | None,
        *,
        timeout_seconds: int = 15,
        max_retries: int = 3,
        http_client: FinnhubHttpClient | None = None,
    ) -> None:
        if not api_key:
            raise MissingAPIKeyError("FINNHUB_API_KEY is required for Finnhub")
        self.api_key = api_key
        self.http_client = http_client or JsonHttpClient(
            timeout_seconds=timeout_seconds, max_retries=max_retries
        )

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        payload = self._get(
            "/stock/candle",
            {
                "symbol": symbol.upper(),
                "resolution": "D",
                "from": str(_timestamp(start)),
                "to": str(_timestamp(end)),
                "token": self.api_key,
            },
        )
        self._raise_for_vendor_error(payload)
        status = str(payload.get("s", "")).lower()
        if status == "no_data":
            raise IncompleteHistoryError(f"no Finnhub price history returned for {symbol.upper()}")
        if status != "ok":
            raise InvalidResponseError("Finnhub response is missing an ok candle status")
        closes = _list(payload, "c")
        highs = _list(payload, "h")
        lows = _list(payload, "l")
        opens = _list(payload, "o")
        timestamps = _list(payload, "t")
        volumes = _list(payload, "v")
        lengths = {len(closes), len(highs), len(lows), len(opens), len(timestamps), len(volumes)}
        if len(lengths) != 1:
            raise InvalidResponseError("Finnhub returned uneven candle arrays")
        retrieval_timestamp = datetime.now(_UTC)
        bars = [
            PriceBar(
                symbol=symbol.upper(),
                trading_date=datetime.fromtimestamp(float(timestamps[index]), _UTC).date(),
                open=float(opens[index]),
                high=float(highs[index]),
                low=float(lows[index]),
                close=float(closes[index]),
                adjusted_close=float(closes[index]),
                volume=int(float(volumes[index] or 0)),
                data_source=self.name,
                retrieval_timestamp=retrieval_timestamp,
            )
            for index in range(len(closes))
        ]
        return normalize_price_bars(symbol, bars, start=start, end=end)

    def get_latest_quote(self, symbol: str) -> Quote:
        payload = self._get("/quote", {"symbol": symbol.upper(), "token": self.api_key})
        self._raise_for_vendor_error(payload)
        price = _safe_float(payload.get("c"))
        if price <= 0:
            raise InvalidResponseError("Finnhub response is missing current quote price")
        timestamp = _safe_float(payload.get("t"))
        as_of = (
            datetime.fromtimestamp(timestamp, _UTC).date()
            if timestamp > 0
            else date.today()
        )
        return Quote(
            symbol=symbol.upper(),
            price=price,
            as_of=as_of,
            source=self.name,
            retrieval_timestamp=datetime.now(_UTC),
        )

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Dividend]:
        payload = self._get(
            "/stock/dividend",
            {
                "symbol": symbol.upper(),
                "from": start.isoformat(),
                "to": end.isoformat(),
                "token": self.api_key,
            },
        )
        self._raise_for_vendor_error(payload)
        if not isinstance(payload, list):
            raise InvalidResponseError("Finnhub response is missing dividends")
        retrieval_timestamp = datetime.now(_UTC)
        dividends = [
            Dividend(
                symbol=symbol.upper(),
                ex_date=_parse_date(item.get("date")),
                amount=float(item.get("amount", 0)),
                currency=_optional_str(item.get("currency")),
                data_source=self.name,
                retrieval_timestamp=retrieval_timestamp,
            )
            for item in payload
            if isinstance(item, dict)
        ]
        return normalize_dividends(symbol, dividends, start=start, end=end)

    def get_splits(self, symbol: str, start: date, end: date) -> list[StockSplit]:
        payload = self._get(
            "/stock/split",
            {
                "symbol": symbol.upper(),
                "from": start.isoformat(),
                "to": end.isoformat(),
                "token": self.api_key,
            },
        )
        self._raise_for_vendor_error(payload)
        if not isinstance(payload, list):
            raise InvalidResponseError("Finnhub response is missing splits")
        retrieval_timestamp = datetime.now(_UTC)
        splits = [
            StockSplit(
                symbol=symbol.upper(),
                split_date=_parse_date(item.get("date")),
                from_factor=float(item.get("fromFactor", 0)),
                to_factor=float(item.get("toFactor", 0)),
                data_source=self.name,
                retrieval_timestamp=retrieval_timestamp,
            )
            for item in payload
            if isinstance(item, dict)
        ]
        return normalize_splits(symbol, splits, start=start, end=end)

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any] | list[Any]:
        try:
            response = self.http_client.get_json(f"{BASE_URL}{path}", params)
        except Exception as exc:
            message = redact_secret(str(exc), [self.api_key])
            if message != str(exc):
                raise type(exc)(message) from exc
            raise
        return response.payload

    def _raise_for_vendor_error(self, payload: dict[str, Any] | list[Any]) -> None:
        if isinstance(payload, list):
            return
        message = str(payload.get("error") or payload.get("msg") or payload.get("message") or "")
        if not message:
            return
        safe_message = redact_secret(message, [self.api_key])
        lowered = safe_message.lower()
        if "api key" in lowered or "token" in lowered:
            raise ProviderAuthenticationError("Finnhub authentication failed")
        if "rate" in lowered or "limit" in lowered:
            raise RateLimitError("Finnhub rate limit reached")
        if "symbol" in lowered:
            raise UnsupportedSymbolError(safe_message)
        if "access" in lowered or "premium" in lowered or "entitlement" in lowered:
            raise ProviderAuthenticationError("Finnhub entitlement does not allow this data")
        raise InvalidResponseError(safe_message)


def _timestamp(value: date) -> int:
    return int(datetime.combine(value, time.min, tzinfo=_UTC).timestamp())


def _list(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise InvalidResponseError(f"Finnhub response is missing {key} array")
    return value


def _parse_date(value: Any) -> date:
    if not value:
        raise InvalidResponseError("provider response is missing a date")
    return date.fromisoformat(str(value).split("T")[0])


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
