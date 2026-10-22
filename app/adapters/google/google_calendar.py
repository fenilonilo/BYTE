from __future__ import annotations

import hashlib
import time
import urllib.parse
from datetime import date, datetime, time as day_time, timedelta
from typing import TYPE_CHECKING, Any

import aiohttp

from app.domain.exceptions import CalendarError, EventNotFoundError
from app.domain.world import CalendarEvent
from app.ports.calendar import CalendarPort

if TYPE_CHECKING:
    from zoneinfo import ZoneInfo

API = "https://www.googleapis.com/calendar/v3/calendars"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105
OK = 200
CONFLICT = 409
GONE = (404, 410)


def event_id(key: str) -> str:
    """Hex is a subset of base32hex, the alphabet Google accepts for client-chosen ids.

    Short on purpose: the model reads ids back from list_events, and every character is a token.
    """
    return hashlib.sha256(key.encode()).hexdigest()[:20]


def parse_event(raw: dict[str, Any], tz: ZoneInfo) -> CalendarEvent:
    start = datetime.fromisoformat(raw["start"]["dateTime"]).astimezone(tz)
    end = datetime.fromisoformat(raw["end"]["dateTime"]).astimezone(tz)
    minutes = int((end - start).total_seconds() // 60)
    return CalendarEvent(raw["id"], raw.get("summary", ""), start, minutes)


class GoogleCalendar(CalendarPort):
    """Google Calendar REST API v3 with an OAuth refresh token (scope calendar.events)."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        calendar_id: str,
        tz: ZoneInfo,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._events_url = f"{API}/{urllib.parse.quote(calendar_id, safe='')}/events"
        self._tz = tz
        self._token = ""
        self._expires = 0.0
        self._session: aiohttp.ClientSession | None = None

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        return self._session

    async def _access_token(self) -> str:
        if time.monotonic() < self._expires:
            return self._token
        data = {
            "grant_type": "refresh_token",
            "refresh_token": self._refresh_token,
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }
        async with self._http().post(TOKEN_URL, data=data) as res:
            if res.status != OK:
                raise CalendarError(f"google token refresh failed: {res.status}")
            body = await res.json()
        self._token = body["access_token"]
        self._expires = time.monotonic() + body["expires_in"] - 30
        return self._token

    async def _call(
        self,
        method: str,
        path: str = "",
        params: dict[str, str] | None = None,
        body: object = None,
    ) -> tuple[int, dict[str, Any]]:
        try:
            headers = {"Authorization": f"Bearer {await self._access_token()}"}
            async with self._http().request(
                method, self._events_url + path, params=params, json=body, headers=headers
            ) as res:
                data: dict[str, Any] = (
                    await res.json() if res.content_type == "application/json" else {}
                )
                return res.status, data
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise CalendarError("google calendar unreachable") from exc

    async def _expect(
        self, method: str, path: str = "", params: dict[str, str] | None = None, body: object = None
    ) -> dict[str, Any]:
        status, data = await self._call(method, path, params, body)
        if status in GONE:
            raise EventNotFoundError(f"Unknown event: {path.lstrip('/')!r}")
        if status >= 400:  # noqa: PLR2004
            raise CalendarError(f"google calendar {status}")
        return data

    def _body(self, key: str, title: str, start: datetime, duration_minutes: int) -> dict[str, Any]:
        if start.tzinfo is None:
            start = start.replace(tzinfo=self._tz)
        end = start + timedelta(minutes=duration_minutes)
        return {
            "id": event_id(key),
            "summary": title,
            "status": "confirmed",
            "start": {"dateTime": start.isoformat(), "timeZone": self._tz.key},
            "end": {"dateTime": end.isoformat(), "timeZone": self._tz.key},
        }

    async def list_events(self, day: date) -> tuple[CalendarEvent, ...]:
        start = datetime.combine(day, day_time(), self._tz)
        params = {
            "timeMin": start.isoformat(),
            "timeMax": datetime.combine(day + timedelta(days=1), day_time(), self._tz).isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
        }
        # ponytail: first page only (250 events/day); follow nextPageToken if that ever bites
        data = await self._expect("GET", params=params)
        timed = (e for e in data.get("items", []) if "dateTime" in e.get("start", {}))
        return tuple(parse_event(e, self._tz) for e in timed)

    async def create_event(
        self, key: str, title: str, start: datetime, duration_minutes: int
    ) -> CalendarEvent:
        body = self._body(key, title, start, duration_minutes)
        status, data = await self._call("POST", body=body)
        if status == CONFLICT:
            existing = await self._expect("GET", f"/{body['id']}")
            if existing.get("status") != "cancelled":
                return parse_event(existing, self._tz)
            # A deleted event keeps its id forever; reusing the key brings it back.
            data = await self._expect("PUT", f"/{body['id']}", body=body)
        elif status >= 400:  # noqa: PLR2004
            raise CalendarError(f"google calendar {status}")
        return parse_event(data, self._tz)

    async def get_event(self, event_id: str) -> CalendarEvent:
        data = await self._expect("GET", f"/{urllib.parse.quote(event_id, safe='')}")
        if data.get("status") == "cancelled" or "dateTime" not in data.get("start", {}):
            raise EventNotFoundError(f"Unknown event: {event_id!r}")
        return parse_event(data, self._tz)

    async def delete_event(self, event_id: str) -> None:
        await self._expect("DELETE", f"/{urllib.parse.quote(event_id, safe='')}")

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
