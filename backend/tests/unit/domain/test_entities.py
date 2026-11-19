from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.domain.entities import Message

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
