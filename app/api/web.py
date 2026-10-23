from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi import FastAPI


def mount_web(app: FastAPI, directory: Path) -> None:
    """Serve the static panel at `/` (public, holds no data). Call after the API routers."""
    if directory.is_dir() and not any(getattr(r, "name", None) == "web" for r in app.routes):
        app.mount("/", StaticFiles(directory=directory, html=True), name="web")
