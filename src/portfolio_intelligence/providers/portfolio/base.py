from __future__ import annotations

from typing import Protocol

from portfolio_intelligence.domain.transactions import Transaction


class PortfolioSource(Protocol):
    def load_transactions(self) -> list[Transaction]: ...
