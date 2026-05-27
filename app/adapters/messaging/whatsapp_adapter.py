from __future__ import annotations

import asyncio
import random
from typing import TYPE_CHECKING

from app.ports.messaging import MessagingPort

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.adapters.messaging.evolution_client import EvolutionClient
    from app.domain.entities import IncomingMessage, OutgoingMessage

# Average chars per second for human typing (~200 wpm)
_CHARS_PER_SEC = 40
_MIN_TYPING_SECS = 1.5
_MAX_TYPING_SECS = 8.0


class WhatsappAdapter(MessagingPort):
    def __init__(self, client: EvolutionClient) -> None:
        self._client = client

    async def send(self, message: OutgoingMessage) -> None:
        text = message.content
        recipient = message.recipient

        # Simulate reading delay before starting to type
        await asyncio.sleep(random.uniform(0.5, 2.0))  # noqa: S311

        await self._client.send_presence(recipient, "composing")

        # Typing duration proportional to message length
        typing_secs = max(_MIN_TYPING_SECS, min(_MAX_TYPING_SECS, len(text) / _CHARS_PER_SEC))
        # Add small jitter so it never feels mechanical
        typing_secs += random.uniform(-0.3, 0.5)  # noqa: S311
        await asyncio.sleep(typing_secs)

        await self._client.send_text(recipient, text)

        # Signal stop typing (best-effort)
        await self._client.send_presence(recipient, "paused")

    def receive(self) -> AsyncIterator[IncomingMessage]:  # type: ignore[override]
        raise NotImplementedError("WhatsApp channel uses webhooks — polling not supported")
