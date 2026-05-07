from __future__ import annotations

from typing import TYPE_CHECKING

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.anthropic import Claude

from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.config import Settings
    from app.domain.entities import Conversation


class AgnoAgent(AgentPort):
    def __init__(self, settings: Settings) -> None:
        # Agno uses psycopg (sync driver); derive from asyncpg URL
        agno_db_url = settings.database_url.replace("+asyncpg", "+psycopg")
        db = PostgresDb(db_url=agno_db_url)
        self._agent = Agent(
            model=Claude(id=settings.agno_model_id),
            db=db,
            add_history_to_context=True,
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
        )

    async def run(self, message: str, conversation: Conversation) -> str:
        response = await self._agent.arun(message, session_id=conversation.id)
        if response is None or response.content is None:
            return ""
        return str(response.content)
