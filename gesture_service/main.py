from __future__ import annotations

import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
import uvicorn
from fastapi import FastAPI

from gesture_service.capture import run_capture_loop
from gesture_service.config_api import build_router as build_config_router
from gesture_service.features import feature_vector
from gesture_service.knn import KnnClassifier
from gesture_service.matcher import GestureMatcher, HandFrame
from gesture_service.pose_store import PoseStore
from gesture_service.preview import router as preview_router, set_latest_frame
from gesture_service.publisher import EventPublisher

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from cv2.typing import MatLike

    from gesture_service.landmarks import HandLandmarks

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
_pose_store = PoseStore(Path("data/gesture_poses.json"))
_knn = KnnClassifier(threshold=0.6)
_latest_gesture: dict[str, object] = {"gesture": "none", "phase": "idle"}
_record: dict[str, object] = {"active": False, "label": "", "remaining": 0}


def _rebuild_knn() -> None:
    _knn._templates.clear()
    for label, vec in _pose_store.samples():
        _knn.add(label, vec)


def _record_start(label: str, frames: int) -> None:
    _record["label"] = label
    _record["remaining"] = frames
    _record["active"] = True


def _record_status() -> dict[str, object]:
    return {"active": _record["active"], "remaining": _record["remaining"]}


def _on_frame(
    frames: list[HandFrame], raw_hands: list[HandLandmarks], annotated: MatLike
) -> None:
    set_latest_frame(annotated)
    if _record["active"] and raw_hands:
        vec = feature_vector(raw_hands[0])
        _pose_store.add_sample(str(_record["label"]), vec)
        _record["remaining"] = int(_record["remaining"]) - 1  # type: ignore[arg-type]
        if int(_record["remaining"]) <= 0:  # type: ignore[arg-type]
            _record["active"] = False
            _pose_store.persist()
            _rebuild_knn()
    event = _matcher.update(frames, now=time.monotonic())
    if event is not None:
        _latest_gesture["gesture"] = event.gesture
        _latest_gesture["phase"] = event.phase
        _publisher.publish(event)
        log.info("gesture", gesture=event.gesture, phase=event.phase, hands=event.hands)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    _pose_store.load()
    _rebuild_knn()
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
app.include_router(
    build_config_router(
        _pose_store, _rebuild_knn, _latest_gesture, _record_start, _record_status
    )
)


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
