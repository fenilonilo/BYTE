from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.domain.entities import Message

if TYPE_CHECKING:
    from app.ports.conversation_store import ConversationStorePort

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def msg(n: int, role: str = "user") -> Message:
    return Message(id=f"m{n}", role=role, content=f"text {n}", timestamp=NOW)


class ConversationStorePortContract(ABC):
    """Every ConversationStorePort adapter must pass this. `make()` returns an empty store."""

    @abstractmethod
    def make(self) -> ConversationStorePort: ...

    async def test_unknown_conversation_is_empty(self) -> None:
        assert await self.make().recent("nope", 20) == ()

    async def test_append_creates_and_preserves_order(self) -> None:
        store = self.make()
        await store.append("c1", [msg(1), msg(2, "assistant")])
        await store.append("c1", [msg(3)])
        assert [m.id for m in await store.recent("c1", 20)] == ["m1", "m2", "m3"]

    async def test_recent_returns_only_the_last_n(self) -> None:
        store = self.make()
        await store.append("c1", [msg(i) for i in range(1, 6)])
        assert [m.id for m in await store.recent("c1", 2)] == ["m4", "m5"]

    async def test_conversations_are_isolated(self) -> None:
        store = self.make()
        await store.append("a", [msg(1)])
        await store.append("b", [msg(2)])
        assert [m.id for m in await store.recent("a", 20)] == ["m1"]
