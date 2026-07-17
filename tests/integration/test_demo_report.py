from __future__ import annotations

from portfolio_intelligence import PortfolioAnalyzer


def test_demo_report_invariants() -> None:
    report = PortfolioAnalyzer.demo().analyze()
    assert report.summary.total_value > 0
    assert report.holdings
    assert report.snapshots
    latest = report.snapshots[-1]
    assert latest.total_portfolio_value == latest.cash_balance + sum(
        latest.position_values.values()
    )
    assert (
        abs(
            sum(position.weight for position in report.holdings)
            - (1 - report.summary.cash / report.summary.total_value)
        )
        < 1e-9
    )
    assert report.performance.maximum_drawdown <= 0
    if report.risk.expected_shortfall is not None and report.risk.historical_var is not None:
        assert report.risk.expected_shortfall >= report.risk.historical_var
    scenario = PortfolioAnalyzer.demo().run_scenario("tech-selloff")
    assert scenario.starting_value > scenario.ending_value
    assert sum(impact.pnl for impact in scenario.impacts) == scenario.pnl
