# app/adapters/repository/in_memory_repository.py
from __future__ import annotations

from app.domain.entities import Conversation
from app.ports.repository import RepositoryPort


class InMemoryRepository(RepositoryPort):
    """Cycle 1 stub. Replace with aiosqlite adapter in Cycle 2."""

    def __init__(self) -> None:
        self._store: dict[str, Conversation] = {}

    async def save(self, conversation: Conversation) -> None:
        self._store[conversation.id] = conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._store.get(conversation_id)
