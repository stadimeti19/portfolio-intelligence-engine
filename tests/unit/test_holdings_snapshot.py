from __future__ import annotations

from datetime import date
from pathlib import Path

from portfolio_intelligence.providers.portfolio.holdings_snapshot import (
    HoldingSnapshot,
    HoldingsSnapshotSource,
    load_holdings_snapshot,
    parse_pasted_holdings,
    upsert_clean_holding,
    write_clean_holdings,
    write_snapshot_transactions,
)


def test_fidelity_positions_export_keeps_only_whitelisted_fields(tmp_path: Path) -> None:
    raw = tmp_path / "fidelity_positions.csv"
    raw.write_text(
        "\t".join(
            [
                "Account name",
                "Symbol",
                "Description",
                "Quantity",
                "Last price",
                "Last price change",
                "Current value",
                "Today's gain/loss dollar",
                "Today's gain/loss percent",
                "Total gain/loss dollar",
                "Total gain/loss percent",
                "Percent of account",
                "Cost basis total",
                "Average cost basis",
                "Type",
            ]
        )
        + "\n"
        + "\t".join(
            [
                "Personal Roth IRA 1234",
                "AAPL",
                "APPLE INC",
                "10",
                "$200.00",
                "$1.00",
                "$2,000.00",
                "$10.00",
                "0.50%",
                "$200.00",
                "11.11%",
                "25.00%",
                "$1,800.00",
                "$180.00",
                "Stock",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = load_holdings_snapshot(raw, source_format="fidelity")

    assert result.errors == []
    assert result.source_format == "fidelity"
    assert result.holdings[0].symbol == "AAPL"
    assert result.holdings[0].quantity == 10
    assert result.holdings[0].average_cost_basis == 180
    assert "Account name" in result.ignored_columns
    assert "Last price change" in result.ignored_columns

    clean = tmp_path / "clean_holdings.csv"
    write_clean_holdings(clean, result.holdings)
    clean_text = clean.read_text(encoding="utf-8")
    assert "AAPL" in clean_text
    assert "Personal Roth IRA" not in clean_text
    assert "1234" not in clean_text


def test_holdings_snapshot_source_creates_synthetic_transactions(tmp_path: Path) -> None:
    holdings = tmp_path / "holdings.csv"
    holdings.write_text(
        "\n".join(
            [
                "symbol,quantity,average_cost,asset_type,currency",
                "AAPL,10,180,Stock,USD",
                "VOO,5,470,ETF,USD",
            ]
        ),
        encoding="utf-8",
    )

    transactions = HoldingsSnapshotSource(
        holdings, source_format="generic", snapshot_start=date(2025, 1, 2)
    ).load_transactions()

    assert [transaction.transaction_type.value for transaction in transactions] == [
        "DEPOSIT",
        "BUY",
        "BUY",
    ]
    assert transactions[0].price == 4150
    assert transactions[1].symbol == "AAPL"
    assert transactions[2].symbol == "VOO"


def test_write_snapshot_transactions_csv(tmp_path: Path) -> None:
    holdings = tmp_path / "holdings.csv"
    holdings.write_text(
        "\n".join(["symbol,quantity,average_cost", "MSFT,3,410"]),
        encoding="utf-8",
    )
    result = load_holdings_snapshot(holdings, source_format="generic")

    output = tmp_path / "snapshot_transactions.csv"
    write_snapshot_transactions(output, result.holdings, as_of=date(2025, 1, 2))

    text = output.read_text(encoding="utf-8")
    assert "snapshot-deposit-2025-01-02" in text
    assert "snapshot-buy-MSFT-1" in text


def test_parse_pasted_holdings_table() -> None:
    result = parse_pasted_holdings(
        "\n".join(
            [
                "Symbol\tQuantity\tAverage Cost\tType",
                "AAPL\t10\t185.20\tStock",
                "VOO\t5\t470.00\tETF",
            ]
        )
    )

    assert result.errors == []
    assert result.source_format == "paste"
    assert [holding.symbol for holding in result.holdings] == ["AAPL", "VOO"]
    assert result.holdings[0].average_cost_basis == 185.20


def test_upsert_clean_holding_replaces_existing_symbol(tmp_path: Path) -> None:
    output = tmp_path / "holdings.csv"
    upsert_clean_holding(
        output,
        HoldingSnapshot(symbol="AAPL", quantity=10, average_cost_basis=180),
    )
    upsert_clean_holding(
        output,
        HoldingSnapshot(symbol="AAPL", quantity=12, average_cost_basis=181),
    )

    result = load_holdings_snapshot(output, source_format="generic")

    assert len(result.holdings) == 1
    assert result.holdings[0].quantity == 12
    assert result.holdings[0].average_cost_basis == 181
