from __future__ import annotations

from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Any

import plotly.graph_objects as go  # type: ignore[import-untyped]
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from portfolio_intelligence.domain.reports import AnalysisReport

_COLORS = ["#2563eb", "#14b8a6", "#f59e0b", "#8b5cf6", "#ef4444", "#64748b"]
_PLOTLY_CONFIG = {"displayModeBar": False, "responsive": True, "displaylogo": False}


class ReportRenderingError(ValueError):
    pass


class HtmlReportRenderer:
    def __init__(self) -> None:
        template_dir = files("portfolio_intelligence").joinpath("reporting/templates")
        self.environment = Environment(
            loader=FileSystemLoader(str(template_dir)),
            autoescape=select_autoescape(("html", "htm", "xml", "j2"), default=True),
        )
        self.environment.filters.update(
            currency=_currency,
            percentage=_percentage,
            number=_number,
            date_value=_date_value,
        )

    def render(
        self,
        report: AnalysisReport,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> str:
        figures = self.build_figures(report, start_date=start_date, end_date=end_date)
        charts: dict[str, Markup | None] = {}
        include_javascript = True
        for name, figure in figures.items():
            if figure is None:
                charts[name] = None
                continue
            html = figure.to_html(
                full_html=False,
                include_plotlyjs="inline" if include_javascript else False,
                config=_PLOTLY_CONFIG,
            )
            include_javascript = False
            charts[name] = Markup(html)
        warnings = _report_warnings(report)
        return self.environment.get_template("portfolio_report.html.j2").render(
            report=report,
            charts=charts,
            warnings=warnings,
            synthetic=_is_synthetic(report),
            generated_date_range=(start_date, end_date),
        )

    def write(
        self,
        report: AnalysisReport,
        output: str | Path,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Path:
        path = _validate_output_path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = self.render(report, start_date=start_date, end_date=end_date)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
        return path

    def build_figures(
        self,
        report: AnalysisReport,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, go.Figure | None]:
        snapshots = [
            item
            for item in report.snapshots
            if (start_date is None or item.date >= start_date)
            and (end_date is None or item.date <= end_date)
        ]
        drawdowns = [
            item
            for item in report.performance.drawdown_history
            if (start_date is None or item.date >= start_date)
            and (end_date is None or item.date <= end_date)
        ]
        if drawdowns and [item.date for item in snapshots] != [item.date for item in drawdowns]:
            raise ReportRenderingError("drawdown history dates must match portfolio snapshot dates")
        return {
            "portfolio_history": _portfolio_history(snapshots),
            "benchmark": _benchmark(report),
            "drawdown": _drawdown(drawdowns),
            "attribution": _attribution(report),
            "positions": _position_allocation(report),
            "sectors": _sector_allocation(report),
            "effective_exposure": _effective_exposure(report),
            "risk_contribution": _risk_contribution(report),
            "correlations": _correlations(report),
            "tail_risk": _tail_risk(report),
            "scenarios": _scenarios(report),
        }


def _portfolio_history(snapshots: list[Any]) -> go.Figure | None:
    if not snapshots:
        return None
    figure = go.Figure(
        go.Scatter(
            x=[item.date for item in snapshots],
            y=[item.total_portfolio_value for item in snapshots],
            mode="lines",
            name="Portfolio value",
            line={"color": _COLORS[0], "width": 2.5},
            hovertemplate="%{x|%Y-%m-%d}<br>$%{y:,.2f}<extra></extra>",
        )
    )
    return _layout(figure, "Portfolio Value History", y_title="Portfolio value", currency=True)


def _benchmark(report: AnalysisReport) -> go.Figure:
    comparison = report.benchmark_comparison
    figure = go.Figure(
        go.Bar(
            x=["Portfolio", comparison.benchmark],
            y=[comparison.portfolio_return, comparison.benchmark_return],
            marker_color=[_COLORS[0], _COLORS[1]],
            text=[comparison.portfolio_return, comparison.benchmark_return],
            texttemplate="%{text:.2%}",
            hovertemplate="%{x}<br>%{y:.2%}<extra></extra>",
        )
    )
    return _layout(figure, "Benchmark Comparison", y_title="Cumulative return", percent=True)


def _drawdown(points: list[Any]) -> go.Figure | None:
    if not points:
        return None
    figure = go.Figure(
        go.Scatter(
            x=[item.date for item in points],
            y=[item.value for item in points],
            fill="tozeroy",
            mode="lines",
            name="Drawdown",
            line={"color": _COLORS[4], "width": 2},
            hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2%}<extra></extra>",
        )
    )
    return _layout(figure, "Portfolio Drawdown", y_title="Drawdown", percent=True)


def _attribution(report: AnalysisReport) -> go.Figure | None:
    rows = report.performance.top_contributors
    if not rows:
        return None
    symbols = [str(row["symbol"]) for row in rows]
    values = [float(row["percentage_point_contribution"]) for row in rows]
    figure = go.Figure(
        go.Bar(
            x=symbols,
            y=values,
            marker_color=[_COLORS[1] if value >= 0 else _COLORS[4] for value in values],
            hovertemplate="%{x}<br>%{y:.2%}<extra></extra>",
        )
    )
    return _layout(figure, "Return Attribution", y_title="Return contribution", percent=True)


def _position_allocation(report: AnalysisReport) -> go.Figure | None:
    values = report.exposure.get("positions", {})
    return _allocation_figure("Position Allocation", values)


def _sector_allocation(report: AnalysisReport) -> go.Figure | None:
    if report.etf_exposure and report.etf_exposure.sectors:
        values = {item.sector: item.weight for item in report.etf_exposure.sectors}
        return _allocation_figure("Effective Sector Allocation", values)
    return _allocation_figure("Sector Allocation", report.exposure.get("sectors", {}))


def _allocation_figure(title: str, values: dict[str, float]) -> go.Figure | None:
    filtered = {name: value for name, value in values.items() if value > 0}
    if not filtered:
        return None
    figure = go.Figure(
        go.Bar(
            x=list(filtered),
            y=list(filtered.values()),
            text=list(filtered.values()),
            texttemplate="%{text:.1%}",
            marker_color=_COLORS[0],
            hovertemplate="%{x}<br>%{y:.2%}<extra></extra>",
        )
    )
    return _layout(figure, title, y_title="Portfolio weight", percent=True)


def _effective_exposure(report: AnalysisReport) -> go.Figure | None:
    if not report.etf_exposure:
        return None
    rows = [item for item in report.etf_exposure.securities if item.effective_weight > 0]
    if not rows:
        return None
    symbols = [item.symbol for item in rows]
    figure = go.Figure()
    for name, values, color in [
        ("Direct", [item.direct_weight for item in rows], _COLORS[0]),
        ("Indirect", [item.indirect_weight for item in rows], _COLORS[1]),
        ("Effective", [item.effective_weight for item in rows], _COLORS[2]),
    ]:
        figure.add_bar(
            name=name,
            x=symbols,
            y=values,
            marker_color=color,
            hovertemplate=f"{name}: %{{y:.2%}}<extra></extra>",
        )
    figure.update_layout(barmode="group")
    return _layout(
        figure,
        "Effective ETF Look-Through Exposure",
        y_title="Portfolio weight",
        percent=True,
    )


def _risk_contribution(report: AnalysisReport) -> go.Figure | None:
    rows = report.risk.risk_contribution
    if not rows:
        return None
    figure = go.Figure(
        go.Bar(
            x=[str(row["symbol"]) for row in rows],
            y=[float(row["percent"]) for row in rows],
            marker_color=_COLORS[3],
            hovertemplate="%{x}<br>%{y:.2%}<extra></extra>",
        )
    )
    return _layout(figure, "Risk Contribution", y_title="Risk contribution", percent=True)


def _correlations(report: AnalysisReport) -> go.Figure | None:
    if not report.correlations:
        return None
    symbols = list(report.correlations)
    matrix = [[report.correlations[left][right] for right in symbols] for left in symbols]
    figure = go.Figure(
        go.Heatmap(
            x=symbols,
            y=symbols,
            z=matrix,
            zmin=-1,
            zmax=1,
            colorscale="RdBu",
            reversescale=True,
            colorbar={"title": "Correlation"},
            hovertemplate="%{y} / %{x}<br>%{z:.2f}<extra></extra>",
        )
    )
    return _layout(figure, "Correlation Heat Map")


def _tail_risk(report: AnalysisReport) -> go.Figure | None:
    available = [
        ("Historical VaR", report.risk.historical_var, _COLORS[2]),
        ("Expected Shortfall", report.risk.expected_shortfall, _COLORS[4]),
    ]
    available = [item for item in available if item[1] is not None]
    if not available:
        return None
    figure = go.Figure(
        go.Bar(
            x=[item[0] for item in available],
            y=[item[1] for item in available],
            marker_color=[item[2] for item in available],
            hovertemplate="%{x}<br>%{y:.2%}<extra></extra>",
        )
    )
    return _layout(figure, "VaR and Expected Shortfall", y_title="One-day loss", percent=True)


def _scenarios(report: AnalysisReport) -> go.Figure | None:
    if not report.scenario_results:
        return None
    figure = go.Figure(
        go.Bar(
            x=[item.name for item in report.scenario_results],
            y=[item.pnl for item in report.scenario_results],
            marker_color=[
                _COLORS[1] if item.pnl >= 0 else _COLORS[4] for item in report.scenario_results
            ],
            hovertemplate="%{x}<br>$%{y:,.2f}<extra></extra>",
        )
    )
    return _layout(figure, "Scenario Results", y_title="Portfolio P&L", currency=True)


def _layout(
    figure: go.Figure,
    title: str,
    *,
    y_title: str | None = None,
    percent: bool = False,
    currency: bool = False,
) -> go.Figure:
    figure.update_layout(
        title={"text": title, "x": 0.02, "xanchor": "left"},
        template="plotly_white",
        font={"family": "Inter, system-ui, sans-serif", "color": "#172033"},
        margin={"l": 58, "r": 24, "t": 58, "b": 52},
        legend={"orientation": "h", "y": -0.2},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=390,
    )
    if y_title:
        tickformat = ".1%" if percent else "$,.0f" if currency else None
        figure.update_yaxes(title=y_title, rangemode="tozero", tickformat=tickformat)
    return figure


def _report_warnings(report: AnalysisReport) -> list[str]:
    warnings = list(report.risk.concentration_warnings)
    if report.etf_exposure:
        warnings.extend(report.etf_exposure.warnings)
    if any(
        (key.lower().endswith("stale") or "stale" in key.lower()) and value is True
        for key, value in report.data_freshness.items()
    ):
        warnings.append("One or more data sources are stale.")
    return list(dict.fromkeys(warnings))


def _is_synthetic(report: AnalysisReport) -> bool:
    value = report.data_freshness.get("synthetic", False)
    return value is True or str(value).lower() == "true"


def _validate_output_path(output: str | Path) -> Path:
    path = Path(output).expanduser()
    if path.exists() and path.is_dir():
        raise ReportRenderingError("HTML report output must be a file, not a directory")
    if path.suffix.lower() not in {".html", ".htm"}:
        raise ReportRenderingError("HTML report output must end in .html or .htm")
    if path.parent.exists() and not path.parent.is_dir():
        raise ReportRenderingError("HTML report parent path is not a directory")
    return path


def _currency(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.2f}"


def _percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


def _number(value: float | None) -> str:
    return "n/a" if value is None else f"{value:,.3f}"


def _date_value(value: date | None) -> str:
    return "unknown" if value is None else value.isoformat()
