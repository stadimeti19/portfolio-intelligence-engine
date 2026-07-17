from __future__ import annotations

import math
from datetime import date, timedelta

from portfolio_intelligence.domain.assets import Asset, AssetType
from portfolio_intelligence.domain.prices import PriceBar, Quote

DEMO_ASSETS: dict[str, Asset] = {
    "NVDA": Asset(
        symbol="NVDA", name="Nvidia Demo Equity", asset_type=AssetType.EQUITY, sector="Technology"
    ),
    "MSFT": Asset(
        symbol="MSFT",
        name="Microsoft Demo Equity",
        asset_type=AssetType.EQUITY,
        sector="Technology",
    ),
    "VOO": Asset(
        symbol="VOO", name="Broad Market Demo ETF", asset_type=AssetType.ETF, sector="Diversified"
    ),
    "BND": Asset(
        symbol="BND", name="Bond Market Demo ETF", asset_type=AssetType.BOND, sector="Fixed Income"
    ),
    "AAPL": Asset(
        symbol="AAPL", name="Apple Demo Equity", asset_type=AssetType.EQUITY, sector="Technology"
    ),
    "JNJ": Asset(
        symbol="JNJ",
        name="Healthcare Demo Equity",
        asset_type=AssetType.EQUITY,
        sector="Healthcare",
    ),
    "SPY": Asset(
        symbol="SPY", name="Benchmark Demo ETF", asset_type=AssetType.ETF, sector="Diversified"
    ),
}

BASE_PRICES = {
    "NVDA": 100.0,
    "MSFT": 240.0,
    "VOO": 380.0,
    "BND": 72.0,
    "AAPL": 145.0,
    "JNJ": 155.0,
    "SPY": 390.0,
}

DRIFT = {
    "NVDA": 0.00055,
    "MSFT": 0.00033,
    "VOO": 0.00025,
    "BND": 0.00008,
    "AAPL": 0.00030,
    "JNJ": 0.00012,
    "SPY": 0.00023,
}


def business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


class DemoMarketDataProvider:
    synthetic = True

    def __init__(self, start: date = date(2024, 1, 2), end: date = date(2026, 1, 2)) -> None:
        self.start = start
        self.end = end
        self._cache: dict[str, list[PriceBar]] = {}

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        symbol = symbol.upper()
        if symbol not in DEMO_ASSETS:
            raise ValueError(f"unknown demo symbol: {symbol}")
        series = self._cache.setdefault(symbol, self._generate(symbol))
        return [bar for bar in series if start <= bar.trading_date <= end]

    def get_latest_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        bars = self.get_daily_prices(symbol, self.start, self.end)
        latest = bars[-1]
        return Quote(
            symbol=symbol,
            price=latest.adjusted_close,
            as_of=latest.trading_date,
            source="demo",
            synthetic=True,
        )

    def _generate(self, symbol: str) -> list[PriceBar]:
        price = BASE_PRICES[symbol]
        bars: list[PriceBar] = []
        for index, day in enumerate(business_days(self.start, self.end)):
            cycle = math.sin(index / 19.0) * 0.0025 + math.cos(index / 43.0) * 0.0015
            shock = 0.0
            if date(2024, 8, 5) <= day <= date(2024, 8, 16):
                shock -= 0.012 if symbol in {"NVDA", "MSFT", "AAPL"} else 0.006
            if date(2025, 3, 10) <= day <= date(2025, 4, 4):
                shock -= 0.006 if symbol != "BND" else -0.001
            if date(2025, 5, 1) <= day <= date(2025, 8, 29):
                shock += 0.0015 if symbol != "BND" else 0.0002
            daily_return = DRIFT[symbol] + cycle + shock
            price = max(1.0, price * (1.0 + daily_return))
            high = price * 1.006
            low = price * 0.994
            bars.append(
                PriceBar(
                    symbol=symbol,
                    trading_date=day,
                    open=price * 0.998,
                    high=high,
                    low=low,
                    close=price,
                    adjusted_close=price,
                    volume=1_000_000 + index * 10,
                    data_source="demo",
                )
            )
        return bars
