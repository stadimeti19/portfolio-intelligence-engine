from __future__ import annotations

import numpy as np
import pytest

portfolio_engine = pytest.importorskip("portfolio_engine")
if not hasattr(portfolio_engine, "PortfolioAnalyticsEngine"):
    pytest.skip("stateful native engine is not built", allow_module_level=True)


def _history() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    timestamps = np.array([1, 2, 3], dtype=np.int64)
    prices = np.array([[100.0, 50.0], [110.0, 50.0], [99.0, 60.0]], dtype=np.float64)
    quantities = np.array([[1.0, 2.0], [1.0, 2.0], [1.0, 2.0]], dtype=np.float64)
    cash = np.array([50.0, 150.0, 150.0], dtype=np.float64)
    flows = np.array([0.0, 100.0, 0.0], dtype=np.float64)
    return timestamps, prices, quantities, cash, flows


def test_native_valuation_matches_independent_numpy_reference() -> None:
    timestamps, prices, quantities, cash, flows = _history()
    result = portfolio_engine.value_history(timestamps, prices, quantities, cash, flows)
    position_values = prices * quantities
    expected_totals = position_values.sum(axis=1) + cash
    expected_returns = (expected_totals[1:] - flows[1:]) / expected_totals[:-1] - 1.0

    np.testing.assert_allclose(result.position_values, position_values)
    np.testing.assert_allclose(result.total_values, expected_totals)
    np.testing.assert_allclose(result.returns, expected_returns)
    np.testing.assert_allclose(result.weights, position_values / expected_totals[:, None])


def test_stateful_engine_updates_and_risk_snapshot() -> None:
    timestamps, prices, quantities, cash, flows = _history()
    config = portfolio_engine.EngineConfig(annualization_factor=252.0, confidence_level=0.95)
    engine = portfolio_engine.PortfolioAnalyticsEngine(config)
    engine.load_history(["A", "B"], timestamps, prices, quantities, cash, flows)

    assert engine.snapshot().total_value == pytest.approx(369.0)
    assert engine.calculate_risk().observations == 2
    engine.apply_price_update(0, 4, 101.0)
    engine.apply_position_update(1, 4, 1.0)
    assert engine.snapshot().total_value == pytest.approx(431.0)
    with pytest.raises(ValueError, match="duplicate"):
        engine.apply_price_update(0, 4, 102.0)
    engine.apply_cash_update(5, 25.0)
    assert engine.snapshot().total_value == pytest.approx(456.0)


def test_covariance_estimators_match_numpy_and_return_diagnostics() -> None:
    returns = np.array(
        [[0.01, 0.02, 0.03, 0.04], [0.02, 0.04, 0.06, 0.08], [0.04, 0.03, 0.02, 0.01]],
        dtype=np.float64,
    )
    sample = portfolio_engine.estimate_covariance(returns)
    np.testing.assert_allclose(sample.covariance, np.cov(returns, ddof=1), atol=1e-14)
    assert sample.diagnostics.symmetric
    assert sample.diagnostics.positive_semidefinite
    assert sample.diagnostics.spectral_diagnostics_exact

    request = portfolio_engine.CovarianceRequest(
        method=portfolio_engine.CovarianceMethod.SHRINKAGE, shrinkage_intensity=0.5
    )
    shrinkage = portfolio_engine.estimate_covariance(returns, request)
    expected = np.cov(returns, ddof=1)
    expected[~np.eye(expected.shape[0], dtype=bool)] *= 0.5
    np.testing.assert_allclose(shrinkage.covariance, expected, atol=1e-14)


def test_simulation_is_thread_count_reproducible() -> None:
    weights = np.array([0.6, 0.4], dtype=np.float64)
    returns = np.array(
        [[0.01, -0.02, 0.015, 0.005], [0.005, -0.01, 0.01, 0.002]], dtype=np.float64
    )
    covariance = np.array([[0.0004, 0.0001], [0.0001, 0.0002]], dtype=np.float64)
    single_config = portfolio_engine.SimulationConfig(
        paths=4_096, horizon_days=5, seed=1234, thread_count=1
    )
    parallel_config = portfolio_engine.SimulationConfig(
        paths=4_096, horizon_days=5, seed=1234, thread_count=4
    )
    single = portfolio_engine.simulate(weights, returns, covariance, single_config)
    parallel = portfolio_engine.simulate(weights, returns, covariance, parallel_config)

    np.testing.assert_array_equal(single.path_returns, parallel.path_returns)
    assert single.value_at_risk == parallel.value_at_risk
    assert single.expected_shortfall >= single.value_at_risk


def test_numpy_boundary_rejects_implicit_dtype_or_layout_conversions() -> None:
    timestamps, prices, quantities, cash, flows = _history()
    with pytest.raises(TypeError):
        portfolio_engine.value_history(
            timestamps, prices.astype(np.float32), quantities, cash, flows
        )
    with pytest.raises(TypeError):
        portfolio_engine.value_history(timestamps, prices[:, ::-1], quantities, cash, flows)
