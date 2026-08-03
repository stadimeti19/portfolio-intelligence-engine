from __future__ import annotations

from datetime import date, datetime, timezone

from portfolio_intelligence.domain.etfs import (
    AllocationType,
    EtfHolding,
    EtfMetadata,
    EtfProvider,
    SectorWeight,
)
from portfolio_intelligence.providers.etf.base import EtfCompositionNotFoundError
from portfolio_intelligence.providers.etf.validation import (
    normalize_holdings,
    normalize_sector_weights,
)

_UTC = timezone.utc  # noqa: UP017
_AS_OF = date(2026, 1, 2)

_HOLDINGS: dict[str, list[tuple[str, float, str, AllocationType]]] = {
    "VOO": [
        ("AAPL", 0.07, "Technology", AllocationType.SECURITY),
        ("MSFT", 0.065, "Technology", AllocationType.SECURITY),
        ("NVDA", 0.06, "Technology", AllocationType.SECURITY),
        ("JNJ", 0.025, "Healthcare", AllocationType.SECURITY),
        ("CASH", 0.005, "Cash", AllocationType.CASH),
    ],
    "QQQ": [
        ("AAPL", 0.09, "Technology", AllocationType.SECURITY),
        ("MSFT", 0.085, "Technology", AllocationType.SECURITY),
        ("NVDA", 0.075, "Technology", AllocationType.SECURITY),
        ("CASH", 0.01, "Cash", AllocationType.CASH),
    ],
    "SPY": [
        ("AAPL", 0.07, "Technology", AllocationType.SECURITY),
        ("MSFT", 0.065, "Technology", AllocationType.SECURITY),
        ("NVDA", 0.06, "Technology", AllocationType.SECURITY),
        ("JNJ", 0.025, "Healthcare", AllocationType.SECURITY),
    ],
}

_SECTORS: dict[str, list[tuple[str, float]]] = {
    "VOO": [("Technology", 0.32), ("Healthcare", 0.11), ("Financials", 0.13)],
    "QQQ": [("Technology", 0.52), ("Communication Services", 0.16), ("Consumer", 0.13)],
    "SPY": [("Technology", 0.32), ("Healthcare", 0.11), ("Financials", 0.13)],
}


class DemoEtfCompositionProvider:
    name = "demo"

    def get_holdings(self, symbol: str) -> list[EtfHolding]:
        symbol = symbol.upper()
        if symbol not in _HOLDINGS:
            raise EtfCompositionNotFoundError(f"no demo ETF composition for {symbol}")
        now = datetime.now(_UTC)
        rows = [
            EtfHolding(
                fund_symbol=symbol,
                constituent_symbol=constituent,
                weight=weight,
                sector=sector,
                allocation_type=allocation_type,
                as_of_date=_AS_OF,
                provider=EtfProvider.DEMO,
                retrieval_time=now,
            )
            for constituent, weight, sector, allocation_type in _HOLDINGS[symbol]
        ]
        return normalize_holdings(rows)

    def get_sector_weights(self, symbol: str) -> list[SectorWeight]:
        symbol = symbol.upper()
        if symbol not in _SECTORS:
            raise EtfCompositionNotFoundError(f"no demo ETF sector composition for {symbol}")
        now = datetime.now(_UTC)
        return normalize_sector_weights(
            [
                SectorWeight(
                    fund_symbol=symbol,
                    sector=sector,
                    weight=weight,
                    as_of_date=_AS_OF,
                    provider=EtfProvider.DEMO,
                    retrieval_time=now,
                )
                for sector, weight in _SECTORS[symbol]
            ]
        )

    def get_metadata(self, symbol: str) -> EtfMetadata:
        symbol = symbol.upper()
        if symbol not in _HOLDINGS:
            raise EtfCompositionNotFoundError(f"no demo ETF composition for {symbol}")
        return EtfMetadata(
            symbol=symbol,
            name=f"{symbol} synthetic demo ETF",
            as_of_date=_AS_OF,
            provider=EtfProvider.DEMO,
        )
