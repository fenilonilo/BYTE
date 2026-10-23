from __future__ import annotations

from abc import ABC, abstractmethod


class DocumentSourcePort(ABC):
    """Where the documents to index live (the local disk today)."""

    @abstractmethod
    async def reachable(self, root: str) -> bool:
        """Whether a project folder can be seen from here at all."""

    @abstractmethod
    async def read(self, path: str) -> str | None:
        """UTF-8 text, or None when the file does not exist. Other failures: KnowledgeError."""
