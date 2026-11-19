from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.device_grant import DeviceGrant


class DeviceGrantStorePort(ABC):
    """Signed-in devices, keyed by the hash of their refresh token; survives restarts."""

    @abstractmethod
    async def get(self, token_hash: str) -> DeviceGrant | None:
        """The grant for this hash, or None."""

    @abstractmethod
    async def put(self, grant: DeviceGrant) -> None:
        """Insert, or replace the grant with the same hash."""

    @abstractmethod
    async def remove(self, token_hash: str) -> None:
        """Forget the grant; an unknown hash is not an error."""
