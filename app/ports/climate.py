from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.climate import ClimateChange, ClimateState


class ClimatePort(ABC):
    """Air conditioners by device name. Unknown name -> UnknownClimateDeviceError."""

    @abstractmethod
    async def devices(self) -> tuple[str, ...]: ...

    @abstractmethod
    async def get_state(self, device: str) -> ClimateState: ...

    @abstractmethod
    async def apply(self, device: str, change: ClimateChange) -> ClimateState:
        """Apply a partial change and return the resulting state."""
