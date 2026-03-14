from __future__ import annotations

from humanizer.core.settings import Settings
from humanizer.core.token_usage import TokenUsageLogger
from humanizer.providers.anthropic_adapter import AnthropicAdapter
from humanizer.providers.base import ProviderAdapter
from humanizer.providers.gemini_adapter import GeminiAdapter
from humanizer.providers.heuristic_adapter import HeuristicAdapter
from humanizer.providers.openai_adapter import OpenAIAdapter
from humanizer.providers.perplexity_adapter import PerplexityAdapter


def build_provider_registry(settings: Settings) -> dict[str, ProviderAdapter]:
    token_usage_logger = TokenUsageLogger(
        path=settings.token_usage_log_path,
        enabled=settings.token_usage_log_enabled,
    )
    provider_specs = [
        (
            "anthropic",
            settings.enable_provider_anthropic,
            settings.anthropic_api_key,
            lambda: AnthropicAdapter(
                settings.anthropic_api_key or "",
                settings.default_model_anthropic,
                getattr(settings, "anthropic_base_url", "https://api.anthropic.com"),
                settings.provider_request_timeout_seconds,
                settings.provider_retry_attempts,
                settings.provider_retry_backoff_seconds,
                token_usage_logger,
            ),
        ),
        (
            "deepseek",
            settings.enable_provider_deepseek,
            settings.deepseek_api_key,
            lambda: HeuristicAdapter("deepseek", settings.default_model_deepseek),
        ),
        (
            "gemini",
            settings.enable_provider_gemini,
            settings.gemini_api_key,
            lambda: GeminiAdapter(
                settings.gemini_api_key or "",
                settings.default_model_gemini,
                settings.gemini_base_url,
                settings.provider_request_timeout_seconds,
                settings.provider_retry_attempts,
                settings.provider_retry_backoff_seconds,
                token_usage_logger,
            ),
        ),
        (
            "grok",
            settings.enable_provider_grok,
            settings.grok_api_key,
            lambda: HeuristicAdapter("grok", settings.default_model_grok),
        ),
        (
            "openai",
            settings.enable_provider_openai,
            settings.openai_api_key,
            lambda: OpenAIAdapter(
                settings.openai_api_key or "",
                settings.default_model_openai,
                settings.openai_base_url,
                settings.provider_request_timeout_seconds,
                settings.provider_retry_attempts,
                settings.provider_retry_backoff_seconds,
                token_usage_logger,
            ),
        ),
        (
            "perplexity",
            settings.enable_provider_perplexity,
            settings.perplexity_api_key,
            lambda: PerplexityAdapter(
                settings.perplexity_api_key or "",
                settings.default_model_perplexity,
                settings.perplexity_base_url,
                settings.provider_request_timeout_seconds,
                settings.provider_retry_attempts,
                settings.provider_retry_backoff_seconds,
                token_usage_logger,
            ),
        ),
    ]

    providers: dict[str, ProviderAdapter] = {}
    for provider_name, enabled, api_key, factory in provider_specs:
        if not enabled:
            continue
        if settings.allow_stub_providers_without_keys:
            providers[provider_name] = HeuristicAdapter(
                provider_name,
                getattr(settings, f"default_model_{provider_name}"),
            )
            continue
        if api_key:
            providers[provider_name] = factory()
    return providers
