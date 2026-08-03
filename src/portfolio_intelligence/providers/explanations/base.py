from __future__ import annotations

from typing import Protocol

from portfolio_intelligence.domain.explanations import ExplanationRequest, PortfolioExplanation


class ExplanationProvider(Protocol):
    def explain(self, request: ExplanationRequest) -> PortfolioExplanation: ...
