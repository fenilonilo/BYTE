from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

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
    sender: str
    content: str
    channel: str
    timestamp: datetime
    conversation_id: str | None = None
    model_override: str | None = None  # "groq" | "gemini" | None


@dataclass(frozen=True, slots=True)
class TextBlock:
    type: Literal["text"] = "text"
    text: str = ""


@dataclass(frozen=True, slots=True)
class ImageBlock:
    type: Literal["image"] = "image"
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "image/jpeg"


@dataclass(frozen=True, slots=True)
class AudioBlock:
    type: Literal["audio"] = "audio"
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "audio/mpeg"


ContentBlock: TypeAlias = TextBlock | ImageBlock | AudioBlock


@dataclass(frozen=True, slots=True)
class AgentResponse:
    content: tuple[ContentBlock, ...]
    model_used: str
    complexity: Literal["simple", "complex"]
    tools_called: tuple[str, ...]
    routed_from: str | None


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    content: str
    channel: str
    recipient: str
    model_used: str = ""
    routed_from: str | None = None


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    messages: tuple[Message, ...]
    created_at: datetime

    def with_message(self, msg: Message) -> Conversation:
        return Conversation(
            id=self.id,
            messages=(*self.messages, msg),
            created_at=self.created_at,
        )
