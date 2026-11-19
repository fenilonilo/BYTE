from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Self

import aiohttp
import pytest

from app.adapters.openmeteo.open_meteo_weather import HTTP_TIMEOUT, OpenMeteoWeather, condition
from app.config import Settings
from app.domain.exceptions import UnknownPlaceError, WeatherUnavailableError
from app.domain.weather import Condition, Place
from tests.fakes.clock import FakeClock

pytestmark = pytest.mark.unit

GOIANIA = Place("Goiânia", "Goiás", "Brasil", -16.68, -49.25)


@dataclass
class FakeResponse:
    status: int
    body: dict[str, Any] = field(default_factory=dict[str, Any])

    async def json(self) -> dict[str, Any]:
        return self.body

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None


@dataclass
class FakeSession:
    replies: list[FakeResponse | Exception]
    calls: list[tuple[str, dict[str, Any]]] = field(
        default_factory=list[tuple[str, dict[str, Any]]]
    )

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def adapter(*replies: FakeResponse | Exception, clock: FakeClock | None = None) -> OpenMeteoWeather:
    weather = OpenMeteoWeather(now=clock or FakeClock())
    weather._session = FakeSession(list(replies))  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage]
    return weather


def calls(weather: OpenMeteoWeather) -> int:
    return len(weather._session.calls)  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage, reportOptionalMemberAccess, reportUnknownArgumentType, reportUnknownMemberType]


def forecast_body(
    *, now: str = "2026-10-23T08:15", code: int = 3, precipitation: float = 0.0
) -> dict[str, Any]:
    times = [f"2026-10-{23 + i // 24:02d}T{i % 24:02d}:00" for i in range(48)]
    return {
        "utc_offset_seconds": -10800,
        "current": {
            "time": now,
            "temperature_2m": 23.4,
            "apparent_temperature": 24.1,
            "relative_humidity_2m": 82,
            "precipitation": precipitation,
            "weather_code": code,
            "wind_speed_10m": 12.0,
            "is_day": 1,
        },
        "hourly": {
            "time": times,
            "temperature_2m": [20.0 + i % 10 for i in range(48)],
            "precipitation_probability": [None if i == 9 else i % 100 for i in range(48)],
            "weather_code": [61] * 48,
            "is_day": [1 if 6 <= i % 24 < 18 else 0 for i in range(48)],
        },
        "daily": {
            "time": [f"2026-10-{23 + i}" for i in range(7)],
            "weather_code": [0, 2, 3, 45, 51, 61, 95],
            "temperature_2m_max": [27.0 + i for i in range(7)],
            "temperature_2m_min": [17.0 + i for i in range(7)],
            "precipitation_probability_max": [80, 20, 0, 40, None, 10, 90],
        },
    }


def geo(*results: tuple[str, str, str]) -> FakeResponse:
    return FakeResponse(
        200,
        {
            "results": [
                {"name": n, "admin1": a, "country": c, "latitude": -29.7, "longitude": -53.8}
                for n, a, c in results
            ]
        },
    )


def test_condition_mapping() -> None:
    assert condition(0) is Condition.CLEAR
    assert condition(2) is Condition.PARTLY_CLOUDY
    assert condition(3) is Condition.CLOUDY
    assert condition(45) is Condition.FOG
    assert condition(53) is Condition.DRIZZLE
    assert condition(61) is Condition.RAIN
    assert condition(81) is Condition.RAIN
    assert condition(95) is Condition.STORM
    assert condition(73) is Condition.CLOUDY
    assert condition(1234) is Condition.CLOUDY


async def test_raining_from_precipitation_even_when_code_is_cloudy() -> None:
    f = await adapter(FakeResponse(200, forecast_body(code=3, precipitation=0.4))).forecast(GOIANIA)
    assert f.current.raining is True
    assert f.current.condition is Condition.CLOUDY


async def test_rain_code_without_precipitation_is_raining() -> None:
    f = await adapter(FakeResponse(200, forecast_body(code=61))).forecast(GOIANIA)
    assert f.current.raining is True


async def test_cloudy_and_dry_is_not_raining() -> None:
    f = await adapter(FakeResponse(200, forecast_body(code=3))).forecast(GOIANIA)
    assert f.current.raining is False


async def test_hours_start_at_current_hour_and_cross_midnight() -> None:
    f = await adapter(FakeResponse(200, forecast_body(now="2026-10-23T23:15"))).forecast(GOIANIA)
    assert len(f.hours) == 24
    assert f.hours[0].time.hour == 23
    assert f.hours[1].time.day == 24
    assert f.hours[0].time.utcoffset() == timedelta(hours=-3)


async def test_days_are_parsed() -> None:
    f = await adapter(FakeResponse(200, forecast_body())).forecast(GOIANIA)
    assert [d.condition for d in f.days][:3] == [
        Condition.CLEAR,
        Condition.PARTLY_CLOUDY,
        Condition.CLOUDY,
    ]
    assert (f.days[0].low, f.days[0].high, f.days[0].rain_chance) == (17.0, 27.0, 80)


async def test_null_rain_chance_is_zero() -> None:
    f = await adapter(FakeResponse(200, forecast_body())).forecast(GOIANIA)
    assert f.hours[1].rain_chance == 0  # hour 09:00 is null in the body
    assert f.days[4].rain_chance == 0


async def test_qualifier_picks_the_matching_state() -> None:
    weather = adapter(
        geo(
            ("Santa Maria", "Distrito Federal", "Brasil"),
            ("Santa Maria", "Rio Grande do Sul", "Brasil"),
        )
    )
    place = await weather.find_place("Santa Maria, RS")
    assert place.region == "Rio Grande do Sul"


async def test_without_qualifier_takes_the_first_result() -> None:
    weather = adapter(
        geo(
            ("Santa Maria", "Distrito Federal", "Brasil"),
            ("Santa Maria", "Rio Grande do Sul", "Brasil"),
        )
    )
    assert (await weather.find_place("Santa Maria")).region == "Distrito Federal"


async def test_unknown_qualifier_raises() -> None:
    weather = adapter(geo(("Santa Maria", "Rio Grande do Sul", "Brasil")))
    with pytest.raises(UnknownPlaceError):
        await weather.find_place("Santa Maria, AM")


async def test_no_results_raises_unknown_place() -> None:
    with pytest.raises(UnknownPlaceError):
        await adapter(FakeResponse(200, {"generationtime_ms": 0.1})).find_place("Xyzzyqwvk")


async def test_places_are_cached() -> None:
    weather = adapter(geo(("Goiânia", "Goiás", "Brasil")))
    await weather.find_place("Goiânia")
    await weather.find_place("goiania")
    assert calls(weather) == 1


async def test_forecast_is_cached_for_ten_minutes() -> None:
    clock = FakeClock()
    body = forecast_body()
    weather = adapter(FakeResponse(200, body), FakeResponse(200, body), clock=clock)
    await weather.forecast(GOIANIA)
    clock.advance(599)
    await weather.forecast(GOIANIA)
    assert calls(weather) == 1
    clock.advance(2)
    await weather.forecast(GOIANIA)
    assert calls(weather) == 2


async def test_http_status_becomes_unavailable() -> None:
    with pytest.raises(WeatherUnavailableError):
        await adapter(FakeResponse(500)).forecast(GOIANIA)


async def test_network_error_becomes_unavailable() -> None:
    with pytest.raises(WeatherUnavailableError) as info:
        await adapter(aiohttp.ClientConnectionError("down")).forecast(GOIANIA)
    assert isinstance(info.value.__cause__, aiohttp.ClientError)


async def test_unreadable_body_becomes_unavailable() -> None:
    with pytest.raises(WeatherUnavailableError):
        await adapter(FakeResponse(200, {"current": {}})).forecast(GOIANIA)


def test_geocoding_plus_forecast_fit_inside_the_tool_timeout() -> None:
    # A cold lookup makes two calls in a row; both must fail before ToolRunner gives up,
    # or the owner hears "estado desconhecido" instead of "Previsão indisponível agora."
    tool_timeout = Settings.model_fields["tool_timeout_seconds"].default
    assert tool_timeout > 2 * HTTP_TIMEOUT
