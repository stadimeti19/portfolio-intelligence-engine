from __future__ import annotations

import importlib
import sys

from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.settings import load_settings
from portfolio_intelligence.providers.market_data.factory import provider_status
from portfolio_intelligence.providers.portfolio.demo import DemoPortfolioSource


def run_doctor() -> list[tuple[str, str, str]]:
    checks: list[tuple[str, str, str]] = []
    checks.append(
        (
            "PASS" if sys.version_info >= (3, 11) else "WARN",
            "Python environment",
            sys.version.split()[0],
        )
    )
    try:
        importlib.import_module("portfolio_engine")
        checks.append(("PASS", "C++ analytics extension", "imported"))
    except Exception as exc:
        checks.append(("WARN", "C++ analytics extension", f"not imported: {exc}"))
    paths = AppPaths()
    try:
        paths.create()
    except OSError as exc:
        checks.append(("FAIL", "Writable application directory", f"{paths.base_dir}: {exc}"))
    else:
        checks.append(("PASS", "Writable application directory", str(paths.base_dir)))
    try:
        DemoPortfolioSource().load_transactions()
        checks.append(("PASS", "Demo portfolio", "loaded"))
    except Exception as exc:
        checks.append(("FAIL", "Demo portfolio", str(exc)))
    checks.append(("PASS", "Demo market data", "synthetic offline provider available"))
    for status in provider_status(load_settings(), paths=paths):
        level = "PASS" if status["status"] == "ok" else "WARN"
        checks.append(
            (
                level,
                f"Market data {status['role']}: {status['provider']}",
                status["detail"],
            )
        )
    checks.append(("WARN", "OpenAI", "disabled"))
    return checks
