from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "byte"
    log_level: str = "INFO"
    segments: list[str] = ["home", "agenda", "finance"]
    router_model: str = "groq:openai/gpt-oss-120b"
    fast_model: str = "groq:openai/gpt-oss-20b"
    balanced_model: str = "google:gemini-3.5-flash"
    heavy_model: str = "google:gemini-3.7-flash"
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    groq_api_key: SecretStr | None = Field(default=None, validation_alias="GROQ_API_KEY")

    model_config = SettingsConfigDict(
        env_prefix="BYTE_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
