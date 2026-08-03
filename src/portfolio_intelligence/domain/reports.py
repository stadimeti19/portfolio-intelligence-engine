from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from portfolio_intelligence.domain.etfs import EtfExposureReport
from portfolio_intelligence.domain.portfolios import PortfolioSnapshot
from portfolio_intelligence.domain.positions import Position
from portfolio_intelligence.domain.scenarios import ScenarioResult


class SummaryReport(BaseModel):
    total_value: float
    cash: float
    cost_basis: float
    realized_pnl: float
    unrealized_pnl: float
    data_date: date
    benchmark: str


class PerformanceReport(BaseModel):
    cumulative_return: float
    annualized_return: float | None
    benchmark_return: float
    relative_return: float
    sharpe: float | None
    sortino: float | None
    maximum_drawdown: float
    drawdown_history: list[ReportSeriesPoint] = Field(default_factory=list)
    top_contributors: list[dict[str, float | str]] = Field(default_factory=list)


class ReportSeriesPoint(BaseModel):
    date: date
    value: float


class RebalancingTrade(BaseModel):
    symbol: str
    action: str
    current_weight: float
    target_weight: float
    trade_value: float


class RebalancingPlan(BaseModel):
    status: str
    trades: list[RebalancingTrade] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RiskReport(BaseModel):
    annualized_volatility: float | None
    beta: float | None
    historical_var: float | None
    expected_shortfall: float | None
    risk_contribution: list[dict[str, float | str]] = Field(default_factory=list)
    concentration_warnings: list[str] = Field(default_factory=list)


class BenchmarkComparison(BaseModel):
    benchmark: str
    portfolio_return: float
    benchmark_return: float
    relative_return: float
    beta: float | None
    correlation: float | None
    tracking_difference: float
    tracking_error: float | None


class AnalysisReport(BaseModel):
    summary: SummaryReport
    holdings: list[Position]
    snapshots: list[PortfolioSnapshot]
    performance: PerformanceReport
    risk: RiskReport
    benchmark_comparison: BenchmarkComparison
    exposure: dict[str, dict[str, float]]
    etf_exposure: EtfExposureReport | None = None
    correlations: dict[str, dict[str, float]]
    scenario_results: list[ScenarioResult] = Field(default_factory=list)
    rebalancing_plan: RebalancingPlan | None = None
    data_freshness: dict[str, str | bool]
    methodology_version: str = "0.1.0"
    limitations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)
