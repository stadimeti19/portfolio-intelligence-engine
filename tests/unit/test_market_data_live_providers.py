from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from portfolio_intelligence.config.settings import Settings
from portfolio_intelligence.domain.prices import PriceBar, Quote
from portfolio_intelligence.providers.market_data import http as http_module
from portfolio_intelligence.providers.market_data.alpha_vantage import AlphaVantageProvider
from portfolio_intelligence.providers.market_data.cache import (
    CachedMarketDataProvider,
    MarketDataCache,
)
from portfolio_intelligence.providers.market_data.demo import DemoMarketDataProvider
from portfolio_intelligence.providers.market_data.errors import (
    IncompleteHistoryError,
    InvalidResponseError,
    MissingAPIKeyError,
    ProviderAuthenticationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    RateLimitError,
    redact_secret,
)
from portfolio_intelligence.providers.market_data.factory import provider_status
from portfolio_intelligence.providers.market_data.fallback import FallbackMarketDataProvider
from portfolio_intelligence.providers.market_data.finnhub import FinnhubProvider
from portfolio_intelligence.providers.market_data.http import HttpResponse
from portfolio_intelligence.providers.market_data.twelvedata import TwelveDataProvider

_UTC = timezone.utc  # noqa: UP017 - keep local test environments on Python 3.10 working.


class FakeHttpClient:
    def __init__(self, responses: list[dict[str, Any] | list[Any] | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get_json(self, url: str, params: dict[str, str]) -> HttpResponse:
        self.calls.append((url, params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return HttpResponse(200, {}, response)


class FailingProvider:
    name = "failing"

    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        raise self.exc

    def get_latest_quote(self, symbol: str) -> Quote:
        raise self.exc

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Any]:
        raise self.exc

    def get_splits(self, symbol: str, start: date, end: date) -> list[Any]:
        raise self.exc


class StaticProvider:
    name = "static"

    def __init__(self, bars: list[PriceBar]) -> None:
        self.bars = bars
        self.requests: list[tuple[date, date]] = []

    def get_daily_prices(self, symbol: str, start: date, end: date) -> list[PriceBar]:
        self.requests.append((start, end))
        return [bar for bar in self.bars if start <= bar.trading_date <= end]

    def get_latest_quote(self, symbol: str) -> Quote:
        bar = self.bars[-1]
        return Quote(
            symbol=symbol,
            price=bar.adjusted_close,
            as_of=bar.trading_date,
            source=self.name,
        )

    def get_dividends(self, symbol: str, start: date, end: date) -> list[Any]:
        return []

    def get_splits(self, symbol: str, start: date, end: date) -> list[Any]:
        return []


def test_successful_twelve_data_response() -> None:
    client = FakeHttpClient(
        [
            {
                "meta": {"symbol": "AAPL", "currency": "USD", "exchange": "NASDAQ"},
                "values": [
                    {
                        "datetime": "2025-01-02",
                        "open": "10",
                        "high": "11",
                        "low": "9",
                        "close": "10.5",
                        "volume": "1000",
                    },
                    {
                        "datetime": "2025-01-02",
                        "open": "10",
                        "high": "11",
                        "low": "9",
                        "close": "10.6",
                        "volume": "1100",
                    },
                    {
                        "datetime": "2025-01-03",
                        "open": "11",
                        "high": "12",
                        "low": "10",
                        "close": "11.5",
                        "volume": "1200",
                    },
                ],
            }
        ]
    )
    provider = TwelveDataProvider("secret", http_client=client)
    bars = provider.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 3))
    assert [bar.trading_date for bar in bars] == [date(2025, 1, 2), date(2025, 1, 3)]
    assert bars[0].close == 10.6
    assert bars[0].currency == "USD"
    assert client.calls[0][1]["apikey"] == "secret"


def test_successful_alpha_vantage_response() -> None:
    client = FakeHttpClient([alpha_daily_payload()])
    provider = AlphaVantageProvider("secret", http_client=client)
    bars = provider.get_daily_prices("MSFT", date(2025, 1, 2), date(2025, 1, 3))
    assert [bar.adjusted_close for bar in bars] == [20.1, 21.1]
    assert bars[0].data_source == "alphavantage"


def test_successful_finnhub_response() -> None:
    client = FakeHttpClient(
        [
            {
                "s": "ok",
                "t": [_ts(2025, 1, 2), _ts(2025, 1, 3)],
                "o": [30.0, 31.0],
                "h": [31.0, 32.0],
                "l": [29.0, 30.0],
                "c": [30.5, 31.5],
                "v": [1000, 1200],
            }
        ]
    )
    provider = FinnhubProvider("secret", http_client=client)
    bars = provider.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 3))
    assert [bar.close for bar in bars] == [30.5, 31.5]
    assert bars[0].data_source == "finnhub"
    assert client.calls[0][1]["token"] == "secret"


def test_successful_finnhub_quote_and_corporate_actions() -> None:
    client = FakeHttpClient(
        [
            {"c": 42.5, "t": _ts(2025, 1, 3), "h": 43, "l": 41, "o": 42, "pc": 41.5},
            [{"symbol": "AAPL", "date": "2025-01-02", "amount": 0.25, "currency": "USD"}],
            [{"symbol": "AAPL", "date": "2025-01-03", "fromFactor": 1, "toFactor": 4}],
        ]
    )
    provider = FinnhubProvider("secret", http_client=client)
    quote = provider.get_latest_quote("AAPL")
    dividends = provider.get_dividends("AAPL", date(2025, 1, 2), date(2025, 1, 3))
    splits = provider.get_splits("AAPL", date(2025, 1, 2), date(2025, 1, 3))
    assert quote.price == 42.5
    assert dividends[0].amount == 0.25
    assert splits[0].ratio == 4.0


def test_finnhub_no_data_is_incomplete_history() -> None:
    client = FakeHttpClient([{"s": "no_data"}])
    provider = FinnhubProvider("secret", http_client=client)
    with pytest.raises(IncompleteHistoryError):
        provider.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 3))


def test_finnhub_missing_key_and_status() -> None:
    with pytest.raises(MissingAPIKeyError):
        FinnhubProvider("")
    statuses = provider_status(Settings(market_data_provider="finnhub"))
    assert statuses[0]["status"] == "missing_api_key"
    assert "FINNHUB_API_KEY" in statuses[0]["detail"]


def test_malformed_data_is_rejected() -> None:
    client = FakeHttpClient(
        [
            {
                "meta": {"symbol": "AAPL"},
                "values": [
                    {
                        "datetime": "2025-01-02",
                        "open": "10",
                        "high": "9",
                        "low": "11",
                        "close": "10",
                    }
                ],
            }
        ]
    )
    provider = TwelveDataProvider("secret", http_client=client)
    with pytest.raises(InvalidResponseError):
        provider.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 3))


def test_empty_response_is_incomplete_history() -> None:
    client = FakeHttpClient([{"meta": {"symbol": "AAPL"}, "values": []}])
    provider = TwelveDataProvider("secret", http_client=client)
    with pytest.raises(IncompleteHistoryError):
        provider.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 3))


def test_authentication_failure() -> None:
    client = FakeHttpClient([{"status": "error", "code": 401, "message": "bad api key"}])
    provider = TwelveDataProvider("secret", http_client=client)
    with pytest.raises(ProviderAuthenticationError):
        provider.get_latest_quote("AAPL")


def test_rate_limit() -> None:
    client = FakeHttpClient([{"Note": "standard API call frequency is 5 calls per minute"}])
    provider = AlphaVantageProvider("secret", http_client=client)
    with pytest.raises(RateLimitError):
        provider.get_latest_quote("AAPL")


def test_timeout() -> None:
    client = FakeHttpClient([ProviderTimeoutError("timed out")])
    provider = TwelveDataProvider("secret", http_client=client)
    with pytest.raises(ProviderTimeoutError):
        provider.get_latest_quote("AAPL")


def test_retry_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"count": 0}

    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"ok": true}'

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        calls["count"] += 1
        if calls["count"] == 1:
            raise http_module.HTTPError(
                "https://example.test",
                503,
                "temporarily unavailable",
                {},
                None,
            )
        return FakeResponse()

    monkeypatch.setattr(http_module, "urlopen", fake_urlopen)
    monkeypatch.setattr(http_module, "_sleep", lambda attempt: None)
    client = http_module.JsonHttpClient(timeout_seconds=1, max_retries=1)
    response = client.get_json("https://example.test", {})
    assert response.payload == {"ok": True}
    assert calls["count"] == 2


def test_primary_failure_and_fallback_success() -> None:
    bars = sample_bars(date(2025, 1, 2), 2)
    provider = FallbackMarketDataProvider(
        FailingProvider(ProviderUnavailableError("down")), StaticProvider(bars)
    )
    result = provider.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 3))
    assert result == bars
    assert provider.last_provider == "static"


def test_both_providers_failing() -> None:
    provider = FallbackMarketDataProvider(
        FailingProvider(ProviderUnavailableError("primary")),
        FailingProvider(ProviderUnavailableError("fallback")),
    )
    with pytest.raises(ProviderUnavailableError):
        provider.get_latest_quote("AAPL")


def test_valid_cache_hit(tmp_path: Path) -> None:
    bars = sample_bars(date(2025, 1, 2), 3)
    upstream = StaticProvider(bars)
    cached = CachedMarketDataProvider(
        upstream,
        MarketDataCache(tmp_path),
        price_ttl_hours=12,
        corporate_action_ttl_hours=24,
        allow_stale=False,
    )
    assert len(cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 6))) == 3
    assert len(cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 6))) == 3
    assert len(upstream.requests) == 1


def test_expired_cache_refetches(tmp_path: Path) -> None:
    bars = sample_bars(date(2025, 1, 2), 3)
    upstream = StaticProvider(bars)
    cached = CachedMarketDataProvider(
        upstream,
        MarketDataCache(tmp_path),
        price_ttl_hours=0,
        corporate_action_ttl_hours=24,
        allow_stale=False,
    )
    cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 6))
    cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 6))
    assert len(upstream.requests) == 2


def test_stale_cache_allowed(tmp_path: Path) -> None:
    bars = sample_bars(date(2025, 1, 2), 3)
    cached = CachedMarketDataProvider(
        StaticProvider(bars),
        MarketDataCache(tmp_path),
        price_ttl_hours=0,
        corporate_action_ttl_hours=24,
        allow_stale=True,
    )
    cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 6))
    cached.provider = FailingProvider(ProviderUnavailableError("down"))
    result = cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 6))
    assert all(bar.stale for bar in result)


def test_stale_cache_rejected(tmp_path: Path) -> None:
    bars = sample_bars(date(2025, 1, 2), 3)
    cached = CachedMarketDataProvider(
        StaticProvider(bars),
        MarketDataCache(tmp_path),
        price_ttl_hours=0,
        corporate_action_ttl_hours=24,
        allow_stale=False,
    )
    cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 6))
    cached.provider = FailingProvider(ProviderUnavailableError("down"))
    with pytest.raises(ProviderUnavailableError):
        cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 6))


def test_incremental_synchronization(tmp_path: Path) -> None:
    initial = sample_bars(date(2025, 1, 2), 2)
    extended = sample_bars(date(2025, 1, 3), 3)
    upstream = StaticProvider(initial)
    cached = CachedMarketDataProvider(
        upstream,
        MarketDataCache(tmp_path),
        price_ttl_hours=12,
        corporate_action_ttl_hours=24,
        allow_stale=False,
    )
    cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 3))
    upstream.bars = extended
    result = cached.get_daily_prices("AAPL", date(2025, 1, 2), date(2025, 1, 7))
    assert result[-1].trading_date == date(2025, 1, 7)
    assert upstream.requests[-1][0] == date(2025, 1, 3)


def test_corporate_actions() -> None:
    client = FakeHttpClient([alpha_daily_payload(), alpha_daily_payload()])
    provider = AlphaVantageProvider("secret", http_client=client)
    dividends = provider.get_dividends("MSFT", date(2025, 1, 2), date(2025, 1, 3))
    splits = provider.get_splits("MSFT", date(2025, 1, 2), date(2025, 1, 3))
    assert dividends[0].amount == 0.25
    assert splits[0].ratio == 2.0


def test_secret_redaction() -> None:
    assert redact_secret("failed with secret-key", ["secret-key"]) == "failed with [REDACTED]"


def test_offline_demo_behavior() -> None:
    provider = DemoMarketDataProvider()
    quote = provider.get_latest_quote("AAPL")
    assert quote.synthetic is True
    assert provider.get_dividends("AAPL", date(2025, 1, 1), date(2025, 1, 31)) == []


def sample_bars(start: date, count: int) -> list[PriceBar]:
    bars = []
    current = start
    while len(bars) < count:
        if current.weekday() < 5:
            price = 10.0 + len(bars)
            bars.append(
                PriceBar(
                    symbol="AAPL",
                    trading_date=current,
                    open=price,
                    high=price + 1,
                    low=price - 1,
                    close=price,
                    adjusted_close=price,
                    volume=100,
                    data_source="static",
                    retrieval_timestamp=datetime.now(_UTC),
                )
            )
        current += timedelta(days=1)
    return bars


def _ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=_UTC).timestamp())


def alpha_daily_payload() -> dict[str, Any]:
    return {
        "Meta Data": {"2. Symbol": "MSFT"},
        "Time Series (Daily)": {
            "2025-01-03": {
                "1. open": "21",
                "2. high": "22",
                "3. low": "20",
                "4. close": "21",
                "5. adjusted close": "21.1",
                "6. volume": "2000",
                "7. dividend amount": "0",
                "8. split coefficient": "2",
            },
            "2025-01-02": {
                "1. open": "20",
                "2. high": "21",
                "3. low": "19",
                "4. close": "20",
                "5. adjusted close": "20.1",
                "6. volume": "1000",
                "7. dividend amount": "0.25",
                "8. split coefficient": "1",
            },
        },
    }
