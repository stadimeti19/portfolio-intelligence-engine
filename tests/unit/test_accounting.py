from __future__ import annotations

from datetime import date

import pytest

from portfolio_intelligence.accounting.ledger import PortfolioLedger
from portfolio_intelligence.domain.transactions import Transaction


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
