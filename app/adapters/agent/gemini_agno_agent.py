from __future__ import annotations

from typing import TYPE_CHECKING

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.google import Gemini

from app.adapters.agent.schemas import GeminiOutputSchema, map_content_block
from app.domain.entities import AgentResponse
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.config import Settings
    from app.domain.entities import Conversation


class GeminiAgnoAgent(AgentPort):
    def __init__(self, settings: Settings) -> None:
        self._model_id = settings.gemini_model_id
        agno_db_url = settings.database_url.replace("+asyncpg", "+psycopg").split("?")[0]
        db = PostgresDb(db_url=agno_db_url)
        self._agent = Agent(
            model=Gemini(id=self._model_id),
            db=db,
            add_history_to_context=True,
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
            output_schema=GeminiOutputSchema,
        )

    @property
    def model_id(self) -> str:
        return f"google/{self._model_id}"

    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse:
        response = await self._agent.arun(message, session_id=conversation.id)
        if response is None or response.content is None:
            return AgentResponse(
                content=(),
                model_used=self.model_id,
                complexity="complex",
                tools_called=(),
                routed_from=None,
            )
        output: GeminiOutputSchema = response.content  # type: ignore[assignment]
        return AgentResponse(
            content=tuple(map_content_block(b) for b in output.content),
            model_used=self.model_id,
            complexity="complex",
            tools_called=tuple(output.tools_called),
            routed_from=None,
        )
