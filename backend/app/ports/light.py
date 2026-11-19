from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.light import LightChange, LightState


class LightPort(ABC):
    """Smart lights by device name. Unknown name -> UnknownLightDeviceError."""

    @abstractmethod
    async def devices(self) -> tuple[str, ...]: ...

    @abstractmethod
    async def get_state(self, device: str) -> LightState: ...

    @abstractmethod
    async def apply(self, device: str, change: LightChange) -> LightState:
        """Apply a partial change and return the resulting state."""
