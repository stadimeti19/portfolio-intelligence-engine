from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class PortfolioSnapshot(BaseModel):
    date: date
    cash_balance: float
    position_values: dict[str, float]
    total_portfolio_value: float
    total_cost_basis: float
    realized_pnl: float
    unrealized_pnl: float
    external_cash_flow: float
    data_provenance: dict[str, str | bool]
