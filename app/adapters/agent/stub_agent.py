from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class StubAgent(AgentPort):
    """Placeholder until the Agno adapter lands. Echoes with its segment name."""

    def __init__(self, segment: str) -> None:
        self._segment = segment

    async def run(self, message: str, conversation: Conversation) -> str:
        return f"[stub:{self._segment}] {message}"
