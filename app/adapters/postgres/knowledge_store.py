from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.postgres import schema
from app.domain.exceptions import KnowledgeError
from app.domain.knowledge import Chunk, DocumentRef, SearchHit
from app.ports.knowledge import KnowledgeStorePort

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Sequence

    from sqlalchemy import ColumnElement
    from sqlalchemy.ext.asyncio import AsyncConnection

DOCS = schema.documents
CHUNKS = schema.chunks


def _match(ref: DocumentRef) -> tuple[ColumnElement[bool], ...]:
    return (DOCS.c.project == ref.project, DOCS.c.rel_path == ref.rel_path)


class PostgresKnowledge(KnowledgeStorePort):
    """pgvector store. Cosine distance, brute force: a few hundred rows need no index."""

    def __init__(self, url: str) -> None:
        self._engine = create_async_engine(url, pool_pre_ping=True)

    @asynccontextmanager
    async def _tx(self) -> AsyncGenerator[AsyncConnection]:
        try:
            async with self._engine.begin() as conn:
                yield conn
        except (SQLAlchemyError, OSError) as exc:
            raise KnowledgeError("knowledge store failed") from exc

    async def digest(self, ref: DocumentRef, model: str) -> str | None:
        query = select(DOCS.c.digest).where(*_match(ref), DOCS.c.model == model)
        async with self._tx() as conn:
            row = (await conn.execute(query)).first()
        return None if row is None else str(row[0])

    async def replace_document(
        self,
        ref: DocumentRef,
        digest: str,
        model: str,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
    ) -> None:
        key = {"project": ref.project, "rel_path": ref.rel_path}
        rows = [
            {
                **key,
                "ordinal": c.ordinal,
                "heading": c.heading,
                "text": c.text,
                "embedding": list(v),
            }
            for c, v in zip(chunks, vectors, strict=True)
        ]
        async with self._tx() as conn:
            await conn.execute(delete(DOCS).where(*_match(ref)))  # cascades to its chunks
            await conn.execute(insert(DOCS).values(**key, digest=digest, model=model))
            if rows:
                await conn.execute(insert(CHUNKS), rows)

    async def remove_document(self, ref: DocumentRef) -> None:
        async with self._tx() as conn:
            await conn.execute(delete(DOCS).where(*_match(ref)))

    async def documents(self) -> tuple[DocumentRef, ...]:
        async with self._tx() as conn:
            rows = await conn.execute(select(DOCS.c.project, DOCS.c.rel_path))
            return tuple(DocumentRef(str(p), str(r)) for p, r in rows)

    async def search(
        self, vector: Sequence[float], model: str, k: int, project: str | None
    ) -> tuple[SearchHit, ...]:
        distance = CHUNKS.c.embedding.cosine_distance(list(vector)).label("distance")
        query = (
            select(
                CHUNKS.c.project,
                CHUNKS.c.rel_path,
                CHUNKS.c.ordinal,
                CHUNKS.c.heading,
                CHUNKS.c.text,
                distance,
            )
            .join(
                DOCS,
                (DOCS.c.project == CHUNKS.c.project) & (DOCS.c.rel_path == CHUNKS.c.rel_path),
            )
            .where(DOCS.c.model == model)
            .order_by(distance)
            .limit(k)
        )
        if project is not None:
            query = query.where(CHUNKS.c.project == project)
        async with self._tx() as conn:
            rows = await conn.execute(query)
            return tuple(
                SearchHit(Chunk(DocumentRef(p, r), o, h, t), 1.0 - float(d))
                for p, r, o, h, t, d in rows
            )

    async def aclose(self) -> None:
        await self._engine.dispose()
