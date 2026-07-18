from __future__ import annotations

from datetime import date, timedelta

from portfolio_intelligence.domain.prices import Dividend, PriceBar, StockSplit
from portfolio_intelligence.providers.market_data.errors import (
    IncompleteHistoryError,
    InvalidResponseError,
)


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise InvalidResponseError("symbol is required")
    return normalized


def normalize_price_bars(
    symbol: str,
    bars: list[PriceBar],
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[PriceBar]:
    expected = normalize_symbol(symbol)
    by_date: dict[date, PriceBar] = {}
    for bar in bars:
        if normalize_symbol(bar.symbol) != expected:
            raise InvalidResponseError("provider returned data for a different symbol")
        if start and bar.trading_date < start:
            continue
        if end and bar.trading_date > end:
            continue
        if bar.high < bar.low:
            raise InvalidResponseError("provider returned high below low")
        if bar.adjusted_close <= 0:
            raise InvalidResponseError("provider returned invalid adjusted close")
        if bar.volume < 0:
            raise InvalidResponseError("provider returned negative volume")
        by_date[bar.trading_date] = bar
    normalized = [by_date[day] for day in sorted(by_date)]
    validate_price_bars(expected, normalized, start=start, end=end)
    return normalized


def validate_price_bars(
    symbol: str,
    bars: list[PriceBar],
    *,
    start: date | None = None,
    end: date | None = None,
) -> None:
    expected = normalize_symbol(symbol)
    if start and end and start > end:
        raise InvalidResponseError("start date is after end date")
    if not bars:
        raise IncompleteHistoryError(f"no price history returned for {expected}")
    previous: date | None = None
    seen: set[date] = set()
    for bar in bars:
        if normalize_symbol(bar.symbol) != expected:
            raise InvalidResponseError("provider returned data for a different symbol")
        if previous and bar.trading_date < previous:
            raise InvalidResponseError("provider returned unordered price dates")
        if bar.trading_date in seen:
            raise InvalidResponseError("provider returned duplicate price dates")
        if bar.high < bar.low:
            raise InvalidResponseError("provider returned high below low")
        if not (bar.low <= bar.open <= bar.high) or not (bar.low <= bar.close <= bar.high):
            raise InvalidResponseError("provider returned OHLC values outside high/low range")
        seen.add(bar.trading_date)
        previous = bar.trading_date
    if start and end and _has_business_day(start, end):
        if bars[0].trading_date > _next_business_day(start) + timedelta(days=7):
            raise IncompleteHistoryError(f"price history for {expected} starts too late")
        if bars[-1].trading_date < _previous_business_day(end) - timedelta(days=7):
            raise IncompleteHistoryError(f"price history for {expected} ends too early")


def normalize_dividends(
    symbol: str, dividends: list[Dividend], *, start: date, end: date
) -> list[Dividend]:
    expected = normalize_symbol(symbol)
    normalized = [
        dividend
        for dividend in dividends
        if start <= dividend.ex_date <= end and normalize_symbol(dividend.symbol) == expected
    ]
    normalized.sort(key=lambda dividend: dividend.ex_date)
    return normalized


def normalize_splits(
    symbol: str, splits: list[StockSplit], *, start: date, end: date
) -> list[StockSplit]:
    expected = normalize_symbol(symbol)
    normalized = [
        split
        for split in splits
        if start <= split.split_date <= end and normalize_symbol(split.symbol) == expected
    ]
    normalized.sort(key=lambda split: split.split_date)
    for split in normalized:
        if split.ratio <= 0:
            raise InvalidResponseError("provider returned impossible split ratio")
    return normalized


def _has_business_day(start: date, end: date) -> bool:
    current = start
    while current <= end:
        if current.weekday() < 5:
            return True
        current += timedelta(days=1)
    return False


def _next_business_day(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def _previous_business_day(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current
