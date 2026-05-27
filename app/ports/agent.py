from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities import AgentResponse, Conversation


class AgentPort(ABC):
    @abstractmethod
    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse: ...
