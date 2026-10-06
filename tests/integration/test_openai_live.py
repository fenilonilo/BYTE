from __future__ import annotations

import asyncio
import os

import pytest
from openai import AsyncOpenAI

from app.adapters.openai.live_session import OpenAILiveSessionAdapter
from app.domain.live import AssistantAudio, LiveError, ResponseDone

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("BYTE_OPENAI_API_KEY"), reason="needs BYTE_OPENAI_API_KEY"
    ),
]

MODEL = os.environ.get("BYTE_LIVE_MODEL", "gpt-realtime-2.1-mini")


async def test_the_provider_session_speaks_when_asked() -> None:
    client = AsyncOpenAI(api_key=os.environ["BYTE_OPENAI_API_KEY"])
    session = await OpenAILiveSessionAdapter(client, MODEL).open("Diga apenas: olá.", [])
    audio_bytes = 0
    try:
        await session.request_response()
        async with asyncio.timeout(30):
            async for event in session.events():
                assert not isinstance(event, LiveError), event
                if isinstance(event, AssistantAudio):
                    audio_bytes += len(event.data)
                if isinstance(event, ResponseDone):
                    break
    finally:
        await session.close()
    assert audio_bytes > 0
