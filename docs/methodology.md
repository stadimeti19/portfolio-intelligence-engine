# Methodology

## Accounting

The MVP uses transaction-driven average-cost accounting. Deposits and withdrawals are external cash flows. Buys reduce cash by notional plus fee and increase position cost basis. Sells reduce quantity and cost basis at average cost, increase cash by proceeds net of fee, and realize P&L. Dividends increase cash but do not change quantity. Shorting and margin are disabled.

## Returns

Daily portfolio history is valued at end-of-day adjusted close. Time-weighted daily return is:

```text
(ending value - external flow) / prior ending value - 1
```

This prevents deposits and withdrawals from being treated as investment performance.

## Annualization

Annualized return uses geometric compounding with a default 252 trading-day annualization factor. Volatility uses sample standard deviation of daily returns multiplied by `sqrt(252)`.

## Sharpe and Sortino

Sharpe uses mean excess daily return divided by sample standard deviation, annualized by `sqrt(252)`. Sortino replaces total standard deviation with downside deviation versus the daily risk-free target. Zero volatility or zero downside deviation is reported as unavailable.

## Drawdown

Maximum drawdown is the most negative percentage decline from a prior peak in the portfolio value series. The engine also returns peak, trough, recovery index, and durations.

## Beta and Benchmark Comparison

Beta is covariance of aligned portfolio and benchmark returns divided by benchmark variance. Benchmark comparison also reports relative return, correlation, tracking difference, and tracking error when enough observations exist.

## Historical VaR and Expected Shortfall

Historical VaR is reported as a positive loss number using the empirical quantile of daily losses `-return`. Expected Shortfall is the average loss at or beyond that VaR threshold. These are one-day historical estimates, not maximum-loss guarantees.

## Covariance, Correlation, and Risk Contribution

Covariance and correlation use sample estimators over aligned return vectors. Risk contribution uses:

```text
variance = w'Σw
volatility = sqrt(variance)
marginal contribution = Σw / volatility
component contribution = w * marginal contribution
percent contribution = component contribution / volatility
```

Component contributions reconcile to portfolio volatility within numerical tolerance.

## Attribution

Initial attribution uses starting portfolio weight times asset return. Periods containing trades or external flows are marked as approximate in report limitations.

## ETF Direct, Indirect, And Effective Exposure

For a company `i`, direct exposure is the current market value held outside an ETF. For ETF `f`,
constituent-level indirect exposure is:

```text
indirect exposure(i, f) = ETF market value(f) * constituent weight(i, f)
```

Effective company exposure is direct exposure plus indirect exposure from every held ETF. All
weights are decimal fractions. ETF wrapper values remain visible as direct holdings but have zero
effective company value after successful look-through, preventing double counting. If retrieval
fails, the wrapper is retained as an effective unknown security and a warning is emitted.

Totals below 100% are reconciled with explicit `OTHER`; cash is explicit `CASH`. Totals up to the
configured tolerance above 100% are normalized to 100%, while larger totals are rejected. Duplicate
symbols are combined by default; providers may request rejection instead.

## Effective Sector Exposure

Direct companies use the local asset classification. Each ETF uses one method:

1. `constituent`: all reported security constituents have sectors, so indirect values are assigned
   individually.
2. `etf_sector_allocation`: constituent sectors are incomplete and the provider supplies a
   fund-level allocation; the fund value is multiplied by those weights.
3. `unclassified`: neither source is available, so fund value is assigned to `Unknown` and warned.

The method accompanies every sector result. Using one method per ETF prevents double counting.
Sector values reconcile to invested value when provider weights reconcile.

## ETF Overlap

Let `w(A,i)` and `w(B,i)` be weights of security `i` in ETFs A and B:

```text
overlap(A, B) = sum(i in intersection(A, B)) min(w(A,i), w(B,i))
```

This is symmetric, ranges from zero to one for valid normalized compositions, and is 100% for
identical fully reported funds. Cash and `OTHER` are excluded. Top overlaps are ordered by their
individual `min` contribution. Sector overlap applies the same formula after aggregating
constituents by sector; it can differ from a provider's separate sector table.

## Effective Concentration

Company and sector warning weights use total portfolio value, including portfolio cash. HHI uses
effective non-cash security values normalized across invested exposure:

```text
p_i = effective value_i / sum(effective non-cash security values)
HHI = sum(p_i ^ 2)
effective number of holdings = 1 / HHI
```

A single holding has HHI 1. Equal exposure to `N` companies has HHI `1/N`. `OTHER` remains in HHI
because it is real unreconciled invested exposure and is not assumed to be diversified. Warning
thresholds for company weight, sector weight, and ETF overlap are configurable; warnings are not
investment recommendations.

## Composition Freshness And Limitations

Provenance includes provider, as-of date, retrieval time, quality, fallback, and stale status. Cache
TTL determines when refresh is attempted; the stale-after window determines when the underlying
composition date is labeled stale. If stale-cache use is enabled, expired cache data may be returned
after refresh failure and is explicitly marked stale.

ETF disclosures can lag trading, providers may omit small positions, derivatives may not map to
issuers, sector taxonomies differ, and weights move between disclosures. Look-through is therefore
an estimate for the reported date, not a real-time fund ledger. Alpha Vantage access and permissible
use depend on the user's plan and provider terms.

## Scenario Analysis

Scenarios are typed YAML files containing symbol, sector, and asset-type shocks. Shocks are additive. Cash is unchanged by default. No arbitrary expressions are evaluated.
