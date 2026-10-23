from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.domain.reminders import Reminder, ReminderKind, calendar_warnings, spoken_time
from app.domain.world import CalendarEvent

NOON = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def make(at: datetime, expires_at: datetime | None = None) -> Reminder:
    return Reminder("r1", "pagar a luz", at, ReminderKind.REMINDER, expires_at)


def test_due_once_its_time_arrives() -> None:
    reminder = make(NOON)
    assert not reminder.is_due(NOON - timedelta(seconds=1))
    assert reminder.is_due(NOON)
    assert reminder.is_due(NOON + timedelta(hours=3))  # late delivery still counts


def test_expires_only_with_an_expiry() -> None:
    assert not make(NOON).is_expired(NOON + timedelta(days=30))
    warning = make(NOON, expires_at=NOON + timedelta(minutes=10))
    assert not warning.is_expired(NOON + timedelta(minutes=9))
    assert warning.is_expired(NOON + timedelta(minutes=10))


def test_calendar_warnings_fire_before_start_and_expire_at_start() -> None:
    event = CalendarEvent("evt1", "dentista", NOON, 60)
    (warning,) = calendar_warnings((event,), timedelta(minutes=10))
    assert warning.at == NOON - timedelta(minutes=10)
    assert warning.expires_at == NOON
    assert warning.kind is ReminderKind.REMINDER
    assert warning.text == "dentista, às 12 horas"
    assert warning.is_calendar


def test_a_moved_event_gets_a_new_warning_id() -> None:
    lead = timedelta(minutes=10)
    (before,) = calendar_warnings((CalendarEvent("evt1", "x", NOON, 30),), lead)
    (after,) = calendar_warnings((CalendarEvent("evt1", "x", NOON + timedelta(hours=1), 30),), lead)
    assert before.id != after.id


def test_user_reminders_are_not_calendar_warnings() -> None:
    assert not make(NOON).is_calendar


def test_spoken_time_reads_minutes_as_words() -> None:
    assert spoken_time(NOON.replace(hour=15, minute=30)) == "às 15 e 30"
    assert spoken_time(NOON.replace(hour=9)) == "às 9 horas"
