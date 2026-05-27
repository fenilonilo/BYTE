from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.entities import AgentResponse, TextBlock
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class StubAgent(AgentPort):
    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse:
        return AgentResponse(
            content=(TextBlock(text=f"[stub] Echo: {message}"),),
            model_used="stub",
            complexity="simple",
            tools_called=(),
            routed_from=None,
        )
