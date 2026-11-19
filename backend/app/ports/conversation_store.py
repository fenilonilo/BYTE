from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities import Message


class ConversationStorePort(ABC):
    @abstractmethod
    async def recent(self, conversation_id: str, limit: int) -> tuple[Message, ...]:
        """Last `limit` messages, oldest first. Empty for an unknown conversation."""

    @abstractmethod
    async def append(self, conversation_id: str, messages: Sequence[Message]) -> None:
        """Atomically add whole messages; creates the conversation if it is unknown."""
