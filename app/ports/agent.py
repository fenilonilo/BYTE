from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class AgentPort(ABC):
    """One agent, one segment. The adapter owns the framework (Agno) and the model."""

    @abstractmethod
    async def run(self, message: str, conversation: Conversation) -> str: ...
