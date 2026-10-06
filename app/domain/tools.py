from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, object]
    segment: str
    requires_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str
    signature: bytes = b""  # opaque provider token that must travel back with the call (Gemini)


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    output: str


@dataclass(frozen=True, slots=True)
class PendingAction:
    tool: str
    arguments: str
    summary: str
    key: str
    expires_at: float
    armed: bool = False
    armed_text: str = ""
