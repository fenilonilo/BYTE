from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.exceptions import EventNotFoundError
from app.domain.world import CalendarEvent
from app.ports.calendar import CalendarPort

if TYPE_CHECKING:
    from datetime import date, datetime


class InMemoryCalendar(CalendarPort):
    def __init__(self) -> None:
        self._events: dict[str, CalendarEvent] = {}
        self._by_key: dict[str, str] = {}

    async def list_events(self, day: date) -> tuple[CalendarEvent, ...]:
        found = [e for e in self._events.values() if e.start.date() == day]
        return tuple(sorted(found, key=lambda e: e.start))

    async def create_event(
        self, key: str, title: str, start: datetime, duration_minutes: int
    ) -> CalendarEvent:
        existing = self._by_key.get(key)
        if existing is not None:
            return self._events[existing]
        event = CalendarEvent(
            id=f"evt-{len(self._by_key) + 1}",
            title=title,
            start=start,
            duration_minutes=duration_minutes,
        )
        self._events[event.id] = event
        self._by_key[key] = event.id
        return event

    async def get_event(self, event_id: str) -> CalendarEvent:
        try:
            return self._events[event_id]
        except KeyError:
            raise EventNotFoundError(f"Unknown event: {event_id!r}") from None

    async def delete_event(self, event_id: str) -> None:
        if self._events.pop(event_id, None) is None:
            raise EventNotFoundError(f"Unknown event: {event_id!r}")
