from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from portfolio_intelligence.providers.portfolio.csv_source import CsvPortfolioSource


class DemoPortfolioSource(CsvPortfolioSource):
    def __init__(self) -> None:
        super().__init__(
            Path(str(files("portfolio_intelligence.data").joinpath("portfolio.example.csv"))),
            source_name="demo",
        )
