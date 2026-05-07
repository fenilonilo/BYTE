from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class StubAgent(AgentPort):
    async def run(self, message: str, conversation: Conversation) -> str:
        return f"[stub] Echo: {message}"
