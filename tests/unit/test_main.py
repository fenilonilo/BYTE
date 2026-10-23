from __future__ import annotations

import json
import os
import time
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.api.deps import get_settings
from app.domain.exceptions import ConfigError
from app.domain.knowledge import DocumentRef
from main import app, run
from tests.fakes.embedder import FakeEmbedder

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BYTE_API_TOKEN", raising=False)
    monkeypatch.delenv("BYTE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("BYTE_PROJECTS", raising=False)
    monkeypatch.delenv("BYTE_DATABASE_URL", raising=False)


@pytest.mark.unit
def test_app_boots_with_a_valid_config_and_guards_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "k" * 32)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.post("/api/v1/messages", json={"content": "oi"}).status_code == 401
        assert client.get("/api/v1/state").status_code == 401


@pytest.mark.unit
def test_app_refuses_to_boot_with_a_bad_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "too-short")
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with pytest.raises(ConfigError), TestClient(app):
        pass


@pytest.mark.unit
def test_panel_is_off_by_default_and_on_with_byte_web(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "k" * 32)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with TestClient(app) as client:
        assert client.get("/").status_code == 404
    monkeypatch.setenv("BYTE_WEB", "true")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            assert "Byte" in client.get("/").text
            assert client.get("/api/v1/state").status_code == 401
    finally:
        app.router.routes[:] = [r for r in app.routes if getattr(r, "name", "") != "web"]
        get_settings.cache_clear()


@pytest.mark.unit
def test_web_flag_sets_the_env_and_starts_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    started: dict[str, object] = {}
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: started.update(k))  # pyright: ignore
    monkeypatch.delenv("BYTE_WEB", raising=False)
    run(["--web", "--port", "9000"])
    assert os.environ["BYTE_WEB"] == "true"
    assert started["port"] == 9000


@pytest.mark.unit
def test_boot_indexes_the_projects_and_stops_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "CLAUDE.md").write_text("# Byte\nloopback", encoding="utf-8")
    monkeypatch.setenv("BYTE_API_TOKEN", "k" * 32)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BYTE_PROJECTS", json.dumps({"Byte": {"path": str(tmp_path)}}))
    monkeypatch.setattr(deps, "get_embedder", FakeEmbedder)  # no model download in a unit test
    with TestClient(app) as client:
        refs: object = ()
        for _ in range(100):
            refs = client.portal.call(deps.get_knowledge().documents)  # type: ignore[union-attr]
            if refs:
                break
            time.sleep(0.01)
        assert refs == (DocumentRef("Byte", "CLAUDE.md"),)
