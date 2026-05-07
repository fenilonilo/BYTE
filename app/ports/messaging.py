from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.domain.entities import IncomingMessage, OutgoingMessage


class MessagingPort(ABC):
    @abstractmethod
    async def send(self, message: OutgoingMessage) -> None: ...

    @abstractmethod
    def receive(self) -> AsyncIterator[IncomingMessage]: ...
