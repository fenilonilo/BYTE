from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import MIN_TOKEN_LENGTH
from app.domain.exceptions import ConfigError


class VoiceSettings(BaseSettings):
    api_token: SecretStr = Field(validation_alias="BYTE_API_TOKEN")
    wake_model: str  # an openWakeWord model name (hey_jarvis) or a path to an .onnx file
    url: str = "ws://127.0.0.1:8000/api/v1/live"
    threshold: float = Field(default=0.5, gt=0.0, lt=1.0)
    idle_seconds: float = Field(default=8.0, gt=0.0)
    segment: str = "auto"
    input_device: str | None = None
    output_device: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="BYTE_VOICE_",
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
