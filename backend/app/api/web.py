from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    import os
    from pathlib import Path

    from fastapi import FastAPI
    from starlette.responses import Response
    from starlette.types import Scope


class _RevalidatedFiles(StaticFiles):
    # Without Cache-Control the browser caches by heuristic and can pair a new index.html
    # with a stylesheet from weeks ago. no-cache still lets the ETag answer 304.
    def file_response(
        self,
        full_path: str | os.PathLike[str],
        stat_result: os.stat_result,
        scope: Scope,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-cache"
        return response


def mount_web(app: FastAPI, directory: Path) -> None:
    """Serve the static panel at `/` (public, holds no data). Call after the API routers."""
    if directory.is_dir() and not any(getattr(r, "name", None) == "web" for r in app.routes):
        app.mount("/", _RevalidatedFiles(directory=directory, html=True), name="web")
