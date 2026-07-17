from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from portfolio_intelligence.cli.doctor import run_doctor
from portfolio_intelligence.cli.formatting import money, pct, print_json, table
from portfolio_intelligence.cli.setup import run_setup
from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.user_config import write_default_config
from portfolio_intelligence.providers.portfolio.csv_source import CsvPortfolioSource
from portfolio_intelligence.sdk import PortfolioAnalyzer
from portfolio_intelligence.services.report_service import ReportService
from portfolio_intelligence.storage.database import engine_from_url
from portfolio_intelligence.storage.schema import initialize_database

app = typer.Typer(help="Portfolio Intelligence & Risk Engine")
scenario_app = typer.Typer(help="Scenario analysis commands")
app.add_typer(scenario_app, name="scenario")
console = Console()


def _analyzer(path: str = "data/portfolio.example.csv") -> PortfolioAnalyzer:
    return PortfolioAnalyzer.from_csv(path)


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
