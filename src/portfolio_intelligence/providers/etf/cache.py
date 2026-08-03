from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError

from portfolio_intelligence.domain.etfs import (
    DataQualityStatus,
    EtfHolding,
    EtfMetadata,
    SectorWeight,
)
from portfolio_intelligence.providers.etf.base import EtfCompositionProvider

_UTC = timezone.utc  # noqa: UP017


class EtfCacheDocument(BaseModel):
    schema_version: int = 1
    symbol: str
    retrieval_time: datetime
    expiration_time: datetime
    holdings: list[EtfHolding]
    sector_weights: list[SectorWeight]
    metadata: EtfMetadata


class EtfCompositionCache:
    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def read(self, symbol: str, *, provider: str = "") -> EtfCacheDocument | None:
        path = self._path(symbol, provider)
        if not path.exists():
            return None
        try:
            return EtfCacheDocument.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"ETF cache entry is corrupt: {path.name}") from exc

    def write(self, document: EtfCacheDocument, *, provider: str = "") -> None:
        path = self._path(document.symbol, provider)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(path)

    def symbols(self) -> list[str]:
        symbols = []
        for path in self.directory.glob("*.json"):
            try:
                symbols.append(
                    EtfCacheDocument.model_validate_json(path.read_text(encoding="utf-8")).symbol
                )
            except (OSError, ValidationError):
                continue
        return sorted(set(symbols))

    def _path(self, symbol: str, provider: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in symbol.upper())
        prefix = f"{provider.lower()}-" if provider else ""
        return self.directory / f"{prefix}{safe.lower()}.json"


class CachedEtfCompositionProvider:
    def __init__(
        self,
        provider: EtfCompositionProvider,
        cache: EtfCompositionCache,
        *,
        ttl_hours: int = 24,
        stale_after_days: int = 45,
        allow_stale: bool = True,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.ttl_hours = ttl_hours
        self.stale_after_days = stale_after_days
        self.allow_stale = allow_stale
        self.name = provider.name
        self._memory: dict[str, EtfCacheDocument] = {}

    def get_holdings(self, symbol: str) -> list[EtfHolding]:
        return self._load(symbol).holdings

    def get_sector_weights(self, symbol: str) -> list[SectorWeight]:
        return self._load(symbol).sector_weights

    def get_metadata(self, symbol: str) -> EtfMetadata:
        return self._load(symbol).metadata

    def refresh(self, symbol: str) -> EtfMetadata:
        self._memory.pop(symbol.upper(), None)
        return self._fetch(symbol.upper()).metadata

    def _load(self, symbol: str) -> EtfCacheDocument:
        symbol = symbol.upper()
        cached = self._memory.get(symbol) or self.cache.read(symbol, provider=self.name)
        now = datetime.now(_UTC)
        if cached and _aware(cached.expiration_time) > now:
            document = self._label_freshness(cached)
            self._memory[symbol] = document
            return document
        try:
            return self._fetch(symbol)
        except Exception:
            if not cached or not self.allow_stale:
                raise
            document = _mark_stale(cached)
            self._memory[symbol] = document
            return document

    def _fetch(self, symbol: str) -> EtfCacheDocument:
        now = datetime.now(_UTC)
        holdings = self.provider.get_holdings(symbol)
        sectors = self.provider.get_sector_weights(symbol)
        metadata = self.provider.get_metadata(symbol)
        document = EtfCacheDocument(
            symbol=symbol,
            retrieval_time=now,
            expiration_time=now + timedelta(hours=self.ttl_hours),
            holdings=holdings,
            sector_weights=sectors,
            metadata=metadata,
        )
        document = self._label_freshness(document)
        self.cache.write(document, provider=self.name)
        self._memory[symbol] = document
        return document

    def _label_freshness(self, document: EtfCacheDocument) -> EtfCacheDocument:
        as_of = document.metadata.as_of_date
        stale = as_of is not None and (date.today() - as_of).days > self.stale_after_days
        return _mark_stale(document) if stale else document


def _mark_stale(document: EtfCacheDocument) -> EtfCacheDocument:
    return document.model_copy(
        update={
            "holdings": [
                item.model_copy(update={"data_quality": DataQualityStatus.STALE})
                for item in document.holdings
            ],
            "sector_weights": [
                item.model_copy(update={"data_quality": DataQualityStatus.STALE})
                for item in document.sector_weights
            ],
            "metadata": document.metadata.model_copy(
                update={"data_quality": DataQualityStatus.STALE, "stale": True}
            ),
        }
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=_UTC)
