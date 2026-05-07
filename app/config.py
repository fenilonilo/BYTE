# app/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "marcelo"
    log_level: str = "INFO"
    default_channel: str = "api"

    # Database — asyncpg URL for SQLAlchemy; Agno adapter derives psycopg URL internally
    database_url: str = "postgresql+asyncpg://marcelo:marcelo@localhost:5432/marcelo"

    # Agno agent
    agno_model_id: str = "claude-sonnet-4-6"
    agno_add_datetime: bool = True
    agno_add_location: bool = True

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
