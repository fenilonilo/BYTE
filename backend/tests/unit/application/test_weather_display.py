from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_weather import FLORIPA, GOIANIA, InMemoryWeather
from app.application.weather_display import WeatherDisplay, WeatherListener

if TYPE_CHECKING:
    from app.domain.weather import Place

pytestmark = pytest.mark.unit


class Recorder(WeatherListener):
    def __init__(self) -> None:
        self.calls = 0

    async def changed(self) -> None:
        self.calls += 1


class Broken(WeatherListener):
    async def changed(self) -> None:
        raise RuntimeError("socket gone")


class CountingWeather(InMemoryWeather):
    def __init__(self) -> None:
        super().__init__()
        self.lookups = 0

    async def find_place(self, query: str) -> Place:
        self.lookups += 1
        return await super().find_place(query)


def display() -> WeatherDisplay:
    return WeatherDisplay(InMemoryWeather(), "Goiânia, GO")


async def test_shows_home_by_default() -> None:
    assert await display().shown() == GOIANIA


async def test_show_switches_and_notifies() -> None:
    d, listener = display(), Recorder()
    d.attach(listener)
    await d.show(FLORIPA)
    assert await d.shown() == FLORIPA
    assert listener.calls == 1


async def test_showing_home_or_none_goes_back_home() -> None:
    d = display()
    await d.show(FLORIPA)
    await d.show(None)
    assert await d.shown() == GOIANIA
    await d.show(FLORIPA)
    await d.show(GOIANIA)
    assert await d.shown() == GOIANIA


async def test_home_is_resolved_once() -> None:
    weather = CountingWeather()
    d = WeatherDisplay(weather, "Goiânia, GO")
    await d.home()
    await d.home()
    assert weather.lookups == 1


async def test_a_failing_listener_does_not_break_show() -> None:
    d = display()
    d.attach(Broken())
    await d.show(FLORIPA)
    assert await d.shown() == FLORIPA


async def test_show_without_listener_works() -> None:
    d = display()
    await d.show(FLORIPA)
    assert await d.shown() == FLORIPA


async def test_detach_ignores_a_stale_listener() -> None:
    d, old, new = display(), Recorder(), Recorder()
    d.attach(old)
    d.attach(new)
    d.detach(old)
    await d.show(FLORIPA)
    assert (old.calls, new.calls) == (0, 1)
    d.detach(new)
    await d.show(None)
    assert new.calls == 1
