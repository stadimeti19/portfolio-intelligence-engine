from __future__ import annotations

import math
from collections.abc import Callable

from portfolio_intelligence import _engine
from portfolio_intelligence.domain.assets import Asset
from portfolio_intelligence.domain.portfolios import PortfolioSnapshot
from portfolio_intelligence.domain.positions import Position
from portfolio_intelligence.domain.reports import (
    AnalysisReport,
    BenchmarkComparison,
    PerformanceReport,
    RiskReport,
    SummaryReport,
)
from portfolio_intelligence.domain.transactions import Transaction
from portfolio_intelligence.providers.market_data.base import MarketDataProvider
from portfolio_intelligence.services.attribution_service import AttributionService
from portfolio_intelligence.services.portfolio_service import PortfolioService
from portfolio_intelligence.services.risk_service import RiskService


class AnalyticsService:
    def __init__(
        self,
        market_data: MarketDataProvider,
        assets: dict[str, Asset],
        position_concentration_threshold: float = 0.25,
        sector_concentration_threshold: float = 0.50,
    ) -> None:
        self.market_data = market_data
        self.assets = assets
        self.portfolio_service = PortfolioService(market_data)
        self.risk_service = RiskService()
        self.attribution_service = AttributionService()
        self.position_concentration_threshold = position_concentration_threshold
        self.sector_concentration_threshold = sector_concentration_threshold

    def analyze(
        self,
        transactions: list[Transaction],
        benchmark: str = "SPY",
        confidence_level: float = 0.95,
    ) -> AnalysisReport:
        holdings, current = self.portfolio_service.current_positions(transactions)
        snapshots = self.portfolio_service.history(transactions, current.date)
        portfolio_returns = _time_weighted_returns(snapshots)
        benchmark_returns = self._benchmark_returns(benchmark, snapshots)
        aligned_portfolio, aligned_benchmark = _align_lengths(portfolio_returns, benchmark_returns)
        values = [snapshot.total_portfolio_value for snapshot in snapshots]
        asset_returns = self._asset_returns([position.symbol for position in holdings], snapshots)

        cumulative = _engine.cumulative_return(portfolio_returns) if portfolio_returns else 0.0
        benchmark_cumulative = (
            _engine.cumulative_return(aligned_benchmark) if aligned_benchmark else 0.0
        )
        annualized = _optional(lambda: _engine.annualized_return(portfolio_returns))
        volatility = _optional(lambda: _engine.annualized_volatility(portfolio_returns))
        sharpe = _optional(lambda: _engine.sharpe_ratio(portfolio_returns))
        sortino = _optional(lambda: _engine.sortino_ratio(portfolio_returns))
        drawdown = _engine.maximum_drawdown(values).drawdown if values else 0.0
        beta_value = _optional(lambda: _engine.beta(aligned_portfolio, aligned_benchmark))
        var_value = _optional(lambda: _engine.historical_var(portfolio_returns, confidence_level))
        es_value = _optional(
            lambda: _engine.expected_shortfall(portfolio_returns, confidence_level)
        )
        corr_value = _optional(
            lambda: _engine.correlation_matrix([aligned_portfolio, aligned_benchmark])[0][1]
        )
        tracking_error = _optional(
            lambda: _engine.annualized_volatility(
                [p - b for p, b in zip(aligned_portfolio, aligned_benchmark, strict=True)]
            )
        )
        invested_snapshots = [snapshot for snapshot in snapshots if snapshot.position_values]
        attribution = (
            self.attribution_service.contribution(invested_snapshots[0], invested_snapshots[-1])
            if len(invested_snapshots) >= 2
            else []
        )
        risk_contrib = self.risk_service.risk_contribution(holdings, asset_returns)
        exposure = self._exposure(holdings)
        correlations = self._correlations(asset_returns)
        warnings = self.risk_service.concentration_warnings(
            holdings,
            self.assets,
            self.position_concentration_threshold,
            self.sector_concentration_threshold,
        )

        return AnalysisReport(
            summary=SummaryReport(
                total_value=current.total_portfolio_value,
                cash=current.cash_balance,
                cost_basis=current.total_cost_basis,
                realized_pnl=current.realized_pnl,
                unrealized_pnl=current.unrealized_pnl,
                data_date=current.date,
                benchmark=benchmark,
            ),
            holdings=holdings,
            snapshots=snapshots,
            performance=PerformanceReport(
                cumulative_return=cumulative,
                annualized_return=annualized,
                benchmark_return=benchmark_cumulative,
                relative_return=cumulative - benchmark_cumulative,
                sharpe=sharpe,
                sortino=sortino,
                maximum_drawdown=drawdown,
                top_contributors=attribution[:5],
            ),
            risk=RiskReport(
                annualized_volatility=volatility,
                beta=beta_value,
                historical_var=var_value,
                expected_shortfall=es_value,
                risk_contribution=risk_contrib,
                concentration_warnings=warnings,
            ),
            benchmark_comparison=BenchmarkComparison(
                benchmark=benchmark,
                portfolio_return=cumulative,
                benchmark_return=benchmark_cumulative,
                relative_return=cumulative - benchmark_cumulative,
                beta=beta_value,
                correlation=corr_value,
                tracking_difference=cumulative - benchmark_cumulative,
                tracking_error=tracking_error,
            ),
            exposure=exposure,
            correlations=correlations,
            data_freshness={
                "portfolio_source": "csv/demo",
                "market_data_provider": "csv/demo",
                "data_date": current.date.isoformat(),
                "synthetic": True,
                "fallback_used": False,
            },
            limitations=[
                "Demo data is synthetic and not investment advice.",
                "Attribution is approximate when the period contains cash flows or trades.",
                "Historical VaR is a quantile of observed daily returns, "
                "not a maximum-loss estimate.",
            ],
        )

    def _benchmark_returns(self, benchmark: str, snapshots: list[PortfolioSnapshot]) -> list[float]:
        if len(snapshots) < 2:
            return []
        bars = self.market_data.get_daily_prices(benchmark, snapshots[0].date, snapshots[-1].date)
        prices_by_date = {bar.trading_date: bar.adjusted_close for bar in bars}
        prices = [
            prices_by_date[snapshot.date]
            for snapshot in snapshots
            if snapshot.date in prices_by_date
        ]
        return _engine.calculate_returns(prices)

    def _asset_returns(
        self, symbols: list[str], snapshots: list[PortfolioSnapshot]
    ) -> dict[str, list[float]]:
        if len(snapshots) < 2:
            return {}
        start, end = snapshots[0].date, snapshots[-1].date
        output: dict[str, list[float]] = {}
        for symbol in symbols:
            bars = self.market_data.get_daily_prices(symbol, start, end)
            if len(bars) >= 2:
                output[symbol] = _engine.calculate_returns([bar.adjusted_close for bar in bars])
        return output

    def _exposure(self, holdings: list[Position]) -> dict[str, dict[str, float]]:
        position = {holding.symbol: holding.weight for holding in holdings}
        sector: dict[str, float] = {}
        asset_type: dict[str, float] = {}
        for holding in holdings:
            asset = self.assets.get(holding.symbol)
            sector_name = asset.sector if asset else "Unknown"
            type_name = asset.asset_type.value if asset else "Unknown"
            sector[sector_name] = sector.get(sector_name, 0.0) + holding.weight
            asset_type[type_name] = asset_type.get(type_name, 0.0) + holding.weight
        return {"positions": position, "sectors": sector, "asset_types": asset_type}

    def _correlations(self, asset_returns: dict[str, list[float]]) -> dict[str, dict[str, float]]:
        symbols = sorted(asset_returns)
        if len(symbols) < 2:
            return {}
        observations = min(len(asset_returns[symbol]) for symbol in symbols)
        matrix = _engine.correlation_matrix(
            [asset_returns[symbol][-observations:] for symbol in symbols]
        )
        return {
            symbol: {symbols[j]: matrix[i][j] for j in range(len(symbols))}
            for i, symbol in enumerate(symbols)
        }


def _time_weighted_returns(snapshots: list[PortfolioSnapshot]) -> list[float]:
    returns: list[float] = []
    for previous, current in zip(snapshots, snapshots[1:], strict=False):
        if previous.total_portfolio_value <= 0:
            continue
        adjusted_value = current.total_portfolio_value - current.external_cash_flow
        returns.append((adjusted_value / previous.total_portfolio_value) - 1.0)
    return [value for value in returns if math.isfinite(value)]


def _align_lengths(left: list[float], right: list[float]) -> tuple[list[float], list[float]]:
    size = min(len(left), len(right))
    return left[-size:], right[-size:]


def _optional(fn: Callable[[], float]) -> float | None:
    try:
        return float(fn())
    except (ValueError, ZeroDivisionError):
        return None
