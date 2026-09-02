from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import Conversation, IncomingMessage, Message

NOW = datetime.now(tz=UTC)


@pytest.fixture
def incoming_msg() -> IncomingMessage:
    return IncomingMessage(
        id="msg-1",
        content="Hello!",
        segment="sales",
        timestamp=NOW,
        conversation_id=None,
    )


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.run.return_value = "Hello back!"
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
async def test_execute_returns_assistant_message(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, Message)
    assert result.role == "assistant"
    assert result.content == "Hello back!"


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
async def test_new_conversation_carries_segment(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    saved: Conversation = mock_repo.save.call_args.args[0]
    assert saved.segment == "sales"
    assert len(saved.messages) == 2


@pytest.mark.unit
async def test_execute_loads_existing_conversation(
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    mock_repo.get.return_value = Conversation(
        id="conv-123", segment="sales", messages=(), created_at=NOW
    )
    msg = IncomingMessage(
        id="msg-2",
        content="Follow-up",
        segment="sales",
        timestamp=NOW,
        conversation_id="conv-123",
    )
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(msg)
    mock_repo.get.assert_called_once_with("conv-123")
