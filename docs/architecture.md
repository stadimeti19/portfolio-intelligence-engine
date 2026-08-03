# Architecture

Portfolio Intelligence & Risk Engine is layered so numerical calculations can be tested and reused outside the CLI.

```text
Python providers, accounting, storage, SDK, CLI, and reports
        ↓ normalized contiguous arrays
pybind11 boundary
        ↓
C++20 valuation, incremental state, covariance, risk, and simulation
```

## C++ Responsibilities

The `portfolio_engine_core` target is organized by implemented responsibility rather than by a
large aspirational directory tree:

- `analytics.cpp`: stateless return, risk, matrix, contribution, and scenario kernels retained for
  API compatibility;
- `engine.cpp`: normalized batch valuation plus the stateful `PortfolioAnalyticsEngine`;
- `incremental_statistics.cpp`: Welford-style running variance/covariance, rolling volatility, and
  online drawdown;
- `covariance.cpp`: sample, exponentially weighted, shrinkage, and diagonal estimators with
  diagnostics;
- `simulation.cpp`: deterministic fixed-block, multi-threaded normal and historical-bootstrap
  simulation.

The engine accepts row-major contiguous arrays. A history contains stable symbol order, strictly
increasing timestamps, prices, quantities, cash balances, and external cash flows. Python completes
accounting and date normalization first. C++ computes position values, invested/total value, asset
weights, and cash-flow-adjusted portfolio returns without accessing Python objects.

The engine owns its copied history summaries and current state. Public methods use an internal
mutex; simulation is a stateless operation that writes each path to a disjoint output slot. Random
streams are assigned to fixed 256-path blocks, so a fixed seed produces the same path array
regardless of worker count.

Bindings accept exact C-contiguous `float64`/`int64` arrays. They reject dtype or layout conversion,
inspect buffers while holding the GIL, then release it before native calculation. Returned arrays
own their Python memory and do not expose native pointers.

## Python Responsibilities

Python owns configuration, CSV ingestion, transaction validation, portfolio accounting, market-data normalization, report models, storage, SDK ergonomics, and CLI presentation. The SDK calls C++ for authoritative analytics through the `portfolio_engine` binding, with a development fallback used only when the extension has not yet been built.

The complete transaction ledger intentionally remains in Python. Current evidence does not show
parsing or average-cost bookkeeping as a bottleneck, and those operations are tightly coupled to
provider normalization and domain validation. Only normalized valuation state crosses into C++.

Cost-aware optimization is also not exposed yet. The repository has no tested convex-solver
dependency, and a bespoke projected-gradient implementation would not satisfy the solver-status,
infeasibility, and constraint guarantees expected of this feature.

## Provider Architecture

Provider protocols isolate external formats from application services. Market-data and ETF
composition providers are separate because price and composition freshness differ. ETF adapters
normalize Alpha Vantage, CSV, and demo responses into `EtfHolding`, `SectorWeight`, and
`EtfMetadata` before analytics. Both provider stacks support caching, fallback, and stale provenance.

## Storage

SQLite is the default local storage target. SQLAlchemy models are intentionally separate from Pydantic domain models. Schema versioning starts with `0.1.0`.

## Configuration

Configuration is loaded from CLI overrides, environment variables, project `.env`, user config, and defaults. Secrets are kept separate from normal configuration and must not be logged.

## Future Dashboard

The standalone Jinja2/Plotly report and local Streamlit dashboard consume serializable typed report
objects. `DashboardService` calls the SDK, caches reports using input/data fingerprints, and delegates
HTML export to the same renderer. Presentation code does not reimplement analytics. See
[visual reporting](visual_reporting.md).
