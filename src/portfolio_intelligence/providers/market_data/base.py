from __future__ import annotations

from datetime import date
from typing import Protocol

from portfolio_intelligence.domain.prices import PriceBar, Quote


class MarketDataProvider(Protocol):
    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]: ...

    def get_latest_quote(self, symbol: str) -> Quote: ...
