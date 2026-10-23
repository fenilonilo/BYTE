from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters.memory.in_memory_knowledge import InMemoryKnowledge
from app.application.knowledge_indexer import KnowledgeIndexer, run_indexer
from app.domain.exceptions import KnowledgeError
from app.domain.knowledge import DocumentRef
from app.domain.projects import Project
from app.ports.documents import DocumentSourcePort
from tests.fakes.embedder import FakeEmbedder, fake_vector
from tests.fakes.logger import RecordingLogger

ROOT = "D:/P/Byte"
DOC = str(Path(ROOT) / "CLAUDE.md")
REF = DocumentRef("Byte", "CLAUDE.md")
PROJECT = Project("Byte", ROOT, ("CLAUDE.md",))


class FakeSource(DocumentSourcePort):
    def __init__(self) -> None:
        self.roots: set[str] = {ROOT}
        self.files: dict[str, str] = {DOC: "# Byte\nloopback"}
        self.broken: set[str] = set()

    async def reachable(self, root: str) -> bool:
        return root in self.roots

    async def read(self, path: str) -> str | None:
        if path in self.broken:
            raise KnowledgeError("locked")
        return self.files.get(path)


class World:
    def __init__(self, projects: tuple[Project, ...] = (PROJECT,)) -> None:
        self.source = FakeSource()
        self.embedder = FakeEmbedder()
        self.store = InMemoryKnowledge()
        self.log = RecordingLogger()
        self.projects = projects

    def indexer(self, embedder: FakeEmbedder | None = None) -> KnowledgeIndexer:
        return KnowledgeIndexer(
            self.projects, self.source, embedder or self.embedder, self.store, self.log
        )

    async def texts(self, model: str = "fake") -> list[str]:
        hits = await self.store.search(fake_vector("x"), model, 50, None)
        return sorted(h.chunk.text for h in hits)


@pytest.mark.unit
async def test_new_doc_is_indexed() -> None:
    w = World()
    await w.indexer().scan()
    assert await w.store.documents() == (REF,)
    assert await w.texts() == ["loopback"]


@pytest.mark.unit
async def test_unchanged_doc_is_not_reembedded() -> None:
    w = World()
    indexer = w.indexer()
    await indexer.scan()
    calls = w.embedder.calls
    await indexer.scan()
    assert w.embedder.calls == calls


@pytest.mark.unit
async def test_changed_doc_is_reindexed() -> None:
    w = World()
    indexer = w.indexer()
    await indexer.scan()
    w.source.files[DOC] = "# Byte\nnovo"
    await indexer.scan()
    assert await w.texts() == ["novo"]


@pytest.mark.unit
async def test_unreachable_project_keeps_index() -> None:
    w = World()
    await w.indexer().scan()
    w.source.roots.clear()
    w.source.files.clear()
    await w.indexer().scan()
    assert await w.store.documents() == (REF,)


@pytest.mark.unit
async def test_missing_file_in_reachable_project_is_removed() -> None:
    w = World()
    await w.indexer().scan()
    del w.source.files[DOC]
    await w.indexer().scan()
    assert await w.store.documents() == ()


@pytest.mark.unit
async def test_doc_dropped_from_config_is_removed() -> None:
    w = World()
    await w.indexer().scan()
    w.projects = ()
    await w.indexer().scan()
    assert await w.store.documents() == ()


@pytest.mark.unit
async def test_model_change_reembeds() -> None:
    w = World()
    await w.indexer().scan()
    await w.indexer(FakeEmbedder(model="other")).scan()
    assert await w.texts("other") == ["loopback"]


@pytest.mark.unit
async def test_one_failing_doc_does_not_stop_others() -> None:
    other = Project("Fin", "D:/P/Fin", ("CLAUDE.md",))
    w = World((other, PROJECT))
    w.source.roots.add(other.path)
    w.source.files[str(Path(other.path) / "CLAUDE.md")] = "# Fin\nfin"
    w.source.broken.add(str(Path(other.path) / "CLAUDE.md"))
    await w.indexer().scan()
    assert await w.store.documents() == (REF,)
    assert "knowledge.doc_failed" in w.log.names()


@pytest.mark.unit
async def test_read_error_keeps_index() -> None:
    w = World()
    await w.indexer().scan()
    w.source.broken.add(DOC)
    await w.indexer().scan()
    assert await w.store.documents() == (REF,)


@pytest.mark.unit
async def test_empty_doc_is_stored_without_chunks() -> None:
    w = World()
    w.source.files[DOC] = ""
    await w.indexer().scan()
    assert await w.store.documents() == (REF,)
    assert await w.texts() == []


@pytest.mark.unit
async def test_run_indexer_survives_scan_error() -> None:
    w = World()
    scans = 0

    class Flaky(KnowledgeIndexer):
        async def scan(self) -> None:
            nonlocal scans
            scans += 1
            if scans == 1:
                raise KnowledgeError("db down")

    sleeps: list[float] = []

    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopAsyncIteration

    indexer = Flaky(w.projects, w.source, w.embedder, w.store, w.log)
    with pytest.raises(StopAsyncIteration):
        await run_indexer(indexer, 300, w.log, sleep=sleep)
    assert scans == 2
    assert sleeps == [300, 300]
    assert "knowledge.scan_failed" in w.log.names()
