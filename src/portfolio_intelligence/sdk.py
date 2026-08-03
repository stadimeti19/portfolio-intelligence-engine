from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from portfolio_intelligence.domain.portfolios import PortfolioSnapshot
from portfolio_intelligence.domain.positions import Position
from portfolio_intelligence.domain.reports import AnalysisReport
from portfolio_intelligence.domain.scenarios import ScenarioDefinition, ScenarioResult
from portfolio_intelligence.domain.transactions import Transaction
from portfolio_intelligence.providers.etf.base import EtfCompositionProvider
from portfolio_intelligence.providers.etf.demo import DemoEtfCompositionProvider
from portfolio_intelligence.providers.market_data.base import MarketDataProvider
from portfolio_intelligence.providers.market_data.demo import DEMO_ASSETS, DemoMarketDataProvider
from portfolio_intelligence.providers.portfolio.base import PortfolioSource
from portfolio_intelligence.providers.portfolio.csv_source import CsvPortfolioSource
from portfolio_intelligence.providers.portfolio.demo import DemoPortfolioSource
from portfolio_intelligence.services.analytics_service import AnalyticsService
from portfolio_intelligence.services.portfolio_service import PortfolioService
from portfolio_intelligence.services.scenario_service import ScenarioService


class PortfolioAnalyzer:
    def __init__(
        self,
        portfolio_source: PortfolioSource,
        market_data_provider: MarketDataProvider | None = None,
        scenario_path: str | Path | None = None,
        etf_composition_provider: EtfCompositionProvider | None = None,
        etf_symbols: set[str] | None = None,
        position_concentration_threshold: float = 0.25,
        sector_concentration_threshold: float = 0.50,
        overlap_warning_threshold: float = 0.40,
    ) -> None:
        self.portfolio_source = portfolio_source
        self.market_data_provider = market_data_provider or DemoMarketDataProvider()
        self.etf_composition_provider = etf_composition_provider
        self.etf_symbols = etf_symbols
        self.position_concentration_threshold = position_concentration_threshold
        self.sector_concentration_threshold = sector_concentration_threshold
        self.overlap_warning_threshold = overlap_warning_threshold
        self.assets = DEMO_ASSETS
        self.scenario_path = (
            Path(scenario_path)
            if scenario_path is not None
            else Path(str(files("portfolio_intelligence.data").joinpath("scenarios.example.yaml")))
        )
        self._transactions: list[Transaction] | None = None

    @classmethod
    def demo(cls) -> PortfolioAnalyzer:
        return cls(
            DemoPortfolioSource(),
            DemoMarketDataProvider(),
            etf_composition_provider=DemoEtfCompositionProvider(),
        )

    @classmethod
    def from_csv(cls, path: str | Path) -> PortfolioAnalyzer:
        return cls(CsvPortfolioSource(path), DemoMarketDataProvider())

    @property
    def transactions(self) -> list[Transaction]:
        if self._transactions is None:
            self._transactions = self.portfolio_source.load_transactions()
        return self._transactions

    def analyze(self, benchmark: str = "SPY", confidence_level: float = 0.95) -> AnalysisReport:
        service = AnalyticsService(
            self.market_data_provider,
            self.assets,
            position_concentration_threshold=self.position_concentration_threshold,
            sector_concentration_threshold=self.sector_concentration_threshold,
            etf_composition=self.etf_composition_provider,
            etf_symbols=self.etf_symbols,
            overlap_warning_threshold=self.overlap_warning_threshold,
        )
        return service.analyze(
            self.transactions, benchmark=benchmark, confidence_level=confidence_level
        )

    def holdings(self) -> list[Position]:
        positions, _ = PortfolioService(self.market_data_provider).current_positions(
            self.transactions
        )
        return positions

    def snapshots(self) -> list[PortfolioSnapshot]:
        return PortfolioService(self.market_data_provider).history(self.transactions)

    def run_scenario(self, name: str) -> ScenarioResult:
        positions, snapshot = PortfolioService(self.market_data_provider).current_positions(
            self.transactions
        )
        service = ScenarioService(self.scenario_path, self.assets)
        return service.run(name, positions, cash=snapshot.cash_balance)

    def list_scenarios(self) -> dict[str, ScenarioDefinition]:
        return ScenarioService(self.scenario_path, self.assets).list_scenarios()
