from humanizer.core.settings import Settings
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
