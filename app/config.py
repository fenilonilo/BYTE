from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.exceptions import ConfigError

MIN_TOKEN_LENGTH = 32


class TuyaLightSettings(BaseModel):
    device_id: str
    address: str
    local_key: SecretStr
    version: float = 3.3


class Settings(BaseSettings):
    app_name: str = "byte"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_token: SecretStr
    openai_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    chat_provider: Literal["openai", "gemini"] = "openai"
    chat_model: str = "gpt-4.1-mini"
    gemini_chat_model: str = "gemini-3.1-flash-lite"
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
    # Real devices. Leave a group unset and Byte runs against the in-memory adapter instead.
    thinq_access_secret: SecretStr | None = None
    thinq_country: str = "BR"
    thinq_client_id: str = "byte-thinq-client"
    tuya_lights: dict[str, TuyaLightSettings] = {}
    spotify_client_id: str | None = None
    spotify_refresh_token: SecretStr | None = None
    spotify_device: str = ""

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
