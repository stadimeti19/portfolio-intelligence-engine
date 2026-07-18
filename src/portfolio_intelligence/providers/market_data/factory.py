from __future__ import annotations

from pathlib import Path

from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.settings import Settings
from portfolio_intelligence.providers.market_data.alpha_vantage import AlphaVantageProvider
from portfolio_intelligence.providers.market_data.base import MarketDataProvider
from portfolio_intelligence.providers.market_data.cache import (
    CachedMarketDataProvider,
    MarketDataCache,
)
from portfolio_intelligence.providers.market_data.csv_provider import CsvMarketDataProvider
from portfolio_intelligence.providers.market_data.demo import DemoMarketDataProvider
from portfolio_intelligence.providers.market_data.errors import UnsupportedSymbolError
from portfolio_intelligence.providers.market_data.fallback import FallbackMarketDataProvider
from portfolio_intelligence.providers.market_data.finnhub import FinnhubProvider
from portfolio_intelligence.providers.market_data.twelvedata import TwelveDataProvider


def build_market_data_provider(
    settings: Settings,
    *,
    paths: AppPaths | None = None,
    cache: MarketDataCache | None = None,
) -> MarketDataProvider:
    paths = paths or AppPaths()
    market_cache = cache or MarketDataCache(paths.cache_dir / "market-data")
    primary = _build_provider(settings.market_data_provider, settings, paths)
    primary = _maybe_cached(primary, settings, market_cache, fallback=False)
    fallback = None
    if settings.market_data_fallback_provider:
        fallback_provider = _build_provider(settings.market_data_fallback_provider, settings, paths)
        fallback = _maybe_cached(fallback_provider, settings, market_cache, fallback=True)
    return FallbackMarketDataProvider(primary, fallback) if fallback else primary


def provider_status(settings: Settings, *, paths: AppPaths | None = None) -> list[dict[str, str]]:
    paths = paths or AppPaths()
    statuses = []
    for role, provider_name in [
        ("primary", settings.market_data_provider),
        ("fallback", settings.market_data_fallback_provider or ""),
    ]:
        if not provider_name:
            continue
        status = "ok"
        detail = "configured"
        normalized = provider_name.lower()
        if normalized in {"twelvedata", "twelve_data", "twelve-data"}:
            if not settings.twelve_data_api_key:
                status = "missing_api_key"
                detail = "TWELVE_DATA_API_KEY is not set"
        elif normalized in {"alphavantage", "alpha_vantage", "alpha-vantage"}:
            if not settings.alpha_vantage_api_key:
                status = "missing_api_key"
                detail = "ALPHA_VANTAGE_API_KEY is not set"
        elif normalized == "finnhub":
            if not settings.finnhub_api_key:
                status = "missing_api_key"
                detail = "FINNHUB_API_KEY is not set"
        elif normalized == "csv":
            directory = Path(settings.market_data_csv_directory)
            if not directory.exists():
                status = "unavailable"
                detail = f"CSV price directory does not exist: {directory}"
        elif normalized == "demo":
            detail = "synthetic offline provider"
        else:
            status = "unsupported"
            detail = f"unsupported provider: {provider_name}"
        statuses.append(
            {"role": role, "provider": provider_name, "status": status, "detail": detail}
        )
    cache_dir = paths.cache_dir / "market-data"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        statuses.append(
            {
                "role": "cache",
                "provider": "local",
                "status": "unavailable",
                "detail": str(exc),
            }
        )
    else:
        statuses.append(
            {
                "role": "cache",
                "provider": "local",
                "status": "ok",
                "detail": str(cache_dir),
            }
        )
    return statuses


def _build_provider(provider_name: str, settings: Settings, paths: AppPaths) -> MarketDataProvider:
    normalized = provider_name.lower()
    if normalized == "demo":
        return DemoMarketDataProvider()
    if normalized == "csv":
        return CsvMarketDataProvider(settings.market_data_csv_directory)
    if normalized in {"twelvedata", "twelve_data", "twelve-data"}:
        return TwelveDataProvider(
            settings.twelve_data_api_key,
            timeout_seconds=settings.market_data_timeout_seconds,
            max_retries=settings.market_data_max_retries,
        )
    if normalized in {"alphavantage", "alpha_vantage", "alpha-vantage"}:
        return AlphaVantageProvider(
            settings.alpha_vantage_api_key,
            timeout_seconds=settings.market_data_timeout_seconds,
            max_retries=settings.market_data_max_retries,
        )
    if normalized == "finnhub":
        return FinnhubProvider(
            settings.finnhub_api_key,
            timeout_seconds=settings.market_data_timeout_seconds,
            max_retries=settings.market_data_max_retries,
        )
    raise UnsupportedSymbolError(f"unsupported market data provider: {provider_name}")


def _maybe_cached(
    provider: MarketDataProvider,
    settings: Settings,
    cache: MarketDataCache,
    *,
    fallback: bool,
) -> MarketDataProvider:
    if provider.name in {"demo", "csv"}:
        return provider
    return CachedMarketDataProvider(
        provider,
        cache,
        price_ttl_hours=settings.price_cache_ttl_hours,
        corporate_action_ttl_hours=settings.corporate_action_cache_ttl_hours,
        allow_stale=settings.allow_stale_cache,
        fallback=fallback,
    )
