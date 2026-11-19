from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from app.ports.conversation_store import ConversationStorePort

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities import Message


class InMemoryConversationStore(ConversationStorePort):
    """LRU-bounded. `recent` and `append` both count as use."""

    def __init__(self, max_conversations: int = 50) -> None:
        self._max = max_conversations
        self._data: OrderedDict[str, list[Message]] = OrderedDict()

    async def recent(self, conversation_id: str, limit: int) -> tuple[Message, ...]:
        messages = self._data.get(conversation_id)
        if messages is None:
            return ()
        self._data.move_to_end(conversation_id)
        return tuple(messages[-limit:])

    async def append(self, conversation_id: str, messages: Sequence[Message]) -> None:
        self._data.setdefault(conversation_id, []).extend(messages)
        self._data.move_to_end(conversation_id)
        while len(self._data) > self._max:
            self._data.popitem(last=False)
