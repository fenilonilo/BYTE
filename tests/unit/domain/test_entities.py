from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.domain.entities import Conversation, IncomingMessage, Message

NOW = datetime.now(tz=UTC)


def test_message_fields() -> None:
    msg = Message(id="1", role="user", content="hello", timestamp=NOW)
    assert msg.id == "1"
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.timestamp == NOW


def test_message_is_frozen() -> None:
    msg = Message(id="1", role="user", content="hello", timestamp=NOW)
    with pytest.raises(FrozenInstanceError):
        msg.content = "changed"  # type: ignore[misc]


def test_incoming_message_defaults() -> None:
    msg = IncomingMessage(id="2", content="hi", segment="general", timestamp=NOW)
    assert msg.conversation_id is None


def test_incoming_message_with_conversation_id() -> None:
    msg = IncomingMessage(
        id="3",
        content="hi",
        segment="general",
        timestamp=NOW,
        conversation_id="conv-1",
    )
    assert msg.conversation_id == "conv-1"


def test_conversation_creation() -> None:
    conv = Conversation(id="c1", segment="general", messages=(), created_at=NOW)
    assert conv.id == "c1"
    assert conv.segment == "general"
    assert conv.messages == ()


def test_conversation_with_message_appends() -> None:
    conv = Conversation(id="c1", segment="general", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    new_conv = conv.with_message(msg)
    assert len(new_conv.messages) == 1
    assert new_conv.messages[0] == msg


def test_conversation_with_message_original_unchanged() -> None:
    conv = Conversation(id="c1", segment="general", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    conv.with_message(msg)
    assert len(conv.messages) == 0


def test_conversation_with_message_preserves_metadata() -> None:
    conv = Conversation(id="c1", segment="general", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    new_conv = conv.with_message(msg)
    assert new_conv.id == "c1"
    assert new_conv.segment == "general"
    assert new_conv.created_at == NOW
