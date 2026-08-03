# Visual Reporting

## Standalone HTML

```bash
portfolio report --output portfolio-report.html
```

The HTML renderer uses Jinja2, Plotly, and the typed `AnalysisReport`. Plotly JavaScript is embedded
once in the file, so charts work without a server or CDN. The layout includes screen, mobile, and
print styles. Values retain the report's as-of date, currency/percentage formatting, provenance,
synthetic-data label, stale warnings, methodology version, and limitations.

The renderer does not calculate returns, risk, exposure, attribution, scenarios, or rebalancing.
Chart traces are projections of typed report fields. Drawdown history is produced by
`AnalyticsService` and stored in `PerformanceReport`; the renderer rejects inconsistent snapshot and
drawdown dates instead of silently aligning them.

HTML output must end in `.html` or `.htm`. Jinja autoescaping remains enabled for portfolio symbols,
provider values, scenario descriptions, and limitation notes. Plotly fragments produced by Plotly
itself are the only explicitly trusted markup.

## Local Dashboard

Install the optional dependency and launch:

```bash
python -m pip install -e ".[dashboard]"
portfolio dashboard
```

Optional network binding:

```bash
portfolio dashboard --address 127.0.0.1 --port 8501
```

The Streamlit application calls `DashboardService`, which calls `PortfolioAnalyzer`. Scenario
selection calls the existing scenario service through the SDK. Plotly figures are shared with the
standalone report renderer. Streamlit components do not implement financial formulas.

The dashboard provides portfolio, displayed date range, benchmark, confidence level, scenario,
security/sector/ETF-overlap thresholds, refresh, and HTML export controls. Rebalancing settings are
shown as disabled placeholders because optimization is not implemented.

## Caching And Invalidation

`DashboardService` caches complete typed reports. The key contains:

- portfolio identifier;
- transaction and local provider-file fingerprint;
- report data date;
- displayed date range;
- benchmark and confidence level;
- methodology version;
- scenario and concentration thresholds;
- reserved optimizer settings.

Transaction changes and price/composition CSV or JSON cache-file changes produce a new fingerprint.
The refresh button bypasses cached analytics. Standalone HTML generated for an unchanged result is
also cached in memory. Cache entries are bounded and evicted in insertion order.

The date range limits displayed history; it does not alter SDK metrics. This prevents the dashboard
from independently recomputing performance for a subset of report observations.

## Layer Boundaries

```text
Providers → accounting/analytics services → PortfolioAnalyzer → AnalysisReport
                                                        ↓
                                      CLI / HTML / dashboard presentation
```

- Providers normalize external data and freshness.
- Application services calculate all metrics.
- The SDK is the public orchestration boundary.
- The CLI handles command input and output selection.
- HTML and Streamlit format typed values and call SDK/service methods.
