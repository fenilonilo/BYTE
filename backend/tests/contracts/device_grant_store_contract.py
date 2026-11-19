from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.domain.device_grant import DeviceGrant

if TYPE_CHECKING:
    from app.ports.device_grants import DeviceGrantStorePort

AT = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


class DeviceGrantStoreContract(ABC):
    """Every DeviceGrantStorePort adapter must pass this. `make()` returns an empty store."""

    @abstractmethod
    def make(self) -> DeviceGrantStorePort: ...

    async def test_put_then_get_round_trips(self) -> None:
        store = self.make()
        grant = DeviceGrant("h1", AT, AT + timedelta(days=1))
        await store.put(grant)
        assert await store.get("h1") == grant
        assert await store.get("h2") is None

    async def test_put_same_hash_replaces(self) -> None:
        store = self.make()
        await store.put(DeviceGrant("h1", AT, AT))
        await store.put(DeviceGrant("h1", AT, AT + timedelta(days=3)))
        got = await store.get("h1")
        assert got is not None
        assert got.last_used_at == AT + timedelta(days=3)

    async def test_remove_forgets_and_unknown_is_quiet(self) -> None:
        store = self.make()
        await store.put(DeviceGrant("h1", AT, AT))
        await store.remove("h1")
        await store.remove("never")
        assert await store.get("h1") is None
