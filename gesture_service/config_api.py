from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from pydantic import BaseModel

if TYPE_CHECKING:
    from collections.abc import Callable

    from gesture_service.pose_store import PoseStore


class CaptureRequest(BaseModel):
    vectors: list[list[float]]


def build_router(
    pose_store: PoseStore,
    rebuild_knn: Callable[[], None],
    latest_gesture: dict[str, object],
    record_start: Callable[[str, int], None],
    record_status: Callable[[], dict[str, object]],
) -> APIRouter:
    router = APIRouter()

    @router.post("/poses/{label}")
    def add_pose(label: str, body: CaptureRequest) -> dict[str, int]:
        for vec in body.vectors:
            pose_store.add_sample(label, tuple(vec))
        pose_store.persist()
        rebuild_knn()
        return {"samples": len(pose_store.samples())}

    @router.post("/poses/{label}/record")
    def record(label: str, frames: int = 15) -> dict[str, bool]:
        record_start(label, frames)
        return {"ok": True}

    @router.get("/poses/record/status")
    def record_status_endpoint() -> dict[str, object]:
        return record_status()

    @router.get("/current")
    def current() -> dict[str, object]:
        return dict(latest_gesture)

    @router.post("/reload")
    def reload() -> dict[str, bool]:
        pose_store.load()
        rebuild_knn()
        return {"ok": True}

    return router
