from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.llm import LLMPort

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class StubLLM(LLMPort):
    """Cycle 1 stub. Returns a fixed echo — replace with real LLM adapter in Cycle 2."""

    async def complete(self, prompt: str, conversation: Conversation) -> str:
        return f"[stub] Echo: {prompt}"
