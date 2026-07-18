from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    FEE = "FEE"


class Transaction(BaseModel):
    model_config = ConfigDict(frozen=True)

    transaction_id: str
    effective_date: date
    transaction_type: TransactionType = Field(alias="type")
    symbol: str | None = None
    quantity: float = 0.0
    price: float = 0.0
    fee: float = 0.0
    currency: str = "USD"
    source: str = "csv"
    import_order: int = 0

    @field_validator("transaction_id")
    @classmethod
    def transaction_id_not_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("transaction_id is required")
        return value

    @field_validator("quantity", "price", "fee")
    @classmethod
    def nonnegative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("must be nonnegative")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> Transaction:
        if self.currency != "USD":
            raise ValueError("only USD is supported in the MVP")
        if self.transaction_type in {TransactionType.BUY, TransactionType.SELL}:
            if not self.symbol:
                raise ValueError("symbol is required for buy and sell transactions")
            if self.quantity <= 0:
                raise ValueError("quantity must be positive for buy and sell transactions")
            if self.price <= 0:
                raise ValueError("price must be positive for buy and sell transactions")
        if self.transaction_type == TransactionType.DIVIDEND and not self.symbol:
            raise ValueError("symbol is required for dividend transactions")
        if self.transaction_type in {TransactionType.DEPOSIT, TransactionType.WITHDRAWAL}:
            if self.price <= 0:
                raise ValueError("price stores cash amount and must be positive")
        return self

    @property
    def cash_amount(self) -> float:
        return self.price
