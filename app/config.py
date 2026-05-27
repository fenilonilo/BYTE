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
    # Tool-use model: supports OpenAI-style function calling
    groq_tools_model_id: str = "meta-llama/llama-4-scout-17b-16e-instruct"

    # Groq TTS — Orpheus v1
    groq_tts_model: str = "canopylabs/orpheus-v1-english"
    groq_tts_voice: str = "daniel"

    # Developer tools
    workspace_path: str = ""  # resolved at runtime to ~/Desktop/marcelo if empty
    pycharm_path: str = r"C:\Users\fenil\AppData\Local\Programs\PyCharm 2025.2.0.1\bin\pycharm.bat"

    # Google Gemini (Gemini 1.5 Flash — complex/fallback model)
    google_api_key: str = ""
    gemini_model_id: str = "gemini-1.5-flash"

    # Evolution API (WhatsApp gateway)
    evolution_api_url: str = "http://evolution-api:8080"
    evolution_api_key: str = "admin"
    evolution_instance_name: str = "WhatsApp"
    whatsapp_target_group: str = "Marcelo_IA"
    # URL this app is reachable at from inside docker network
    webhook_base_url: str = "http://app:8000"

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
