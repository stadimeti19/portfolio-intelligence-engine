from __future__ import annotations

from pathlib import Path

from portfolio_intelligence.config.paths import AppPaths

DEFAULT_CONFIG = """# Portfolio Intelligence & Risk Engine
active_portfolio_name = "demo"
portfolio_source = "demo"
base_currency = "USD"
benchmark_symbol = "SPY"
market_data_provider = "demo"
default_confidence_level = 0.95
position_concentration_threshold = 0.25
sector_concentration_threshold = 0.50
enable_ai = false
"""


def write_default_config(paths: AppPaths, overwrite: bool = False) -> Path:
    paths.create()
    if paths.config_file.exists() and not overwrite:
        return paths.config_file
    paths.config_file.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return paths.config_file
