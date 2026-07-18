# Market Data Providers

Portfolio Intelligence supports offline demo data by default and live market data through provider adapters. Provider payloads are normalized into `PriceBar`, `Quote`, `Dividend`, and `StockSplit` before analytics code sees them.

## Configuration

Project-local `.env` values are loaded first, environment variables override them, and explicit application overrides remain highest precedence.

```dotenv
MARKET_DATA_PROVIDER=twelvedata
MARKET_DATA_FALLBACK_PROVIDER=csv
MARKET_DATA_CSV_DIRECTORY=data/prices

TWELVE_DATA_API_KEY=
ALPHA_VANTAGE_API_KEY=
FINNHUB_API_KEY=

MARKET_DATA_TIMEOUT_SECONDS=15
MARKET_DATA_MAX_RETRIES=3
PRICE_CACHE_TTL_HOURS=12
CORPORATE_ACTION_CACHE_TTL_HOURS=24
ALLOW_STALE_CACHE=true
```

Use `MARKET_DATA_PROVIDER=demo` to force the deterministic offline provider. The offline demo does not require API keys.

## Providers

- `demo`: deterministic synthetic data for the bundled demo portfolio.
- `csv`: local `SYMBOL.csv` files with `date,open,high,low,close,adjusted_close,volume`.
- `twelvedata`: primary live provider for daily prices, quotes, dividends, and splits where the symbol is supported by Twelve Data.
- `finnhub`: live provider/fallback for daily stock candles, quotes, dividends, and splits where supported by Finnhub.
- `alphavantage`: optional live fallback. Daily adjusted prices include dividends and split coefficients.

Twelve Data is intended as the primary live provider. Finnhub is useful as a quote/price fallback and for provider diversification, but some stock candle and corporate-action endpoints can be plan or entitlement constrained. Alpha Vantage is also useful as a backup, but free plans can be rate limited and some adjusted or corporate-action endpoints may be entitlement constrained.

## Cache Behavior

Live providers are wrapped with a local cache under the application cache directory. Cache entries include provider, symbol, endpoint, request parameters, retrieval time, effective market-data date, expiration, schema version, payload checksum, completeness, and fallback status.

Price synchronization is incremental. When cached history exists, the provider requests data starting from the latest cached trading date and merges the returned bars by date. Valid unexpired cache entries are used directly.

Expired cache is not presented as current. If `ALLOW_STALE_CACHE=true`, stale cache may be returned only after a provider failure, and returned bars/quotes/actions are marked stale. If stale cache is disabled or missing, the command fails with a clear error.

## Freshness Policy

`PRICE_CACHE_TTL_HOURS` controls price and quote freshness. `CORPORATE_ACTION_CACHE_TTL_HOURS` controls dividends and splits. `portfolio data-status` shows the first and latest dates, retrieval time, age, cache status, fallback status, and stale warnings. Use `--format json` for machine-readable output.

## Rate Limits and Retries

Provider requests use configurable timeout and retry settings. Temporary 5xx/network failures are retried with backoff. HTTP 429 and provider-specific limit messages raise explicit rate-limit errors. Authentication failures, unsupported symbols, malformed responses, incomplete histories, and cache corruption are reported without exposing API keys or full provider payloads.

## Commands

```bash
portfolio provider-status
portfolio sync
portfolio sync prices
portfolio sync prices --symbol AAPL
portfolio sync corporate-actions
portfolio data-status
portfolio data-status --format json
portfolio doctor
```

## Troubleshooting

- Missing API key: set `TWELVE_DATA_API_KEY`, `FINNHUB_API_KEY`, or `ALPHA_VANTAGE_API_KEY`, or use `MARKET_DATA_PROVIDER=demo`.
- Rate limit: wait for the provider window to reset, reduce sync frequency, or configure a fallback.
- Unsupported symbol: verify the vendor symbol format and exchange support.
- Stale cache warning: run `portfolio sync`; if the provider is unavailable, decide whether `ALLOW_STALE_CACHE=true` is acceptable for your workflow.
- Cache corruption: remove the affected cache file shown by diagnostics and sync again.
