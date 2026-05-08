from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from testcontainers.postgres import PostgresContainer

from app.adapters.agent.stub_agent import StubAgent
from app.adapters.repository.models import Base
from app.adapters.repository.postgres_repository import PostgresRepository
from app.api import deps


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer(image="pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture(scope="session")
def db_url(pg_container: PostgresContainer) -> str:
    raw = pg_container.get_connection_url()
    return raw.replace("+psycopg2", "+asyncpg").replace("postgresql://", "postgresql+asyncpg://")


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def prepared_engine(db_url: str):
    eng = create_async_engine(db_url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def client(prepared_engine):
    from main import app

    repo = PostgresRepository(prepared_engine)
    agent = StubAgent()

    app.dependency_overrides[deps.get_repo] = lambda: repo
    app.dependency_overrides[deps.get_agent] = lambda: agent

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_post_message_returns_200(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/messages",
        json={"sender": "user-1", "content": "Hello", "channel": "api"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["recipient"] == "user-1"
    assert data["channel"] == "api"
    assert isinstance(data["content"], str)


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_conversation_persists_across_requests(client: AsyncClient) -> None:
    conv_id = str(uuid4())

    r1 = await client.post(
        "/api/v1/messages",
        json={
            "sender": "user-1",
            "content": "First message",
            "channel": "api",
            "conversation_id": conv_id,
        },
    )
    assert r1.status_code == 200

    r2 = await client.post(
        "/api/v1/messages",
        json={
            "sender": "user-1",
            "content": "Second message",
            "channel": "api",
            "conversation_id": conv_id,
        },
    )
    assert r2.status_code == 200


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
async def test_missing_required_fields_returns_422(client: AsyncClient) -> None:
    response = await client.post("/api/v1/messages", json={"sender": "user-1"})
    assert response.status_code == 422
