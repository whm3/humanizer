from __future__ import annotations

from os.path import expanduser

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "humanizer"
    app_version: str = "0.1.0"
    default_provider: str = "openai"
    default_model: str = "gpt-5-mini"
    default_humanizer_provider: str = "openai"
    default_humanizer_model: str = "gpt-5-mini"
    enable_provider_anthropic: bool = True
    enable_provider_deepseek: bool = True
    enable_provider_gemini: bool = True
    enable_provider_grok: bool = True
    enable_provider_openai: bool = True
    enable_provider_perplexity: bool = True
    request_text_max_chars: int = 250000
    batch_max_items: int = 20
    allow_stub_providers_without_keys: bool = False
    anthropic_api_key: str | None = Field(
        default=None,
        alias="ANTHROPIC_API_KEY",
        validation_alias=AliasChoices("ANTHROPIC_API_KEY"),
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
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "HUMANIZER_GEMINI_API_KEY",
        ),
    )
    grok_api_key: str | None = Field(
        default=None,
        alias="GROK_API_KEY",
        validation_alias=AliasChoices("GROK_API_KEY", "XAI_API_KEY"),
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
