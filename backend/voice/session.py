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

from voice.notifications import WAKE_CHIME

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from app.ports.logger import LoggerPort

FRAME_SECONDS = 0.08  # 1280 samples of PCM16 mono at 16 kHz
AGENT_BYTES_PER_SECOND = 24_000 * 2

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
    def __call__(self, frame: bytes) -> float:
        """The wake word score of this frame, 0..1."""
        ...

    def reset(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """Defaults switch every guard off; VoiceSettings holds the values the daemon runs with."""

    segment: str = "auto"
    idle_seconds: float = 8.0
    buffer_seconds: float = 5.0
    echo_tail_seconds: float = 0.3
    threshold: float = 0.5
    patience: int = 1  # consecutive frames over the threshold before a wake
    cooldown_seconds: float = 0.0  # deaf after a session, so its tail cannot wake us again
    no_speech_seconds: float = 0.0  # close a session nobody speaks in; 0 = never
    speech_rms: int = 300  # mic level (PCM16 RMS) that counts as someone speaking
    preroll_seconds: float = 0.0  # audio before each wake handed to save_clip; 0 = none


def upsample_16k_to_24k(frame: bytes) -> bytes:
    # ponytail: resampling per 80 ms frame leaves small edge artifacts; use a stateful
    # resampler if recognition suffers.
    samples = np.frombuffer(frame, dtype=np.int16)
    return np.clip(resample_poly(samples, 3, 2), -32768, 32767).astype(np.int16).tobytes()


def rms(frame: bytes) -> int:
    usable = len(frame) - len(frame) % 2  # a torn frame must not crash the mic loop
    samples = np.frombuffer(frame[:usable], dtype=np.int16).astype(np.float64)
    return round(float(np.sqrt(np.mean(samples**2)))) if samples.size else 0


@dataclass(slots=True)
class _Stats:
    """Content-free numbers about one session, for voice.session_end."""

    started: float = 0.0
    live_at: float = 0.0
    reason: str = "socket_closed"
    user_turns: int = 0
    agent_bytes: int = 0
    heard_speech: bool = False
    peak_rms: int = 0


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
        save_clip: Callable[[bytes, float], str | None] = lambda _pcm, _score: None,
    ) -> None:
        self._detector = detector
        self._interrupt = interrupt
        self._save_clip = save_clip
        self._connect = connect
        self._speaker = speaker
        self._clock = clock
        self._log = log
        self._cfg = config
        self._state: State = "idle"
        self._buffer: deque[bytes] = deque(
            maxlen=max(1, round(config.buffer_seconds / FRAME_SECONDS))
        )
        self._preroll: deque[bytes] = deque(maxlen=round(config.preroll_seconds / FRAME_SECONDS))
        self._ws: Socket | None = None
        self._link: asyncio.Task[None] | None = None
        self._last_activity = 0.0
        self._unmute_at = 0.0
        self._idle_armed = False
        self._deaf_until = 0.0
        self._hits = 0
        self._peak = 0.0
        self._stats = _Stats()

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
            if self._preroll.maxlen:
                self._preroll.append(frame)
            if not self._heard_wake(self._detector(frame)):
                return
            if self._interrupt():  # the wake word stopped an alarm: no conversation, no tokens
                self._detector.reset()
                self._deaf_until = self._clock() + self._cfg.cooldown_seconds
            else:
                self._open_link()
        elif self._state == "connecting":
            if self._muted():  # the wake chime must not reach the model
                return
            self._buffer.append(frame)
        else:
            await self._relay(frame)

    def _heard_wake(self, score: float) -> bool:
        """True once `patience` frames in a row score over the threshold, outside the cooldown."""
        if self._clock() < self._deaf_until:
            self._hits = 0
            return False
        if score > self._cfg.threshold:
            self._hits += 1
            self._peak = max(self._peak, score)
            return self._hits >= self._cfg.patience
        if self._hits:  # a near miss: how close it came tells whether the threshold is right
            self._log.info("voice.wake_rejected", frames=self._hits, score=round(self._peak, 3))
        self._hits = 0
        self._peak = 0.0
        return False

    def _open_link(self) -> None:
        self._state = "connecting"
        self._buffer.clear()
        self._stats = _Stats(started=self._clock())
        fields: dict[str, object] = {"score": round(self._peak, 3), "frames": self._hits}
        if self._preroll:
            clip = self._save_clip(b"".join(self._preroll), self._peak)
            if clip is not None:
                fields["clip"] = clip
        self._hits = 0
        self._peak = 0.0
        self._log.info("voice.wake", **fields)
        self._speaker.play(WAKE_CHIME)
        self._link = asyncio.create_task(self._serve())

    async def _serve(self) -> None:
        try:
            self._ws = await self._connect()
            await self._ws.send(json.dumps({"type": "start", "segment": self._cfg.segment}))
            async for message in self._ws:
                if await self._handle(message):
                    break
        except Exception as exc:  # any failure must end in IDLE, or the daemon stays deaf
            self._stats.reason = "link_failed"
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
                self._stats.agent_bytes += len(message)
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
            self._stats.heard_speech = True
            if event.get("final", True):
                self._stats.user_turns += 1
        elif kind == "error":
            self._stats.reason = "server_error"
            self._log.warning("voice.server_error", code=event.get("code"))
            return True
        elif kind == "closed":
            self._stats.reason = f"server_{event.get('reason')}"
            self._log.info("voice.server_closed", reason=event.get("reason"))
            return True
        return False

    async def _go_live(self) -> None:
        self._last_activity = self._clock()
        # state flips only after the drain, so frames arriving meanwhile stay in order
        while self._buffer:
            frame = self._buffer.popleft()
            self._hear(frame)
            await self._send(upsample_16k_to_24k(frame))
        self._state = "live"
        self._stats.live_at = self._clock()
        self._log.info(
            "voice.live", connect_ms=round((self._stats.live_at - self._stats.started) * 1000)
        )

    async def _send_played(self) -> None:
        played_ms = self._speaker.clear()
        await self._send(json.dumps({"type": "played", "audio_end_ms": played_ms}))

    async def _relay(self, frame: bytes) -> None:
        now = self._clock()
        if self._muted():
            # ponytail: half-duplex, no barge-in; upgrade to AEC or a headset with hardware AEC
            return
        self._hear(frame)
        if self._nobody_spoke(now):
            return await self._close("no_speech")
        # ponytail: no local VAD, so a user utterance that starts after a turn and runs past
        # idle_seconds is cut; raise BYTE_VOICE_IDLE_SECONDS or add an energy VAD if that bites
        if self._idle_armed and now - self._last_activity > self._cfg.idle_seconds:
            self._idle_armed = False
            self._log.info("voice.idle_close")
            return await self._close("idle_close")
        with contextlib.suppress(Exception):  # the receive loop sees a dead socket and ends us
            await self._send(upsample_16k_to_24k(frame))

    def _hear(self, frame: bytes) -> None:
        level = rms(frame)
        self._stats.peak_rms = max(self._stats.peak_rms, level)
        if level >= self._cfg.speech_rms:
            self._stats.heard_speech = True

    def _nobody_spoke(self, now: float) -> bool:
        """A wake followed by silence: the wake word was a false alarm."""
        return (
            self._cfg.no_speech_seconds > 0
            and not self._stats.heard_speech
            and self._stats.agent_bytes == 0
            and now - self._stats.live_at > self._cfg.no_speech_seconds
        )

    async def _close(self, reason: str) -> None:
        self._stats.reason = reason
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()  # ends _serve's receive loop, which runs _finish

    def _muted(self) -> bool:
        """True while our own speaker plays, and for the echo tail after it."""
        now = self._clock()
        if self._speaker.busy():
            self._unmute_at = now + self._cfg.echo_tail_seconds
            self._last_activity = now
            return True
        return now < self._unmute_at

    async def _send(self, message: str | bytes) -> None:
        assert self._ws is not None
        await self._ws.send(message)

    async def _finish(self) -> None:
        ws, self._ws = self._ws, None
        self._state = "idle"
        self._buffer.clear()
        self._preroll.clear()  # the next clip must hold only audio heard while waiting
        self._unmute_at = 0.0
        self._idle_armed = False
        self._speaker.clear()
        self._detector.reset()
        self._deaf_until = self._clock() + self._cfg.cooldown_seconds
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        s = self._stats
        self._log.info(
            "voice.session_end",
            reason=s.reason,
            seconds=round(self._clock() - s.started, 1),
            user_turns=s.user_turns,
            agent_seconds=round(s.agent_bytes / AGENT_BYTES_PER_SECOND, 1),
            heard_speech=s.heard_speech,
            peak_rms=s.peak_rms,
        )
        self._log.info("voice.idle")
