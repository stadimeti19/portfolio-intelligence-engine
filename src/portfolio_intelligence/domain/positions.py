from __future__ import annotations

from pydantic import BaseModel


class Position(BaseModel):
    symbol: str
    quantity: float
    average_cost: float
    current_price: float
    market_value: float
    realized_pnl: float
    unrealized_pnl: float
    weight: float
