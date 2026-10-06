from __future__ import annotations

import asyncio
import os

import pytest
from google import genai

from app.adapters.gemini.live_session import GeminiLiveSessionAdapter
from app.domain.live import AssistantAudio, LiveError, ResponseDone

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("BYTE_GEMINI_API_KEY"), reason="needs BYTE_GEMINI_API_KEY"
    ),
]

MODEL = os.environ.get("BYTE_GEMINI_LIVE_MODEL", "gemini-3.1-flash-live-preview")
SILENCE_100MS = bytes(4800)  # PCM16 mono 24 kHz


async def test_the_provider_accepts_the_session_and_a_silent_stream() -> None:
    """Connects, streams silence and closes: proves auth, model id and config are accepted."""
    client = genai.Client(api_key=os.environ["BYTE_GEMINI_API_KEY"])
    session = await GeminiLiveSessionAdapter(client, MODEL).open("Diga apenas: olá.", [])
    try:
        for _ in range(10):
            await session.send_audio(SILENCE_100MS)
        try:
            async with asyncio.timeout(5):
                async for event in session.events():
                    assert not isinstance(event, LiveError), event
                    if isinstance(event, AssistantAudio | ResponseDone):
                        break
        except TimeoutError:
            pass  # silence may legitimately produce no response
    finally:
        await session.close()
