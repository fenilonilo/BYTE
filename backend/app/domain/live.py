from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.tools import ToolCall


@dataclass(frozen=True, slots=True)
class AssistantAudio:
    data: bytes
    item_id: str


@dataclass(frozen=True, slots=True)
class UserSpeechStarted:
    item_id: str


@dataclass(frozen=True, slots=True)
class UserTranscript:
    item_id: str
    text: str


@dataclass(frozen=True, slots=True)
class AssistantTranscript:
    text: str


@dataclass(frozen=True, slots=True)
class ResponseStarted:
    """The provider began a response (also the one it starts by itself after a barge-in)."""


@dataclass(frozen=True, slots=True)
class ResponseDone:
    """The response ended. `calls` holds the tool calls it asked for, if any."""

    calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class LiveError:
    code: str


type LiveEvent = (
    AssistantAudio
    | UserSpeechStarted
    | UserTranscript
    | AssistantTranscript
    | ResponseStarted
    | ResponseDone
    | LiveError
)
