from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from portfolio_intelligence.domain.reports import AnalysisReport
from portfolio_intelligence.domain.scenarios import ScenarioResult
from portfolio_intelligence.reporting.html import HtmlReportRenderer

_UTC = timezone.utc  # noqa: UP017 - local test environments include Python 3.10.


class DashboardAnalyzer(Protocol):
    def analyze(self, benchmark: str, confidence_level: float) -> AnalysisReport: ...

    def run_scenario(self, name: str) -> ScenarioResult: ...


class DashboardRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    portfolio: str = "configured"
    start_date: date | None = None
    end_date: date | None = None
    benchmark: str = "SPY"
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    scenario: str | None = None
    position_concentration_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    sector_concentration_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    overlap_warning_threshold: float = Field(default=0.40, ge=0.0, le=1.0)
    rebalancing_settings: dict[str, str | float | bool] = Field(default_factory=dict)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, value: date | None, info: Any) -> date | None:
        start = info.data.get("start_date")
        if value is not None and start is not None and value < start:
            raise ValueError("end_date must be on or after start_date")
        return value


class DashboardResult(BaseModel):
    request: DashboardRequest
    report: AnalysisReport
    cache_key: str
    cached: bool = False


class DashboardService:
    """Orchestrates SDK calls and caches their typed reports without recalculating metrics."""

    def __init__(
        self,
        analyzer_factory: Callable[[str], DashboardAnalyzer],
        *,
        html_renderer: HtmlReportRenderer | None = None,
        max_cache_entries: int = 16,
    ) -> None:
        self.analyzer_factory = analyzer_factory
        self.html_renderer = html_renderer or HtmlReportRenderer()
        self.max_cache_entries = max_cache_entries
        self._cache: dict[str, DashboardResult] = {}
        self._lookup: dict[str, str] = {}
        self._html_cache: dict[str, str] = {}

    def analyze(self, request: DashboardRequest, *, refresh: bool = False) -> DashboardResult:
        analyzer = self.analyzer_factory(request.portfolio)
        fingerprint = _input_fingerprint(analyzer)
        lookup_key = _digest({"request": request.model_dump(mode="json"), "input": fingerprint})
        final_key = self._lookup.get(lookup_key)
        if not refresh and final_key and final_key in self._cache:
            return self._cache[final_key].model_copy(update={"cached": True})

        _configure_thresholds(analyzer, request)
        report = analyzer.analyze(
            benchmark=request.benchmark.upper(),
            confidence_level=request.confidence_level,
        )
        if request.scenario:
            scenario = analyzer.run_scenario(request.scenario)
            report = report.model_copy(update={"scenario_results": [scenario]})
        final_key = _digest(
            {
                "portfolio": request.portfolio,
                "data_date": report.summary.data_date.isoformat(),
                "date_range": [
                    request.start_date.isoformat() if request.start_date else None,
                    request.end_date.isoformat() if request.end_date else None,
                ],
                "benchmark": request.benchmark.upper(),
                "confidence_level": request.confidence_level,
                "methodology_version": report.methodology_version,
                "scenario": request.scenario,
                "thresholds": [
                    request.position_concentration_threshold,
                    request.sector_concentration_threshold,
                    request.overlap_warning_threshold,
                ],
                "optimizer_settings": request.rebalancing_settings,
                "input": fingerprint,
            }
        )
        result = DashboardResult(
            request=request,
            report=report,
            cache_key=final_key,
            cached=False,
        )
        self._lookup[lookup_key] = final_key
        self._cache[final_key] = result
        self._trim_cache()
        return result

    def render_html(self, result: DashboardResult) -> str:
        if result.cache_key in self._html_cache:
            return self._html_cache[result.cache_key]
        html = self.html_renderer.render(
            result.report,
            start_date=result.request.start_date,
            end_date=result.request.end_date,
        )
        self._html_cache[result.cache_key] = html
        return html

    def export_html(self, result: DashboardResult, output: str | Path) -> Path:
        return self.html_renderer.write(
            result.report,
            output,
            start_date=result.request.start_date,
            end_date=result.request.end_date,
        )

    def clear(self) -> None:
        self._cache.clear()
        self._lookup.clear()
        self._html_cache.clear()

    def _trim_cache(self) -> None:
        while len(self._cache) > self.max_cache_entries:
            oldest = next(iter(self._cache))
            self._cache.pop(oldest)
            self._html_cache.pop(oldest, None)
            self._lookup = {key: value for key, value in self._lookup.items() if value != oldest}


def _configure_thresholds(analyzer: DashboardAnalyzer, request: DashboardRequest) -> None:
    for name, value in [
        ("position_concentration_threshold", request.position_concentration_threshold),
        ("sector_concentration_threshold", request.sector_concentration_threshold),
        ("overlap_warning_threshold", request.overlap_warning_threshold),
    ]:
        if hasattr(analyzer, name):
            setattr(analyzer, name, value)


def _input_fingerprint(analyzer: DashboardAnalyzer) -> str:
    transactions = getattr(analyzer, "transactions", [])
    transaction_payload = [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else repr(item)
        for item in transactions
    ]
    files_payload = []
    for path in _source_paths(analyzer):
        if path.is_file():
            stat = path.stat()
            files_payload.append(
                (str(path), stat.st_mtime_ns, stat.st_size, _expiration_state(path))
            )
        elif path.is_dir():
            for item in sorted(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file() and candidate.suffix.lower() in {".csv", ".json"}
            ):
                stat = item.stat()
                files_payload.append(
                    (str(item), stat.st_mtime_ns, stat.st_size, _expiration_state(item))
                )
    return _digest({"transactions": transaction_payload, "files": files_payload})


def _source_paths(analyzer: DashboardAnalyzer) -> set[Path]:
    paths: set[Path] = set()
    seen: set[int] = set()

    def visit(value: Any, depth: int = 0) -> None:
        if value is None or depth > 4 or id(value) in seen:
            return
        seen.add(id(value))
        for attribute in ("path", "directory"):
            candidate = getattr(value, attribute, None)
            if isinstance(candidate, (str, Path)):
                paths.add(Path(candidate))
        cache = getattr(value, "cache", None)
        for attribute in (
            "portfolio_source",
            "market_data_provider",
            "etf_composition_provider",
            "provider",
            "primary",
            "fallback",
            "cache",
        ):
            child = cache if attribute == "cache" else getattr(value, attribute, None)
            if child is not None:
                visit(child, depth + 1)

    visit(analyzer)
    return paths


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _expiration_state(path: Path) -> bool | None:
    if path.suffix.lower() != ".json":
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    raw = None
    if isinstance(metadata, dict):
        raw = metadata.get("expiration_timestamp")
    if raw is None and isinstance(payload, dict):
        raw = payload.get("expiration_time")
    if not isinstance(raw, str):
        return None
    try:
        expiration = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if expiration.tzinfo is None:
        expiration = expiration.replace(tzinfo=_UTC)
    return expiration <= datetime.now(_UTC)
