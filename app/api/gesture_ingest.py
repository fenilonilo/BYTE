from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_event_bus, get_logger
from app.api.schemas import GestureEventSchema

router = APIRouter()


@router.websocket("/ws/gesture-ingest")
async def ws_gesture_ingest(websocket: WebSocket) -> None:
    await websocket.accept()
    bus = get_event_bus()
    log = get_logger()
    try:
        while True:
            raw = await websocket.receive_json()
            try:
                event = GestureEventSchema.model_validate(raw).to_domain()
            except Exception as exc:  # malformed payload from service
                log.info("gesture-ingest-invalid", error=str(exc))
                continue
            await bus.publish(event)
    except WebSocketDisconnect:
        pass
