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
        self._buffer: deque[bytes] = deque(
            maxlen=max(1, round(config.buffer_seconds / FRAME_SECONDS))
        )
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
