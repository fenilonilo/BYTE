from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    role: str
    content: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    id: str
    content: str
    segment: str
    timestamp: datetime
    conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    segment: str
    messages: tuple[Message, ...]
    created_at: datetime

    def with_message(self, msg: Message) -> Conversation:
        return Conversation(
            id=self.id,
            segment=self.segment,
            messages=(*self.messages, msg),
            created_at=self.created_at,
        )
