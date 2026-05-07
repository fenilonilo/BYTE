from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class LLMPort(ABC):
    @abstractmethod
    async def complete(self, prompt: str, conversation: Conversation) -> str: ...
