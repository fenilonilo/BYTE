from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
import uvicorn
from fastapi import FastAPI

from gesture_service.capture import run_capture_loop
from gesture_service.matcher import GestureMatcher, HandFrame
from gesture_service.preview import router as preview_router, set_latest_frame
from gesture_service.publisher import EventPublisher

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cv2.typing import MatLike

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
_publisher = EventPublisher()


def _on_frame(frames: list[HandFrame], annotated: MatLike) -> None:
    set_latest_frame(annotated)
    event = _matcher.update(frames, now=time.monotonic())
    if event is not None:
        _publisher.publish(event)
        log.info("gesture", gesture=event.gesture, phase=event.phase, hands=event.hands)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    _publisher.start()
    thread = threading.Thread(
        target=run_capture_loop,
        kwargs={"on_frame": _on_frame, "stop": _stop.is_set},
        daemon=True,
    )
    thread.start()
    log.info("capture-thread-started")
    yield
    _stop.set()
    _publisher.stop()


app = FastAPI(title="Marcelo Gesture Service", lifespan=lifespan)
app.include_router(preview_router)


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
