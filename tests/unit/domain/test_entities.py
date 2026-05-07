from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.domain.entities import Conversation, IncomingMessage, Message, OutgoingMessage


NOW = datetime.now(tz=timezone.utc)


def test_message_fields() -> None:
    msg = Message(id="1", role="user", content="hello", timestamp=NOW)
    assert msg.id == "1"
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.timestamp == NOW


def test_message_is_frozen() -> None:
    msg = Message(id="1", role="user", content="hello", timestamp=NOW)
    with pytest.raises(Exception):
        msg.content = "changed"  # type: ignore[misc]


def test_incoming_message_defaults() -> None:
    msg = IncomingMessage(id="2", sender="alice", content="hi", channel="api", timestamp=NOW)
    assert msg.conversation_id is None


def test_incoming_message_with_conversation_id() -> None:
    msg = IncomingMessage(
        id="3",
        sender="alice",
        content="hi",
        channel="api",
        timestamp=NOW,
        conversation_id="conv-1",
    )
    assert msg.conversation_id == "conv-1"


def test_outgoing_message_fields() -> None:
    msg = OutgoingMessage(content="hello back", channel="api", recipient="alice")
    assert msg.content == "hello back"
    assert msg.channel == "api"
    assert msg.recipient == "alice"


def test_conversation_creation() -> None:
    conv = Conversation(id="c1", messages=(), created_at=NOW)
    assert conv.id == "c1"
    assert conv.messages == ()


def test_conversation_with_message_appends() -> None:
    conv = Conversation(id="c1", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    new_conv = conv.with_message(msg)
    assert len(new_conv.messages) == 1
    assert new_conv.messages[0] == msg


def test_conversation_with_message_original_unchanged() -> None:
    conv = Conversation(id="c1", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    conv.with_message(msg)
    assert len(conv.messages) == 0


def test_conversation_with_message_preserves_metadata() -> None:
    conv = Conversation(id="c1", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    new_conv = conv.with_message(msg)
    assert new_conv.id == "c1"
    assert new_conv.created_at == NOW
