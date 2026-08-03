from __future__ import annotations

from enum import Enum

import numpy as np
import numpy.typing as npt

Float64Array = npt.NDArray[np.float64]
Int64Array = npt.NDArray[np.int64]

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

class EngineConfig:
    def __init__(
        self, annualization_factor: float = 252.0, confidence_level: float = 0.95
    ) -> None: ...
    annualization_factor: float
    confidence_level: float

class PortfolioSnapshot:
    timestamp: int
    prices: list[float]
    quantities: list[float]
    position_values: list[float]
    weights: list[float]
    cash: float
    invested_value: float
    total_value: float

class RiskSnapshot:
    observations: int
    annualized_volatility: float
    maximum_drawdown: float
    value_at_risk: float
    expected_shortfall: float

class ValuationResult:
    position_values: Float64Array
    weights: Float64Array
    invested_values: Float64Array
    total_values: Float64Array
    returns: Float64Array

class RunningStatistics:
    def __init__(self) -> None: ...
    def add_observation(self, value: float) -> None: ...
    def initialize(self, values: list[float]) -> None: ...
    def reset(self) -> None: ...
    count: int
    mean: float
    sample_variance: float
    sample_standard_deviation: float

class RunningCovariance:
    def __init__(self) -> None: ...
    def add_observation(self, left: float, right: float) -> None: ...
    def initialize(self, left: list[float], right: list[float]) -> None: ...
    def reset(self) -> None: ...
    count: int
    covariance: float
    beta: float

class RollingVolatility:
    def __init__(self, window: int, periods_per_year: float = 252.0) -> None: ...
    def add_observation(self, value: float) -> None: ...
    def initialize(self, values: list[float]) -> None: ...
    count: int
    window: int
    volatility: float

class PortfolioAnalyticsEngine:
    def __init__(self, config: EngineConfig = ...) -> None: ...
    def load_history(
        self,
        symbols: list[str],
        timestamps: Int64Array,
        prices: Float64Array,
        quantities: Float64Array,
        cash_balances: Float64Array,
        external_cash_flows: Float64Array,
    ) -> None: ...
    def apply_price_update(self, asset: int, timestamp: int, price: float) -> None: ...
    def apply_position_update(
        self, asset: int, timestamp: int, quantity_delta: float
    ) -> None: ...
    def apply_cash_update(self, timestamp: int, amount: float) -> None: ...
    def snapshot(self) -> PortfolioSnapshot: ...
    def calculate_risk(self) -> RiskSnapshot: ...
    def run_scenario(self, shocks: list[float]) -> ScenarioResult: ...
    empty: bool
    asset_count: int
    portfolio_returns: list[float]
    value_history: list[float]

class CovarianceMethod(Enum):
    SAMPLE = 0
    EXPONENTIALLY_WEIGHTED = 1
    SHRINKAGE = 2
    DIAGONAL = 3

class CovarianceRequest:
    def __init__(
        self,
        method: CovarianceMethod = CovarianceMethod.SAMPLE,
        decay_factor: float = 0.94,
        shrinkage_intensity: float = 0.10,
    ) -> None: ...
    method: CovarianceMethod
    decay_factor: float
    shrinkage_intensity: float

class CovarianceDiagnostics:
    observations: int
    assets: int
    symmetric: bool
    positive_semidefinite: bool
    spectral_diagnostics_exact: bool
    smallest_eigenvalue: float
    largest_eigenvalue: float
    condition_number: float
    effective_rank: float
    shrinkage_intensity: float

class CovarianceEstimate:
    covariance: Float64Array
    diagnostics: CovarianceDiagnostics

class SimulationMethod(Enum):
    NORMAL = 0
    HISTORICAL_BOOTSTRAP = 1

class SimulationConfig:
    def __init__(
        self,
        paths: int = 10_000,
        horizon_days: int = 1,
        seed: int = 42,
        thread_count: int = 1,
        confidence_level: float = 0.95,
        method: SimulationMethod = SimulationMethod.NORMAL,
    ) -> None: ...
    paths: int
    horizon_days: int
    seed: int
    thread_count: int
    confidence_level: float
    method: SimulationMethod

class SimulationResult:
    path_returns: Float64Array
    value_at_risk: float
    expected_shortfall: float
    minimum: float
    maximum: float
    mean: float
    standard_deviation: float
    paths: int
    horizon_days: int
    seed: int
    thread_count: int
    method: str

def value_history(
    timestamps: Int64Array,
    prices: Float64Array,
    quantities: Float64Array,
    cash_balances: Float64Array,
    external_cash_flows: Float64Array,
) -> ValuationResult: ...
def estimate_covariance(
    return_history: Float64Array, request: CovarianceRequest = ...
) -> CovarianceEstimate: ...
def simulate(
    weights: Float64Array,
    return_history: Float64Array,
    covariance: Float64Array,
    config: SimulationConfig,
) -> SimulationResult: ...

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
def apply_scenario(
    symbols: list[str],
    values: list[float],
    sectors: list[str],
    asset_types: list[str],
    symbol_shocks: dict[str, float],
    sector_shocks: dict[str, float],
    asset_type_shocks: dict[str, float],
) -> ScenarioResult: ...
