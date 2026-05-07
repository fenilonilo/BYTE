from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.repository import RepositoryPort

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class InMemoryRepository(RepositoryPort):
    """Cycle 1 stub. Replace with aiosqlite adapter in Cycle 2."""

    def __init__(self) -> None:
        self._store: dict[str, Conversation] = {}

    async def save(self, conversation: Conversation) -> None:
        self._store[conversation.id] = conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._store.get(conversation_id)
