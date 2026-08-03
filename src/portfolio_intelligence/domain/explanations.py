from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExplanationType(str, Enum):
    """The deterministic report slice to explain."""

    SUMMARY = "summary"
    PERFORMANCE = "performance"
    BENCHMARK = "benchmark"
    ATTRIBUTION = "attribution"
    RISK = "risk"
    CONCENTRATION = "concentration"
    ETF_OVERLAP = "etf-overlap"
    SCENARIO = "scenario"
    REBALANCE = "rebalance"
    LIMITATIONS = "limitations"


class ExplanationRequest(BaseModel):
    """A privacy-filtered, deterministic report slice supplied to an explainer."""

    model_config = ConfigDict(extra="forbid")

    explanation_type: ExplanationType
    report_content: dict[str, Any]
    prompt_version: str
    force: bool = False


class PortfolioExplanation(BaseModel):
    """Structured narrative that never replaces the underlying analytics."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    return_drivers: list[str] = Field(default_factory=list)
    risk_findings: list[str] = Field(default_factory=list)
    scenario_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
