from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime

    from app.domain.world import CalendarEvent


class CalendarPort(ABC):
    @abstractmethod
    async def list_events(self, day: date) -> tuple[CalendarEvent, ...]: ...

    @abstractmethod
    async def create_event(
        self, key: str, title: str, start: datetime, duration_minutes: int
    ) -> CalendarEvent:
        """Idempotent: the same `key` returns the event created the first time."""

    @abstractmethod
    async def get_event(self, event_id: str) -> CalendarEvent:
        """Raises EventNotFoundError for an unknown id."""

    @abstractmethod
    async def delete_event(self, event_id: str) -> None:
        """Raises EventNotFoundError for an unknown id."""
