from __future__ import annotations


class FakeClock:
    """Injectable monotonic clock: tests advance time instead of sleeping."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds
