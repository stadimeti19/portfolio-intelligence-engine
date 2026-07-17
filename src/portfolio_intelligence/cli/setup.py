from __future__ import annotations

from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.user_config import write_default_config


def run_setup(reset: bool = False) -> str:
    paths = AppPaths()
    config_path = write_default_config(paths, overwrite=reset)
    return f"Configuration ready at {config_path}"
