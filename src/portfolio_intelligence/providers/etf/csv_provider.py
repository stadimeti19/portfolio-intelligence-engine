from __future__ import annotations

import csv
from datetime import date, datetime, timezone
from pathlib import Path

from portfolio_intelligence.domain.etfs import (
    AllocationType,
    DataQualityStatus,
    EtfHolding,
    EtfMetadata,
    EtfProvider,
    SectorWeight,
)
from portfolio_intelligence.providers.etf.base import (
    EtfCompositionNotFoundError,
    EtfCompositionValidationError,
)
from portfolio_intelligence.providers.etf.validation import (
    normalize_holdings,
    normalize_sector_weights,
)

_UTC = timezone.utc  # noqa: UP017


class CsvEtfCompositionProvider:
    """Read `<SYMBOL>.csv` or a consolidated `etf_holdings.csv` composition file."""

    name = "csv"

    def __init__(
        self,
        directory: str | Path,
        *,
        stale_after_days: int = 45,
        duplicate_policy: str = "combine",
        weight_tolerance: float = 0.01,
    ) -> None:
        self.directory = Path(directory)
        self.stale_after_days = stale_after_days
        self.duplicate_policy = duplicate_policy
        self.weight_tolerance = weight_tolerance

    def get_holdings(self, symbol: str) -> list[EtfHolding]:
        symbol = symbol.upper()
        rows = self._rows(symbol, "holdings")
        now = datetime.now(_UTC)
        holdings: list[EtfHolding] = []
        for row in rows:
            as_of = _date(row.get("as_of_date") or row.get("as_of"))
            quality = _quality(as_of, self.stale_after_days)
            constituent = _required(row, "constituent_symbol", "symbol", "ticker")
            allocation_text = (row.get("allocation_type") or "security").strip().lower()
            if constituent.upper() in {"CASH", "CASH & EQUIVALENTS"}:
                allocation_text = "cash"
            try:
                allocation_type = AllocationType(allocation_text)
            except ValueError as exc:
                raise EtfCompositionValidationError(
                    f"invalid allocation_type {allocation_text!r} for {symbol}"
                ) from exc
            holdings.append(
                EtfHolding(
                    fund_symbol=symbol,
                    constituent_symbol=constituent,
                    name=row.get("name") or row.get("description") or None,
                    weight=_weight(_required(row, "weight")),
                    sector=row.get("sector") or None,
                    allocation_type=allocation_type,
                    as_of_date=as_of,
                    provider=EtfProvider.CSV,
                    retrieval_time=now,
                    data_quality=quality,
                )
            )
        return normalize_holdings(
            holdings,
            duplicate_policy=self.duplicate_policy,
            weight_tolerance=self.weight_tolerance,
        )

    def get_sector_weights(self, symbol: str) -> list[SectorWeight]:
        symbol = symbol.upper()
        try:
            rows = self._rows(symbol, "sectors")
        except EtfCompositionNotFoundError:
            holdings = self.get_holdings(symbol)
            if not any(
                item.sector for item in holdings if item.allocation_type == AllocationType.SECURITY
            ):
                return []
            now = datetime.now(_UTC)
            as_of = min((item.as_of_date for item in holdings if item.as_of_date), default=None)
            quality = (
                DataQualityStatus.STALE
                if any(item.data_quality == DataQualityStatus.STALE for item in holdings)
                else DataQualityStatus.FRESH
            )
            by_sector: dict[str, float] = {}
            for item in holdings:
                sector = item.sector or "Unknown"
                by_sector[sector] = by_sector.get(sector, 0.0) + item.weight
            return normalize_sector_weights(
                [
                    SectorWeight(
                        fund_symbol=symbol,
                        sector=sector,
                        weight=weight,
                        as_of_date=as_of,
                        provider=EtfProvider.CSV,
                        retrieval_time=now,
                        data_quality=quality,
                    )
                    for sector, weight in by_sector.items()
                ]
            )
        now = datetime.now(_UTC)
        return normalize_sector_weights(
            [
                SectorWeight(
                    fund_symbol=symbol,
                    sector=_required(row, "sector"),
                    weight=_weight(_required(row, "weight")),
                    as_of_date=_date(row.get("as_of_date") or row.get("as_of")),
                    provider=EtfProvider.CSV,
                    retrieval_time=now,
                    data_quality=_quality(
                        _date(row.get("as_of_date") or row.get("as_of")),
                        self.stale_after_days,
                    ),
                )
                for row in rows
            ],
            weight_tolerance=self.weight_tolerance,
        )

    def get_metadata(self, symbol: str) -> EtfMetadata:
        symbol = symbol.upper()
        metadata_path = self.directory / "etf_metadata.csv"
        match: dict[str, str] | None = None
        if metadata_path.exists():
            for row in _read_csv(metadata_path):
                if (row.get("symbol") or row.get("fund_symbol") or "").upper() == symbol:
                    match = row
                    break
        holdings = self.get_holdings(symbol)
        as_of = _date(match.get("as_of_date")) if match else None
        as_of = as_of or min(
            (item.as_of_date for item in holdings if item.as_of_date), default=None
        )
        quality = _quality(as_of, self.stale_after_days)
        return EtfMetadata(
            symbol=symbol,
            name=(match or {}).get("name") or None,
            description=(match or {}).get("description") or None,
            net_assets=_optional_float((match or {}).get("net_assets")),
            expense_ratio=_optional_weight((match or {}).get("expense_ratio")),
            as_of_date=as_of,
            provider=EtfProvider.CSV,
            data_quality=quality,
            stale=quality == DataQualityStatus.STALE,
            missing_constituents=["OTHER"]
            if any(item.allocation_type == AllocationType.OTHER for item in holdings)
            else [],
        )

    def _rows(self, symbol: str, kind: str) -> list[dict[str, str]]:
        candidates = (
            [self.directory / f"{symbol}.csv", self.directory / "etf_holdings.csv"]
            if kind == "holdings"
            else [self.directory / f"{symbol}.sectors.csv", self.directory / "etf_sectors.csv"]
        )
        for path in candidates:
            if not path.exists():
                continue
            rows = _read_csv(path)
            filtered = [
                row
                for row in rows
                if not (row.get("fund_symbol") or row.get("etf_symbol"))
                or (row.get("fund_symbol") or row.get("etf_symbol") or "").upper() == symbol
            ]
            if filtered:
                return filtered
        raise EtfCompositionNotFoundError(f"no CSV ETF {kind} found for {symbol}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [
                {key.strip(): (value or "").strip() for key, value in row.items()}
                for row in csv.DictReader(handle)
            ]
    except OSError as exc:
        raise EtfCompositionNotFoundError(f"cannot read ETF CSV: {path}") from exc


def _required(row: dict[str, str], *names: str) -> str:
    for name in names:
        if row.get(name):
            return row[name]
    raise EtfCompositionValidationError(f"ETF CSV is missing required field: {'/'.join(names)}")


def _weight(value: str) -> float:
    text = value.strip()
    percent = text.endswith("%")
    try:
        number = float(text.removesuffix("%").replace(",", ""))
    except ValueError as exc:
        raise EtfCompositionValidationError(f"invalid ETF weight: {value!r}") from exc
    return number / 100.0 if percent or number > 1.0 else number


def _optional_weight(value: str | None) -> float | None:
    return _weight(value) if value else None


def _optional_float(value: str | None) -> float | None:
    return float(value.replace(",", "")) if value else None


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise EtfCompositionValidationError(f"invalid ETF as-of date: {value!r}") from exc


def _quality(as_of: date | None, stale_after_days: int) -> DataQualityStatus:
    if as_of and (date.today() - as_of).days > stale_after_days:
        return DataQualityStatus.STALE
    return DataQualityStatus.FRESH
