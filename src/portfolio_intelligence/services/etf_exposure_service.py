from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations

from portfolio_intelligence.domain.assets import Asset, AssetType
from portfolio_intelligence.domain.etfs import (
    AllocationType,
    ConcentrationMetrics,
    DataQualityStatus,
    EtfExposureReport,
    EtfHolding,
    EtfOverlap,
    SectorExposure,
    SectorExposureMethod,
    SecurityExposure,
)
from portfolio_intelligence.domain.positions import Position
from portfolio_intelligence.providers.etf.base import EtfCompositionProvider


class EtfExposureService:
    def __init__(
        self,
        provider: EtfCompositionProvider | None,
        assets: dict[str, Asset],
        *,
        security_concentration_threshold: float = 0.15,
        sector_concentration_threshold: float = 0.50,
        overlap_warning_threshold: float = 0.40,
    ) -> None:
        self.provider = provider
        self.assets = assets
        self.security_threshold = security_concentration_threshold
        self.sector_threshold = sector_concentration_threshold
        self.overlap_threshold = overlap_warning_threshold

    def analyze(
        self,
        positions: list[Position],
        *,
        total_portfolio_value: float | None = None,
        look_through: bool = True,
        etf_symbols: set[str] | None = None,
    ) -> EtfExposureReport:
        total = total_portfolio_value
        if total is None:
            total = sum(position.market_value for position in positions)
        etfs = {
            position.symbol
            for position in positions
            if position.symbol in (etf_symbols or set())
            or self.assets.get(position.symbol, _UNKNOWN_ASSET).asset_type == AssetType.ETF
        }
        values: dict[str, _ExposureAccumulator] = {}
        sectors: dict[str, float] = defaultdict(float)
        sector_methods: dict[str, set[SectorExposureMethod]] = defaultdict(set)
        compositions: dict[str, list[EtfHolding]] = {}
        data_as_of: dict[str, date | None] = {}
        warnings: list[str] = []

        for position in positions:
            if position.symbol not in etfs or not look_through:
                row = _security(values, position.symbol)
                row.direct += position.market_value
                row.effective += position.market_value
                sector = self.assets.get(position.symbol, _UNKNOWN_ASSET).sector or "Unknown"
                row.sector = sector
                sectors[sector] += position.market_value
                sector_methods[sector].add(SectorExposureMethod.DIRECT)
                continue

            wrapper = _security(values, position.symbol)
            wrapper.direct += position.market_value
            if self.provider is None:
                self._retain_unexpanded_etf(position, wrapper, sectors, sector_methods)
                warnings.append(
                    f"{position.symbol} composition is unavailable; ETF was not expanded."
                )
                continue
            try:
                holdings = self.provider.get_holdings(position.symbol)
                metadata = self.provider.get_metadata(position.symbol)
            except Exception as exc:
                self._retain_unexpanded_etf(position, wrapper, sectors, sector_methods)
                warnings.append(
                    f"{position.symbol} composition is unavailable; ETF was not expanded: {exc}"
                )
                continue
            compositions[position.symbol] = holdings
            data_as_of[position.symbol] = metadata.as_of_date
            if metadata.stale or metadata.data_quality == DataQualityStatus.STALE:
                warnings.append(
                    f"{position.symbol} composition is stale"
                    + (
                        f" (as of {metadata.as_of_date.isoformat()})."
                        if metadata.as_of_date
                        else "."
                    )
                )
            missing = sorted(
                {
                    item.constituent_symbol
                    for item in holdings
                    if item.allocation_type == AllocationType.OTHER
                    or item.data_quality == DataQualityStatus.INCOMPLETE
                }
                | set(metadata.missing_constituents)
            )
            if missing:
                warnings.append(
                    f"{position.symbol} has missing or unreported constituents: "
                    f"{', '.join(missing)}."
                )
            for constituent in holdings:
                indirect = position.market_value * constituent.weight
                row = _security(values, constituent.constituent_symbol)
                row.indirect += indirect
                row.effective += indirect
                row.sector = constituent.sector or row.sector
                row.contributing[position.symbol] = indirect
                if constituent.as_of_date:
                    row.as_of_dates.add(constituent.as_of_date)
            self._add_etf_sectors(
                position,
                holdings,
                sectors,
                sector_methods,
                warnings,
            )

        securities = _build_security_exposures(values, total)
        sector_rows = [
            SectorExposure(
                sector=sector,
                value=value,
                weight=value / total if total else 0.0,
                methods=sorted(sector_methods[sector], key=lambda item: item.value),
            )
            for sector, value in sorted(sectors.items(), key=lambda item: (-item[1], item[0]))
        ]
        overlaps = self.calculate_overlaps(compositions)
        concentration = self._concentration(securities, sector_rows, overlaps)
        warnings.extend(concentration.warnings)
        return EtfExposureReport(
            securities=securities,
            sectors=sector_rows,
            concentration=concentration,
            etf_overlaps=overlaps,
            data_as_of=data_as_of,
            warnings=_deduplicate(warnings),
            look_through=look_through,
            total_portfolio_value=total,
        )

    def calculate_overlaps(self, compositions: dict[str, list[EtfHolding]]) -> list[EtfOverlap]:
        return [
            calculate_etf_overlap(left, right, compositions[left], compositions[right])
            for left, right in combinations(sorted(compositions), 2)
        ]

    def _add_etf_sectors(
        self,
        position: Position,
        holdings: list[EtfHolding],
        sectors: dict[str, float],
        methods: dict[str, set[SectorExposureMethod]],
        warnings: list[str],
    ) -> None:
        securities = [item for item in holdings if item.allocation_type == AllocationType.SECURITY]
        constituent_sectors_complete = bool(securities) and all(item.sector for item in securities)
        if constituent_sectors_complete:
            for item in holdings:
                sector = item.sector or (
                    "Cash" if item.allocation_type == AllocationType.CASH else "Unknown"
                )
                sectors[sector] += position.market_value * item.weight
                methods[sector].add(SectorExposureMethod.CONSTITUENT)
            return
        try:
            sector_weights = (
                self.provider.get_sector_weights(position.symbol) if self.provider else []
            )
        except Exception as exc:
            sector_weights = []
            warnings.append(f"{position.symbol} sector allocation is unavailable: {exc}")
        if sector_weights:
            for sector_weight in sector_weights:
                sectors[sector_weight.sector] += position.market_value * sector_weight.weight
                methods[sector_weight.sector].add(SectorExposureMethod.ETF_SECTOR_ALLOCATION)
            return
        sectors["Unknown"] += position.market_value
        methods["Unknown"].add(SectorExposureMethod.UNCLASSIFIED)
        warnings.append(f"{position.symbol} has no constituent or ETF-level sector metadata.")

    def _retain_unexpanded_etf(
        self,
        position: Position,
        wrapper: _ExposureAccumulator,
        sectors: dict[str, float],
        methods: dict[str, set[SectorExposureMethod]],
    ) -> None:
        wrapper.effective += position.market_value
        wrapper.sector = "Unknown"
        sectors["Unknown"] += position.market_value
        methods["Unknown"].add(SectorExposureMethod.UNCLASSIFIED)

    def _concentration(
        self,
        securities: list[SecurityExposure],
        sectors: list[SectorExposure],
        overlaps: list[EtfOverlap],
    ) -> ConcentrationMetrics:
        effective = [
            item for item in securities if item.effective_value > 0 and item.symbol != "CASH"
        ]
        invested = sum(item.effective_value for item in effective)
        normalized = [item.effective_value / invested for item in effective] if invested else []
        hhi = sum(weight * weight for weight in normalized)
        warnings = [
            f"{item.symbol} effective exposure is {item.effective_weight:.1%}, "
            f"above the configured {self.security_threshold:.0%} limit."
            for item in effective
            if item.effective_weight > self.security_threshold
        ]
        warnings.extend(
            f"{item.sector} effective exposure is {item.weight:.1%}, "
            f"above the configured {self.sector_threshold:.0%} limit."
            for item in sectors
            if item.weight > self.sector_threshold
        )
        warnings.extend(
            f"{item.left_symbol} and {item.right_symbol} have "
            f"{item.weighted_overlap:.0%} weighted overlap."
            for item in overlaps
            if item.weighted_overlap > self.overlap_threshold
        )
        return ConcentrationMetrics(
            largest_security_weight=max((item.effective_weight for item in effective), default=0.0),
            largest_sector_weight=max((item.weight for item in sectors), default=0.0),
            top_five_effective_holdings=sorted(
                effective, key=lambda item: (-item.effective_value, item.symbol)
            )[:5],
            hhi=hhi,
            effective_number_of_holdings=1.0 / hhi if hhi else 0.0,
            warnings=warnings,
        )


def calculate_etf_overlap(
    left_symbol: str,
    right_symbol: str,
    left: list[EtfHolding],
    right: list[EtfHolding],
) -> EtfOverlap:
    left_weights = _security_weights(left)
    right_weights = _security_weights(right)
    shared = sorted(set(left_weights) & set(right_weights))
    overlap_rows: list[dict[str, float | str]] = [
        {
            "symbol": symbol,
            "overlap_weight": min(left_weights[symbol], right_weights[symbol]),
            "left_weight": left_weights[symbol],
            "right_weight": right_weights[symbol],
        }
        for symbol in shared
    ]
    overlap_rows.sort(key=lambda item: (-float(item["overlap_weight"]), str(item["symbol"])))
    left_sectors = _sector_weights(left)
    right_sectors = _sector_weights(right)
    sector_overlap = sum(
        min(left_sectors[sector], right_sectors[sector])
        for sector in set(left_sectors) & set(right_sectors)
    )
    return EtfOverlap(
        left_symbol=left_symbol.upper(),
        right_symbol=right_symbol.upper(),
        shared_constituents=shared,
        weighted_overlap=sum(float(row["overlap_weight"]) for row in overlap_rows),
        top_overlapping_securities=overlap_rows[:10],
        sector_overlap=sector_overlap,
    )


def _security_weights(holdings: list[EtfHolding]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for item in holdings:
        if item.allocation_type == AllocationType.SECURITY:
            result[item.constituent_symbol] += item.weight
    return dict(result)


def _sector_weights(holdings: list[EtfHolding]) -> dict[str, float]:
    result: dict[str, float] = defaultdict(float)
    for item in holdings:
        if item.allocation_type == AllocationType.SECURITY:
            result[item.sector or "Unknown"] += item.weight
    return dict(result)


@dataclass
class _ExposureAccumulator:
    direct: float = 0.0
    indirect: float = 0.0
    effective: float = 0.0
    contributing: dict[str, float] = field(default_factory=dict)
    sector: str | None = None
    as_of_dates: set[date] = field(default_factory=set)


def _security(values: dict[str, _ExposureAccumulator], symbol: str) -> _ExposureAccumulator:
    return values.setdefault(symbol, _ExposureAccumulator())


def _build_security_exposures(
    values: dict[str, _ExposureAccumulator], total: float
) -> list[SecurityExposure]:
    output = []
    for symbol, value in values.items():
        direct = value.direct
        indirect = value.indirect
        effective = value.effective
        output.append(
            SecurityExposure(
                symbol=symbol,
                direct_value=direct,
                indirect_value=indirect,
                effective_value=effective,
                direct_weight=direct / total if total else 0.0,
                indirect_weight=indirect / total if total else 0.0,
                effective_weight=effective / total if total else 0.0,
                contributing_etfs=value.contributing,
                sector=value.sector,
                as_of_dates=sorted(value.as_of_dates),
            )
        )
    return sorted(output, key=lambda item: (-item.effective_value, item.symbol))


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


_UNKNOWN_ASSET = Asset(
    symbol="UNKNOWN", name="Unknown", asset_type=AssetType.EQUITY, sector="Unknown"
)
