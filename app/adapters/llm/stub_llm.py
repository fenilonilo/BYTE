# app/adapters/llm/stub_llm.py
from __future__ import annotations

from app.domain.entities import Conversation
from app.ports.llm import LLMPort


class StubLLM(LLMPort):
    """Cycle 1 stub. Returns a fixed echo — replace with real LLM adapter in Cycle 2."""

    async def complete(self, prompt: str, conversation: Conversation) -> str:
        return f"[stub] Echo: {prompt}"
