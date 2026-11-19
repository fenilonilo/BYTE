from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from app.domain.live import LiveEvent
    from app.domain.tools import ToolResult, ToolSpec


class LiveSession(ABC):
    """One open speech-to-speech conversation with a provider. Audio is opaque bytes."""

    @abstractmethod
    async def send_audio(self, data: bytes) -> None: ...

    @abstractmethod
    def events(self) -> AsyncIterator[LiveEvent]: ...

    @abstractmethod
    async def send_tool_results(self, results: Sequence[ToolResult]) -> None:
        """Hand every output back to the model. Does not start a new response."""

    @abstractmethod
    async def request_response(self) -> None:
        """Ask the model to answer now (after tool results were sent)."""

    @abstractmethod
    async def truncate(self, item_id: str, audio_end_ms: int) -> None:
        """Tell the model how much of an assistant audio item the user actually heard."""

    @abstractmethod
    async def close(self) -> None: ...


class LiveSessionPort(ABC):
    @abstractmethod
    async def open(self, instructions: str, tools: Sequence[ToolSpec]) -> LiveSession:
        """Returns once the provider session is configured. Raises LiveSessionError."""
