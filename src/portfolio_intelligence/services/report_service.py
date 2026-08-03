from __future__ import annotations

from pathlib import Path

from portfolio_intelligence.domain.reports import AnalysisReport
from portfolio_intelligence.reporting.html import HtmlReportRenderer


class ReportService:
    def __init__(self, html_renderer: HtmlReportRenderer | None = None) -> None:
        self.html_renderer = html_renderer or HtmlReportRenderer()

    def to_json(self, report: AnalysisReport) -> str:
        return report.model_dump_json(indent=2)

    def to_markdown(self, report: AnalysisReport) -> str:
        lines = [
            "# Portfolio Intelligence Report",
            "",
            f"Generated: {report.generated_at.isoformat()}",
            f"Methodology version: {report.methodology_version}",
            "",
            "## Summary",
            f"- Total value: ${report.summary.total_value:,.2f}",
            f"- Cash: ${report.summary.cash:,.2f}",
            f"- Unrealized P&L: ${report.summary.unrealized_pnl:,.2f}",
            f"- Benchmark: {report.summary.benchmark}",
            "",
            "## Risk",
            f"- Annualized volatility: {_fmt_pct(report.risk.annualized_volatility)}",
            f"- Beta: {_fmt_num(report.risk.beta)}",
            f"- Historical VaR: {_fmt_pct(report.risk.historical_var)}",
            f"- Expected Shortfall: {_fmt_pct(report.risk.expected_shortfall)}",
            "",
            "## Holdings",
        ]
        for position in report.holdings:
            lines.append(
                f"- {position.symbol}: {position.quantity:.4f} shares, "
                f"${position.market_value:,.2f}, {position.weight:.1%}"
            )
        if report.etf_exposure:
            lines.extend(["", "## Effective Exposure"])
            for security_item in report.etf_exposure.securities:
                if security_item.effective_value <= 0:
                    continue
                contributors = ", ".join(sorted(security_item.contributing_etfs)) or "none"
                lines.append(
                    f"- {security_item.symbol}: direct {security_item.direct_weight:.1%}, "
                    f"indirect {security_item.indirect_weight:.1%}, effective "
                    f"{security_item.effective_weight:.1%}; ETFs: {contributors}"
                )
            lines.extend(["", "## Effective Sectors"])
            for sector_item in report.etf_exposure.sectors:
                methods = ", ".join(method.value for method in sector_item.methods)
                lines.append(f"- {sector_item.sector}: {sector_item.weight:.1%} ({methods})")
            if report.etf_exposure.warnings:
                lines.extend(
                    ["", "## ETF Data and Concentration Warnings"]
                    + [f"- {item}" for item in report.etf_exposure.warnings]
                )
        if report.limitations:
            lines.extend(["", "## Limitations", *[f"- {item}" for item in report.limitations]])
        return "\n".join(lines) + "\n"

    def to_html(self, report: AnalysisReport) -> str:
        return self.html_renderer.render(report)

    def write(self, report: AnalysisReport, output: str | Path, fmt: str = "json") -> Path:
        path = Path(output)
        if fmt == "html":
            return self.html_renderer.write(report, path)
        if fmt not in {"json", "markdown"}:
            raise ValueError("report format must be json, markdown, or html")
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.to_json(report) if fmt == "json" else self.to_markdown(report)
        path.write_text(content, encoding="utf-8")
        return path


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _fmt_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
