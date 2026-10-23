from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.live_transport import LiveTransport
from app.application.music_ducker import MusicDucker
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.use_cases.run_live_session import LiveLimits, RunLiveSession
from app.ports.live_session import LiveSession, LiveSessionPort
from tests.fakes.clock import FakeClock, wall
from tests.fakes.logger import RecordingLogger

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping, Sequence

    from app.application.live_transport import ClientFrame
    from app.application.registry import Registry
    from app.application.tool import Tool
    from app.domain.live import LiveEvent
    from app.domain.tools import ToolResult, ToolSpec


async def eventually(predicate: Callable[[], bool], within: float = 1.0) -> None:
    """Poll until `predicate()` is true; fail the test instead of hanging."""
    deadline = time.monotonic() + within
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.005)


class ScriptedLiveSession(LiveSession):
    """A provider session driven by the test: `push` events in, inspect what was sent."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[LiveEvent | None] = asyncio.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self.audio_in: list[bytes] = []
        self.tool_results: list[list[ToolResult]] = []
        self.response_requests = 0
        self.truncations: list[tuple[str, int]] = []
        self.closed = False

    def push(self, *events: LiveEvent) -> None:
        for event in events:
            self._put(event)

    def end(self) -> None:
        self._put(None)

    def _put(self, item: LiveEvent | None) -> None:
        # callable from another thread (the WebSocket test client runs the app in its own loop)
        if self._loop is None:
            self._queue.put_nowait(item)
        else:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, item)

    async def events(self) -> AsyncIterator[LiveEvent]:
        self._loop = asyncio.get_running_loop()
        while True:
            event = await self._queue.get()
            if event is None:
                return
            yield event

    async def send_audio(self, data: bytes) -> None:
        self.audio_in.append(data)

    async def send_tool_results(self, results: Sequence[ToolResult]) -> None:
        self.tool_results.append(list(results))

    async def request_response(self) -> None:
        self.response_requests += 1

    async def truncate(self, item_id: str, audio_end_ms: int) -> None:
        self.truncations.append((item_id, audio_end_ms))

    async def close(self) -> None:
        self.closed = True


class ScriptedLiveAdapter(LiveSessionPort):
    """Hands out `session` first, then a fresh scripted session for every later `open`
    (each WebSocket connection runs in its own event loop, so sessions cannot be shared)."""

    def __init__(self, session: ScriptedLiveSession, error: Exception | None = None) -> None:
        self.sessions = [session]
        self._opened = 0
        self._error = error
        self.opened_with: tuple[str, tuple[ToolSpec, ...]] | None = None

    async def open(self, instructions: str, tools: Sequence[ToolSpec]) -> LiveSession:
        if self._error is not None:
            raise self._error
        if self._opened == len(self.sessions):
            self.sessions.append(ScriptedLiveSession())
        session = self.sessions[self._opened]
        self._opened += 1
        self.opened_with = (instructions, tuple(tools))
        return session


class FakeTransport(LiveTransport):
    """The client: `feed` frames in, inspect the audio and events the server sent."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[ClientFrame | None] = asyncio.Queue()
        self.audio_out: list[bytes] = []
        self.events: list[Mapping[str, object]] = []

    def feed(self, frame: ClientFrame) -> None:
        self._queue.put_nowait(frame)

    def disconnect(self) -> None:
        self._queue.put_nowait(None)

    def sent(self, event_type: str) -> list[Mapping[str, object]]:
        return [e for e in self.events if e.get("type") == event_type]

    async def incoming(self) -> AsyncIterator[ClientFrame]:
        while True:
            frame = await self._queue.get()
            if frame is None:
                return
            yield frame

    async def send_audio(self, data: bytes) -> None:
        self.audio_out.append(data)

    async def send_event(self, event: Mapping[str, object]) -> None:
        self.events.append(event)


class LiveWorld:
    """Everything a live session needs, in memory, with a scripted provider and client."""

    def __init__(
        self,
        *,
        extra_tools: Sequence[Tool] = (),
        limits: LiveLimits | None = None,
        open_error: Exception | None = None,
        projects: Sequence[str] = (),
    ) -> None:
        self.light = InMemoryLight()
        self.calendar = InMemoryCalendar()
        self.store = InMemoryConversationStore()
        self.pending = PendingActionStore(FakeClock())
        self.log = RecordingLogger()
        self.music = InMemoryMusic()
        self.ducker = MusicDucker(self.music, self.log, 20)
        registry: Registry[Tool] = build_tool_registry(
            self.light,
            InMemoryClimate(),
            self.music,
            self.calendar,
            InMemoryExpenses(),
            on_volume=self.ducker.note_volume,
        )
        for tool in extra_tools:
            registry.register(tool.spec.name, tool)
        self.runner = ToolRunner(registry, self.pending, self.log)
        self.session = ScriptedLiveSession()
        self.adapter = ScriptedLiveAdapter(self.session, open_error)
        self.transport = FakeTransport()
        self.run = RunLiveSession(
            self.adapter,
            self.store,
            self.runner,
            self.pending,
            self.log,
            now=time.monotonic,
            clock=wall,
            limits=limits or LiveLimits(),
            ducker=self.ducker,
            projects=projects,
        )

    def start(self, segment: str | None = None) -> asyncio.Task[None]:
        return asyncio.create_task(self.run.execute(self.transport, "c1", segment))
