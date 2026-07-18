from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from portfolio_intelligence.domain.prices import Dividend, PriceBar, Quote, StockSplit
from portfolio_intelligence.providers.market_data.base import MarketDataProvider
from portfolio_intelligence.providers.market_data.errors import (
    CacheCorruptionError,
    MarketDataError,
)
from portfolio_intelligence.providers.market_data.validation import (
    normalize_dividends,
    normalize_price_bars,
    normalize_splits,
)

SCHEMA_VERSION = 1
CacheEndpoint = Literal["prices", "quote", "dividends", "splits"]
_UTC = timezone.utc  # noqa: UP017 - keep local test environments on Python 3.10 working.


class CacheMetadata(BaseModel):
    provider: str
    symbol: str
    endpoint: CacheEndpoint
    request_params: dict[str, str]
    retrieval_timestamp: datetime
    effective_market_data_date: date | None = None
    expiration_timestamp: datetime
    schema_version: int = SCHEMA_VERSION
    payload_checksum: str
    complete: bool
    fallback: bool = False


class CacheDocument(BaseModel):
    metadata: CacheMetadata
    payload: list[dict[str, Any]] | dict[str, Any]


@dataclass(frozen=True)
class CacheStatus:
    symbol: str
    provider: str
    endpoint: str
    first_date: date | None
    latest_date: date | None
    retrieval_timestamp: datetime | None
    expiration_timestamp: datetime | None
    complete: bool
    fallback: bool
    stale: bool
    path: Path

    @property
    def cache_status(self) -> str:
        if self.retrieval_timestamp is None:
            return "missing"
        return "stale" if self.stale else "valid"


class MarketDataCache:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def read_prices(
        self, provider: str, symbol: str
    ) -> tuple[CacheMetadata, list[PriceBar]] | None:
        document = self._read(provider, symbol, "prices")
        if document is None:
            return None
        try:
            bars = [PriceBar.model_validate(item) for item in document.payload]
        except (TypeError, ValidationError) as exc:
            raise CacheCorruptionError("cached price payload is invalid") from exc
        return document.metadata, bars

    def write_prices(
        self,
        provider: str,
        symbol: str,
        bars: list[PriceBar],
        *,
        ttl_hours: int,
        request_params: dict[str, str],
        complete: bool,
        fallback: bool,
    ) -> CacheMetadata:
        normalized = normalize_price_bars(symbol, bars)
        now = _now()
        payload = [bar.model_dump(mode="json") for bar in normalized]
        metadata = CacheMetadata(
            provider=provider,
            symbol=symbol.upper(),
            endpoint="prices",
            request_params=request_params,
            retrieval_timestamp=now,
            effective_market_data_date=normalized[-1].trading_date if normalized else None,
            expiration_timestamp=now + timedelta(hours=ttl_hours),
            payload_checksum=_checksum(payload),
            complete=complete,
            fallback=fallback,
        )
        self._write(provider, symbol, "prices", CacheDocument(metadata=metadata, payload=payload))
        return metadata

    def read_quote(self, provider: str, symbol: str) -> tuple[CacheMetadata, Quote] | None:
        document = self._read(provider, symbol, "quote")
        if document is None:
            return None
        try:
            quote = Quote.model_validate(document.payload)
        except (TypeError, ValidationError) as exc:
            raise CacheCorruptionError("cached quote payload is invalid") from exc
        return document.metadata, quote

    def write_quote(
        self,
        provider: str,
        symbol: str,
        quote: Quote,
        *,
        ttl_hours: int,
        request_params: dict[str, str],
        fallback: bool,
    ) -> CacheMetadata:
        now = _now()
        payload = quote.model_dump(mode="json")
        metadata = CacheMetadata(
            provider=provider,
            symbol=symbol.upper(),
            endpoint="quote",
            request_params=request_params,
            retrieval_timestamp=now,
            effective_market_data_date=quote.as_of,
            expiration_timestamp=now + timedelta(hours=ttl_hours),
            payload_checksum=_checksum(payload),
            complete=True,
            fallback=fallback,
        )
        self._write(provider, symbol, "quote", CacheDocument(metadata=metadata, payload=payload))
        return metadata

    def read_dividends(
        self, provider: str, symbol: str
    ) -> tuple[CacheMetadata, list[Dividend]] | None:
        document = self._read(provider, symbol, "dividends")
        if document is None:
            return None
        try:
            dividends = [Dividend.model_validate(item) for item in document.payload]
        except (TypeError, ValidationError) as exc:
            raise CacheCorruptionError("cached dividend payload is invalid") from exc
        return document.metadata, dividends

    def write_dividends(
        self,
        provider: str,
        symbol: str,
        dividends: list[Dividend],
        *,
        ttl_hours: int,
        request_params: dict[str, str],
        complete: bool,
        fallback: bool,
    ) -> CacheMetadata:
        now = _now()
        payload = [item.model_dump(mode="json") for item in dividends]
        latest = max((item.ex_date for item in dividends), default=None)
        metadata = CacheMetadata(
            provider=provider,
            symbol=symbol.upper(),
            endpoint="dividends",
            request_params=request_params,
            retrieval_timestamp=now,
            effective_market_data_date=latest,
            expiration_timestamp=now + timedelta(hours=ttl_hours),
            payload_checksum=_checksum(payload),
            complete=complete,
            fallback=fallback,
        )
        self._write(
            provider, symbol, "dividends", CacheDocument(metadata=metadata, payload=payload)
        )
        return metadata

    def read_splits(
        self, provider: str, symbol: str
    ) -> tuple[CacheMetadata, list[StockSplit]] | None:
        document = self._read(provider, symbol, "splits")
        if document is None:
            return None
        try:
            splits = [StockSplit.model_validate(item) for item in document.payload]
        except (TypeError, ValidationError) as exc:
            raise CacheCorruptionError("cached split payload is invalid") from exc
        return document.metadata, splits

    def write_splits(
        self,
        provider: str,
        symbol: str,
        splits: list[StockSplit],
        *,
        ttl_hours: int,
        request_params: dict[str, str],
        complete: bool,
        fallback: bool,
    ) -> CacheMetadata:
        now = _now()
        payload = [item.model_dump(mode="json") for item in splits]
        latest = max((item.split_date for item in splits), default=None)
        metadata = CacheMetadata(
            provider=provider,
            symbol=symbol.upper(),
            endpoint="splits",
            request_params=request_params,
            retrieval_timestamp=now,
            effective_market_data_date=latest,
            expiration_timestamp=now + timedelta(hours=ttl_hours),
            payload_checksum=_checksum(payload),
            complete=complete,
            fallback=fallback,
        )
        self._write(provider, symbol, "splits", CacheDocument(metadata=metadata, payload=payload))
        return metadata

    def statuses(self) -> list[CacheStatus]:
        statuses: list[CacheStatus] = []
        for path in sorted(self.directory.glob("*.json")):
            try:
                document = self._read_path(path)
            except CacheCorruptionError:
                statuses.append(
                    CacheStatus(
                        symbol="unknown",
                        provider="unknown",
                        endpoint=path.stem,
                        first_date=None,
                        latest_date=None,
                        retrieval_timestamp=None,
                        expiration_timestamp=None,
                        complete=False,
                        fallback=False,
                        stale=True,
                        path=path,
                    )
                )
                continue
            metadata = document.metadata
            first_date, latest_date = _payload_dates(metadata.endpoint, document.payload)
            statuses.append(
                CacheStatus(
                    symbol=metadata.symbol,
                    provider=metadata.provider,
                    endpoint=metadata.endpoint,
                    first_date=first_date,
                    latest_date=latest_date or metadata.effective_market_data_date,
                    retrieval_timestamp=metadata.retrieval_timestamp,
                    expiration_timestamp=metadata.expiration_timestamp,
                    complete=metadata.complete,
                    fallback=metadata.fallback,
                    stale=_is_expired(metadata),
                    path=path,
                )
            )
        return statuses

    def _read(
        self, provider: str, symbol: str, endpoint: CacheEndpoint
    ) -> CacheDocument | None:
        path = self._path(provider, symbol, endpoint)
        if not path.exists():
            return None
        return self._read_path(path)

    def _read_path(self, path: Path) -> CacheDocument:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            document = CacheDocument.model_validate(raw)
        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            raise CacheCorruptionError(f"cache entry is corrupt: {path.name}") from exc
        if document.metadata.schema_version != SCHEMA_VERSION:
            raise CacheCorruptionError("cache schema version is unsupported")
        expected = _checksum(document.payload)
        if expected != document.metadata.payload_checksum:
            raise CacheCorruptionError("cache payload checksum mismatch")
        return document

    def _write(
        self, provider: str, symbol: str, endpoint: CacheEndpoint, document: CacheDocument
    ) -> None:
        path = self._path(provider, symbol, endpoint)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)

    def _path(self, provider: str, symbol: str, endpoint: CacheEndpoint) -> Path:
        safe_symbol = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in symbol.upper())
        return self.directory / f"{provider.lower()}-{safe_symbol}-{endpoint}.json"


class CachedMarketDataProvider:
    def __init__(
        self,
        provider: MarketDataProvider,
        cache: MarketDataCache,
        *,
        price_ttl_hours: int,
        corporate_action_ttl_hours: int,
        allow_stale: bool,
        fallback: bool = False,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.price_ttl_hours = price_ttl_hours
        self.corporate_action_ttl_hours = corporate_action_ttl_hours
        self.allow_stale = allow_stale
        self.fallback = fallback
        self.name = provider.name

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        symbol = symbol.upper()
        cached = self.cache.read_prices(self.name, symbol)
        if cached:
            metadata, bars = cached
            normalized = normalize_price_bars(symbol, bars, start=start, end=end)
            if _covers(normalized, start, end) and not _is_expired(metadata):
                return _mark_prices(normalized, stale=False, fallback=metadata.fallback)
        else:
            metadata = None
            bars = []
        fetch_start = _incremental_start(bars, start)
        try:
            fetched = self.provider.get_daily_prices(symbol, fetch_start, end)
        except MarketDataError:
            if cached and self.allow_stale:
                return _mark_prices(
                    normalize_price_bars(symbol, bars, start=start, end=end),
                    stale=True,
                    fallback=metadata.fallback if metadata else self.fallback,
                )
            raise
        merged = _merge_prices(bars, fetched)
        complete = _covers(normalize_price_bars(symbol, merged, start=start, end=end), start, end)
        self.cache.write_prices(
            self.name,
            symbol,
            merged,
            ttl_hours=self.price_ttl_hours,
            request_params={"start": start.isoformat(), "end": end.isoformat()},
            complete=complete,
            fallback=self.fallback,
        )
        return _mark_prices(
            normalize_price_bars(symbol, merged, start=start, end=end),
            stale=False,
            fallback=self.fallback,
        )

    def get_latest_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        cached = self.cache.read_quote(self.name, symbol)
        if cached and not _is_expired(cached[0]):
            return cached[1].model_copy(update={"stale": False, "fallback": cached[0].fallback})
        try:
            quote = self.provider.get_latest_quote(symbol)
        except MarketDataError:
            if cached and self.allow_stale:
                return cached[1].model_copy(update={"stale": True, "fallback": cached[0].fallback})
            raise
        self.cache.write_quote(
            self.name,
            symbol,
            quote,
            ttl_hours=self.price_ttl_hours,
            request_params={"symbol": symbol},
            fallback=self.fallback,
        )
        return quote.model_copy(update={"stale": False, "fallback": self.fallback})

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Dividend]:
        symbol = symbol.upper()
        cached = self.cache.read_dividends(self.name, symbol)
        if cached and not _is_expired(cached[0]):
            return normalize_dividends(symbol, cached[1], start=start, end=end)
        try:
            dividends = self.provider.get_dividends(symbol, start, end)
        except MarketDataError:
            if cached and self.allow_stale:
                return [
                    item.model_copy(update={"stale": True, "fallback": cached[0].fallback})
                    for item in normalize_dividends(symbol, cached[1], start=start, end=end)
                ]
            raise
        normalized = normalize_dividends(symbol, dividends, start=start, end=end)
        self.cache.write_dividends(
            self.name,
            symbol,
            normalized,
            ttl_hours=self.corporate_action_ttl_hours,
            request_params={"start": start.isoformat(), "end": end.isoformat()},
            complete=True,
            fallback=self.fallback,
        )
        return [item.model_copy(update={"fallback": self.fallback}) for item in normalized]

    def get_splits(self, symbol: str, start: date, end: date) -> list[StockSplit]:
        symbol = symbol.upper()
        cached = self.cache.read_splits(self.name, symbol)
        if cached and not _is_expired(cached[0]):
            return normalize_splits(symbol, cached[1], start=start, end=end)
        try:
            splits = self.provider.get_splits(symbol, start, end)
        except MarketDataError:
            if cached and self.allow_stale:
                return [
                    item.model_copy(update={"stale": True, "fallback": cached[0].fallback})
                    for item in normalize_splits(symbol, cached[1], start=start, end=end)
                ]
            raise
        normalized = normalize_splits(symbol, splits, start=start, end=end)
        self.cache.write_splits(
            self.name,
            symbol,
            normalized,
            ttl_hours=self.corporate_action_ttl_hours,
            request_params={"start": start.isoformat(), "end": end.isoformat()},
            complete=True,
            fallback=self.fallback,
        )
        return [item.model_copy(update={"fallback": self.fallback}) for item in normalized]


def _now() -> datetime:
    return datetime.now(_UTC)


def _is_expired(metadata: CacheMetadata) -> bool:
    return metadata.expiration_timestamp <= _now()


def _checksum(payload: list[dict[str, Any]] | dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _covers(bars: list[PriceBar], start: date, end: date) -> bool:
    return (
        bool(bars)
        and bars[0].trading_date <= _next_business_day(start)
        and bars[-1].trading_date >= _previous_business_day(end)
    )


def _incremental_start(cached: list[PriceBar], requested_start: date) -> date:
    if not cached:
        return requested_start
    latest = max(bar.trading_date for bar in cached)
    if latest < requested_start:
        return requested_start
    return latest


def _merge_prices(existing: list[PriceBar], fetched: list[PriceBar]) -> list[PriceBar]:
    by_date = {bar.trading_date: bar for bar in existing}
    by_date.update({bar.trading_date: bar for bar in fetched})
    return [by_date[day] for day in sorted(by_date)]


def _mark_prices(bars: list[PriceBar], *, stale: bool, fallback: bool) -> list[PriceBar]:
    return [bar.model_copy(update={"stale": stale, "fallback": fallback}) for bar in bars]


def _next_business_day(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def _previous_business_day(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _payload_dates(
    endpoint: CacheEndpoint, payload: list[dict[str, Any]] | dict[str, Any]
) -> tuple[date | None, date | None]:
    if endpoint == "quote" and isinstance(payload, dict):
        value = payload.get("as_of")
        parsed = date.fromisoformat(str(value)) if value else None
        return parsed, parsed
    if not isinstance(payload, list) or not payload:
        return None, None
    key = {"prices": "trading_date", "dividends": "ex_date", "splits": "split_date"}[endpoint]
    dates = sorted(date.fromisoformat(str(item[key])) for item in payload if item.get(key))
    return (dates[0], dates[-1]) if dates else (None, None)
