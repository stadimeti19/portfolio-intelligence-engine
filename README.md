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
- Live daily prices, quotes, dividends, and splits through Twelve Data, with optional Finnhub, Alpha Vantage, or CSV fallback.
- Local market-data cache with freshness metadata, incremental price synchronization, retries, timeout handling, and provider diagnostics.
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
portfolio provider-status
portfolio sync
portfolio data-status
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

Market-data defaults remain offline-safe. To use live data:

```dotenv
MARKET_DATA_PROVIDER=twelvedata
MARKET_DATA_FALLBACK_PROVIDER=finnhub
TWELVE_DATA_API_KEY=...
ALPHA_VANTAGE_API_KEY=
FINNHUB_API_KEY=
MARKET_DATA_TIMEOUT_SECONDS=15
MARKET_DATA_MAX_RETRIES=3
PRICE_CACHE_TTL_HOURS=12
CORPORATE_ACTION_CACHE_TTL_HOURS=24
ALLOW_STALE_CACHE=true
```

Use `MARKET_DATA_PROVIDER=demo` for the deterministic no-key demo. See `docs/market_data.md` for provider configuration, freshness policy, cache behavior, rate-limit behavior, limitations, and troubleshooting.

## Testing

```bash
make test-python
make test-cpp
make test
```

Python tests cover CSV parsing, validation, average-cost accounting, cash flows, demo providers, scenarios, C++ reference wrapper behavior, and the demo report integration path.
Live provider tests use mocked HTTP responses only; normal unit tests and CI do not make real API requests.

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
- `TwelveDataProvider`
- `FinnhubProvider`
- `AlphaVantageProvider`
- Local cached provider wrapper
- Fallback market-data coordinator

Provider-specific response objects stay inside provider modules. External formats are normalized into domain models before application services see them.

## Roadmap

1. ETF look-through exposure and overlap.
2. Historical stress-period library.
3. Cost-aware constrained rebalancing.
4. Transaction-cost and turnover reporting.
5. Standalone HTML reports.
6. FRED macro-data adapter.
7. SEC EDGAR fundamentals adapter.
8. Probabilistic and Deflated Sharpe Ratio.
9. Optional grounded OpenAI explanations.

## Limitations

This is not financial advice. Demo data is synthetic. VaR is not a maximum-loss estimate. Correlations, betas, and Sharpe ratios are uncertain estimates. Taxes, tax-lot elections, live provider delays, vendor data corrections, and transaction-cost optimization remain important limitations.

## Contributing

Keep CLI commands thin, provider code isolated, and numerical formulas documented. Add tests for accounting invariants, risk calculations, and integration paths before expanding the feature surface.

## License

MIT. See [LICENSE](LICENSE).
