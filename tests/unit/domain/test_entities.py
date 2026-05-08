from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.domain.entities import (
    AgentResponse,
    AudioBlock,
    Conversation,
    ImageBlock,
    IncomingMessage,
    Message,
    OutgoingMessage,
    TextBlock,
)

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


@pytest.mark.unit
def test_text_block_defaults() -> None:
    block = TextBlock()
    assert block.type == "text"
    assert block.text == ""


@pytest.mark.unit
def test_text_block_is_frozen() -> None:
    block = TextBlock(text="hello")
    with pytest.raises(FrozenInstanceError):
        block.text = "world"  # type: ignore[misc]


@pytest.mark.unit
def test_image_block_default_mime_type() -> None:
    block = ImageBlock()
    assert block.mime_type == "image/jpeg"
    assert block.url is None
    assert block.base64_data is None


@pytest.mark.unit
def test_audio_block_default_mime_type() -> None:
    block = AudioBlock()
    assert block.mime_type == "audio/mpeg"


@pytest.mark.unit
def test_agent_response_simple() -> None:
    resp = AgentResponse(
        content=(TextBlock(text="hello"),),
        model_used="groq/llama-3.3-70b-versatile",
        complexity="simple",
        tools_called=(),
        routed_from=None,
    )
    assert isinstance(resp.content[0], TextBlock)
    assert resp.content[0].text == "hello"
    assert resp.complexity == "simple"
    assert resp.routed_from is None


@pytest.mark.unit
def test_agent_response_empty_content_is_handoff_signal() -> None:
    resp = AgentResponse(
        content=(),
        model_used="groq/llama-3.3-70b-versatile",
        complexity="complex",
        tools_called=(),
        routed_from=None,
    )
    assert resp.content == ()
    assert resp.complexity == "complex"


@pytest.mark.unit
def test_outgoing_message_model_fields_default() -> None:
    msg = OutgoingMessage(content="hi", channel="api", recipient="user-1")
    assert msg.model_used == ""
    assert msg.routed_from is None


@pytest.mark.unit
def test_incoming_message_model_override_defaults_none() -> None:
    msg = IncomingMessage(id="4", sender="alice", content="hi", channel="api", timestamp=NOW)
    assert msg.model_override is None


@pytest.mark.unit
def test_incoming_message_model_override_set() -> None:
    msg = IncomingMessage(
        id="5",
        sender="alice",
        content="hi",
        channel="api",
        timestamp=NOW,
        model_override="gemini",
    )
    assert msg.model_override == "gemini"
