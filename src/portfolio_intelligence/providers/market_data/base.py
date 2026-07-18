from __future__ import annotations

from datetime import date
from typing import Protocol

from portfolio_intelligence.domain.prices import Dividend, PriceBar, Quote, StockSplit


class MarketDataProvider(Protocol):
    name: str

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]: ...

    def get_latest_quote(self, symbol: str) -> Quote: ...

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Dividend]: ...

    def get_splits(self, symbol: str, start: date, end: date) -> list[StockSplit]: ...
