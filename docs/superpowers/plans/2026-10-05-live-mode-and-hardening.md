# Byte: Live Mode and Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the live spoken mode (`WS /api/v1/live`, OpenAI Realtime) that runs the same tools, including your lights, air conditioner and music, with the same code-enforced confirmation, then harden the deployment: locked dependencies, non-root image, TLS for the ESP32, repo hygiene and documentation that matches the code.

**Architecture:** `RunLiveSession` relays opaque audio between a `LiveTransport` (the client) and a `LiveSessionPort` (the provider), executes tool calls through the Plan 1 `ToolRunner`, and treats speech that starts over the assistant's voice as echo that can never confirm anything. The OpenAI Realtime adapter maps provider events to domain events with pure, unit-tested functions; the WebSocket endpoint adds auth, the `start` handshake, pacing and single-session replacement.

**Tech Stack:** FastAPI WebSockets, `openai` SDK Realtime (`client.realtime.connect`), `websockets` (probe script), pip-tools, Docker/Compose, OpenSSL for the self-signed certificate.

**Spec:** `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md` (this is **Plan 2 of 2**). **Prerequisite:** Plan 1 is finished and green on the same branch (`feat/personal-agent`).

## Global Constraints

Everything in Plan 1's constraints still applies. Specific to the live mode (spec §3):

- Live endpoint `WS /api/v1/live`; the bearer token travels in the `Authorization` header of the upgrade request (never in the URL). Missing or wrong token -> close code **1008**.
- First client frame is JSON `{"type":"start","segment"?,"conversation_id"?}`; the server opens the provider first and sends `ready` (with `{"format":"pcm16","rate":24000,"channels":1}`) only afterwards.
- Audio: binary frames both ways, **PCM16 mono 24 kHz**. The server never resamples and **`application/` never decodes audio** (it is opaque `bytes`). Client frames above **64 KiB** close the socket with **1009**.
- Server events: `transcript {role, text, final}`, `interrupt`, `turn_done`, `error {code}`, `closed {reason}`. Client control frame: `{"type":"played","audio_end_ms":N}`.
- **One live session at a time**; a new connection replaces the old one, which is closed with code **4000**.
- Session limits: **60 s** without speech ends the session; **10 minutes** is the hard cap (`error {code: "session_limit"}`).
- Provider session settings are explicit: PCM 24 kHz in/out, input transcription on (`gpt-4o-mini-transcribe`, Portuguese), `far_field` noise reduction, `server_vad` by default (`BYTE_LIVE_VAD` switches to `semantic_vad`), `retention_ratio` 0.8, model `gpt-realtime-2.1-mini` (`BYTE_LIVE_MODEL`).
- Tool calls from one provider response run **sequentially**, all results are sent, then **exactly one** response is requested, **deferred** while another response is active.
- Speech that starts while the assistant is speaking can **never** confirm an action; `confirm_action` waits up to **2 s** for the transcript and is refused without it.
- LAN exposure is opt-in (`BYTE_PUBLISH_HOST`) and requires TLS (`BYTE_TLS_CERT`/`BYTE_TLS_KEY`). The image runs as a non-root user from locked dependencies that include your three device extras. Compose binds to `127.0.0.1` by default.
- Integration tests (real OpenAI, real lamp) never run in the default `pytest`.

## Review Focus

1. **Speech over the assistant's own voice (echo, TV)** never confirms an action, even when it says "sim". `test_speech_over_the_assistant_voice_cannot_confirm`.
2. **A Wi-Fi drop leaves a half-open socket** -> the owner reconnects and the new connection wins (old one gets `4000`), instead of being locked out. `test_a_new_connection_replaces_the_old_one_with_close_code_4000`.
3. **A misbehaving client** (invalid JSON, JSON that is not an object, unknown frame types, `played` with a string or boolean, a 70 KB audio frame) -> garbage is ignored and the session survives; the oversized frame closes with `1009`. `test_garbage_frames_are_ignored_and_the_session_survives`, `test_barge_in_interrupts_the_client_which_reports_what_it_played`, `test_an_oversized_audio_frame_closes_the_socket`.
4. **Several tool calls in one response, plus a barge-in while they run** -> every result is sent once, and only one new response is requested, after the active one finishes. `test_a_multi_call_response_sends_every_result_then_exactly_one_response_create`, `test_response_create_waits_while_another_response_is_active`.
5. **The provider is down at the start, or fails mid-conversation** -> the client receives an `error` event before the socket closes. `test_provider_unavailable_is_reported_before_closing`, `test_provider_errors_are_reported_to_the_client_and_raised`.

## How to run things

- `python` below means the interpreter that has the project's dependencies installed (in this repo's shell that is `C:/Users/fenil/anaconda3/python.exe`; elsewhere, the activated virtualenv). `ruff`, `pyright` and `pytest` are the same tools run as `python -m ruff`, `python -m pyright`, `python -m pytest`.
- One test file: `python -m pytest <path> -q --no-cov`. Full gate: `ruff check . && ruff format --check . && pyright && pytest`.
- Every task follows the same rhythm: write the tests, watch them fail, write the code, watch them pass, run the gate, commit. The code blocks are the verified end state of each file: copy them as they are.
- Commits use Conventional Commits (the pre-commit hook enforces it). Add the repository's usual `Co-Authored-By` trailer when an agent writes the commit.
- **Never stage the whole tree** (`git add -A` or `git add .` with no paths). Your working tree has notes that are not part of this work (`AR_Controle.md`, `Lampada_Controle.md`, `Spotfy_Controle.md`); every commit step stages explicit paths only (Task 8 uses `git add -A` restricted to a path list so the deletions are staged too).

## File structure

```
app/
  domain/        live.py                         (events)
  ports/         live_session.py                 (LiveSession, LiveSessionPort)
  application/   live_transport.py               (LiveTransport: the client side)
                 use_cases/run_live_session.py   (RunLiveSession, LiveRun, LiveLimits)
  adapters/      openai/live_session.py          (Realtime over WebSocket, pure map_event/build_session_config)
  api/           live.py  live_slot.py  live_transport.py     (+ deps.py, schemas.py, config.py extended)
scripts/         live_probe.py                   (next to your spotify_login.py)
tests/fakes/     live.py                         (ScriptedLiveSession, FakeTransport, LiveWorld)
Dockerfile  docker-compose.yml  requirements.lock  .env.example  .pre-commit-config.yaml  .dockerignore
docs/ARCHITECTURE.md  docs/CONVENTIONS.md  README.md  CLAUDE.md
```

---

### Task 1: Live domain events and the live ports

**Files:**
- Create: `app/domain/live.py`, `app/ports/live_session.py`, `app/application/live_transport.py`

**Interfaces:**
- Consumes: `ToolCall`, `ToolResult`, `ToolSpec` from Plan 1.
- Produces: events `AssistantAudio(data, item_id)`, `UserSpeechStarted(item_id)`, `UserTranscript(item_id, text)`, `AssistantTranscript(text)`, `ResponseStarted()`, `ResponseDone(calls=())`, `LiveError(code)` and the union `LiveEvent`; `LiveSession` (ABC: `send_audio`, `events`, `send_tool_results`, `request_response`, `truncate`, `close`) and `LiveSessionPort.open(instructions, tools) -> LiveSession`; `LiveTransport` (ABC: `incoming`, `send_audio`, `send_event`) and `ClientFrame`.

No tests in this task: these are declarations (frozen dataclasses and ABCs) that Task 2 exercises through the fakes. Audio is opaque `bytes` everywhere: `application/` relays it, never decodes it. `LiveTransport` is the client side seen from the use case (a WebSocket in production, a fake in tests); `LiveSession` is the provider side. `send_tool_results` and `request_response` are separate on purpose, so the use case can defer the response while another one is still active.

- [ ] **Step 1: Create `app/domain/live.py`**

Create `app/domain/live.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.tools import ToolCall


@dataclass(frozen=True, slots=True)
class AssistantAudio:
    data: bytes
    item_id: str


@dataclass(frozen=True, slots=True)
class UserSpeechStarted:
    item_id: str


@dataclass(frozen=True, slots=True)
class UserTranscript:
    item_id: str
    text: str


@dataclass(frozen=True, slots=True)
class AssistantTranscript:
    text: str


@dataclass(frozen=True, slots=True)
class ResponseStarted:
    """The provider began a response (also the one it starts by itself after a barge-in)."""


@dataclass(frozen=True, slots=True)
class ResponseDone:
    """The response ended. `calls` holds the tool calls it asked for, if any."""

    calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class LiveError:
    code: str


type LiveEvent = (
    AssistantAudio
    | UserSpeechStarted
    | UserTranscript
    | AssistantTranscript
    | ResponseStarted
    | ResponseDone
    | LiveError
)
```

- [ ] **Step 2: Create `app/ports/live_session.py`**

Create `app/ports/live_session.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from app.domain.live import LiveEvent
    from app.domain.tools import ToolResult, ToolSpec


class LiveSession(ABC):
    """One open speech-to-speech conversation with a provider. Audio is opaque bytes."""

    @abstractmethod
    async def send_audio(self, data: bytes) -> None: ...

    @abstractmethod
    def events(self) -> AsyncIterator[LiveEvent]: ...

    @abstractmethod
    async def send_tool_results(self, results: Sequence[ToolResult]) -> None:
        """Hand every output back to the model. Does not start a new response."""

    @abstractmethod
    async def request_response(self) -> None:
        """Ask the model to answer now (after tool results were sent)."""

    @abstractmethod
    async def truncate(self, item_id: str, audio_end_ms: int) -> None:
        """Tell the model how much of an assistant audio item the user actually heard."""

    @abstractmethod
    async def close(self) -> None: ...


class LiveSessionPort(ABC):
    @abstractmethod
    async def open(self, instructions: str, tools: Sequence[ToolSpec]) -> LiveSession:
        """Returns once the provider session is configured. Raises LiveSessionError."""
```

- [ ] **Step 3: Create `app/application/live_transport.py`**

Create `app/application/live_transport.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

type ClientFrame = bytes | Mapping[str, object]


class LiveTransport(ABC):
    """The client side of a live session (a WebSocket in production, a fake in tests).

    Audio is opaque `bytes`; control messages are plain mappings."""

    @abstractmethod
    def incoming(self) -> AsyncIterator[ClientFrame]:
        """Frames from the client. The iterator ends when the client goes away."""

    @abstractmethod
    async def send_audio(self, data: bytes) -> None: ...

    @abstractmethod
    async def send_event(self, event: Mapping[str, object]) -> None: ...
```

- [ ] **Step 4: Commit**

```bash
git add app/domain/live.py \
  app/ports/live_session.py \
  app/application/live_transport.py
git commit -m "feat(domain): add live events and the live session and transport ports"
```

### Task 2: `RunLiveSession`: relay, tool calls, barge-in and the confirmation gate for speech

**Files:**
- Create: `app/application/use_cases/run_live_session.py`
- Create: `tests/fakes/live.py`
- Test: `tests/unit/application/use_cases/test_run_live_session.py`

**Interfaces:**
- Consumes: Task 1 ports and events; Plan 1 `ToolRunner`, `PendingActionStore`, `ConversationStorePort`, `SYSTEM_PROMPT`, `CONFIRM_ACTION`.
- Produces: `LiveLimits(idle_seconds=60.0, max_seconds=600.0, transcript_wait_seconds=2.0)`, `RunLiveSession(live, store, runner, pending, log, *, now, limits=None).execute(transport, conversation_id, segment)`, `AUDIO_FORMAT`, `LIVE_INSTRUCTIONS`; test helpers `ScriptedLiveSession` (`push`, `end`, recorded `audio_in`, `tool_results`, `response_requests`, `truncations`, `closed`), `ScriptedLiveAdapter`, `FakeTransport`, `LiveWorld`, `eventually(predicate, within=1.0)`.

The rules this task implements (spec §2 and §3):

- A response that asks for several tools runs them **one at a time**, sends **all** results, then asks for **exactly one** new response, **deferred** while another response is active (a barge-in can start one).
- `confirm_action` waits up to 2 s for the transcript of the user's speech; without it the action is refused.
- Speech that **starts while the assistant is talking** is flagged: the client gets `interrupt`, and that speech can never arm a pending action (echo, TV).
- `played` frames from the client become `truncate(item_id, audio_end_ms)` (bad numbers are ignored).
- Idle (60 s without speech) and the 10-minute cap end the session; a provider error is reported to the client and raised; cancellation still closes the provider.

The tests drive the use case with a scripted provider and client; they use short real timeouts (tens of milliseconds) and `eventually(...)` instead of fixed sleeps.

- [ ] **Step 1: Create `tests/fakes/live.py`**

Create `tests/fakes/live.py`:

```python
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
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.use_cases.run_live_session import LiveLimits, RunLiveSession
from app.ports.live_session import LiveSession, LiveSessionPort
from tests.fakes.clock import FakeClock
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
    ) -> None:
        self.light = InMemoryLight()
        self.calendar = InMemoryCalendar()
        self.store = InMemoryConversationStore()
        self.pending = PendingActionStore(FakeClock())
        self.log = RecordingLogger()
        registry: Registry[Tool] = build_tool_registry(
            self.light, InMemoryClimate(), InMemoryMusic(), self.calendar, InMemoryExpenses()
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
            limits=limits or LiveLimits(),
        )

    def start(self, segment: str | None = None) -> asyncio.Task[None]:
        return asyncio.create_task(self.run.execute(self.transport, "c1", segment))
```

- [ ] **Step 2: Create `tests/unit/application/use_cases/test_run_live_session.py`**

Create `tests/unit/application/use_cases/test_run_live_session.py`:

```python
from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import pytest

from app.application.tool import Tool
from app.application.tools.args import object_schema
from app.application.use_cases.run_live_session import LiveLimits
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
from app.domain.tools import ToolCall, ToolSpec
from tests.fakes.events import events_on_day, seed_event
from tests.fakes.live import LiveWorld, eventually

if TYPE_CHECKING:
    from collections.abc import Mapping


class GateTool(Tool):
    """Blocks until the test opens the gate."""

    def __init__(self) -> None:
        self.spec = ToolSpec("gate", "d", object_schema({}), "home")
        self.gate = asyncio.Event()
        self.started = False

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        self.started = True
        await self.gate.wait()
        return "aberto"


class BrokenTool(Tool):
    def __init__(self) -> None:
        self.spec = ToolSpec("broken", "d", object_schema({}), "home")

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        raise RuntimeError("detalhe interno")


def call(name: str, arguments: str = "{}", call_id: str = "call-1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def user_says(world: LiveWorld, text: str, item: str = "u1") -> None:
    world.session.push(UserSpeechStarted(item), UserTranscript(item, text))


async def finish(world: LiveWorld, task: asyncio.Task[None]) -> None:
    world.transport.disconnect()
    await asyncio.wait_for(task, timeout=1)


async def start_and_wait_ready(world: LiveWorld, segment: str | None = None) -> asyncio.Task[None]:
    task = world.start(segment)
    await eventually(lambda: bool(world.transport.sent("ready")))
    return task


async def ask_to_delete_the_event(world: LiveWorld) -> None:
    """The user asks; the model calls the sensitive tool; the pending action is created."""
    await seed_event(world.calendar)
    user_says(world, "apaga o dentista")
    world.session.push(
        ResponseStarted(),
        ResponseDone(calls=(call("delete_event", '{"event_id": "evt-1"}'),)),
    )
    await eventually(lambda: len(world.session.tool_results) == 1)
    assert "needs_confirmation" in world.session.tool_results[0][0].output
    world.session.push(
        ResponseStarted(), AssistantTranscript("Apagar o evento evt-1?"), ResponseDone()
    )
    await eventually(lambda: bool(world.transport.sent("turn_done")))


@pytest.mark.unit
async def test_opens_the_provider_with_instructions_and_the_segment_tools_then_says_ready() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world, "home")

    assert world.adapter.opened_with is not None
    instructions, tools = world.adapter.opened_with
    assert "Byte" in instructions
    assert {t.segment for t in tools} == {"home", "*"}
    ready = world.transport.sent("ready")[0]
    assert ready["conversation_id"] == "c1"
    assert ready["audio"] == {"format": "pcm16", "rate": 24000, "channels": 1}
    await finish(world, task)
    assert world.session.closed is True


@pytest.mark.unit
async def test_audio_is_relayed_in_both_directions_untouched() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    world.transport.feed(b"\x01\x02\x03")
    world.session.push(AssistantAudio(data=b"\x09\x08", item_id="a1"))
    await eventually(lambda: world.session.audio_in == [b"\x01\x02\x03"])
    await eventually(lambda: world.transport.audio_out == [b"\x09\x08"])
    await finish(world, task)


@pytest.mark.unit
async def test_transcripts_are_forwarded_and_saved_under_the_conversation() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    user_says(world, "oi")
    world.session.push(AssistantTranscript("olá"), ResponseDone())
    await eventually(lambda: bool(world.transport.sent("turn_done")))

    roles = [(e["role"], e["text"]) for e in world.transport.sent("transcript")]
    assert roles == [("user", "oi"), ("assistant", "olá")]
    stored = await world.store.recent("c1", 20)
    assert [(m.role, m.content) for m in stored] == [("user", "oi"), ("assistant", "olá")]
    await finish(world, task)


@pytest.mark.unit
async def test_a_multi_call_response_sends_every_result_then_exactly_one_response_create() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    world.session.push(
        ResponseStarted(),
        ResponseDone(calls=(call("list_lights", call_id="a"), call("list_lights", call_id="b"))),
    )
    await eventually(lambda: len(world.session.tool_results) == 1)

    assert [r.call_id for r in world.session.tool_results[0]] == ["a", "b"]
    assert world.session.response_requests == 1
    await finish(world, task)


@pytest.mark.unit
async def test_response_create_waits_while_another_response_is_active() -> None:
    gate = GateTool()
    world = LiveWorld(extra_tools=[gate])
    task = await start_and_wait_ready(world)

    world.session.push(ResponseDone(calls=(call("gate"),)))
    await eventually(lambda: gate.started)
    world.session.push(ResponseStarted())  # the user barged in and the provider answered on its own
    await asyncio.sleep(0.05)
    gate.gate.set()
    await eventually(lambda: len(world.session.tool_results) == 1)

    assert world.session.response_requests == 0
    world.session.push(ResponseDone())
    await eventually(lambda: world.session.response_requests == 1)
    await finish(world, task)


@pytest.mark.unit
async def test_confirmation_waits_for_the_transcript_then_runs_the_tool() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)
    await ask_to_delete_the_event(world)

    world.session.push(
        UserSpeechStarted("u2"),
        ResponseStarted(),
        ResponseDone(calls=(call("confirm_action", call_id="c2"),)),
    )
    await asyncio.sleep(0.05)
    assert len(await events_on_day(world.calendar)) == 1  # still waiting for the transcript

    world.session.push(UserTranscript("u2", "sim"))
    await eventually(lambda: len(world.session.tool_results) == 2)

    assert world.session.tool_results[1][0].output == "Evento evt-1 apagado"
    assert await events_on_day(world.calendar) == ()
    await finish(world, task)


@pytest.mark.unit
async def test_speech_over_the_assistant_voice_cannot_confirm() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)
    await ask_to_delete_the_event(world)

    world.session.push(
        ResponseStarted(),
        AssistantAudio(data=b"\x01", item_id="a1"),
        UserSpeechStarted("echo"),
        UserTranscript("echo", "sim"),
        ResponseDone(calls=(call("confirm_action", call_id="c2"),)),
    )
    await eventually(lambda: len(world.session.tool_results) == 2)

    assert world.transport.sent("interrupt")
    assert world.session.tool_results[1][0].output.startswith("erro: aguarde")
    assert len(await events_on_day(world.calendar)) == 1
    await finish(world, task)


@pytest.mark.unit
async def test_confirm_without_any_transcript_is_refused_after_the_wait() -> None:
    world = LiveWorld(limits=LiveLimits(transcript_wait_seconds=0.03))
    task = await start_and_wait_ready(world)

    world.session.push(ResponseDone(calls=(call("confirm_action"),)))
    await eventually(lambda: len(world.session.tool_results) == 1)

    assert world.session.tool_results[0][0].output == "erro: não ouvi a confirmação do usuário"
    await finish(world, task)


@pytest.mark.unit
async def test_barge_in_interrupts_the_client_and_truncates_what_was_heard() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    world.session.push(AssistantAudio(data=b"\x01", item_id="a1"), UserSpeechStarted("u1"))
    await eventually(lambda: bool(world.transport.sent("interrupt")))
    world.transport.feed({"type": "played", "audio_end_ms": 1234})
    world.transport.feed({"type": "played", "audio_end_ms": "soon"})
    world.transport.feed({"type": "played", "audio_end_ms": True})
    world.transport.feed({"type": "hello"})
    await eventually(lambda: world.session.truncations == [("a1", 1234)])
    await finish(world, task)
    assert world.session.truncations == [("a1", 1234)]


@pytest.mark.unit
async def test_a_failing_tool_does_not_end_the_session() -> None:
    world = LiveWorld(extra_tools=[BrokenTool()])
    task = await start_and_wait_ready(world)

    world.session.push(ResponseDone(calls=(call("broken"),)))
    await eventually(lambda: len(world.session.tool_results) == 1)

    assert world.session.tool_results[0][0].output == "erro: falha interna na ferramenta"
    assert world.session.response_requests == 1
    assert not task.done()
    await finish(world, task)


@pytest.mark.unit
async def test_provider_errors_are_reported_to_the_client_and_raised() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)

    world.session.push(LiveError("rate_limit"))
    with pytest.raises(LiveSessionError, match="rate_limit"):
        await asyncio.wait_for(task, timeout=1)

    assert world.transport.sent("error")[0]["code"] == "rate_limit"
    assert world.session.closed is True


@pytest.mark.unit
async def test_open_failure_tells_the_client_and_never_says_ready() -> None:
    world = LiveWorld(open_error=LiveSessionError("provider down"))
    with pytest.raises(LiveSessionError, match="provider down"):
        await world.start()
    assert world.transport.events == [{"type": "error", "code": "model_unavailable"}]


@pytest.mark.unit
async def test_idle_sessions_are_closed() -> None:
    world = LiveWorld(limits=LiveLimits(idle_seconds=0.05))
    task = world.start()
    await asyncio.wait_for(task, timeout=1)

    assert world.transport.sent("closed")[0]["reason"] == "idle"
    assert world.session.closed is True


@pytest.mark.unit
async def test_the_hard_cap_ends_the_session_with_an_error_event() -> None:
    world = LiveWorld(limits=LiveLimits(max_seconds=0.05))
    task = world.start()
    await asyncio.wait_for(task, timeout=1)

    assert world.transport.sent("error")[0]["code"] == "session_limit"
    assert world.session.closed is True


@pytest.mark.unit
async def test_the_session_ends_when_the_provider_ends() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)
    world.session.end()
    await asyncio.wait_for(task, timeout=1)
    assert world.session.closed is True


@pytest.mark.unit
async def test_cancelling_the_session_still_closes_the_provider() -> None:
    world = LiveWorld()
    task = await start_and_wait_ready(world)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    assert world.session.closed is True
```

- [ ] **Step 3: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/application/use_cases/test_run_live_session.py -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 4: Create `app/application/use_cases/run_live_session.py`**

Create `app/application/use_cases/run_live_session.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.application.prompts import SYSTEM_PROMPT
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
        limits: LiveLimits | None = None,
    ) -> None:
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
            session = await self._live.open(LIVE_INSTRUCTIONS, self._runner.specs(segment))
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
```

- [ ] **Step 5: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/application/use_cases/test_run_live_session.py -q --no-cov
```

Expected: PASS (16 tests). Run it five times in a row; it must pass every time (`for i in 1 2 3 4 5; do python -m pytest tests/unit/application/use_cases/test_run_live_session.py -q --no-cov; done`).

- [ ] **Step 6: Commit**

```bash
git add app/application/use_cases/run_live_session.py \
  tests/fakes/live.py \
  tests/unit/application/use_cases/test_run_live_session.py
git commit -m "feat(application): add RunLiveSession with tool calls, barge-in and speech confirmation"
```

### Task 3: OpenAI Realtime adapter

**Files:**
- Create: `app/adapters/openai/live_session.py`
- Test: `tests/unit/adapters/test_openai_live_mapping.py`, `tests/integration/test_openai_live.py`

**Interfaces:**
- Consumes: `LiveSession`, `LiveSessionPort`, the live events, `LiveSessionError`; the SDK's `client.realtime.connect`.
- Produces: `OpenAILiveSessionAdapter(client, model, *, vad='server_vad', transcribe_model='gpt-4o-mini-transcribe', retention_ratio=0.8)`, `OpenAILiveSession`, and the pure functions `build_session_config(...)` and `map_event(event) -> LiveEvent | None`.

Everything the provider docs leave ambiguous is set explicitly in `build_session_config`: PCM 24 kHz in and out, input transcription on, `far_field` noise reduction, the VAD mode, context truncation. `open()` returns only after `session.updated`, so the server can send `ready` knowing the provider is configured. `map_event` is pure and is tested with the SDK's own event models, so a renamed provider event breaks a unit test instead of production.

The integration test opens a real session and asks it to speak; it skips itself without `BYTE_OPENAI_API_KEY` and is excluded from the default run.

- [ ] **Step 1: Create `tests/unit/adapters/test_openai_live_mapping.py`**

Create `tests/unit/adapters/test_openai_live_mapping.py`:

```python
from __future__ import annotations

import base64
from typing import TYPE_CHECKING

import pytest
from openai.types.realtime import (
    ConversationItemInputAudioTranscriptionCompletedEvent,
    InputAudioBufferSpeechStartedEvent,
    RealtimeErrorEvent,
    ResponseAudioDeltaEvent,
    ResponseAudioTranscriptDoneEvent,
    ResponseCreatedEvent,
    ResponseDoneEvent,
    SessionUpdatedEvent,
)

from app.adapters.openai.live_session import build_session_config, map_event
from app.domain.live import (
    AssistantAudio,
    AssistantTranscript,
    LiveError,
    ResponseDone,
    ResponseStarted,
    UserSpeechStarted,
    UserTranscript,
)
from app.domain.tools import ToolCall, ToolSpec

if TYPE_CHECKING:
    from openai.types.realtime import RealtimeServerEvent


def parse(model: type, payload: dict[str, object]) -> RealtimeServerEvent:
    return model.model_validate(payload)  # type: ignore[attr-defined, no-any-return]


@pytest.mark.unit
def test_audio_delta_is_decoded_to_raw_bytes() -> None:
    event = parse(
        ResponseAudioDeltaEvent,
        {
            "type": "response.output_audio.delta",
            "event_id": "e1",
            "response_id": "r1",
            "item_id": "item-1",
            "output_index": 0,
            "content_index": 0,
            "delta": base64.b64encode(b"\x01\x02").decode(),
        },
    )
    assert map_event(event) == AssistantAudio(data=b"\x01\x02", item_id="item-1")


@pytest.mark.unit
def test_speech_started_and_transcripts() -> None:
    started = parse(
        InputAudioBufferSpeechStartedEvent,
        {
            "type": "input_audio_buffer.speech_started",
            "event_id": "e1",
            "item_id": "u1",
            "audio_start_ms": 10,
        },
    )
    transcript = parse(
        ConversationItemInputAudioTranscriptionCompletedEvent,
        {
            "type": "conversation.item.input_audio_transcription.completed",
            "event_id": "e2",
            "item_id": "u1",
            "content_index": 0,
            "transcript": "sim",
            "usage": {"type": "duration", "seconds": 1.0},
        },
    )
    spoken = parse(
        ResponseAudioTranscriptDoneEvent,
        {
            "type": "response.output_audio_transcript.done",
            "event_id": "e3",
            "response_id": "r1",
            "item_id": "a1",
            "output_index": 0,
            "content_index": 0,
            "transcript": "Pronto.",
        },
    )
    assert map_event(started) == UserSpeechStarted(item_id="u1")
    assert map_event(transcript) == UserTranscript(item_id="u1", text="sim")
    assert map_event(spoken) == AssistantTranscript(text="Pronto.")


@pytest.mark.unit
def test_response_created_and_done_with_function_calls() -> None:
    created = parse(
        ResponseCreatedEvent,
        {"type": "response.created", "event_id": "e1", "response": {"id": "r1"}},
    )
    done = parse(
        ResponseDoneEvent,
        {
            "type": "response.done",
            "event_id": "e2",
            "response": {
                "id": "r1",
                "output": [
                    {"type": "message", "role": "assistant", "content": []},
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "list_lights",
                        "arguments": "",
                    },
                    {
                        "type": "function_call",
                        "call_id": "call-2",
                        "name": "set_light",
                        "arguments": '{"name": "lampada", "power": true}',
                    },
                ],
            },
        },
    )
    assert map_event(created) == ResponseStarted()
    assert map_event(done) == ResponseDone(
        calls=(
            ToolCall(id="call-1", name="list_lights", arguments="{}"),
            ToolCall(id="call-2", name="set_light", arguments='{"name": "lampada", "power": true}'),
        )
    )


@pytest.mark.unit
def test_response_done_without_output_has_no_calls() -> None:
    done = parse(ResponseDoneEvent, {"type": "response.done", "event_id": "e", "response": {}})
    assert map_event(done) == ResponseDone(calls=())


@pytest.mark.unit
def test_errors_keep_the_code_and_unrelated_events_are_dropped() -> None:
    error = parse(
        RealtimeErrorEvent,
        {
            "type": "error",
            "event_id": "e1",
            "error": {
                "type": "invalid_request_error",
                "code": "rate_limit_exceeded",
                "message": "x",
            },
        },
    )
    no_code = parse(
        RealtimeErrorEvent,
        {"type": "error", "event_id": "e2", "error": {"type": "server_error", "message": "x"}},
    )
    updated = parse(
        SessionUpdatedEvent,
        {"type": "session.updated", "event_id": "e3", "session": {"type": "realtime"}},
    )
    assert map_event(error) == LiveError(code="rate_limit_exceeded")
    assert map_event(no_code) == LiveError(code="server_error")
    assert map_event(updated) is None


@pytest.mark.unit
def test_session_config_sets_everything_explicitly() -> None:
    spec = ToolSpec(
        name="set_light",
        description="Liga.",
        parameters={"type": "object", "properties": {}},
        segment="home",
    )
    config = build_session_config(
        "seja breve",
        [spec],
        vad="semantic_vad",
        transcribe_model="gpt-4o-mini-transcribe",
        retention_ratio=0.8,
    )
    pcm = {"type": "audio/pcm", "rate": 24000}
    expected: dict[str, object] = {
        "type": "realtime",
        "instructions": "seja breve",
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": pcm,
                "noise_reduction": {"type": "far_field"},
                "transcription": {"model": "gpt-4o-mini-transcribe", "language": "pt"},
                "turn_detection": {"type": "semantic_vad"},
            },
            "output": {"format": pcm, "voice": "marin"},
        },
        "tools": [
            {
                "type": "function",
                "name": "set_light",
                "description": "Liga.",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "tool_choice": "auto",
        "truncation": {"type": "retention_ratio", "retention_ratio": 0.8},
    }
    assert dict(config) == expected
```

- [ ] **Step 2: Create `tests/integration/test_openai_live.py`**

Create `tests/integration/test_openai_live.py`:

```python
from __future__ import annotations

import asyncio
import os

import pytest
from openai import AsyncOpenAI

from app.adapters.openai.live_session import OpenAILiveSessionAdapter
from app.domain.live import AssistantAudio, LiveError, ResponseDone

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("BYTE_OPENAI_API_KEY"), reason="needs BYTE_OPENAI_API_KEY"
    ),
]

MODEL = os.environ.get("BYTE_LIVE_MODEL", "gpt-realtime-2.1-mini")


async def test_the_provider_session_speaks_when_asked() -> None:
    client = AsyncOpenAI(api_key=os.environ["BYTE_OPENAI_API_KEY"])
    session = await OpenAILiveSessionAdapter(client, MODEL).open("Diga apenas: olá.", [])
    audio_bytes = 0
    try:
        await session.request_response()
        async with asyncio.timeout(30):
            async for event in session.events():
                assert not isinstance(event, LiveError), event
                if isinstance(event, AssistantAudio):
                    audio_bytes += len(event.data)
                if isinstance(event, ResponseDone):
                    break
    finally:
        await session.close()
    assert audio_bytes > 0
```

- [ ] **Step 3: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/adapters/test_openai_live_mapping.py -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 4: Create `app/adapters/openai/live_session.py`**

Create `app/adapters/openai/live_session.py`:

```python
from __future__ import annotations

import asyncio
import base64
from contextlib import AsyncExitStack, contextmanager
from typing import TYPE_CHECKING, Literal

from openai import OpenAIError
from websockets.exceptions import WebSocketException

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
from app.domain.tools import ToolCall
from app.ports.live_session import LiveSession, LiveSessionPort

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Generator, Sequence

    from openai import AsyncOpenAI
    from openai.resources.realtime.realtime import AsyncRealtimeConnection
    from openai.types.realtime import RealtimeServerEvent, RealtimeSessionCreateRequestParam
    from openai.types.realtime.realtime_audio_formats_param import AudioPCM
    from openai.types.realtime.realtime_audio_input_turn_detection_param import (
        SemanticVad,
        ServerVad,
    )

    from app.domain.live import LiveEvent
    from app.domain.tools import ToolResult, ToolSpec

type Vad = Literal["server_vad", "semantic_vad"]

HANDSHAKE_TIMEOUT_SECONDS = 10.0
PCM_24K: AudioPCM = {"type": "audio/pcm", "rate": 24000}
_PROVIDER_ERRORS = (OpenAIError, WebSocketException, OSError)


@contextmanager
def _provider_errors() -> Generator[None]:
    try:
        yield
    except _PROVIDER_ERRORS as exc:
        raise LiveSessionError(f"provider failure: {type(exc).__name__}") from exc


def build_session_config(
    instructions: str,
    tools: Sequence[ToolSpec],
    *,
    vad: Vad,
    transcribe_model: str,
    retention_ratio: float,
) -> RealtimeSessionCreateRequestParam:
    """Everything the docs leave ambiguous is set explicitly: VAD, transcription, audio rate."""
    turn_detection: ServerVad | SemanticVad = (
        {"type": "server_vad"} if vad == "server_vad" else {"type": "semantic_vad"}
    )
    return {
        "type": "realtime",
        "instructions": instructions,
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": PCM_24K,
                "noise_reduction": {"type": "far_field"},
                "transcription": {"model": transcribe_model, "language": "pt"},
                "turn_detection": turn_detection,
            },
            "output": {"format": PCM_24K, "voice": "marin"},
        },
        "tools": [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": dict(t.parameters),
            }
            for t in tools
        ],
        "tool_choice": "auto",
        "truncation": {"type": "retention_ratio", "retention_ratio": retention_ratio},
    }


def map_event(event: RealtimeServerEvent) -> LiveEvent | None:  # noqa: PLR0911 - one branch per event
    """Provider event -> domain event; everything Byte does not care about maps to None."""
    if event.type == "response.output_audio.delta":
        return AssistantAudio(data=base64.b64decode(event.delta), item_id=event.item_id)
    if event.type == "input_audio_buffer.speech_started":
        return UserSpeechStarted(item_id=event.item_id)
    if event.type == "conversation.item.input_audio_transcription.completed":
        return UserTranscript(item_id=event.item_id, text=event.transcript)
    if event.type == "response.output_audio_transcript.done":
        return AssistantTranscript(text=event.transcript)
    if event.type == "response.created":
        return ResponseStarted()
    if event.type == "response.done":
        calls = tuple(
            ToolCall(id=item.call_id, name=item.name, arguments=item.arguments or "{}")
            for item in event.response.output or ()
            if item.type == "function_call" and item.call_id
        )
        return ResponseDone(calls=calls)
    if event.type == "error":
        return LiveError(code=event.error.code or event.error.type)
    return None


class OpenAILiveSession(LiveSession):
    def __init__(self, connection: AsyncRealtimeConnection, stack: AsyncExitStack) -> None:
        self._conn = connection
        self._stack = stack

    async def send_audio(self, data: bytes) -> None:
        with _provider_errors():
            await self._conn.input_audio_buffer.append(audio=base64.b64encode(data).decode("ascii"))

    async def events(self) -> AsyncIterator[LiveEvent]:
        with _provider_errors():
            async for raw in self._conn:
                if (event := map_event(raw)) is not None:
                    yield event

    async def send_tool_results(self, results: Sequence[ToolResult]) -> None:
        with _provider_errors():
            for result in results:
                await self._conn.conversation.item.create(
                    item={
                        "type": "function_call_output",
                        "call_id": result.call_id,
                        "output": result.output,
                    }
                )

    async def request_response(self) -> None:
        with _provider_errors():
            await self._conn.response.create()

    async def truncate(self, item_id: str, audio_end_ms: int) -> None:
        with _provider_errors():
            await self._conn.conversation.item.truncate(
                item_id=item_id, content_index=0, audio_end_ms=audio_end_ms
            )

    async def close(self) -> None:
        with _provider_errors():
            await self._stack.aclose()


class OpenAILiveSessionAdapter(LiveSessionPort):
    """OpenAI Realtime over WebSocket. The OpenAI SDK never leaves this package."""

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        *,
        vad: Vad = "server_vad",
        transcribe_model: str = "gpt-4o-mini-transcribe",
        retention_ratio: float = 0.8,
    ) -> None:
        self._client = client
        self._model = model
        self._vad: Vad = vad
        self._transcribe_model = transcribe_model
        self._retention_ratio = retention_ratio

    async def open(self, instructions: str, tools: Sequence[ToolSpec]) -> LiveSession:
        config = build_session_config(
            instructions,
            tools,
            vad=self._vad,
            transcribe_model=self._transcribe_model,
            retention_ratio=self._retention_ratio,
        )
        stack = AsyncExitStack()
        try:
            with _provider_errors():
                connection = await stack.enter_async_context(
                    self._client.realtime.connect(model=self._model)
                )
                await connection.session.update(session=config)
                async with asyncio.timeout(HANDSHAKE_TIMEOUT_SECONDS):
                    await self._wait_until_configured(connection)
        except BaseException:
            await stack.aclose()
            raise
        return OpenAILiveSession(connection, stack)

    @staticmethod
    async def _wait_until_configured(connection: AsyncRealtimeConnection) -> None:
        async for event in connection:
            if event.type == "session.updated":
                return
            if event.type == "error":
                raise LiveSessionError(f"provider rejected the session: {event.error.type}")
        raise LiveSessionError("provider closed before the session was configured")
```

- [ ] **Step 5: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/adapters/test_openai_live_mapping.py -q --no-cov
```

Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add app/adapters/openai/live_session.py \
  tests/unit/adapters/test_openai_live_mapping.py \
  tests/integration/test_openai_live.py
git commit -m "feat(adapters): add OpenAI Realtime adapter behind LiveSessionPort"
```

### Task 4: `WS /api/v1/live`: auth, handshake, pacing, one session at a time

**Files:**
- Create: `app/api/live_slot.py`, `app/api/live_transport.py`, `app/api/live.py`
- Replace: `app/api/deps.py`, `app/api/schemas.py`, `main.py`, `tests/conftest.py`
- Modify: `app/config.py` (live settings)
- Test: `tests/unit/api/test_live.py`

**Interfaces:**
- Consumes: Tasks 1-3; Plan 1 `token_matches`, `Settings`, `ToolRunner.segments()`, the `deps` singletons.
- Produces: `LiveSlot.claim/release` (close code 4000 for the replaced connection), `WebSocketTransport(websocket, *, pace_factor, max_frame_bytes)` with `aclose()`, `LiveStartSchema`, `deps.get_openai / get_live_port / get_live_slot / get_run_live_session`, the `/live` WebSocket route, and the `live_*` settings (`BYTE_LIVE_MODEL`, `BYTE_LIVE_VAD`, ...).

How the endpoint behaves (spec §3): the bearer token is checked on the upgrade (close 1008 otherwise); the first frame must be a valid `start` and a known `segment` (`error` event then close 1008); only then does a new connection **replace** the previous one (close code 4000); the server opens the provider first and sends `ready` only afterwards; audio frames are capped at 64 KiB (close 1009); outgoing audio is paced at roughly real time and an `interrupt` event flushes whatever audio is still queued. The slot is released **last**, after the socket and the outbox are cleaned up.

Note for the tests: Starlette's `TestClient` cancels the app right after the client disconnects, so the tests wait for the server to finish cleaning up (`TrackingSlot.releases`) before leaving the `with` block.

- [ ] **Step 1: Create `tests/conftest.py`**

Create `tests/conftest.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.api import deps

if TYPE_CHECKING:
    from collections.abc import Iterator

_CACHED = (
    deps.get_settings,
    deps.get_logger,
    deps.get_store,
    deps.get_pending,
    deps.get_light,
    deps.get_climate,
    deps.get_music,
    deps.get_calendar,
    deps.get_expenses,
    deps.get_tools,
    deps.get_runner,
    deps.get_openai,
    deps.get_chat_model,
    deps.get_live_slot,
    deps.get_live_port,
)


@pytest.fixture(autouse=True)
def clear_dependency_caches() -> Iterator[None]:
    """`lru_cache` singletons must not leak between tests."""
    for fn in _CACHED:
        fn.cache_clear()
    yield
    for fn in _CACHED:
        fn.cache_clear()
```

- [ ] **Step 2: Create `tests/unit/api/test_live.py`**

Create `tests/unit/api/test_live.py`:

```python
from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.deps import get_live_slot, get_run_live_session, get_runner, get_settings
from app.api.live import router as live_router
from app.api.live_slot import LiveSlot
from app.domain.exceptions import LiveSessionError
from app.domain.live import (
    AssistantAudio,
    AssistantTranscript,
    ResponseDone,
    UserSpeechStarted,
)
from tests.fakes.live import LiveWorld
from tests.fakes.world import TOKEN, make_settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import WebSocket
    from starlette.testclient import WebSocketTestSession

URL = "/api/v1/live"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


class TrackingSlot(LiveSlot):
    """Counts released connections, so a test can wait for the server side to finish cleaning
    up (the Starlette test client cancels the app right after the client disconnects)."""

    def __init__(self) -> None:
        super().__init__()
        self.releases = 0

    def release(self, websocket: WebSocket) -> None:
        super().release(websocket)
        self.releases += 1


def make_client(world: LiveWorld) -> tuple[TestClient, TrackingSlot]:
    app = FastAPI()
    app.include_router(live_router, prefix="/api/v1")
    slot = TrackingSlot()
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_runner] = lambda: world.runner
    app.dependency_overrides[get_run_live_session] = lambda: world.run
    app.dependency_overrides[get_live_slot] = lambda: slot
    return TestClient(app), slot


def until(predicate: Callable[[], bool], within: float = 2.0) -> None:
    deadline = time.monotonic() + within
    while not predicate():
        assert time.monotonic() < deadline, "condition not reached in time"
        time.sleep(0.01)


def leave(ws: WebSocketTestSession, slot: TrackingSlot, releases: int = 1) -> None:
    """Disconnect and wait until the server finished cleaning up this connection."""
    ws.close()
    until(lambda: slot.releases >= releases)


def receive_event(ws: WebSocketTestSession, event_type: str) -> dict[str, object]:
    """Skip audio frames and other events until the wanted JSON event shows up."""
    for _ in range(20):
        message = ws.receive()
        text = message.get("text")
        if text is not None:
            event: dict[str, object] = json.loads(text)
            if event.get("type") == event_type:
                return event
    raise AssertionError(f"no {event_type!r} event received")


def start(ws: WebSocketTestSession, **extra: object) -> dict[str, object]:
    ws.send_json({"type": "start", **extra})
    return receive_event(ws, "ready")


@pytest.mark.unit
@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer nope"}, {"Authorization": TOKEN}]
)
def test_the_socket_requires_the_bearer_token(headers: dict[str, str]) -> None:
    client, _ = make_client(LiveWorld())
    with pytest.raises(WebSocketDisconnect) as info, client.websocket_connect(URL, headers=headers):
        pass
    assert info.value.code == 1008


@pytest.mark.unit
def test_start_then_ready_with_the_audio_contract() -> None:
    world = LiveWorld()
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ready = start(ws, segment="HOME", conversation_id="conv-1")
        leave(ws, slot)
    assert ready["conversation_id"] == "conv-1"
    assert ready["audio"] == {"format": "pcm16", "rate": 24000, "channels": 1}
    assert world.adapter.opened_with is not None
    assert {t.segment for t in world.adapter.opened_with[1]} == {"home", "*"}


@pytest.mark.unit
def test_audio_and_events_flow_through_the_socket() -> None:
    world = LiveWorld()
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        ws.send_bytes(b"\x01\x02")
        until(lambda: world.session.audio_in == [b"\x01\x02"])

        world.session.push(
            AssistantAudio(data=b"\x09\x08", item_id="a1"),
            AssistantTranscript("Pronto."),
            ResponseDone(),
        )
        assert ws.receive_bytes() == b"\x09\x08"
        transcript = receive_event(ws, "transcript")
        assert (transcript["role"], transcript["text"]) == ("assistant", "Pronto.")
        receive_event(ws, "turn_done")
        leave(ws, slot)


@pytest.mark.unit
def test_barge_in_interrupts_the_client_which_reports_what_it_played() -> None:
    world = LiveWorld()
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        world.session.push(AssistantAudio(data=b"\x01", item_id="a1"), UserSpeechStarted("u1"))
        receive_event(ws, "interrupt")
        ws.send_json({"type": "played", "audio_end_ms": 500})
        until(lambda: world.session.truncations == [("a1", 500)])
        leave(ws, slot)


@pytest.mark.unit
def test_a_bad_first_frame_is_rejected() -> None:
    client, _ = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ws.send_json({"type": "hello"})
        assert ws.receive_json() == {"type": "error", "code": "bad_start"}
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
    assert info.value.code == 1008


@pytest.mark.unit
def test_an_unknown_segment_is_rejected_never_defaulted() -> None:
    world = LiveWorld()
    client, _ = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ws.send_json({"type": "start", "segment": "nope"})
        assert ws.receive_json() == {"type": "error", "code": "bad_segment"}
    assert world.adapter.opened_with is None


@pytest.mark.unit
def test_a_new_connection_replaces_the_old_one_with_close_code_4000() -> None:
    client, slot = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as first:
        start(first)
        with client.websocket_connect(URL, headers=AUTH) as second:
            start(second)
            with pytest.raises(WebSocketDisconnect) as info:
                first.receive_json()
            leave(second, slot)
        leave(first, slot, releases=2)  # the test client only disconnects `first` when told to
    assert info.value.code == 4000


@pytest.mark.unit
def test_an_oversized_audio_frame_closes_the_socket() -> None:
    client, slot = make_client(LiveWorld())
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        ws.send_bytes(b"x" * 70_000)
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        until(lambda: slot.releases >= 1)
    assert info.value.code == 1009


@pytest.mark.unit
def test_provider_unavailable_is_reported_before_closing() -> None:
    world = LiveWorld(open_error=LiveSessionError("down"))
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        ws.send_json({"type": "start"})
        assert ws.receive_json() == {"type": "error", "code": "model_unavailable"}
        until(lambda: slot.releases >= 1)


@pytest.mark.unit
def test_garbage_frames_are_ignored_and_the_session_survives() -> None:
    world = LiveWorld()
    client, slot = make_client(world)
    with client.websocket_connect(URL, headers=AUTH) as ws:
        start(ws)
        ws.send_text("{not json")
        ws.send_text("[1, 2]")
        ws.send_bytes(b"\x07")
        until(lambda: world.session.audio_in == [b"\x07"])
        leave(ws, slot)
```

- [ ] **Step 3: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/api/test_live.py -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 4: Create `app/api/live_slot.py`**

Create `app/api/live_slot.py`:

```python
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
```

- [ ] **Step 5: Create `app/api/live_transport.py`**

Create `app/api/live_transport.py`:

```python
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
```

- [ ] **Step 6: Create `app/api/schemas.py`**

Create `app/api/schemas.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_CONTENT_CHARS = 4000


class IncomingMessageSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    segment: str = "auto"
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class PendingConfirmationSchema(BaseModel):
    summary: str


class MessageSchema(BaseModel):
    id: str
    role: str
    content: str
    conversation_id: str
    pending_confirmation: PendingConfirmationSchema | None = None


class LiveStartSchema(BaseModel):
    """First frame a live client sends."""

    model_config = ConfigDict(str_strip_whitespace=True)

    type: Literal["start"]
    segment: str = "auto"
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
```

- [ ] **Step 7: Create `app/api/deps.py`**

Create `app/api/deps.py`:

```python
from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Depends
from openai import AsyncOpenAI

from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.adapters.openai.chat_model import OpenAIChatModel
from app.adapters.openai.live_session import OpenAILiveSessionAdapter
from app.api.live_slot import LiveSlot
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.use_cases.process_chat_message import ProcessChatMessage
from app.application.use_cases.run_live_session import LiveLimits, RunLiveSession
from app.config import Settings, load_settings

if TYPE_CHECKING:
    from app.application.registry import Registry
    from app.application.tool import Tool
    from app.ports.calendar import CalendarPort
    from app.ports.chat_model import ChatModelPort
    from app.ports.climate import ClimatePort
    from app.ports.conversation_store import ConversationStorePort
    from app.ports.expenses import ExpensesPort
    from app.ports.light import LightPort
    from app.ports.live_session import LiveSessionPort
    from app.ports.logger import LoggerPort
    from app.ports.music import MusicPort


@lru_cache
def get_settings() -> Settings:
    return load_settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_store() -> ConversationStorePort:
    return InMemoryConversationStore(get_settings().max_conversations)


@lru_cache
def get_pending() -> PendingActionStore:
    return PendingActionStore(time.monotonic)


# The three device groups pick the real adapter when it is configured and the in-memory one
# otherwise, so the whole service runs without hardware. The lifespan logs which one is active.
# Real adapters are imported lazily: their packages live in optional extras (tuya, thinq, spotify).


@lru_cache
def get_light() -> LightPort:
    lights = get_settings().tuya_lights
    if not lights:
        return InMemoryLight()
    from app.adapters.tuya.tuya_light import (  # noqa: PLC0415 - optional extra
        TuyaLight,
        TuyaLightDevice,
    )

    return TuyaLight(
        {
            name: TuyaLightDevice(s.device_id, s.address, s.local_key.get_secret_value(), s.version)
            for name, s in lights.items()
        }
    )


@lru_cache
def get_climate() -> ClimatePort:
    settings = get_settings()
    if settings.thinq_access_secret is None:
        return InMemoryClimate()
    from app.adapters.thinq.thinq_climate import ThinQClimate  # noqa: PLC0415 - optional extra

    return ThinQClimate(
        settings.thinq_access_secret.get_secret_value(),
        settings.thinq_country,
        settings.thinq_client_id,
    )


@lru_cache
def get_music() -> MusicPort:
    settings = get_settings()
    if settings.spotify_client_id is None or settings.spotify_refresh_token is None:
        return InMemoryMusic()
    from app.adapters.spotify.spotify_music import SpotifyMusic  # noqa: PLC0415 - optional extra

    return SpotifyMusic(
        settings.spotify_client_id,
        settings.spotify_refresh_token.get_secret_value(),
        settings.spotify_device,
    )


@lru_cache
def get_calendar() -> CalendarPort:
    # ponytail: in memory until the Google Calendar adapter exists
    return InMemoryCalendar()


@lru_cache
def get_expenses() -> ExpensesPort:
    # ponytail: in memory until the Google Sheets adapter exists
    return InMemoryExpenses()


@lru_cache
def get_tools() -> Registry[Tool]:
    return build_tool_registry(
        get_light(), get_climate(), get_music(), get_calendar(), get_expenses()
    )


@lru_cache
def get_runner() -> ToolRunner:
    return ToolRunner(
        get_tools(),
        get_pending(),
        get_logger(),
        tool_timeout=get_settings().tool_timeout_seconds,
    )


@lru_cache
def get_openai() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.chat_timeout_seconds,
    )


@lru_cache
def get_chat_model() -> ChatModelPort:
    return OpenAIChatModel(get_openai(), get_settings().chat_model)


@lru_cache
def get_live_port() -> LiveSessionPort:
    settings = get_settings()
    return OpenAILiveSessionAdapter(get_openai(), settings.live_model, vad=settings.live_vad)


@lru_cache
def get_live_slot() -> LiveSlot:
    return LiveSlot()


def get_process_chat(
    model: ChatModelPort = Depends(get_chat_model),
    store: ConversationStorePort = Depends(get_store),
    runner: ToolRunner = Depends(get_runner),
    pending: PendingActionStore = Depends(get_pending),
    log: LoggerPort = Depends(get_logger),
    settings: Settings = Depends(get_settings),
) -> ProcessChatMessage:
    return ProcessChatMessage(
        model,
        store,
        runner,
        pending,
        log,
        max_steps=settings.max_steps,
        history_limit=settings.history_limit,
        timeout_seconds=settings.chat_timeout_seconds,
    )


def get_run_live_session(
    live: LiveSessionPort = Depends(get_live_port),
    store: ConversationStorePort = Depends(get_store),
    runner: ToolRunner = Depends(get_runner),
    pending: PendingActionStore = Depends(get_pending),
    log: LoggerPort = Depends(get_logger),
    settings: Settings = Depends(get_settings),
) -> RunLiveSession:
    return RunLiveSession(
        live,
        store,
        runner,
        pending,
        log,
        now=time.monotonic,
        limits=LiveLimits(
            idle_seconds=settings.live_idle_seconds,
            max_seconds=settings.live_max_seconds,
            transcript_wait_seconds=settings.live_transcript_wait_seconds,
        ),
    )
```

- [ ] **Step 8: Create `app/api/live.py`**

Create `app/api/live.py`:

```python
from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.api.auth import token_matches
from app.api.deps import (
    get_live_slot,
    get_logger,
    get_run_live_session,
    get_runner,
    get_settings,
)
from app.api.live_transport import WebSocketTransport
from app.api.schemas import LiveStartSchema
from app.domain.exceptions import LiveSessionError

if TYPE_CHECKING:
    from app.api.live_slot import LiveSlot
    from app.application.tool_runner import ToolRunner
    from app.application.use_cases.run_live_session import RunLiveSession
    from app.config import Settings
    from app.ports.logger import LoggerPort

AUTO = "auto"
START_TIMEOUT_SECONDS = 5.0

router = APIRouter()


async def _reject(websocket: WebSocket, code: str) -> None:
    await websocket.send_json({"type": "error", "code": code})
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


async def _read_start(websocket: WebSocket, runner: ToolRunner) -> LiveStartSchema | None:
    """The first frame must be a valid `start`; anything else closes the socket."""
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), START_TIMEOUT_SECONDS)
    except (TimeoutError, WebSocketDisconnect, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None
    try:
        start = LiveStartSchema.model_validate(raw)
    except ValidationError:
        await _reject(websocket, "bad_start")
        return None
    segment = start.segment.strip().lower()
    if segment != AUTO and segment not in runner.segments():
        await _reject(websocket, "bad_segment")
        return None
    return start


@router.websocket("/live")
async def live(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
    runner: ToolRunner = Depends(get_runner),
    slot: LiveSlot = Depends(get_live_slot),
    run: RunLiveSession = Depends(get_run_live_session),
    log: LoggerPort = Depends(get_logger),
) -> None:
    if not token_matches(websocket.headers.get("authorization"), settings.api_token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()
    start = await _read_start(websocket, runner)
    if start is None:
        return
    segment = start.segment.strip().lower()
    await slot.claim(websocket)
    transport = WebSocketTransport(
        websocket,
        pace_factor=settings.live_pace_factor,
        max_frame_bytes=settings.live_max_frame_bytes,
    )
    try:
        await run.execute(
            transport,
            start.conversation_id or uuid4().hex,
            None if segment == AUTO else segment,
        )
    except LiveSessionError as exc:
        cause = type(exc.__cause__).__name__ if exc.__cause__ is not None else None
        log.error("live.failed", error=type(exc).__name__, cause=cause)
    finally:
        await transport.aclose()
        with contextlib.suppress(RuntimeError):
            await websocket.close()
        slot.release(websocket)  # last: "released" means this connection is fully cleaned up
```

- [ ] **Step 9: Create `main.py`**

Create `main.py`:

```python
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.adapters.logging.structlog_logger import configure_logging
from app.api.deps import (
    get_chat_model,
    get_climate,
    get_light,
    get_live_port,
    get_logger,
    get_music,
    get_runner,
    get_settings,
)
from app.api.errors import install_error_handlers
from app.api.live import router as live_router
from app.api.router import router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()  # a bad config stops the boot here, not at the first request
    configure_logging(settings.log_level, json=not sys.stdout.isatty())
    get_chat_model()
    get_live_port()
    runner = get_runner()
    # Which adapter drives each device group: an in-memory name here means "not configured".
    get_logger().info(
        "adapters.selected",
        light=type(get_light()).__name__,
        climate=type(get_climate()).__name__,
        music=type(get_music()).__name__,
    )
    yield
    await runner.drain()


app = FastAPI(title="byte", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
app.include_router(live_router, prefix="/api/v1")
install_error_handlers(app)
```

- [ ] **Step 10: Edit `app/config.py`**

In `app/config.py`, replace:

```python
    max_conversations: int = 50
```

with:

```python
    max_conversations: int = 50
    live_model: str = "gpt-realtime-2.1-mini"
    live_vad: Literal["server_vad", "semantic_vad"] = "server_vad"
    live_idle_seconds: float = 60.0
    live_max_seconds: float = 600.0
    live_transcript_wait_seconds: float = 2.0
    live_pace_factor: float = 0.9
    live_max_frame_bytes: int = 65536
```

- [ ] **Step 11: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/api/test_live.py tests/unit/test_main.py -q --no-cov
```

Expected: PASS (12 tests). Run it ten times in a row; it must pass every time.

- [ ] **Step 12: Commit**

```bash
git add app/api \
  app/config.py \
  main.py \
  tests/conftest.py \
  tests/unit/api/test_live.py
git commit -m "feat(api): add the authenticated live WebSocket with pacing and session replacement"
```

### Task 5: `scripts/live_probe.py`: try `/live` without hardware

**Files:**
- Create: `scripts/live_probe.py`
- Modify: `pyproject.toml` (dev extra: `websockets`, `pip-tools`)

**Interfaces:**
- Consumes: the running `/live` endpoint.
- Produces: a command-line WebSocket client: sends a PCM16 mono 24 kHz WAV, saves the spoken reply as a WAV.

It is a client of the protocol, not a GUI. It streams the question in 20 ms frames, appends 1.5 s of silence so the provider VAD ends the turn, and stops at the first `turn_done` that followed audio.

- [ ] **Step 1: Create `scripts/live_probe.py`**

Create `scripts/live_probe.py`:

```python
"""Manual check of /live: send a WAV question, save the spoken reply.

    python scripts/live_probe.py question.wav reply.wav \
        --url wss://192.168.0.10:8000/api/v1/live --token "$BYTE_API_TOKEN" --cafile certs/byte.crt

The WAV must be PCM16, mono, 24 kHz. This is a client of the WebSocket protocol, not a GUI.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import ssl
import wave
from pathlib import Path

import websockets

RATE = 24_000
FRAME_MS = 20
FRAME_BYTES = RATE * 2 * FRAME_MS // 1000
SILENCE_SECONDS = 1.5
REPLY_TIMEOUT_SECONDS = 30


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, RATE):
            raise SystemExit("question.wav must be PCM16 mono 24000 Hz")
        return wav.readframes(wav.getnframes())


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm)


async def stream_question(ws: websockets.ClientConnection, pcm: bytes) -> None:
    silence = bytes(int(RATE * 2 * SILENCE_SECONDS))  # lets the provider VAD end the turn
    audio = pcm + silence
    for offset in range(0, len(audio), FRAME_BYTES):
        await ws.send(audio[offset : offset + FRAME_BYTES])
        await asyncio.sleep(FRAME_MS / 1000)


async def probe(args: argparse.Namespace) -> None:
    context = ssl.create_default_context(cafile=args.cafile) if args.url.startswith("wss") else None
    headers = {"Authorization": f"Bearer {args.token}"}
    reply = bytearray()
    async with websockets.connect(args.url, additional_headers=headers, ssl=context) as ws:
        await ws.send(json.dumps({"type": "start", "segment": args.segment}))
        sender: asyncio.Task[None] | None = None
        try:
            async with asyncio.timeout(REPLY_TIMEOUT_SECONDS):
                async for message in ws:
                    if isinstance(message, bytes):
                        reply.extend(message)
                        continue
                    event = json.loads(message)
                    print(event)
                    if event["type"] == "ready":
                        sender = asyncio.create_task(stream_question(ws, read_wav(args.question)))
                    elif event["type"] == "error":
                        raise SystemExit(f"server error: {event['code']}")
                    elif event["type"] == "turn_done" and reply:
                        break
        finally:
            if sender is not None:
                sender.cancel()
    write_wav(args.reply, bytes(reply))
    print(f"saved {len(reply)} bytes of audio to {args.reply}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", type=Path)
    parser.add_argument("reply", type=Path)
    parser.add_argument("--url", default="ws://127.0.0.1:8000/api/v1/live")
    parser.add_argument("--token", required=True)
    parser.add_argument("--segment", default="auto")
    parser.add_argument("--cafile", help="pinned self-signed certificate for wss://")
    asyncio.run(probe(parser.parse_args()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Edit `pyproject.toml`**

In `pyproject.toml`, replace:

```toml
    "httpx>=0.27",
]
```

with:

```toml
    "httpx>=0.27",
    "websockets>=14",
    "pip-tools>=7.4",
]
```

- [ ] **Step 3: Run the tests and watch them pass**

```bash
python scripts/live_probe.py --help
```

Expected: prints the usage line with `question`, `reply`, `--url`, `--token`, `--segment`, `--cafile`.

- [ ] **Step 4: Try it for real (needs a real OpenAI key; skip if you do not have one yet)**

```bash
pip install -e ".[api,openai,dev]"
uvicorn main:app --port 8000 &
python scripts/live_probe.py question.wav reply.wav --token "$BYTE_API_TOKEN"
```

`question.wav` must be PCM16, mono, 24 kHz (for example `ffmpeg -i in.m4a -ac 1 -ar 24000 -sample_fmt s16 question.wav`). Expected: `ready`, `transcript` and `turn_done` events printed, then `saved N bytes of audio to reply.wav`; play `reply.wav` to hear the answer. Stop the server afterwards (`kill %1`).

- [ ] **Step 5: Commit**

```bash
git add scripts/live_probe.py \
  pyproject.toml
git commit -m "feat(scripts): add live_probe, a command-line client for the live WebSocket"
```

### Task 6: Hardening: locked dependencies, non-root image, TLS flags, repo hygiene, docs

**Files:**
- Replace: `Dockerfile`, `docker-compose.yml`, `.env.example`, `.pre-commit-config.yaml`, `.dockerignore`, `README.md`, `docs/ARCHITECTURE.md`, `docs/CONVENTIONS.md`
- Create: `requirements.lock`
- Modify: `.gitignore` (append; keep the uncommitted tinytuya lines), `CLAUDE.md` (Current state)
- Untrack: `.idea/`, `.claude/settings.local.json`

**Interfaces:**
- Consumes: the finished chat and live services.
- Produces: an image that runs as a non-root user from locked dependencies, TLS enabled by `BYTE_TLS_CERT`/`BYTE_TLS_KEY`, LAN exposure opt-in through `BYTE_PUBLISH_HOST`, a pre-commit that type-checks in the project environment, and docs that match the code.

**Check before touching `.gitignore`:** it may have uncommitted lines of yours (the tinytuya wizard output files). Run `git diff .gitignore`; step 8 only *appends* and never discards them. Likewise, only `git add` the paths listed in each commit step: other untracked files in your working tree are not part of this plan.

`requirements.lock` is generated, not written by hand (step 2). It needs network access.

- [ ] **Step 1: Create `Dockerfile`**

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Locked dependencies: regenerate with the pip-compile command in the README.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY main.py ./

RUN useradd --system --no-create-home --uid 10001 byte
USER byte

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
    CMD python -c "import os, ssl, urllib.request as u; tls = os.environ.get('BYTE_TLS_CERT'); u.urlopen(('https' if tls else 'http') + '://localhost:8000/api/v1/health', context=ssl._create_unverified_context() if tls else None)"

# TLS is on when BYTE_TLS_CERT and BYTE_TLS_KEY are set (required for LAN exposure).
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port 8000 ${BYTE_TLS_CERT:+--ssl-certfile \"$BYTE_TLS_CERT\" --ssl-keyfile \"$BYTE_TLS_KEY\"}"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

Create `docker-compose.yml`:

```yaml
services:
  api:
    build: .
    ports:
      # Loopback by default. Set BYTE_PUBLISH_HOST=<LAN IP> only together with TLS (see README).
      - "${BYTE_PUBLISH_HOST:-127.0.0.1}:8000:8000"
    env_file:
      - .env
    volumes:
      - ./certs:/certs:ro
    restart: unless-stopped
```

- [ ] **Step 3: Create `.env.example`**

Create `.env.example`:

```bash
# --- required ---------------------------------------------------------------
# Bearer token for every route and the WebSocket. At least 32 characters; the app
# refuses to boot otherwise. Generate one: python -c "import secrets; print(secrets.token_urlsafe(48))"
BYTE_API_TOKEN=
BYTE_OPENAI_API_KEY=

# --- models -----------------------------------------------------------------
BYTE_CHAT_MODEL=gpt-4.1-mini
BYTE_LIVE_MODEL=gpt-realtime-2.1-mini
# server_vad | semantic_vad (A/B them with your own voice)
BYTE_LIVE_VAD=server_vad

# --- devices (optional) -----------------------------------------------------
# A group left empty runs against an in-memory fake, and the log says so at boot.
# LG ThinQ Personal Access Token (https://connect-pat.lgthinq.com)
BYTE_THINQ_ACCESS_SECRET=
BYTE_THINQ_COUNTRY=BR
# Tuya lights over the LAN, by name: {"lampada":{"device_id":"","address":"","local_key":"","version":3.3}}
BYTE_TUYA_LIGHTS=
# Spotify (Premium). Client ID from developer.spotify.com; token via scripts/spotify_login.py
BYTE_SPOTIFY_CLIENT_ID=
BYTE_SPOTIFY_REFRESH_TOKEN=
# Spotify Connect device name, e.g. your Nest Mini
BYTE_SPOTIFY_DEVICE=

# --- runtime ----------------------------------------------------------------
BYTE_LOG_LEVEL=INFO

# --- LAN exposure (ESP32) ---------------------------------------------------
# Leave empty for loopback only. To expose on the LAN set BOTH the host and the TLS pair;
# never publish without TLS: the bearer token would travel in cleartext.
BYTE_PUBLISH_HOST=
BYTE_TLS_CERT=
BYTE_TLS_KEY=
```

- [ ] **Step 4: Create `.pre-commit-config.yaml`**

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
        args: [--maxkb=500]
      - id: check-merge-conflict
      - id: detect-private-key
      - id: mixed-line-ending
        args: [--fix=lf]

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.7.4
    hooks:
      - id: ruff
        args: [--fix, --exit-non-zero-on-fix]
      - id: ruff-format

  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.6.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
        args: [feat, fix, refactor, test, chore, docs, perf, style, ci, build, revert]

  - repo: local
    hooks:
      # Runs in the project environment: an isolated pyright env cannot resolve fastapi/openai
      # and would report every import as unknown under strict mode.
      - id: pyright
        name: pyright (project environment)
        entry: pyright
        language: system
        types: [python]
        pass_filenames: false
      - id: pytest-fast
        name: pytest (unit only)
        entry: pytest -q
        language: system
        pass_filenames: false
        stages: [pre-push]
```

- [ ] **Step 5: Create `.dockerignore`**

Create `.dockerignore`:

```
.git/
.idea/
.claude/
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
tests/
docs/
scripts/
certs/
.env
.env.*
!.env.example
```

- [ ] **Step 6: Create `README.md`**

Create `README.md`:

````markdown
# Byte

A personal assistant backend for one person, running headless in Docker on a home
server. It controls lights, an air conditioner and music, manages a calendar and tracks
monthly expenses, through two modes:

- **chat** — `POST /api/v1/messages`: a text message in, a text reply out.
- **live** — `WS /api/v1/live`: a spoken conversation; the agent runs tools while it talks.

One agent holds every tool. Every outside resource (the model provider, the smart
home, the calendar, the expense sheet, storage) is an adapter behind a port. The
live client is a custom ESP32-S3, but the protocol is plain WebSocket: any client works.

No GUI, no computer vision, no chat-channel adapters, no multi-user support.

## Run

```bash
cp .env.example .env        # fill BYTE_API_TOKEN (32+ chars) and BYTE_OPENAI_API_KEY
docker compose up --build
```

API on `http://127.0.0.1:8000/api/v1`, interactive docs at `/docs`. Compose binds to
loopback only.

### Real devices

Each group runs against an in-memory fake until you configure the real thing, and the
boot log says which adapter is active (`adapters.selected`).

| Group | Adapter | Configure in `.env` |
|---|---|---|
| Lights | Tuya, over the LAN (`tinytuya`) | `BYTE_TUYA_LIGHTS`: JSON of name → `device_id`, `address`, `local_key`, `version` |
| Air conditioner | LG ThinQ | `BYTE_THINQ_ACCESS_SECRET` (personal access token), `BYTE_THINQ_COUNTRY` |
| Music | Spotify (Premium) | `BYTE_SPOTIFY_CLIENT_ID`, `BYTE_SPOTIFY_REFRESH_TOKEN` (get it with `python scripts/spotify_login.py`), `BYTE_SPOTIFY_DEVICE` |

### Expose it on the LAN (for the ESP32)

Only together with TLS, because the bearer token would otherwise travel in cleartext.

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=byte" \
  -keyout certs/byte.key -out certs/byte.crt \
  -addext "subjectAltName=IP:192.168.0.10"          # the server's LAN IP
```

Give the server a fixed DHCP reservation for that IP, pin `certs/byte.crt` in the
firmware, then set in `.env`:

```
BYTE_PUBLISH_HOST=192.168.0.10
BYTE_TLS_CERT=/certs/byte.crt
BYTE_TLS_KEY=/certs/byte.key
```

## Chat

```bash
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H "authorization: Bearer $BYTE_API_TOKEN" -H 'content-type: application/json' \
  -d '{"content": "apaga o dentista de amanhã"}'
```

```json
{
  "id": "…",
  "role": "assistant",
  "content": "Apagar o evento evt-1. Posso apagar?",
  "conversation_id": "…",
  "pending_confirmation": { "summary": "Apagar o evento evt-1" }
}
```

Send `conversation_id` on later calls to continue the conversation. `segment`
(`home`, `music`, `agenda`, `finance`) is an optional filter over the tools; omitted or
`auto` means all of them; an unknown segment returns `404`.

Sensitive actions (deleting a calendar event, recording an expense, switching the air
conditioner on or off) never run on the first request: the reply carries the exact action in
`pending_confirmation`, and only the user's very next message, if it is a clear
"sim", executes it.

## Live protocol

`WS /api/v1/live` with `Authorization: Bearer <token>` on the upgrade request.

| Direction | Frame | Meaning |
|---|---|---|
| client → server | JSON `{"type":"start","segment"?,"conversation_id"?}` | first frame |
| server → client | JSON `{"type":"ready","conversation_id","audio":{"format":"pcm16","rate":24000,"channels":1}}` | provider session is open; start streaming |
| both | binary | PCM16 mono 24 kHz audio |
| server → client | JSON `transcript`, `turn_done`, `interrupt`, `error {code}`, `closed {reason}` | events |
| client → server | JSON `{"type":"played","audio_end_ms":N}` | after `interrupt`: how much of the reply was actually played |

Firmware requirements: upsample 16 → 24 kHz, echo cancellation (or mute the mic
while playing), buffer microphone audio until `ready`, pin the server certificate,
and do not auto-reconnect after close code `4000` (another client took over).
One live session at a time; a session ends after 60 s without speech or 10 minutes.

Try it without hardware:

```bash
python scripts/live_probe.py question.wav reply.wav --token "$BYTE_API_TOKEN"
```

## Develop

```bash
pip install -e ".[api,openai,thinq,tuya,spotify,dev]"
ruff check . && pyright && pytest
pytest -m integration        # hits the real OpenAI API (needs BYTE_OPENAI_API_KEY)
```

Regenerate the locked dependencies used by the Docker image:

```bash
pip-compile --extra api --extra openai --extra thinq --extra tuya --extra spotify \
  --strip-extras -o requirements.lock pyproject.toml
```

## Status

Chat and live are built end to end. Lights (Tuya), the air conditioner (ThinQ) and music
(Spotify) have real adapters; the calendar and the expenses are still **in memory**, so
the whole flow (tools, confirmation, barge-in) also runs with no device at all. Not built
yet: the Google Calendar and Google Sheets adapters, Postgres persistence (history is in
memory and lost on restart), the Gemini Live adapter and the reminder scheduler.

See `CLAUDE.md` for the rules, `docs/ARCHITECTURE.md` for the decisions and
`docs/superpowers/specs/` for the design.
````

- [ ] **Step 7: Create `docs/ARCHITECTURE.md`**

Create `docs/ARCHITECTURE.md`:

````markdown
# Architecture

## Why Hexagonal

Byte is a headless personal assistant for one person: text or voice in, an answer out, with tools that act on the home, the calendar and the expenses. The pieces that will change are the model provider (OpenAI today, Gemini Live next), the smart-home vendor (Tuya), the calendar and spreadsheet providers (Google), and the datastore. The conversation and tool lifecycle does not change. Hexagonal isolates that lifecycle from all of them.

We chose Hexagonal over Onion or Clean because:

- **Smaller surface.** Two zones: inside (domain + use cases) vs outside (adapters).
- **Ports are explicit.** ABCs make the contract visible; no Protocol guessing.
- **Driving vs Driven** distinction matches our reality (the HTTP/WebSocket API and the scheduler drive; the model provider, Tuya, Google, DB and logging are driven).

We rejected Clean Architecture's `entities/` vs `rules/` split — business rules live inside the entities or use cases here. The split adds folders without adding clarity.

## Layers

```
┌──────────────────────────────────────────────────────────┐
│  api/  ──── driving adapter (FastAPI). Only entrypoint.  │
│         │                                                 │
│         ▼                                                 │
│  application/  ──── use cases, ToolRunner, tools, Registry│
│         │                                                 │
│         ▼                                                 │
│  domain/  ──── entities, value objects, domain errors     │
│         ▲                                                 │
│         │                                                 │
│  ports/  ──── ABCs the application calls                  │
│         ▲                                                 │
│         │                                                 │
│  adapters/  ──── concrete impls (driven side)             │
└──────────────────────────────────────────────────────────┘
```

**Dependency rule (strict):**

| Layer | May import |
|---|---|
| `domain/` | stdlib only |
| `ports/` | `domain/` + stdlib |
| `application/` | `domain/`, `ports/`, stdlib |
| `adapters/` | everything except `api/` |
| `api/` | everything |

Violations of this rule are caught by import linting (TID rule in ruff) + pyright.

## The tool loop

There is **one agent with all tools**. A `Tool` (ABC in `application/`) has a `ToolSpec` (name, JSON schema, segment, `requires_confirmation`) and an async `execute(args, key)` that talks to the world only through ports (`LightPort`, `ClimatePort`, `MusicPort`, `CalendarPort`, `ExpensesPort`). Tools live in a `Registry[Tool]`; `segment` is only an optional filter over it.

```python
registry = build_tool_registry(light, climate, music, calendar, expenses)   # Registry[Tool]
runner = ToolRunner(registry, pending, log)                # allowlist, timeout, shield, confirmation
reply = await ProcessChatMessage(model, store, runner, pending, log).execute(cid, text, segment)
```

Chat (`POST /messages`) and live (`WS /live`) share the registry, the runner and the confirmation rules; only the transport differs. A sensitive tool does not run when called: `ToolRunner` stores one `PendingAction` per conversation, and only the argument-free `confirm_action()` executes it, iff the very next user utterance is affirmative (`is_affirmative`). Tool execution is shielded from cancellation and bounded by a timeout that reports `estado desconhecido` rather than success or failure.

**Contract of `Registry[T]`:** case-insensitive lookup, duplicate registration raises `RegistryDuplicateError`, a missing key raises `RegistryKeyError`, `values()` lists the registered instances.

## Patterns we use

| Pattern | Where | Why |
|---|---|---|
| Adapter | `adapters/**` | Heart of Hexagonal. One adapter per outside resource. |
| Registry | `application/registry.py` | Tools by name; segments are a filter. |
| Strategy | prompt builders, summarizers | Interchangeable algorithms behind a port. |
| Dependency Injection | `api/deps.py` via `lru_cache` | No singletons, FastAPI-native. |

## Patterns we rejected

- **Factory Method as a class** — Registry already plays factory. A separate `ToolFactory` adds a layer with no behavior.
- **Singleton** — `lru_cache` on a DI provider gives the same effect with zero ceremony and no global state.
- **Repository + UnitOfWork combo** — too heavy for a single-aggregate backend. We start with a simple `ConversationStorePort`. Revisit if multi-aggregate transactions appear.
- **Sub-agents, Teams, agent-to-agent handoff** — one owner and about sixteen tools do not need routing. Cross-segment work is the single agent calling two tools. Keeps the call graph a line, not a mesh.

## Decisions log (ADRs)

### ADR-001: Hexagonal over Onion+Clean (2026-05-06)
**Context:** original spec stacked Onion + Hexagonal + Clean.
**Decision:** Hexagonal only.
**Why:** the three patterns overlap. Stacking them adds folders without isolation gain.
**Trade-off:** less "academic completeness," faster onboarding.

### ADR-002: Pydantic at boundary only (2026-05-06)
**Context:** original spec had `schemas/` at root with Pydantic everywhere.
**Decision:** Pydantic models live in `api/` and `config.py`. Domain uses `@dataclass(frozen=True, slots=True)`.
**Why:** keeps domain pure and dependency-free. Pydantic upgrades cannot break domain logic.
**Trade-off:** explicit conversion at the boundary (DTO ↔ entity). Worth the isolation.

### ADR-003: Async-first I/O (2026-05-06)
**Context:** decision between sync MVP + async migration vs async from day one.
**Decision:** async from day one for all I/O ports.
**Why:** rewriting sync→async later is painful. Agent SDKs and asyncpg are async-native.
**Trade-off:** slightly more boilerplate in tests (`pytest-asyncio`). Acceptable.

### ADR-004: One use case per file (2026-05-06)
**Context:** lean structure favored single `use_cases.py`.
**Decision:** `application/use_cases/<name>.py` from day one.
**Why:** use cases grow fast. Splitting later forces git-rename churn.
**Trade-off:** more files at start. Negligible.

### ADR-005: LoggerPort in Cycle 1 (2026-05-06)
**Context:** logging often deferred.
**Decision:** ship `LoggerPort` + structlog adapter in Cycle 1.
**Why:** retrofit cost is high; debugging without structured logs is slow.
**Trade-off:** ~30 lines extra in Cycle 1. Negligible.

### ADR-006: API-only, no channel adapters (2026-09-01)
**Context:** the original design targeted a personal assistant reachable over WhatsApp/Telegram/Email, with an eye on a GUI and vision input.
**Decision:** Byte is a headless backend. HTTP is the only interface. No GUI, no computer vision, no chat-channel adapters.
**Why:** Byte runs on a local server and serves other applications. Those consumers already own their own channels and UIs; duplicating that inside Byte doubles the surface for zero gain.
**Trade-off:** nothing talks to Byte directly out of the box — a consumer must exist. Accepted: that is the deployment model.
**Consequence:** `MessagingPort` deleted; `channel`, `sender` and `recipient` removed from the domain.

### ADR-007: One agent per segment, explicit routing (2026-09-01)
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** a single general agent versus several specialised ones, and how a request reaches the right one.
**Decision:** one `AgentPort` instance per segment, held in `Registry[AgentPort]`. The caller names the segment in the request body.
**Why:** each segment gets its own instructions, tools and model without conditionals in the use case. Explicit routing keeps the request deterministic and debuggable — no classifier silently picking the wrong agent.
**Trade-off:** the consumer must know the segment names. Cheap: they are a short, stable list.
**Alternative kept open:** an intent-classification use case in front of the registry, if auto-routing is ever wanted. It composes; it does not replace.

### ADR-008: AgentPort replaces LLMPort (2026-09-01)
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** Cycle 1 shipped `LLMPort.complete()`; the Cycle 2 design added `AgentPort.run()` alongside it, keeping `LLMPort` "for embeddings later".
**Decision:** one port. `LLMPort` and `StubLLM` deleted; `AgentPort.run(message, conversation) -> str` is the contract.
**Why:** two ports with the same shape and one implementation each is a speculative abstraction. Embeddings are not on the roadmap; when they arrive they get their own port with a real signature instead of a guessed one.
**Trade-off:** if raw completions are needed, a port has to be reintroduced. Small, and better designed with the actual requirement in hand.

### ADR-009: Speech runs on the server (2026-09-01)
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** the client is a custom ESP32-S3. Speech-to-text and text-to-speech could run on the device or on the server.
**Decision:** the device does wake-word detection locally (ESP-SR) and streams raw audio. Transcription, reasoning and synthesis all happen server-side; audio comes back over the same request.
**Why:** on-device recognition on an ESP32-S3 is limited to a fixed command set, which is the opposite of an assistant you can talk to freely. Keeping speech on the server also means the engine can be swapped without reflashing hardware, and a second client gets voice for free.
**Trade-off:** more bandwidth, and round-trip latency now includes the network. Accepted — the device is on the same LAN as the server.
**Consequence:** `SpeechToTextPort` and `TextToSpeechPort`, plus `POST /voice`. Audio never travels below the API layer; the use case still receives text.

### ADR-010: Agno Team (route mode) for intent routing (2026-09-01)
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** ADR-007 had the caller name the segment explicitly. A person speaking a sentence to a device cannot do that, so something must map an utterance onto a segment. Options: a hand-written classifier use case in front of `Registry[AgentPort]`, a single agent holding every tool, or Agno's Team in route mode.
**Decision:** Agno Team in route mode, wrapped as `AgnoTeamAgent(AgentPort)` and registered under the key `auto`. Explicit `segment` from ADR-007 survives as a direct path that skips the routing hop.
**Why:** the routing logic is already written, tested and maintained inside Agno. Writing our own classifier means owning prompt tuning and a second failure mode for no differentiated gain. Keeping per-segment agents (rather than one agent with every tool) keeps prompts and tool sets small and separately testable.
**Trade-off — accepted knowingly:** orchestration now lives inside the framework instead of inside `application/`, which is a genuine softening of the hexagonal boundary. This project's rule that "orchestration is a use case, not an agent calling an agent" is relaxed for the routing layer specifically, and for nothing else.
**Containment:** the Team is exposed as a single `AgentPort`. Nothing above `adapters/agent/` knows a Team exists. Agno types do not cross the port.
**Exit:** if Team routing becomes limiting — ordering, retries, partial failures across segments — the replacement is a `RouteUtterance` use case calling the registry directly. `AgentPort` does not change, so the swap touches one adapter and its registration.

### ADR-011: Google owns calendar and expenses (2026-09-01)
**Context:** events and monthly expenses could live in our Postgres, in Google Calendar and Sheets, or in Postgres with a sync to Google.
**Decision:** Google Calendar and Google Sheets are the system of record. Postgres holds conversation history, OAuth tokens, pending reminders and memory embeddings — never a second copy of the truth.
**Why:** the spreadsheet and the calendar are already used from a phone every day. Making Postgres authoritative would mean building an interface to view and edit them, which is a frontend, which is out of scope. Bidirectional sync was rejected outright: it is the option that generates conflict bugs.
**Trade-off:** Byte now depends on OAuth, refresh tokens and Google rate limits, and it degrades when Google is unreachable. Cached reads are allowed for latency; a cache is never promoted to source of truth.

### ADR-012: Reminders pushed over WebSocket (2026-09-01)
**Context:** bill and appointment reminders must reach the device unprompted. Options: the device polls, the server pushes over WebSocket, or the server publishes to an MQTT broker.
**Decision:** the server pushes over a WebSocket at `/ws/notifications`. A scheduler adapter wakes periodically; deciding what is due is a use case, testable without a real clock.
**Why:** polling adds latency for something time-sensitive. Between the two push options, FastAPI serves WebSocket natively, so it costs no broker container and no extra operational surface.
**Trade-off:** the server now holds connection state and must handle reconnects, which a broker would have handled. Undelivered reminders are persisted and replayed on reconnect rather than dropped.
**Revisit when:** the device sleeps deeply enough to miss pushes, or more than one client connects. That is when MQTT earns its container — not before.

### ADR-013: Model tier per role, cross-provider fallback (2026-09-02)
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** every agent ran on one model from one vendor. Byte answers by voice, so a trivial "apaga a luz" pays the same latency and price as a question that actually needs reasoning, and a single provider outage takes the whole assistant down.
**Decision:** each role gets a tier fixed at build time — the routing Team and `home` on Groq (fastest), `agenda` and `finance` on Gemini — and every tier declares an Agno `FallbackConfig`. `on_error` prefers another provider first; `on_rate_limit` prefers the same provider's other tier first. Models are configured as `<provider>:<model_id>` strings, which Agno resolves natively.
**Why:** the difficulty of a segment's work is known when the segment is written, so paying an LLM hop to classify difficulty at runtime buys nothing and costs latency on every utterance — the same reasoning ADR-010 used against a hand-written router. Splitting the two fallback lists follows the failure modes: a 429 means that model is busy while the provider is up, an error may mean it is not.
**Trade-off:** a request whose difficulty is unusual for its segment gets the wrong tier. Accepted — retuning is one env var, and the tier table lives in one dict.
**Consequence:** Anthropic is not wired in; there is no key for it. Adding it later is a config string, not a code change. `google-genai` and `groq` join the `agents` extra.
**Note:** the free Gemini tier serves no `pro` model — `gemini-2.5-pro` is closed to new accounts and `gemini-3.1-pro-preview` has a zero quota — so the heavy tier is `gemini-3.7-flash`. Revisit when the account is paid.

### ADR-014: One agent, own tool loop, OpenAI behind ports (2026-10-05)
**Context:** the Agno Team routed each utterance to a per-segment agent. The owner wants two modes — chat and a live spoken conversation that executes tools mid-conversation — for one person, with every outside integration as an adapter.
**Decision:** one agent holding every tool, a small tool loop in `ProcessChatMessage`, and OpenAI behind `ChatModelPort` (chat) and `LiveSessionPort` (Realtime, `gpt-realtime-2.1-mini`). Agno, the Team, `AgentPort` and `Registry[AgentPort]` are removed. Gemini Live is the planned second `LiveSessionPort` adapter.
**Why:** with one owner and about sixteen tools the routing hop is latency with no gain, and Agno cannot do speech-to-speech, so live would have bypassed it and defined every tool twice. At personal scale the price gap between providers is $10-40 per month, so quality (tool-call reliability, pt-BR, latency) decides, settled by an A/B day.
**Trade-off:** cross-provider fallback is gone for now; the OpenAI SDK's default retries cover 429/5xx. A second provider returns with its own adapter.
**Consequence:** supersedes ADR-007, 008, 009, 010 and 013. `segment` is an optional tool filter; an unknown segment still fails with 404.

### ADR-015: Confirmation is enforced in code (2026-10-05)
**Context:** "confirm before acting" lived only in the prompt, so a model could act first and apologise later; in live mode, noise or the assistant's own echo can look like consent.
**Decision:** a tool with `requires_confirmation` is never executed when called. `ToolRunner` stores one `PendingAction` per conversation (frozen arguments, code-generated summary, 60 s expiry). The argument-free `confirm_action()` runs it iff the pending action is armed by the very next user utterance and that utterance passes `is_affirmative` (whole words, five words or fewer, deny list wins). In live, speech that starts while the assistant is talking never confirms, and `confirm_action` waits up to 2 s for the transcript.
**Why:** the model cannot guess an id, replay one across conversations or confirm in the same turn. A restart drops pending actions, which fails safe.
**Residual risk:** a spoken "sim" from a TV or another person in the room still counts; the 60 s expiry, the next-utterance rule and the code-generated summary limit the window. In live the user hears the model's wording of the summary.

### ADR-016: Live over WebSocket, LAN exposure with TLS (2026-10-05)
**Context:** the live client is an ESP32-S3 on the LAN, which cannot reach a loopback-bound server; plain `ws://` would send the bearer token in cleartext.
**Decision:** `WS /api/v1/live` carries PCM16 mono 24 kHz audio as opaque binary frames plus JSON control events. Auth is `Authorization: Bearer` (a token of at least 32 characters). Compose binds to `127.0.0.1` by default; `BYTE_PUBLISH_HOST=<LAN IP>` opts in to LAN exposure, which requires `wss://` with a self-signed certificate pinned in the firmware. One live session at a time; a new connection replaces the old one (close code 4000).
**Why:** audio stays opaque below the API layer, the provider session is an adapter, and a half-open socket after a Wi-Fi drop cannot lock the owner out.
**Firmware requirements:** upsample 16 to 24 kHz, echo cancellation or mute while playing, buffer microphone audio until `ready`, pin the certificate, do not auto-reconnect after close code 4000.
````

- [ ] **Step 8: Create `docs/CONVENTIONS.md`**

Create `docs/CONVENTIONS.md`:

````markdown
# Coding Conventions

> Mechanical rules. For the *why*, see `ARCHITECTURE.md`. For project-wide guardrails, see `CLAUDE.md`.

## Naming

| Kind | Style | Example |
|---|---|---|
| Module | `snake_case` | `process_message.py` |
| Package | `snake_case` | `memory` |
| Class | `PascalCase` | `ChatModelPort` |
| Function/method | `snake_case` | `run_agent` |
| Constant | `UPPER_SNAKE` | `DEFAULT_TIMEOUT_S` |
| Private | leading `_` | `_internal_state` |
| Type var | single upper letter | `T`, `K`, `V` |

### Suffix conventions

| Kind | Suffix | Example |
|---|---|---|
| Port (ABC) | `Port` | `ChatModelPort`, `ConversationStorePort` |
| Adapter | adapter target | `OpenAIChatModel`, `InMemoryHome` |
| Pydantic schema | `Schema` | `IncomingMessageSchema` |
| Domain entity | none | `Message`, `Device` |
| Use case | verb phrase | `ProcessChatMessage` |
| Exception | `Error` | `RegistryDuplicateError` |

## Files & layout

- One **public** class per module. Helpers may share if used only by that class.
- Test path mirrors source: `app/application/use_cases/x.py` → `tests/unit/application/use_cases/test_x.py`.
- `__init__.py` exports only public surface. Use explicit `__all__`.

## Imports

- **Absolute** from `app.*`. No `from ..foo import bar`.
- Group: stdlib → third-party → first-party. `ruff` enforces.
- `from __future__ import annotations` at top of every module.
- Type-only imports inside `if TYPE_CHECKING:`.

## Type hints

- Mandatory on every function signature, including return type (use `-> None` explicitly).
- Use `from collections.abc import` for `Sequence`, `Mapping`, `Iterable`, `Awaitable`.
- Prefer `list[X]` over `List[X]` (we are 3.12+).
- Generics: declare `TypeVar` at module top with `bound=` when applicable.
- `Any` is banned. If unavoidable, add `# noqa: ANN401` with a one-line justification.

## Domain entities

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class Message:
    id: str
    role: str
    content: str
    timestamp: datetime
```

Rules:
- `frozen=True` always.
- `slots=True` always.
- No methods that touch I/O. Pure logic only.
- No Pydantic. No external libs.

## Ports

```python
from abc import ABC, abstractmethod
from app.domain.model import ModelMessage, ModelTurn
from app.domain.tools import ToolSpec

class ChatModelPort(ABC):
    @abstractmethod
    async def complete(
        self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn: ...
```

Rules:
- `ABC` + `@abstractmethod`. No `Protocol`.
- Methods take/return domain entities, never DTOs.
- Async for I/O. Sync for pure computation.

## Use cases

```python
class ProcessChatMessage:
    def __init__(self, model: ChatModelPort, store: ConversationStorePort, ...) -> None:
        self._model = model
        self._store = store

    async def execute(self, conversation_id: str, text: str, segment: str | None) -> ChatReply:
        ...
```

Rules:
- Constructor takes ports. No defaults pointing to concrete classes.
- One public method, named `execute`.
- Returns a domain entity or `None`. Never a DTO.

## Adapters

- Translate external lib types ↔ domain entities at the boundary.
- Wrap external exceptions: `try: ... except OpenAIError as e: raise AgentError(...) from e`.
- No domain logic inside adapters.

## Errors

```python
# app/domain/exceptions.py
class DomainError(Exception): ...
class AgentError(DomainError): ...
class LiveSessionError(DomainError): ...
class RegistryError(DomainError): ...
class RegistryDuplicateError(RegistryError): ...
class RegistryKeyError(RegistryError): ...
```

Rules:
- All raise paths through `DomainError` subclasses.
- Adapters define their own subclass of `DomainError` (e.g., `AgentError`).
- Never raise `Exception` or `RuntimeError` directly in app code.

## Async

- I/O = async. CPU = sync.
- No `asyncio.run()` outside `main.py`.
- No `time.sleep` — use `asyncio.sleep`.
- Tests: `pytest-asyncio` with `asyncio_mode = "auto"` (already set).

## Logging

```python
class LoggerPort(ABC):
    @abstractmethod
    def info(self, event: str, **fields: object) -> None: ...
    # debug, warning, error similar
```

Rules:
- Structured. Pass fields as kwargs, not f-strings.
- Never log raw user content without redaction (PII).
- `event` is a stable string id, not a sentence.

## Testing

- **Arrange / Act / Assert** with blank lines separating.
- One assertion concept per test (multiple `assert` lines OK if they verify the same outcome).
- Test names: `test_<unit>_<condition>_<expected>`. Example: `test_registry_duplicate_key_raises`.
- Fixtures in nearest `conftest.py`. No global mocks.
- Never mock the SUT. If you need to, the design is wrong.

## Commits

Conventional Commits. Examples:

```
feat(live): add realtime session adapter
fix(registry): case-insensitive lookup ignored unicode
refactor(application): extract prompt strategy
test(domain): add Message equality cases
chore(deps): bump pydantic to 2.10
docs: ADR-009 add caching strategy
```

Body (optional) explains *why*. Footer for breaking changes:

```
BREAKING CHANGE: ChatModelPort.complete now returns a ModelTurn.
```

## Pull request / branch (when applicable)

- Branch: `<type>/<short-slug>` — `feat/live-mode`, `fix/registry-case`.
- One concern per PR. If it touches > 3 layers, split it.
- PR description: what + why + how to verify. Link to ADR if architectural.
````

- [ ] **Step 9: Edit `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md`**

In `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md`, replace:

```markdown
Status: **Approved by the owner (2026-10-05).** Plan 1 (chat) implemented; Plan 2 (live voice and hardening) pending.
```

with:

```markdown
Status: **Approved and implemented** (Plan 1: chat; Plan 2: live and hardening). Kept as the design record.
```

- [ ] **Step 10: Edit `.gitignore`**

In `.gitignore`, replace:

```
node_modules/
```

with:

```
node_modules/

# Local TLS material and per-user tool settings
certs/
.idea/
.claude/settings.local.json
```

- [ ] **Step 11: Edit `CLAUDE.md`**

In `CLAUDE.md`, replace:

```markdown
Spec 1 is delivered in two plans. **Plan 1 (chat) is done**: one agent with tools,
code-enforced confirmation, OpenAI chat, bearer auth, fail-fast boot. **Plan 2 (live voice
and hardening) is next**; until it lands, `WS /live` and TLS in this file describe the
target, not the code.

| Piece | Status |
|---|---|
| Hexagonal skeleton, structlog, in-memory store | done |
| Domain types, ports, `Tool`, `ToolRunner`, confirmation | done |
| OpenAI `ChatModelPort` + chat loop, `POST /messages` | done |
| Auth (bearer), input limits, boot validation, JSON logs | done |
| Tuya lights, LG ThinQ air conditioner, Spotify music (+ in-memory fakes) | done |
| In-memory Calendar / Expenses adapters | done |
| `WS /live` + OpenAI Realtime adapter | not started (Plan 2) |
| TLS, LAN exposure, locked dependencies, non-root image | not started (Plan 2) |
| Google Calendar / Sheets adapters | not started (later spec) |
| Postgres + pgvector + Alembic | not started (later spec) |
| Scheduler + `/ws/notifications` | not started (later spec) |
```

with:

```markdown
Spec 1 is done: chat and live voice run end to end on in-memory home, calendar and
expense adapters. What is left is replacing those adapters with real ones.

| Piece | Status |
|---|---|
| Hexagonal skeleton, structlog, in-memory store | done |
| Domain types, ports, `Tool`, `ToolRunner`, confirmation | done |
| OpenAI `ChatModelPort` + chat loop, `POST /messages` | done |
| Auth (bearer), input limits, boot validation, JSON logs | done |
| In-memory Home / Calendar / Expenses adapters | done |
| `WS /live` + OpenAI Realtime adapter | done |
| TLS, LAN exposure, locked dependencies, non-root image | done |
| Tuya, Google Calendar / Sheets adapters | not started (later spec) |
| Gemini Live adapter, A/B against OpenAI | not started (later spec) |
| Postgres + pgvector + Alembic | not started (later spec) |
| Scheduler + `/ws/notifications` | not started (later spec) |
```

- [ ] **Step 12: Run the tests and watch them pass**

```bash
python -m pytest
```

Expected: PASS — 296 passed, 4 deselected (the integration tests), coverage above 80% (about 92%).

- [ ] **Step 13: Generate the locked dependencies**

```bash
pip install "pip-tools>=7.4"
pip-compile --extra api --extra openai --extra thinq --extra tuya --extra spotify \
  --strip-extras -o requirements.lock pyproject.toml
```

Expected: `requirements.lock` is created with every package pinned (`openai`, `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `structlog`, `websockets`, `tinytuya`, `thinqconnect`, `aiohttp`, ...). The image installs the three device extras, so the real adapters work inside Docker. Re-run this command whenever you change the dependencies in `pyproject.toml`.

- [ ] **Step 14: Append the ignore rules (keep your uncommitted lines)**

Run `git diff .gitignore` first. Then append this block at the end of `.gitignore`; do not remove anything that is already there:

```gitignore
# Local TLS material and per-user tool settings
certs/
.idea/
.claude/settings.local.json
```

- [ ] **Step 15: Stop tracking files that must stay local**

```bash
git rm -r --cached .idea .claude/settings.local.json
```

Expected: the files are staged for deletion but **stay on disk**. `.idea/workspace.xml` and the local Claude permission list were tracked by accident (they carry local paths and broad allow rules).

- [ ] **Step 16: Verify the image builds, runs as non-root and passes its healthcheck**

```bash
cp .env.example .env     # skip if you already have one; set BYTE_API_TOKEN (32+ chars) and BYTE_OPENAI_API_KEY
docker compose build
docker compose up -d
docker compose exec api id -u
sleep 15 && docker inspect --format '{{.State.Health.Status}}' $(docker compose ps -q api)
curl -s http://127.0.0.1:8000/api/v1/health
docker compose down
```

Expected: the build succeeds; `id -u` prints `10001` (not `0`); health status `healthy`; `{"status":"ok"}`. If the build fails on `requirements.lock`, regenerate it (previous step).

- [ ] **Step 17: Verify TLS and LAN exposure (only if you will connect the ESP32)**

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=byte" \
  -keyout certs/byte.key -out certs/byte.crt -addext "subjectAltName=IP:<server LAN IP>"
# in .env: BYTE_PUBLISH_HOST=<server LAN IP>  BYTE_TLS_CERT=/certs/byte.crt  BYTE_TLS_KEY=/certs/byte.key
docker compose up -d
curl --cacert certs/byte.crt https://<server LAN IP>:8000/api/v1/health
python scripts/live_probe.py question.wav reply.wav --url wss://<server LAN IP>:8000/api/v1/live \
  --token "$BYTE_API_TOKEN" --cafile certs/byte.crt
```

Expected: the health call works over `https` with the pinned certificate and the probe completes a turn over `wss`. Without `--cacert` the same `curl` must fail with a certificate error: that is the pinning working.

- [ ] **Step 18: Merge-readiness gate**

```bash
ruff check . && ruff format --check . && pyright && pytest
```

Expected: all four clean (pyright: 0 errors, 0 warnings).

- [ ] **Step 19: Commit**

```bash
git add Dockerfile \
  docker-compose.yml \
  .env.example \
  .pre-commit-config.yaml \
  .dockerignore \
  .gitignore \
  requirements.lock \
  README.md \
  CLAUDE.md \
  docs/ARCHITECTURE.md \
  docs/CONVENTIONS.md \
  docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md
git commit -m "chore: lock dependencies, run as non-root with TLS flags, untrack local files and update docs"
```

> The `.gitignore` you stage here also carries your own uncommitted lines (tinytuya wizard output). They belong in `.gitignore`, so committing them together is intended.

---

## Spec coverage

| Spec item | Where |
|---|---|
| §0 success criteria 1-3 (same tools and confirmation in both modes; confirmation in code; provider swappable by one adapter) | Plan 1 Tasks 3-6, Plan 2 Tasks 1-3 |
| §1 layers and ports | Plan 1 Tasks 1-3, 6; Plan 2 Task 1 (home ports are the owner's `LightPort`/`ClimatePort`/`MusicPort`, see the amendment) |
| §2 tool loop, shielded execution, `estado desconhecido`, idempotency keys | Plan 1 Tasks 3, 5, 6 |
| §2 confirmation (one pending, next utterance only, `is_affirmative`, live transcript gate, echo guard) | Plan 1 Tasks 1, 4, 5; Plan 2 Task 2 |
| §3 auth (token >= 32 chars, `compare_digest`, header only) | Plan 1 Task 8; Plan 2 Task 4 |
| §3 protocol (`start`/`ready`, PCM16 24 kHz, events, barge-in + truncate, pacing, replace-on-reconnect, limits) | Plan 2 Tasks 2-4 |
| §3 deployment (LAN opt-in, TLS, pinned certificate) and firmware requirements | Plan 2 Task 6 (compose, Dockerfile, README, ADR-016) |
| §3 config (BYTE_ prefix, boot validation) and input limits | Plan 1 Task 8; Plan 2 Task 4 |
| §4 errors, bounds (20 messages, 50 conversations), testing strategy, contract suites | Plan 1 Tasks 2, 6, 8; Plan 2 Tasks 2-4 |
| §4 migration steps 1-7 | Plan 1 (steps 1-5), Plan 2 (steps 6-7) |
| Report findings A1-A6, M1-M9, Docker/repo/doc hygiene | A1/A3/M1/M3/M6 Plan 1 Task 8; A4/A5 Plan 1 Tasks 2, 6; A6/M4 Plan 1 Tasks 4-6; A2/M2/M5/M7/M8/M9 by design (single owner, no Agno); hygiene Plan 2 Task 6 |

### Deviations from the spec (decided while planning, all conservative)

- **The home tools use your ports.** The spec's demo `HomePort` is dropped: `home` (lights, air conditioner) and a new `music` segment sit on `LightPort`, `ClimatePort` and `MusicPort`. Plan 1 Task 9 records this as an amendment in the spec.
- **Confirmation follows your device notes, per call.** `delete_event` and `add_expense` always ask; `set_climate` asks only when it switches the unit on or off (`AR_Controle.md`: physical action) through the new `Tool.needs_confirmation(args)`, so adjusting the temperature does not ask; lights and music never ask (`Lampada_Controle.md`, `Spotfy_Controle.md`). The spec's "turning off something that is running" is read as "something physical that matters", not as every lamp.
- **Rules from the notes enforced in the tools:** a lamp is not switched on or off twice within 5 s (rapid toggling can reset it into pairing mode); the model can only play or queue a `uri` that a search or the playlists returned; a unit that reports an error says so. Not exposed, as the notes say (YAGNI): lamp scenes, liking tracks.
- **A device group with nothing configured falls back to your in-memory adapter** instead of failing at the first request, and the boot log names the adapter in use, so a missing variable is visible.
- **Order:** the spec's migration step 1 (remove Agno) happens in Plan 1 Task 8, not first: old and new code coexist, green, until the API switches in one task.
- **Transcripts are saved per message** (`append` on each user and assistant transcript), not "at turn end": same result, simpler and no data lost if the socket drops mid-turn.
- **`gpt-4.1-mini` is the default `BYTE_CHAT_MODEL`** (cheap, supports tool calling); it is one env var, to be settled by the A/B day the spec calls for.
- **Provider keys go through `Settings`/`BYTE_OPENAI_API_KEY`** and are handed to the SDK client directly; nothing is exported to the process environment.

## Done when

- `ruff check . && ruff format --check . && pyright && pytest` is clean: **296 passed, 4 deselected**, coverage about 92%, `pyright` 0 errors.
- The Docker image builds with your three device extras, runs as user `10001`, reports `healthy`, and (with a certificate) serves `wss://` to a client that pins it.
- `scripts/live_probe.py` completes a turn against the real provider, and `pytest -m integration` passes with a real key (and your lamp).
- Remaining work: Google Calendar/Sheets adapters to replace the in-memory calendar and expenses, Postgres persistence, the Gemini Live adapter, and the reminder scheduler: each its own spec.
