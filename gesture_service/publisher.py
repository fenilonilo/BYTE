from __future__ import annotations

import asyncio
import contextlib
import json
import queue
import threading
from dataclasses import asdict
from typing import TYPE_CHECKING

import websockets

from gesture_service.config import ServiceSettings

if TYPE_CHECKING:
    from gesture_service.events import GestureEvent


class EventPublisher:
    """Thread-safe queue drained by a background asyncio loop that ships
    events to the backend ingest WebSocket, reconnecting on drop."""

    def __init__(self, settings: ServiceSettings | None = None) -> None:
        self._settings = settings or ServiceSettings()
        self._queue: queue.Queue[GestureEvent] = queue.Queue(maxsize=256)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._stop = threading.Event()

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def publish(self, event: GestureEvent) -> None:
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(event)

    def _payload(self, ev: GestureEvent) -> str:
        return json.dumps(
            {
                "gesture": ev.gesture,
                "phase": ev.phase,
                "hands": ev.hands,
                "params": asdict(ev.params),
                "ts": ev.ts,
            }
        )

    def _run(self) -> None:
        asyncio.run(self._loop())

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                async with websockets.connect(self._settings.backend_ingest_url) as ws:
                    while not self._stop.is_set():
                        try:
                            ev = self._queue.get(timeout=0.1)
                        except queue.Empty:
                            await asyncio.sleep(0)
                            continue
                        await ws.send(self._payload(ev))
            except Exception:
                await asyncio.sleep(self._settings.reconnect_seconds)
