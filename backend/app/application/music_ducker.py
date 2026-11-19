from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from app.domain.music import MAX_VOLUME, PlaybackChange

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Coroutine

    from app.ports.logger import LoggerPort
    from app.ports.music import MusicPort


class MusicDucker:
    """Lowers music while a live session runs and restores it afterwards. Never raises.

    Overlapping sessions (a replacement) share one duck: the original volume is kept until
    the last one ends. A volume the agent set meanwhile wins over the remembered one."""

    def __init__(self, music: MusicPort, log: LoggerPort, percent: int) -> None:
        self._music = music
        self._log = log
        self._percent = percent
        self._lock = asyncio.Lock()
        self._sessions = 0
        self._original: int | None = None  # set only while we hold the volume down
        self._chosen: int | None = None
        self._tasks: set[asyncio.Task[None]] = set()

    def note_volume(self, volume: int) -> None:
        """The agent (control_music) picked a volume: restore to it, not to the old one."""
        if self._sessions:
            self._chosen = volume

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncGenerator[None]:
        if self._percent >= MAX_VOLUME:
            yield
            return
        enter = self._spawn(self._enter())
        try:
            yield
        finally:
            # shielded: a dropped socket or a replaced session must still restore the volume
            await asyncio.shield(self._spawn(self._leave(enter)))

    def _spawn(self, coro: Coroutine[object, object, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _enter(self) -> None:
        async with self._lock:
            self._sessions += 1
            if self._sessions > 1:
                return
            self._chosen = None
            await self._duck()

    async def _leave(self, enter: asyncio.Task[None]) -> None:
        await asyncio.wait({enter})
        async with self._lock:
            self._sessions -= 1
            if self._sessions == 0:
                await self._restore()

    async def _duck(self) -> None:
        try:
            state = await self._music.state()
            if not state.playing or not state.device or state.volume <= self._percent:
                self._skip("idle")
                return
            if self._chosen is not None:
                self._skip("agent_chose")
                return
            await self._music.apply(PlaybackChange(volume=self._percent))
            self._original = state.volume
        except Exception as exc:
            self._skip(type(exc).__name__)

    async def _restore(self) -> None:
        original, chosen = self._original, self._chosen
        self._original = self._chosen = None
        if original is None:
            return
        try:
            await self._music.apply(PlaybackChange(volume=original if chosen is None else chosen))
        except Exception as exc:
            self._skip(type(exc).__name__)

    def _skip(self, why: str) -> None:
        self._log.info("music.duck_skipped", reason=why)
