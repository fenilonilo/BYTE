from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.adapters.repository.models import Base
from app.adapters.repository.postgres_repository import PostgresRepository
from app.domain.entities import Conversation, Message

NOW = datetime.now(tz=UTC)


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer(image="pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture(scope="session")
def db_url(pg_container: PostgresContainer) -> str:
    raw = pg_container.get_connection_url()
    # testcontainers returns postgresql+psycopg2://... → convert to asyncpg
    return raw.replace("+psycopg2", "+asyncpg").replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine(db_url: str):
    eng = create_async_engine(db_url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
def repo(engine) -> PostgresRepository:
    return PostgresRepository(engine)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_get_returns_none_for_missing(repo: PostgresRepository) -> None:
    result = await repo.get("nonexistent-id")
    assert result is None


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_save_and_get_conversation(repo: PostgresRepository) -> None:
    conv_id = str(uuid4())
    conv = Conversation(id=conv_id, messages=(), created_at=NOW)
    msg = Message(id=str(uuid4()), role="user", content="Hello", timestamp=NOW)
    conv = conv.with_message(msg)

    await repo.save(conv)
    result = await repo.get(conv_id)

    assert result is not None
    assert result.id == conv_id
    assert len(result.messages) == 1
    assert result.messages[0].content == "Hello"
    assert result.messages[0].role == "user"


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_save_appends_new_messages_only(repo: PostgresRepository) -> None:
    conv_id = str(uuid4())
    conv = Conversation(id=conv_id, messages=(), created_at=NOW)
    msg1 = Message(id=str(uuid4()), role="user", content="First", timestamp=NOW)
    conv = conv.with_message(msg1)
    await repo.save(conv)

    msg2 = Message(id=str(uuid4()), role="assistant", content="Second", timestamp=NOW)
    conv = conv.with_message(msg2)
    await repo.save(conv)

    result = await repo.get(conv_id)
    assert result is not None
    assert len(result.messages) == 2
    assert result.messages[1].content == "Second"


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_save_is_idempotent(repo: PostgresRepository) -> None:
    conv_id = str(uuid4())
    conv = Conversation(id=conv_id, messages=(), created_at=NOW)
    msg = Message(id=str(uuid4()), role="user", content="Hello", timestamp=NOW)
    conv = conv.with_message(msg)

    await repo.save(conv)
    await repo.save(conv)  # second save must not duplicate messages

    result = await repo.get(conv_id)
    assert result is not None
    assert len(result.messages) == 1
