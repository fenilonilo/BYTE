from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest

from app.adapters.files.json_reminder_store import JsonReminderStore
from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.tools.catalog import build_tool_registry
from app.application.tools.reminders import CancelReminder, CreateReminder, ListReminders
from app.domain.exceptions import ReminderNotFoundError, ToolArgumentError
from app.domain.reminders import Reminder, ReminderKind
from tests.fakes.clock import WALL, wall

if TYPE_CHECKING:
    from pathlib import Path

BRT = timezone(timedelta(hours=-3))
LOCAL_NOW = WALL.astimezone(BRT)


@pytest.fixture
def store(tmp_path: Path) -> JsonReminderStore:
    return JsonReminderStore(tmp_path / "reminders.json")


def create(store: JsonReminderStore) -> CreateReminder:
    return CreateReminder(store, lambda: LOCAL_NOW)


@pytest.mark.unit
async def test_create_stores_an_alarm(store: JsonReminderStore) -> None:
    args = {"text": "acordar", "at": "2026-10-22T06:30:00-03:00", "kind": "alarme"}
    out = await create(store).execute(args, "k1")
    (saved,) = await store.all()
    assert saved.kind is ReminderKind.ALARM
    assert saved.at == datetime(2026, 10, 22, 9, 30, tzinfo=UTC)
    assert saved.expires_at is None
    assert out == f"alarme {saved.id} 22/10 06:30"


@pytest.mark.unit
async def test_create_reads_a_naive_time_in_the_owner_zone(store: JsonReminderStore) -> None:
    args = {"text": "pagar a luz", "at": "2026-10-22T09:00:00", "kind": "lembrete"}
    await create(store).execute(args, "k1")
    (saved,) = await store.all()
    assert saved.at == datetime(2026, 10, 22, 9, 0, tzinfo=BRT)


@pytest.mark.unit
async def test_create_is_idempotent_per_key(store: JsonReminderStore) -> None:
    args = {"text": "x", "at": "2026-10-22T09:00:00", "kind": "lembrete"}
    await create(store).execute(args, "same")
    await create(store).execute(args, "same")
    assert len(await store.all()) == 1


@pytest.mark.unit
@pytest.mark.parametrize(
    "args",
    [
        {"text": "x", "at": "2026-10-21T08:00:00", "kind": "lembrete"},  # already past
        {"text": "x", "at": "amanhã", "kind": "lembrete"},
        {"text": "x", "at": "2026-10-22T09:00:00", "kind": "soneca"},
        {"text": " ", "at": "2026-10-22T09:00:00", "kind": "lembrete"},
    ],
)
async def test_create_rejects_bad_arguments(
    store: JsonReminderStore, args: dict[str, object]
) -> None:
    with pytest.raises(ToolArgumentError):
        await create(store).execute(args, "k1")


@pytest.mark.unit
async def test_list_shows_user_reminders_in_local_time_and_hides_calendar_warnings(
    store: JsonReminderStore,
) -> None:
    await store.put(Reminder("r1", "pagar a luz", WALL, ReminderKind.REMINDER))
    await store.put(Reminder("cal-e1-1", "Daqui a 10 minutos: x", WALL, ReminderKind.REMINDER))
    out = await ListReminders(store, wall).execute({}, "k")
    assert out == "r1: 21/10 12:00 lembrete pagar a luz"


@pytest.mark.unit
async def test_list_empty(tmp_path: Path) -> None:
    out = await ListReminders(JsonReminderStore(tmp_path / "r.json"), wall).execute({}, "k")
    assert out == "nenhum lembrete"


@pytest.mark.unit
async def test_cancel_removes_and_unknown_raises(store: JsonReminderStore) -> None:
    await store.put(Reminder("r1", "x", WALL, ReminderKind.ALARM))
    assert await CancelReminder(store).execute({"id": "r1"}, "k") == "r1 cancelado"
    assert await store.all() == ()
    with pytest.raises(ReminderNotFoundError):
        await CancelReminder(store).execute({"id": "r1"}, "k")


@pytest.mark.unit
def test_catalog_registers_reminder_tools_in_agenda(store: JsonReminderStore) -> None:
    registry = build_tool_registry(
        InMemoryLight(),
        InMemoryClimate(),
        InMemoryMusic(),
        InMemoryCalendar(),
        InMemoryExpenses(),
        reminders=(store, wall),
    )
    names = {"create_reminder", "list_reminders", "cancel_reminder"}
    assert {t.spec.segment for t in registry.values() if t.spec.name in names} == {"agenda"}
    assert names <= {t.spec.name for t in registry.values()}
