import pytest

from humanizer.core.settings import Settings
from humanizer.providers.gemini_adapter import GeminiAdapter
from humanizer.providers.openai_adapter import OpenAIAdapter
from humanizer.providers.perplexity_adapter import PerplexityAdapter
from humanizer.providers.registry import build_provider_registry


def test_settings_autodetect_provider_tokens_from_environment() -> None:
    settings = Settings()

    assert settings.anthropic_api_key == "test-anthropic-key"
    assert settings.deepseek_api_key == "test-deepseek-key"
    assert settings.gemini_api_key == "test-gemini-key"
    assert settings.grok_api_key == "test-grok-key"
    assert settings.openai_api_key == "test-openai-key"
    assert settings.perplexity_api_key == "test-perplexity-key"


def test_registry_includes_providers_with_detected_tokens() -> None:
    settings = Settings()

    providers = build_provider_registry(settings)

    assert set(providers) == {
        "anthropic",
        "deepseek",
        "gemini",
        "grok",
        "openai",
        "perplexity",
    }


def test_registry_uses_live_adapters_when_stub_mode_is_disabled() -> None:
    settings = Settings(allow_stub_providers_without_keys=False)

    providers = build_provider_registry(settings)

    assert isinstance(providers["gemini"], GeminiAdapter)
    assert isinstance(providers["openai"], OpenAIAdapter)
    assert isinstance(providers["perplexity"], PerplexityAdapter)
    assert providers["openai"].default_model == "gpt-5-mini"
    assert providers["gemini"].default_model == "gemini-2.5-flash"
    assert providers["perplexity"].default_model == "sonar"


def test_default_request_text_limit_is_large_enough_for_real_documents() -> None:
    settings = Settings()

    assert settings.request_text_max_chars == 250000


def test_request_text_limit_can_be_overridden_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUEST_TEXT_MAX_CHARS", "12345")

    settings = Settings()

    assert settings.request_text_max_chars == 12345
