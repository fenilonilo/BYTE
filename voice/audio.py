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

    def _pull(
        self, outdata: memoryview, frames: int, time: object, status: sd.CallbackFlags
    ) -> None:
        need = frames * 2
        with self._lock:
            chunk = bytes(self._buffer[:need])
            del self._buffer[:need]
            self._played_bytes += len(chunk)
        outdata[:] = chunk + bytes(need - len(chunk))
