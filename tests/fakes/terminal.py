from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.application.project_session import TerminalListener
from app.ports.terminal import ProjectTerminalPort

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class FakeTerminal(ProjectTerminalPort):
    def __init__(self) -> None:
        self.started: list[tuple[str, tuple[str, ...], dict[str, str]]] = []
        self.written: list[bytes] = []
        self.sizes: list[tuple[int, int]] = []
        self.stops = 0
        self._alive = False
        self._out: asyncio.Queue[bytes] = asyncio.Queue()

    @property
    def alive(self) -> bool:
        return self._alive

    async def start(
        self, cwd: str, argv: Sequence[str], env: Mapping[str, str], cols: int, rows: int
    ) -> None:
        self._out = asyncio.Queue()
        self._alive = True
        self.started.append((cwd, tuple(argv), dict(env)))
        self.sizes.append((cols, rows))

    async def write(self, data: bytes) -> None:
        self.written.append(data)

    async def resize(self, cols: int, rows: int) -> None:
        self.sizes.append((cols, rows))

    async def read(self) -> bytes:
        return await self._out.get()

    async def stop(self) -> None:
        self.stops += 1
        if self._alive:
            self._alive = False
            self._out.put_nowait(b"")

    def feed(self, data: bytes) -> None:
        self._out.put_nowait(data)

    def exit(self) -> None:
        self._alive = False
        self._out.put_nowait(b"")


class RecordingListener(TerminalListener):
    def __init__(self) -> None:
        self.states: list[str | None] = []
        self.received = bytearray()
        self.events: list[str] = []

    async def state(self, project: str | None) -> None:
        self.states.append(project)
        self.events.append(f"state:{project}")

    async def output(self, data: bytes) -> None:
        self.received += data
        self.events.append(f"output:{data.decode()}")


async def settle() -> None:
    """Let the session's reader task run; no wall-clock sleeping."""
    for _ in range(10):
        await asyncio.sleep(0)
