from __future__ import annotations

import math

import pytest

from portfolio_intelligence import _engine


def test_returns_and_tail_risk_reference_values() -> None:
    returns = _engine.calculate_returns([100.0, 110.0, 99.0, 108.9])
    assert returns == pytest.approx([0.10, -0.10, 0.10])
    assert _engine.cumulative_return(returns) == pytest.approx(0.089)
    tail = [-0.10, -0.04, 0.01, 0.02, 0.03]
    assert _engine.historical_var(tail, 0.8) == pytest.approx(0.04)
    assert _engine.expected_shortfall(tail, 0.8) >= _engine.historical_var(tail, 0.8)


def test_drawdown_beta_covariance_correlation_and_risk_contribution() -> None:
    drawdown = _engine.maximum_drawdown([100.0, 120.0, 90.0, 95.0, 121.0])
    assert drawdown.drawdown == pytest.approx(-0.25)
    assert drawdown.recovery_index == 4
    assert _engine.beta([0.01, 0.02, -0.01, 0.03], [0.005, 0.01, -0.005, 0.015]) == pytest.approx(
        2.0
    )
    corr = _engine.correlation_matrix(
        [[0.01, 0.02, 0.03, 0.04], [0.02, 0.04, 0.06, 0.08], [0.04, 0.03, 0.02, 0.01]]
    )
    assert corr[0][1] == pytest.approx(1.0)
    assert corr[0][2] == pytest.approx(-1.0)
    result = _engine.risk_contributions([0.6, 0.4], [[0.04, 0.01], [0.01, 0.09]])
    assert sum(result.component_contribution) == pytest.approx(result.portfolio_volatility)
    assert math.isfinite(result.portfolio_variance)
