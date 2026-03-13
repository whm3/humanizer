from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "humanizer"
    app_version: str = "0.1.0"
    default_provider: str = "openai"
    default_model: str = "gpt-5-mini"
    enable_provider_openai: bool = True
    enable_provider_perplexity: bool = True
    request_text_max_chars: int = 10000
    batch_max_items: int = 20
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    perplexity_api_key: str | None = Field(default=None, alias="PERPLEXITY_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


def get_settings() -> Settings:
    return Settings()
