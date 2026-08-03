# Architecture

Portfolio Intelligence & Risk Engine is layered so numerical calculations can be tested and reused outside the CLI.

```text
Portfolio, market data, and ETF compositions
        ↓
Validation and normalization
        ↓
Portfolio accounting
        ↓
Return, risk, look-through, overlap, and concentration analytics
        ↓
Scenario analysis and future rebalancing
        ↓
SDK, CLI, and future visual reports
```

## C++ Responsibilities

The `portfolio_engine` C++ library owns deterministic numerical analytics: returns, annualization, volatility, Sharpe, Sortino, drawdown, beta, historical VaR, Expected Shortfall, covariance, correlation, risk contribution, and direct scenario shock arithmetic. It has no knowledge of HTTP, environment variables, SQLite, CLI formatting, AI, or provider response formats.

## Python Responsibilities

Python owns configuration, CSV ingestion, transaction validation, portfolio accounting, market-data normalization, report models, storage, SDK ergonomics, and CLI presentation. The SDK calls C++ for authoritative analytics through the `portfolio_engine` binding, with a development fallback used only when the extension has not yet been built.

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

The report objects are serializable and already separate from Rich terminal formatting. A dashboard or standalone HTML report should consume the SDK rather than reimplementing calculations.
