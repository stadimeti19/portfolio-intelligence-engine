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
    currency: str | None = None
    exchange: str | None = None
    effective_timestamp: datetime | None = None
    retrieval_timestamp: datetime | None = None
    stale: bool = False
    fallback: bool = False

    @field_validator("open", "high", "low", "close", "adjusted_close")
    @classmethod
    def positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("price values must be positive")
        return value

    @field_validator("volume")
    @classmethod
    def nonnegative_volume(cls, value: int) -> int:
        if value < 0:
            raise ValueError("volume must be nonnegative")
        return value


class Quote(BaseModel):
    symbol: str
    price: float
    as_of: date
    source: str
    synthetic: bool = False
    currency: str | None = None
    exchange: str | None = None
    retrieval_timestamp: datetime | None = None
    stale: bool = False
    fallback: bool = False

    @field_validator("price")
    @classmethod
    def positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("quote price must be positive")
        return value


class Dividend(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    ex_date: date
    amount: float
    currency: str | None = None
    data_source: str
    retrieval_timestamp: datetime | None = None
    stale: bool = False
    fallback: bool = False

    @field_validator("amount")
    @classmethod
    def nonnegative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("dividend amount must be nonnegative")
        return value


class StockSplit(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    split_date: date
    from_factor: float
    to_factor: float
    data_source: str
    retrieval_timestamp: datetime | None = None
    stale: bool = False
    fallback: bool = False

    @property
    def ratio(self) -> float:
        return self.to_factor / self.from_factor

    @field_validator("from_factor", "to_factor")
    @classmethod
    def positive(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("split factors must be positive")
        return value
