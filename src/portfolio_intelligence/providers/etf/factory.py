from __future__ import annotations

from pathlib import Path

from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.settings import Settings
from portfolio_intelligence.providers.etf.alpha_vantage import (
    AlphaVantageEtfCompositionProvider,
)
from portfolio_intelligence.providers.etf.base import EtfCompositionProvider
from portfolio_intelligence.providers.etf.cache import (
    CachedEtfCompositionProvider,
    EtfCompositionCache,
)
from portfolio_intelligence.providers.etf.csv_provider import CsvEtfCompositionProvider
from portfolio_intelligence.providers.etf.demo import DemoEtfCompositionProvider
from portfolio_intelligence.providers.etf.fallback import FallbackEtfCompositionProvider


def build_etf_composition_provider(
    settings: Settings,
    *,
    paths: AppPaths | None = None,
    cache: EtfCompositionCache | None = None,
) -> EtfCompositionProvider:
    paths = paths or AppPaths()
    composition_cache = cache or EtfCompositionCache(paths.cache_dir / "etf-composition")
    primary = _build(settings.etf_composition_provider, settings)
    primary = _cached(primary, settings, composition_cache)
    fallback = None
    if settings.etf_composition_fallback_provider:
        fallback = _build(settings.etf_composition_fallback_provider, settings)
        fallback = _cached(fallback, settings, composition_cache)
    return FallbackEtfCompositionProvider(primary, fallback) if fallback else primary


def _build(name: str, settings: Settings) -> EtfCompositionProvider:
    normalized = name.lower()
    if normalized == "demo":
        return DemoEtfCompositionProvider()
    if normalized == "csv":
        return CsvEtfCompositionProvider(
            settings.etf_composition_csv_directory,
            stale_after_days=settings.etf_composition_stale_after_days,
            weight_tolerance=settings.etf_weight_tolerance,
        )
    if normalized in {"alphavantage", "alpha_vantage", "alpha-vantage"}:
        return AlphaVantageEtfCompositionProvider(
            settings.alpha_vantage_api_key,
            timeout_seconds=settings.market_data_timeout_seconds,
            max_retries=settings.market_data_max_retries,
            weight_tolerance=settings.etf_weight_tolerance,
        )
    raise ValueError(f"unsupported ETF composition provider: {name}")


def _cached(
    provider: EtfCompositionProvider,
    settings: Settings,
    cache: EtfCompositionCache,
) -> EtfCompositionProvider:
    if provider.name == "demo":
        return provider
    return CachedEtfCompositionProvider(
        provider,
        cache,
        ttl_hours=settings.etf_composition_cache_ttl_hours,
        stale_after_days=settings.etf_composition_stale_after_days,
        allow_stale=settings.allow_stale_cache,
    )


def etf_provider_status(
    settings: Settings, *, paths: AppPaths | None = None
) -> list[dict[str, str]]:
    paths = paths or AppPaths()
    statuses: list[dict[str, str]] = []
    for role, name in [
        ("etf_primary", settings.etf_composition_provider),
        ("etf_fallback", settings.etf_composition_fallback_provider or ""),
    ]:
        if not name:
            continue
        status, detail = "ok", "configured"
        normalized = name.lower()
        if (
            normalized in {"alphavantage", "alpha_vantage", "alpha-vantage"}
            and not settings.alpha_vantage_api_key
        ):
            status, detail = "missing_api_key", "ALPHA_VANTAGE_API_KEY is not set"
        elif normalized == "csv" and not Path(settings.etf_composition_csv_directory).exists():
            status, detail = "unavailable", "ETF CSV directory does not exist"
        elif normalized == "demo":
            detail = "synthetic offline ETF compositions"
        statuses.append({"role": role, "provider": name, "status": status, "detail": detail})
    statuses.append(
        {
            "role": "etf_cache",
            "provider": "local",
            "status": "ok",
            "detail": str(paths.cache_dir / "etf-composition"),
        }
    )
    return statuses
