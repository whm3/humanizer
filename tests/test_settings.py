import pytest

from humanizer.core.settings import Settings, with_api_key_overrides
from humanizer.providers.anthropic_adapter import AnthropicAdapter
from humanizer.providers.gemini_adapter import GeminiAdapter
from humanizer.providers.grok_adapter import GrokAdapter
from humanizer.providers.openai_adapter import OpenAIAdapter
from humanizer.providers.perplexity_adapter import PerplexityAdapter
from humanizer.providers.registry import build_provider_registry


def test_settings_autodetect_provider_tokens_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUMANIZER_ANTHROPIC_PAID_KEY", "test-anthropic-key")
    monkeypatch.setenv("HUMANIZER_GEMINI_PAID_KEY", "test-gemini-key")
    monkeypatch.setenv("HUMANIZER_GROK_KEY", "test-grok-key")
    settings = Settings()

    assert settings.anthropic_api_key == "test-anthropic-key"
    assert settings.deepseek_api_key == "test-deepseek-key"
    assert settings.gemini_api_key == "test-gemini-key"
    assert settings.grok_api_key == "test-grok-key"
    assert settings.openai_api_key == "test-openai-key"
    assert settings.perplexity_api_key == "test-perplexity-key"
    assert settings.enable_provider_deepseek is False
    assert settings.enable_provider_grok is True


def test_registry_includes_providers_with_detected_tokens() -> None:
    settings = Settings()

    providers = build_provider_registry(settings)

    assert set(providers) == {
        "anthropic",
        "gemini",
        "grok",
        "openai",
        "perplexity",
    }


def test_registry_uses_live_adapters_when_stub_mode_is_disabled() -> None:
    settings = Settings(allow_stub_providers_without_keys=False)

    providers = build_provider_registry(settings)

    assert isinstance(providers["anthropic"], AnthropicAdapter)
    assert isinstance(providers["gemini"], GeminiAdapter)
    assert isinstance(providers["openai"], OpenAIAdapter)
    assert isinstance(providers["perplexity"], PerplexityAdapter)
    assert providers["openai"].default_model == "gpt-5-mini"
    assert providers["gemini"].default_model == "gemini-2.5-flash"
    assert providers["perplexity"].default_model == "sonar"


def test_default_request_text_limit_is_large_enough_for_real_documents() -> None:
    settings = Settings()

    assert settings.request_text_max_chars == 250000
    assert settings.log_level == "DEBUG"


def test_request_text_limit_can_be_overridden_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REQUEST_TEXT_MAX_CHARS", "12345")
    monkeypatch.setenv("LOG_LEVEL", "INFO")

    settings = Settings()

    assert settings.request_text_max_chars == 12345
    assert settings.log_level == "INFO"


def test_token_usage_log_defaults_to_local_ignored_path() -> None:
    settings = Settings()

    assert settings.token_usage_log_enabled is True
    assert settings.token_usage_log_path == ".local/token-usage.jsonl"


def test_paid_gemini_key_alias_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUMANIZER_GEMINI_PAID_KEY", "paid-gemini-key")
    monkeypatch.setenv("HUMANIZER_GEMINI_API_KEY", "free-gemini-key")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    settings = Settings()

    assert settings.gemini_api_key == "paid-gemini-key"


def test_paid_anthropic_key_alias_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUMANIZER_ANTHROPIC_PAID_KEY", "paid-anthropic-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "free-anthropic-key")

    settings = Settings()

    assert settings.anthropic_api_key == "paid-anthropic-key"


def test_paid_grok_key_alias_takes_precedence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUMANIZER_GROK_KEY", "paid-grok-key")
    monkeypatch.setenv("XAI_API_KEY", "free-grok-key")
    monkeypatch.delenv("GROK_API_KEY", raising=False)

    settings = Settings()

    assert settings.grok_api_key == "paid-grok-key"


def test_registry_uses_live_grok_adapter_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUMANIZER_GROK_KEY", "test-grok-key")

    settings = Settings(enable_provider_grok=True, allow_stub_providers_without_keys=False)
    providers = build_provider_registry(settings)

    assert isinstance(providers["grok"], GrokAdapter)


def test_request_scoped_key_overrides_can_ignore_environment_keys() -> None:
    settings = Settings(allow_stub_providers_without_keys=True)

    overridden = with_api_key_overrides(
        settings,
        ignore_env_keys=True,
        overrides={"openai": "request-openai-key"},
    )

    assert overridden.allow_stub_providers_without_keys is False
    assert overridden.openai_api_key == "request-openai-key"
    assert overridden.anthropic_api_key is None
    assert overridden.gemini_api_key is None
