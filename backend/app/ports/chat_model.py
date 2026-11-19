from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.model import ModelMessage, ModelTurn
    from app.domain.tools import ToolSpec


class ChatModelPort(ABC):
    """One model call: a transcript and the available tools in, text or tool calls out."""

    @abstractmethod
    async def complete(
        self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn: ...
