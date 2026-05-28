from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.ports.event_bus import EventBusPort, GestureHandler

if TYPE_CHECKING:
    from app.domain.gestures import GestureEvent


class InProcessEventBus(EventBusPort):
    def __init__(self) -> None:
        self._handlers: list[GestureHandler] = []

    def subscribe(self, handler: GestureHandler) -> None:
        self._handlers.append(handler)

    async def publish(self, event: GestureEvent) -> None:
        # Failing subscribers must not break the fan-out; they are swallowed here.
        await asyncio.gather(*(h(event) for h in self._handlers), return_exceptions=True)
