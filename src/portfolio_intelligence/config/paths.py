from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

APP_NAME = "portfolio-intelligence"


class AppPaths:
    def __init__(self, base_dir: Path | None = None) -> None:
        env_home = os.environ.get("PORTFOLIO_INTELLIGENCE_HOME")
        self.base_dir = base_dir or (
            Path(env_home) if env_home else Path(user_data_dir(APP_NAME, appauthor=False))
        )
        self.config_file = self.base_dir / "config.toml"
        self.credentials_file = self.base_dir / "credentials.json"
        self.database_file = self.base_dir / "portfolio.db"
        self.cache_dir = self.base_dir / "cache"
        self.portfolios_dir = self.base_dir / "portfolios"
        self.reports_dir = self.base_dir / "reports"
        self.logs_dir = (
            self.base_dir / "logs" if env_home else Path(user_log_dir(APP_NAME, appauthor=False))
        )

    def create(self) -> None:
        for path in [
            self.base_dir,
            self.cache_dir,
            self.portfolios_dir,
            self.reports_dir,
            self.logs_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)
            try:
                path.chmod(0o700)
            except OSError:
                # Some filesystems (notably Windows) do not expose POSIX modes.
                pass
