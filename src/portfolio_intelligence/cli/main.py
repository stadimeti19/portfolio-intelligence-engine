from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console

from portfolio_intelligence.cli.doctor import run_doctor
from portfolio_intelligence.cli.formatting import money, pct, print_json, table
from portfolio_intelligence.cli.setup import run_setup
from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.settings import Settings, load_settings
from portfolio_intelligence.config.user_config import write_default_config
from portfolio_intelligence.providers.market_data.cache import MarketDataCache
from portfolio_intelligence.providers.market_data.errors import MarketDataError
from portfolio_intelligence.providers.market_data.factory import (
    build_market_data_provider,
)
from portfolio_intelligence.providers.market_data.factory import (
    provider_status as load_provider_status,
)
from portfolio_intelligence.providers.portfolio.base import PortfolioSource
from portfolio_intelligence.providers.portfolio.csv_source import CsvPortfolioSource
from portfolio_intelligence.providers.portfolio.demo import DemoPortfolioSource
from portfolio_intelligence.sdk import PortfolioAnalyzer
from portfolio_intelligence.services.report_service import ReportService
from portfolio_intelligence.storage.database import engine_from_url
from portfolio_intelligence.storage.schema import initialize_database

app = typer.Typer(help="Portfolio Intelligence & Risk Engine")
scenario_app = typer.Typer(help="Scenario analysis commands")
sync_app = typer.Typer(help="Synchronize market data")
app.add_typer(scenario_app, name="scenario")
app.add_typer(sync_app, name="sync")
console = Console()
_UTC = timezone.utc  # noqa: UP017 - keep local test environments on Python 3.10 working.


def _settings() -> Settings:
    return load_settings()


def _portfolio_source(settings: Settings) -> PortfolioSource:
    if settings.portfolio_source.lower() == "demo":
        return DemoPortfolioSource()
    return CsvPortfolioSource(settings.portfolio_csv_path)


def _analyzer() -> PortfolioAnalyzer:
    settings = _settings()
    market_data = build_market_data_provider(settings)
    return PortfolioAnalyzer(_portfolio_source(settings), market_data)


def _portfolio_symbols(settings: Settings) -> tuple[list[str], date]:
    transactions = _portfolio_source(settings).load_transactions()
    symbols = sorted({tx.symbol for tx in transactions if tx.symbol})
    start = min(
        (tx.effective_date for tx in transactions),
        default=date.today() - timedelta(days=365),
    )
    return symbols, start


@app.callback(invoke_without_command=True)
def root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())


@app.command()
def setup(reset: bool = typer.Option(False, "--reset", help="Overwrite existing config.")) -> None:
    console.print(run_setup(reset=reset))


@app.command()
def init() -> None:
    paths = AppPaths()
    paths.create()
    write_default_config(paths, overwrite=False)
    initialize_database(engine_from_url(f"sqlite:///{paths.database_file}"))
    console.print(f"Initialized portfolio intelligence workspace at {paths.base_dir}")


@app.command()
def doctor(format: str = typer.Option("table", "--format")) -> None:
    checks = run_doctor()
    if format == "json":
        print_json(
            [
                {"status": status, "check": check, "detail": detail}
                for status, check, detail in checks
            ]
        )
        return
    rows = [[f"[{status}]", check, detail] for status, check, detail in checks]
    table("Doctor", ["Status", "Check", "Detail"], rows)
    if any(status == "FAIL" for status, _, _ in checks):
        raise typer.Exit(1)
    console.print("System is ready in offline mode.")


@sync_app.callback(invoke_without_command=True)
def sync_root(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        _sync_prices(symbol=None)
        _sync_corporate_actions(symbol=None)


@sync_app.command("prices")
def sync_prices(symbol: str | None = typer.Option(None, "--symbol")) -> None:
    _sync_prices(symbol=symbol)


@sync_app.command("corporate-actions")
def sync_corporate_actions(symbol: str | None = typer.Option(None, "--symbol")) -> None:
    _sync_corporate_actions(symbol=symbol)


def _sync_prices(symbol: str | None) -> None:
    settings = _settings()
    symbols, start = _portfolio_symbols(settings)
    if symbol:
        symbols = [symbol.upper()]
        if start > date.today() - timedelta(days=365):
            start = date.today() - timedelta(days=365)
    provider = build_market_data_provider(settings)
    rows: list[list[str]] = []
    for item in symbols:
        try:
            bars = provider.get_daily_prices(item, start, date.today())
        except MarketDataError as exc:
            rows.append([item, "FAIL", str(exc)])
        else:
            latest = bars[-1].trading_date.isoformat() if bars else "n/a"
            rows.append([item, "OK", f"{len(bars)} bars through {latest}"])
    table("Price sync", ["Symbol", "Status", "Detail"], rows)
    if any(row[1] == "FAIL" for row in rows):
        raise typer.Exit(1)


def _sync_corporate_actions(symbol: str | None) -> None:
    settings = _settings()
    symbols, start = _portfolio_symbols(settings)
    if symbol:
        symbols = [symbol.upper()]
        if start > date.today() - timedelta(days=365):
            start = date.today() - timedelta(days=365)
    provider = build_market_data_provider(settings)
    rows: list[list[str]] = []
    for item in symbols:
        try:
            dividends = provider.get_dividends(item, start, date.today())
            splits = provider.get_splits(item, start, date.today())
        except MarketDataError as exc:
            rows.append([item, "FAIL", str(exc)])
        else:
            rows.append([item, "OK", f"{len(dividends)} dividends, {len(splits)} splits"])
    table("Corporate-action sync", ["Symbol", "Status", "Detail"], rows)
    if any(row[1] == "FAIL" for row in rows):
        raise typer.Exit(1)


@app.command("data-status")
def data_status(format: str = typer.Option("table", "--format")) -> None:
    paths = AppPaths()
    cache = MarketDataCache(paths.cache_dir / "market-data")
    statuses = cache.statuses()
    settings = _settings()
    if not statuses and settings.market_data_provider.lower() in {"demo", "csv"}:
        payload = _uncached_data_status(settings)
    else:
        payload = [
            {
                "symbol": status.symbol,
                "provider": status.provider,
                "endpoint": status.endpoint,
                "first_date": status.first_date,
                "latest_date": status.latest_date,
                "retrieval_time": status.retrieval_timestamp,
                "age": _age(status.retrieval_timestamp),
                "cache_status": status.cache_status,
                "fallback": status.fallback,
                "stale_warning": "stale cache entry" if status.stale else "",
            }
            for status in statuses
        ]
    if format == "json":
        print_json(payload)
        return
    table(
        "Market data status",
        [
            "Symbol",
            "Provider",
            "Endpoint",
            "First date",
            "Latest date",
            "Retrieved",
            "Age",
            "Cache",
            "Fallback",
            "Stale warning",
        ],
        [
            [
                str(row["symbol"]),
                str(row["provider"]),
                str(row["endpoint"]),
                str(row["first_date"] or "n/a"),
                str(row["latest_date"] or "n/a"),
                str(row["retrieval_time"] or "n/a"),
                str(row["age"]),
                str(row["cache_status"]),
                "yes" if row["fallback"] else "no",
                str(row["stale_warning"]),
            ]
            for row in payload
        ],
    )


@app.command("provider-status")
def provider_status(format: str = typer.Option("table", "--format")) -> None:
    statuses = load_provider_status(_settings())
    if format == "json":
        print_json(statuses)
        return
    table(
        "Provider status",
        ["Role", "Provider", "Status", "Detail"],
        [[item["role"], item["provider"], item["status"], item["detail"]] for item in statuses],
    )


def _uncached_data_status(settings: Settings) -> list[dict[str, object]]:
    symbols, start = _portfolio_symbols(settings)
    provider = build_market_data_provider(settings)
    rows: list[dict[str, object]] = []
    for symbol in symbols:
        try:
            bars = provider.get_daily_prices(symbol, start, date.today())
        except MarketDataError as exc:
            rows.append(
                {
                    "symbol": symbol,
                    "provider": provider.name,
                    "endpoint": "prices",
                    "first_date": None,
                    "latest_date": None,
                    "retrieval_time": None,
                    "age": "n/a",
                    "cache_status": f"unavailable: {exc}",
                    "fallback": False,
                    "stale_warning": "",
                }
            )
            continue
        rows.append(
            {
                "symbol": symbol,
                "provider": provider.name,
                "endpoint": "prices",
                "first_date": bars[0].trading_date if bars else None,
                "latest_date": bars[-1].trading_date if bars else None,
                "retrieval_time": None,
                "age": "n/a",
                "cache_status": "uncached",
                "fallback": any(bar.fallback for bar in bars),
                "stale_warning": "",
            }
        )
    return rows


def _age(value: datetime | None) -> str:
    if value is None:
        return "n/a"
    current = value if value.tzinfo else value.replace(tzinfo=_UTC)
    delta = datetime.now(_UTC) - current
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{int(delta.total_seconds() // 60)}m"
    if hours < 48:
        return f"{hours:.1f}h"
    return f"{hours / 24:.1f}d"


@app.command("import-transactions")
def import_transactions(
    path: Path,
    dry_run: bool = typer.Option(False, "--dry-run"),
    format: str = typer.Option("table", "--format"),
) -> None:
    source = CsvPortfolioSource(path)
    transactions, errors = source.parse()
    payload = {
        "path": str(path),
        "valid_transactions": len(transactions),
        "errors": [error.__dict__ for error in errors],
        "dry_run": dry_run,
    }
    if format == "json":
        print_json(payload)
        return
    if errors:
        table(
            "Import errors", ["Line", "Message"], [[str(e.line_number), e.message] for e in errors]
        )
        raise typer.Exit(1)
    console.print(f"Validated {len(transactions)} transactions from {path}")
    if dry_run:
        console.print("Dry run only. No data was written.")


@app.command()
def holdings(format: str = typer.Option("table", "--format")) -> None:
    report = _analyzer().analyze()
    if format == "json":
        print_json(report.holdings)
        return
    table(
        "Holdings",
        ["Symbol", "Qty", "Avg Cost", "Price", "Value", "Weight", "Realized", "Unrealized"],
        [
            [
                pos.symbol,
                f"{pos.quantity:.4f}",
                money(pos.average_cost),
                money(pos.current_price),
                money(pos.market_value),
                pct(pos.weight),
                money(pos.realized_pnl),
                money(pos.unrealized_pnl),
            ]
            for pos in report.holdings
        ],
    )


@app.command()
def summary(format: str = typer.Option("table", "--format")) -> None:
    report = _analyzer().analyze()
    if format == "json":
        print_json(report.summary)
        return
    rows = [
        ["Portfolio value", money(report.summary.total_value)],
        ["Cash", money(report.summary.cash)],
        ["Cost basis", money(report.summary.cost_basis)],
        ["Realized P&L", money(report.summary.realized_pnl)],
        ["Unrealized P&L", money(report.summary.unrealized_pnl)],
        ["Data date", report.summary.data_date.isoformat()],
        ["Benchmark", report.summary.benchmark],
    ]
    table("Summary", ["Metric", "Value"], rows)


@app.command()
def performance(format: str = typer.Option("table", "--format")) -> None:
    report = _analyzer().analyze()
    if format == "json":
        print_json(report.performance)
        return
    rows = [
        ["Cumulative return", pct(report.performance.cumulative_return)],
        ["Annualized return", pct(report.performance.annualized_return)],
        ["Benchmark return", pct(report.performance.benchmark_return)],
        ["Relative return", pct(report.performance.relative_return)],
        [
            "Sharpe",
            "n/a" if report.performance.sharpe is None else f"{report.performance.sharpe:.3f}",
        ],
        [
            "Sortino",
            "n/a" if report.performance.sortino is None else f"{report.performance.sortino:.3f}",
        ],
        ["Maximum drawdown", pct(report.performance.maximum_drawdown)],
    ]
    table("Performance", ["Metric", "Value"], rows)
    if report.performance.top_contributors:
        table(
            "Top contributors",
            ["Symbol", "Contribution", "Dollar P&L"],
            [
                [
                    str(row["symbol"]),
                    pct(float(row["percentage_point_contribution"])),
                    money(float(row["dollar_pnl_contribution"])),
                ]
                for row in report.performance.top_contributors
            ],
        )


@app.command()
def risk(format: str = typer.Option("table", "--format")) -> None:
    report = _analyzer().analyze()
    if format == "json":
        print_json(report.risk)
        return
    rows = [
        ["Annualized volatility", pct(report.risk.annualized_volatility)],
        ["Beta", "n/a" if report.risk.beta is None else f"{report.risk.beta:.3f}"],
        ["Historical VaR", pct(report.risk.historical_var)],
        ["Expected Shortfall", pct(report.risk.expected_shortfall)],
    ]
    table("Risk", ["Metric", "Value"], rows)
    if report.risk.risk_contribution:
        table(
            "Risk contribution",
            ["Symbol", "Component", "Percent"],
            [
                [str(row["symbol"]), f"{float(row['component']):.4f}", pct(float(row["percent"]))]
                for row in report.risk.risk_contribution
            ],
        )
    for warning in report.risk.concentration_warnings:
        console.print(f"[yellow]WARN[/yellow] {warning}")


@app.command()
def exposure(format: str = typer.Option("table", "--format")) -> None:
    report = _analyzer().analyze()
    if format == "json":
        print_json(report.exposure)
        return
    for name, values in report.exposure.items():
        table(
            name.replace("_", " ").title(),
            ["Name", "Weight"],
            [[key, pct(value)] for key, value in values.items()],
        )


@app.command()
def correlations(format: str = typer.Option("table", "--format")) -> None:
    report = _analyzer().analyze()
    if format == "json":
        print_json(report.correlations)
        return
    symbols = list(report.correlations)
    rows = [
        [symbol, *[f"{report.correlations[symbol][other]:.2f}" for other in symbols]]
        for symbol in symbols
    ]
    table("Correlations", ["Symbol", *symbols], rows)


@scenario_app.command("list")
def scenario_list(format: str = typer.Option("table", "--format")) -> None:
    scenarios = PortfolioAnalyzer.demo().list_scenarios()
    if format == "json":
        print_json({name: scenario.model_dump(mode="json") for name, scenario in scenarios.items()})
        return
    table(
        "Scenarios",
        ["Name", "Description"],
        [[name, scenario.description] for name, scenario in scenarios.items()],
    )


@scenario_app.command("run")
def scenario_run(name: str, format: str = typer.Option("table", "--format")) -> None:
    result = PortfolioAnalyzer.demo().run_scenario(name)
    if format == "json":
        print_json(result)
        return
    rows = [
        ["Starting value", money(result.starting_value)],
        ["Ending value", money(result.ending_value)],
        ["P&L", money(result.pnl)],
        ["Percent P&L", pct(result.percent_pnl)],
    ]
    table(result.name, ["Metric", "Value"], rows)
    table(
        "Largest impacts",
        ["Symbol", "Shock", "P&L", "Ending value"],
        [
            [impact.symbol, pct(impact.shock), money(impact.pnl), money(impact.ending_value)]
            for impact in result.impacts[:5]
        ],
    )


@app.command()
def report(
    output: Path | None = typer.Option(None, "--output"),
    format: str = typer.Option("json", "--format"),
) -> None:
    analysis = PortfolioAnalyzer.demo().analyze()
    service = ReportService()
    if output:
        path = service.write(analysis, output, fmt=format)
        console.print(f"Wrote report to {path}")
    elif format == "markdown":
        console.print(service.to_markdown(analysis))
    else:
        console.print(service.to_json(analysis))


if __name__ == "__main__":
    app()
