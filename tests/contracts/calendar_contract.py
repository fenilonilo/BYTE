from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from app.domain.exceptions import EventNotFoundError

if TYPE_CHECKING:
    from app.ports.calendar import CalendarPort

DAY = date(2026, 10, 6)


def at(hour: int, day: date = DAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC)


class CalendarPortContract(ABC):
    """Every CalendarPort adapter must pass this. `make()` returns an empty calendar."""

    @abstractmethod
    def make(self) -> CalendarPort: ...

    async def test_create_then_list_sorted_by_start(self) -> None:
        cal = self.make()
        await cal.create_event("k2", "dentista", at(15), 60)
        await cal.create_event("k1", "reuniao", at(9), 30)
        titles = [e.title for e in await cal.list_events(DAY)]
        assert titles == ["reuniao", "dentista"]

    async def test_list_only_returns_that_day(self) -> None:
        cal = self.make()
        await cal.create_event("k1", "hoje", at(9), 30)
        await cal.create_event("k2", "amanha", at(9, date(2026, 10, 7)), 30)
        assert [e.title for e in await cal.list_events(DAY)] == ["hoje"]

    async def test_create_is_idempotent_per_key(self) -> None:
        cal = self.make()
        first = await cal.create_event("same", "reuniao", at(9), 30)
        second = await cal.create_event("same", "reuniao", at(9), 30)
        assert first.id == second.id
        assert len(await cal.list_events(DAY)) == 1

    async def test_delete_removes_event(self) -> None:
        cal = self.make()
        event = await cal.create_event("k1", "reuniao", at(9), 30)
        await cal.delete_event(event.id)
        assert await cal.list_events(DAY) == ()

    async def test_delete_unknown_raises(self) -> None:
        with pytest.raises(EventNotFoundError):
            await self.make().delete_event("nope")
