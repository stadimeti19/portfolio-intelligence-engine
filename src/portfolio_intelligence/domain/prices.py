from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


class PriceBar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: int = 0
    data_source: str = "demo"
    effective_timestamp: datetime | None = None
    retrieval_timestamp: datetime | None = None

    @field_validator("open", "high", "low", "close", "adjusted_close")
    @classmethod
    def positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("price values must be positive")
        return value


class Quote(BaseModel):
    symbol: str
    price: float
    as_of: date
    source: str
    synthetic: bool = False
