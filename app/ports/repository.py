from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import Conversation


class RepositoryPort(ABC):
    @abstractmethod
    async def save(self, conversation: Conversation) -> None: ...

    @abstractmethod
    async def get(self, conversation_id: str) -> Conversation | None: ...
