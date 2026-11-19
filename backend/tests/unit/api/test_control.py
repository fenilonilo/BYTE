from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.files.json_reminder_store import JsonReminderStore
from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.api import deps
from app.api.control import router
from app.api.errors import install_error_handlers
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.tools.music import KnownUris
from app.domain.exceptions import LightError, MusicError, MusicOfflineError
from app.domain.reminders import calendar_warnings
from app.domain.world import CalendarEvent
from tests.fakes.clock import FakeClock
from tests.fakes.logger import RecordingLogger
from tests.fakes.world import TOKEN, make_settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from httpx2 import Response  # what starlette's TestClient returns since 1.x

    from app.domain.light import LightChange, LightState
    from app.domain.music import MediaKind, MusicItem, PlaybackState

AUTH = {"Authorization": f"Bearer {TOKEN}"}
P = "/api/v1"


class FailingMusic(InMemoryMusic):
    async def search(self, query: str, kind: MediaKind) -> tuple[MusicItem, ...]:
        raise MusicError("spotify fora do ar")

    async def state(self) -> PlaybackState:
        raise MusicError("spotify fora do ar")


class OfflineMusic(InMemoryMusic):
    async def play(self, uri: str | None = None, device: str | None = None) -> PlaybackState:
        raise MusicOfflineError("BatCaverna está offline no Spotify. Abra o Spotify nele.")

    async def select_device(self, name: str) -> None:
        raise MusicOfflineError("BatCaverna está offline no Spotify. Abra o Spotify nele.")


class OfflineLight(InMemoryLight):
    async def get_state(self, device: str) -> LightState:
        raise LightError("lampada fora da rede")


class SlowLight(InMemoryLight):
    async def apply(self, device: str, change: LightChange) -> LightState:
        await asyncio.sleep(0.2)
        return await super().apply(device, change)


def _provide(value: object) -> Callable[[], object]:
    # not `lambda value=value`: FastAPI deep-copies parameter defaults
    return lambda: value


class Panel:
    def __init__(
        self,
        music: InMemoryMusic | None = None,
        light: InMemoryLight | None = None,
        tool_timeout: float = 10.0,
    ) -> None:
        self.clock = FakeClock()
        self.log = RecordingLogger()
        self.pending = PendingActionStore(self.clock)
        known = KnownUris()
        climate, calendar, expenses = InMemoryClimate(), InMemoryCalendar(), InMemoryExpenses()
        music = music or InMemoryMusic()
        light = light or InMemoryLight()
        self.reminders = JsonReminderStore(Path(tempfile.mkdtemp()) / "r.json")
        registry = build_tool_registry(
            light,
            climate,
            music,
            calendar,
            expenses,
            known=known,
            reminders=(self.reminders, lambda: NOW),
        )
        runner = ToolRunner(registry, self.pending, self.log, tool_timeout=tool_timeout)
        app = FastAPI()
        app.include_router(router, prefix=P)
        install_error_handlers(app)
        overrides: dict[Callable[..., object], object] = {
            deps.get_settings: make_settings(),
            deps.get_runner: runner,
            deps.get_pending: self.pending,
            deps.get_light: light,
            deps.get_climate: climate,
            deps.get_music: music,
            deps.get_calendar: calendar,
            deps.get_expenses: expenses,
            deps.get_known_uris: known,
            deps.get_reminder_store: self.reminders,
        }
        for dep, value in overrides.items():
            app.dependency_overrides[dep] = _provide(value)
        self.client = TestClient(app)

    def get(self, url: str) -> Response:
        return self.client.get(P + url, headers=AUTH)

    def send(self, method: str, url: str, json: object = None) -> Response:
        return self.client.request(method, P + url, json=json, headers=AUTH)


EXPENSE = {
    "amount_cents": 5000,
    "category": "mercado",
    "description": "feira",
    "date": "2026-10-02",
}
EVENT = {"title": "Dentista", "start": "2026-10-06T15:00:00-03:00", "duration_minutes": 30}
MONTH = "/finance/expenses?year=2026&month=10"
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone(timedelta(hours=-3)))


@pytest.mark.unit
@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("GET", "/state"),
        ("GET", "/lights"),
        ("PATCH", "/lights/lampada"),
        ("GET", "/music/search?q=a"),
        ("DELETE", "/agenda/evt-1"),
        ("GET", "/reminders"),
        ("DELETE", "/reminders/abc"),
        ("POST", "/confirm"),
    ],
)
def test_every_route_needs_the_token(method: str, url: str) -> None:
    assert Panel().client.request(method, P + url).status_code == 401


@pytest.mark.unit
def test_lights_list_and_set() -> None:
    panel = Panel()
    lights = panel.get("/lights").json()["lights"]
    assert (lights[0]["name"], lights[0]["power"]) == ("lampada", False)
    res = panel.send("PATCH", "/lights/lampada", {"power": True, "brightness": 40})
    assert res.status_code == 200
    assert res.json()["status"] == "done"
    state = panel.get("/lights").json()["lights"][0]
    assert (state["power"], state["brightness"]) == (True, 40)


@pytest.mark.unit
def test_unknown_light_unknown_field_and_empty_body_are_422() -> None:
    panel = Panel()
    assert (
        Panel(light=InMemoryLight(("lampada", "quarto")))
        .send("PATCH", "/lights/cofre", {"power": True})
        .status_code
        == 422
    )
    assert panel.send("PATCH", "/lights/lampada", {"device_id": "x"}).status_code == 422
    assert panel.send("PATCH", "/lights/lampada", {}).status_code == 422


@pytest.mark.unit
def test_lamp_toggles_back_and_forth_from_the_panel() -> None:
    panel = Panel()
    assert panel.send("PATCH", "/lights/lampada", {"power": True}).status_code == 200
    assert panel.send("PATCH", "/lights/lampada", {"power": False}).status_code == 200


@pytest.mark.unit
def test_climate_adjustment_while_off_is_422() -> None:
    res = Panel().send("PATCH", "/climate/ar-condicionado", {"target_temperature": 22})
    assert res.status_code == 422
    assert "desligado" in res.json()["detail"]


@pytest.mark.unit
def test_climate_power_and_adjust_run_without_asking() -> None:
    panel = Panel()
    assert panel.send("PATCH", "/climate/ar-condicionado", {"power": True}).json()["status"] == (
        "done"
    )
    ok = panel.send("PATCH", "/climate/ar-condicionado", {"target_temperature": 22})
    assert ok.json()["status"] == "done"
    panel.send("PATCH", "/climate/ar-condicionado", {"power": False})
    assert panel.get("/climate").json()["climates"][0]["power"] is False


@pytest.mark.unit
def test_confirm_runs_the_pending_action_once() -> None:
    panel = Panel()
    panel.send("POST", "/finance/expenses", EXPENSE)
    done = panel.send("POST", "/confirm", {"approve": True})
    assert (done.status_code, done.json()["status"]) == (200, "done")
    assert panel.get(MONTH).json()["total_cents"] == 5000
    assert panel.send("POST", "/confirm", {"approve": True}).status_code == 409


@pytest.mark.unit
def test_cancel_drops_the_pending_action() -> None:
    panel = Panel()
    panel.send("POST", "/finance/expenses", EXPENSE)
    assert panel.send("POST", "/confirm", {"approve": False}).json()["status"] == "cancelled"
    assert panel.send("POST", "/confirm", {"approve": True}).status_code == 409


@pytest.mark.unit
def test_any_other_action_drops_the_pending_one() -> None:
    panel = Panel()
    panel.send("POST", "/finance/expenses", EXPENSE)
    panel.send("PATCH", "/lights/lampada", {"brightness": 10})
    assert panel.send("POST", "/confirm", {"approve": True}).status_code == 409
    assert panel.get(MONTH).json()["expenses"] == []


@pytest.mark.unit
def test_pending_expires_after_60_seconds() -> None:
    panel = Panel()
    panel.send("POST", "/finance/expenses", EXPENSE)
    panel.clock.t += 61
    assert panel.send("POST", "/confirm", {"approve": True}).status_code == 409


@pytest.mark.unit
def test_resending_an_action_does_not_confirm_it() -> None:
    panel = Panel()
    panel.send("POST", "/finance/expenses", EXPENSE)
    again = panel.send("POST", "/finance/expenses", EXPENSE)
    assert again.json()["status"] == "pending_confirmation"
    assert panel.get(MONTH).json()["total_cents"] == 0


@pytest.mark.unit
def test_reads_do_not_drop_the_pending_action() -> None:
    panel = Panel()
    panel.send("POST", "/finance/expenses", EXPENSE)
    panel.get("/state")
    panel.get("/lights")
    assert panel.send("POST", "/confirm", {"approve": True}).json()["status"] == "done"


@pytest.mark.unit
def test_expense_flow_and_listing() -> None:
    panel = Panel()
    asked = panel.send("POST", "/finance/expenses", EXPENSE).json()
    assert asked["pending_confirmation"]["summary"].startswith("Registrar gasto de R$ 50,00")
    panel.send("POST", "/confirm", {"approve": True})
    listed = panel.get(MONTH).json()
    assert listed["total_cents"] == 5000
    assert listed["expenses"] == [EXPENSE]


@pytest.mark.unit
def test_invalid_expense_and_month_are_422() -> None:
    panel = Panel()
    assert (
        panel.send("POST", "/finance/expenses", {**EXPENSE, "amount_cents": 0}).status_code == 422
    )
    assert panel.send("POST", "/finance/expenses", {**EXPENSE, "date": "x"}).status_code == 422
    assert panel.get("/finance/expenses?year=2026&month=13").status_code == 422


@pytest.mark.unit
def test_agenda_create_list_and_delete_asks() -> None:
    panel = Panel()
    assert panel.send("POST", "/agenda", EVENT).json()["status"] == "done"
    events = panel.get("/agenda?date=2026-10-06").json()["events"]
    assert (events[0]["title"], events[0]["duration_minutes"]) == ("Dentista", 30)
    asked = panel.send("DELETE", f"/agenda/{events[0]['id']}").json()
    assert asked["status"] == "pending_confirmation"
    assert asked["pending_confirmation"]["summary"] == 'Apagar o evento "Dentista"'
    assert panel.get("/agenda?date=2026-10-06").json()["events"]
    panel.send("POST", "/confirm", {"approve": True})
    assert panel.get("/agenda?date=2026-10-06").json()["events"] == []


@pytest.mark.unit
def test_deleting_an_unknown_event_is_422_before_any_pending_action() -> None:
    panel = Panel()
    assert panel.send("DELETE", "/agenda/evt-9").status_code == 422
    assert panel.send("POST", "/confirm", {"approve": True}).status_code == 409


@pytest.mark.unit
def test_reminders_create_list_and_cancel_without_asking() -> None:
    panel = Panel()
    alarm = {"text": "acordar", "at": "2026-10-07T07:00:00-03:00", "kind": "alarme"}
    created = panel.send("POST", "/reminders", alarm).json()
    assert created["status"] == "done"
    [listed] = panel.get("/reminders").json()["reminders"]
    assert (listed["text"], listed["kind"]) == ("acordar", "alarme")
    assert panel.send("DELETE", f"/reminders/{listed['id']}").json()["status"] == "done"
    assert panel.get("/reminders").json()["reminders"] == []


@pytest.mark.unit
def test_reminder_in_the_past_unknown_kind_and_unknown_id_are_422() -> None:
    panel = Panel()
    past = {"text": "x", "at": "2026-10-06T11:00:00-03:00", "kind": "lembrete"}
    assert panel.send("POST", "/reminders", past).status_code == 422
    assert panel.send("POST", "/reminders", {**past, "kind": "sirene"}).status_code == 422
    assert panel.send("DELETE", "/reminders/nada").status_code == 422


@pytest.mark.unit
def test_reminder_list_hides_calendar_warnings() -> None:
    panel = Panel()
    [warning] = calendar_warnings(
        [CalendarEvent("evt-1", "Dentista", NOW + timedelta(hours=1), 30)], timedelta(minutes=10)
    )
    asyncio.run(panel.reminders.put(warning))
    assert panel.get("/reminders").json()["reminders"] == []


@pytest.mark.unit
def test_music_search_play_control() -> None:
    panel = Panel()
    items = panel.get("/music/search?q=aquarela").json()["items"]
    assert items[0]["uri"] == "spotify:track:2"
    assert panel.send("POST", "/music/play", {"uri": items[0]["uri"]}).json()["status"] == "done"
    assert panel.get("/music/state").json()["item"]["name"] == "Aquarela"
    assert panel.send("POST", "/music/control", {"volume": 30}).status_code == 200
    assert panel.send("POST", "/music/control", {"paused": True}).status_code == 200
    state = panel.get("/music/state").json()
    assert (state["volume"], state["playing"]) == (30, False)


@pytest.mark.unit
def test_music_play_refuses_a_uri_no_search_returned() -> None:
    assert Panel().send("POST", "/music/play", {"uri": "spotify:track:1"}).status_code == 422


@pytest.mark.unit
def test_playlists_make_their_uris_playable() -> None:
    panel = Panel()
    uri = panel.get("/music/playlists").json()["items"][0]["uri"]
    assert panel.send("POST", "/music/play", {"uri": uri}).status_code == 200


@pytest.mark.unit
def test_state_snapshot() -> None:
    body = Panel().get("/state").json()
    assert body["lights"][0]["name"] == "lampada"
    assert body["climates"][0]["name"] == "ar-condicionado"
    assert body["music"]["device"] == "nest mini"
    assert body["pending_confirmation"] is None
    assert body["errors"] == []


@pytest.mark.unit
def test_state_isolates_a_failing_section() -> None:
    body = Panel(FailingMusic()).get("/state").json()
    assert body["music"] is None
    assert body["errors"] == ["music"]
    assert body["lights"]


@pytest.mark.unit
def test_an_offline_device_is_listed_as_unavailable() -> None:
    panel = Panel(light=OfflineLight())
    body = panel.get("/state").json()
    assert [(x["name"], x["available"], x["power"]) for x in body["lights"]] == [
        ("lampada", False, False)
    ]
    assert body["climates"][0]["available"] is True
    assert body["errors"] == []
    assert panel.get("/lights").json()["lights"][0]["available"] is False


@pytest.mark.unit
def test_state_shows_the_pending_summary() -> None:
    panel = Panel()
    panel.send("POST", "/agenda", EVENT)
    panel.send("DELETE", "/agenda/evt-1")
    assert panel.get("/state").json()["pending_confirmation"] == {
        "summary": 'Apagar o evento "Dentista"'
    }


@pytest.mark.unit
def test_failing_read_is_a_generic_500() -> None:
    res = Panel(FailingMusic()).get("/music/search?q=x")
    assert (res.status_code, res.json()) == (500, {"detail": "Internal error"})


@pytest.mark.unit
def test_timeout_is_504_estado_desconhecido() -> None:
    res = Panel(light=SlowLight(), tool_timeout=0.01).send(
        "PATCH", "/lights/lampada", {"power": True}
    )
    assert res.status_code == 504
    assert res.json()["detail"].startswith("estado desconhecido")


@pytest.mark.unit
def test_no_content_reaches_the_logs() -> None:
    panel = Panel()
    panel.send("POST", "/finance/expenses", {**EXPENSE, "description": "SEGREDO-XYZ"})
    panel.send("POST", "/confirm", {"approve": True})
    assert "SEGREDO-XYZ" not in repr(panel.log.events)


@pytest.mark.unit
def test_music_devices_list_and_select() -> None:
    panel = Panel(InMemoryMusic(("nest mini", "cozinha")))
    body = panel.get("/music/devices").json()
    assert body["default"] == (make_settings().spotify_device or None)
    assert body["devices"][0] == {"name": "nest mini", "active": True, "volume": 50}
    res = panel.send("POST", "/music/device", {"name": "Cozinha"})
    assert (res.status_code, res.json()["status"]) == (200, "done")
    assert panel.get("/music/state").json()["device"] == "cozinha"


@pytest.mark.unit
def test_music_device_unknown_name_is_422_in_portuguese() -> None:
    res = Panel().send("POST", "/music/device", {"name": "garagem"})
    assert res.status_code == 422
    assert res.json()["detail"] == "Aparelho desconhecido: garagem"
    assert Panel().send("POST", "/music/device", {"name": ""}).status_code == 422


@pytest.mark.unit
def test_offline_device_is_a_clear_422_for_play_and_select() -> None:
    panel = Panel(OfflineMusic())
    for method, url, body in (
        ("POST", "/music/play", {}),
        ("POST", "/music/device", {"name": "nest mini"}),
    ):
        res = panel.send(method, url, body)
        assert res.status_code == 422
        assert "offline no Spotify" in res.json()["detail"]
