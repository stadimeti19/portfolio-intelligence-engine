from __future__ import annotations

from portfolio_intelligence.domain.reports import AnalysisReport


class DisabledExplanationProvider:
    def explain(self, report: AnalysisReport) -> str:
        return "AI explanations are disabled. Numerical results were computed locally."
