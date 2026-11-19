from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, cast

from fastapi import WebSocketDisconnect

from app.application.live_transport import LiveTransport

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from fastapi import WebSocket

    from app.application.live_transport import ClientFrame

BYTES_PER_SECOND = 24000 * 2  # PCM16 mono at 24 kHz
CLOSE_MESSAGE_TOO_BIG = 1009
DRAIN_SECONDS = 1.0


def _json_object(text: str) -> Mapping[str, object] | None:
    try:
        parsed: object = json.loads(text)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


class WebSocketTransport(LiveTransport):
    """Server end of the live WebSocket.

    Everything leaves through one ordered outbox. Audio is paced at roughly real time
    because the provider sends faster than the device can play; an `interrupt` event
    flushes whatever audio is still queued.

    ponytail: the outbox is unbounded (one response of audio is well under 1 MB); bound it
    if a provider ever streams minutes of audio in one response."""

    def __init__(self, websocket: WebSocket, *, pace_factor: float, max_frame_bytes: int) -> None:
        self._ws = websocket
        self._pace = pace_factor
        self._max_frame_bytes = max_frame_bytes
        self._outbox: asyncio.Queue[bytes | Mapping[str, object]] = asyncio.Queue()
        self._sender = asyncio.create_task(self._send_loop())

    async def incoming(self) -> AsyncIterator[ClientFrame]:
        while True:
            try:
                message = await self._ws.receive()
            except RuntimeError:  # receive() after the socket was closed
                return
            if message["type"] == "websocket.disconnect":
                return
            data = message.get("bytes")
            if data is not None:
                if len(data) > self._max_frame_bytes:
                    with contextlib.suppress(RuntimeError):
                        await self._ws.close(code=CLOSE_MESSAGE_TOO_BIG)
                    return
                yield data
            elif (text := message.get("text")) is not None and (frame := _json_object(text)):
                yield frame

    async def send_audio(self, data: bytes) -> None:
        self._outbox.put_nowait(data)

    async def send_event(self, event: Mapping[str, object]) -> None:
        if event.get("type") == "interrupt":
            self._discard_queued()
        self._outbox.put_nowait(event)

    async def aclose(self) -> None:
        """Give queued events a moment to leave (a final `error`, say), then stop."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._outbox.join(), DRAIN_SECONDS)
        self._sender.cancel()
        await asyncio.gather(self._sender, return_exceptions=True)

    def _discard_queued(self) -> None:
        while not self._outbox.empty():
            self._outbox.get_nowait()
            self._outbox.task_done()

    async def _send_loop(self) -> None:
        while True:
            item = await self._outbox.get()
            try:
                if isinstance(item, bytes):
                    await self._ws.send_bytes(item)
                    await asyncio.sleep(len(item) / BYTES_PER_SECOND * self._pace)
                else:
                    await self._ws.send_json(dict(item))
            except (WebSocketDisconnect, RuntimeError):
                self._outbox.task_done()
                self._discard_queued()
                return
            self._outbox.task_done()
