from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

type ClientFrame = bytes | Mapping[str, object]


class LiveTransport(ABC):
    """The client side of a live session (a WebSocket in production, a fake in tests).

    Audio is opaque `bytes`; control messages are plain mappings."""

    @abstractmethod
    def incoming(self) -> AsyncIterator[ClientFrame]:
        """Frames from the client. The iterator ends when the client goes away."""

    @abstractmethod
    async def send_audio(self, data: bytes) -> None: ...

    @abstractmethod
    async def send_event(self, event: Mapping[str, object]) -> None: ...
