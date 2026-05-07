# app/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "marcelo"
    log_level: str = "INFO"
    default_channel: str = "api"

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
