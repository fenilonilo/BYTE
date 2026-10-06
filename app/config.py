from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TuyaLightSettings(BaseModel):
    device_id: str
    address: str
    local_key: SecretStr
    version: float = 3.3


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
    )
