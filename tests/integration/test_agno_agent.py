from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.agent.agno_agent import build_agents
from app.config import Settings
from app.domain.entities import Conversation, Message

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not (Settings().gemini_api_key and Settings().groq_api_key),
        reason="needs real Gemini and Groq keys",
    ),
]


def _conversation(text: str) -> Conversation:
    now = datetime.now(tz=UTC)
    user = Message(id="m1", role="user", content=text, timestamp=now)
    return Conversation(id="conv-it", segment="auto", messages=(user,), created_at=now)


async def test_team_routes_and_answers_in_portuguese() -> None:
    agents = build_agents(Settings())
    reply = await agents["auto"].run("acende a luz da sala", _conversation("acende a luz da sala"))
    assert reply.strip()


async def test_direct_segment_agent_answers() -> None:
    agents = build_agents(Settings())
    text = "quanto gastei esse mes?"
    reply = await agents["finance"].run(text, _conversation(text))
    assert reply.strip()
