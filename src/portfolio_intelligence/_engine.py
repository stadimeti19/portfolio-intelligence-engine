from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_cpp: Any
try:
    import portfolio_engine as portfolio_engine_module

    _cpp = portfolio_engine_module
except Exception:  # pragma: no cover - used only before the extension is built
    _cpp = None


@dataclass(frozen=True)
class DrawdownResult:
    drawdown: float
    peak_index: int
    trough_index: int
    recovery_index: int
    drawdown_duration: int
    recovery_duration: int


@dataclass(frozen=True)
class RiskContributionResult:
    portfolio_variance: float
    portfolio_volatility: float
    marginal_contribution: list[float]
    component_contribution: list[float]
    percent_contribution: list[float]


def _finite(values: Sequence[float], name: str) -> None:
    if any(not math.isfinite(v) for v in values):
        raise ValueError(f"{name} contains NaN or infinite values")


def calculate_returns(prices: Sequence[float]) -> list[float]:
    if _cpp is not None:
        return list(_cpp.calculate_returns(list(prices)))
    _finite(prices, "prices")
    returns: list[float] = []
    for previous, current in zip(prices, prices[1:], strict=False):
        if previous <= 0:
            raise ValueError("prices must be positive to calculate returns")
        returns.append((current / previous) - 1.0)
    return returns


def cumulative_return(returns: Sequence[float]) -> float:
    if _cpp is not None:
        return float(_cpp.cumulative_return(list(returns)))
    _finite(returns, "returns")
    growth = 1.0
    for value in returns:
        growth *= 1.0 + value
    return growth - 1.0


def annualized_return(returns: Sequence[float], periods_per_year: float = 252.0) -> float:
    if _cpp is not None:
        return float(_cpp.annualized_return(list(returns), periods_per_year))
    if len(returns) < 2:
        raise ValueError("annualized_return requires at least two return observations")
    cumulative = cumulative_return(returns)
    return float((1.0 + cumulative) ** (periods_per_year / len(returns)) - 1.0)


def annualized_volatility(returns: Sequence[float], periods_per_year: float = 252.0) -> float:
    if _cpp is not None:
        return float(_cpp.annualized_volatility(list(returns), periods_per_year))
    if len(returns) < 2:
        raise ValueError("annualized_volatility requires at least two return observations")
    avg = sum(returns) / len(returns)
    variance = sum((value - avg) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(periods_per_year)


def sharpe_ratio(
    returns: Sequence[float], risk_free_rate: float = 0.0, periods_per_year: float = 252.0
) -> float:
    if _cpp is not None:
        return float(_cpp.sharpe_ratio(list(returns), risk_free_rate, periods_per_year))
    excess = [value - (risk_free_rate / periods_per_year) for value in returns]
    vol = annualized_volatility(excess, periods_per_year)
    if vol == 0:
        raise ValueError("sharpe_ratio is undefined for zero volatility")
    return (sum(excess) / len(excess) * periods_per_year) / vol


def sortino_ratio(
    returns: Sequence[float], risk_free_rate: float = 0.0, periods_per_year: float = 252.0
) -> float:
    if _cpp is not None:
        return float(_cpp.sortino_ratio(list(returns), risk_free_rate, periods_per_year))
    target = risk_free_rate / periods_per_year
    downside = [min(0.0, value - target) for value in returns]
    downside_dev = math.sqrt(sum(value * value for value in downside) / len(returns))
    if downside_dev == 0:
        raise ValueError("sortino_ratio is undefined for zero downside deviation")
    return ((sum(value - target for value in returns) / len(returns)) / downside_dev) * math.sqrt(
        periods_per_year
    )


def maximum_drawdown(values: Sequence[float]) -> DrawdownResult:
    if _cpp is not None:
        result = _cpp.maximum_drawdown(list(values))
        return DrawdownResult(
            result.drawdown,
            result.peak_index,
            result.trough_index,
            result.recovery_index,
            result.drawdown_duration,
            result.recovery_duration,
        )
    if not values:
        raise ValueError("maximum_drawdown requires at least one observation")
    peak = best_peak = trough = 0
    max_drawdown = 0.0
    for index, value in enumerate(values):
        if value <= 0:
            raise ValueError("portfolio values must be positive for drawdown")
        if value > values[peak]:
            peak = index
        drawdown = (value / values[peak]) - 1.0
        if drawdown < max_drawdown:
            max_drawdown = drawdown
            best_peak = peak
            trough = index
    recovery_index = -1
    for index in range(trough + 1, len(values)):
        if max_drawdown < 0 and values[index] >= values[best_peak]:
            recovery_index = index
            break
    return DrawdownResult(
        max_drawdown,
        best_peak,
        trough,
        recovery_index,
        max(0, trough - best_peak),
        recovery_index - trough if recovery_index >= 0 else -1,
    )


def beta(asset_returns: Sequence[float], benchmark_returns: Sequence[float]) -> float:
    if _cpp is not None:
        return float(_cpp.beta(list(asset_returns), list(benchmark_returns)))
    if len(asset_returns) != len(benchmark_returns) or len(asset_returns) < 2:
        raise ValueError("beta inputs must have the same length and at least two observations")
    asset_avg = sum(asset_returns) / len(asset_returns)
    bench_avg = sum(benchmark_returns) / len(benchmark_returns)
    cov = sum(
        (a - asset_avg) * (b - bench_avg)
        for a, b in zip(asset_returns, benchmark_returns, strict=True)
    ) / (len(asset_returns) - 1)
    var = sum((b - bench_avg) ** 2 for b in benchmark_returns) / (len(benchmark_returns) - 1)
    if var == 0:
        raise ValueError("beta is undefined for zero benchmark variance")
    return cov / var


def historical_var(returns: Sequence[float], confidence_level: float) -> float:
    if _cpp is not None:
        return float(_cpp.historical_var(list(returns), confidence_level))
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be between 0 and 1")
    losses = sorted(-value for value in returns)
    index = max(0, min(len(losses) - 1, math.ceil(confidence_level * len(losses)) - 1))
    return losses[index]


def expected_shortfall(returns: Sequence[float], confidence_level: float) -> float:
    if _cpp is not None:
        return float(_cpp.expected_shortfall(list(returns), confidence_level))
    var = historical_var(returns, confidence_level)
    tail = [-value for value in returns if -value >= var - 1e-12]
    return sum(tail) / len(tail)


def covariance_matrix(returns: Sequence[Sequence[float]]) -> list[list[float]]:
    if _cpp is not None:
        return [list(row) for row in _cpp.covariance_matrix([list(row) for row in returns])]
    rows = [list(row) for row in returns]
    if not rows or len(rows[0]) < 2:
        raise ValueError("covariance_matrix requires observations")
    out = [[0.0 for _ in rows] for _ in rows]
    for i, left in enumerate(rows):
        for j, right in enumerate(rows):
            l_avg = sum(left) / len(left)
            r_avg = sum(right) / len(right)
            out[i][j] = sum((a - l_avg) * (b - r_avg) for a, b in zip(left, right, strict=True)) / (
                len(left) - 1
            )
    return out


def correlation_matrix(returns: Sequence[Sequence[float]]) -> list[list[float]]:
    if _cpp is not None:
        return [list(row) for row in _cpp.correlation_matrix([list(row) for row in returns])]
    cov = covariance_matrix(returns)
    stddevs = [math.sqrt(max(0.0, cov[i][i])) for i in range(len(cov))]
    return [
        [
            0.0 if stddevs[i] == 0 or stddevs[j] == 0 else cov[i][j] / (stddevs[i] * stddevs[j])
            for j in range(len(cov))
        ]
        for i in range(len(cov))
    ]


def risk_contributions(
    weights: Sequence[float], covariance: Sequence[Sequence[float]]
) -> RiskContributionResult:
    if _cpp is not None:
        result = _cpp.risk_contributions(list(weights), [list(row) for row in covariance])
        return RiskContributionResult(
            result.portfolio_variance,
            result.portfolio_volatility,
            list(result.marginal_contribution),
            list(result.component_contribution),
            list(result.percent_contribution),
        )
    sigma_w = [sum(row[j] * weights[j] for j in range(len(weights))) for row in covariance]
    variance = sum(weights[i] * sigma_w[i] for i in range(len(weights)))
    volatility = math.sqrt(max(0.0, variance))
    marginal = [value / volatility if volatility else 0.0 for value in sigma_w]
    component = [weights[i] * marginal[i] for i in range(len(weights))]
    percent = [value / volatility if volatility else 0.0 for value in component]
    return RiskContributionResult(variance, volatility, marginal, component, percent)
