# portfolio-intelligence-engine

Open-source C++/Python portfolio analytics SDK and CLI for performance attribution, risk decomposition, stress testing, ETF exposure, and cost-aware rebalancing.

## Overview

Portfolio Intelligence & Risk Engine is a local-first quantitative portfolio analytics platform. The first milestone is an offline MVP: it reconstructs a portfolio from transactions, ingests deterministic demo market data, computes current holdings and portfolio history, calls a C++ analytics engine for risk/performance metrics, and exposes the same calculations through a Python SDK and `portfolio` CLI.

The core product direction is:

> An open-source C++/Python portfolio analytics SDK with an installable CLI and local visual reporting for performance attribution, risk decomposition, stress testing, ETF exposure analysis, and cost-aware constrained rebalancing.

This is not a stock chatbot. Authoritative accounting and risk numbers are computed by deterministic application code.

## Capabilities

- Transaction-driven accounting with deposits, withdrawals, buys, sells, dividends, fees, cash, average cost, realized P&L, and unrealized P&L.
- Offline synthetic demo data for equities, ETFs, bond-like exposure, SPY benchmark, drawdown, volatility spike, and recovery periods.
- C++ analytics for returns, annualization, volatility, Sharpe, Sortino, maximum drawdown, beta, historical VaR, Expected Shortfall, covariance, correlation, risk contribution, and scenario shock arithmetic.
- Python SDK centered on `PortfolioAnalyzer`.
- Typer/Rich CLI with table and JSON output.
- YAML scenario files with symbol, sector, and asset-type shocks.
- SQLite initialization boundary and SQLAlchemy models.
- Documentation for architecture, methodology, privacy, and limitations.

## Architecture

```text
Portfolio and market data
        ↓
Validation and normalization
        ↓
Portfolio accounting
        ↓
Return and risk analytics
        ↓
Scenario analysis and future rebalancing
        ↓
SDK, CLI, and future visual reports
```

The C++ layer has no knowledge of providers, HTTP, SQLite, API keys, CLI formatting, or AI. Python owns ingestion, configuration, accounting orchestration, storage, reports, and CLI/SDK ergonomics.

## Installation

Target development setup:

```bash
pip install -e ".[dev]"
```

The package targets Python 3.11+ and builds the `portfolio_engine` pybind11 extension through scikit-build-core and CMake.

## Offline Demo

```bash
portfolio init
portfolio doctor
portfolio import-transactions data/portfolio.example.csv --dry-run
portfolio holdings
portfolio summary
portfolio performance
portfolio risk
portfolio exposure
portfolio correlations
portfolio scenario list
portfolio scenario run tech-selloff
portfolio report --format markdown
```

In sandboxed environments, keep generated app files inside a writable directory:

```bash
PORTFOLIO_INTELLIGENCE_HOME=/tmp/portfolio-intelligence portfolio init
```

## SDK Example

```python
from portfolio_intelligence import PortfolioAnalyzer

analyzer = PortfolioAnalyzer.from_csv("data/portfolio.example.csv")
report = analyzer.analyze(benchmark="SPY", confidence_level=0.95)
scenario = analyzer.run_scenario("tech-selloff")

print(report.summary.total_value)
print(report.performance.cumulative_return)
print(report.risk.maximum_drawdown)
print(report.risk.expected_shortfall)
print(scenario.pnl)
```

## CSV Format

```csv
transaction_id,date,type,symbol,quantity,price,fee,currency
deposit-1,2025-01-02,DEPOSIT,,0,10000.00,0,USD
buy-nvda-1,2025-01-03,BUY,NVDA,10,120.00,0,USD
buy-voo-1,2025-02-04,BUY,VOO,5,485.00,0,USD
dividend-voo-1,2025-03-01,DIVIDEND,VOO,0,14.20,0,USD
```

For dividends, deposits, and withdrawals, `price` stores the cash amount. The MVP supports USD only, no margin, and no shorting.

## Configuration

`.env.example` documents supported environment variables. Configuration precedence is intended to be:

1. CLI flags
2. Environment variables
3. Project-local `.env`
4. User-level `config.toml`
5. Application defaults

Secrets should live outside normal config and are ignored by git.

## Testing

```bash
make test-python
make test-cpp
make test
```

Python tests cover CSV parsing, validation, average-cost accounting, cash flows, demo providers, scenarios, C++ reference wrapper behavior, and the demo report integration path.

C++ tests are available through CTest. The repository includes deterministic C++ assertions rather than a vendored GoogleTest copy so the offline MVP does not fetch dependencies during test configuration.

## Benchmarks

```bash
make benchmark
```

The benchmark target runs a reproducible single-threaded timing loop over 5,000 synthetic prices. Do not compare results across machines without controlling compiler, build type, CPU, and thermal state.

## Data Provider Design

The MVP includes:

- `DemoPortfolioSource`
- `CsvPortfolioSource`
- `DemoMarketDataProvider`
- `CsvMarketDataProvider`

Future providers should normalize external formats into domain models before application services see them. Planned adapters include Twelve Data, Alpha Vantage, SEC EDGAR, FRED, and optional Plaid.

## Roadmap

1. Twelve Data market-data adapter with caching and rate limits.
2. Alpha Vantage ETF composition adapter.
3. ETF look-through exposure and overlap.
4. Historical stress-period library.
5. Cost-aware constrained rebalancing.
6. Transaction-cost and turnover reporting.
7. Standalone HTML reports.
8. FRED macro-data adapter.
9. SEC EDGAR fundamentals adapter.
10. Probabilistic and Deflated Sharpe Ratio.
11. Optional grounded OpenAI explanations.

## Limitations

This is not financial advice. Demo data is synthetic. VaR is not a maximum-loss estimate. Correlations, betas, and Sharpe ratios are uncertain estimates. Taxes, corporate actions, tax-lot elections, live provider delays, and transaction-cost optimization are future work.

## Contributing

Keep CLI commands thin, provider code isolated, and numerical formulas documented. Add tests for accounting invariants, risk calculations, and integration paths before expanding the feature surface.

## License

MIT. See [LICENSE](LICENSE).
