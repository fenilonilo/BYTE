from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime, timedelta

    from app.domain.world import CalendarEvent

CALENDAR_PREFIX = "cal-"


class ReminderKind(StrEnum):
    REMINDER = "lembrete"  # spoken once
    ALARM = "alarme"  # rings until the owner stops it


@dataclass(frozen=True, slots=True)
class Reminder:
    id: str
    text: str
    at: datetime
    kind: ReminderKind
    expires_at: datetime | None = None

    def is_due(self, now: datetime) -> bool:
        return self.at <= now

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    @property
    def is_calendar(self) -> bool:
        return self.id.startswith(CALENDAR_PREFIX)


def spoken_time(at: datetime) -> str:
    """Words Piper reads naturally ("às 15 e 30"), unlike "15:30"."""
    return f"às {at.hour} horas" if at.minute == 0 else f"às {at.hour} e {at.minute}"


def calendar_warnings(events: Iterable[CalendarEvent], lead: timedelta) -> tuple[Reminder, ...]:
    """A spoken warning `lead` before each event, useless (expired) once it starts."""
    return tuple(
        Reminder(
            # the start is part of the id: a moved event must be warned again
            id=f"{CALENDAR_PREFIX}{e.id}-{int(e.start.timestamp())}",
            text=f"{e.title}, {spoken_time(e.start)}",
            at=e.start - lead,
            kind=ReminderKind.REMINDER,
            expires_at=e.start,
        )
        for e in events
    )
