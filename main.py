from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn
from fastapi import FastAPI

from app.adapters.logging.structlog_logger import configure_logging
from app.api.control import router as control_router
from app.api.deps import (
    get_calendar,
    get_chat_model,
    get_climate,
    get_indexer,
    get_knowledge,
    get_light,
    get_live_port,
    get_logger,
    get_music,
    get_project_session,
    get_reminder_hub,
    get_runner,
    get_settings,
    get_speech,
    get_wall_clock,
)
from app.api.errors import install_error_handlers
from app.api.live import router as live_router
from app.api.notifications import router as notifications_router, run_reminders
from app.api.router import router
from app.api.terminal import router as terminal_router
from app.api.web import mount_web
from app.application.knowledge_indexer import run_indexer

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()  # a bad config stops the boot here, not at the first request
    configure_logging(settings.log_level, json=not sys.stdout.isatty())
    if settings.web:
        mount_web(app, WEB_DIR)
    if settings.database_url is not None:
        from app.adapters.postgres.migrate import upgrade  # noqa: PLC0415 - optional extra

        await asyncio.to_thread(upgrade, settings.database_url.get_secret_value())
    get_chat_model()
    get_live_port()
    runner = get_runner()
    # Which adapter drives each device group: an in-memory name here means "not configured".
    get_logger().info(
        "adapters.selected",
        light=type(get_light()).__name__,
        climate=type(get_climate()).__name__,
        music=type(get_music()).__name__,
        calendar=type(get_calendar()).__name__,
        speech=type(get_speech()).__name__,
        knowledge=type(get_knowledge()).__name__,
        terminal=(session := get_project_session()) is not None,
        web=settings.web,
    )
    reminders = asyncio.create_task(
        run_reminders(get_reminder_hub(), get_wall_clock(), get_logger())
    )
    background = [reminders]
    if (indexer := get_indexer()) is not None:
        background.append(
            asyncio.create_task(run_indexer(indexer, settings.knowledge_scan_seconds, get_logger()))
        )
    yield
    for task in background:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await runner.drain()
    if session is not None:
        await session.aclose()  # never leave a claude process behind the server
    if (close := getattr(get_knowledge(), "aclose", None)) is not None:
        await close()


WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="byte", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
app.include_router(live_router, prefix="/api/v1")
app.include_router(control_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")
app.include_router(terminal_router, prefix="/api/v1")
install_error_handlers(app)


def run(argv: list[str] | None = None) -> None:
    """`python main.py [--web]`: same as uvicorn, plus the panel on request (or BYTE_WEB=true)."""
    parser = argparse.ArgumentParser(prog="byte")
    parser.add_argument("--web", action="store_true", help="serve the web control panel at /")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.web:
        os.environ["BYTE_WEB"] = "true"
    cert, key = os.environ.get("BYTE_TLS_CERT"), os.environ.get("BYTE_TLS_KEY")
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        access_log=False,
        ssl_certfile=cert or None,
        ssl_keyfile=key if cert else None,
    )


if __name__ == "__main__":
    run()
