# main.py
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_event_bus, get_evolution_client, get_settings
from app.api.gesture_ingest import router as gesture_ingest_router
from app.api.router import router
from app.api.voice import router as voice_router
from app.api.webhooks import router as webhook_router
from app.api.ws_chat import router as ws_chat_router
from app.api.ws_gesture import frontend_bridge, router as ws_gesture_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

# Windows: use SelectorEventLoop to avoid ProactorEventLoop issues with asyncpg
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    try:
        client = get_evolution_client()
        await client.configure_webhook(
            webhook_url=f"{settings.webhook_base_url}/api/v1/webhook/whatsapp",
        )
    except Exception:  # noqa: S110 — WhatsApp gateway may not be available in dev
        pass
    get_event_bus().subscribe(frontend_bridge)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routes under /api/v1
app.include_router(router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/api/v1")

# WebSocket — mounted at /ws/chat (Vite proxy: /ws → ws://localhost:8000)
app.include_router(ws_chat_router)
app.include_router(ws_gesture_router)
app.include_router(gesture_ingest_router)
