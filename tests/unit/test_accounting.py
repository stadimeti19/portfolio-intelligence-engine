from __future__ import annotations

from datetime import date

import pytest

from portfolio_intelligence.accounting.ledger import PortfolioLedger
from portfolio_intelligence.domain.transactions import Transaction
from portfolio_intelligence.providers.market_data.demo import DemoMarketDataProvider
from portfolio_intelligence.services.portfolio_service import PortfolioService


def tx(transaction_id: str, day: str, type_: str, **kwargs) -> Transaction:
    return Transaction.model_validate(
        {
            "transaction_id": transaction_id,
            "effective_date": date.fromisoformat(day),
            "type": type_,
            "currency": "USD",
            "source": "test",
            "import_order": kwargs.pop("import_order", 1),
            **kwargs,
        }
    )


def test_average_cost_partial_sale_realized_pnl_and_cash() -> None:
    transactions = [
        tx("d1", "2025-01-01", "DEPOSIT", price=1_000.0),
        tx("b1", "2025-01-02", "BUY", symbol="ABC", quantity=10, price=20.0, fee=1.0),
        tx("b2", "2025-01-03", "BUY", symbol="ABC", quantity=10, price=30.0, fee=1.0),
        tx("s1", "2025-01-04", "SELL", symbol="ABC", quantity=5, price=40.0, fee=1.0),
    ]
    state = PortfolioLedger().build(transactions)
    lot = state.lots["ABC"]
    assert lot.quantity == pytest.approx(15)
    assert lot.average_cost == pytest.approx(25.1)
    assert lot.realized_pnl == pytest.approx(73.5)
    assert state.cash == pytest.approx(697.0)


def test_deposits_are_external_cash_flows() -> None:
    transactions = [
        tx("d1", "2025-01-01", "DEPOSIT", price=1_000.0),
        tx("d2", "2025-01-02", "DEPOSIT", price=500.0),
    ]
    state = PortfolioLedger().build(transactions)
    assert state.cash == 1_500.0
    assert state.external_cash_flows[date(2025, 1, 1)] == 1_000.0
    assert state.external_cash_flows[date(2025, 1, 2)] == 500.0


def test_withdrawals_dividends_and_fees_update_cash_consistently() -> None:
    transactions = [
        tx("d1", "2025-01-01", "DEPOSIT", price=1_000.0, import_order=1),
        tx("b1", "2025-01-02", "BUY", symbol="ABC", quantity=10, price=20.0, fee=2.0),
        tx("div1", "2025-01-03", "DIVIDEND", symbol="ABC", price=12.5, import_order=3),
        tx("fee1", "2025-01-04", "FEE", price=3.0, fee=1.0, import_order=4),
        tx("w1", "2025-01-05", "WITHDRAWAL", price=100.0, import_order=5),
    ]
    state = PortfolioLedger().build(transactions)
    assert state.cash == pytest.approx(706.5)
    assert state.dividends == pytest.approx(12.5)
    assert state.fees == pytest.approx(6.0)
    assert state.external_cash_flows[date(2025, 1, 5)] == pytest.approx(-100.0)


def test_duplicate_transactions_and_nondeterministic_order_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate transaction_id"):
        PortfolioLedger().build(
            [
                tx("d1", "2025-01-01", "DEPOSIT", price=1_000.0, import_order=1),
                tx("d1", "2025-01-02", "DEPOSIT", price=1_000.0, import_order=2),
            ]
        )
    with pytest.raises(ValueError, match="deterministically ordered"):
        PortfolioLedger().build(
            [
                tx("d2", "2025-01-02", "DEPOSIT", price=1_000.0, import_order=2),
                tx("d1", "2025-01-01", "DEPOSIT", price=1_000.0, import_order=1),
            ]
        )


def test_cash_only_portfolio_history_returns_snapshots() -> None:
    transactions = [
        tx("d1", "2025-01-01", "DEPOSIT", price=1_000.0, import_order=1),
        tx("w1", "2025-01-03", "WITHDRAWAL", price=250.0, import_order=2),
    ]
    history = PortfolioService(DemoMarketDataProvider()).history(transactions)
    assert [snapshot.date for snapshot in history] == [
        date(2025, 1, 1),
        date(2025, 1, 3),
    ]
    assert [snapshot.total_portfolio_value for snapshot in history] == [1_000.0, 750.0]
    assert all(snapshot.position_values == {} for snapshot in history)
    assert history[0].external_cash_flow == 1_000.0
    assert history[1].external_cash_flow == -250.0


def test_oversell_and_insufficient_cash_are_rejected() -> None:
    with pytest.raises(ValueError, match="insufficient cash"):
        PortfolioLedger().build(
            [tx("b1", "2025-01-02", "BUY", symbol="ABC", quantity=10, price=20.0, fee=0.0)]
        )
    with pytest.raises(ValueError, match="selling more than owned"):
        PortfolioLedger().build(
            [
                tx("d1", "2025-01-01", "DEPOSIT", price=1_000.0),
                tx("s1", "2025-01-04", "SELL", symbol="ABC", quantity=5, price=40.0, fee=0.0),
            ]
        )
    with pytest.raises(ValueError, match="insufficient cash"):
        PortfolioLedger().build(
            [
                tx("d1", "2025-01-01", "DEPOSIT", price=10.0),
                tx("fee1", "2025-01-02", "FEE", price=11.0, fee=0.0, import_order=2),
            ]
        )
