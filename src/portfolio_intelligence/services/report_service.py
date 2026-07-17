from __future__ import annotations

from pathlib import Path

from portfolio_intelligence.domain.reports import AnalysisReport


class ReportService:
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
        if report.limitations:
            lines.extend(["", "## Limitations", *[f"- {item}" for item in report.limitations]])
        return "\n".join(lines) + "\n"

    def write(self, report: AnalysisReport, output: str | Path, fmt: str = "json") -> Path:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.to_json(report) if fmt == "json" else self.to_markdown(report)
        path.write_text(content, encoding="utf-8")
        return path


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _fmt_num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
