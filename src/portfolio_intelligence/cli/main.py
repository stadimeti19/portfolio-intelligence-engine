from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from itertools import combinations
from pathlib import Path

import typer
from rich.console import Console

from portfolio_intelligence import __version__
from portfolio_intelligence.cli.doctor import run_doctor
from portfolio_intelligence.cli.formatting import money, pct, print_json, table
from portfolio_intelligence.cli.setup import run_setup
from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.settings import Settings, load_settings
from portfolio_intelligence.config.user_config import write_default_config
from portfolio_intelligence.domain.assets import AssetType
from portfolio_intelligence.domain.explanations import ExplanationType, PortfolioExplanation
from portfolio_intelligence.providers.etf.factory import (
    build_etf_composition_provider,
    etf_provider_status,
)
from portfolio_intelligence.providers.explanations.factory import build_explanation_provider
from portfolio_intelligence.providers.market_data.cache import MarketDataCache
from portfolio_intelligence.providers.market_data.demo import DEMO_ASSETS
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
from portfolio_intelligence.providers.portfolio.holdings_snapshot import (
    HoldingsImportResult,
    HoldingSnapshot,
    HoldingsSnapshotSource,
    load_holdings_snapshot,
    parse_pasted_holdings,
    upsert_clean_holding,
    write_clean_holdings,
    write_snapshot_transactions,
)
from portfolio_intelligence.sdk import PortfolioAnalyzer
from portfolio_intelligence.services.etf_exposure_service import calculate_etf_overlap
from portfolio_intelligence.services.explanation_service import prepare_explanation_request
from portfolio_intelligence.services.report_service import ReportService
from portfolio_intelligence.storage.database import engine_from_url
from portfolio_intelligence.storage.schema import initialize_database

app = typer.Typer(help="Portfolio Intelligence & Risk Engine")
scenario_app = typer.Typer(help="Scenario analysis commands")
sync_app = typer.Typer(help="Synchronize market data")
broker_app = typer.Typer(help="Import local brokerage exports")
app.add_typer(scenario_app, name="scenario")
app.add_typer(sync_app, name="sync")
app.add_typer(broker_app, name="import-broker")
console = Console()
_UTC = timezone.utc  # noqa: UP017 - keep local test environments on Python 3.10 working.


def _settings() -> Settings:
    return load_settings()


def _portfolio_source(settings: Settings) -> PortfolioSource:
    source = settings.portfolio_source.lower()
    if source == "demo":
        return DemoPortfolioSource()
    if source == "holdings":
        return HoldingsSnapshotSource(
            settings.portfolio_holdings_path,
            source_format=settings.portfolio_holdings_format,
        )
    return CsvPortfolioSource(settings.portfolio_csv_path)


def _analyzer() -> PortfolioAnalyzer:
    settings = _settings()
    market_data = build_market_data_provider(settings)
    etf_composition = build_etf_composition_provider(settings)
    return PortfolioAnalyzer(
        _portfolio_source(settings),
        market_data,
        etf_composition_provider=etf_composition,
        etf_symbols=set(_portfolio_etf_symbols(settings)),
        position_concentration_threshold=settings.position_concentration_threshold,
        sector_concentration_threshold=settings.sector_concentration_threshold,
        overlap_warning_threshold=settings.etf_overlap_warning_threshold,
    )


def _portfolio_symbols(settings: Settings) -> tuple[list[str], date]:
    transactions = _portfolio_source(settings).load_transactions()
    symbols = sorted({tx.symbol for tx in transactions if tx.symbol})
    start = min(
        (tx.effective_date for tx in transactions),
        default=date.today() - timedelta(days=365),
    )
    return symbols, start


def _version_callback(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback(invoke_without_command=True)
def root(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed version and exit.",
    ),
) -> None:
    del version
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


@sync_app.command("etfs")
def sync_etfs(format: str = typer.Option("table", "--format")) -> None:
    settings = _settings()
    provider = build_etf_composition_provider(settings)
    symbols = _configured_etf_symbols(settings, _portfolio_symbols(settings)[0])
    payload: list[dict[str, object]] = []
    for symbol in symbols:
        try:
            refresh = getattr(provider, "refresh", None)
            if callable(refresh):
                metadata = refresh(symbol)
            else:
                provider.get_holdings(symbol)
                metadata = provider.get_metadata(symbol)
        except Exception as exc:
            payload.append({"symbol": symbol, "status": "FAIL", "detail": str(exc)})
        else:
            payload.append(
                {
                    "symbol": symbol,
                    "status": "OK",
                    "detail": (
                        f"as of {metadata.as_of_date or 'unknown'} via {metadata.provider.value}"
                    ),
                }
            )
    if format == "json":
        print_json(payload)
        return
    table(
        "ETF composition sync",
        ["Symbol", "Status", "Detail"],
        [[str(row["symbol"]), str(row["status"]), str(row["detail"])] for row in payload],
    )
    if any(row["status"] == "FAIL" for row in payload):
        raise typer.Exit(1)


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
    settings = _settings()
    statuses = load_provider_status(settings) + etf_provider_status(settings)
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


@app.command("import-holdings")
def import_holdings(
    path: Path | None = typer.Argument(None),
    source_format: str = typer.Option("auto", "--source-format", help="auto, generic, fidelity"),
    paste: bool = typer.Option(False, "--paste", help="Read a pasted holdings table from stdin."),
    export_clean: Path | None = typer.Option(None, "--export-clean"),
    export_transactions: Path | None = typer.Option(None, "--export-transactions"),
    as_of: str | None = typer.Option(None, "--as-of", help="Snapshot simulation start date."),
    format: str = typer.Option("table", "--format"),
) -> None:
    if paste:
        console.print("Paste holdings table, then press Ctrl-D:")
        result = parse_pasted_holdings(_read_stdin())
    elif path is not None:
        result = load_holdings_snapshot(path, source_format=source_format)
    else:
        raise typer.BadParameter("provide a holdings file path or use --paste")
    _handle_holdings_import(
        result,
        export_clean=export_clean,
        export_transactions=export_transactions,
        as_of=_parse_optional_date(as_of),
        output_format=format,
    )


@app.command("add")
def add_holding(
    symbol: str,
    shares: float = typer.Option(..., "--shares", "--quantity"),
    average_cost: float | None = typer.Option(None, "--average-cost"),
    cost_basis: float | None = typer.Option(None, "--cost-basis"),
    current_price: float | None = typer.Option(None, "--current-price"),
    asset_type: str | None = typer.Option(None, "--asset-type"),
    description: str | None = typer.Option(None, "--description"),
    output: Path = typer.Option(Path("data/holdings.csv"), "--output"),
) -> None:
    holding = HoldingSnapshot(
        symbol=symbol,
        quantity=shares,
        average_cost_basis=average_cost,
        cost_basis_total=cost_basis,
        current_price=current_price,
        asset_type=asset_type,
        description=description,
    )
    upsert_clean_holding(output, holding)
    console.print(f"Saved {holding.symbol} to {output}")


@app.command("holdings-wizard")
def holdings_wizard(
    output: Path = typer.Option(Path("data/holdings.csv"), "--output"),
) -> None:
    holdings: list[HoldingSnapshot] = []
    if output.exists():
        existing = load_holdings_snapshot(output, source_format="generic")
        if existing.errors:
            _handle_holdings_import(
                existing,
                export_clean=None,
                export_transactions=None,
                as_of=None,
                output_format="table",
            )
        holdings.extend(existing.holdings)
    console.print("Enter holdings. Average cost is optional if you provide current price.")
    while True:
        symbol = typer.prompt("Symbol").strip()
        shares = float(typer.prompt("Shares"))
        average_cost_text = typer.prompt("Average cost", default="", show_default=False)
        current_price_text = typer.prompt("Current price", default="", show_default=False)
        asset_type = typer.prompt("Type", default="", show_default=False).strip() or None
        holding = HoldingSnapshot(
            symbol=symbol,
            quantity=shares,
            average_cost_basis=_optional_float(average_cost_text),
            current_price=_optional_float(current_price_text),
            asset_type=asset_type,
        )
        holdings.append(holding)
        if not typer.confirm("Add another holding?", default=True):
            break
    write_clean_holdings(output, holdings)
    console.print(f"Wrote {len(holdings)} holdings to {output}")


@broker_app.command("fidelity")
def import_fidelity(
    path: Path,
    export_clean: Path | None = typer.Option(None, "--export-clean"),
    export_transactions: Path | None = typer.Option(None, "--export-transactions"),
    as_of: str | None = typer.Option(None, "--as-of", help="Snapshot simulation start date."),
    format: str = typer.Option("table", "--format"),
) -> None:
    result = load_holdings_snapshot(path, source_format="fidelity")
    _handle_holdings_import(
        result,
        export_clean=export_clean,
        export_transactions=export_transactions,
        as_of=_parse_optional_date(as_of),
        output_format=format,
    )


def _handle_holdings_import(
    result: HoldingsImportResult,
    *,
    export_clean: Path | None,
    export_transactions: Path | None,
    as_of: date | None,
    output_format: str,
) -> None:
    payload = {
        "source_format": result.source_format,
        "valid_holdings": len(result.holdings),
        "errors": [error.__dict__ for error in result.errors],
        "retained_columns": result.retained_columns,
        "ignored_columns": result.ignored_columns,
        "symbols": [holding.symbol for holding in result.holdings],
        "total_cost_basis": result.total_cost_basis if not result.errors else None,
        "export_clean": str(export_clean) if export_clean else None,
        "export_transactions": str(export_transactions) if export_transactions else None,
    }
    if result.errors:
        if output_format == "json":
            print_json(payload)
        else:
            table(
                "Holdings import errors",
                ["Line", "Message"],
                [[str(error.line_number), error.message] for error in result.errors],
            )
        raise typer.Exit(1)
    if export_clean:
        write_clean_holdings(export_clean, result.holdings)
    if export_transactions:
        write_snapshot_transactions(
            export_transactions,
            result.holdings,
            as_of=as_of or date.today() - timedelta(days=365),
        )
    if output_format == "json":
        print_json(payload)
        return
    console.print(f"Detected {result.source_format} holdings export")
    table(
        "Holdings preview",
        ["Symbol", "Quantity", "Average Cost", "Cost Basis", "Type"],
        [
            [
                holding.symbol,
                f"{holding.quantity:.6g}",
                money(holding.average_cost_basis or holding.synthetic_purchase_price),
                money(
                    holding.cost_basis_total or holding.synthetic_purchase_price * holding.quantity
                ),
                holding.asset_type or "n/a",
            ]
            for holding in result.holdings
        ],
    )
    table("Fields retained", ["Column"], [[column] for column in result.retained_columns])
    table("Fields ignored", ["Column"], [[column] for column in result.ignored_columns])
    if export_clean:
        console.print(f"Wrote clean holdings to {export_clean}")
    if export_transactions:
        console.print(f"Wrote snapshot transactions to {export_transactions}")


def _parse_optional_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _read_stdin() -> str:
    import sys

    return sys.stdin.read()


def _optional_float(value: str) -> float | None:
    text = value.strip()
    return float(text) if text else None


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
def exposure(
    look_through: bool = typer.Option(False, "--look-through"),
    security: bool = typer.Option(False, "--security"),
    sector: bool = typer.Option(False, "--sector"),
    format: str = typer.Option("table", "--format"),
) -> None:
    report = _analyzer().analyze()
    effective = report.etf_exposure
    if look_through or security or sector:
        if effective is None:
            raise typer.BadParameter("ETF exposure analysis is unavailable")
        if format == "json":
            if security and not sector:
                print_json(effective.securities)
            elif sector and not security:
                print_json(effective.sectors)
            else:
                print_json(effective)
            return
        if not sector:
            table(
                "Effective security exposure",
                ["Security", "Direct", "Indirect", "Effective", "ETFs", "As of"],
                [
                    [
                        item.symbol,
                        pct(item.direct_weight),
                        pct(item.indirect_weight),
                        pct(item.effective_weight),
                        ", ".join(sorted(item.contributing_etfs)) or "-",
                        ", ".join(day.isoformat() for day in item.as_of_dates) or "-",
                    ]
                    for item in effective.securities
                ],
            )
        if not security:
            table(
                "Effective sector exposure",
                ["Sector", "Weight", "Method"],
                [
                    [
                        item.sector,
                        pct(item.weight),
                        ", ".join(method.value for method in item.methods),
                    ]
                    for item in effective.sectors
                ],
            )
        if effective.concentration and not (security or sector):
            table(
                "Concentration",
                ["Metric", "Value"],
                [
                    [
                        "Largest effective security",
                        pct(effective.concentration.largest_security_weight),
                    ],
                    [
                        "Largest effective sector",
                        pct(effective.concentration.largest_sector_weight),
                    ],
                    ["HHI", f"{effective.concentration.hhi:.4f}"],
                    [
                        "Effective holdings",
                        f"{effective.concentration.effective_number_of_holdings:.2f}",
                    ],
                ],
            )
        for warning in effective.warnings:
            console.print(f"[yellow]WARN[/yellow] {warning}")
        return
    if format == "json":
        print_json(report.exposure)
        return
    for name, values in report.exposure.items():
        table(
            name.replace("_", " ").title(),
            ["Name", "Weight"],
            [[key, pct(value)] for key, value in values.items()],
        )


@app.command("etf-overlap")
def etf_overlap(
    left: str | None = typer.Argument(None),
    right: str | None = typer.Argument(None),
    format: str = typer.Option("table", "--format"),
) -> None:
    if (left is None) != (right is None):
        raise typer.BadParameter("provide both ETF symbols or neither")
    settings = _settings()
    provider = build_etf_composition_provider(settings)
    if left and right:
        pairs = [(left.upper(), right.upper())]
    else:
        symbols = _configured_etf_symbols(settings, _portfolio_symbols(settings)[0])
        pairs = list(combinations(symbols, 2))
    results = [
        calculate_etf_overlap(
            first,
            second,
            provider.get_holdings(first),
            provider.get_holdings(second),
        )
        for first, second in pairs
    ]
    if format == "json":
        print_json([item.model_dump(mode="json") for item in results])
        return
    table(
        "ETF overlap",
        ["ETF pair", "Shared", "Weighted overlap", "Sector overlap", "Top overlaps"],
        [
            [
                f"{item.left_symbol} / {item.right_symbol}",
                str(len(item.shared_constituents)),
                pct(item.weighted_overlap),
                pct(item.sector_overlap),
                ", ".join(str(row["symbol"]) for row in item.top_overlapping_securities[:5]) or "-",
            ]
            for item in results
        ],
    )


def _configured_etf_symbols(settings: Settings, portfolio_symbols: list[str]) -> list[str]:
    detected = {
        symbol
        for symbol in portfolio_symbols
        if DEMO_ASSETS.get(symbol) and DEMO_ASSETS[symbol].asset_type == AssetType.ETF
    }
    return sorted(detected | set(_portfolio_etf_symbols(settings)))


def _portfolio_etf_symbols(settings: Settings) -> list[str]:
    detected = set(settings.etf_symbols)
    portfolio_symbols, _ = _portfolio_symbols(settings)
    detected.update(
        symbol
        for symbol in portfolio_symbols
        if DEMO_ASSETS.get(symbol) and DEMO_ASSETS[symbol].asset_type == AssetType.ETF
    )
    if settings.portfolio_source.lower() == "holdings":
        result = load_holdings_snapshot(
            settings.portfolio_holdings_path,
            source_format=settings.portfolio_holdings_format,
        )
        detected.update(
            holding.symbol
            for holding in result.holdings
            if holding.asset_type and "ETF" in holding.asset_type.upper()
        )
    return sorted(detected)


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
    format: str | None = typer.Option(None, "--format"),
    scenario: str | None = typer.Option(None, "--scenario"),
) -> None:
    analyzer = _analyzer()
    analysis = analyzer.analyze()
    if scenario:
        analysis = analysis.model_copy(
            update={"scenario_results": [analyzer.run_scenario(scenario)]}
        )
    service = ReportService()
    if output:
        selected_format = format or (
            "html" if output.suffix.lower() in {".html", ".htm"} else "json"
        )
        path = service.write(analysis, output, fmt=selected_format)
        console.print(f"Wrote report to {path}")
    elif format == "markdown":
        console.print(service.to_markdown(analysis))
    elif format == "html":
        console.print(service.to_html(analysis))
    else:
        console.print(service.to_json(analysis))


@app.command("explain")
def explain(
    focus: str | None = typer.Argument(
        None,
        help=(
            "summary, performance, benchmark, attribution, risk, concentration, etf-overlap, "
            "scenario, rebalance, or limitations"
        ),
    ),
    scenario_name: str | None = typer.Argument(
        None, help="Scenario name; required only when focus is scenario."
    ),
    force: bool = typer.Option(False, "--force", help="Bypass the local explanation cache."),
    format: str = typer.Option("table", "--format"),
) -> None:
    """Explain already-computed analytics without changing them."""

    explanation_type = _explanation_type(focus)
    if explanation_type == ExplanationType.SCENARIO and not scenario_name:
        raise typer.BadParameter(
            "provide a scenario name, for example: portfolio explain scenario tech-selloff"
        )
    if explanation_type != ExplanationType.SCENARIO and scenario_name:
        raise typer.BadParameter(
            "a scenario name is only valid with `portfolio explain scenario <name>`"
        )

    settings = _settings()
    analyzer = _analyzer()
    analysis = analyzer.analyze()
    if scenario_name:
        analysis = analysis.model_copy(
            update={"scenario_results": [analyzer.run_scenario(scenario_name)]}
        )
    request = prepare_explanation_request(
        analysis,
        explanation_type,
        send_dollar_values=settings.openai_send_dollar_values,
        max_input_tokens=settings.openai_max_input_tokens,
        force=force,
    )
    explanation = build_explanation_provider(settings).explain(request)
    if format == "json":
        print_json(explanation.model_dump(mode="json"))
        return
    _print_explanation(explanation)


def _explanation_type(value: str | None) -> ExplanationType:
    if value is None:
        return ExplanationType.SUMMARY
    aliases = {
        "overall": "summary",
        "return-attribution": "attribution",
        "rebalancing": "rebalance",
    }
    normalized = aliases.get(value.strip().lower(), value.strip().lower())
    try:
        return ExplanationType(normalized)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ExplanationType)
        raise typer.BadParameter(
            f"unknown explanation focus {value!r}; choose one of: {allowed}"
        ) from exc


def _print_explanation(explanation: PortfolioExplanation) -> None:
    console.print(explanation.summary)
    sections = [
        ("Return drivers", explanation.return_drivers),
        ("Risk findings", explanation.risk_findings),
        ("Scenario findings", explanation.scenario_findings),
        ("Limitations", explanation.limitations),
    ]
    for title, findings in sections:
        if findings:
            console.print(f"\n[bold]{title}[/bold]")
            for finding in findings:
                console.print(f"- {finding}")


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", min=1, max=65535),
    address: str = typer.Option("localhost", "--address"),
) -> None:
    from portfolio_intelligence.dashboard.launcher import (
        DashboardDependencyError,
        launch_dashboard,
    )

    try:
        return_code = launch_dashboard(port=port, address=address)
    except DashboardDependencyError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if return_code:
        raise typer.Exit(return_code)


if __name__ == "__main__":
    app()
