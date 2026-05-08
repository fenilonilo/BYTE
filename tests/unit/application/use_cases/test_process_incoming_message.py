from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import (
    AgentResponse,
    Conversation,
    IncomingMessage,
    OutgoingMessage,
    TextBlock,
)

NOW = datetime.now(tz=UTC)

_AGENT_RESPONSE = AgentResponse(
    content=(TextBlock(text="Hello back!"),),
    model_used="groq/llama-3.3-70b-versatile",
    complexity="simple",
    tools_called=(),
    routed_from=None,
)


@pytest.fixture
def incoming_msg() -> IncomingMessage:
    return IncomingMessage(
        id="msg-1",
        sender="user-1",
        content="Hello!",
        channel="api",
        timestamp=NOW,
        conversation_id=None,
    )


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.run.return_value = _AGENT_RESPONSE
    return agent


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get.return_value = None
    repo.save.return_value = None
    return repo


@pytest.fixture
def mock_log() -> MagicMock:
    return MagicMock()


@pytest.mark.unit
async def test_execute_returns_outgoing_message(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    assert result.content == "Hello back!"
    assert result.channel == "api"
    assert result.recipient == "user-1"


@pytest.mark.unit
async def test_execute_propagates_model_used(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert result.model_used == "groq/llama-3.3-70b-versatile"
    assert result.routed_from is None


@pytest.mark.unit
async def test_execute_passes_model_override_to_agent(
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    msg = IncomingMessage(
        id="msg-x",
        sender="user-1",
        content="Hello!",
        channel="api",
        timestamp=NOW,
        model_override="gemini",
    )
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(msg)
    _, kwargs = mock_agent.run.call_args
    assert kwargs.get("model_override") == "gemini"


@pytest.mark.unit
async def test_execute_calls_agent(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_agent.run.assert_called_once()


@pytest.mark.unit
async def test_execute_saves_conversation(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_repo.save.assert_called_once()


@pytest.mark.unit
async def test_execute_loads_existing_conversation(
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    existing_conv = Conversation(id="conv-123", messages=(), created_at=NOW)
    mock_repo.get.return_value = existing_conv
    msg = IncomingMessage(
        id="msg-2",
        sender="user-1",
        content="Follow-up",
        channel="api",
        timestamp=NOW,
        conversation_id="conv-123",
    )
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(msg)
    mock_repo.get.assert_called_once_with("conv-123")


@pytest.mark.unit
async def test_execute_creates_conversation_when_none(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    mock_repo.get.return_value = None
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    mock_repo.save.assert_called_once()


@pytest.mark.unit
async def test_execute_returns_empty_string_when_no_text_block(
    incoming_msg: IncomingMessage,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    empty_response = AgentResponse(
        content=(),
        model_used="groq/llama-3.3-70b-versatile",
        complexity="simple",
        tools_called=(),
        routed_from=None,
    )
    agent = AsyncMock()
    agent.run.return_value = empty_response
    use_case = ProcessIncomingMessage(agent=agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert result.content == ""
