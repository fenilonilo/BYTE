from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.knowledge import Chunk, DocumentRef, SearchHit


class KnowledgeStorePort(ABC):
    """Indexed document chunks and their vectors. Survives without access to the files."""

    @abstractmethod
    async def digest(self, ref: DocumentRef, model: str) -> str | None:
        """Stored content hash, only if the document was embedded with `model`."""

    @abstractmethod
    async def replace_document(
        self,
        ref: DocumentRef,
        digest: str,
        model: str,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        """Atomically drop the document's old chunks and store these."""

    @abstractmethod
    async def remove_document(self, ref: DocumentRef) -> None:
        """Forget a document; an unknown one is a no-op."""

    @abstractmethod
    async def documents(self) -> tuple[DocumentRef, ...]:
        """Every stored document."""

    @abstractmethod
    async def search(
        self, vector: Sequence[float], model: str, k: int, project: str | None
    ) -> tuple[SearchHit, ...]:
        """Top `k` chunks of `model` by cosine similarity, best first."""
