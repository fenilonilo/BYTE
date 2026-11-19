from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from app.domain.exceptions import UnknownPlaceError
from app.domain.weather import (
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
    from collections.abc import Sequence

GOIANIA = Place("Goiânia", "Goiás", "Brasil", -16.68, -49.25)
FLORIPA = Place("Florianópolis", "Santa Catarina", "Brasil", -27.6, -48.55)
START = datetime(2026, 10, 23, 8, tzinfo=timezone(timedelta(hours=-3)))
FIRST_DAY = date(2026, 10, 23)
DAYLIGHT = range(6, 18)


class InMemoryWeather(WeatherPort):
    """Fixed, deterministic weather for tests."""

    def __init__(
        self, places: Sequence[Place] = (GOIANIA, FLORIPA), *, raining: bool = False
    ) -> None:
        self._places = tuple(places)
        self._raining = raining

    async def find_place(self, query: str) -> Place:
        name, _, qualifier = query.partition(",")
        for place in self._places:
            if fold(place.name) == fold(name) and (
                not qualifier.strip() or place.matches(qualifier)
            ):
                return place
        raise UnknownPlaceError(query)

    async def forecast(self, place: Place) -> Forecast:
        now = Condition.RAIN if self._raining else Condition.PARTLY_CLOUDY
        current = CurrentWeather(23.0, 24.0, 82, 12.0, now, self._raining, is_day=True)
        hours = tuple(
            HourlyPoint(
                START + timedelta(hours=i),
                20.0 + i % 8,
                (i * 7) % 100,
                now,
                (8 + i) % 24 in DAYLIGHT,
            )
            for i in range(24)
        )
        days = tuple(
            DailyForecast(
                FIRST_DAY + timedelta(days=i), now, 17.0 + i % 3, 26.0 + i % 5, (i * 20) % 100
            )
            for i in range(7)
        )
        return Forecast(place, current, hours, days)
