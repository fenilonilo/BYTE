from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.chat_model import ChatModelPort

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.model import ModelMessage, ModelTurn
    from app.domain.tools import ToolSpec


class ScriptedChatModel(ChatModelPort):
    """Returns the scripted turns in order and records every call it receives."""

    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self._turns = list(turns)
        self.calls: list[tuple[tuple[ModelMessage, ...], tuple[ToolSpec, ...]]] = []

    async def complete(
        self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        self.calls.append((tuple(messages), tuple(tools)))
        return self._turns.pop(0)
