from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.reminders import Reminder


class ReminderStorePort(ABC):
    """Reminders that must survive a restart until the device has played them."""

    @abstractmethod
    async def all(self) -> tuple[Reminder, ...]:
        """Every stored reminder, soonest first."""

    @abstractmethod
    async def put(self, reminder: Reminder) -> None:
        """Insert, or replace the reminder with the same id."""

    @abstractmethod
    async def remove(self, reminder_id: str) -> None:
        """Raises ReminderNotFoundError for an unknown id."""
