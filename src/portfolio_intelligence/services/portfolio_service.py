from __future__ import annotations

from datetime import date

from portfolio_intelligence.accounting.ledger import PortfolioLedger, positions_from_state
from portfolio_intelligence.domain.portfolios import PortfolioSnapshot
from portfolio_intelligence.domain.positions import Position
from portfolio_intelligence.domain.transactions import Transaction
from portfolio_intelligence.providers.market_data.base import MarketDataProvider


class PortfolioService:
    def __init__(self, market_data: MarketDataProvider) -> None:
        self.market_data = market_data
        self.ledger = PortfolioLedger()

    def current_positions(
        self, transactions: list[Transaction]
    ) -> tuple[list[Position], PortfolioSnapshot]:
        state = self.ledger.build(transactions)
        symbols = [symbol for symbol, lot in state.lots.items() if lot.quantity]
        quotes = {symbol: self.market_data.get_latest_quote(symbol) for symbol in symbols}
        position_values = {
            symbol: state.lots[symbol].quantity * quote.price for symbol, quote in quotes.items()
        }
        total_value = state.cash + sum(position_values.values())
        latest_prices = {symbol: quote.price for symbol, quote in quotes.items()}
        positions = positions_from_state(state, latest_prices, total_value)
        data_date = min(
            (quote.as_of for quote in quotes.values()),
            default=max(tx.effective_date for tx in transactions),
        )
        snapshot = PortfolioSnapshot(
            date=data_date,
            cash_balance=state.cash,
            position_values=position_values,
            total_portfolio_value=total_value,
            total_cost_basis=sum(lot.cost_basis for lot in state.lots.values()),
            realized_pnl=state.realized_pnl,
            unrealized_pnl=sum(pos.unrealized_pnl for pos in positions),
            external_cash_flow=sum(state.external_cash_flows.values()),
            data_provenance={
                "portfolio_source": "transactions",
                "market_data_provider": "configured",
            },
        )
        return positions, snapshot

    def history(
        self, transactions: list[Transaction], end: date | None = None
    ) -> list[PortfolioSnapshot]:
        if not transactions:
            return []
        start = min(tx.effective_date for tx in transactions)
        symbols = sorted({tx.symbol for tx in transactions if tx.symbol})
        end_date = end or min(self.market_data.get_latest_quote(symbol).as_of for symbol in symbols)
        calendars: dict[str, dict[date, float]] = {}
        all_dates: set[date] = set()
        for symbol in symbols:
            bars = self.market_data.get_daily_prices(symbol, start, end_date)
            calendars[symbol] = {bar.trading_date: bar.adjusted_close for bar in bars}
            all_dates.update(calendars[symbol])
        snapshots: list[PortfolioSnapshot] = []
        last_prices: dict[str, float] = {}
        for current_date in sorted(day for day in all_dates if start <= day <= end_date):
            for symbol in symbols:
                if current_date in calendars[symbol]:
                    last_prices[symbol] = calendars[symbol][current_date]
            state = self.ledger.build_through(transactions, current_date)
            position_values: dict[str, float] = {}
            for symbol, lot in state.lots.items():
                if lot.quantity and symbol in last_prices:
                    position_values[symbol] = lot.quantity * last_prices[symbol]
            total_value = state.cash + sum(position_values.values())
            snapshots.append(
                PortfolioSnapshot(
                    date=current_date,
                    cash_balance=state.cash,
                    position_values=position_values,
                    total_portfolio_value=total_value,
                    total_cost_basis=sum(lot.cost_basis for lot in state.lots.values()),
                    realized_pnl=state.realized_pnl,
                    unrealized_pnl=sum(
                        position_values.get(symbol, 0.0) - lot.cost_basis
                        for symbol, lot in state.lots.items()
                    ),
                    external_cash_flow=state.external_cash_flows.get(current_date, 0.0),
                    data_provenance={"synthetic": True, "method": "end_of_day"},
                )
            )
        return [snapshot for snapshot in snapshots if snapshot.total_portfolio_value > 0]
