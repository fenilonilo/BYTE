from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.entities import Conversation

NOW = datetime.now(tz=UTC)


@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.database_url = "postgresql+asyncpg://test:test@localhost/test"
    s.agno_model_id = "claude-sonnet-4-6"
    s.agno_add_datetime = True
    s.agno_add_location = True
    return s


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-abc", messages=(), created_at=NOW)


@pytest.mark.unit
async def test_run_returns_response_content(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_response = MagicMock()
    mock_response.content = "Agent says hello"

    with (
        patch("app.adapters.agent.agno_agent.Agent") as mock_agent_cls,
        patch("app.adapters.agent.agno_agent.PostgresDb"),
        patch("app.adapters.agent.agno_agent.Claude"),
    ):
        mock_inner = AsyncMock()
        mock_agent_cls.return_value = mock_inner
        mock_inner.arun = AsyncMock(return_value=mock_response)

        from app.adapters.agent.agno_agent import AgnoAgent  # noqa: PLC0415

        agent = AgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert result == "Agent says hello"


@pytest.mark.unit
async def test_run_passes_session_id_from_conversation(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_response = MagicMock()
    mock_response.content = "response"

    with (
        patch("app.adapters.agent.agno_agent.Agent") as mock_agent_cls,
        patch("app.adapters.agent.agno_agent.PostgresDb"),
        patch("app.adapters.agent.agno_agent.Claude"),
    ):
        mock_inner = AsyncMock()
        mock_agent_cls.return_value = mock_inner
        mock_inner.arun = AsyncMock(return_value=mock_response)

        from app.adapters.agent.agno_agent import AgnoAgent  # noqa: PLC0415

        agent = AgnoAgent(mock_settings)
        await agent.run("Hello", conversation)

        mock_inner.arun.assert_called_once_with("Hello", session_id="conv-abc")


@pytest.mark.unit
async def test_run_returns_empty_string_when_content_is_none(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_response = MagicMock()
    mock_response.content = None

    with (
        patch("app.adapters.agent.agno_agent.Agent") as mock_agent_cls,
        patch("app.adapters.agent.agno_agent.PostgresDb"),
        patch("app.adapters.agent.agno_agent.Claude"),
    ):
        mock_inner = AsyncMock()
        mock_agent_cls.return_value = mock_inner
        mock_inner.arun = AsyncMock(return_value=mock_response)

        from app.adapters.agent.agno_agent import AgnoAgent  # noqa: PLC0415

        agent = AgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert result == ""


@pytest.mark.unit
async def test_agno_agent_implements_port(mock_settings: MagicMock) -> None:
    from app.ports.agent import AgentPort  # noqa: PLC0415

    with (
        patch("app.adapters.agent.agno_agent.Agent"),
        patch("app.adapters.agent.agno_agent.PostgresDb"),
        patch("app.adapters.agent.agno_agent.Claude"),
    ):
        from app.adapters.agent.agno_agent import AgnoAgent  # noqa: PLC0415

        agent = AgnoAgent(mock_settings)
        assert isinstance(agent, AgentPort)
