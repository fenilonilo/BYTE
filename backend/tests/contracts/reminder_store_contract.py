from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.domain.exceptions import ReminderNotFoundError
from app.domain.reminders import Reminder, ReminderKind

if TYPE_CHECKING:
    from app.ports.reminders import ReminderStorePort

AT = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)


def reminder(rid: str, at: datetime = AT, text: str = "pagar a luz") -> Reminder:
    return Reminder(rid, text, at, ReminderKind.ALARM, expires_at=at + timedelta(hours=1))


class ReminderStoreContract(ABC):
    """Every ReminderStorePort adapter must pass this. `make()` returns an empty store."""

    @abstractmethod
    def make(self) -> ReminderStorePort: ...

    async def test_put_then_all_sorted_by_time(self) -> None:
        store = self.make()
        await store.put(reminder("b", AT + timedelta(hours=1)))
        await store.put(reminder("a"))
        assert [r.id for r in await store.all()] == ["a", "b"]

    async def test_put_same_id_replaces(self) -> None:
        store = self.make()
        await store.put(reminder("a", text="velho"))
        await store.put(reminder("a", text="novo"))
        assert [r.text for r in await store.all()] == ["novo"]

    async def test_round_trips_every_field(self) -> None:
        store = self.make()
        await store.put(reminder("a"))
        assert await store.all() == (reminder("a"),)

    async def test_remove(self) -> None:
        store = self.make()
        await store.put(reminder("a"))
        await store.remove("a")
        assert await store.all() == ()

    async def test_remove_unknown_raises(self) -> None:
        with pytest.raises(ReminderNotFoundError):
            await self.make().remove("nope")
