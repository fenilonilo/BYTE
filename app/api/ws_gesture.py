from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

if TYPE_CHECKING:
    from app.domain.gestures import GestureEvent

router = APIRouter()


class _ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def remove(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, event: GestureEvent) -> None:
        payload = {
            "gesture": event.gesture,
            "phase": event.phase,
            "hands": event.hands,
            "params": asdict(event.params),
            "ts": event.ts,
        }
        async with self._lock:
            targets = list(self._clients)
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.remove(ws)


manager = _ConnectionManager()


async def frontend_bridge(event: GestureEvent) -> None:
    """Bus subscriber: forward every gesture event to connected browsers."""
    await manager.broadcast(event)


@router.websocket("/ws/gesture")
async def ws_gesture(websocket: WebSocket) -> None:
    await manager.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # keepalive; browser sends nothing meaningful
    except WebSocketDisconnect:
        await manager.remove(websocket)
