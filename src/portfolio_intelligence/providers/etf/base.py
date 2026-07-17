from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class EtfHolding(BaseModel):
    fund_symbol: str
    constituent_symbol: str
    weight: float
    as_of_date: date | None = None
    source: str
