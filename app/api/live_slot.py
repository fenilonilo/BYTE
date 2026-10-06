from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import WebSocket

REPLACED_CLOSE_CODE = 4000


class LiveSlot:
    """One live session at a time: a new connection replaces the old one.

    After a Wi-Fi drop the old socket may be half-open for minutes; the owner reconnecting
    must win. Clients must not auto-reconnect after close code 4000."""

    def __init__(self) -> None:
        self._current: WebSocket | None = None

    async def claim(self, websocket: WebSocket) -> None:
        previous, self._current = self._current, websocket
        if previous is not None:
            with contextlib.suppress(RuntimeError):
                await previous.close(code=REPLACED_CLOSE_CODE)

    def release(self, websocket: WebSocket) -> None:
        if self._current is websocket:
            self._current = None
