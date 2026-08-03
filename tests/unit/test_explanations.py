from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from portfolio_intelligence import PortfolioAnalyzer
from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.settings import Settings
from portfolio_intelligence.domain.explanations import (
    ExplanationRequest,
    ExplanationType,
    PortfolioExplanation,
)
from portfolio_intelligence.providers.explanations.cache import ExplanationCache
from portfolio_intelligence.providers.explanations.disabled import DisabledExplanationProvider
from portfolio_intelligence.providers.explanations.factory import build_explanation_provider
from portfolio_intelligence.providers.explanations.openai import (
    SYSTEM_INSTRUCTIONS,
    InvalidExplanationResponseError,
    OpenAIExplanationProvider,
)
from portfolio_intelligence.services.explanation_service import prepare_explanation_request


class FakeResponses:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClient:
    def __init__(self, outcomes: list[object]) -> None:
        self.responses = FakeResponses(outcomes)


class RetryableFailure(Exception):
    status_code = 429


@pytest.fixture
def report():
    return PortfolioAnalyzer.demo().analyze()


@pytest.fixture
def safe_explanation() -> PortfolioExplanation:
    return PortfolioExplanation(
        summary="The reported portfolio return was below the reported benchmark return.",
        return_drivers=["The supplied attribution lists the largest reported contributors."],
        risk_findings=["The risk section reports historical metrics and concentration warnings."],
        scenario_findings=["Scenario findings describe supplied shocks, not forecasts."],
        limitations=["Historical results and simplified scenarios have stated limitations."],
    )


def _response(explanation: PortfolioExplanation) -> SimpleNamespace:
    return SimpleNamespace(
        output_parsed=explanation,
        usage=SimpleNamespace(input_tokens=125, output_tokens=48),
    )


def _provider(
    client: FakeClient, cache: ExplanationCache | None = None
) -> OpenAIExplanationProvider:
    return OpenAIExplanationProvider(
        api_key="test-key",
        model="gpt-5.6",
        client=client,
        cache=cache,
        sleep=lambda _: None,
    )


def test_ai_disabled_returns_deterministic_guidance(report) -> None:
    provider = build_explanation_provider(Settings(enable_ai=False))
    explanation = provider.explain(prepare_explanation_request(report, ExplanationType.SUMMARY))
    assert isinstance(provider, DisabledExplanationProvider)
    assert "disabled" in explanation.summary.lower()
    assert "portfolio summary" in explanation.summary


def test_missing_api_key_returns_clear_guidance(report, tmp_path) -> None:
    settings = Settings(enable_ai=True, openai_api_key=None)
    provider = build_explanation_provider(settings, paths=AppPaths(base_dir=tmp_path))
    explanation = provider.explain(prepare_explanation_request(report, ExplanationType.RISK))
    assert isinstance(provider, DisabledExplanationProvider)
    assert "OPENAI_API_KEY" in explanation.summary
    assert "portfolio risk" in explanation.summary


def test_openai_provider_uses_responses_parse_and_pydantic_schema(report, safe_explanation) -> None:
    client = FakeClient([_response(safe_explanation)])
    explanation = _provider(client).explain(
        prepare_explanation_request(report, ExplanationType.PERFORMANCE)
    )
    assert explanation == safe_explanation
    call = client.responses.calls[0]
    assert call["text_format"] is PortfolioExplanation
    assert call["instructions"] == SYSTEM_INSTRUCTIONS
    assert call["store"] is False
    assert call["max_output_tokens"] == 800
    assert "tools" not in call
    assert "Do not calculate" in str(call["instructions"])
    assert "deterministic report payload" in str(call["input"])


def test_invalid_structured_response_is_rejected(report) -> None:
    client = FakeClient([SimpleNamespace(output_parsed=None, usage=None)])
    with pytest.raises(InvalidExplanationResponseError, match="invalid structured"):
        _provider(client).explain(prepare_explanation_request(report, ExplanationType.SUMMARY))


def test_retryable_failure_is_retried(report, safe_explanation) -> None:
    client = FakeClient([RetryableFailure(), _response(safe_explanation)])
    waits: list[float] = []
    provider = OpenAIExplanationProvider(
        api_key="test-key",
        model="gpt-5.6",
        client=client,
        sleep=waits.append,
    )
    explanation = provider.explain(prepare_explanation_request(report, ExplanationType.RISK))
    assert explanation == safe_explanation
    assert len(client.responses.calls) == 2
    assert waits == [1.0]


def test_redaction_keeps_only_minimal_report_values(report) -> None:
    sensitive = report.model_copy(
        update={
            "data_freshness": {
                **report.data_freshness,
                "account_name": "Private Retirement Account",
                "account_id": "acct-123456",
                "transaction_id": "tx-987654",
            }
        }
    )
    request = prepare_explanation_request(sensitive, ExplanationType.SUMMARY)
    payload = json.dumps(request.report_content)
    assert "Private Retirement Account" not in payload
    assert "acct-123456" not in payload
    assert "tx-987654" not in payload
    assert '"portfolio_value":' not in payload
    assert "dollar_pnl_contribution" not in payload
    assert "market_value" not in payload
    assert "cash_weight" in payload

    limitations_request = prepare_explanation_request(sensitive, ExplanationType.LIMITATIONS)
    limitations_payload = json.dumps(limitations_request.report_content)
    assert "Private Retirement Account" not in limitations_payload
    assert "acct-123456" not in limitations_payload
    assert "tx-987654" not in limitations_payload


def test_dollar_value_privacy_mode_is_explicit(report) -> None:
    private = prepare_explanation_request(report, ExplanationType.SUMMARY)
    opted_in = prepare_explanation_request(
        report, ExplanationType.SUMMARY, send_dollar_values=True
    )
    assert '"dollar_values":' not in json.dumps(private.report_content)
    assert opted_in.report_content["privacy"]["exact_dollar_values_included"] is True
    assert opted_in.report_content["computed_values"]["dollar_values"]["portfolio_value"] == (
        report.summary.total_value
    )


def test_explanation_cache_avoids_repeat_requests(report, safe_explanation, tmp_path) -> None:
    client = FakeClient([_response(safe_explanation), _response(safe_explanation)])
    cache = ExplanationCache(tmp_path / "explanations")
    provider = _provider(client, cache)
    request = prepare_explanation_request(report, ExplanationType.BENCHMARK)
    assert provider.explain(request) == safe_explanation
    assert provider.explain(request) == safe_explanation
    assert len(client.responses.calls) == 1
    assert provider.explain(request.model_copy(update={"force": True})) == safe_explanation
    assert len(client.responses.calls) == 2


def test_cache_key_includes_content_type_model_and_prompt_version(report, tmp_path) -> None:
    cache = ExplanationCache(tmp_path / "explanations")
    request = prepare_explanation_request(report, ExplanationType.PERFORMANCE)
    key = cache.key_for(request, "gpt-5.6")
    assert key != cache.key_for(request, "another-model")
    changed_type = request.model_copy(update={"explanation_type": ExplanationType.RISK})
    assert key != cache.key_for(changed_type, "gpt-5.6")
    assert key != cache.key_for(request.model_copy(update={"prompt_version": "next"}), "gpt-5.6")
    assert key != cache.key_for(
        request.model_copy(update={"report_content": {"changed": True}}), "gpt-5.6"
    )


def test_prepare_and_explain_do_not_change_deterministic_analytics(
    report, safe_explanation
) -> None:
    before = report.model_dump(mode="json")
    request = prepare_explanation_request(report, ExplanationType.CONCENTRATION)
    _provider(FakeClient([_response(safe_explanation)])).explain(request)
    assert report.model_dump(mode="json") == before


def test_input_limit_is_enforced(safe_explanation) -> None:
    client = FakeClient([_response(safe_explanation)])
    request = ExplanationRequest(
        explanation_type=ExplanationType.SUMMARY,
        report_content={"untrusted": "x" * 1000},
        prompt_version="test-v1",
    )
    provider = OpenAIExplanationProvider(
        api_key="test-key",
        model="gpt-5.6",
        max_input_tokens=10,
        client=client,
        sleep=lambda _: None,
    )
    provider.explain(request)
    assert '{"truncated":true}' in str(client.responses.calls[0]["input"])


def test_trading_recommendations_are_rejected(report) -> None:
    unsafe = PortfolioExplanation(summary="Buy AAPL now.")
    with pytest.raises(InvalidExplanationResponseError, match="trading language"):
        _provider(FakeClient([_response(unsafe)])).explain(
            prepare_explanation_request(report, ExplanationType.PERFORMANCE)
        )


def test_fixtures_contain_no_buy_or_sell_recommendation(safe_explanation) -> None:
    text = "\n".join(
        [
            safe_explanation.summary,
            *safe_explanation.return_drivers,
            *safe_explanation.risk_findings,
            *safe_explanation.scenario_findings,
            *safe_explanation.limitations,
        ]
    )
    assert "buy " not in text.lower()
    assert "sell " not in text.lower()
