from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from portfolio_intelligence.domain.positions import Position
from portfolio_intelligence.domain.transactions import Transaction, TransactionType


@dataclass
class LotState:
    quantity: float = 0.0
    cost_basis: float = 0.0
    realized_pnl: float = 0.0

    @property
    def average_cost(self) -> float:
        return self.cost_basis / self.quantity if self.quantity else 0.0


@dataclass
class LedgerState:
    cash: float = 0.0
    lots: dict[str, LotState] = field(default_factory=dict)
    external_cash_flows: dict[date, float] = field(default_factory=dict)
    fees: float = 0.0
    dividends: float = 0.0

    @property
    def realized_pnl(self) -> float:
        return sum(lot.realized_pnl for lot in self.lots.values())


class PortfolioLedger:
    def __init__(self, allow_shorting: bool = False, allow_margin: bool = False) -> None:
        self.allow_shorting = allow_shorting
        self.allow_margin = allow_margin

    def build(self, transactions: list[Transaction]) -> LedgerState:
        state = LedgerState()
        seen: set[str] = set()
        last_key: tuple[date, int] | None = None
        for transaction in transactions:
            key = (transaction.effective_date, transaction.import_order)
            if last_key is not None and key < last_key:
                raise ValueError("transactions must be deterministically ordered")
            last_key = key
            if transaction.transaction_id in seen:
                raise ValueError(f"duplicate transaction_id: {transaction.transaction_id}")
            seen.add(transaction.transaction_id)
            self.apply(state, transaction)
        return state

    def build_through(self, transactions: list[Transaction], through: date) -> LedgerState:
        return self.build([tx for tx in transactions if tx.effective_date <= through])

    def apply(self, state: LedgerState, transaction: Transaction) -> None:
        tx_type = transaction.transaction_type
        amount = transaction.quantity * transaction.price
        if tx_type == TransactionType.DEPOSIT:
            state.cash += transaction.cash_amount
            state.external_cash_flows[transaction.effective_date] = (
                state.external_cash_flows.get(transaction.effective_date, 0.0)
                + transaction.cash_amount
            )
            return
        if tx_type == TransactionType.WITHDRAWAL:
            if state.cash < transaction.cash_amount and not self.allow_margin:
                raise ValueError(f"insufficient cash for withdrawal {transaction.transaction_id}")
            state.cash -= transaction.cash_amount
            state.external_cash_flows[transaction.effective_date] = (
                state.external_cash_flows.get(transaction.effective_date, 0.0)
                - transaction.cash_amount
            )
            return
        if tx_type == TransactionType.FEE:
            if state.cash < transaction.fee + transaction.cash_amount and not self.allow_margin:
                raise ValueError(f"insufficient cash for fee {transaction.transaction_id}")
            state.cash -= transaction.fee + transaction.cash_amount
            state.fees += transaction.fee + transaction.cash_amount
            return
        if transaction.symbol is None:
            raise ValueError("symbol is required")
        lot = state.lots.setdefault(transaction.symbol, LotState())
        if tx_type == TransactionType.BUY:
            cash_needed = amount + transaction.fee
            if state.cash < cash_needed and not self.allow_margin:
                raise ValueError(f"insufficient cash for buy {transaction.transaction_id}")
            state.cash -= cash_needed
            lot.quantity += transaction.quantity
            lot.cost_basis += amount + transaction.fee
            state.fees += transaction.fee
            return
        if tx_type == TransactionType.SELL:
            if lot.quantity + 1e-12 < transaction.quantity and not self.allow_shorting:
                raise ValueError(f"selling more than owned for {transaction.transaction_id}")
            average_cost = lot.average_cost
            proceeds = amount - transaction.fee
            state.cash += proceeds
            lot.quantity -= transaction.quantity
            lot.cost_basis -= average_cost * transaction.quantity
            lot.realized_pnl += proceeds - (average_cost * transaction.quantity)
            state.fees += transaction.fee
            if abs(lot.quantity) < 1e-10:
                lot.quantity = 0.0
                lot.cost_basis = 0.0
            return
        if tx_type == TransactionType.DIVIDEND:
            state.cash += transaction.cash_amount
            state.dividends += transaction.cash_amount
            return
        raise ValueError(f"unsupported transaction type: {tx_type}")


def positions_from_state(
    state: LedgerState, latest_prices: dict[str, float], total_value: float
) -> list[Position]:
    positions: list[Position] = []
    for symbol, lot in sorted(state.lots.items()):
        if lot.quantity == 0:
            continue
        current_price = latest_prices[symbol]
        market_value = lot.quantity * current_price
        positions.append(
            Position(
                symbol=symbol,
                quantity=lot.quantity,
                average_cost=lot.average_cost,
                current_price=current_price,
                market_value=market_value,
                realized_pnl=lot.realized_pnl,
                unrealized_pnl=market_value - lot.cost_basis,
                weight=market_value / total_value if total_value else 0.0,
            )
        )
    return positions
