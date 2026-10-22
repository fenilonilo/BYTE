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
        interrupt: Callable[[], bool] = lambda: False,
    ) -> None:
        self._detector = detector
        self._interrupt = interrupt
        self._connect = connect
        self._speaker = speaker
        self._clock = clock
        self._log = log
        self._cfg = config
        self._state: State = "idle"
        self._buffer: deque[bytes] = deque(
            maxlen=max(1, round(config.buffer_seconds / FRAME_SECONDS))
        )
        self._ws: Socket | None = None
        self._link: asyncio.Task[None] | None = None
        self._last_activity = 0.0
        self._unmute_at = 0.0
        self._idle_armed = False

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
            if not self._detector(frame):
                return
            if self._interrupt():  # the wake word stopped an alarm: no conversation, no tokens
                self._detector.reset()
            else:
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
            fields: dict[str, str | int] = {"error": type(exc).__name__}
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if isinstance(status, int):
                fields["status"] = status
            self._log.warning("voice.link_failed", **fields)
        finally:
            await self._finish()

    async def _handle(self, message: str | bytes) -> bool:
        """Process one server message; True means the session is over."""
        self._last_activity = self._clock()
        if isinstance(message, bytes):
            self._idle_armed = False
            if self._state == "live":
                self._speaker.play(message)
            return False
        event = cast("dict[str, object]", json.loads(message))
        kind = event.get("type")
        if kind == "ready":
            await self._go_live()
        elif kind == "interrupt":
            await self._send_played()
        elif kind == "turn_done":
            self._idle_armed = True
        elif kind == "transcript" and event.get("role") == "user":
            self._idle_armed = False
        elif kind == "error":
            self._log.warning("voice.server_error", code=event.get("code"))
            return True
        elif kind == "closed":
            self._log.info("voice.server_closed", reason=event.get("reason"))
            return True
        return False

    async def _go_live(self) -> None:
        self._last_activity = self._clock()
        # state flips only after the drain, so frames arriving meanwhile stay in order
        while self._buffer:
            await self._send(upsample_16k_to_24k(self._buffer.popleft()))
        self._state = "live"
        self._log.info("voice.live")

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
        # ponytail: no local VAD, so a user utterance that starts after a turn and runs past
        # idle_seconds is cut; raise BYTE_VOICE_IDLE_SECONDS or add an energy VAD if that bites
        if self._idle_armed and now - self._last_activity > self._cfg.idle_seconds:
            self._idle_armed = False
            self._log.info("voice.idle_close")
            if self._ws is not None:
                with contextlib.suppress(Exception):
                    await self._ws.close()  # ends _serve's receive loop, which runs _finish
            return
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
        self._idle_armed = False
        self._speaker.clear()
        self._detector.reset()
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        self._log.info("voice.idle")
