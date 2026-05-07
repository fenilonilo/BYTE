# main.py
from __future__ import annotations

import structlog
from fastapi import FastAPI

from app.api.deps import get_settings
from app.api.router import router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(router, prefix="/api/v1")
