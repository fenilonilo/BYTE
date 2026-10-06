from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class FakeSocket:
    """In-memory /live peer: tests push server messages and read what the client sent."""

    def __init__(self) -> None:
        self.sent: list[str | bytes] = []
        self.closed = False
        self._inbox: asyncio.Queue[str | bytes | None] = asyncio.Queue()

    def push(self, message: str | bytes | dict[str, object]) -> None:
        self._inbox.put_nowait(json.dumps(message) if isinstance(message, dict) else message)

    def end(self) -> None:
        self._inbox.put_nowait(None)

    async def send(self, message: str | bytes) -> None:
        if self.closed:
            raise ConnectionError("socket is closed")
        self.sent.append(message)

    async def close(self) -> None:
        self.closed = True
        self._inbox.put_nowait(None)

    async def __aiter__(self) -> AsyncIterator[str | bytes]:
        while (message := await self._inbox.get()) is not None:
            yield message

    def events(self) -> list[dict[str, object]]:
        return [cast("dict[str, object]", json.loads(m)) for m in self.sent if isinstance(m, str)]

    def audio(self) -> list[bytes]:
        return [m for m in self.sent if isinstance(m, bytes)]


class FakeSpeaker:
    def __init__(self) -> None:
        self.played: list[bytes] = []
        self.is_busy = False
        self.cleared = 0
        self.played_ms = 1234

    def play(self, pcm: bytes) -> None:
        self.played.append(pcm)

    def busy(self) -> bool:
        return self.is_busy

    def clear(self) -> int:
        self.cleared += 1
        return self.played_ms


class FakeDetector:
    def __init__(self) -> None:
        self.wake_next = False
        self.calls = 0
        self.resets = 0

    def __call__(self, frame: bytes) -> bool:
        self.calls += 1
        fired, self.wake_next = self.wake_next, False
        return fired

    def reset(self) -> None:
        self.resets += 1
