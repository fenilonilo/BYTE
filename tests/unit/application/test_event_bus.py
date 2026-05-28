from __future__ import annotations

import pytest

from app.application.event_bus import InProcessEventBus
from app.domain.gestures import GestureEvent, GestureParams


def _event(name: str) -> GestureEvent:
    return GestureEvent(gesture=name, phase="instant", hands=1, params=GestureParams(), ts=0.0)


@pytest.mark.asyncio
async def test_publish_fans_out_to_all_subscribers() -> None:
    bus = InProcessEventBus()
    seen_a: list[str] = []
    seen_b: list[str] = []

    async def a(ev: GestureEvent) -> None:
        seen_a.append(ev.gesture)

    async def b(ev: GestureEvent) -> None:
        seen_b.append(ev.gesture)

    bus.subscribe(a)
    bus.subscribe(b)
    await bus.publish(_event("pinch"))

    assert seen_a == ["pinch"]
    assert seen_b == ["pinch"]


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_is_noop() -> None:
    bus = InProcessEventBus()
    await bus.publish(_event("swipe"))


@pytest.mark.asyncio
async def test_one_failing_subscriber_does_not_block_others() -> None:
    bus = InProcessEventBus()
    seen: list[str] = []

    async def bad(ev: GestureEvent) -> None:
        raise RuntimeError("boom")

    async def good(ev: GestureEvent) -> None:
        seen.append(ev.gesture)

    bus.subscribe(bad)
    bus.subscribe(good)
    await bus.publish(_event("freeze"))

    assert seen == ["freeze"]
