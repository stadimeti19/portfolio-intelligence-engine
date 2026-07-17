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

## Scenario Analysis

Scenarios are typed YAML files containing symbol, sector, and asset-type shocks. Shocks are additive. Cash is unchanged by default. No arbitrary expressions are evaluated.

