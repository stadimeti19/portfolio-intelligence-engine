from __future__ import annotations

from portfolio_intelligence.config.settings import Settings, load_settings
from portfolio_intelligence.dashboard.service import DashboardService
from portfolio_intelligence.domain.assets import AssetType
from portfolio_intelligence.providers.etf.factory import build_etf_composition_provider
from portfolio_intelligence.providers.market_data.demo import DEMO_ASSETS
from portfolio_intelligence.providers.market_data.factory import build_market_data_provider
from portfolio_intelligence.providers.portfolio.base import PortfolioSource
from portfolio_intelligence.providers.portfolio.csv_source import CsvPortfolioSource
from portfolio_intelligence.providers.portfolio.demo import DemoPortfolioSource
from portfolio_intelligence.providers.portfolio.holdings_snapshot import (
    HoldingsSnapshotSource,
    load_holdings_snapshot,
)
from portfolio_intelligence.sdk import PortfolioAnalyzer


def build_dashboard_service() -> DashboardService:
    return DashboardService(build_analyzer)


def build_analyzer(portfolio: str) -> PortfolioAnalyzer:
    if portfolio.lower() == "demo":
        return PortfolioAnalyzer.demo()
    if portfolio.lower() != "configured":
        raise ValueError(f"unknown portfolio: {portfolio}")
    settings = load_settings()
    source = _portfolio_source(settings)
    return PortfolioAnalyzer(
        source,
        build_market_data_provider(settings),
        etf_composition_provider=build_etf_composition_provider(settings),
        etf_symbols=_etf_symbols(settings, source),
        position_concentration_threshold=settings.position_concentration_threshold,
        sector_concentration_threshold=settings.sector_concentration_threshold,
        overlap_warning_threshold=settings.etf_overlap_warning_threshold,
    )


def available_scenarios(portfolio: str) -> list[str]:
    # Scenario definitions are shared by configured and demo analyzers in the current SDK.
    # Reading them does not require constructing live market-data providers.
    return sorted(PortfolioAnalyzer.demo().list_scenarios())


def _portfolio_source(settings: Settings) -> PortfolioSource:
    source = settings.portfolio_source.lower()
    if source == "demo":
        return DemoPortfolioSource()
    if source == "holdings":
        return HoldingsSnapshotSource(
            settings.portfolio_holdings_path,
            source_format=settings.portfolio_holdings_format,
        )
    return CsvPortfolioSource(settings.portfolio_csv_path)


def _etf_symbols(settings: Settings, source: PortfolioSource) -> set[str]:
    symbols = set(settings.etf_symbols)
    transactions = source.load_transactions()
    symbols.update(
        transaction.symbol
        for transaction in transactions
        if transaction.symbol
        and DEMO_ASSETS.get(transaction.symbol)
        and DEMO_ASSETS[transaction.symbol].asset_type == AssetType.ETF
    )
    if settings.portfolio_source.lower() == "holdings":
        result = load_holdings_snapshot(
            settings.portfolio_holdings_path,
            source_format=settings.portfolio_holdings_format,
        )
        symbols.update(
            item.symbol
            for item in result.holdings
            if item.asset_type and "ETF" in item.asset_type.upper()
        )
    return symbols
