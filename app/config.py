from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.exceptions import ConfigError
from app.domain.projects import PROJECT_NAME_PATTERN, Project

MIN_TOKEN_LENGTH = 32


class TuyaLightSettings(BaseModel):
    device_id: str
    address: str
    local_key: SecretStr
    version: float = 3.3


class ProjectSettings(BaseModel):
    path: str
    docs: list[str] = ["CLAUDE.md"]

    @field_validator("docs")
    @classmethod
    def _docs_stay_inside(cls, value: list[str]) -> list[str]:
        for doc in value:
            win, posix = PureWindowsPath(doc), PurePosixPath(doc)
            if win.is_absolute() or win.anchor or posix.is_absolute() or ".." in win.parts:
                raise ValueError("docs must be relative paths inside the project")
        return value


class Settings(BaseSettings):
    app_name: str = "byte"
    web: bool = False
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    timezone: str = "America/Sao_Paulo"  # the owner's wall clock: prompts, reminders, calendar
    api_token: SecretStr
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    chat_provider: Literal["openai", "gemini"] = "openai"
    chat_model: str = "gpt-4.1-mini"
    gemini_chat_model: str = "gemini-3.1-flash-lite"
    # Thinking is billed as output and buys nothing for tool calls; Pro models reject "minimal".
    gemini_thinking_level: Literal["minimal", "low", "medium", "high"] = "minimal"
    chat_timeout_seconds: float = 30.0
    tool_timeout_seconds: float = 10.0
    max_steps: int = 6
    history_limit: int = 20
    max_conversations: int = 50
    live_provider: Literal["openai", "gemini"] = "openai"
    live_model: str = "gpt-realtime-2.1-mini"
    gemini_live_model: str = "gemini-3.1-flash-live-preview"
    gemini_voice: str = "Charon"
    live_vad: Literal["server_vad", "semantic_vad"] = "server_vad"
    live_idle_seconds: float = 30.0
    live_max_seconds: float = 600.0
    live_transcript_wait_seconds: float = 2.0
    live_pace_factor: float = 0.9
    live_max_frame_bytes: int = 65536
    live_duck_percent: int = Field(default=20, ge=0, le=100)  # 100 = never lower the music
    # Real devices. Leave a group unset and Byte runs against the in-memory adapter instead.
    thinq_access_secret: SecretStr | None = None
    thinq_country: str = "BR"
    thinq_client_id: str = "byte-thinq-client"
    tuya_lights: dict[str, TuyaLightSettings] = {}
    spotify_client_id: str | None = None
    spotify_refresh_token: SecretStr | None = None
    spotify_device: str = ""
    # Google Calendar (scripts/google_login.py writes the refresh token). Unset: in-memory.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_refresh_token: SecretStr | None = None
    google_calendar_id: str = "primary"
    # Reminders: kept in a JSON file; spoken with a local Piper voice (.onnx), beep-only if unset.
    reminders_path: str = "data/reminders.json"
    piper_model: str | None = None
    # Projects (Spec 4): name -> folder + Markdown docs to index. Empty: the feature is off.
    projects: dict[str, ProjectSettings] = {}
    database_url: SecretStr | None = None  # postgresql+asyncpg://...; unset: in-memory index
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_cache: str = "data/models"
    knowledge_scan_seconds: float = Field(default=300.0, gt=0)
    claude_command: str = "claude"

    model_config = SettingsConfigDict(
        env_prefix="BYTE_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    @field_validator("api_token")
    @classmethod
    def _token_is_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_TOKEN_LENGTH:
            raise ValueError(f"must be at least {MIN_TOKEN_LENGTH} characters")
        return value

    @field_validator("projects")
    @classmethod
    def _project_names_are_keys(
        cls, value: dict[str, ProjectSettings]
    ) -> dict[str, ProjectSettings]:
        for name in value:
            if not re.fullmatch(PROJECT_NAME_PATTERN, name):
                raise ValueError("project names must match " + PROJECT_NAME_PATTERN)
        return value

    def project_list(self) -> tuple[Project, ...]:
        return tuple(
            Project(name, s.path, tuple(s.docs)) for name, s in sorted(self.projects.items())
        )

    @field_validator("timezone")
    @classmethod
    def _timezone_exists(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("unknown time zone") from exc
        return value

    @field_validator("openai_api_key")
    @classmethod
    def _key_is_not_empty(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value

    @model_validator(mode="after")
    def _providers_have_their_keys(self) -> Settings:
        providers = {self.chat_provider, self.live_provider}
        if "openai" in providers and self.openai_api_key is None:
            raise ValueError("openai_api_key is required when a provider is openai")
        if "gemini" in providers and self.gemini_api_key is None:
            raise ValueError("gemini_api_key is required when a provider is gemini")
        return self


def load_settings() -> Settings:
    """Build Settings or raise ConfigError naming the bad fields, never their values."""
    try:
        return Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as exc:
        problems = ", ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigError(f"invalid settings ({problems})") from exc
