from __future__ import annotations

from portfolio_intelligence.domain.explanations import ExplanationRequest, PortfolioExplanation


class DisabledExplanationProvider:
    def __init__(self, reason: str | None = None) -> None:
        self.reason = reason or (
            "AI explanations are disabled. Run the deterministic portfolio commands "
            "(for example, `portfolio summary`, `portfolio performance`, or `portfolio risk`) "
            "for locally computed results."
        )

    def explain(self, request: ExplanationRequest) -> PortfolioExplanation:
        return PortfolioExplanation(summary=self.reason, limitations=[self.reason])
