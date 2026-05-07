# tests/unit/application/use_cases/test_process_incoming_message.py
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import Conversation, IncomingMessage, OutgoingMessage


NOW = datetime.now(tz=timezone.utc)


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
def mock_llm() -> AsyncMock:
    llm = AsyncMock()
    llm.complete.return_value = "Hello back!"
    return llm


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
    mock_llm: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    assert result.content == "Hello back!"
    assert result.channel == "api"
    assert result.recipient == "user-1"


@pytest.mark.unit
async def test_execute_calls_llm(
    incoming_msg: IncomingMessage,
    mock_llm: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_llm.complete.assert_called_once()


@pytest.mark.unit
async def test_execute_saves_conversation(
    incoming_msg: IncomingMessage,
    mock_llm: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_repo.save.assert_called_once()


@pytest.mark.unit
async def test_execute_loads_existing_conversation(
    mock_llm: AsyncMock,
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
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    await use_case.execute(msg)
    mock_repo.get.assert_called_once_with("conv-123")


@pytest.mark.unit
async def test_execute_creates_conversation_when_none(
    incoming_msg: IncomingMessage,
    mock_llm: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    mock_repo.get.return_value = None
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    mock_repo.save.assert_called_once()
