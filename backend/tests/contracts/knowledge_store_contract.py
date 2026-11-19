from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.domain.knowledge import Chunk, DocumentRef
from tests.fakes.embedder import fake_vector

if TYPE_CHECKING:
    from app.ports.knowledge import KnowledgeStorePort

BYTE = DocumentRef("Byte", "CLAUDE.md")
FIN = DocumentRef("FinFlow", "CLAUDE.md")
MODEL = "fake"


def chunks(ref: DocumentRef, *texts: str) -> tuple[Chunk, ...]:
    return tuple(Chunk(ref, i, f"h{i}", t) for i, t in enumerate(texts))


def vectors(*texts: str) -> tuple[tuple[float, ...], ...]:
    return tuple(fake_vector(t) for t in texts)


class KnowledgeStoreContract(ABC):
    """Every KnowledgeStorePort adapter must pass this. `make()` returns an empty store."""

    @abstractmethod
    def make(self) -> KnowledgeStorePort: ...

    async def _put(
        self, store: KnowledgeStorePort, ref: DocumentRef, *texts: str, model: str = MODEL
    ) -> None:
        await store.replace_document(ref, f"d-{texts}", model, chunks(ref, *texts), vectors(*texts))

    async def test_replace_then_digest(self) -> None:
        store = self.make()
        await self._put(store, BYTE, "a")
        assert await store.digest(BYTE, MODEL) == "d-('a',)"

    async def test_digest_none_for_unknown_or_other_model(self) -> None:
        store = self.make()
        assert await store.digest(BYTE, MODEL) is None
        await self._put(store, BYTE, "a")
        assert await store.digest(BYTE, "other") is None

    async def test_replace_swaps_old_chunks(self) -> None:
        store = self.make()
        await self._put(store, BYTE, "velho um", "velho dois")
        await self._put(store, BYTE, "novo")
        hits = await store.search(fake_vector("velho um"), MODEL, 10, None)
        assert [h.chunk.text for h in hits] == ["novo"]

    async def test_round_trips_chunk_fields(self) -> None:
        store = self.make()
        await self._put(store, BYTE, "texto")
        (hit,) = await store.search(fake_vector("texto"), MODEL, 1, None)
        assert hit.chunk == Chunk(BYTE, 0, "h0", "texto")
        assert abs(hit.score - 1.0) < 1e-5

    async def test_remove_document(self) -> None:
        store = self.make()
        await self._put(store, BYTE, "a")
        await store.remove_document(BYTE)
        assert await store.documents() == ()
        assert await store.search(fake_vector("a"), MODEL, 4, None) == ()

    async def test_remove_unknown_is_noop(self) -> None:
        await self.make().remove_document(BYTE)

    async def test_documents_lists_refs(self) -> None:
        store = self.make()
        await self._put(store, FIN, "a")
        await self._put(store, BYTE, "b")
        assert sorted(await store.documents(), key=lambda r: r.project) == [BYTE, FIN]

    async def test_search_orders_by_similarity(self) -> None:
        store = self.make()
        await self._put(store, BYTE, "um", "dois", "três")
        hits = await store.search(fake_vector("dois"), MODEL, 2, None)
        assert hits[0].chunk.text == "dois"
        assert len(hits) == 2
        assert hits[0].score >= hits[1].score

    async def test_search_filters_project(self) -> None:
        store = self.make()
        await self._put(store, BYTE, "a")
        await self._put(store, FIN, "a")
        hits = await store.search(fake_vector("a"), MODEL, 4, "FinFlow")
        assert [h.chunk.ref for h in hits] == [FIN]

    async def test_search_ignores_other_model(self) -> None:
        store = self.make()
        await self._put(store, BYTE, "a", model="other")
        assert await store.search(fake_vector("a"), MODEL, 4, None) == ()

    async def test_search_empty_store(self) -> None:
        assert await self.make().search(fake_vector("a"), MODEL, 4, None) == ()
