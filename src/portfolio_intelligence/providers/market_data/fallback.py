from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import TypeVar

from portfolio_intelligence.domain.prices import Dividend, PriceBar, Quote, StockSplit
from portfolio_intelligence.providers.market_data.base import MarketDataProvider
from portfolio_intelligence.providers.market_data.errors import MarketDataError

T = TypeVar("T")


class FallbackMarketDataProvider:
    def __init__(self, primary: MarketDataProvider, fallback: MarketDataProvider | None) -> None:
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name if fallback is None else f"{primary.name}+{fallback.name}"
        self.last_error: MarketDataError | None = None
        self.last_provider: str | None = None

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        return self._call(
            self.primary.get_daily_prices,
            self.fallback.get_daily_prices if self.fallback else None,
            symbol,
            start,
            end,
        )

    def get_latest_quote(self, symbol: str) -> Quote:
        return self._call(
            self.primary.get_latest_quote,
            self.fallback.get_latest_quote if self.fallback else None,
            symbol,
        )

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Dividend]:
        return self._call(
            self.primary.get_dividends,
            self.fallback.get_dividends if self.fallback else None,
            symbol,
            start,
            end,
        )

    def get_splits(self, symbol: str, start: date, end: date) -> list[StockSplit]:
        return self._call(
            self.primary.get_splits,
            self.fallback.get_splits if self.fallback else None,
            symbol,
            start,
            end,
        )

    def _call(
        self,
        primary_call: Callable[..., T],
        fallback_call: Callable[..., T] | None,
        *args: object,
    ) -> T:
        try:
            result = primary_call(*args)
            self.last_error = None
            self.last_provider = self.primary.name
            return result
        except MarketDataError as exc:
            self.last_error = exc
            if fallback_call is None:
                raise
            result = fallback_call(*args)
            self.last_provider = self.fallback.name if self.fallback else None
            return result
