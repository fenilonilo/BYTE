from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.adapters.memory.in_memory_weather import FLORIPA, InMemoryWeather
from app.api import deps
from app.api.control import router
from app.api.errors import install_error_handlers
from app.api.live_slot import REPLACED_CLOSE_CODE, LiveSlot
from app.api.panel import router as panel_router
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.weather_display import WeatherDisplay
from app.domain.exceptions import WeatherUnavailableError
from tests.fakes.clock import FakeClock
from tests.fakes.logger import RecordingLogger
from tests.fakes.world import TOKEN, make_settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.domain.weather import Forecast, Place

pytestmark = pytest.mark.unit

P = "/api/v1"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
WS = P + "/ws/panel"
BEARER = ["bearer", TOKEN]


class DownWeather(InMemoryWeather):
    async def forecast(self, place: Place) -> Forecast:
        raise WeatherUnavailableError("open-meteo answered 503")


class NoGeocoding(InMemoryWeather):
    async def find_place(self, query: str) -> Place:
        raise WeatherUnavailableError("open-meteo unreachable")


class HomeDown(InMemoryWeather):
    async def forecast(self, place: Place) -> Forecast:
        if place.name == "Goiânia":
            raise WeatherUnavailableError("open-meteo answered 503")
        return await super().forecast(place)


def _provide(value: object) -> Callable[[], object]:
    return lambda: value


class Env:
    def __init__(self, weather: InMemoryWeather | None = None) -> None:
        weather = weather or InMemoryWeather()
        self.display = WeatherDisplay(weather, "Goiânia, GO")
        pending = PendingActionStore(FakeClock())
        registry = build_tool_registry(
            InMemoryLight(),
            InMemoryClimate(),
            InMemoryMusic(),
            InMemoryCalendar(),
            InMemoryExpenses(),
            weather=(weather, self.display),
        )
        runner = ToolRunner(registry, pending, RecordingLogger(), tool_timeout=10.0)
        app = FastAPI()
        app.include_router(router, prefix=P)
        app.include_router(panel_router, prefix=P)
        install_error_handlers(app)
        overrides: dict[Callable[..., object], object] = {
            deps.get_settings: make_settings(),
            deps.get_runner: runner,
            deps.get_pending: pending,
            deps.get_weather: weather,
            deps.get_weather_display: self.display,
            deps.get_panel_slot: LiveSlot(),
        }
        for dep, value in overrides.items():
            app.dependency_overrides[dep] = _provide(value)
        self.client = TestClient(app)

    def weather(self) -> dict[str, object]:
        res = self.client.get(P + "/weather", headers=AUTH)
        assert res.status_code == 200
        body: dict[str, object] = res.json()
        return body


def test_weather_home() -> None:
    body = Env().weather()
    assert body["is_home"] is True
    assert body["errors"] == []
    forecast = body["forecast"]
    assert isinstance(forecast, dict)
    assert forecast["place"]["label"] == "Goiânia, Goiás"  # pyright: ignore[reportUnknownMemberType]
    assert len(forecast["hours"]) == 24  # pyright: ignore[reportUnknownArgumentType]
    assert len(forecast["days"]) == 7  # pyright: ignore[reportUnknownArgumentType]
    assert body["home_now"] == forecast["current"]
    assert set(forecast["days"][0]) == {"day", "condition", "low", "high", "rain_chance"}  # pyright: ignore[reportUnknownArgumentType]


def test_hours_keep_the_place_offset() -> None:
    hours = Env().weather()["forecast"]["hours"]  # pyright: ignore[reportIndexIssue, reportOptionalSubscript, reportUnknownVariableType]
    assert hours[0]["time"].endswith("-03:00")  # pyright: ignore[reportUnknownMemberType]


def test_weather_after_show_weather() -> None:
    env = Env()
    asyncio.run(env.display.show(FLORIPA))
    body = env.weather()
    assert body["is_home"] is False
    assert body["forecast"]["place"]["name"] == "Florianópolis"  # pyright: ignore[reportIndexIssue, reportOptionalSubscript]
    assert body["home_now"] is not None


def test_delete_display_goes_home() -> None:
    env = Env()
    asyncio.run(env.display.show(FLORIPA))
    res = env.client.delete(P + "/weather/display", headers=AUTH)
    assert res.status_code == 200
    assert res.json()["is_home"] is True


def test_forecast_failure_is_partial() -> None:
    body = Env(DownWeather()).weather()
    assert body["forecast"] is None
    assert body["home_now"] is None
    assert body["errors"] == ["forecast", "home"]


def test_home_failure_alone_keeps_the_other_city() -> None:
    env = Env(HomeDown())
    asyncio.run(env.display.show(FLORIPA))
    body = env.weather()
    assert body["forecast"] is not None
    assert body["home_now"] is None
    assert body["errors"] == ["home"]


def test_geocoding_down_blanks_both() -> None:
    body = Env(NoGeocoding()).weather()
    assert (body["forecast"], body["home_now"], body["errors"]) == (
        None,
        None,
        ["forecast", "home"],
    )


def test_weather_requires_token() -> None:
    env = Env()
    assert env.client.get(P + "/weather").status_code == 401
    assert env.client.delete(P + "/weather/display").status_code == 401


def test_panel_socket_rejects_bad_token() -> None:
    env = Env()
    with (
        pytest.raises(WebSocketDisconnect),
        env.client.websocket_connect(WS, subprotocols=["bearer", "x" * 40]) as ws,
    ):
        ws.receive_json()


def test_show_pushes_weather_message() -> None:
    env = Env()
    with env.client.websocket_connect(WS, subprotocols=BEARER) as ws:
        ws.portal.call(env.display.show, FLORIPA)
        assert ws.receive_json() == {"type": "weather"}


def test_delete_display_pushes() -> None:
    env = Env()
    with env.client.websocket_connect(WS, subprotocols=BEARER) as ws:
        env.client.delete(P + "/weather/display", headers=AUTH)
        assert ws.receive_json() == {"type": "weather"}


def test_second_panel_replaces_first() -> None:
    env = Env()
    with (
        env.client.websocket_connect(WS, subprotocols=BEARER) as first,
        env.client.websocket_connect(WS, subprotocols=BEARER) as second,
    ):
        with pytest.raises(WebSocketDisconnect) as info:
            first.receive_json()
        assert info.value.code == REPLACED_CLOSE_CODE
        second.portal.call(env.display.show, FLORIPA)
        assert second.receive_json() == {"type": "weather"}
