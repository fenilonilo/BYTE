from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import aiohttp

from app.domain.exceptions import UnknownPlaceError, WeatherUnavailableError
from app.domain.weather import (
    WET,
    Condition,
    CurrentWeather,
    DailyForecast,
    Forecast,
    HourlyPoint,
    Place,
    fold,
)
from app.ports.weather import WeatherPort

if TYPE_CHECKING:
    from collections.abc import Callable

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_TTL = 600.0
HTTP_TIMEOUT = 4.0  # two calls in a row must fail before the 10 s tool timeout
HOURS = 24
OK = 200
FORECAST_PARAMS = {
    "timezone": "auto",
    "forecast_days": 7,
    "current": "temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,"
    "weather_code,wind_speed_10m,is_day",
    "hourly": "temperature_2m,precipitation_probability,weather_code,is_day",
    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
}

# WMO weather interpretation codes. Snow is folded into cloudy: Byte's owner lives in Brazil.
_CODES: dict[int, Condition] = {
    0: Condition.CLEAR,
    1: Condition.PARTLY_CLOUDY,
    2: Condition.PARTLY_CLOUDY,
    3: Condition.CLOUDY,
    45: Condition.FOG,
    48: Condition.FOG,
    **dict.fromkeys(range(51, 58), Condition.DRIZZLE),
    **dict.fromkeys((*range(61, 68), 80, 81, 82), Condition.RAIN),
    **dict.fromkeys(range(95, 100), Condition.STORM),
}


def condition(code: int) -> Condition:
    return _CODES.get(code, Condition.CLOUDY)


def _place(raw: dict[str, Any]) -> Place:
    return Place(
        str(raw["name"]),
        str(raw.get("admin1") or ""),
        str(raw.get("country") or ""),
        float(raw["latitude"]),
        float(raw["longitude"]),
    )


def _forecast(place: Place, body: dict[str, Any]) -> Forecast:
    tz = timezone(timedelta(seconds=int(body["utc_offset_seconds"])))
    cur = body["current"]
    now = condition(int(cur["weather_code"]))
    current = CurrentWeather(
        temperature=float(cur["temperature_2m"]),
        feels_like=float(cur["apparent_temperature"]),
        humidity=int(cur["relative_humidity_2m"]),
        wind_kmh=float(cur["wind_speed_10m"]),
        condition=now,
        raining=now in WET or float(cur.get("precipitation") or 0) > 0,
        is_day=bool(cur["is_day"]),
    )
    this_hour = datetime.fromisoformat(cur["time"]).replace(minute=0, tzinfo=tz)
    h = body["hourly"]
    points = (
        HourlyPoint(
            datetime.fromisoformat(t).replace(tzinfo=tz),
            float(temp),
            int(p or 0),
            condition(int(c)),
            bool(d),
        )
        for t, temp, p, c, d in zip(
            h["time"],
            h["temperature_2m"],
            h["precipitation_probability"],
            h["weather_code"],
            h["is_day"],
            strict=True,
        )
    )
    hours = tuple(p for p in points if p.time >= this_hour)[:HOURS]
    if len(hours) < HOURS:
        raise ValueError("fewer than 24 hours ahead")
    d = body["daily"]
    days = tuple(
        DailyForecast(date.fromisoformat(t), condition(int(c)), float(lo), float(hi), int(p or 0))
        for t, c, lo, hi, p in zip(
            d["time"],
            d["weather_code"],
            d["temperature_2m_min"],
            d["temperature_2m_max"],
            d["precipitation_probability_max"],
            strict=True,
        )
    )
    return Forecast(place, current, hours, days)


class OpenMeteoWeather(WeatherPort):
    """Open-Meteo forecast and geocoding: free, no key, no account."""

    def __init__(self, *, now: Callable[[], float] = time.monotonic) -> None:
        self._now = now
        self._session: aiohttp.ClientSession | None = None
        self._places: dict[str, Place] = {}
        # A rate guard for the panel's refreshes, not a source of truth.
        self._forecasts: dict[Place, tuple[float, Forecast]] = {}

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT))
        return self._session

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._http().get(url, params=params) as res:
                if res.status != OK:
                    raise WeatherUnavailableError(f"open-meteo answered {res.status}")
                body: dict[str, Any] = await res.json()
                return body
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise WeatherUnavailableError("open-meteo unreachable") from exc

    async def find_place(self, query: str) -> Place:
        key = fold(query)
        if key in self._places:
            return self._places[key]
        name, _, qualifier = query.partition(",")
        if not name.strip():
            raise UnknownPlaceError(query)
        body = await self._get(GEOCODE_URL, {"name": name.strip(), "count": 10, "language": "pt"})
        try:
            places = [_place(raw) for raw in body.get("results") or []]
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherUnavailableError("unreadable geocoding answer") from exc
        if qualifier.strip():
            places = [p for p in places if p.matches(qualifier)]
        if not places:
            raise UnknownPlaceError(query)
        self._places[key] = places[0]
        return places[0]

    async def forecast(self, place: Place) -> Forecast:
        cached = self._forecasts.get(place)
        if cached is not None and self._now() - cached[0] < FORECAST_TTL:
            return cached[1]
        params = {"latitude": place.latitude, "longitude": place.longitude, **FORECAST_PARAMS}
        body = await self._get(FORECAST_URL, params)
        try:
            result = _forecast(place, body)
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherUnavailableError("unreadable forecast answer") from exc
        self._forecasts[place] = (self._now(), result)
        return result
