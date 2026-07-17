from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


class AssetType(str, Enum):
    EQUITY = "Equity"
    ETF = "ETF"
    BOND = "Bond"
    CASH = "Cash"


class Asset(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str
    asset_type: AssetType
    sector: str
    currency: str = "USD"
