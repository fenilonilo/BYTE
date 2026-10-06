from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from app.domain.exceptions import ConfigError
from voice.config import load_voice_settings

if TYPE_CHECKING:
    from pathlib import Path

TOKEN = "t" * 32


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:  # pyright: ignore[reportUnusedFunction]
    for name in [n for n in os.environ if n.startswith("BYTE_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)  # a developer's real .env must not leak into the test
    monkeypatch.setenv("BYTE_API_TOKEN", TOKEN)
    monkeypatch.setenv("BYTE_VOICE_WAKE_MODEL", "hey_jarvis")


def test_defaults() -> None:
    settings = load_voice_settings()
    assert settings.url == "ws://127.0.0.1:8000/api/v1/live"
    assert settings.threshold == 0.5
    assert settings.idle_seconds == 8.0
    assert settings.segment == "auto"
    assert settings.input_device is None
    assert settings.api_token.get_secret_value() == TOKEN


def test_short_token_is_rejected_without_echoing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "x" * 10)
    with pytest.raises(ConfigError, match="BYTE_API_TOKEN") as error:
        load_voice_settings()
    assert "x" * 10 not in str(error.value)


def test_wake_model_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BYTE_VOICE_WAKE_MODEL")
    with pytest.raises(ConfigError, match="wake_model"):
        load_voice_settings()


def test_missing_onnx_file_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BYTE_VOICE_WAKE_MODEL", str(tmp_path / "byte.onnx"))
    with pytest.raises(ConfigError, match="wake_model"):
        load_voice_settings()


def test_existing_onnx_file_is_accepted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = tmp_path / "byte.onnx"
    model.write_bytes(b"")
    monkeypatch.setenv("BYTE_VOICE_WAKE_MODEL", str(model))
    assert load_voice_settings().wake_model == str(model)


@pytest.mark.parametrize("value", ["0", "1", "1.5", "-0.2"])
def test_threshold_must_be_between_zero_and_one(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("BYTE_VOICE_THRESHOLD", value)
    with pytest.raises(ConfigError, match="threshold"):
        load_voice_settings()


@pytest.mark.parametrize(
    "url", ["ws://127.0.0.1:9/x", "ws://localhost/x", "wss://192.168.1.10:8000/api/v1/live"]
)
def test_safe_urls_are_accepted(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("BYTE_VOICE_URL", url)
    assert load_voice_settings().url == url


@pytest.mark.parametrize("url", ["ws://192.168.1.10:8000/api/v1/live", "http://127.0.0.1/x"])
def test_cleartext_remote_or_non_ws_urls_are_rejected(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("BYTE_VOICE_URL", url)
    with pytest.raises(ConfigError, match="url"):
        load_voice_settings()
