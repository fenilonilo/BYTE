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
def test_files_are_revalidated_so_a_deploy_is_never_hidden_by_the_cache(tmp_path: Path) -> None:
    (tmp_path / "style.css").write_text("body{}")
    app = FastAPI()
    mount_web(app, tmp_path)
    client = TestClient(app)
    first = client.get("/style.css")
    assert first.headers["cache-control"] == "no-cache"
    again = client.get("/style.css", headers={"if-none-match": first.headers["etag"]})
    assert again.status_code == 304


@pytest.mark.unit
def test_missing_directory_mounts_nothing(tmp_path: Path) -> None:
    app = FastAPI()
    mount_web(app, tmp_path / "web")
    assert TestClient(app).get("/").status_code == 404
