from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from portfolio_intelligence import PortfolioAnalyzer
from portfolio_intelligence.dashboard import DashboardRequest, DashboardService, launcher


class FakeAnalyzer:
    def __init__(self, report) -> None:
        self.report = report
        self.transactions: list[str] = ["transaction-v1"]
        self.analyze_calls: list[tuple[str, float]] = []
        self.scenario_calls: list[str] = []
        self.position_concentration_threshold = 0.0
        self.sector_concentration_threshold = 0.0
        self.overlap_warning_threshold = 0.0

    def analyze(self, benchmark: str, confidence_level: float):
        self.analyze_calls.append((benchmark, confidence_level))
        return self.report

    def run_scenario(self, name: str):
        self.scenario_calls.append(name)
        return PortfolioAnalyzer.demo().run_scenario(name)


class FakeRenderer:
    def __init__(self) -> None:
        self.render_calls = 0

    def render(self, report, *, start_date=None, end_date=None) -> str:
        self.render_calls += 1
        return f"<html>{report.summary.total_value}:{start_date}:{end_date}</html>"

    def write(self, report, output, *, start_date=None, end_date=None) -> Path:
        path = Path(output)
        path.write_text(self.render(report, start_date=start_date, end_date=end_date))
        return path


@pytest.fixture
def demo_report():
    return PortfolioAnalyzer.demo().analyze()


def test_dashboard_calls_sdk_service_once_for_cached_request(demo_report) -> None:
    analyzer = FakeAnalyzer(demo_report)
    service = DashboardService(lambda portfolio: analyzer)
    request = DashboardRequest(
        portfolio="demo",
        benchmark="spy",
        confidence_level=0.95,
        position_concentration_threshold=0.15,
        sector_concentration_threshold=0.45,
        overlap_warning_threshold=0.35,
    )
    first = service.analyze(request)
    second = service.analyze(request)
    assert first.cached is False
    assert second.cached is True
    assert first.cache_key == second.cache_key
    assert analyzer.analyze_calls == [("SPY", 0.95)]
    assert analyzer.position_concentration_threshold == 0.15
    assert analyzer.sector_concentration_threshold == 0.45
    assert analyzer.overlap_warning_threshold == 0.35


def test_dashboard_cache_invalidates_on_refresh_input_and_settings(demo_report) -> None:
    analyzer = FakeAnalyzer(demo_report)
    service = DashboardService(lambda portfolio: analyzer)
    request = DashboardRequest(portfolio="demo")
    service.analyze(request)
    service.analyze(request, refresh=True)
    analyzer.transactions.append("transaction-v2")
    service.analyze(request)
    service.analyze(request.model_copy(update={"benchmark": "QQQ"}))
    assert len(analyzer.analyze_calls) == 4


def test_dashboard_cache_invalidates_when_price_file_changes(demo_report, tmp_path: Path) -> None:
    analyzer = FakeAnalyzer(demo_report)
    analyzer.market_data_provider = SimpleNamespace(directory=tmp_path)
    prices = tmp_path / "AAPL.csv"
    prices.write_text("date,close\n2026-01-01,100\n", encoding="utf-8")
    service = DashboardService(lambda portfolio: analyzer)
    request = DashboardRequest(portfolio="demo")
    service.analyze(request)
    prices.write_text("date,close\n2026-01-01,101\n", encoding="utf-8")
    service.analyze(request)
    assert len(analyzer.analyze_calls) == 2


def test_dashboard_scenario_uses_existing_scenario_service(demo_report) -> None:
    analyzer = FakeAnalyzer(demo_report)
    service = DashboardService(lambda portfolio: analyzer)
    result = service.analyze(DashboardRequest(portfolio="demo", scenario="tech-selloff"))
    assert analyzer.scenario_calls == ["tech-selloff"]
    assert result.report.scenario_results[0].name == "tech-selloff"


def test_dashboard_html_export_is_cached(demo_report, tmp_path: Path) -> None:
    analyzer = FakeAnalyzer(demo_report)
    renderer = FakeRenderer()
    service = DashboardService(lambda portfolio: analyzer, html_renderer=renderer)  # type: ignore[arg-type]
    result = service.analyze(
        DashboardRequest(
            portfolio="demo",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )
    )
    assert service.render_html(result) == service.render_html(result)
    assert renderer.render_calls == 1
    output = service.export_html(result, tmp_path / "report.html")
    assert output.exists()


def test_dashboard_rejects_invalid_date_range() -> None:
    with pytest.raises(ValidationError, match="end_date"):
        DashboardRequest(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 1),
        )


def test_dashboard_launcher_uses_streamlit_module(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(launcher.importlib.util, "find_spec", lambda name: object())

    def run(command, check):
        calls.append(command)
        assert check is False
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", run)
    assert launcher.launch_dashboard(port=9999, address="127.0.0.1") == 0
    assert calls[0][1:4] == ["-m", "streamlit", "run"]
    assert "9999" in calls[0]
    assert "127.0.0.1" in calls[0]
