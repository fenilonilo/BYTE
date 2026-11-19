from __future__ import annotations

from abc import ABC, abstractmethod


class SpeechPort(ABC):
    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """PCM16 mono 24 kHz, the live audio format. Raises SpeechError on failure."""
