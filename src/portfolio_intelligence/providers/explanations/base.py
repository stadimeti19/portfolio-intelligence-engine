from __future__ import annotations

from typing import Protocol

from portfolio_intelligence.domain.reports import AnalysisReport


class ExplanationProvider(Protocol):
    def explain(self, report: AnalysisReport) -> str: ...
