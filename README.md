# Portfolio Intelligence & Risk Engine

Local-first portfolio accounting, market-data ingestion, performance analytics, risk analytics, and scenario testing in a Python SDK and `portfolio` CLI.

This project is for investors, builders, and researchers who want deterministic portfolio analytics they can run locally. It reconstructs holdings from transactions, values them with demo, CSV, or live market data, and computes performance/risk metrics without sending portfolio data to a hosted service.

It is not a stock chatbot and it is not financial advice. Accounting and risk numbers are computed by deterministic application code.

## What It Does

- Reconstructs a portfolio from transaction CSV files.
- Imports current-holdings snapshots for easier first-time setup.
- Reads Fidelity positions exports locally and keeps only safe whitelisted fields.
- Supports deposits, withdrawals, buys, sells, dividends, fees, cash, average cost, realized P&L, and unrealized P&L.
- Runs fully offline with synthetic demo portfolio and market data.
- Supports live daily prices, quotes, dividends, and splits through:
  - [Twelve Data](https://twelvedata.com/) as the recommended primary provider.
  - [Finnhub](https://finnhub.io/) as a live provider or fallback.
  - [Alpha Vantage](https://www.alphavantage.co/) as an optional fallback.
  - Local CSV price files.
- Caches live provider responses locally with freshness, provenance, checksum, completeness, and stale/fallback metadata.
- Looks through ETFs to combine direct and indirect company and sector exposure.
- Measures ETF overlap, effective concentration, HHI, and effective number of holdings.
- Handles provider retries, timeouts, rate limits, stale-cache policy, and provider health diagnostics.
- Computes returns, volatility, Sharpe, Sortino, drawdown, beta, historical VaR, Expected Shortfall, covariance, correlation, and risk contribution.
- Runs YAML scenario shocks by symbol, sector, and asset type.
- Exposes the same calculations through a Python SDK and Typer/Rich CLI.

## Quick Start

Use the offline demo first. It does not need API keys.

```bash
git clone <this-repo-url>
cd portfolio-intelligence-engine
python -m pip install -e ".[dev]"

portfolio setup
portfolio doctor
portfolio summary
portfolio risk
portfolio scenario run tech-selloff
```

If you are in a sandboxed or temporary environment, keep generated app files somewhere writable:

```bash
PORTFOLIO_INTELLIGENCE_HOME=/tmp/portfolio-intelligence portfolio setup
```

## Live Market Data Setup

The default demo mode is offline-safe. To use live data, create a `.env` file in the repo root.

Start with Twelve Data primary and Finnhub fallback:

```dotenv
MARKET_DATA_PROVIDER=twelvedata
MARKET_DATA_FALLBACK_PROVIDER=finnhub

TWELVE_DATA_API_KEY=replace_me
FINNHUB_API_KEY=replace_me
ALPHA_VANTAGE_API_KEY=

MARKET_DATA_TIMEOUT_SECONDS=15
MARKET_DATA_MAX_RETRIES=3
PRICE_CACHE_TTL_HOURS=12
CORPORATE_ACTION_CACHE_TTL_HOURS=24
ALLOW_STALE_CACHE=true
```

Get API keys here:

- Twelve Data: [sign up](https://twelvedata.com/) and see the [Twelve Data API docs](https://twelvedata.com/docs).
- Finnhub: [get a free API key](https://finnhub.io/register) and see the [Finnhub API docs](https://finnhub.io/docs/api).
- Alpha Vantage: [claim a free API key](https://www.alphavantage.co/support/#api-key) and see the [Alpha Vantage docs](https://www.alphavantage.co/documentation/).

Before verifying, make sure you have already installed the package and initialized the local workspace:

```bash
python -m pip install -e ".[dev]"
portfolio setup
```

If you want to sync live data for your own portfolio instead of the bundled demo portfolio, also point the app at your transaction CSV:

```dotenv
PORTFOLIO_SOURCE=csv
PORTFOLIO_CSV_PATH=path/to/your-transactions.csv
```

You can validate that CSV before syncing:

```bash
portfolio import-transactions path/to/your-transactions.csv --dry-run
```

Then verify and sync:

```bash
portfolio provider-status
portfolio doctor
portfolio sync prices
portfolio sync corporate-actions
portfolio data-status
portfolio summary
portfolio risk
```

## Easiest Portfolio Setup

The easiest way to use your own portfolio is a current-holdings snapshot. This is less detailed than full transaction history, but it is much simpler and avoids storing broker account identifiers.

For Fidelity positions exports, the app keeps only approved fields such as symbol, quantity, description, current price, current value, cost basis, average cost basis, type, and currency. Fields such as account name, account ID, gain/loss columns, percentages, and other broker metadata are ignored.

Preview a Fidelity positions export locally:

```bash
portfolio import-broker fidelity ~/Downloads/Portfolio_Positions.csv
```

Write a clean holdings file with sensitive broker columns discarded:

```bash
portfolio import-broker fidelity ~/Downloads/Portfolio_Positions.csv \
  --export-clean data/holdings.csv
```

Then use that clean holdings file:

```dotenv
PORTFOLIO_SOURCE=holdings
PORTFOLIO_HOLDINGS_PATH=data/holdings.csv
PORTFOLIO_HOLDINGS_FORMAT=generic
```

You can also import a simple holdings CSV directly:

```csv
symbol,quantity,average_cost,asset_type,currency
AAPL,10,185.20,Stock,USD
VOO,5,470.00,ETF,USD
MSFT,3,410.00,Stock,USD
```

```bash
portfolio import-holdings data/holdings.csv
```

For a small portfolio, add holdings one at a time:

```bash
portfolio add AAPL --shares 10 --average-cost 185.20 --asset-type Stock
portfolio add VOO --shares 5 --average-cost 470.00 --asset-type ETF
```

Or use the interactive wizard:

```bash
portfolio holdings-wizard
```

You can also paste a table copied from a spreadsheet or broker page:

```bash
portfolio import-holdings --paste --export-clean data/holdings.csv
```

Paste something like this, then press Ctrl-D:

```text
Symbol    Quantity    Average Cost    Type
AAPL      10          185.20          Stock
VOO       5           470.00          ETF
```

Snapshot mode supports current value, allocation, unrealized P&L when cost basis exists, volatility estimates, correlations, beta, VaR, Expected Shortfall, concentration checks, and stress scenarios. It does not represent your actual historical deposits, withdrawals, realized P&L, or time-weighted performance.

If you only have one live provider key, use it directly:

```dotenv
MARKET_DATA_PROVIDER=finnhub
MARKET_DATA_FALLBACK_PROVIDER=demo
FINNHUB_API_KEY=replace_me
```

`demo` fallback is useful for testing only because demo prices are synthetic. For real analysis, prefer `finnhub`, `alphavantage`, or `csv` as fallback.

More detail: [docs/market_data.md](docs/market_data.md).

## Common Commands

```bash
portfolio setup
portfolio doctor
portfolio provider-status

portfolio sync
portfolio sync prices
portfolio sync prices --symbol AAPL
portfolio sync corporate-actions
portfolio data-status
portfolio data-status --format json

portfolio import-broker fidelity ~/Downloads/Portfolio_Positions.csv
portfolio import-holdings data/holdings.csv
portfolio import-holdings --paste --export-clean data/holdings.csv
portfolio add AAPL --shares 10 --average-cost 185.20
portfolio holdings-wizard
portfolio import-transactions data/portfolio.example.csv --dry-run
portfolio holdings
portfolio summary
portfolio performance
portfolio risk
portfolio exposure
portfolio exposure --look-through
portfolio exposure --security
portfolio exposure --sector
portfolio etf-overlap
portfolio etf-overlap VOO QQQ
portfolio sync etfs
portfolio correlations
portfolio scenario list
portfolio scenario run tech-selloff
portfolio report --format markdown
```

Most reporting commands also support JSON:

```bash
portfolio summary --format json
portfolio risk --format json
portfolio provider-status --format json
```

## Transaction CSV Format

Portfolio input is transaction-driven. A minimal CSV looks like:

```csv
transaction_id,date,type,symbol,quantity,price,fee,currency
deposit-1,2025-01-02,DEPOSIT,,0,10000.00,0,USD
buy-nvda-1,2025-01-03,BUY,NVDA,10,120.00,0,USD
buy-voo-1,2025-02-04,BUY,VOO,5,485.00,0,USD
dividend-voo-1,2025-03-01,DIVIDEND,VOO,0,14.20,0,USD
```

For deposits, withdrawals, and dividends, `price` stores the cash amount. Current limitations: USD only, no margin, and no shorting.

Import or validate a CSV:

```bash
portfolio import-transactions data/portfolio.example.csv --dry-run
```

## Configuration

Configuration is loaded from project-local `.env` and environment variables. Environment variables override `.env` values.

Important settings:

```dotenv
PORTFOLIO_SOURCE=demo
PORTFOLIO_CSV_PATH=data/portfolio.example.csv
PORTFOLIO_HOLDINGS_PATH=data/holdings.csv
PORTFOLIO_HOLDINGS_FORMAT=auto

MARKET_DATA_PROVIDER=demo
MARKET_DATA_FALLBACK_PROVIDER=
MARKET_DATA_CSV_DIRECTORY=data/prices

TWELVE_DATA_API_KEY=
FINNHUB_API_KEY=
ALPHA_VANTAGE_API_KEY=

MARKET_DATA_TIMEOUT_SECONDS=15
MARKET_DATA_MAX_RETRIES=3
PRICE_CACHE_TTL_HOURS=12
CORPORATE_ACTION_CACHE_TTL_HOURS=24
ALLOW_STALE_CACHE=true

ETF_COMPOSITION_PROVIDER=demo
ETF_COMPOSITION_FALLBACK_PROVIDER=
ETF_COMPOSITION_CSV_DIRECTORY=data/etfs
ETF_COMPOSITION_CACHE_TTL_HOURS=24
ETF_COMPOSITION_STALE_AFTER_DAYS=45
ETF_WEIGHT_TOLERANCE=0.01
ETF_SYMBOLS=VOO,QQQ
ETF_OVERLAP_WARNING_THRESHOLD=0.40
```

Provider choices:

- `demo`: synthetic offline data, no API key required.
- `csv`: local `SYMBOL.csv` files.
- `twelvedata`: live Twelve Data adapter.
- `finnhub`: live Finnhub adapter.
- `alphavantage`: live Alpha Vantage adapter.

ETF composition providers are configured separately:

- `demo`: synthetic VOO/QQQ/SPY compositions for offline use.
- `csv`: local compositions with no provider redistribution dependency.
- `alphavantage`: the Alpha Vantage `ETF_PROFILE` endpoint. Availability, rate limits,
  entitlements, retention, and redistribution are controlled by the provider's plan and terms.

A per-fund CSV such as `data/etfs/VOO.csv` uses decimal or percentage weights:

```csv
constituent_symbol,name,weight,sector,allocation_type,as_of_date
AAPL,Apple Inc.,7.0%,Technology,security,2026-07-31
MSFT,Microsoft Corp.,6.5%,Technology,security,2026-07-31
CASH,Cash,0.5%,Cash,cash,2026-07-31
```

A consolidated `etf_holdings.csv` adds a `fund_symbol` column. Optional
`etf_sectors.csv` and `etf_metadata.csv` files provide fund-level sectors and metadata. For holdings
snapshots, `asset_type=ETF` identifies funds automatically. Transaction CSVs have no asset-type
field, so list their funds in `ETF_SYMBOLS`.

Duplicate constituents are combined by default. Totals materially above 100% are rejected; totals
below 100% receive an explicit `OTHER` allocation.

## ETF Look-Through And Concentration

Direct exposure is the market value held in a company itself. Indirect exposure is ETF market value
multiplied by constituent weight. Effective company exposure adds direct and all indirect exposure.
For example, $5,000 of AAPL held directly plus $1,200 through VOO and $800 through QQQ produces
$7,000 of effective AAPL exposure.

Effective sectors use constituent classifications when complete. If they are unavailable, the
engine uses the ETF-provided sector allocation for the whole fund. Output labels the method as
`direct`, `constituent`, `etf_sector_allocation`, or `unclassified`.

For ETFs A and B, weighted overlap is:

```text
weighted overlap(A, B) = sum over shared securities i of min(weight_A_i, weight_B_i)
```

Identical fully reported funds have 100% overlap. Cash and `OTHER` are excluded. Sector overlap
applies the same formula to constituent-derived sector totals.

Concentration output includes the largest effective company and sector weights, top five holdings,
HHI, effective number of holdings, and configurable warnings. HHI normalizes effective company
exposure across invested non-cash value; effective number of holdings is `1 / HHI`.

Composition dates can lag current prices and holdings can change between disclosures. Stale data is
labeled and missing weights remain `OTHER`; the engine does not silently redistribute them. See
[the methodology](docs/methodology.md) for complete definitions.

## Cache And Freshness

Live provider results are cached under the application cache directory. Cache entries include:

- provider
- symbol
- endpoint/data type
- request parameters
- retrieval timestamp
- effective market-data date
- expiration timestamp
- schema version
- payload checksum
- completeness flag
- fallback flag

Price sync is incremental: once a symbol has cached history, the engine requests only the missing date range. Expired data is not silently presented as current. If `ALLOW_STALE_CACHE=true`, stale data may be returned only after a provider failure and is marked stale in the returned data/status.

Check freshness:

```bash
portfolio data-status
portfolio data-status --format json
```

## Python SDK

```python
from portfolio_intelligence import PortfolioAnalyzer

analyzer = PortfolioAnalyzer.from_csv("data/portfolio.example.csv")
report = analyzer.analyze(benchmark="SPY", confidence_level=0.95)

print(report.summary.total_value)
print(report.performance.cumulative_return)
print(report.risk.maximum_drawdown)
print(report.risk.expected_shortfall)
```

## Architecture

```text
Portfolio transactions + market data
        ↓
Validation and normalization
        ↓
Portfolio accounting
        ↓
Return and risk analytics
        ↓
Scenario analysis
        ↓
SDK, CLI, and reports
```

The C++ layer owns deterministic numerical analytics. It has no knowledge of providers, HTTP, SQLite, API keys, CLI formatting, or AI. Python owns ingestion, configuration, accounting orchestration, storage, provider normalization, reports, and CLI/SDK ergonomics.

Provider-specific response objects stay inside provider modules. Application services see normalized domain models such as `PriceBar`, `Quote`, `Dividend`, and `StockSplit`.

## Testing

```bash
make test-python
make test-cpp
make test
python -m ruff check src tests
```

Python tests cover CSV parsing, validation, average-cost accounting, cash flows, demo providers,
live provider parsing with mocked HTTP responses, provider fallback, cache behavior, stale-cache
policy, ETF reconciliation/overlap/concentration, scenarios, and the demo report path.

Normal unit tests and CI do not make real API requests.

## Troubleshooting

Check setup first:

```bash
portfolio doctor
portfolio provider-status
portfolio data-status
```

Common issues:

- Missing API key: set `TWELVE_DATA_API_KEY`, `FINNHUB_API_KEY`, or `ALPHA_VANTAGE_API_KEY`.
- Rate limit: wait for the provider window to reset, reduce sync frequency, or configure a fallback provider.
- Unsupported symbol: confirm the vendor supports the ticker and exchange format.
- Empty `data-status` in demo mode: demo data is generated locally and reported as uncached.
- Stale warning: run `portfolio sync`; stale cache is used only when configured and provider refresh fails.
- Cache corruption: remove the affected cache file shown by diagnostics and sync again.

## Limitations

- This is not financial advice.
- Demo data is synthetic.
- VaR is not a maximum-loss estimate.
- Sharpe, Sortino, beta, correlations, and VaR are statistical estimates and can be unstable.
- Live provider data can be delayed, revised, rate-limited, incomplete, or entitlement constrained.
- Taxes, tax-lot elections, margin, shorting, multi-currency accounting, and rebalancing optimization are not complete.

## Roadmap

1. Historical stress-period library.
2. Cost-aware constrained rebalancing.
3. Transaction-cost and turnover reporting.
4. Standalone HTML reports.
5. FRED macro-data adapter.
6. SEC EDGAR fundamentals adapter.
7. Probabilistic and Deflated Sharpe Ratio.
8. Optional grounded explanations.

## License

MIT. See [LICENSE](LICENSE).
