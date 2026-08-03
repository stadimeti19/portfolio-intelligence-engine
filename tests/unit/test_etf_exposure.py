from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from portfolio_intelligence.domain.assets import Asset, AssetType
from portfolio_intelligence.domain.etfs import (
    AllocationType,
    DataQualityStatus,
    EtfHolding,
    EtfMetadata,
    EtfProvider,
    SectorExposureMethod,
    SectorWeight,
)
from portfolio_intelligence.domain.positions import Position
from portfolio_intelligence.providers.etf.alpha_vantage import AlphaVantageEtfCompositionProvider
from portfolio_intelligence.providers.etf.base import EtfCompositionNotFoundError
from portfolio_intelligence.providers.etf.cache import (
    CachedEtfCompositionProvider,
    EtfCompositionCache,
)
from portfolio_intelligence.providers.etf.csv_provider import CsvEtfCompositionProvider
from portfolio_intelligence.providers.etf.fallback import FallbackEtfCompositionProvider
from portfolio_intelligence.providers.etf.validation import normalize_holdings
from portfolio_intelligence.providers.market_data.http import HttpResponse
from portfolio_intelligence.services.etf_exposure_service import (
    EtfExposureService,
    calculate_etf_overlap,
)

NOW = datetime.now(timezone.utc)  # noqa: UP017 - local test environments include Python 3.10.
AS_OF = date.today() - timedelta(days=1)


class SyntheticProvider:
    name = "synthetic"

    def __init__(
        self,
        holdings: dict[str, list[EtfHolding]],
        sectors: dict[str, list[SectorWeight]] | None = None,
        *,
        stale: bool = False,
    ) -> None:
        self.holdings = holdings
        self.sectors = sectors or {}
        self.stale = stale

    def get_holdings(self, symbol: str) -> list[EtfHolding]:
        return self.holdings[symbol]

    def get_sector_weights(self, symbol: str) -> list[SectorWeight]:
        return self.sectors.get(symbol, [])

    def get_metadata(self, symbol: str) -> EtfMetadata:
        return EtfMetadata(
            symbol=symbol,
            as_of_date=AS_OF,
            provider=EtfProvider.DEMO,
            stale=self.stale,
            data_quality=DataQualityStatus.STALE if self.stale else DataQualityStatus.FRESH,
        )


def holding(
    fund: str,
    symbol: str,
    weight: float,
    sector: str | None,
    allocation_type: AllocationType = AllocationType.SECURITY,
) -> EtfHolding:
    return EtfHolding(
        fund_symbol=fund,
        constituent_symbol=symbol,
        weight=weight,
        sector=sector,
        allocation_type=allocation_type,
        as_of_date=AS_OF,
        provider=EtfProvider.DEMO,
        retrieval_time=NOW,
    )


def position(symbol: str, value: float, weight: float) -> Position:
    return Position(
        symbol=symbol,
        quantity=1,
        average_cost=value,
        current_price=value,
        market_value=value,
        realized_pnl=0,
        unrealized_pnl=0,
        weight=weight,
    )


ASSETS = {
    "AAPL": Asset(symbol="AAPL", name="Apple", asset_type=AssetType.EQUITY, sector="Technology"),
    "JNJ": Asset(symbol="JNJ", name="JNJ", asset_type=AssetType.EQUITY, sector="Healthcare"),
    "VOO": Asset(symbol="VOO", name="VOO", asset_type=AssetType.ETF, sector="Diversified"),
    "QQQ": Asset(symbol="QQQ", name="QQQ", asset_type=AssetType.ETF, sector="Diversified"),
}


def test_direct_plus_indirect_and_effective_reconciliation() -> None:
    provider = SyntheticProvider(
        {
            "VOO": [
                holding("VOO", "AAPL", 0.60, "Technology"),
                holding("VOO", "JNJ", 0.40, "Healthcare"),
            ]
        }
    )
    report = EtfExposureService(provider, ASSETS).analyze(
        [position("AAPL", 5_000, 0.5), position("VOO", 5_000, 0.5)],
        total_portfolio_value=10_000,
    )
    apple = next(item for item in report.securities if item.symbol == "AAPL")
    assert apple.direct_value == 5_000
    assert apple.indirect_value == 3_000
    assert apple.effective_value == 8_000
    assert apple.contributing_etfs == {"VOO": 3_000}
    assert sum(item.effective_value for item in report.securities) == pytest.approx(10_000)
    assert sum(item.value for item in report.sectors) == pytest.approx(10_000)


def test_one_direct_stock_and_one_etf_without_lookthrough() -> None:
    report = EtfExposureService(None, ASSETS).analyze(
        [position("AAPL", 4_000, 0.4), position("VOO", 6_000, 0.6)],
        look_through=False,
    )
    assert {item.symbol: item.effective_value for item in report.securities} == {
        "VOO": 6_000,
        "AAPL": 4_000,
    }


def test_duplicate_constituents_are_combined_or_rejected() -> None:
    rows = [holding("VOO", "AAPL", 0.4, "Technology"), holding("VOO", "AAPL", 0.3, "Technology")]
    normalized = normalize_holdings(rows)
    assert next(item for item in normalized if item.constituent_symbol == "AAPL").weight == 0.7
    with pytest.raises(ValueError, match="duplicate ETF constituents"):
        normalize_holdings(rows, duplicate_policy="reject")


def test_cash_and_unreported_allocation_are_explicit() -> None:
    rows = normalize_holdings(
        [
            holding("VOO", "AAPL", 0.7, "Technology"),
            holding("VOO", "CASH", 0.1, "Cash", AllocationType.CASH),
        ]
    )
    assert sum(item.weight for item in rows) == pytest.approx(1.0)
    assert any(item.allocation_type == AllocationType.CASH for item in rows)
    other = next(item for item in rows if item.allocation_type == AllocationType.OTHER)
    assert other.weight == pytest.approx(0.2)
    assert other.data_quality == DataQualityStatus.INCOMPLETE


def test_weights_above_tolerance_are_rejected() -> None:
    with pytest.raises(ValueError, match="above the allowed"):
        normalize_holdings(
            [holding("VOO", "AAPL", 0.7, "Technology"), holding("VOO", "JNJ", 0.4, "Healthcare")]
        )


def test_missing_constituent_sector_uses_etf_sector_allocation() -> None:
    provider = SyntheticProvider(
        {"VOO": [holding("VOO", "AAPL", 1.0, None)]},
        {
            "VOO": [
                SectorWeight(
                    fund_symbol="VOO",
                    sector="Technology",
                    weight=0.75,
                    as_of_date=AS_OF,
                    provider=EtfProvider.DEMO,
                ),
                SectorWeight(
                    fund_symbol="VOO",
                    sector="Healthcare",
                    weight=0.25,
                    as_of_date=AS_OF,
                    provider=EtfProvider.DEMO,
                ),
            ]
        },
    )
    report = EtfExposureService(provider, ASSETS).analyze([position("VOO", 10_000, 1.0)])
    assert sum(item.value for item in report.sectors) == 10_000
    assert all(
        SectorExposureMethod.ETF_SECTOR_ALLOCATION in item.methods for item in report.sectors
    )


def test_weighted_overlap_hhi_and_effective_number() -> None:
    voo = [holding("VOO", "AAPL", 0.6, "Technology"), holding("VOO", "JNJ", 0.4, "Healthcare")]
    qqq = [holding("QQQ", "AAPL", 0.3, "Technology"), holding("QQQ", "MSFT", 0.7, "Technology")]
    overlap = calculate_etf_overlap("VOO", "QQQ", voo, qqq)
    assert overlap.shared_constituents == ["AAPL"]
    assert overlap.weighted_overlap == pytest.approx(0.3)
    assert overlap.sector_overlap == pytest.approx(0.6)

    provider = SyntheticProvider(
        {
            "VOO": [
                holding("VOO", "AAPL", 0.5, "Technology"),
                holding("VOO", "JNJ", 0.5, "Healthcare"),
            ]
        }
    )
    report = EtfExposureService(provider, ASSETS).analyze([position("VOO", 10_000, 1.0)])
    assert report.concentration is not None
    assert report.concentration.hhi == pytest.approx(0.5)
    assert report.concentration.effective_number_of_holdings == pytest.approx(2.0)


def test_stale_data_and_csv_fallback(tmp_path) -> None:
    old = (date.today() - timedelta(days=100)).isoformat()
    (tmp_path / "VOO.csv").write_text(
        "constituent_symbol,weight,sector,as_of_date\nAAPL,100%,Technology," + old + "\n",
        encoding="utf-8",
    )
    csv_provider = CsvEtfCompositionProvider(tmp_path, stale_after_days=45)

    class MissingProvider:
        name = "missing"

        def get_holdings(self, symbol: str) -> list[EtfHolding]:
            raise EtfCompositionNotFoundError(symbol)

        get_sector_weights = get_holdings
        get_metadata = get_holdings

    provider = FallbackEtfCompositionProvider(MissingProvider(), csv_provider)
    rows = provider.get_holdings("VOO")
    metadata = provider.get_metadata("VOO")
    assert rows[0].data_quality == DataQualityStatus.STALE
    assert metadata.stale is True
    assert metadata.fallback_used is True


def test_alpha_vantage_etf_adapter_normalizes_profile() -> None:
    class Client:
        def get_json(self, url: str, params: dict[str, str]) -> HttpResponse:
            assert params["function"] == "ETF_PROFILE"
            return HttpResponse(
                200,
                {},
                {
                    "name": "Synthetic Fund",
                    "net_assets": "1000000",
                    "net_expense_ratio": "0.20%",
                    "as_of_date": AS_OF.isoformat(),
                    "holdings": [
                        {"symbol": "AAPL", "description": "Apple", "weight": "60%"},
                        {"symbol": "JNJ", "description": "JNJ", "weight": "40%"},
                    ],
                    "sectors": [
                        {"sector": "Technology", "weight": "60%"},
                        {"sector": "Healthcare", "weight": "40%"},
                    ],
                },
            )

    provider = AlphaVantageEtfCompositionProvider("secret", http_client=Client())
    assert sum(item.weight for item in provider.get_holdings("VOO")) == 1.0
    assert provider.get_sector_weights("VOO")[0].sector == "Technology"
    assert provider.get_metadata("VOO").expense_ratio == pytest.approx(0.002)


def test_expired_cache_falls_back_to_labeled_stale_data(tmp_path) -> None:
    class Provider(SyntheticProvider):
        name = "demo"

        def __init__(self) -> None:
            super().__init__({"VOO": [holding("VOO", "AAPL", 1.0, "Technology")]})
            self.fail = False

        def get_holdings(self, symbol: str) -> list[EtfHolding]:
            if self.fail:
                raise EtfCompositionNotFoundError(symbol)
            return super().get_holdings(symbol)

    raw = Provider()
    provider = CachedEtfCompositionProvider(
        raw,
        EtfCompositionCache(tmp_path),
        ttl_hours=-1,
        allow_stale=True,
    )
    provider.get_holdings("VOO")
    raw.fail = True
    assert provider.get_metadata("VOO").stale is True
    assert provider.get_holdings("VOO")[0].data_quality == DataQualityStatus.STALE
