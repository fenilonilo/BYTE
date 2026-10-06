from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.config import load_settings

if TYPE_CHECKING:
    from pathlib import Path

GOOD_TOKEN = "k" * 32


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A valid core config, no .env in the working directory and no device configured."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    for name in ("BYTE_TUYA_LIGHTS", "BYTE_THINQ_ACCESS_SECRET", "BYTE_SPOTIFY_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_devices_default_to_unset() -> None:
    settings = load_settings()
    assert settings.tuya_lights == {}
    assert settings.thinq_access_secret is None
    assert settings.spotify_client_id is None


@pytest.mark.unit
def test_blank_device_variables_are_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_TUYA_LIGHTS", "")
    monkeypatch.setenv("BYTE_THINQ_ACCESS_SECRET", "")
    settings = load_settings()
    assert settings.tuya_lights == {}
    assert settings.thinq_access_secret is None


@pytest.mark.unit
def test_tuya_lights_are_read_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "BYTE_TUYA_LIGHTS",
        '{"lampada": {"device_id": "d", "address": "192.168.0.5", "local_key": "k"}}',
    )
    lamp = load_settings().tuya_lights["lampada"]
    assert (lamp.device_id, lamp.address, lamp.version) == ("d", "192.168.0.5", 3.3)
    assert lamp.local_key.get_secret_value() == "k"
