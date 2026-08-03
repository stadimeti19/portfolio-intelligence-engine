from __future__ import annotations

from portfolio_intelligence.config.paths import AppPaths
from portfolio_intelligence.config.settings import Settings
from portfolio_intelligence.providers.explanations.base import ExplanationProvider
from portfolio_intelligence.providers.explanations.cache import ExplanationCache
from portfolio_intelligence.providers.explanations.disabled import DisabledExplanationProvider
from portfolio_intelligence.providers.explanations.openai import OpenAIExplanationProvider


def build_explanation_provider(
    settings: Settings, *, paths: AppPaths | None = None
) -> ExplanationProvider:
    if not settings.enable_ai:
        return DisabledExplanationProvider()
    if not settings.openai_api_key:
        return DisabledExplanationProvider(
            "AI explanations are enabled but OPENAI_API_KEY is not set. "
            "Run deterministic commands such as `portfolio summary`, `portfolio performance`, "
            "or `portfolio risk` until you configure an API key."
        )
    app_paths = paths or AppPaths()
    return OpenAIExplanationProvider(
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        max_input_tokens=settings.openai_max_input_tokens,
        max_output_tokens=settings.openai_max_output_tokens,
        store_responses=settings.openai_store_responses,
        cache=ExplanationCache(app_paths.cache_dir / "explanations"),
    )
