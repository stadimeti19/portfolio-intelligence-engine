from __future__ import annotations

from pathlib import Path

from portfolio_intelligence.config.paths import AppPaths

DEFAULT_CONFIG = """# Portfolio Intelligence & Risk Engine
active_portfolio_name = "demo"
portfolio_source = "demo"
portfolio_holdings_path = "data/holdings.csv"
portfolio_holdings_format = "auto"
base_currency = "USD"
benchmark_symbol = "SPY"
market_data_provider = "demo"
market_data_fallback_provider = ""
market_data_csv_directory = "data/prices"
market_data_timeout_seconds = 15
market_data_max_retries = 3
price_cache_ttl_hours = 12
corporate_action_cache_ttl_hours = 24
allow_stale_cache = true
etf_composition_provider = "demo"
etf_composition_fallback_provider = ""
etf_composition_csv_directory = "data/etfs"
etf_composition_cache_ttl_hours = 24
etf_composition_stale_after_days = 45
etf_weight_tolerance = 0.01
etf_symbols = ""
default_confidence_level = 0.95
position_concentration_threshold = 0.25
sector_concentration_threshold = 0.50
etf_overlap_warning_threshold = 0.40
enable_ai = false
"""


def write_default_config(paths: AppPaths, overwrite: bool = False) -> Path:
    paths.create()
    if paths.config_file.exists() and not overwrite:
        return paths.config_file
    paths.config_file.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return paths.config_file
