from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.world import CalendarEvent
    from app.ports.calendar import CalendarPort

EVENT_DAY = date(2026, 10, 6)


async def seed_event(calendar: CalendarPort) -> CalendarEvent:
    """One appointment on EVENT_DAY. Deleting it is the sensitive action the tests confirm."""
    return await calendar.create_event(
        "seed", "dentista", datetime(2026, 10, 6, 15, 0, tzinfo=UTC), 60
    )


async def events_on_day(calendar: CalendarPort) -> tuple[CalendarEvent, ...]:
    return await calendar.list_events(EVENT_DAY)
