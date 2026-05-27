from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Path:
    """Create 3 fake project directories with varying mtimes."""
    for name in ("alpha", "beta", "gamma"):
        d = tmp_path / name
        d.mkdir()
    # force mtime order: gamma newest
    now = time.time()
    os.utime(tmp_path / "alpha", (now - 200, now - 200))
    os.utime(tmp_path / "beta",  (now - 100, now - 100))
    os.utime(tmp_path / "gamma", (now,       now))
    return tmp_path


def test_projects_returns_dirs_sorted_by_mtime(tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARCELO_WORKSPACE_PATH", str(tmp_workspace))
    # re-import after env patch
    from importlib import reload
    import app.config as cfg_mod
    reload(cfg_mod)
    import app.api.router as router_mod
    reload(router_mod)
    from main import app
    client = TestClient(app)

    resp = client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    names = [d["name"] for d in data]
    # newest first
    assert names[0] == "gamma"
    assert names[-1] == "alpha"
    for item in data:
        assert "name" in item
        assert "path" in item
        assert "mtime" in item


def test_projects_skips_files(tmp_workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_workspace / "README.md").write_text("hello")
    monkeypatch.setenv("MARCELO_WORKSPACE_PATH", str(tmp_workspace))
    from importlib import reload
    import app.config as cfg_mod
    reload(cfg_mod)
    import app.api.router as router_mod
    reload(router_mod)
    from main import app
    client = TestClient(app)

    resp = client.get("/api/v1/projects")
    data = resp.json()
    names = [d["name"] for d in data]
    assert "README.md" not in names
