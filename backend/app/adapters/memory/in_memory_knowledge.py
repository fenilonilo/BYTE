from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.domain.knowledge import SearchHit
from app.ports.knowledge import KnowledgeStorePort

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.knowledge import Chunk, DocumentRef


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0


class InMemoryKnowledge(KnowledgeStorePort):
    """Brute-force cosine over a dict. Unit tests, and the mode without a database."""

    def __init__(self) -> None:
        self._docs: dict[DocumentRef, tuple[str, str, tuple[tuple[Chunk, tuple[float, ...]], ...]]]
        self._docs = {}

    async def digest(self, ref: DocumentRef, model: str) -> str | None:
        doc = self._docs.get(ref)
        return doc[0] if doc is not None and doc[1] == model else None

    async def replace_document(
        self,
        ref: DocumentRef,
        digest: str,
        model: str,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        pairs = tuple((c, tuple(v)) for c, v in zip(chunks, vectors, strict=True))
        self._docs[ref] = (digest, model, pairs)

    async def remove_document(self, ref: DocumentRef) -> None:
        self._docs.pop(ref, None)

    async def documents(self) -> tuple[DocumentRef, ...]:
        return tuple(self._docs)

    async def search(
        self, vector: Sequence[float], model: str, k: int, project: str | None
    ) -> tuple[SearchHit, ...]:
        hits = [
            SearchHit(chunk, _cosine(vector, v))
            for ref, (_, doc_model, pairs) in self._docs.items()
            if doc_model == model and (project is None or ref.project == project)
            for chunk, v in pairs
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return tuple(hits[:k])
