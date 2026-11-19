"""CalendarPortContract against the real Google Calendar.

The contract assumes an empty calendar on 2026-10-06/07, so point BYTE_GOOGLE_CALENDAR_ID at a
dedicated test calendar, not your real one. Cleanup deletes only the events whose ids are the
hashes of the contract's keys, before and after each test. Deleted ids stay reserved in Google
(status "cancelled"); the adapter revives them when the same key is created again.
"""

from __future__ import annotations

import contextlib
from datetime import date
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.adapters.google.google_calendar import GoogleCalendar, event_id
from app.domain.exceptions import EventNotFoundError
from tests.contracts.calendar_contract import CalendarPortContract

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class _GoogleEnv(BaseSettings):
    """Just the Google config: this test needs neither the API token nor a model key."""

    model_config = SettingsConfigDict(
        env_prefix="BYTE_GOOGLE_", env_file=".env", env_ignore_empty=True, extra="ignore"
    )
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    calendar_id: str = "primary"
    timezone: str = "America/Sao_Paulo"


ENV = _GoogleEnv()
CONTRACT_KEYS = ("k1", "k2", "same")
DAYS = (date(2026, 10, 6), date(2026, 10, 7))

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not (ENV.client_id and ENV.client_secret and ENV.refresh_token and ENV.calendar_id),
        reason="needs BYTE_GOOGLE_CLIENT_ID/_CLIENT_SECRET/_REFRESH_TOKEN/_CALENDAR_ID",
    ),
]


def _adapter() -> GoogleCalendar:
    return GoogleCalendar(
        ENV.client_id, ENV.client_secret, ENV.refresh_token, ENV.calendar_id, ZoneInfo(ENV.timezone)
    )


async def _clean(cal: GoogleCalendar) -> None:
    ours = {event_id(k) for k in CONTRACT_KEYS}
    for day in DAYS:
        for event in await cal.list_events(day):
            if event.id in ours:
                with contextlib.suppress(EventNotFoundError):
                    await cal.delete_event(event.id)


class TestGoogleCalendarContract(CalendarPortContract):
    @pytest.fixture(autouse=True)
    async def _isolate(self) -> AsyncIterator[None]:
        self._made: list[GoogleCalendar] = []
        janitor = _adapter()
        await _clean(janitor)
        yield
        await _clean(janitor)
        for cal in (*self._made, janitor):
            await cal.close()

    def make(self) -> GoogleCalendar:
        cal = _adapter()
        self._made.append(cal)
        return cal
