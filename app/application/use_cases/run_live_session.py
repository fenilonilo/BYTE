from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.application.prompts import SYSTEM_PROMPT, now_line
from app.application.tool_runner import CONFIRM_ACTION
from app.domain.entities import Message
from app.domain.exceptions import LiveSessionError
from app.domain.live import (
    AssistantAudio,
    AssistantTranscript,
    LiveError,
    ResponseDone,
    ResponseStarted,
    UserSpeechStarted,
    UserTranscript,
)
from app.domain.tools import ToolResult

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from app.application.live_transport import LiveTransport
    from app.application.music_ducker import MusicDucker
    from app.application.pending_actions import PendingActionStore
    from app.application.tool_runner import ToolRunner
    from app.domain.live import LiveEvent
    from app.domain.tools import ToolCall
    from app.ports.conversation_store import ConversationStorePort
    from app.ports.live_session import LiveSession, LiveSessionPort
    from app.ports.logger import LoggerPort

AUDIO_FORMAT: Mapping[str, object] = {"format": "pcm16", "rate": 24000, "channels": 1}
LIVE_INSTRUCTIONS = f"{SYSTEM_PROMPT} Você está numa conversa por voz: seja breve."


@dataclass(frozen=True, slots=True)
class LiveLimits:
    idle_seconds: float = 60.0
    max_seconds: float = 600.0
    transcript_wait_seconds: float = 2.0


class RunLiveSession:
    """A spoken conversation: client audio <-> provider session, tools run server-side."""

    def __init__(
        self,
        live: LiveSessionPort,
        store: ConversationStorePort,
        runner: ToolRunner,
        pending: PendingActionStore,
        log: LoggerPort,
        *,
        now: Callable[[], float],
        clock: Callable[[], datetime],
        limits: LiveLimits | None = None,
        ducker: MusicDucker | None = None,
    ) -> None:
        self._clock = clock
        self._ducker = ducker
        self._live = live
        self._store = store
        self._runner = runner
        self._pending = pending
        self._log = log
        self._now = now
        self._limits = limits or LiveLimits()

    async def execute(
        self, transport: LiveTransport, conversation_id: str, segment: str | None
    ) -> None:
        try:
            # sessions last minutes, so the time at the start is close enough
            instructions = f"{LIVE_INSTRUCTIONS} {now_line(self._clock())}"
            session = await self._live.open(instructions, self._runner.specs(segment))
        except LiveSessionError:
            await transport.send_event({"type": "error", "code": "model_unavailable"})
            raise
        run = LiveRun(
            session=session,
            transport=transport,
            conversation_id=conversation_id,
            segment=segment,
            store=self._store,
            runner=self._runner,
            pending=self._pending,
            log=self._log,
            limits=self._limits,
            now=self._now,
        )
        self._log.info("live.start", conversation_id=conversation_id)
        try:
            await transport.send_event(
                {"type": "ready", "conversation_id": conversation_id, "audio": AUDIO_FORMAT}
            )
            async with contextlib.AsyncExitStack() as stack:
                if self._ducker is not None:
                    await stack.enter_async_context(self._ducker.session())
                async with asyncio.timeout(self._limits.max_seconds):
                    await run.pump()
        except TimeoutError:
            await transport.send_event({"type": "error", "code": "session_limit"})
        finally:
            await run.close()
            self._log.info("live.end", conversation_id=conversation_id)


class LiveRun:
    """State and event handling of one open live session."""

    def __init__(
        self,
        *,
        session: LiveSession,
        transport: LiveTransport,
        conversation_id: str,
        segment: str | None,
        store: ConversationStorePort,
        runner: ToolRunner,
        pending: PendingActionStore,
        log: LoggerPort,
        limits: LiveLimits,
        now: Callable[[], float],
    ) -> None:
        self._session = session
        self._transport = transport
        self._cid = conversation_id
        self._segment = segment
        self._store = store
        self._runner = runner
        self._pending = pending
        self._log = log
        self._limits = limits
        self._now = now
        self._last_activity = now()
        self._item: str | None = None
        self._speaking = False
        self._response_active = False
        self._deferred = False
        self._echo_items: set[str] = set()
        self._transcript_ready = asyncio.Event()
        self._tool_lock = asyncio.Lock()
        self._tool_tasks: set[asyncio.Task[None]] = set()

    async def pump(self) -> None:
        tasks = {
            asyncio.create_task(self._from_client()),
            asyncio.create_task(self._from_provider()),
            asyncio.create_task(self._watch_idle()),
        }
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        for task in self._tool_tasks:
            task.cancel()
        await asyncio.gather(*self._tool_tasks, return_exceptions=True)
        await self._session.close()

    async def _from_client(self) -> None:
        async for frame in self._transport.incoming():
            if isinstance(frame, bytes):
                await self._session.send_audio(frame)
            elif frame.get("type") == "played":
                await self._truncate(frame.get("audio_end_ms"))

    async def _truncate(self, audio_end_ms: object) -> None:
        if (
            self._item is None
            or isinstance(audio_end_ms, bool)
            or not isinstance(audio_end_ms, int)
        ):
            return
        await self._session.truncate(self._item, audio_end_ms)

    async def _from_provider(self) -> None:
        async for event in self._session.events():
            await self._handle(event)

    async def _watch_idle(self) -> None:
        while True:
            remaining = self._last_activity + self._limits.idle_seconds - self._now()
            if remaining <= 0:
                break
            await asyncio.sleep(remaining)
        await self._transport.send_event({"type": "closed", "reason": "idle"})

    def _touch(self) -> None:
        self._last_activity = self._now()

    async def _handle(self, event: LiveEvent) -> None:
        match event:
            case AssistantAudio(data=data, item_id=item_id):
                self._touch()
                self._item = item_id
                self._speaking = True
                await self._transport.send_audio(data)
            case UserSpeechStarted(item_id=item_id):
                self._touch()
                if self._speaking:
                    # barge-in or echo; either way the client stops playing, but speech that
                    # started over the assistant's voice can never confirm an action
                    self._echo_items.add(item_id)
                    await self._transport.send_event({"type": "interrupt"})
                else:
                    self._transcript_ready.clear()
            case UserTranscript(item_id=item_id, text=text):
                self._touch()
                await self._transport.send_event(
                    {"type": "transcript", "role": "user", "text": text, "final": True}
                )
                await self._save("user", text)
                if item_id not in self._echo_items:
                    self._pending.on_user_utterance(self._cid, text)
                    self._transcript_ready.set()
            case AssistantTranscript(text=text):
                await self._transport.send_event(
                    {"type": "transcript", "role": "assistant", "text": text, "final": True}
                )
                await self._save("assistant", text)
            case ResponseStarted():
                self._response_active = True
            case ResponseDone(calls=calls):
                await self._finish_response(calls)
            case LiveError(code=code):
                await self._transport.send_event({"type": "error", "code": code})
                raise LiveSessionError(f"provider error: {code}")

    async def _finish_response(self, calls: tuple[ToolCall, ...]) -> None:
        self._response_active = False
        self._speaking = False
        if calls:
            self._deferred = False  # the tool batch will request the next response itself
            task = asyncio.create_task(self._run_tools(calls))
            self._tool_tasks.add(task)
            task.add_done_callback(self._tool_task_done)
            return
        await self._transport.send_event({"type": "turn_done"})
        if self._deferred:
            self._deferred = False
            await self._request_response()

    async def _run_tools(self, calls: tuple[ToolCall, ...]) -> None:
        async with self._tool_lock:
            results: list[ToolResult] = []
            for call in calls:
                if call.name == CONFIRM_ACTION and not await self._transcript_arrived():
                    results.append(ToolResult(call.id, "erro: não ouvi a confirmação do usuário"))
                    continue
                results.append(await self._runner.run(call, self._cid, self._segment))
            self._touch()
            await self._session.send_tool_results(results)
            await self._request_response()

    async def _transcript_arrived(self) -> bool:
        try:
            await asyncio.wait_for(
                self._transcript_ready.wait(), self._limits.transcript_wait_seconds
            )
        except TimeoutError:
            return False
        return True

    async def _request_response(self) -> None:
        if self._response_active:
            self._deferred = True
            return
        self._response_active = True
        await self._session.request_response()

    def _tool_task_done(self, task: asyncio.Task[None]) -> None:
        self._tool_tasks.discard(task)
        if not task.cancelled() and (exc := task.exception()) is not None:
            self._log.error("live.tools_failed", error=type(exc).__name__)

    async def _save(self, role: str, text: str) -> None:
        message = Message(id=str(uuid4()), role=role, content=text, timestamp=datetime.now(tz=UTC))
        await self._store.append(self._cid, (message,))
