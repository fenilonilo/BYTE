from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import groq as groq_sdk

from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.adapters.agent.gemini_agno_agent import GeminiAgnoAgent
    from app.adapters.agent.groq_agno_agent import GroqAgnoAgent
    from app.domain.entities import AgentResponse, Conversation


class RoutingAgnoAgent(AgentPort):
    def __init__(self, groq_agent: GroqAgnoAgent, gemini_agent: GeminiAgnoAgent) -> None:
        self._groq = groq_agent
        self._gemini = gemini_agent

    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse:
        if model_override == "gemini":
            return await self._gemini.run(message, conversation)
        if model_override == "groq":
            return await self._groq.run(message, conversation)

        # Tool-tag routing (spec priority 3): when tools are added with
        # metadata={"model": "gemini"}, inspect them here and route to Gemini.

        try:
            response = await self._groq.run(message, conversation)
        except groq_sdk.RateLimitError:
            result = await self._gemini.run(message, conversation)
            return replace(result, routed_from=self._groq.model_id)

        if response.complexity == "complex" and not response.content:
            result = await self._gemini.run(message, conversation)
            return replace(result, routed_from=self._groq.model_id)

        return response
