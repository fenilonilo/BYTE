from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.adapters.agent.agno_agent import build_agents
from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.repository.in_memory_repository import InMemoryRepository
from app.application.registry import Registry
from app.config import Settings
from app.domain.exceptions import ClimateError, LightError, MusicError

if TYPE_CHECKING:
    from app.ports.agent import AgentPort
    from app.ports.climate import ClimatePort
    from app.ports.light import LightPort
    from app.ports.logger import LoggerPort
    from app.ports.music import MusicPort
    from app.ports.repository import RepositoryPort


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_repo() -> RepositoryPort:
    return InMemoryRepository()


@lru_cache
def get_agents() -> Registry[AgentPort]:
    registry: Registry[AgentPort] = Registry()
    for name, agent in build_agents(get_settings()).items():
        registry.register(name, agent)
    return registry


@lru_cache
def get_climate() -> ClimatePort:
    from app.adapters.thinq.thinq_climate import ThinQClimate  # noqa: PLC0415 - optional extra

    settings = get_settings()
    if settings.thinq_access_secret is None:
        raise ClimateError("BYTE_THINQ_ACCESS_SECRET is not set")
    return ThinQClimate(
        settings.thinq_access_secret.get_secret_value(),
        settings.thinq_country,
        settings.thinq_client_id,
    )


@lru_cache
def get_light() -> LightPort:
    from app.adapters.tuya.tuya_light import (  # noqa: PLC0415 - optional extra
        TuyaLight,
        TuyaLightDevice,
    )

    lights = get_settings().tuya_lights
    if not lights:
        raise LightError("BYTE_TUYA_LIGHTS is not set")
    return TuyaLight(
        {
            name: TuyaLightDevice(s.device_id, s.address, s.local_key.get_secret_value(), s.version)
            for name, s in lights.items()
        }
    )


@lru_cache
def get_music() -> MusicPort:
    from app.adapters.spotify.spotify_music import SpotifyMusic  # noqa: PLC0415 - optional extra

    settings = get_settings()
    if settings.spotify_client_id is None or settings.spotify_refresh_token is None:
        raise MusicError("BYTE_SPOTIFY_CLIENT_ID / BYTE_SPOTIFY_REFRESH_TOKEN not set")
    return SpotifyMusic(
        settings.spotify_client_id,
        settings.spotify_refresh_token.get_secret_value(),
        settings.spotify_device,
    )
