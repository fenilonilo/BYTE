from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

from app.domain.exceptions import DomainError
from app.domain.knowledge import HEADING_SEPARATOR, DocumentRef, content_hash, split_markdown

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from app.domain.knowledge import Chunk
    from app.domain.projects import Project
    from app.ports.documents import DocumentSourcePort
    from app.ports.embedder import EmbedderPort
    from app.ports.knowledge import KnowledgeStorePort
    from app.ports.logger import LoggerPort


def _embedding_text(chunk: Chunk) -> str:
    # the project and heading path carry most of the meaning of a short section
    title = HEADING_SEPARATOR.join(p for p in (chunk.ref.project, chunk.heading) if p)
    return f"{title}\n{chunk.text}"


class KnowledgeIndexer:
    """Keeps the store in step with the registered documents; never forgets what it cannot see."""

    def __init__(
        self,
        projects: Sequence[Project],
        source: DocumentSourcePort,
        embedder: EmbedderPort,
        store: KnowledgeStorePort,
        log: LoggerPort,
    ) -> None:
        self._projects = tuple(projects)
        self._source = source
        self._embedder = embedder
        self._store = store
        self._log = log

    async def scan(self) -> None:
        started = time.monotonic()
        wanted = {DocumentRef(p.name, doc) for p in self._projects for doc in p.docs}
        for ref in await self._store.documents():
            if ref not in wanted:
                await self._store.remove_document(ref)
        changed = 0
        for project in self._projects:
            if not await self._source.reachable(project.path):
                continue
            for doc in project.docs:
                try:
                    changed += await self._sync(project, DocumentRef(project.name, doc))
                except DomainError as exc:
                    self._log.warning(
                        "knowledge.doc_failed",
                        project=project.name,
                        rel_path=doc,
                        error=type(exc).__name__,
                    )
        self._log.info(
            "knowledge.scanned",
            changed=changed,
            duration_ms=round((time.monotonic() - started) * 1000),
        )

    async def _sync(self, project: Project, ref: DocumentRef) -> int:
        text = await self._source.read(str(Path(project.path) / ref.rel_path))
        if text is None:
            await self._store.remove_document(ref)
            return 1
        digest = content_hash(text)
        model = self._embedder.model
        if await self._store.digest(ref, model) == digest:
            return 0
        chunks = split_markdown(ref, text)
        vectors = await self._embedder.embed([_embedding_text(c) for c in chunks]) if chunks else ()
        await self._store.replace_document(ref, digest, model, chunks, vectors)
        self._log.info("knowledge.indexed", project=ref.project, chunks=len(chunks))
        return 1


async def run_indexer(
    indexer: KnowledgeIndexer,
    every: float,
    log: LoggerPort,
    *,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Background loop of the lifespan: scan now, then every `every` seconds."""
    # ponytail: polling by hash; a file watcher if minutes of staleness ever matter
    while True:
        try:
            await indexer.scan()
        except Exception as exc:  # the loop must outlive any one scan
            log.error("knowledge.scan_failed", error=type(exc).__name__)
        await sleep(every)
