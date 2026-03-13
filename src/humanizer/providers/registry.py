from __future__ import annotations

from humanizer.core.settings import Settings
from humanizer.providers.base import ProviderAdapter
from humanizer.providers.heuristic_adapter import HeuristicAdapter


def build_provider_registry(settings: Settings) -> dict[str, ProviderAdapter]:
    provider_specs = [
        ("anthropic", settings.enable_provider_anthropic, settings.anthropic_api_key),
        ("deepseek", settings.enable_provider_deepseek, settings.deepseek_api_key),
        ("gemini", settings.enable_provider_gemini, settings.gemini_api_key),
        ("grok", settings.enable_provider_grok, settings.grok_api_key),
        ("openai", settings.enable_provider_openai, settings.openai_api_key),
        ("perplexity", settings.enable_provider_perplexity, settings.perplexity_api_key),
    ]

    providers: dict[str, ProviderAdapter] = {}
    for provider_name, enabled, api_key in provider_specs:
        if enabled and (settings.allow_stub_providers_without_keys or bool(api_key)):
            providers[provider_name] = HeuristicAdapter(provider_name)
    return providers
