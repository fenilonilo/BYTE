from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions import ConfigError
from main import app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BYTE_API_TOKEN", raising=False)
    monkeypatch.delenv("BYTE_OPENAI_API_KEY", raising=False)


@pytest.mark.unit
def test_app_boots_with_a_valid_config_and_guards_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "k" * 32)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.post("/api/v1/messages", json={"content": "oi"}).status_code == 401


@pytest.mark.unit
def test_app_refuses_to_boot_with_a_bad_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "too-short")
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with pytest.raises(ConfigError), TestClient(app):
        pass
