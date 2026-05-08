# app/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "marcelo"
    log_level: str = "INFO"
    default_channel: str = "api"

    # Database — asyncpg URL for SQLAlchemy; Agno adapters derive psycopg URL internally
    database_url: str = "postgresql+asyncpg://marcelo:marcelo@localhost:5432/marcelo"

    # Agno shared settings
    agno_add_datetime: bool = True
    agno_add_location: bool = True

    # Groq (Llama 3.3 70B — default model)
    groq_api_key: str = ""
    groq_model_id: str = "llama-3.3-70b-versatile"

    # Google Gemini (Gemini 1.5 Flash — complex/fallback model)
    google_api_key: str = ""
    gemini_model_id: str = "gemini-1.5-flash"

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
