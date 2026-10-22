from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Self
from zoneinfo import ZoneInfo

import aiohttp
import pytest

from app.adapters.google.google_calendar import GoogleCalendar, event_id
from app.domain.exceptions import CalendarError, EventNotFoundError

TZ = ZoneInfo("America/Sao_Paulo")
EVENTS = "https://www.googleapis.com/calendar/v3/calendars/me%40gmail.com/events"
TOKEN = {"access_token": "at", "expires_in": 3600}


def raw(event_id: str, title: str, start: str, end: str) -> dict[str, Any]:
    return {
        "id": event_id,
        "summary": title,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }


@dataclass
class FakeResponse:
    status: int
    body: dict[str, Any] = field(default_factory=dict[str, Any])
    content_type: str = "application/json"

    async def json(self) -> dict[str, Any]:
        return self.body

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


@dataclass
class FakeSession:
    replies: list[FakeResponse | Exception]
    calls: list[tuple[str, str, dict[str, Any]]] = field(
        default_factory=list[tuple[str, str, dict[str, Any]]]
    )

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self.request("POST", url, **kwargs)

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((method, url, kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def make(
    monkeypatch: pytest.MonkeyPatch, *replies: FakeResponse | Exception
) -> tuple[GoogleCalendar, FakeSession]:
    session = FakeSession([FakeResponse(200, TOKEN), *replies])
    cal = GoogleCalendar("cid", "secret", "refresh", "me@gmail.com", TZ)
    monkeypatch.setattr(cal, "_http", lambda: session)
    return cal, session


async def test_token_is_refreshed_once_and_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    cal, session = make(monkeypatch, FakeResponse(200, {}), FakeResponse(200, {}))
    await cal.list_events(date(2026, 10, 6))
    await cal.list_events(date(2026, 10, 6))
    token_call, first, second = session.calls
    assert token_call[0] == "POST"
    assert token_call[2]["data"]["grant_type"] == "refresh_token"
    assert token_call[2]["data"]["client_secret"] == "secret"
    assert first[2]["headers"] == second[2]["headers"] == {"Authorization": "Bearer at"}


async def test_create_hashes_key_and_applies_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    created = raw("x", "dentista", "2026-10-06T15:00:00-03:00", "2026-10-06T16:00:00-03:00")
    cal, session = make(monkeypatch, FakeResponse(200, created))
    event = await cal.create_event("k1", "dentista", datetime(2026, 10, 6, 15), 60)
    method, url, kwargs = session.calls[1]
    body = kwargs["json"]
    assert (method, url) == ("POST", EVENTS)
    assert body["id"] == event_id("k1")
    assert body["summary"] == "dentista"
    assert body["start"] == {"dateTime": "2026-10-06T15:00:00-03:00", "timeZone": TZ.key}
    assert body["end"]["dateTime"] == "2026-10-06T16:00:00-03:00"
    assert (event.title, event.duration_minutes) == ("dentista", 60)
    assert event.start == datetime(2026, 10, 6, 15, tzinfo=TZ)


async def test_create_conflict_returns_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = raw("abc", "reuniao", "2026-10-06T09:00:00-03:00", "2026-10-06T09:30:00-03:00")
    cal, session = make(monkeypatch, FakeResponse(409), FakeResponse(200, existing))
    event = await cal.create_event("k", "reuniao", datetime(2026, 10, 6, 9), 30)
    assert event.id == "abc"
    assert session.calls[2][:2] == ("GET", f"{EVENTS}/{event_id('k')}")


async def test_create_conflict_on_deleted_event_revives_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gone = {"id": "abc", "status": "cancelled"}
    back = raw("abc", "reuniao", "2026-10-06T09:00:00-03:00", "2026-10-06T09:30:00-03:00")
    cal, session = make(
        monkeypatch, FakeResponse(409), FakeResponse(200, gone), FakeResponse(200, back)
    )
    event = await cal.create_event("k", "reuniao", datetime(2026, 10, 6, 9), 30)
    assert event.id == "abc"
    assert session.calls[3][0] == "PUT"


async def test_list_skips_all_day_and_computes_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    items = [
        {"id": "a", "summary": "feriado", "start": {"date": "2026-10-06"}},
        raw("b", "reuniao", "2026-10-06T12:00:00Z", "2026-10-06T13:30:00Z"),
    ]
    cal, session = make(monkeypatch, FakeResponse(200, {"items": items}))
    events = await cal.list_events(date(2026, 10, 6))
    assert [(e.id, e.duration_minutes) for e in events] == [("b", 90)]
    assert events[0].start == datetime(2026, 10, 6, 9, tzinfo=TZ)
    assert session.calls[1][2]["params"] == {
        "timeMin": "2026-10-06T00:00:00-03:00",
        "timeMax": "2026-10-07T00:00:00-03:00",
        "singleEvents": "true",
        "orderBy": "startTime",
    }


@pytest.mark.parametrize("status", [404, 410])
async def test_unknown_event_raises_not_found(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    cal, _ = make(monkeypatch, FakeResponse(status), FakeResponse(status))
    with pytest.raises(EventNotFoundError):
        await cal.get_event("nope")
    with pytest.raises(EventNotFoundError):
        await cal.delete_event("nope")


async def test_cancelled_event_reads_as_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    cal, _ = make(monkeypatch, FakeResponse(200, {"id": "a", "status": "cancelled"}))
    with pytest.raises(EventNotFoundError):
        await cal.get_event("a")


async def test_server_error_raises_calendar_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cal, _ = make(monkeypatch, FakeResponse(500, {"error": "secret detail"}))
    with pytest.raises(CalendarError, match=r"^google calendar 500$"):
        await cal.delete_event("a")


async def test_network_error_raises_calendar_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cal, _ = make(monkeypatch, aiohttp.ClientConnectionError("down"))
    with pytest.raises(CalendarError) as info:
        await cal.list_events(date(2026, 10, 6))
    assert isinstance(info.value.__cause__, aiohttp.ClientError)


async def test_token_failure_raises_calendar_error(monkeypatch: pytest.MonkeyPatch) -> None:
    cal, session = make(monkeypatch)
    session.replies[0] = FakeResponse(400)
    with pytest.raises(CalendarError, match="token"):
        await cal.get_event("a")
