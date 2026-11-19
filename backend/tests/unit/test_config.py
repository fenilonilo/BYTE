from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.config import MIN_TOKEN_LENGTH, load_settings
from app.domain.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path

GOOD_TOKEN = "k" * MIN_TOKEN_LENGTH


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No .env in the working directory and no BYTE_* variables from the machine."""
    monkeypatch.chdir(tmp_path)
    for name in ("BYTE_API_TOKEN", "BYTE_OPENAI_API_KEY", "BYTE_CHAT_MODEL", "BYTE_LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_valid_environment_loads_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    settings = load_settings()
    assert settings.api_token.get_secret_value() == GOOD_TOKEN
    assert settings.chat_model == "gpt-4.1-mini"
    assert settings.log_level == "INFO"


@pytest.mark.unit
def test_short_token_refuses_to_boot_without_echoing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "short-secret")
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with pytest.raises(ConfigError) as info:
        load_settings()
    assert "api_token" in str(info.value)
    assert "short-secret" not in str(info.value)


@pytest.mark.unit
def test_empty_openai_key_refuses_to_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "")
    with pytest.raises(ConfigError, match="openai_api_key"):
        load_settings()


@pytest.mark.unit
def test_missing_secrets_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigError, match="api_token"):
        load_settings()
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    with pytest.raises(ConfigError, match="openai_api_key"):
        load_settings()


@pytest.mark.unit
def test_unknown_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BYTE_LOG_LEVEL", "LOUD")
    with pytest.raises(ConfigError, match="log_level"):
        load_settings()


@pytest.mark.unit
def test_gemini_live_provider_needs_its_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BYTE_LIVE_PROVIDER", "gemini")
    with pytest.raises(ConfigError, match="gemini_api_key"):
        load_settings()
    monkeypatch.setenv("BYTE_GEMINI_API_KEY", "g-test")
    assert load_settings().live_provider == "gemini"


@pytest.mark.unit
def test_google_only_boots_without_an_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_CHAT_PROVIDER", "gemini")
    monkeypatch.setenv("BYTE_LIVE_PROVIDER", "gemini")
    monkeypatch.setenv("BYTE_GEMINI_API_KEY", "g-test")
    assert load_settings().openai_api_key is None


@pytest.mark.unit
@pytest.mark.parametrize(("raw", "ok"), [("20", True), ("0", True), ("100", True), ("101", False)])
def test_live_duck_percent_is_bounded(monkeypatch: pytest.MonkeyPatch, raw: str, ok: bool) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BYTE_LIVE_DUCK_PERCENT", raw)
    if ok:
        assert load_settings().live_duck_percent == int(raw)
    else:
        with pytest.raises(ConfigError):
            load_settings()


@pytest.mark.unit
def test_unknown_timezone_refuses_to_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    assert load_settings().timezone == "America/Sao_Paulo"
    monkeypatch.setenv("BYTE_TIMEZONE", "Mars/Olympus")
    with pytest.raises(ConfigError, match="timezone"):
        load_settings()


@pytest.mark.unit
def test_weather_home_defaults_to_goiania_and_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    assert load_settings().weather_home == "Goiânia, GO"
    monkeypatch.setenv("BYTE_WEATHER_HOME", "Florianópolis, SC")
    assert load_settings().weather_home == "Florianópolis, SC"
