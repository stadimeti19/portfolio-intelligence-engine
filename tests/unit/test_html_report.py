from __future__ import annotations

from pathlib import Path

import pytest

from portfolio_intelligence import PortfolioAnalyzer
from portfolio_intelligence.domain.reports import ReportSeriesPoint
from portfolio_intelligence.reporting.html import HtmlReportRenderer, ReportRenderingError


@pytest.fixture(scope="module")
def demo_report():
    return PortfolioAnalyzer.demo().analyze()


@pytest.fixture(scope="module")
def rendered_html(demo_report) -> str:
    return HtmlReportRenderer().render(demo_report)


def test_html_generation_contains_required_sections_and_is_self_contained(
    rendered_html: str,
) -> None:
    required = [
        "1. Portfolio Summary",
        "2. Holdings",
        "3. Portfolio Value History",
        "4. Benchmark Comparison",
        "5. Drawdown",
        "6. Return Attribution",
        "7. Position Allocation",
        "8. Sector Allocation",
        "9. Effective ETF Look-Through Exposure",
        "10. Risk Contribution",
        "11. Correlation Heat Map",
        "12. VaR and Expected Shortfall",
        "13. Scenario Results",
        "14. Rebalancing Plan",
        "15. Data Freshness and Provenance",
        "16. Methodology and Limitations",
    ]
    assert rendered_html.startswith("<!doctype html>")
    assert all(section in rendered_html for section in required)
    assert "plotly.js" in rendered_html
    assert '<script src="https://cdn.plot.ly' not in rendered_html


def test_report_values_match_sdk_report(demo_report, rendered_html: str) -> None:
    assert f"${demo_report.summary.total_value:,.2f}" in rendered_html
    assert f"{demo_report.performance.cumulative_return:.2%}" in rendered_html
    assert demo_report.summary.data_date.isoformat() in rendered_html
    assert demo_report.summary.benchmark in rendered_html


def test_demo_and_stale_data_warnings(demo_report, rendered_html: str) -> None:
    assert "Synthetic demo data" in rendered_html
    assert "Demo-data warning" in rendered_html
    stale = demo_report.model_copy(
        update={"data_freshness": {**demo_report.data_freshness, "prices_stale": True}}
    )
    stale_html = HtmlReportRenderer().render(stale)
    assert "One or more data sources are stale." in stale_html


def test_empty_optional_sections_are_handled(demo_report) -> None:
    report = demo_report.model_copy(
        update={
            "etf_exposure": None,
            "correlations": {},
            "scenario_results": [],
            "rebalancing_plan": None,
        }
    )
    html = HtmlReportRenderer().render(report)
    assert "No ETF look-through exposure is available." in html
    assert "Correlation data requires at least two securities." in html
    assert "No scenario was selected" in html
    assert "No rebalancing plan is available" in html


def test_chart_inputs_match_typed_report(demo_report) -> None:
    figures = HtmlReportRenderer().build_figures(demo_report)
    history = figures["portfolio_history"]
    drawdown = figures["drawdown"]
    assert history is not None and drawdown is not None
    assert len(history.data[0].x) == len(demo_report.snapshots)
    assert len(history.data[0].y) == len(demo_report.snapshots)
    assert len(drawdown.data[0].x) == len(demo_report.performance.drawdown_history)


def test_inconsistent_drawdown_input_is_rejected(demo_report) -> None:
    performance = demo_report.performance.model_copy(
        update={
            "drawdown_history": [ReportSeriesPoint(date=demo_report.summary.data_date, value=0)]
        }
    )
    report = demo_report.model_copy(update={"performance": performance})
    with pytest.raises(ReportRenderingError, match="drawdown history dates"):
        HtmlReportRenderer().build_figures(report)


def test_template_escapes_untrusted_text(demo_report) -> None:
    malicious = "</script><script>alert('x')</script>"
    exposure = {**demo_report.exposure, "positions": {malicious: 1.0}}
    report = demo_report.model_copy(
        update={"limitations": ["<script>alert('x')</script>"], "exposure": exposure}
    )
    html = HtmlReportRenderer().render(report)
    assert "&lt;script&gt;alert" in html
    assert "<script>alert('x')</script>" not in html
    assert malicious not in html
    assert "\\u003c\\u002fscript" in html


def test_output_path_validation(demo_report, tmp_path: Path) -> None:
    renderer = HtmlReportRenderer()
    output = renderer.write(demo_report, tmp_path / "report.html")
    assert output.exists()
    assert output.read_text(encoding="utf-8").startswith("<!doctype html>")
    with pytest.raises(ReportRenderingError, match="must end"):
        renderer.write(demo_report, tmp_path / "report.pdf")
    with pytest.raises(ReportRenderingError, match="must be a file"):
        renderer.write(demo_report, tmp_path)
