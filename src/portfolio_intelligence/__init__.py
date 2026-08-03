from importlib.metadata import PackageNotFoundError, version

from portfolio_intelligence.sdk import PortfolioAnalyzer

try:
    __version__ = version("portfolio-intelligence")
except PackageNotFoundError:  # Source checkout without installed package metadata.
    __version__ = "0.1.0"

__all__ = ["PortfolioAnalyzer", "__version__"]
