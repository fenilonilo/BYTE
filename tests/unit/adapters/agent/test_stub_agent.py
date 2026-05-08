from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.agent.stub_agent import StubAgent
from app.domain.entities import AgentResponse, Conversation, TextBlock
from app.ports.agent import AgentPort

NOW = datetime.now(tz=UTC)


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-1", messages=(), created_at=NOW)


@pytest.mark.unit
async def test_stub_agent_returns_agent_response(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation)
    assert isinstance(result, AgentResponse)


@pytest.mark.unit
async def test_stub_agent_content_is_text_block(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation)
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextBlock)
    assert "Hello" in result.content[0].text


@pytest.mark.unit
async def test_stub_agent_complexity_is_simple(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation)
    assert result.complexity == "simple"
    assert result.model_used == "stub"
    assert result.routed_from is None


@pytest.mark.unit
async def test_stub_agent_implements_port(conversation: Conversation) -> None:
    agent = StubAgent()
    assert isinstance(agent, AgentPort)


@pytest.mark.unit
async def test_stub_agent_accepts_model_override(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation, model_override="gemini")
    assert isinstance(result, AgentResponse)
