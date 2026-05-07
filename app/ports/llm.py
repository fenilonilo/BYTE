from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import Conversation


class LLMPort(ABC):
    @abstractmethod
    async def complete(self, prompt: str, conversation: Conversation) -> str: ...
