from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.web import mount_web

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.unit
def test_serves_the_directory_publicly_and_leaves_api_routes_alone(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>byte</h1>")
    app = FastAPI()

    @app.get("/api/v1/health")
    async def health() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    mount_web(app, tmp_path)
    client = TestClient(app)
    assert "<h1>byte</h1>" in client.get("/").text
    assert client.get("/api/v1/health").json() == {"status": "ok"}


@pytest.mark.unit
def test_missing_directory_mounts_nothing(tmp_path: Path) -> None:
    app = FastAPI()
    mount_web(app, tmp_path / "web")
    assert TestClient(app).get("/").status_code == 404
