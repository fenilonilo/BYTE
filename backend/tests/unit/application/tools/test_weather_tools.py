from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_weather import FLORIPA, GOIANIA, InMemoryWeather
from app.application.tools.weather import GetWeather, ShowWeather
from app.application.weather_display import WeatherDisplay
from app.domain.exceptions import ToolArgumentError, WeatherUnavailableError

if TYPE_CHECKING:
    from app.domain.weather import Forecast, Place

pytestmark = pytest.mark.unit


class DownWeather(InMemoryWeather):
    async def forecast(self, place: Place) -> Forecast:
        raise WeatherUnavailableError("open-meteo answered 503")


def tools(weather: InMemoryWeather | None = None) -> tuple[GetWeather, ShowWeather, WeatherDisplay]:
    weather = weather or InMemoryWeather()
    display = WeatherDisplay(weather, "Goiânia, GO")
    return GetWeather(weather, display), ShowWeather(weather, display), display


async def test_get_weather_defaults_to_home_and_three_days() -> None:
    get, _, _ = tools()
    lines = (await get.execute({}, "k")).splitlines()
    assert lines[0] == (
        "Goiânia, Goiás — agora 23°C (sensação 24°), sem chuva, umidade 82%, vento 12 km/h."
    )
    assert lines[1:] == [
        "hoje: 17-26°, chuva 0%, parcialmente nublado",
        "sáb: 18-27°, chuva 20%, parcialmente nublado",
        "dom: 19-28°, chuva 40%, parcialmente nublado",
    ]


async def test_get_weather_other_city_does_not_change_the_panel() -> None:
    get, _, display = tools()
    text = await get.execute({"city": "Florianópolis"}, "k")
    assert text.startswith("Florianópolis, Santa Catarina — agora")
    assert await display.shown() == GOIANIA


async def test_get_weather_says_raining() -> None:
    get, _, _ = tools(InMemoryWeather(raining=True))
    first = (await get.execute({}, "k")).splitlines()[0]
    assert ", chovendo," in first


async def test_days_bounds() -> None:
    get, _, _ = tools()
    for bad in (0, 8):
        with pytest.raises(ToolArgumentError):
            await get.execute({"days": bad}, "k")
    assert len((await get.execute({"days": 7}, "k")).splitlines()) == 8


async def test_unknown_city_is_reported_not_raised() -> None:
    get, show, display = tools()
    assert await get.execute({"city": "Xyzzyqwvk"}, "k") == "Não encontrei a cidade Xyzzyqwvk."
    assert await show.execute({"city": "Xyzzyqwvk"}, "k") == "Não encontrei a cidade Xyzzyqwvk."
    assert await display.shown() == GOIANIA


async def test_unavailable_is_reported_not_raised() -> None:
    get, _, _ = tools(DownWeather())
    assert await get.execute({}, "k") == "Previsão indisponível agora."


async def test_show_weather_switches_the_panel() -> None:
    _, show, display = tools()
    assert await show.execute({"city": "Florianópolis"}, "k") == (
        "Painel mostrando Florianópolis, Santa Catarina."
    )
    assert await display.shown() == FLORIPA


async def test_show_weather_without_city_goes_home() -> None:
    _, show, display = tools()
    await display.show(FLORIPA)
    assert await show.execute({}, "k") == "Painel de volta para Goiânia, Goiás."
    assert await display.shown() == GOIANIA


async def test_show_weather_home_by_name_goes_home() -> None:
    _, show, display = tools()
    await display.show(FLORIPA)
    assert await show.execute({"city": "goiania"}, "k") == "Painel de volta para Goiânia, Goiás."
    assert await display.shown() == GOIANIA


def test_weather_tools_need_no_confirmation_and_are_not_panel_only() -> None:
    for tool in tools()[:2]:
        assert tool.spec.segment == "weather"
        assert tool.spec.requires_confirmation is False
        assert tool.spec.panel_only is False
