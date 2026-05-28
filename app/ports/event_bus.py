from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.gestures import GestureEvent

GestureHandler = Callable[["GestureEvent"], Awaitable[None]]


class EventBusPort(ABC):
    @abstractmethod
    def subscribe(self, handler: GestureHandler) -> None: ...

    @abstractmethod
    async def publish(self, event: GestureEvent) -> None: ...
