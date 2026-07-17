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
    market_data_provider: str = "demo"
    confidence_level: float = 0.95
    position_concentration_threshold: float = 0.25
    sector_concentration_threshold: float = 0.50
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
        "market_data_provider": merged.get("MARKET_DATA_PROVIDER", "demo"),
        "confidence_level": float(str(merged.get("CONFIDENCE_LEVEL", "0.95"))),
        "position_concentration_threshold": float(
            str(merged.get("POSITION_CONCENTRATION_THRESHOLD", "0.25"))
        ),
        "sector_concentration_threshold": float(
            str(merged.get("SECTOR_CONCENTRATION_THRESHOLD", "0.50"))
        ),
        "enable_ai": str(merged.get("ENABLE_AI", "false")).lower() == "true",
        "openai_model": merged.get("OPENAI_MODEL") or None,
    }
    if overrides:
        data.update(overrides)
    return Settings.model_validate(data)
