from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.agent.stub_agent import StubAgent
from app.domain.entities import Conversation
from app.ports.agent import AgentPort

NOW = datetime.now(tz=UTC)


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-1", messages=(), created_at=NOW)


@pytest.mark.unit
async def test_stub_agent_returns_string(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
async def test_stub_agent_implements_port(conversation: Conversation) -> None:
    agent = StubAgent()
    assert isinstance(agent, AgentPort)
