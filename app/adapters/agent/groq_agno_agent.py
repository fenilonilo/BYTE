from __future__ import annotations

from typing import TYPE_CHECKING

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.groq import Groq

from app.adapters.agent.schemas import GroqOutputSchema, map_content_block
from app.domain.entities import AgentResponse
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.config import Settings
    from app.domain.entities import Conversation

_SYSTEM_PROMPT = (
    "Classify this task before responding. "
    "If the task requires deep multi-step reasoning, advanced mathematics, "
    "complex code generation, or long-form structured analysis: "
    "set complexity='complex' and content=[]. Do NOT answer the question. "
    "Otherwise: set complexity='simple' and fill content with your full answer."
)


class GroqAgnoAgent(AgentPort):
    def __init__(self, settings: Settings) -> None:
        self._model_id = settings.groq_model_id
        agno_db_url = settings.database_url.replace("+asyncpg", "+psycopg")
        db = PostgresDb(db_url=agno_db_url)
        self._agent = Agent(
            model=Groq(id=self._model_id),
            db=db,
            add_history_to_context=True,
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
            output_schema=GroqOutputSchema,
            instructions=[_SYSTEM_PROMPT],
        )

    @property
    def model_id(self) -> str:
        return f"groq/{self._model_id}"

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
                complexity="simple",
                tools_called=(),
                routed_from=None,
            )
        output: GroqOutputSchema = response.content  # type: ignore[assignment]
        return AgentResponse(
            content=tuple(map_content_block(b) for b in output.content),
            model_used=self.model_id,
            complexity=output.complexity,
            tools_called=tuple(output.tools_called),
            routed_from=None,
        )
