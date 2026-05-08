from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.agent.schemas import GroqOutputSchema, TextBlockSchema
from app.domain.entities import AgentResponse, Conversation, TextBlock
from app.ports.agent import AgentPort

NOW = datetime.now(tz=UTC)


@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.database_url = "postgresql+asyncpg://test:test@localhost/test"
    s.groq_model_id = "llama-3.3-70b-versatile"
    s.agno_add_datetime = True
    s.agno_add_location = True
    return s


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-abc", messages=(), created_at=NOW)


def _make_agent_cls(output: GroqOutputSchema) -> tuple[MagicMock, AsyncMock]:
    mock_response = MagicMock()
    mock_response.content = output
    mock_inner = AsyncMock()
    mock_inner.arun = AsyncMock(return_value=mock_response)
    mock_cls = MagicMock(return_value=mock_inner)
    return mock_cls, mock_inner


@pytest.mark.unit
async def test_groq_agent_returns_simple_agent_response(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    output = GroqOutputSchema(
        complexity="simple",
        content=[TextBlockSchema(type="text", text="Hello!")],
        tools_called=[],
    )
    mock_cls, _ = _make_agent_cls(output)

    with (
        patch("app.adapters.agent.groq_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert isinstance(result, AgentResponse)
    assert result.complexity == "simple"
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextBlock)
    assert result.content[0].text == "Hello!"
    assert result.model_used == "groq/llama-3.3-70b-versatile"
    assert result.routed_from is None


@pytest.mark.unit
async def test_groq_agent_returns_complex_signal(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    output = GroqOutputSchema(complexity="complex", content=[], tools_called=[])
    mock_cls, _ = _make_agent_cls(output)

    with (
        patch("app.adapters.agent.groq_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        result = await agent.run("Complex task", conversation)

    assert result.complexity == "complex"
    assert result.content == ()


@pytest.mark.unit
async def test_groq_agent_passes_session_id(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    output = GroqOutputSchema(complexity="simple", content=[], tools_called=[])
    mock_cls, mock_inner = _make_agent_cls(output)

    with (
        patch("app.adapters.agent.groq_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        await agent.run("Hello", conversation)

    mock_inner.arun.assert_called_once_with("Hello", session_id="conv-abc")


@pytest.mark.unit
async def test_groq_agent_returns_empty_on_none_response(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_inner = AsyncMock()
    mock_inner.arun = AsyncMock(return_value=None)
    mock_cls = MagicMock(return_value=mock_inner)

    with (
        patch("app.adapters.agent.groq_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert result.content == ()
    assert result.complexity == "simple"


@pytest.mark.unit
async def test_groq_agent_implements_port(mock_settings: MagicMock) -> None:
    with (
        patch("app.adapters.agent.groq_agno_agent.Agent"),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        assert isinstance(agent, AgentPort)
