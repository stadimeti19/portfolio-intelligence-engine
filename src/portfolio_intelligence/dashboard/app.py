from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import streamlit as st

from portfolio_intelligence.dashboard.runtime import (
    available_scenarios,
    build_dashboard_service,
)
from portfolio_intelligence.dashboard.service import DashboardRequest, DashboardService


def _plot(figure: Any) -> None:
    if figure is None:
        st.info("This visualization is unavailable for the selected data.")
    else:
        st.plotly_chart(figure, use_container_width=True, config={"displayModeBar": False})


def _percentage(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2%}"


st.set_page_config(page_title="Portfolio Intelligence", page_icon="📊", layout="wide")


@st.cache_resource
def dashboard_service() -> DashboardService:
    return build_dashboard_service()


@st.cache_data(ttl=300)
def scenario_names(portfolio: str) -> list[str]:
    return available_scenarios(portfolio)


st.title("Portfolio Intelligence & Risk Dashboard")
st.caption(
    "Typed analytics from the SDK, presented locally. No financial metrics are calculated here."
)

with st.sidebar:
    st.header("Analysis controls")
    portfolio = st.selectbox(
        "Portfolio",
        options=["configured", "demo"],
        format_func=lambda value: "Configured portfolio" if value == "configured" else "Demo",
    )
    date_range = st.date_input(
        "Displayed date range",
        value=(date.today() - timedelta(days=365), date.today()),
    )
    start_date: date | None
    end_date: date | None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = None
    benchmark = st.text_input("Benchmark", value="SPY").strip().upper() or "SPY"
    confidence = st.slider("Confidence level", 0.80, 0.99, 0.95, 0.01)
    scenarios = ["None", *scenario_names(portfolio)]
    selected_scenario = st.selectbox("Scenario", scenarios)
    st.subheader("Concentration thresholds")
    position_threshold = st.slider("Security", 0.01, 1.0, 0.25, 0.01)
    sector_threshold = st.slider("Sector", 0.01, 1.0, 0.50, 0.01)
    overlap_threshold = st.slider("ETF overlap", 0.01, 1.0, 0.40, 0.01)
    with st.expander("Rebalancing settings"):
        st.info("Rebalancing optimization is not implemented yet; these controls are reserved.")
        st.number_input("Maximum turnover", 0.0, 1.0, 0.10, disabled=True)
        st.number_input("Minimum trade value", 0.0, value=100.0, disabled=True)
    refresh = st.button("Refresh data", type="primary", use_container_width=True)

request = DashboardRequest(
    portfolio=portfolio,
    start_date=start_date,
    end_date=end_date,
    benchmark=benchmark,
    confidence_level=confidence,
    scenario=None if selected_scenario == "None" else selected_scenario,
    position_concentration_threshold=position_threshold,
    sector_concentration_threshold=sector_threshold,
    overlap_warning_threshold=overlap_threshold,
    rebalancing_settings={"optimizer_available": False},
)

try:
    result = dashboard_service().analyze(request, refresh=refresh)
except Exception as exc:
    st.error(f"Analysis failed: {exc}")
    st.stop()

report = result.report
st.caption(
    f"As of {report.summary.data_date.isoformat()} · Methodology {report.methodology_version} · "
    f"{'cached' if result.cached else 'freshly calculated'}"
)
if report.data_freshness.get("synthetic") is True:
    st.warning("Synthetic demo data — not actual investment performance.")
for warning in dict.fromkeys(
    report.risk.concentration_warnings
    + (report.etf_exposure.warnings if report.etf_exposure else [])
):
    st.warning(warning)

summary_columns = st.columns(5)
summary_columns[0].metric("Portfolio value", f"${report.summary.total_value:,.2f}")
summary_columns[1].metric("Cash", f"${report.summary.cash:,.2f}")
summary_columns[2].metric("Cumulative return", f"{report.performance.cumulative_return:.2%}")
summary_columns[3].metric("Volatility", _percentage(report.risk.annualized_volatility))
summary_columns[4].metric("Maximum drawdown", f"{report.performance.maximum_drawdown:.2%}")

figures = dashboard_service().html_renderer.build_figures(
    report, start_date=start_date, end_date=end_date
)
overview, exposure, risk, scenarios_tab, provenance = st.tabs(
    ["Overview", "Exposure", "Risk", "Scenarios", "Provenance"]
)
with overview:
    _plot(figures["portfolio_history"])
    left, right = st.columns(2)
    with left:
        _plot(figures["benchmark"])
    with right:
        _plot(figures["drawdown"])
    st.dataframe(
        [item.model_dump(mode="json") for item in report.holdings], use_container_width=True
    )
with exposure:
    left, right = st.columns(2)
    with left:
        _plot(figures["positions"])
    with right:
        _plot(figures["sectors"])
    _plot(figures["effective_exposure"])
    if report.etf_exposure:
        st.dataframe(
            [item.model_dump(mode="json") for item in report.etf_exposure.securities],
            use_container_width=True,
        )
with risk:
    left, right = st.columns(2)
    with left:
        _plot(figures["risk_contribution"])
    with right:
        _plot(figures["tail_risk"])
    _plot(figures["correlations"])
with scenarios_tab:
    _plot(figures["scenarios"])
    if not report.scenario_results:
        st.info("Select a scenario to include deterministic scenario-service results.")
with provenance:
    st.json(report.data_freshness)
    st.markdown("### Methodology and limitations")
    st.write(f"Methodology version: {report.methodology_version}")
    for note in report.limitations:
        st.write(f"- {note}")

html = dashboard_service().render_html(result)
st.download_button(
    "Export standalone HTML report",
    data=html.encode("utf-8"),
    file_name=f"portfolio-report-{report.summary.data_date.isoformat()}.html",
    mime="text/html",
)
