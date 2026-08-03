from __future__ import annotations

from typing import Any

from portfolio_intelligence.domain.explanations import ExplanationRequest, ExplanationType
from portfolio_intelligence.domain.reports import AnalysisReport

PROMPT_VERSION = "portfolio-explanation-v1"


def prepare_explanation_request(
    report: AnalysisReport,
    explanation_type: ExplanationType,
    *,
    send_dollar_values: bool = False,
    max_input_tokens: int = 5000,
    force: bool = False,
) -> ExplanationRequest:
    """Create a minimal, privacy-filtered payload from already-computed analytics.

    This function deliberately selects and formats existing values. It does not invoke an
    analytics service, read transactions, or provide the model any account-level identifiers.
    """

    content = _base_content(report)
    content["computed_values"] = _values_for(report, explanation_type, send_dollar_values)
    content["privacy"]["exact_dollar_values_included"] = send_dollar_values
    content = _limit_content(content, max_input_tokens)
    return ExplanationRequest(
        explanation_type=explanation_type,
        report_content=content,
        prompt_version=PROMPT_VERSION,
        force=force,
    )


def _base_content(report: AnalysisReport) -> dict[str, Any]:
    freshness = {
        key: value
        for key, value in report.data_freshness.items()
        if key
        in {
            "portfolio_source",
            "market_data_provider",
            "data_date",
            "synthetic",
            "fallback_used",
            "etf_composition_provider",
            "etf_composition_as_of",
        }
    }
    return {
        "data_date": report.summary.data_date.isoformat(),
        "methodology_version": report.methodology_version,
        "data_freshness": freshness,
        "limitations": report.limitations,
        "privacy": {
            "exact_dollar_values_included": False,
            "raw_transactions_included": False,
            "account_identifiers_included": False,
        },
    }


def _values_for(
    report: AnalysisReport,
    explanation_type: ExplanationType,
    send_dollar_values: bool,
) -> dict[str, Any]:
    if explanation_type == ExplanationType.PERFORMANCE:
        return _performance_values(report)
    if explanation_type == ExplanationType.BENCHMARK:
        return _benchmark_values(report)
    if explanation_type == ExplanationType.ATTRIBUTION:
        return _attribution_values(report)
    if explanation_type == ExplanationType.RISK:
        return _risk_values(report)
    if explanation_type == ExplanationType.CONCENTRATION:
        return _concentration_values(report)
    if explanation_type == ExplanationType.ETF_OVERLAP:
        return _overlap_values(report)
    if explanation_type == ExplanationType.SCENARIO:
        return _scenario_values(report, send_dollar_values)
    if explanation_type == ExplanationType.REBALANCE:
        return _rebalancing_values(report, send_dollar_values)
    if explanation_type == ExplanationType.LIMITATIONS:
        return {
            "reported_limitations": report.limitations,
            "data_freshness": _base_content(report)["data_freshness"],
        }
    return _summary_values(report, send_dollar_values)


def _summary_values(report: AnalysisReport, send_dollar_values: bool) -> dict[str, Any]:
    values: dict[str, Any] = {
        "benchmark": report.summary.benchmark,
        "portfolio_overview": _relative_summary_values(report),
        "allocation_by_position": _percent_map(report.exposure.get("positions", {})),
        "allocation_by_sector": _percent_map(report.exposure.get("sectors", {})),
        "performance": _performance_values(report),
        "risk": _risk_values(report),
        "concentration": _concentration_values(report),
        "etf_overlap": _overlap_values(report),
    }
    if report.scenario_results:
        values["scenarios"] = _scenario_values(report, send_dollar_values)
    if report.rebalancing_plan is not None:
        values["rebalancing"] = _rebalancing_values(report, send_dollar_values)
    if send_dollar_values:
        values["dollar_values"] = _dollar_summary_values(report)
    return values


def _relative_summary_values(report: AnalysisReport) -> dict[str, str | None]:
    total = report.summary.total_value
    return {
        "cash_weight": _percentage(_ratio(report.summary.cash, total)),
        "cost_basis_as_percent_of_portfolio_value": _percentage(
            _ratio(report.summary.cost_basis, total)
        ),
        "realized_pnl_as_percent_of_portfolio_value": _percentage(
            _ratio(report.summary.realized_pnl, total)
        ),
        "unrealized_pnl_as_percent_of_portfolio_value": _percentage(
            _ratio(report.summary.unrealized_pnl, total)
        ),
    }


def _performance_values(report: AnalysisReport) -> dict[str, Any]:
    start = report.snapshots[0].date.isoformat() if report.snapshots else None
    return {
        "period_start": start,
        "period_end": report.summary.data_date.isoformat(),
        "cumulative_return": _percentage(report.performance.cumulative_return),
        "annualized_return": _percentage(report.performance.annualized_return),
        "benchmark_return": _percentage(report.performance.benchmark_return),
        "relative_return": _percentage(report.performance.relative_return),
        "maximum_drawdown": _percentage(report.performance.maximum_drawdown),
        "sharpe": _number(report.performance.sharpe),
        "sortino": _number(report.performance.sortino),
        "top_contributors": [
            {
                "symbol": item.get("symbol"),
                "asset_return": _percentage(_float_or_none(item.get("asset_return"))),
                "starting_weight": _percentage(_float_or_none(item.get("starting_weight"))),
                "percentage_point_contribution": _percentage_points(
                    _float_or_none(item.get("percentage_point_contribution"))
                ),
            }
            for item in report.performance.top_contributors
        ],
    }


def _benchmark_values(report: AnalysisReport) -> dict[str, Any]:
    benchmark = report.benchmark_comparison
    return {
        "benchmark": benchmark.benchmark,
        "portfolio_return": _percentage(benchmark.portfolio_return),
        "benchmark_return": _percentage(benchmark.benchmark_return),
        "relative_return": _percentage(benchmark.relative_return),
        "tracking_difference": _percentage(benchmark.tracking_difference),
        "tracking_error": _percentage(benchmark.tracking_error),
        "beta": _number(benchmark.beta),
        "correlation": _number(benchmark.correlation),
    }


def _attribution_values(report: AnalysisReport) -> dict[str, Any]:
    return {
        "methodology_note": "Contributions are deterministic attribution inputs, not causal proof.",
        "top_contributors": _performance_values(report)["top_contributors"],
    }


def _risk_values(report: AnalysisReport) -> dict[str, Any]:
    return {
        "annualized_volatility": _percentage(report.risk.annualized_volatility),
        "beta": _number(report.risk.beta),
        "historical_var": _percentage(report.risk.historical_var),
        "expected_shortfall": _percentage(report.risk.expected_shortfall),
        "risk_contribution": [
            {
                "symbol": item.get("symbol"),
                "percent": _percentage(_float_or_none(item.get("percent"))),
            }
            for item in report.risk.risk_contribution
        ],
        "concentration_warnings": report.risk.concentration_warnings,
    }


def _concentration_values(report: AnalysisReport) -> dict[str, Any]:
    exposure = report.etf_exposure
    if exposure is None or exposure.concentration is None:
        return {"available": False, "warnings": report.risk.concentration_warnings}
    concentration = exposure.concentration
    return {
        "available": True,
        "largest_effective_security_weight": _percentage(concentration.largest_security_weight),
        "largest_effective_sector_weight": _percentage(concentration.largest_sector_weight),
        "hhi": _number(concentration.hhi),
        "effective_number_of_holdings": _number(concentration.effective_number_of_holdings),
        "top_five_effective_holdings": [
            {
                "symbol": item.symbol,
                "effective_weight": _percentage(item.effective_weight),
                "sector": item.sector,
            }
            for item in concentration.top_five_effective_holdings
        ],
        "warnings": list(dict.fromkeys(concentration.warnings + exposure.warnings)),
        "data_as_of": {
            symbol: value.isoformat() if value else None
            for symbol, value in exposure.data_as_of.items()
        },
    }


def _overlap_values(report: AnalysisReport) -> dict[str, Any]:
    exposure = report.etf_exposure
    if exposure is None:
        return {"available": False}
    return {
        "available": True,
        "pairs": [
            {
                "funds": [item.left_symbol, item.right_symbol],
                "shared_constituent_count": len(item.shared_constituents),
                "weighted_overlap": _percentage(item.weighted_overlap),
                "sector_overlap": _percentage(item.sector_overlap),
                "top_overlapping_securities": [
                    {
                        "symbol": row.get("symbol"),
                        "overlap_weight": _percentage(_float_or_none(row.get("overlap_weight"))),
                    }
                    for row in item.top_overlapping_securities[:5]
                ],
                "data_as_of": {
                    symbol: value.isoformat() if value else None
                    for symbol, value in exposure.data_as_of.items()
                    if symbol in {item.left_symbol, item.right_symbol}
                },
            }
            for item in exposure.etf_overlaps
        ],
        "warnings": exposure.warnings,
    }


def _scenario_values(report: AnalysisReport, send_dollar_values: bool) -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for result in report.scenario_results:
        item: dict[str, Any] = {
            "name": result.name,
            "description": result.description,
            "portfolio_percent_pnl": _percentage(result.percent_pnl),
            "largest_impacts": [
                {
                    "symbol": impact.symbol,
                    "shock": _percentage(impact.shock),
                    "pnl_as_percent_of_starting_value": _percentage(
                        _ratio(impact.pnl, result.starting_value)
                    ),
                }
                for impact in result.impacts[:5]
            ],
        }
        if send_dollar_values:
            item["dollar_values"] = {
                "starting_value": result.starting_value,
                "ending_value": result.ending_value,
                "pnl": result.pnl,
            }
        scenarios.append(item)
    return {"scenarios": scenarios, "available": bool(scenarios)}


def _rebalancing_values(report: AnalysisReport, send_dollar_values: bool) -> dict[str, Any]:
    plan = report.rebalancing_plan
    if plan is None:
        return {
            "available": False,
            "note": "No deterministic rebalancing plan is present in this report.",
        }
    total = report.summary.total_value
    values: dict[str, Any] = {
        "available": True,
        "status": plan.status,
        "allocation_trade_offs": [
            {
                "symbol": trade.symbol,
                "current_weight": _percentage(trade.current_weight),
                "target_weight": _percentage(trade.target_weight),
                "weight_change_percentage_points": _percentage_points(
                    trade.target_weight - trade.current_weight
                ),
                "trade_value_as_percent_of_portfolio": _percentage(
                    _ratio(trade.trade_value, total)
                ),
            }
            for trade in plan.trades
        ],
        "deterministic_plan_notes": plan.notes,
    }
    if send_dollar_values:
        values["dollar_trade_values"] = {
            trade.symbol: trade.trade_value for trade in plan.trades
        }
    return values


def _dollar_summary_values(report: AnalysisReport) -> dict[str, float]:
    return {
        "portfolio_value": report.summary.total_value,
        "cash": report.summary.cash,
        "cost_basis": report.summary.cost_basis,
        "realized_pnl": report.summary.realized_pnl,
        "unrealized_pnl": report.summary.unrealized_pnl,
    }


def _percent_map(values: dict[str, float]) -> dict[str, str | None]:
    return {str(name): _percentage(value) for name, value in values.items()}


def _percentage(value: float | None) -> str | None:
    return None if value is None else f"{value:.2%}"


def _percentage_points(value: float | None) -> str | None:
    return None if value is None else f"{value * 100:.2f} percentage points"


def _number(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _ratio(value: float, total: float) -> float | None:
    return None if total == 0 else value / total


def _float_or_none(value: object) -> float | None:
    return float(value) if isinstance(value, (float, int)) else None


def _limit_content(content: dict[str, Any], max_input_tokens: int) -> dict[str, Any]:
    # The provider has a second, defensive guard. This preserves useful provenance for a
    # deliberately very small configuration while keeping the normal payload human-readable.
    import json

    maximum_characters = max(1, max_input_tokens) * 3
    if len(json.dumps(content, sort_keys=True, default=str)) <= maximum_characters:
        return content
    return {
        "data_date": content["data_date"],
        "methodology_version": content["methodology_version"],
        "input_truncated": True,
    }
