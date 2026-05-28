from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import cv2  # type: ignore[import-untyped]
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

_lock = threading.Lock()
_latest_jpeg: bytes | None = None


def set_latest_frame(frame_bgr: object) -> None:
    global _latest_jpeg
    ok, buf = cv2.imencode(".jpg", frame_bgr)
    if ok:
        with _lock:
            _latest_jpeg = buf.tobytes()


def _mjpeg_stream() -> Iterator[bytes]:
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    while True:
        with _lock:
            data = _latest_jpeg
        if data is not None:
            yield boundary + data + b"\r\n"
        time.sleep(0.015)


@router.get("/preview")
def preview() -> StreamingResponse:
    return StreamingResponse(
        _mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
