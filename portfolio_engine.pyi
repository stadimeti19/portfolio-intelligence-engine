from __future__ import annotations

class DrawdownResult:
    drawdown: float
    peak_index: int
    trough_index: int
    recovery_index: int
    drawdown_duration: int
    recovery_duration: int

class RiskContributionResult:
    portfolio_variance: float
    portfolio_volatility: float
    marginal_contribution: list[float]
    component_contribution: list[float]
    percent_contribution: list[float]

class ScenarioPositionImpact:
    symbol: str
    starting_value: float
    shock: float
    pnl: float
    ending_value: float

class ScenarioResult:
    starting_value: float
    ending_value: float
    pnl: float
    percent_pnl: float
    impacts: list[ScenarioPositionImpact]

def calculate_returns(prices: list[float]) -> list[float]: ...
def cumulative_return(returns: list[float]) -> float: ...
def annualized_return(returns: list[float], periods_per_year: float = 252.0) -> float: ...
def annualized_volatility(returns: list[float], periods_per_year: float = 252.0) -> float: ...
def sharpe_ratio(
    returns: list[float], risk_free_rate: float = 0.0, periods_per_year: float = 252.0
) -> float: ...
def sortino_ratio(
    returns: list[float], risk_free_rate: float = 0.0, periods_per_year: float = 252.0
) -> float: ...
def maximum_drawdown(values: list[float]) -> DrawdownResult: ...
def beta(asset_returns: list[float], benchmark_returns: list[float]) -> float: ...
def historical_var(returns: list[float], confidence_level: float) -> float: ...
def expected_shortfall(returns: list[float], confidence_level: float) -> float: ...
def covariance_matrix(returns: list[list[float]]) -> list[list[float]]: ...
def correlation_matrix(returns: list[list[float]]) -> list[list[float]]: ...
def risk_contributions(
    weights: list[float], covariance: list[list[float]]
) -> RiskContributionResult: ...

