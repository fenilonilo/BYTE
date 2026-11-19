from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.adapters.files.json_reminder_store import JsonReminderStore
from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.silent_speech import SilentSpeech
from app.api.deps import get_notify_slot, get_reminder_hub, get_settings, get_wall_clock
from app.api.live_slot import LiveSlot
from app.api.notifications import SYNC_EVERY_TICKS, router, run_reminders
from app.application.reminder_hub import ReminderHub
from app.domain.reminders import Reminder, ReminderKind
from tests.fakes.logger import RecordingLogger
from tests.fakes.world import TOKEN, make_settings

if TYPE_CHECKING:
    from pathlib import Path

URL = "/api/v1/ws/notifications"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


class Env:
    def __init__(self, tmp_path: Path) -> None:
        self.store = JsonReminderStore(tmp_path / "r.json")
        self.log = RecordingLogger()
        self.hub = ReminderHub(self.store, SilentSpeech(), InMemoryCalendar(), self.log)
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.dependency_overrides[get_settings] = make_settings
        app.dependency_overrides[get_reminder_hub] = lambda: self.hub
        app.dependency_overrides[get_notify_slot] = LiveSlot
        app.dependency_overrides[get_wall_clock] = lambda: lambda: NOW
        self.client = TestClient(app)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def put(env: Env, rid: str = "r1", kind: ReminderKind = ReminderKind.ALARM) -> None:
    asyncio.run(env.store.put(Reminder(rid, "acordar", NOW - timedelta(minutes=1), kind)))


@pytest.mark.unit
def test_missing_token_closes_the_socket(env: Env) -> None:
    with pytest.raises(WebSocketDisconnect), env.client.websocket_connect(URL) as ws:
        ws.receive_json()


@pytest.mark.unit
def test_backlog_is_pushed_on_connect_and_ack_removes_it(env: Env) -> None:
    put(env)
    with env.client.websocket_connect(URL, headers=AUTH) as ws:
        assert ws.receive_json() == {"type": "reminder", "id": "r1", "kind": "alarme"}
        assert ws.receive_bytes() == b""
        ws.send_text("not json")
        ws.send_text(json.dumps({"type": "ack", "id": "../../etc"}))
        ws.send_text(json.dumps({"type": "ack", "id": "r1"}))
        ws.send_text(json.dumps({"type": "ping"}))
    assert asyncio.run(env.store.all()) == ()


@pytest.mark.unit
def test_unacked_reminder_comes_back_on_reconnect(env: Env) -> None:
    put(env)
    for _ in range(2):
        with env.client.websocket_connect(URL, headers=AUTH) as ws:
            assert ws.receive_json()["id"] == "r1"
            ws.receive_bytes()


class StopLoopError(Exception):
    pass


class FlakyHub(ReminderHub):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(
            JsonReminderStore(tmp_path / "r.json"),
            SilentSpeech(),
            InMemoryCalendar(),
            RecordingLogger(),
        )
        self.calls: list[str] = []

    async def tick(self, now: datetime) -> None:
        self.calls.append("tick")
        raise RuntimeError("bad data")

    async def sync_calendar(self, now: datetime) -> None:
        self.calls.append("sync")


@pytest.mark.unit
async def test_loop_ticks_every_round_syncs_every_five_minutes_and_survives_errors(
    tmp_path: Path,
) -> None:
    hub, log = FlakyHub(tmp_path), RecordingLogger()
    rounds = 0

    async def sleep(seconds: float) -> None:
        nonlocal rounds
        rounds += 1
        if rounds > SYNC_EVERY_TICKS:
            raise StopLoopError

    with pytest.raises(StopLoopError):
        await run_reminders(hub, lambda: NOW, log, sleep=sleep)
    assert hub.calls.count("sync") == 2
    assert hub.calls.count("tick") == SYNC_EVERY_TICKS + 1
    assert log.names().count("reminders.failed") == SYNC_EVERY_TICKS + 1
