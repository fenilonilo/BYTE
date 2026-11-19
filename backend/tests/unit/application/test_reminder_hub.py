from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.adapters.files.json_reminder_store import JsonReminderStore
from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.application.reminder_hub import ReminderHub, ReminderListener
from app.domain.exceptions import SpeechError
from app.domain.reminders import Reminder, ReminderKind
from app.ports.speech import SpeechPort
from tests.fakes.logger import RecordingLogger

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
MINUTE = timedelta(minutes=1)


class EchoSpeech(SpeechPort):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    async def synthesize(self, text: str) -> bytes:
        if self.fail:
            raise SpeechError("boom")
        return text.encode()


class Device(ReminderListener):
    def __init__(self) -> None:
        self.got: list[tuple[str, ReminderKind, bytes]] = []

    async def push(self, reminder: Reminder, audio: bytes) -> None:
        self.got.append((reminder.id, reminder.kind, audio))


class Harness:
    def __init__(self, tmp_path: Path, speech: SpeechPort | None = None) -> None:
        self.store = JsonReminderStore(tmp_path / "r.json")
        self.calendar = InMemoryCalendar()
        self.log = RecordingLogger()
        self.hub = ReminderHub(self.store, speech or EchoSpeech(), self.calendar, self.log)

    async def ids(self) -> list[str]:
        return [r.id for r in await self.store.all()]


@pytest.fixture
def h(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


def due(rid: str = "r1", at: datetime = NOW, expires: datetime | None = None) -> Reminder:
    return Reminder(rid, "pagar a luz", at, ReminderKind.REMINDER, expires)


@pytest.mark.unit
async def test_due_reminder_is_spoken_on_the_device(h: Harness) -> None:
    device = Device()
    h.hub.attach(device)
    await h.store.put(due())
    await h.store.put(due("later", NOW + MINUTE))
    await h.hub.tick(NOW)
    assert device.got == [("r1", ReminderKind.REMINDER, b"pagar a luz")]


@pytest.mark.unit
async def test_sent_once_per_connection_until_acked(h: Harness) -> None:
    device = Device()
    h.hub.attach(device)
    await h.store.put(due())
    await h.hub.tick(NOW)
    await h.hub.tick(NOW + MINUTE)
    assert len(device.got) == 1
    await h.hub.ack("r1")
    assert await h.ids() == []


@pytest.mark.unit
async def test_unacked_reminder_is_sent_again_on_reconnect(h: Harness) -> None:
    first, second = Device(), Device()
    h.hub.attach(first)
    await h.store.put(due())
    await h.hub.tick(NOW)
    h.hub.detach(first)
    h.hub.attach(second)
    await h.hub.tick(NOW)
    assert [g[0] for g in second.got] == ["r1"]


@pytest.mark.unit
async def test_offline_reminder_waits_and_is_delivered_late(h: Harness) -> None:
    await h.store.put(due())
    await h.hub.tick(NOW)
    assert await h.ids() == ["r1"]
    device = Device()
    h.hub.attach(device)
    await h.hub.tick(NOW + timedelta(hours=3))
    assert [g[0] for g in device.got] == ["r1"]


@pytest.mark.unit
async def test_expired_reminders_are_dropped_unspoken(h: Harness) -> None:
    device = Device()
    h.hub.attach(device)
    await h.store.put(due(expires=NOW))
    await h.hub.tick(NOW)
    assert device.got == []
    assert await h.ids() == []


@pytest.mark.unit
async def test_detach_of_a_replaced_listener_keeps_the_new_one(h: Harness) -> None:
    old, new = Device(), Device()
    h.hub.attach(old)
    h.hub.attach(new)
    h.hub.detach(old)
    await h.store.put(due())
    await h.hub.tick(NOW)
    assert len(new.got) == 1


@pytest.mark.unit
async def test_speech_failure_still_rings_without_words(tmp_path: Path) -> None:
    h = Harness(tmp_path, EchoSpeech(fail=True))
    device = Device()
    h.hub.attach(device)
    await h.store.put(due())
    await h.hub.tick(NOW)
    assert device.got == [("r1", ReminderKind.REMINDER, b"")]
    assert "reminders.speech_failed" in h.log.names()


@pytest.mark.unit
async def test_ack_of_unknown_id_is_ignored(h: Harness) -> None:
    await h.hub.ack("nope")


@pytest.mark.unit
async def test_calendar_event_is_warned_ten_minutes_before(h: Harness) -> None:
    await h.calendar.create_event("k", "dentista", NOW + timedelta(minutes=30), 60)
    await h.hub.sync_calendar(NOW)
    device = Device()
    h.hub.attach(device)
    await h.hub.tick(NOW + timedelta(minutes=19))
    assert device.got == []
    await h.hub.tick(NOW + timedelta(minutes=20))
    assert device.got[0][2] == "dentista, às 12 e 30".encode()


@pytest.mark.unit
async def test_an_acked_calendar_warning_is_not_recreated_by_the_next_sync(h: Harness) -> None:
    await h.calendar.create_event("k", "dentista", NOW + timedelta(minutes=5), 60)
    await h.hub.sync_calendar(NOW)
    (warning,) = await h.ids()
    await h.hub.ack(warning)
    await h.hub.sync_calendar(NOW + MINUTE)
    assert await h.ids() == []


@pytest.mark.unit
async def test_sync_drops_warnings_of_deleted_events_and_keeps_user_reminders(
    h: Harness,
) -> None:
    event = await h.calendar.create_event("k", "dentista", NOW + timedelta(minutes=30), 60)
    await h.store.put(due("mine", NOW + timedelta(hours=1)))
    await h.hub.sync_calendar(NOW)
    assert len(await h.ids()) == 2
    await h.calendar.delete_event(event.id)
    await h.hub.sync_calendar(NOW + MINUTE)
    assert await h.ids() == ["mine"]


@pytest.mark.unit
async def test_sync_reads_tomorrow_too_and_skips_started_events(h: Harness) -> None:
    late = datetime(2026, 10, 21, 23, 55, tzinfo=UTC)
    await h.calendar.create_event("a", "virada", late + timedelta(minutes=10), 30)
    await h.calendar.create_event("b", "passou", late - timedelta(hours=1), 30)
    await h.hub.sync_calendar(late)
    (only,) = await h.store.all()
    assert only.text.startswith("virada")
