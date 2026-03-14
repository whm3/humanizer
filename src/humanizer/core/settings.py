from __future__ import annotations

from os.path import expanduser

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "humanizer"
    app_version: str = "0.1.0"
    log_level: str = "DEBUG"
    default_provider: str = "openai"
    default_model: str = "gpt-5-mini"
    default_model_openai: str = "gpt-5-mini"
    default_model_gemini: str = "gemini-2.5-flash"
    default_model_perplexity: str = "sonar"
    default_model_anthropic: str = "claude-sonnet-4-5"
    default_model_deepseek: str = "deepseek-chat"
    default_model_grok: str = "grok-3-mini"
    default_humanizer_provider: str = "openai"
    default_humanizer_model: str = "gpt-5-mini"
    enable_provider_anthropic: bool = True
    enable_provider_deepseek: bool = False
    enable_provider_gemini: bool = True
    enable_provider_grok: bool = True
    enable_provider_openai: bool = True
    enable_provider_perplexity: bool = True
    request_text_max_chars: int = 250000
    batch_max_items: int = 20
    provider_request_timeout_seconds: float = 60.0
    provider_retry_attempts: int = 2
    provider_retry_backoff_seconds: float = 2.0
    token_usage_log_enabled: bool = True
    token_usage_log_path: str = ".local/token-usage.jsonl"
    allow_stub_providers_without_keys: bool = False
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_base_url: str = "https://api.anthropic.com"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    grok_base_url: str = "https://api.x.ai/v1"
    perplexity_base_url: str = "https://api.perplexity.ai"
    anthropic_api_key: str | None = Field(
        default=None,
        alias="ANTHROPIC_API_KEY",
        validation_alias=AliasChoices(
            "HUMANIZER_ANTHROPIC_PAID_KEY",
            "ANTHROPIC_API_KEY",
        ),
    )
    deepseek_api_key: str | None = Field(
        default=None,
        alias="DEEPSEEK_API_KEY",
        validation_alias=AliasChoices("DEEPSEEK_API_KEY"),
    )
    gemini_api_key: str | None = Field(
        default=None,
        alias="GEMINI_API_KEY",
        validation_alias=AliasChoices(
            "HUMANIZER_GEMINI_PAID_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "HUMANIZER_GEMINI_API_KEY",
        ),
    )
    grok_api_key: str | None = Field(
        default=None,
        alias="GROK_API_KEY",
        validation_alias=AliasChoices(
            "HUMANIZER_GROK_KEY",
            "HUMANIZER_GROK_PAID_KEY",
            "GROK_API_KEY",
            "XAI_API_KEY",
        ),
    )
    openai_api_key: str | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
        validation_alias=AliasChoices("OPENAI_API_KEY"),
    )
    perplexity_api_key: str | None = Field(
        default=None,
        alias="PERPLEXITY_API_KEY",
        validation_alias=AliasChoices("PERPLEXITY_API_KEY"),
    )

    model_config = SettingsConfigDict(
        env_file=(expanduser("~/.env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


def get_settings() -> Settings:
    return Settings()


def with_api_key_overrides(
    settings: Settings,
    *,
    ignore_env_keys: bool = False,
    overrides: dict[str, str | None] | None = None,
) -> Settings:
    key_fields = (
        "anthropic_api_key",
        "deepseek_api_key",
        "gemini_api_key",
        "grok_api_key",
        "openai_api_key",
        "perplexity_api_key",
    )
    update: dict[str, str | None] = {}
    if ignore_env_keys:
        update.update({field_name: None for field_name in key_fields})
    if overrides:
        for provider_name, api_key in overrides.items():
            field_name = f"{provider_name}_api_key"
            if field_name in key_fields:
                update[field_name] = api_key
    if ignore_env_keys or overrides:
        update["allow_stub_providers_without_keys"] = False
    return settings.model_copy(update=update)
