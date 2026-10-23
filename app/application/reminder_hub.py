from __future__ import annotations

import contextlib
from abc import ABC, abstractmethod
from datetime import timedelta
from typing import TYPE_CHECKING

from app.domain.exceptions import ReminderNotFoundError, SpeechError
from app.domain.reminders import CALENDAR_PREFIX, calendar_warnings

if TYPE_CHECKING:
    from datetime import datetime

    from app.domain.reminders import Reminder
    from app.ports.calendar import CalendarPort
    from app.ports.logger import LoggerPort
    from app.ports.reminders import ReminderStorePort
    from app.ports.speech import SpeechPort

CALENDAR_LEAD = timedelta(minutes=10)


class ReminderListener(ABC):
    """The voice device's notification link (a WebSocket in production)."""

    @abstractmethod
    async def push(self, reminder: Reminder, audio: bytes) -> None:
        """Deliver one reminder. Must not raise: a dead link just never acks."""


class ReminderHub:
    """Fires due reminders at the connected device; a reminder leaves the store only on ack.

    Pure code on purpose: firing a reminder never calls the model."""

    def __init__(
        self,
        store: ReminderStorePort,
        speech: SpeechPort,
        calendar: CalendarPort,
        log: LoggerPort,
    ) -> None:
        self._store = store
        self._speech = speech
        self._calendar = calendar
        self._log = log
        self._listener: ReminderListener | None = None
        self._sent: set[str] = set()
        # ponytail: in memory, so a restart inside the 10-minute window repeats a warning once
        self._warned: set[str] = set()

    def attach(self, listener: ReminderListener) -> None:
        self._listener = listener
        self._sent.clear()  # whatever the last link never acked goes out again

    def detach(self, listener: ReminderListener) -> None:
        if self._listener is listener:
            self._listener = None

    async def tick(self, now: datetime) -> None:
        for reminder in await self._store.all():
            if reminder.is_expired(now):
                await self._forget(reminder.id)
            elif (
                self._listener is not None
                and reminder.is_due(now)
                and reminder.id not in self._sent
            ):
                self._sent.add(reminder.id)
                await self._listener.push(reminder, await self._voice(reminder))
                self._log.info("reminders.sent", reminder_id=reminder.id)

    async def ack(self, reminder_id: str) -> None:
        if reminder_id.startswith(CALENDAR_PREFIX):
            self._warned.add(reminder_id)
        await self._forget(reminder_id)
        self._log.info("reminders.acked", reminder_id=reminder_id)

    async def sync_calendar(self, now: datetime) -> None:
        """Recompute warnings from the calendar, which stays the source of truth."""
        today = now.date()
        events = (
            *await self._calendar.list_events(today),
            *await self._calendar.list_events(today + timedelta(days=1)),
        )
        fresh = {w.id: w for w in calendar_warnings(events, CALENDAR_LEAD) if not w.is_expired(now)}
        self._warned &= fresh.keys()
        stored = {r.id for r in await self._store.all() if r.is_calendar}
        for stale in stored - fresh.keys():
            await self._forget(stale)
        for wid in fresh.keys() - stored - self._warned:
            await self._store.put(fresh[wid])

    async def _voice(self, reminder: Reminder) -> bytes:
        try:
            return await self._speech.synthesize(reminder.text)
        except SpeechError as exc:
            # a beep without words beats a silent reminder
            self._log.warning("reminders.speech_failed", error=type(exc.__cause__).__name__)
            return b""

    async def _forget(self, reminder_id: str) -> None:
        self._sent.discard(reminder_id)
        with contextlib.suppress(ReminderNotFoundError):
            await self._store.remove(reminder_id)
