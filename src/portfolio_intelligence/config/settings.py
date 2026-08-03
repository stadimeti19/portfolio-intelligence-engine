from __future__ import annotations

import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_env: str = "development"
    log_level: str = "INFO"
    base_currency: str = "USD"
    benchmark_symbol: str = "SPY"
    database_url: str = "sqlite:///data/portfolio.db"
    portfolio_source: str = "demo"
    portfolio_csv_path: str = "data/portfolio.example.csv"
    portfolio_holdings_path: str = "data/holdings.csv"
    portfolio_holdings_format: str = "auto"
    market_data_provider: str = "demo"
    market_data_fallback_provider: str | None = None
    market_data_csv_directory: str = "data/prices"
    twelve_data_api_key: str | None = None
    alpha_vantage_api_key: str | None = None
    finnhub_api_key: str | None = None
    market_data_timeout_seconds: int = 15
    market_data_max_retries: int = 3
    price_cache_ttl_hours: int = 12
    corporate_action_cache_ttl_hours: int = 24
    allow_stale_cache: bool = True
    etf_composition_provider: str = "demo"
    etf_composition_fallback_provider: str | None = None
    etf_composition_csv_directory: str = "data/etfs"
    etf_composition_cache_ttl_hours: int = 24
    etf_composition_stale_after_days: int = 45
    etf_weight_tolerance: float = 0.01
    etf_symbols: list[str] = Field(default_factory=list)
    confidence_level: float = 0.95
    position_concentration_threshold: float = 0.25
    sector_concentration_threshold: float = 0.50
    etf_overlap_warning_threshold: float = 0.40
    enable_ai: bool = False
    openai_model: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)


def load_settings(
    env_path: str | Path = ".env", overrides: dict[str, object] | None = None
) -> Settings:
    env_file_values = dotenv_values(env_path) if Path(env_path).exists() else {}
    merged = {**env_file_values, **os.environ}
    data: dict[str, object] = {
        "app_env": merged.get("APP_ENV", "development"),
        "log_level": merged.get("LOG_LEVEL", "INFO"),
        "base_currency": merged.get("BASE_CURRENCY", "USD"),
        "benchmark_symbol": merged.get("BENCHMARK_SYMBOL", "SPY"),
        "database_url": merged.get("DATABASE_URL", "sqlite:///data/portfolio.db"),
        "portfolio_source": merged.get("PORTFOLIO_SOURCE", "demo"),
        "portfolio_csv_path": merged.get("PORTFOLIO_CSV_PATH", "data/portfolio.example.csv"),
        "portfolio_holdings_path": merged.get("PORTFOLIO_HOLDINGS_PATH", "data/holdings.csv"),
        "portfolio_holdings_format": merged.get("PORTFOLIO_HOLDINGS_FORMAT", "auto"),
        "market_data_provider": merged.get("MARKET_DATA_PROVIDER", "demo"),
        "market_data_fallback_provider": merged.get("MARKET_DATA_FALLBACK_PROVIDER") or None,
        "market_data_csv_directory": merged.get("MARKET_DATA_CSV_DIRECTORY", "data/prices"),
        "twelve_data_api_key": merged.get("TWELVE_DATA_API_KEY") or None,
        "alpha_vantage_api_key": merged.get("ALPHA_VANTAGE_API_KEY") or None,
        "finnhub_api_key": merged.get("FINNHUB_API_KEY") or None,
        "market_data_timeout_seconds": int(str(merged.get("MARKET_DATA_TIMEOUT_SECONDS", "15"))),
        "market_data_max_retries": int(str(merged.get("MARKET_DATA_MAX_RETRIES", "3"))),
        "price_cache_ttl_hours": int(str(merged.get("PRICE_CACHE_TTL_HOURS", "12"))),
        "corporate_action_cache_ttl_hours": int(
            str(merged.get("CORPORATE_ACTION_CACHE_TTL_HOURS", "24"))
        ),
        "allow_stale_cache": str(merged.get("ALLOW_STALE_CACHE", "true")).lower() == "true",
        "etf_composition_provider": merged.get("ETF_COMPOSITION_PROVIDER", "demo"),
        "etf_composition_fallback_provider": merged.get("ETF_COMPOSITION_FALLBACK_PROVIDER")
        or None,
        "etf_composition_csv_directory": merged.get("ETF_COMPOSITION_CSV_DIRECTORY", "data/etfs"),
        "etf_composition_cache_ttl_hours": int(
            str(merged.get("ETF_COMPOSITION_CACHE_TTL_HOURS", "24"))
        ),
        "etf_composition_stale_after_days": int(
            str(merged.get("ETF_COMPOSITION_STALE_AFTER_DAYS", "45"))
        ),
        "etf_weight_tolerance": float(str(merged.get("ETF_WEIGHT_TOLERANCE", "0.01"))),
        "etf_symbols": [
            item.strip().upper()
            for item in str(merged.get("ETF_SYMBOLS", "")).split(",")
            if item.strip()
        ],
        "confidence_level": float(str(merged.get("CONFIDENCE_LEVEL", "0.95"))),
        "position_concentration_threshold": float(
            str(merged.get("POSITION_CONCENTRATION_THRESHOLD", "0.25"))
        ),
        "sector_concentration_threshold": float(
            str(merged.get("SECTOR_CONCENTRATION_THRESHOLD", "0.50"))
        ),
        "etf_overlap_warning_threshold": float(
            str(merged.get("ETF_OVERLAP_WARNING_THRESHOLD", "0.40"))
        ),
        "enable_ai": str(merged.get("ENABLE_AI", "false")).lower() == "true",
        "openai_model": merged.get("OPENAI_MODEL") or None,
    }
    if overrides:
        data.update(overrides)
    return Settings.model_validate(data)
