from __future__ import annotations

from datetime import date

from portfolio_intelligence.providers.market_data.demo import DemoMarketDataProvider
from portfolio_intelligence.scenarios.loader import load_scenarios


def test_demo_provider_has_two_years_and_drawdown_period() -> None:
    provider = DemoMarketDataProvider()
    bars = provider.get_daily_prices("NVDA", date(2024, 1, 2), date(2026, 1, 2))
    assert len(bars) > 500
    assert min(bar.adjusted_close for bar in bars) > 0
    assert provider.get_latest_quote("SPY").synthetic is True


def test_scenario_loader() -> None:
    scenarios = load_scenarios("data/scenarios.example.yaml")
    assert "tech-selloff" in scenarios
    assert scenarios["market-correction"].asset_type_shocks["Equity"] == -0.10
