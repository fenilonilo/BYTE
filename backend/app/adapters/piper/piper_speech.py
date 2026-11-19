from __future__ import annotations

import asyncio

import numpy as np
from piper import PiperVoice

from app.domain.exceptions import SpeechError
from app.ports.speech import SpeechPort

RATE = 24_000  # the live audio contract


def resample(pcm: bytes, rate: int) -> bytes:
    """PCM16 mono at `rate` -> 24 kHz."""
    # ponytail: linear interpolation, fine for speech; resample_poly if it ever sounds harsh
    samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32)
    if rate == RATE or samples.size == 0:
        return pcm
    count = round(samples.size * RATE / rate)
    out = np.interp(np.linspace(0, samples.size - 1, count), np.arange(samples.size), samples)
    return out.astype(np.int16).tobytes()


class PiperSpeech(SpeechPort):
    """Local neural TTS on the CPU: natural pt-BR voice, no tokens, no network."""

    def __init__(self, model_path: str) -> None:
        try:
            self._voice = PiperVoice.load(model_path)
        except Exception as exc:  # any load failure means no usable voice
            raise SpeechError("piper voice failed to load") from exc

    async def synthesize(self, text: str) -> bytes:
        try:
            return await asyncio.to_thread(self._render, text)
        except Exception as exc:
            raise SpeechError("piper synthesis failed") from exc

    def _render(self, text: str) -> bytes:
        chunks = list(self._voice.synthesize(text))
        if not chunks:
            return b""
        pcm = b"".join(c.audio_int16_bytes for c in chunks)
        return resample(pcm, chunks[0].sample_rate)
