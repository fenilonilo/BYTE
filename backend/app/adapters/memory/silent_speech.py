from __future__ import annotations

from app.ports.speech import SpeechPort


class SilentSpeech(SpeechPort):
    """No voice model configured: reminders arrive as a beep with no words."""

    async def synthesize(self, text: str) -> bytes:
        return b""
