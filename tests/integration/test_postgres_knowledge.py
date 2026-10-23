from __future__ import annotations

import asyncio
import shutil
from typing import TYPE_CHECKING

import pytest
from testcontainers.community.postgres import PostgresContainer

from app.adapters.postgres.knowledge_store import PostgresKnowledge
from app.adapters.postgres.migrate import upgrade
from tests.contracts.knowledge_store_contract import KnowledgeStoreContract

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(shutil.which("docker") is None, reason="needs Docker for testcontainers"),
]


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("pgvector/pgvector:pg16", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        upgrade(url)
        yield url


class TestPostgresKnowledge(KnowledgeStoreContract):
    @pytest.fixture(autouse=True)
    async def _empty(self, database_url: str) -> None:
        self.url = database_url
        store = self.make()
        for ref in await store.documents():
            await store.remove_document(ref)

    def make(self) -> PostgresKnowledge:
        return PostgresKnowledge(self.url)

    async def test_upgrade_is_idempotent(self) -> None:
        await asyncio.to_thread(upgrade, self.url)
