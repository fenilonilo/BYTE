from __future__ import annotations

import threading
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
import uvicorn
from cv2.typing import MatLike
from fastapi import FastAPI

from gesture_service.capture import run_capture_loop
from gesture_service.matcher import GestureMatcher, HandFrame
from gesture_service.preview import router as preview_router
from gesture_service.preview import set_latest_frame

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger("gesture-service")

_stop = threading.Event()
_matcher = GestureMatcher()


def _on_frame(frames: list[HandFrame], annotated: MatLike) -> None:
    set_latest_frame(annotated)
    event = _matcher.update(frames, now=time.monotonic())
    if event is not None:
        log.info("gesture", gesture=event.gesture, phase=event.phase, hands=event.hands)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    thread = threading.Thread(
        target=run_capture_loop,
        kwargs={"on_frame": _on_frame, "stop": _stop.is_set},
        daemon=True,
    )
    thread.start()
    log.info("capture-thread-started")
    yield
    _stop.set()


app = FastAPI(title="Marcelo Gesture Service", lifespan=lifespan)
app.include_router(preview_router)


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
