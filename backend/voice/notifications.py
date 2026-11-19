"""Always-open link to WS /ws/notifications: Byte speaks first.

A reminder is played once; an alarm rings until the wake word stops it. No model is involved:
the server sends ready-made speech, the device plays it and acks.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, cast

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from app.ports.logger import LoggerPort
    from voice.session import Socket, Speaker

RATE = 24_000
ALARM = "alarme"
RETRY_SECONDS = 5.0
RING_PAUSE_SECONDS = 1.5
POLL_SECONDS = 0.1


def _tone(freq: float, seconds: float, volume: float = 0.3) -> bytes:
    t = np.arange(int(RATE * seconds)) / RATE
    return (np.sin(2 * np.pi * freq * t) * volume * 32767).astype(np.int16).tobytes()


def _silence(seconds: float) -> bytes:
    return bytes(int(RATE * seconds) * 2)


CHIME = _tone(660, 0.15) + _tone(880, 0.2) + _silence(0.2)
BEEPS = (_tone(880, 0.2) + _silence(0.1)) * 3 + _silence(0.3)


class Notifier:
    def __init__(
        self,
        *,
        connect: Callable[[], Awaitable[Socket]],
        speaker: Speaker,
        log: LoggerPort,
        idle: Callable[[], bool],
        clock: Callable[[], float],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        ring_seconds: float = 300.0,
    ) -> None:
        self._connect = connect
        self._speaker = speaker
        self._log = log
        self._idle = idle
        self._clock = clock
        self._sleep = sleep
        self._ring_seconds = ring_seconds
        self._playing = False
        self._stopped = False

    def stop(self) -> bool:
        """The wake word was heard: silence a playing reminder or alarm. True if one was."""
        if not self._playing:
            return False
        self._stopped = True
        self._speaker.clear()
        return True

    async def run(self) -> None:
        while True:
            try:
                await self._serve(await self._connect())
            except Exception as exc:  # any failure: wait and reconnect, never give up
                self._log.warning("voice.notify_link_failed", error=type(exc).__name__)
            # ponytail: a fixed retry; two daemons on one token would take turns every 5 s
            await self._sleep(RETRY_SECONDS)

    async def _serve(self, ws: Socket) -> None:
        self._log.info("voice.notify_linked")
        header: dict[str, object] | None = None
        async for message in ws:
            if isinstance(message, str):
                event = cast("dict[str, object]", json.loads(message))
                header = event if event.get("type") == "reminder" else None
            elif header is not None:
                await self._play(header.get("kind") == ALARM, message)
                await ws.send(json.dumps({"type": "ack", "id": header.get("id")}))
                header = None

    async def _play(self, alarm: bool, speech: bytes) -> None:
        while not self._idle():  # never talk over a live conversation
            await self._sleep(POLL_SECONDS)
        self._playing, self._stopped = True, False
        try:
            if not alarm:
                self._speaker.play(CHIME + speech)
                await self._drain()
                return
            # safety cap: an alarm nobody stops must not ring all day
            deadline = self._clock() + self._ring_seconds
            while not self._stopped and self._clock() < deadline:
                self._speaker.play(BEEPS + speech)
                await self._drain()
                await self._sleep(RING_PAUSE_SECONDS)
            self._log.info("voice.alarm_done", stopped=self._stopped)
        finally:
            self._playing = False

    async def _drain(self) -> None:
        while self._speaker.busy() and not self._stopped:
            await self._sleep(POLL_SECONDS)
