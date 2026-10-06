from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.adapters.logging.structlog_logger import configure_logging
from app.api.deps import (
    get_chat_model,
    get_climate,
    get_light,
    get_live_port,
    get_logger,
    get_music,
    get_runner,
    get_settings,
)
from app.api.errors import install_error_handlers
from app.api.live import router as live_router
from app.api.router import router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()  # a bad config stops the boot here, not at the first request
    configure_logging(settings.log_level, json=not sys.stdout.isatty())
    get_chat_model()
    get_live_port()
    runner = get_runner()
    # Which adapter drives each device group: an in-memory name here means "not configured".
    get_logger().info(
        "adapters.selected",
        light=type(get_light()).__name__,
        climate=type(get_climate()).__name__,
        music=type(get_music()).__name__,
    )
    yield
    await runner.drain()


app = FastAPI(title="byte", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
app.include_router(live_router, prefix="/api/v1")
install_error_handlers(app)
