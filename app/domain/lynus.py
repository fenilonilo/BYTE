from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from datetime import datetime


class LynusPhase(StrEnum):
    OFF = "off"
    BRIEFING = "briefing"  # talking with the owner about the task
    WORKING = "working"  # driving Claude Code on its own
    DONE = "done"
    STOPPED = "stopped"
    FAILED = "failed"

    @property
    def active(self) -> bool:
        return self in (LynusPhase.BRIEFING, LynusPhase.WORKING)


@dataclass(frozen=True, slots=True)
class LynusNote:
    """One line of what the panel shows: `claude` notes are the prompts Lynus sent."""

    role: Literal["owner", "lynus", "claude", "system"]
    text: str
    at: datetime
