"""Audio heard just before each wake, kept on this machine to train and check the wake word."""

from __future__ import annotations

import wave
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from app.ports.logger import LoggerPort

MIC_RATE = 16_000


class ClipStore:
    """Writes PCM16 mono 16 kHz WAV files and keeps only the newest `keep` of them."""

    def __init__(
        self, directory: Path, *, keep: int, log: LoggerPort, now: Callable[[], datetime]
    ) -> None:
        self._keep = keep
        self._log = log
        self._now = now
        self._dir: Path | None = directory
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:  # a read-only disk must not stop the wake word
            self._disable(exc)

    def save(self, pcm: bytes, score: float) -> str | None:
        """Store one clip; return its file name, or None when clips are off or the write failed."""
        if self._dir is None:
            return None
        name = f"{self._now():%Y%m%dT%H%M%SZ}_{score:.2f}.wav"
        try:
            with wave.open(str(self._dir / name), "wb") as clip:
                clip.setnchannels(1)
                clip.setsampwidth(2)
                clip.setframerate(MIC_RATE)
                clip.writeframes(pcm)
            for old in sorted(self._dir.glob("*.wav"))[: -self._keep]:
                old.unlink(missing_ok=True)
        except OSError as exc:
            self._log.warning("voice.clip_failed", error=type(exc).__name__)
            return None
        return name

    def _disable(self, exc: OSError) -> None:
        self._dir = None
        self._log.warning("voice.clips_disabled", error=type(exc).__name__)
