from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

import pytest

from app.domain.exceptions import UnknownPlaceError

if TYPE_CHECKING:
    from app.ports.weather import WeatherPort


class WeatherPortContract(ABC):
    """Every WeatherPort adapter must pass this. `make()` must know Goiânia."""

    @abstractmethod
    def make(self) -> WeatherPort: ...

    async def test_finds_home_by_name(self) -> None:
        assert (await self.make().find_place("Goiânia")).name == "Goiânia"

    async def test_accents_and_case_do_not_matter(self) -> None:
        weather = self.make()
        home = await weather.find_place("Goiânia")
        assert await weather.find_place("goiania") == home
        assert await weather.find_place("GOIÂNIA") == home

    async def test_qualifier_after_comma(self) -> None:
        weather = self.make()
        assert await weather.find_place("Goiânia, GO") == await weather.find_place("Goiânia")

    async def test_unknown_place_raises(self) -> None:
        with pytest.raises(UnknownPlaceError):
            await self.make().find_place("Xyzzyqwvk")

    async def test_forecast_shape(self) -> None:
        weather = self.make()
        place = await weather.find_place("Goiânia")
        f = await weather.forecast(place)
        assert f.place == place
        assert len(f.days) == 7
        assert all(a.day < b.day for a, b in zip(f.days, f.days[1:], strict=False))
        assert len(f.hours) == 24
        assert all(a.time < b.time for a, b in zip(f.hours, f.hours[1:], strict=False))
        assert all(h.time.tzinfo is not None for h in f.hours)
        assert all(d.low <= d.high for d in f.days)
        chances = [d.rain_chance for d in f.days] + [h.rain_chance for h in f.hours]
        assert all(0 <= c <= 100 for c in chances)
