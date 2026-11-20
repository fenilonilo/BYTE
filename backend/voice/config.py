from __future__ import annotations

import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import MIN_TOKEN_LENGTH
from app.domain.exceptions import ConfigError


def _state_dir() -> Path:
    """systemd's StateDirectory= when run as a service, else data/ next to the code."""
    return Path(os.environ.get("STATE_DIRECTORY", "data").split(":")[0])


class VoiceSettings(BaseSettings):
    api_token: SecretStr = Field(validation_alias="BYTE_API_TOKEN")
    wake_model: str  # an openWakeWord model name (hey_jarvis) or a path to an .onnx file
    url: str = "ws://127.0.0.1:8000/api/v1/live"
    threshold: float = Field(default=0.5, gt=0.0, lt=1.0)
    idle_seconds: float = Field(default=8.0, gt=0.0)
    # false-wake guards (see voice/session.py SessionConfig)
    patience: int = Field(default=3, ge=1, le=12)
    cooldown_seconds: float = Field(default=2.0, ge=0.0)
    vad_threshold: float = Field(default=0.5, ge=0.0, lt=1.0)  # 0 = no VAD gate
    no_speech_seconds: float = Field(default=6.0, ge=0.0)  # 0 = never close for silence
    # ponytail: fixed RMS for this mic; voice.session_end logs peak_rms to recalibrate it
    speech_rms: int = Field(default=300, gt=0)
    # audio before each wake, kept to train and check the wake word; 0 = off
    clip_seconds: float = Field(default=10.0, ge=0.0, le=30.0)
    clip_keep: int = Field(default=500, ge=1)
    clip_dir: Path = Field(default_factory=lambda: _state_dir() / "voice_clips")
    segment: str = "auto"
    input_device: str | None = None
    output_device: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="BYTE_VOICE_",
        env_file=("../.env", ".env"),  # compose keeps .env at the repo root; later wins
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

    @field_validator("url")
    @classmethod
    def _url_keeps_the_token_private(cls, value: str) -> str:
        parts = urlsplit(value)
        if parts.scheme not in ("ws", "wss"):
            raise ValueError("must be a ws:// or wss:// URL")
        if parts.scheme == "ws" and parts.hostname not in ("127.0.0.1", "::1", "localhost"):
            raise ValueError("non-loopback URLs must use wss://")
        return value

    @field_validator("wake_model")
    @classmethod
    def _model_file_exists(cls, value: str) -> str:
        if value.endswith(".onnx") and not Path(value).is_file():
            raise ValueError("model file not found")
        return value


def load_voice_settings() -> VoiceSettings:
    """Build VoiceSettings or raise ConfigError naming the bad fields, never their values."""
    try:
        return VoiceSettings()  # pyright: ignore[reportCallIssue]
    except ValidationError as exc:
        problems = ", ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigError(f"invalid voice settings ({problems})") from exc
