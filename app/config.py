# app/config.py
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "marcelo"
    log_level: str = "INFO"
    default_channel: str = "api"
    workspace_path: Path = Path("D:/Projetos/Projetos_Marcelo")

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
