from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from portfolio_intelligence.domain.prices import Dividend, PriceBar, Quote, StockSplit


class CsvMarketDataProvider:
    name = "csv"

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory)
        self._cache: dict[str, list[PriceBar]] = {}

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        symbol = symbol.upper()
        bars = self._cache.setdefault(symbol, self._load_symbol(symbol))
        return [bar for bar in bars if start <= bar.trading_date <= end]

    def get_latest_quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        bars = self._cache.setdefault(symbol, self._load_symbol(symbol))
        latest = bars[-1]
        return Quote(
            symbol=symbol, price=latest.adjusted_close, as_of=latest.trading_date, source="csv"
        )

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Dividend]:
        return []

    def get_splits(self, symbol: str, start: date, end: date) -> list[StockSplit]:
        return []

    def _load_symbol(self, symbol: str) -> list[PriceBar]:
        path = self.directory / f"{symbol}.csv"
        if not path.exists():
            raise FileNotFoundError(f"missing price file for {symbol}: {path}")
        bars: list[PriceBar] = []
        seen_dates: set[date] = set()
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                trading_date = date.fromisoformat(row["date"])
                if trading_date in seen_dates:
                    raise ValueError(f"duplicate price row for {symbol} on {trading_date}")
                seen_dates.add(trading_date)
                bars.append(
                    PriceBar(
                        symbol=symbol,
                        trading_date=trading_date,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        adjusted_close=float(row.get("adjusted_close") or row["close"]),
                        volume=int(float(row.get("volume") or 0)),
                        data_source="csv",
                    )
                )
        bars.sort(key=lambda bar: bar.trading_date)
        if not bars:
            raise ValueError(f"price file for {symbol} contains no rows: {path}")
        return bars
