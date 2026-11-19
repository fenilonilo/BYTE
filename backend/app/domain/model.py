from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.domain.tools import ToolCall


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """One entry of the transcript the model sees during a single chat request."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModelTurn:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
