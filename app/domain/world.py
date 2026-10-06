from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime
    duration_minutes: int


@dataclass(frozen=True, slots=True)
class Expense:
    key: str
    amount_cents: int
    category: str
    description: str
    day: date
