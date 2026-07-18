from __future__ import annotations

from datetime import date
from pathlib import Path

from portfolio_intelligence.providers.market_data.csv_provider import CsvMarketDataProvider
from portfolio_intelligence.providers.portfolio.csv_source import CsvPortfolioSource


def test_csv_source_preserves_stable_order_and_reports_duplicate(tmp_path: Path) -> None:
    path = tmp_path / "transactions.csv"
    path.write_text(
        "\n".join(
            [
                "transaction_id,date,type,symbol,quantity,price,fee,currency",
                "d1,2025-01-01,DEPOSIT,,0,1000,0,USD",
                "b1,2025-01-02,BUY,ABC,1,10,0,USD",
                "b1,2025-01-02,BUY,ABC,1,10,0,USD",
            ]
        ),
        encoding="utf-8",
    )
    transactions, errors = CsvPortfolioSource(path).parse()
    assert [tx.transaction_id for tx in transactions] == ["d1", "b1"]
    assert errors[0].line_number == 4
    assert "duplicate" in errors[0].message


def test_csv_source_line_specific_validation(tmp_path: Path) -> None:
    path = tmp_path / "transactions.csv"
    path.write_text(
        "\n".join(
            [
                "transaction_id,date,type,symbol,quantity,price,fee,currency",
                "b1,2025-01-02,BUY,,1,10,0,USD",
            ]
        ),
        encoding="utf-8",
    )
    _, errors = CsvPortfolioSource(path).parse()
    assert errors
    assert errors[0].line_number == 2


def test_csv_source_rejects_empty_transaction_ids(tmp_path: Path) -> None:
    path = tmp_path / "transactions.csv"
    path.write_text(
        "\n".join(
            [
                "transaction_id,date,type,symbol,quantity,price,fee,currency",
                ",2025-01-02,DEPOSIT,,0,100,0,USD",
            ]
        ),
        encoding="utf-8",
    )
    _, errors = CsvPortfolioSource(path).parse()
    assert errors
    assert "transaction_id is required" in errors[0].message


def test_csv_market_data_provider_rejects_duplicate_price_dates(tmp_path: Path) -> None:
    path = tmp_path / "ABC.csv"
    path.write_text(
        "\n".join(
            [
                "date,open,high,low,close,adjusted_close,volume",
                "2025-01-02,10,11,9,10,10,1000",
                "2025-01-02,10,11,9,10,10,1000",
            ]
        ),
        encoding="utf-8",
    )
    provider = CsvMarketDataProvider(tmp_path)
    try:
        provider.get_daily_prices(
            "ABC", date.fromisoformat("2025-01-01"), date.fromisoformat("2025-01-03")
        )
    except ValueError as exc:
        assert "duplicate price row" in str(exc)
    else:
        raise AssertionError("duplicate price row was not rejected")
