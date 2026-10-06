# Voice Client (Wake Word + Live) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daemon on the home laptop that listens to the local microphone, detects "Byte" with openWakeWord, then holds a spoken conversation with the agent over `WS /live`.

**Architecture:** New top-level package `voice/`, a *client* of the existing `WS /live` protocol (like `scripts/live_probe.py`), outside the hexagon. `voice/session.py` is a hardware-free state machine (`idle → connecting → live`) with every collaborator injected; `voice/audio.py` and `voice/wake.py` are thin hardware/model wrappers tested by hand; `voice/main.py` wires them. Runs as a systemd service on the host.

**Tech Stack:** Python 3.12, `websockets>=14`, `sounddevice` (PortAudio/ALSA), `numpy`, `scipy` (`resample_poly`), `openwakeword` (onnx), pydantic-settings, existing `app.*` logger/config helpers.

**Spec:** `docs/superpowers/specs/2026-10-05-voice-client-wake-word-design.md` (protocol: `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md` §3).

## Global Constraints

- Python `>=3.12`; line length 100; `pyright --strict` must pass; ruff rules as in `pyproject.toml`.
- No `print()`; log through `LoggerPort` (`app.ports.logger`). Log state transitions, close codes, error codes and durations only. Never audio, transcripts, message content or the token.
- Token comes from `BYTE_API_TOKEN` (min 32 chars, reuse `app.config.MIN_TOKEN_LENGTH`); other settings use the `BYTE_VOICE_` prefix.
- Wake-word input: PCM16 mono **16 kHz**, frames of **80 ms = 1280 samples = 2560 bytes**, `inference_framework="onnx"`.
- `/live` audio: PCM16 mono little-endian **24 kHz**, binary frames; first frame is JSON `{"type":"start","segment":...}`; audio is sent only after `{"type":"ready"}`.
- Server events handled: `ready`, `interrupt` (reply `{"type":"played","audio_end_ms":N}`), `error`, `closed`; `transcript` and `turn_done` count as activity. Binary frames = agent audio.
- Defaults: `BYTE_VOICE_URL=ws://127.0.0.1:8000/api/v1/live`, threshold `0.5`, idle `8` s, pre-ready buffer `5` s (oldest dropped), echo tail `0.3` s.
- No automatic reconnect: only a new wake word opens a session.
- Nothing leaves the laptop in IDLE.
- Voice dependencies live in the optional extra `voice`; the server image must not install it.
- Tests: no real audio, no real network, no sleeping (injected `FakeClock`). Use `--no-cov` when running a subset (the repo enforces `--cov-fail-under=80` on the full run).
- Conventional Commits; end each commit message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

**Deviation from the spec (flagged):** `openwakeword` is *not* in the `voice` extra. Its Linux requirement `tflite-runtime` has no Python 3.12 wheel, which would make the extra unresolvable. It is installed separately with `pip install --no-deps openwakeword` plus its runtime deps (Task 5, Task 7 docs). Verify this still holds when executing Task 5.

## Review Focus

Failure modes the spec implies but a happy-path test would not exercise, most likely first:

1. **Mic frame of odd length / garbage** → dropped, daemon keeps listening (Task 2 test).
2. **Server dies while a mic frame is mid-send** → no exception reaches the mic loop (Task 4 test).
3. **Agent talks longer than the idle timeout** → session must NOT be idle-closed while audio is playing (Task 4 test).
4. **Second wake word while still connecting** → no second connection (Task 2 test).
5. **Sound card cannot capture at 16 kHz** (common on built-in codecs, bare ALSA `hw:`) → clear failure, documented `plughw:` workaround (Task 6 manual check, Task 7 docs).

Also covered by tests: binary audio before `ready` is ignored (Task 2); malformed server JSON ends the session (Task 4).

## File Structure

```
voice/
├── __init__.py
├── config.py      VoiceSettings (pydantic-settings), load_voice_settings()
├── session.py     upsample_16k_to_24k, SessionConfig, VoiceSession (state machine, protocol)
├── wake.py        WakeWord: openWakeWord wrapper (bytes -> bool, reset())   [hand-tested]
├── audio.py       microphone_frames(), Speaker (sounddevice)                [hand-tested]
└── main.py        wiring + `python -m voice.main`
tests/fakes/voice.py               FakeSocket, FakeSpeaker, FakeDetector
tests/unit/voice/test_config.py
tests/unit/voice/test_session.py
deploy/byte-voice.service          systemd unit
docs/VOICE.md                      setup, devices, training the "Byte" model, tuning
```

---

### Task 1: Package skeleton, dependencies, settings

**Files:**
- Modify: `pyproject.toml`
- Create: `voice/__init__.py`, `voice/config.py`, `tests/unit/voice/__init__.py`, `tests/unit/voice/test_config.py`

**Interfaces:**
- Produces: `voice.config.VoiceSettings` with fields `api_token: SecretStr`, `wake_model: str`, `url: str`, `threshold: float`, `idle_seconds: float`, `segment: str`, `input_device: str | None`, `output_device: str | None`, `log_level: Literal["DEBUG","INFO","WARNING","ERROR"]`; `voice.config.load_voice_settings() -> VoiceSettings` (raises `app.domain.exceptions.ConfigError`, message never contains values).

- [ ] **Step 1: Wire the package into the toolchain**

Edit `pyproject.toml`:

```toml
# in [project.optional-dependencies], after `spotify`:
voice = [
    "sounddevice>=0.5",
    "websockets>=14",
    "numpy>=1.26",
    "scipy>=1.11",
    "onnxruntime>=1.16",
]
```
```toml
# [tool.hatch.build.targets.wheel]
packages = ["app", "voice"]
```
```toml
# [tool.ruff.lint.isort]
known-first-party = ["app", "voice"]
```
```toml
# [tool.pyright]
include = ["app", "voice", "tests", "main.py"]
```
```toml
# [tool.pytest.ini_options] addopts: add after "--cov=app",
    "--cov=voice",
```
```toml
# [tool.coverage.run]
source = ["app", "voice"]
omit = ["app/adapters/openai/**", "app/ports/**", "voice/audio.py", "voice/wake.py"]  # openai: integration only; ports: pure ABCs; voice/audio+wake: hardware and model, tested by hand
```

Create `voice/__init__.py` and `tests/unit/voice/__init__.py` (both empty).

- [ ] **Step 2: Install the dev + voice environment**

Run: `pip install -e ".[dev,voice]"`
Expected: installs without error (openwakeword is intentionally not part of it).

- [ ] **Step 3: Write the failing tests**

`tests/unit/voice/test_config.py`:

```python
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.domain.exceptions import ConfigError
from voice.config import load_voice_settings

TOKEN = "t" * 32


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in [n for n in os.environ if n.startswith("BYTE_")]:
        monkeypatch.delenv(name)
    monkeypatch.chdir(tmp_path)  # a developer's real .env must not leak into the test
    monkeypatch.setenv("BYTE_API_TOKEN", TOKEN)
    monkeypatch.setenv("BYTE_VOICE_WAKE_MODEL", "hey_jarvis")


def test_defaults() -> None:
    settings = load_voice_settings()
    assert settings.url == "ws://127.0.0.1:8000/api/v1/live"
    assert settings.threshold == 0.5
    assert settings.idle_seconds == 8.0
    assert settings.segment == "auto"
    assert settings.input_device is None
    assert settings.api_token.get_secret_value() == TOKEN


def test_short_token_is_rejected_without_echoing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "x" * 10)
    with pytest.raises(ConfigError, match="BYTE_API_TOKEN") as error:
        load_voice_settings()
    assert "x" * 10 not in str(error.value)


def test_wake_model_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BYTE_VOICE_WAKE_MODEL")
    with pytest.raises(ConfigError, match="wake_model"):
        load_voice_settings()


def test_missing_onnx_file_is_rejected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BYTE_VOICE_WAKE_MODEL", str(tmp_path / "byte.onnx"))
    with pytest.raises(ConfigError, match="wake_model"):
        load_voice_settings()


def test_existing_onnx_file_is_accepted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    model = tmp_path / "byte.onnx"
    model.write_bytes(b"")
    monkeypatch.setenv("BYTE_VOICE_WAKE_MODEL", str(model))
    assert load_voice_settings().wake_model == str(model)


@pytest.mark.parametrize("value", ["0", "1", "1.5", "-0.2"])
def test_threshold_must_be_between_zero_and_one(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("BYTE_VOICE_THRESHOLD", value)
    with pytest.raises(ConfigError, match="threshold"):
        load_voice_settings()
```

- [ ] **Step 4: Run to verify failure**

Run: `pytest tests/unit/voice/test_config.py --no-cov -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voice.config'`.

- [ ] **Step 5: Implement**

`voice/config.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import MIN_TOKEN_LENGTH
from app.domain.exceptions import ConfigError


class VoiceSettings(BaseSettings):
    api_token: SecretStr = Field(validation_alias="BYTE_API_TOKEN")
    wake_model: str  # an openWakeWord model name (hey_jarvis) or a path to an .onnx file
    url: str = "ws://127.0.0.1:8000/api/v1/live"
    threshold: float = Field(default=0.5, gt=0.0, lt=1.0)
    idle_seconds: float = Field(default=8.0, gt=0.0)
    segment: str = "auto"
    input_device: str | None = None
    output_device: str | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    model_config = SettingsConfigDict(
        env_prefix="BYTE_VOICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    @field_validator("api_token")
    @classmethod
    def _token_is_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_TOKEN_LENGTH:
            raise ValueError(f"must be at least {MIN_TOKEN_LENGTH} characters")
        return value

    @field_validator("wake_model")
    @classmethod
    def _model_file_exists(cls, value: str) -> str:
        if value.endswith(".onnx") and not Path(value).is_file():
            raise ValueError("model file not found")
        return value


def load_voice_settings() -> VoiceSettings:
    """Build VoiceSettings or raise ConfigError naming the bad fields, never their values."""
    try:
        return VoiceSettings()  # pyright: ignore[reportCallIssue]
    except ValidationError as exc:
        problems = ", ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigError(f"invalid voice settings ({problems})") from exc
```

- [ ] **Step 6: Run to verify pass**

Run: `pytest tests/unit/voice/test_config.py --no-cov -v`
Expected: PASS (all). If `test_short_token...` fails on `match="BYTE_API_TOKEN"`, print `str(error.value)`: pydantic reports the alias as the error `loc`; adjust only the `match` string to what it prints.

- [ ] **Step 7: Lint, types, commit**

```bash
ruff check voice tests/unit/voice && ruff format voice tests/unit/voice && pyright
git add pyproject.toml voice tests/unit/voice
git commit -m "feat(voice): add package skeleton and settings" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Session core — wake, handshake, pre-ready buffer, relay

**Files:**
- Create: `voice/session.py`, `tests/fakes/voice.py`, `tests/unit/voice/test_session.py`

**Interfaces:**
- Consumes: `app.ports.logger.LoggerPort`, `tests.fakes.clock.FakeClock`, `tests.fakes.logger.RecordingLogger`.
- Produces (used by Tasks 3, 4, 6):
  - `upsample_16k_to_24k(frame: bytes) -> bytes`
  - `SessionConfig(segment="auto", idle_seconds=8.0, buffer_seconds=5.0, echo_tail_seconds=0.3)` frozen dataclass
  - Protocols: `Socket` (`async send(str|bytes)`, `async close()`, `__aiter__() -> AsyncIterator[str|bytes]`), `Speaker` (`play(bytes)`, `busy() -> bool`, `clear() -> int`), `Detector` (`__call__(bytes) -> bool`, `reset()`)
  - `VoiceSession(*, detector, connect: Callable[[], Awaitable[Socket]], speaker, clock: Callable[[], float], log: LoggerPort, config: SessionConfig)` with `state` property (`"idle" | "connecting" | "live"`), `async on_frame(frame: bytes) -> None`, `async run(mic: AsyncIterator[bytes]) -> None`.
  - Fakes: `FakeSocket` (`push(message)`, `end()`, `sent`, `closed`, `events()`, `audio()`), `FakeSpeaker` (`played`, `is_busy`, `cleared`, `played_ms`), `FakeDetector` (`wake_next`, `calls`, `resets`).

- [ ] **Step 1: Write the fakes**

`tests/fakes/voice.py`:

```python
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
        return [
            cast("dict[str, object]", json.loads(m)) for m in self.sent if isinstance(m, str)
        ]

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
```

- [ ] **Step 2: Write the failing tests**

`tests/unit/voice/test_session.py`:

```python
from __future__ import annotations

import asyncio

import numpy as np
import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.logger import RecordingLogger
from tests.fakes.voice import FakeDetector, FakeSocket, FakeSpeaker
from voice.session import SessionConfig, VoiceSession, upsample_16k_to_24k

FRAME = np.zeros(1280, dtype=np.int16).tobytes()  # 80 ms at 16 kHz


def tone(value: int) -> bytes:
    return np.full(1280, value, dtype=np.int16).tobytes()


def middle(chunk: bytes) -> int:
    return int(np.frombuffer(chunk, dtype=np.int16)[len(chunk) // 4])


async def settle() -> None:
    for _ in range(10):
        await asyncio.sleep(0)


class Rig:
    def __init__(
        self, config: SessionConfig | None = None, connect_error: Exception | None = None
    ) -> None:
        self.sockets: list[FakeSocket] = []
        self.connect_error = connect_error
        self.detector = FakeDetector()
        self.speaker = FakeSpeaker()
        self.clock = FakeClock()
        self.log = RecordingLogger()
        self.session = VoiceSession(
            detector=self.detector,
            connect=self._connect,
            speaker=self.speaker,
            clock=self.clock,
            log=self.log,
            config=config or SessionConfig(),
        )

    async def _connect(self) -> FakeSocket:
        if self.connect_error is not None:
            raise self.connect_error
        self.sockets.append(FakeSocket())
        return self.sockets[-1]

    @property
    def socket(self) -> FakeSocket:
        return self.sockets[-1]

    async def wake(self) -> None:
        self.detector.wake_next = True
        await self.session.on_frame(FRAME)
        await settle()

    async def go_live(self) -> None:
        await self.wake()
        self.socket.push({"type": "ready"})
        await settle()


def test_upsample_ratio_is_three_to_two() -> None:
    assert len(upsample_16k_to_24k(FRAME)) == 3840


async def test_idle_frames_only_reach_the_detector() -> None:
    rig = Rig()
    await rig.session.on_frame(FRAME)
    assert rig.detector.calls == 1
    assert rig.sockets == []
    assert rig.session.state == "idle"


async def test_wake_opens_the_socket_and_sends_start() -> None:
    rig = Rig(SessionConfig(segment="home"))
    await rig.wake()
    assert rig.session.state == "connecting"
    assert rig.socket.events() == [{"type": "start", "segment": "home"}]


async def test_audio_before_ready_is_buffered_then_flushed_in_order() -> None:
    rig = Rig()
    await rig.wake()
    for value in (100, 200, 300):
        await rig.session.on_frame(tone(value))
    assert rig.socket.audio() == []
    rig.socket.push({"type": "ready"})
    await settle()
    assert rig.session.state == "live"
    assert [middle(c) for c in rig.socket.audio()] == pytest.approx([100, 200, 300], rel=0.05)


async def test_buffer_keeps_only_the_latest_frames() -> None:
    rig = Rig(SessionConfig(buffer_seconds=0.16))  # two frames
    await rig.wake()
    for value in (100, 200, 300, 400):
        await rig.session.on_frame(tone(value))
    rig.socket.push({"type": "ready"})
    await settle()
    assert [middle(c) for c in rig.socket.audio()] == pytest.approx([300, 400], rel=0.05)


async def test_second_wake_while_connecting_is_ignored() -> None:
    rig = Rig()
    await rig.wake()
    rig.detector.wake_next = True
    await rig.session.on_frame(FRAME)
    await settle()
    assert len(rig.sockets) == 1
    assert rig.detector.calls == 1


async def test_binary_before_ready_is_not_played() -> None:
    rig = Rig()
    await rig.wake()
    rig.socket.push(b"\x01\x02")
    await settle()
    assert rig.speaker.played == []


async def test_live_frames_are_upsampled_and_sent() -> None:
    rig = Rig()
    await rig.go_live()
    await rig.session.on_frame(FRAME)
    assert [len(c) for c in rig.socket.audio()] == [3840]


async def test_odd_length_frame_is_dropped_without_crashing() -> None:
    rig = Rig()
    await rig.go_live()
    await rig.session.on_frame(b"\x00\x00\x00")
    assert rig.socket.audio() == []
    assert rig.session.state == "live"
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest tests/unit/voice/test_session.py --no-cov -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'voice.session'`.

- [ ] **Step 4: Implement**

`voice/session.py`:

```python
"""Wake word → live conversation state machine.

Hardware-free: the microphone frames, socket, speaker, detector and clock are injected.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, cast

import numpy as np
from scipy.signal import resample_poly

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from app.ports.logger import LoggerPort

FRAME_SECONDS = 0.08  # 1280 samples of PCM16 mono at 16 kHz

State = Literal["idle", "connecting", "live"]


class Socket(Protocol):
    async def send(self, message: str | bytes) -> None: ...
    async def close(self) -> None: ...
    def __aiter__(self) -> AsyncIterator[str | bytes]: ...


class Speaker(Protocol):
    def play(self, pcm: bytes) -> None: ...
    def busy(self) -> bool: ...
    def clear(self) -> int:
        """Drop queued audio; return the milliseconds of the current response already played."""
        ...


class Detector(Protocol):
    def __call__(self, frame: bytes) -> bool: ...
    def reset(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SessionConfig:
    segment: str = "auto"
    idle_seconds: float = 8.0
    buffer_seconds: float = 5.0
    echo_tail_seconds: float = 0.3


def upsample_16k_to_24k(frame: bytes) -> bytes:
    # ponytail: resampling per 80 ms frame leaves small edge artifacts; use a stateful
    # resampler if recognition suffers.
    samples = np.frombuffer(frame, dtype=np.int16)
    return np.clip(resample_poly(samples, 3, 2), -32768, 32767).astype(np.int16).tobytes()


class VoiceSession:
    def __init__(
        self,
        *,
        detector: Detector,
        connect: Callable[[], Awaitable[Socket]],
        speaker: Speaker,
        clock: Callable[[], float],
        log: LoggerPort,
        config: SessionConfig,
    ) -> None:
        self._detector = detector
        self._connect = connect
        self._speaker = speaker
        self._clock = clock
        self._log = log
        self._cfg = config
        self._state: State = "idle"
        self._buffer: deque[bytes] = deque(maxlen=max(1, round(config.buffer_seconds / FRAME_SECONDS)))
        self._ws: Socket | None = None
        self._link: asyncio.Task[None] | None = None
        self._last_activity = 0.0
        self._unmute_at = 0.0

    @property
    def state(self) -> State:
        return self._state

    async def run(self, mic: AsyncIterator[bytes]) -> None:
        try:
            async for frame in mic:
                await self.on_frame(frame)
        finally:
            if self._link is not None:
                self._link.cancel()
                await asyncio.gather(self._link, return_exceptions=True)

    async def on_frame(self, frame: bytes) -> None:
        if self._state == "idle":
            if self._detector(frame):
                self._open_link()
        elif self._state == "connecting":
            self._buffer.append(frame)
        else:
            await self._relay(frame)

    def _open_link(self) -> None:
        self._state = "connecting"
        self._buffer.clear()
        self._log.info("voice.wake")
        self._link = asyncio.create_task(self._serve())

    async def _serve(self) -> None:
        try:
            self._ws = await self._connect()
            await self._ws.send(json.dumps({"type": "start", "segment": self._cfg.segment}))
            async for message in self._ws:
                if await self._handle(message):
                    break
        except Exception as exc:  # any failure must end in IDLE, or the daemon stays deaf
            self._log.warning("voice.link_failed", error=type(exc).__name__)
        finally:
            await self._finish()

    async def _handle(self, message: str | bytes) -> bool:
        """Process one server message; True means the session is over."""
        self._last_activity = self._clock()
        if isinstance(message, bytes):
            return False
        event = cast("dict[str, object]", json.loads(message))
        if event.get("type") == "ready":
            await self._go_live()
        return False

    async def _go_live(self) -> None:
        self._last_activity = self._clock()
        # state flips only after the drain, so frames arriving meanwhile stay in order
        while self._buffer:
            await self._send(upsample_16k_to_24k(self._buffer.popleft()))
        self._state = "live"
        self._log.info("voice.live")

    async def _relay(self, frame: bytes) -> None:
        with contextlib.suppress(Exception):  # the receive loop sees a dead socket and ends us
            await self._send(upsample_16k_to_24k(frame))

    async def _send(self, message: str | bytes) -> None:
        assert self._ws is not None
        await self._ws.send(message)

    async def _finish(self) -> None:
        ws, self._ws = self._ws, None
        self._state = "idle"
        self._buffer.clear()
        self._unmute_at = 0.0
        self._speaker.clear()
        self._detector.reset()
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        self._log.info("voice.idle")
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/unit/voice/test_session.py --no-cov -v`
Expected: PASS (9 tests). If a `pytest.approx` ordering check fails on edge samples, print `middle(c)` — constant tones must land within 5 % in the middle of a 1920-sample chunk.

- [ ] **Step 6: Lint, types, commit**

```bash
ruff check voice tests && ruff format voice tests && pyright
git add voice/session.py tests/fakes/voice.py tests/unit/voice/test_session.py
git commit -m "feat(voice): add session state machine with wake, handshake and pre-ready buffer" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Playback, half-duplex mute, interrupt

**Files:**
- Modify: `voice/session.py` (`_handle`, `_relay`, new `_send_played`)
- Test: `tests/unit/voice/test_session.py` (append)

**Interfaces:**
- Consumes: Task 2 `VoiceSession`, `FakeSpeaker`, `Rig`.
- Produces: agent audio reaches `Speaker.play`; mic frames are withheld while `Speaker.busy()` and for `echo_tail_seconds` afterwards; `interrupt` → `Speaker.clear()` + `{"type":"played","audio_end_ms":N}`.

- [ ] **Step 1: Write the failing tests** (append to `test_session.py`)

```python
async def test_server_audio_is_played() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.push(b"\x01\x00" * 10)
    await settle()
    assert rig.speaker.played == [b"\x01\x00" * 10]


async def test_mic_is_muted_while_speaking_and_for_the_echo_tail() -> None:
    rig = Rig()
    await rig.go_live()
    rig.speaker.is_busy = True
    await rig.session.on_frame(FRAME)
    assert rig.socket.audio() == []
    rig.speaker.is_busy = False
    rig.clock.advance(0.1)
    await rig.session.on_frame(FRAME)  # inside the 0.3 s tail
    assert rig.socket.audio() == []
    rig.clock.advance(0.3)
    await rig.session.on_frame(FRAME)
    assert len(rig.socket.audio()) == 1


async def test_interrupt_flushes_playback_and_reports_played_ms() -> None:
    rig = Rig()
    await rig.go_live()
    rig.speaker.played_ms = 1234
    rig.socket.push({"type": "interrupt"})
    await settle()
    assert rig.speaker.cleared == 1
    assert {"type": "played", "audio_end_ms": 1234} in rig.socket.events()
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/voice/test_session.py --no-cov -v`
Expected: the 3 new tests FAIL (audio not played, frames still sent, no `played`).

- [ ] **Step 3: Implement**

In `voice/session.py`, replace `_handle` and `_relay`, and add `_send_played`:

```python
    async def _handle(self, message: str | bytes) -> bool:
        """Process one server message; True means the session is over."""
        self._last_activity = self._clock()
        if isinstance(message, bytes):
            if self._state == "live":
                self._speaker.play(message)
            return False
        event = cast("dict[str, object]", json.loads(message))
        kind = event.get("type")
        if kind == "ready":
            await self._go_live()
        elif kind == "interrupt":
            await self._send_played()
        return False

    async def _send_played(self) -> None:
        played_ms = self._speaker.clear()
        await self._send(json.dumps({"type": "played", "audio_end_ms": played_ms}))

    async def _relay(self, frame: bytes) -> None:
        now = self._clock()
        if self._speaker.busy():
            # ponytail: half-duplex, no barge-in; upgrade to AEC or a headset with hardware AEC
            self._unmute_at = now + self._cfg.echo_tail_seconds
            self._last_activity = now
            return
        if now < self._unmute_at:
            return
        with contextlib.suppress(Exception):  # the receive loop sees a dead socket and ends us
            await self._send(upsample_16k_to_24k(frame))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/voice/test_session.py --no-cov -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Lint, types, commit**

```bash
ruff check voice tests && ruff format voice tests && pyright
git add voice/session.py tests/unit/voice/test_session.py
git commit -m "feat(voice): play agent audio, mute mic while it speaks, honor interrupt" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Ending sessions — idle, server close, errors, failures, shutdown

**Files:**
- Modify: `voice/session.py` (`_handle`, `_relay`)
- Test: `tests/unit/voice/test_session.py` (append)

**Interfaces:**
- Consumes: Tasks 2–3.
- Produces: every way a session can end returns the machine to `idle` with the detector reset and the speaker cleared; the client closes after `idle_seconds` without activity.

- [ ] **Step 1: Write the failing tests** (append)

```python
async def test_idle_timeout_closes_the_link() -> None:
    rig = Rig()
    await rig.go_live()
    rig.clock.advance(9)
    await rig.session.on_frame(FRAME)
    await settle()
    assert rig.socket.closed
    assert rig.session.state == "idle"
    assert "voice.idle_close" in rig.log.names()


async def test_server_events_count_as_activity() -> None:
    rig = Rig()
    await rig.go_live()
    rig.clock.advance(7)
    rig.socket.push({"type": "transcript", "role": "user", "text": "ignored", "final": True})
    await settle()
    rig.clock.advance(7)
    await rig.session.on_frame(FRAME)
    await settle()
    assert not rig.socket.closed


async def test_long_agent_speech_is_not_idle_closed() -> None:
    rig = Rig()
    await rig.go_live()
    rig.speaker.is_busy = True
    for _ in range(300):  # 24 s of agent audio, longer than idle_seconds
        rig.clock.advance(0.08)
        await rig.session.on_frame(FRAME)
    rig.speaker.is_busy = False
    rig.clock.advance(0.31)
    await rig.session.on_frame(FRAME)
    await settle()
    assert not rig.socket.closed
    assert len(rig.socket.audio()) == 1


async def test_server_close_returns_to_idle_and_resets_the_detector() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.end()
    await settle()
    assert rig.session.state == "idle"
    assert rig.detector.resets == 1
    assert rig.speaker.cleared >= 1
    await rig.wake()  # a new wake word opens a fresh session
    assert len(rig.sockets) == 2


async def test_error_event_ends_the_session_and_logs_only_the_code() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.push({"type": "error", "code": "session_limit"})
    await settle()
    assert rig.socket.closed
    assert rig.session.state == "idle"
    assert ("warning", "voice.server_error", {"code": "session_limit"}) in rig.log.events


async def test_closed_event_ends_the_session() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.push({"type": "closed", "reason": "idle"})
    await settle()
    assert rig.session.state == "idle"


async def test_malformed_server_message_ends_the_session() -> None:
    rig = Rig()
    await rig.wake()
    rig.socket.push("not json")
    await settle()
    assert rig.session.state == "idle"
    assert rig.socket.closed


async def test_connect_failure_returns_to_idle_and_can_retry() -> None:
    rig = Rig(connect_error=OSError("refused"))
    await rig.wake()
    assert rig.session.state == "idle"
    assert ("warning", "voice.link_failed", {"error": "OSError"}) in rig.log.events
    rig.connect_error = None
    await rig.wake()
    assert len(rig.sockets) == 1


async def test_send_failure_on_a_dead_socket_does_not_crash_the_mic_loop() -> None:
    rig = Rig()
    await rig.go_live()
    rig.socket.closed = True  # peer vanished, receive loop has not noticed yet
    await rig.session.on_frame(FRAME)  # must not raise
    assert rig.socket.audio() == []


async def test_detector_is_not_called_while_live() -> None:
    rig = Rig()
    await rig.go_live()
    calls = rig.detector.calls
    await rig.session.on_frame(FRAME)
    assert rig.detector.calls == calls


async def test_run_closes_the_link_when_the_mic_ends() -> None:
    rig = Rig()
    rig.detector.wake_next = True

    async def mic() -> AsyncIterator[bytes]:
        yield FRAME
        await settle()

    await rig.session.run(mic())
    assert rig.socket.closed
    assert rig.session.state == "idle"
```

Also add at the top of the test file: `from collections.abc import AsyncIterator` under `if TYPE_CHECKING:` (with `from typing import TYPE_CHECKING`).

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/unit/voice/test_session.py --no-cov -v`
Expected: idle, error, closed tests FAIL; the others (server close, malformed, connect failure, send failure, detector, run) may already pass from Task 2. Confirm the failing ones fail for the stated reason.

- [ ] **Step 3: Implement**

In `voice/session.py` replace `_handle` and `_relay`:

```python
    async def _handle(self, message: str | bytes) -> bool:
        """Process one server message; True means the session is over."""
        self._last_activity = self._clock()
        if isinstance(message, bytes):
            if self._state == "live":
                self._speaker.play(message)
            return False
        event = cast("dict[str, object]", json.loads(message))
        kind = event.get("type")
        if kind == "ready":
            await self._go_live()
        elif kind == "interrupt":
            await self._send_played()
        elif kind == "error":
            self._log.warning("voice.server_error", code=event.get("code"))
            return True
        elif kind == "closed":
            self._log.info("voice.server_closed", reason=event.get("reason"))
            return True
        return False

    async def _relay(self, frame: bytes) -> None:
        now = self._clock()
        if self._speaker.busy():
            # ponytail: half-duplex, no barge-in; upgrade to AEC or a headset with hardware AEC
            self._unmute_at = now + self._cfg.echo_tail_seconds
            self._last_activity = now
            return
        if now < self._unmute_at:
            return
        if now - self._last_activity > self._cfg.idle_seconds:
            self._log.info("voice.idle_close")
            if self._ws is not None:
                with contextlib.suppress(Exception):
                    await self._ws.close()  # ends _serve's receive loop, which runs _finish
            return
        with contextlib.suppress(Exception):  # the receive loop sees a dead socket and ends us
            await self._send(upsample_16k_to_24k(frame))
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/unit/voice -v --no-cov`
Expected: PASS (all voice tests, ~28).

- [ ] **Step 5: Lint, types, commit**

```bash
ruff check voice tests && ruff format voice tests && pyright
git add voice/session.py tests/unit/voice/test_session.py
git commit -m "feat(voice): end sessions on idle, server close, errors and failures" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Wake-word wrapper (openWakeWord)

**Files:**
- Create: `voice/wake.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `voice.wake.WakeWord(model: str, threshold: float)` satisfying the `Detector` protocol: `__call__(frame: bytes) -> bool` (frame = 2560 bytes of PCM16 16 kHz) and `reset() -> None`.

No unit test: it wraps a third-party model (`voice/wake.py` is omitted from coverage). It is verified by hand below.

- [ ] **Step 1: Install openWakeWord without its tflite dependency**

```bash
pip install --no-deps openwakeword
pip install onnxruntime tqdm scikit-learn requests
python -c "import openwakeword; openwakeword.utils.download_models()"
```
Expected: the last command downloads the feature models and pretrained wake words (needs network once). If `pip install openwakeword` (with deps) works on the target Python, that is also fine; if the API below differs (`wakeword_models` argument, `predict`, `reset`), check the installed version's README and adapt only `voice/wake.py`.

- [ ] **Step 2: Implement**

`voice/wake.py`:

```python
"""openWakeWord behind the Detector protocol. Model wrapper, verified by hand."""

from __future__ import annotations

import numpy as np
from openwakeword.model import Model


class WakeWord:
    def __init__(self, model: str, threshold: float) -> None:
        self._model = Model(wakeword_models=[model], inference_framework="onnx")
        self._threshold = threshold

    def __call__(self, frame: bytes) -> bool:
        scores = self._model.predict(np.frombuffer(frame, dtype=np.int16))
        return any(score > self._threshold for score in scores.values())

    def reset(self) -> None:
        self._model.reset()
```

- [ ] **Step 3: Verify by hand with the stand-in model**

```bash
python - <<'EOF'
import sounddevice as sd
from voice.wake import WakeWord

wake = WakeWord("hey_jarvis", 0.5)
with sd.RawInputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1280) as mic:
    for _ in range(250):  # ~20 s
        data, _overflow = mic.read(1280)
        if wake(bytes(data)):
            print("WAKE")
EOF
```
Expected: say "hey jarvis" a few times → prints `WAKE` for each; silence and normal talk print nothing. (`print` is fine in this throwaway check, not in `voice/`.) If the input device rejects 16 kHz, note the error and jump to Task 7's device notes.

- [ ] **Step 4: Types and commit**

```bash
ruff check voice && ruff format voice && pyright
git add voice/wake.py
git commit -m "feat(voice): add openWakeWord detector wrapper" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Audio I/O, daemon wiring, end-to-end smoke

**Files:**
- Create: `voice/audio.py`, `voice/main.py`

**Interfaces:**
- Consumes: `VoiceSession`, `SessionConfig`, `Socket` (Task 2), `WakeWord` (Task 5), `load_voice_settings` (Task 1), `app.adapters.logging.structlog_logger.StructlogLogger/configure_logging`.
- Produces: `voice.audio.microphone_frames(device: str | None) -> AsyncIterator[bytes]` (80 ms PCM16 16 kHz frames); `voice.audio.Speaker(device)` context manager satisfying the `Speaker` protocol (24 kHz PCM16 output); `python -m voice.main`.

Hardware glue, verified by hand (`voice/audio.py` omitted from coverage).

- [ ] **Step 1: Implement audio I/O**

`voice/audio.py`:

```python
"""Microphone and speaker on the local sound card (PortAudio). Hardware glue, tested by hand."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

import sounddevice as sd

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

MIC_RATE = 16_000
SPEAKER_RATE = 24_000
FRAME_SAMPLES = 1280  # 80 ms at 16 kHz, the chunk openWakeWord expects
BYTES_PER_SECOND = SPEAKER_RATE * 2


def _device(name: str | None) -> int | str | None:
    return int(name) if name is not None and name.isdigit() else name


async def microphone_frames(device: str | None) -> AsyncIterator[bytes]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[bytes] = asyncio.Queue()

    def on_audio(indata: bytes, frames: int, time: object, status: sd.CallbackFlags) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

    # ponytail: unbounded queue, fine while the consumer drains it every 80 ms
    with sd.RawInputStream(
        samplerate=MIC_RATE,
        channels=1,
        dtype="int16",
        blocksize=FRAME_SAMPLES,
        device=_device(device),
        callback=on_audio,
    ):
        while True:
            yield await queue.get()


class Speaker:
    def __init__(self, device: str | None) -> None:
        self._buffer = bytearray()
        self._played_bytes = 0
        self._lock = threading.Lock()
        self._stream = sd.RawOutputStream(
            samplerate=SPEAKER_RATE,
            channels=1,
            dtype="int16",
            device=_device(device),
            callback=self._pull,
        )

    def __enter__(self) -> Speaker:
        self._stream.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stream.close()

    def play(self, pcm: bytes) -> None:
        with self._lock:
            if not self._buffer:
                # ponytail: a mid-response underrun also resets the count; pacing keeps the
                # buffer non-empty in practice, track per-response ids if truncation drifts
                self._played_bytes = 0
            self._buffer += pcm

    def busy(self) -> bool:
        with self._lock:
            return bool(self._buffer)

    def clear(self) -> int:
        with self._lock:
            self._buffer.clear()
            return self._played_bytes * 1000 // BYTES_PER_SECOND

    def _pull(self, outdata: memoryview, frames: int, time: object, status: sd.CallbackFlags) -> None:
        need = frames * 2
        with self._lock:
            chunk = bytes(self._buffer[:need])
            del self._buffer[:need]
            self._played_bytes += len(chunk)
        outdata[:] = chunk + bytes(need - len(chunk))
```

- [ ] **Step 2: Implement the daemon**

`voice/main.py`:

```python
"""Voice daemon: local wake word, then a live conversation over WS /live.

    python -m voice.main
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
import sys
import time
from typing import TYPE_CHECKING

import websockets

from app.adapters.logging.structlog_logger import StructlogLogger, configure_logging
from app.domain.exceptions import ConfigError
from voice.audio import Speaker, microphone_frames
from voice.config import load_voice_settings
from voice.session import SessionConfig, VoiceSession
from voice.wake import WakeWord

if TYPE_CHECKING:
    from voice.session import Socket


async def run() -> None:
    settings = load_voice_settings()
    configure_logging(settings.log_level, json=False)  # journald keeps stdout
    headers = {"Authorization": f"Bearer {settings.api_token.get_secret_value()}"}

    async def connect() -> Socket:
        return await websockets.connect(settings.url, additional_headers=headers)

    with Speaker(settings.output_device) as speaker:
        session = VoiceSession(
            detector=WakeWord(settings.wake_model, settings.threshold),
            connect=connect,
            speaker=speaker,
            clock=time.monotonic,
            log=StructlogLogger(),
            config=SessionConfig(segment=settings.segment, idle_seconds=settings.idle_seconds),
        )
        await session.run(microphone_frames(settings.input_device))


def main() -> None:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # systemd stop: unwind and release audio
    try:
        with contextlib.suppress(KeyboardInterrupt):
            asyncio.run(run())
    except ConfigError as exc:
        sys.exit(f"config error: {exc}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Types and lint**

```bash
ruff check voice && ruff format voice && pyright
```
Expected: clean (untyped `sounddevice`/`openwakeword` members may show `reportUnknown*` warnings; warnings are allowed, errors are not).

- [ ] **Step 4: Manual end-to-end smoke (needs the API running and a real `BYTE_OPENAI_API_KEY`)**

In `.env` add: `BYTE_VOICE_WAKE_MODEL=hey_jarvis`. Then:

```bash
docker compose up -d --build        # API on 127.0.0.1:8000 (or run uvicorn locally)
python -m voice.main
```
Checklist (write results in the commit message or tell the owner):
1. Log shows nothing while you talk without the wake word (IDLE).
2. Say "hey jarvis" then immediately a question → logs `voice.wake` → `voice.live`; the agent answers aloud.
3. Mic is muted while it speaks (the agent does not answer its own voice); after it ends you can ask a follow-up within ~8 s.
4. Stay silent ~8 s → `voice.idle_close` → `voice.idle`; saying "hey jarvis" again opens a new session.
5. Stop the API container mid-conversation → `voice.idle` (no crash); start it, wake again → works.
6. Bad `BYTE_API_TOKEN` (short) → exits with `config error: ...BYTE_API_TOKEN...`, no token in output.
7. If audio open fails with "Invalid sample rate": set `BYTE_VOICE_INPUT_DEVICE`/`BYTE_VOICE_OUTPUT_DEVICE` to a `plughw:` or `default` device (list with `python -m sounddevice`) and retry.

- [ ] **Step 5: Commit**

```bash
git add voice/audio.py voice/main.py
git commit -m "feat(voice): add audio I/O and daemon entrypoint" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Deploy on Ubuntu Server, docs, final gate

**Files:**
- Create: `deploy/byte-voice.service`, `docs/VOICE.md`
- Modify: `.env.example` (append), `CLAUDE.md` (Current state table, one row)

**Interfaces:**
- Consumes: everything above.
- Produces: an installable systemd service and the owner's guide for training the "Byte" model.

- [ ] **Step 1: Write the unit**

`deploy/byte-voice.service`:

```ini
[Unit]
Description=Byte voice client (wake word + live conversation)
After=network-online.target docker.service sound.target
Wants=network-online.target

[Service]
Type=simple
User=byte
SupplementaryGroups=audio
WorkingDirectory=/opt/byte
EnvironmentFile=/opt/byte/.env
ExecStart=/opt/byte/.venv/bin/python -m voice.main
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Append to `.env.example`** (names only, empty values)

```
# Voice client (voice/)
BYTE_VOICE_WAKE_MODEL=
BYTE_VOICE_URL=
BYTE_VOICE_THRESHOLD=
BYTE_VOICE_IDLE_SECONDS=
BYTE_VOICE_SEGMENT=
BYTE_VOICE_INPUT_DEVICE=
BYTE_VOICE_OUTPUT_DEVICE=
```

- [ ] **Step 3: Write `docs/VOICE.md`** with these sections (full prose, in English):

1. **What it is**: the daemon, one paragraph, link to the spec.
2. **Install on Ubuntu Server**: `sudo apt install libportaudio2 alsa-utils python3.12-venv`; create user `byte`, `sudo usermod -aG audio byte`; clone to `/opt/byte`; `python3.12 -m venv .venv`; `.venv/bin/pip install -e ".[voice]"`; `.venv/bin/pip install --no-deps openwakeword && .venv/bin/pip install tqdm scikit-learn requests`; `.venv/bin/python -c "import openwakeword; openwakeword.utils.download_models()"`; copy the unit to `/etc/systemd/system/`, `sudo systemctl daemon-reload && sudo systemctl enable --now byte-voice`; logs with `journalctl -u byte-voice -f`. Note: voice dependencies are not in the lock file used by the Docker image.
3. **Choosing audio devices**: `arecord -l`, `aplay -l`, `python -m sounddevice`; set `BYTE_VOICE_INPUT_DEVICE`/`OUTPUT_DEVICE` (index or name). Built-in codecs often cannot capture at 16 kHz on raw `hw:` devices: use a `plughw:CARD=...,DEV=0` name or `default`. Built-in mic + speaker: half-duplex means no interrupting the agent; a USB speakerphone/headset with hardware echo cancellation is the planned upgrade.
4. **Training the "Byte" wake word**: use openWakeWord's automatic training notebook (`notebooks/automatic_model_training.ipynb` in the openWakeWord repository, run on Colab). Set the target phrase to `byte`; also train/test spelling variants that match pt-BR pronunciation (e.g. `baiti`, `bait`) and compare; the notebook outputs an `.onnx` file: copy it to `/opt/byte/models/byte.onnx` and set `BYTE_VOICE_WAKE_MODEL=/opt/byte/models/byte.onnx`. Optional: record 20–30 real samples of your own voice and train a custom verifier model (see the openWakeWord README) to cut false triggers. Check the repository README for current notebook and API names before following these steps.
5. **Tuning**: `BYTE_VOICE_THRESHOLD` (default 0.5): raise it if it triggers on TV/conversation, lower it if it misses you. Keep a one-day tally of false triggers and misses before judging the model.
6. **Troubleshooting**: "Invalid sample rate" → device note above; `config error` at start → check names in the message; no sound out → `aplay` test and the `audio` group; service restarts in a loop → `journalctl -u byte-voice`.

- [ ] **Step 4: Update `CLAUDE.md` Current state table** — add one row after "TLS, LAN exposure…":

```
| Voice client (`voice/`): wake word "Byte", `/live` over the laptop mic and speaker | done (Spec 2) |
```
Only flip it to "done" after Step 5 is green and the Task 6 manual checklist passed on the laptop; until then write `in progress`.

- [ ] **Step 5: Final gate**

```bash
ruff check . && ruff format --check . && pyright && pytest
```
Expected: all three green; coverage ≥ 80 % with `voice/` included.

- [ ] **Step 6: Commit**

```bash
git add deploy docs/VOICE.md .env.example CLAUDE.md
git commit -m "docs(voice): add systemd unit, setup guide and wake-word training notes" -m "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:** §3 decisions → Tasks 1, 5, 6, 7 (onnx, custom model path, host systemd, loopback URL default, half-duplex with `ponytail:`, callable-like detector). §4 components → File Structure and Tasks 1–6; extra `voice` → Task 1; system packages/audio group → Task 7. §5 states, buffer bound, upsample, half-duplex + tail, `interrupt`/`played`, idle close, server close, no reconnect, `error` → Tasks 2–4 (each has a test). §6 config → Task 1 (`BYTE_VOICE_*`, token ≥32, model file check). §7 security/logging → Global Constraints; tests assert logs carry only `code`/`error` names. §8 tests → Tasks 1–4; manual checklist → Task 6. §9 open items → Task 7 docs (training, device checks).

**Placeholders:** none; the docs task lists the concrete content of each section instead of "write docs".

**Type consistency:** `Detector`/`Speaker`/`Socket` protocols (Task 2) match `WakeWord` (Task 5), `audio.Speaker` (Task 6), and the fakes. `SessionConfig` fields used in Task 6 (`segment`, `idle_seconds`) exist in Task 2. `VoiceSession.on_frame/run/state` names are used consistently in tests.

**Known risks to watch while executing:** openWakeWord's install/API on Python 3.12 (Task 5 step 1); `pytest.approx` on resampled constant tones (Task 2 step 5); ALSA 16 kHz capture on the laptop (Task 6 step 4); pt-BR accuracy of the trained "Byte" model (Task 7 docs).
