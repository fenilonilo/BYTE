from __future__ import annotations

from app.adapters.memory.in_memory_knowledge import InMemoryKnowledge
from tests.contracts.knowledge_store_contract import KnowledgeStoreContract


class TestInMemoryKnowledge(KnowledgeStoreContract):
    def make(self) -> InMemoryKnowledge:
        return InMemoryKnowledge()
