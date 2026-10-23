from __future__ import annotations

from datetime import UTC, datetime

WALL = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def wall() -> datetime:
    return WALL


class FakeClock:
    """Injectable monotonic clock: tests advance time instead of sleeping."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds
