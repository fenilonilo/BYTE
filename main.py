from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_evolution_client, get_logger, get_settings
from app.api.router import router
from app.api.voice import router as voice_router
from app.api.webhooks import router as webhook_router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log = get_logger()
    webhook_url = f"{settings.webhook_base_url}/api/v1/webhook/whatsapp"
    try:
        client = get_evolution_client()
        await client.configure_webhook(webhook_url)
        log.info("whatsapp.webhook.configured", url=webhook_url)
    except Exception as exc:
        log.warning("whatsapp.webhook.configure_failed", error=str(exc))
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(webhook_router, prefix="/api/v1")
