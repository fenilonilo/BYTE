from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.adapters.spotify.spotify_music import SpotifyMusic
from app.adapters.thinq.thinq_climate import ThinQClimate
from app.adapters.tuya.tuya_light import TuyaLight
from app.api import deps

if TYPE_CHECKING:
    from pathlib import Path

LAMP = '{"lampada": {"device_id": "d", "address": "192.168.0.5", "local_key": "k", "version": 3.3}}'
DEVICE_VARIABLES = (
    "BYTE_TUYA_LIGHTS",
    "BYTE_THINQ_ACCESS_SECRET",
    "BYTE_SPOTIFY_CLIENT_ID",
    "BYTE_SPOTIFY_REFRESH_TOKEN",
)


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A valid core config, no .env in the working directory and no device configured."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BYTE_API_TOKEN", "k" * 32)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    for name in DEVICE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_unconfigured_devices_run_against_the_in_memory_adapters() -> None:
    assert isinstance(deps.get_light(), InMemoryLight)
    assert isinstance(deps.get_climate(), InMemoryClimate)
    assert isinstance(deps.get_music(), InMemoryMusic)


@pytest.mark.unit
def test_configured_lamps_select_the_tuya_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_TUYA_LIGHTS", LAMP)
    assert isinstance(deps.get_light(), TuyaLight)


@pytest.mark.unit
def test_a_thinq_token_selects_the_thinq_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_THINQ_ACCESS_SECRET", "token")
    assert isinstance(deps.get_climate(), ThinQClimate)


@pytest.mark.unit
def test_spotify_needs_both_the_client_id_and_the_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BYTE_SPOTIFY_CLIENT_ID", "client")
    assert isinstance(deps.get_music(), InMemoryMusic)
    deps.get_settings.cache_clear()
    deps.get_music.cache_clear()
    monkeypatch.setenv("BYTE_SPOTIFY_REFRESH_TOKEN", "refresh")
    assert isinstance(deps.get_music(), SpotifyMusic)


@pytest.mark.unit
def test_the_tool_registry_uses_whatever_adapters_were_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BYTE_TUYA_LIGHTS", LAMP)
    names = {t.spec.name for t in deps.get_tools().values()}
    assert {"set_light", "set_climate", "play_music", "delete_event", "add_expense"} <= names
