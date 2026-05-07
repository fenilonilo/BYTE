# Agent Memory & Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce Agno-powered AI agent as a driven adapter, PostgreSQL+pgvector persistence, and Docker Compose infrastructure — all decoupled via hexagonal ports.

**Architecture:** `AgentPort` ABC isolates use case from Agno. `ProcessIncomingMessage` uses `AgentPort` (replaces `LLMPort`). `PostgresRepository` implements `RepositoryPort` via SQLAlchemy async + asyncpg. Agno's internal session storage uses the same Postgres via `psycopg` in an isolated table namespace.

**Tech Stack:** agno, anthropic, sqlalchemy[asyncio], asyncpg, psycopg (for Agno), pgvector, alembic, testcontainers[postgres], httpx

---

## File Map

| File | Action |
|---|---|
| `app/ports/agent.py` | CREATE — AgentPort ABC |
| `app/adapters/agent/__init__.py` | CREATE — empty |
| `app/adapters/agent/stub_agent.py` | CREATE — StubAgent for unit tests |
| `app/adapters/agent/agno_agent.py` | CREATE — AgnoAgent implements AgentPort |
| `app/adapters/repository/models.py` | CREATE — SQLAlchemy mapped models |
| `app/adapters/repository/postgres_repository.py` | CREATE — PostgresRepository |
| `app/application/use_cases/process_incoming_message.py` | MODIFY — LLMPort → AgentPort |
| `app/config.py` | MODIFY — add database_url, agno_* settings |
| `app/api/deps.py` | MODIFY — add get_engine, get_agent; update get_repo |
| `app/api/router.py` | MODIFY — use get_agent instead of get_llm |
| `main.py` | CREATE (if missing) — FastAPI app entrypoint |
| `alembic.ini` | CREATE — alembic config |
| `alembic/env.py` | CREATE — async alembic env |
| `alembic/versions/001_initial_schema.py` | CREATE — conversations + messages + pgvector |
| `Dockerfile` | CREATE |
| `docker-compose.yml` | CREATE |
| `.env.example` | CREATE |
| `pyproject.toml` | MODIFY — new dependency groups |
| `tests/unit/adapters/__init__.py` | CREATE — empty |
| `tests/unit/adapters/agent/__init__.py` | CREATE — empty |
| `tests/unit/adapters/agent/test_agno_agent.py` | CREATE |
| `tests/unit/application/use_cases/test_process_incoming_message.py` | MODIFY — mock_llm → mock_agent |
| `tests/integration/__init__.py` | CREATE — empty |
| `tests/integration/adapters/__init__.py` | CREATE — empty |
| `tests/integration/adapters/repository/__init__.py` | CREATE — empty |
| `tests/integration/adapters/repository/test_postgres_repository.py` | CREATE |
| `tests/integration/api/__init__.py` | CREATE — empty |
| `tests/integration/api/test_messages_endpoint.py` | CREATE |

---

## Task 1: Update pyproject.toml — add all new dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependency groups**

Replace the `[project.optional-dependencies]` section with:

```toml
[project.optional-dependencies]
api = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
]
agent = [
    "agno>=1.5",
    "anthropic>=0.39",
]
db = [
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "psycopg[binary]>=3.1",
    "pgvector>=0.3",
    "alembic>=1.13",
]
dev = [
    "ruff>=0.7",
    "pyright>=1.1.385",
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "pre-commit>=4.0",
    "testcontainers[postgres]>=4.9",
    "httpx>=0.27",
]
```

- [ ] **Step 2: Install new deps**

```bash
pip install -e ".[api,agent,db,dev]"
```

Expected: no errors. Verify `agno`, `sqlalchemy`, `asyncpg`, `alembic`, `testcontainers` installed.

```bash
python -c "import agno; import sqlalchemy; import asyncpg; import alembic; import testcontainers"
```

Expected: no ImportError.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: add agent, db, and test dependencies for Cycle 2"
```

---

## Task 2: AgentPort ABC

**Files:**
- Create: `app/ports/agent.py`

- [ ] **Step 1: Write the failing import test**

```python
# tests/unit/test_imports.py  (temporary, delete after)
def test_agent_port_importable():
    from app.ports.agent import AgentPort
    assert AgentPort is not None
```

Run: `pytest tests/unit/test_imports.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Create the port**

```python
# app/ports/agent.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class AgentPort(ABC):
    @abstractmethod
    async def run(self, message: str, conversation: Conversation) -> str: ...
```

- [ ] **Step 3: Run test**

```bash
pytest tests/unit/test_imports.py -v
```

Expected: PASS

- [ ] **Step 4: Delete temporary test file, commit**

```bash
rm tests/unit/test_imports.py
git add app/ports/agent.py
git commit -m "feat(ports): add AgentPort ABC"
```

---

## Task 3: StubAgent adapter

**Files:**
- Create: `app/adapters/agent/__init__.py`
- Create: `app/adapters/agent/stub_agent.py`
- Create: `tests/unit/adapters/__init__.py`
- Create: `tests/unit/adapters/agent/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/adapters/agent/test_stub_agent.py
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.agent.stub_agent import StubAgent
from app.domain.entities import Conversation

NOW = datetime.now(tz=UTC)


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-1", messages=(), created_at=NOW)


@pytest.mark.unit
async def test_stub_agent_returns_string(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.unit
async def test_stub_agent_implements_port(conversation: Conversation) -> None:
    from app.ports.agent import AgentPort
    agent = StubAgent()
    assert isinstance(agent, AgentPort)
```

Run: `pytest tests/unit/adapters/agent/test_stub_agent.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Create empty `__init__.py` files**

```python
# app/adapters/agent/__init__.py
# (empty)
```

```python
# tests/unit/adapters/__init__.py
# (empty)
```

```python
# tests/unit/adapters/agent/__init__.py
# (empty)
```

- [ ] **Step 3: Create StubAgent**

```python
# app/adapters/agent/stub_agent.py
from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class StubAgent(AgentPort):
    async def run(self, message: str, conversation: Conversation) -> str:
        return f"[stub] Echo: {message}"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/adapters/agent/test_stub_agent.py -v
```

Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add app/adapters/agent/ tests/unit/adapters/
git commit -m "feat(adapters): add StubAgent for unit testing"
```

---

## Task 4: Refactor ProcessIncomingMessage — LLMPort → AgentPort

**Files:**
- Modify: `app/application/use_cases/process_incoming_message.py`

- [ ] **Step 1: Read existing file to understand current state**

Current file uses `LLMPort` with `llm.complete(prompt, conversation)`. We switch to `AgentPort` with `agent.run(message, conversation)`.

- [ ] **Step 2: Update the use case**

```python
# app/application/use_cases/process_incoming_message.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.domain.entities import Conversation, IncomingMessage, Message, OutgoingMessage

if TYPE_CHECKING:
    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort


class ProcessIncomingMessage:
    def __init__(self, agent: AgentPort, repo: RepositoryPort, log: LoggerPort) -> None:
        self._agent = agent
        self._repo = repo
        self._log = log

    async def execute(self, msg: IncomingMessage) -> OutgoingMessage:
        conv_id = msg.conversation_id or str(uuid4())
        conversation = await self._repo.get(conv_id)
        if conversation is None:
            conversation = Conversation(
                id=conv_id,
                messages=(),
                created_at=datetime.now(tz=UTC),
            )

        user_msg = Message(
            id=str(uuid4()),
            role="user",
            content=msg.content,
            timestamp=msg.timestamp,
        )
        conversation = conversation.with_message(user_msg)

        self._log.info("agent.run.start", conversation_id=conv_id)
        response_text = await self._agent.run(
            message=msg.content,
            conversation=conversation,
        )

        assistant_msg = Message(
            id=str(uuid4()),
            role="assistant",
            content=response_text,
            timestamp=datetime.now(tz=UTC),
        )
        conversation = conversation.with_message(assistant_msg)

        await self._repo.save(conversation)
        self._log.info("agent.run.done", conversation_id=conv_id)

        return OutgoingMessage(
            content=response_text,
            channel=msg.channel,
            recipient=msg.sender,
        )
```

- [ ] **Step 3: Verify ruff + pyright pass (expect test failures — fixed in Task 5)**

```bash
ruff check app/application/use_cases/process_incoming_message.py
```

Expected: no errors

---

## Task 5: Update ProcessIncomingMessage unit tests

**Files:**
- Modify: `tests/unit/application/use_cases/test_process_incoming_message.py`

- [ ] **Step 1: Update the test file**

```python
# tests/unit/application/use_cases/test_process_incoming_message.py
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import Conversation, IncomingMessage, OutgoingMessage

NOW = datetime.now(tz=UTC)


@pytest.fixture
def incoming_msg() -> IncomingMessage:
    return IncomingMessage(
        id="msg-1",
        sender="user-1",
        content="Hello!",
        channel="api",
        timestamp=NOW,
        conversation_id=None,
    )


@pytest.fixture
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.run.return_value = "Hello back!"
    return agent


@pytest.fixture
def mock_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get.return_value = None
    repo.save.return_value = None
    return repo


@pytest.fixture
def mock_log() -> MagicMock:
    return MagicMock()


@pytest.mark.unit
async def test_execute_returns_outgoing_message(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    assert result.content == "Hello back!"
    assert result.channel == "api"
    assert result.recipient == "user-1"


@pytest.mark.unit
async def test_execute_calls_agent(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_agent.run.assert_called_once()


@pytest.mark.unit
async def test_execute_saves_conversation(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_repo.save.assert_called_once()


@pytest.mark.unit
async def test_execute_loads_existing_conversation(
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    existing_conv = Conversation(id="conv-123", messages=(), created_at=NOW)
    mock_repo.get.return_value = existing_conv
    msg = IncomingMessage(
        id="msg-2",
        sender="user-1",
        content="Follow-up",
        channel="api",
        timestamp=NOW,
        conversation_id="conv-123",
    )
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(msg)
    mock_repo.get.assert_called_once_with("conv-123")


@pytest.mark.unit
async def test_execute_creates_conversation_when_none(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    mock_repo.get.return_value = None
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    mock_repo.save.assert_called_once()
```

- [ ] **Step 2: Run unit tests (excluding integration)**

```bash
pytest tests/unit/ -v -m "not integration"
```

Expected: all PASS (previous 5 tests now passing with new signatures)

- [ ] **Step 3: Commit**

```bash
git add app/application/use_cases/process_incoming_message.py \
        tests/unit/application/use_cases/test_process_incoming_message.py
git commit -m "refactor(application): swap LLMPort for AgentPort in ProcessIncomingMessage"
```

---

## Task 6: Update config.py — database + Agno settings

**Files:**
- Modify: `app/config.py`

- [ ] **Step 1: Update Settings**

```python
# app/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "marcelo"
    log_level: str = "INFO"
    default_channel: str = "api"

    # Database — asyncpg URL for SQLAlchemy; Agno adapter derives psycopg URL internally
    database_url: str = "postgresql+asyncpg://marcelo:marcelo@localhost:5432/marcelo"

    # Agno agent
    agno_model_id: str = "claude-sonnet-4-6"
    agno_add_datetime: bool = True
    agno_add_location: bool = True

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
```

- [ ] **Step 2: Verify**

```bash
python -c "from app.config import Settings; s = Settings(); print(s.database_url)"
```

Expected: `postgresql+asyncpg://marcelo:marcelo@localhost:5432/marcelo`

- [ ] **Step 3: Create .env.example**

```bash
# .env.example
MARCELO_DATABASE_URL=postgresql+asyncpg://marcelo:marcelo@localhost:5432/marcelo
MARCELO_AGNO_MODEL_ID=claude-sonnet-4-6
MARCELO_AGNO_ADD_DATETIME=true
MARCELO_AGNO_ADD_LOCATION=true
ANTHROPIC_API_KEY=sk-ant-...
```

- [ ] **Step 4: Commit**

```bash
git add app/config.py .env.example
git commit -m "feat(config): add database_url and Agno settings"
```

---

## Task 7: SQLAlchemy models

**Files:**
- Create: `app/adapters/repository/models.py`

- [ ] **Step 1: Write failing import test**

```python
# Temporary: run inline
python -c "from app.adapters.repository.models import Base, ConversationModel, MessageModel; print('ok')"
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 2: Create models**

```python
# app/adapters/repository/models.py
from __future__ import annotations

from datetime import datetime
from typing import List

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    messages: Mapped[List[MessageModel]] = relationship(
        "MessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="MessageModel.timestamp",
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conversation: Mapped[ConversationModel] = relationship(
        "ConversationModel", back_populates="messages"
    )
```

Note: `embedding` column (vector(1536)) is defined in the Alembic migration, not in the SQLAlchemy model, since we don't use it in application code yet. The index is also in the migration.

- [ ] **Step 3: Verify import**

```bash
python -c "from app.adapters.repository.models import Base, ConversationModel, MessageModel; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add app/adapters/repository/models.py
git commit -m "feat(adapters): add SQLAlchemy models for conversations and messages"
```

---

## Task 8: Alembic setup + initial migration

**Files:**
- Create: `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/001_initial_schema.py`

- [ ] **Step 1: Initialize alembic**

```bash
alembic init alembic
```

Expected: creates `alembic.ini` and `alembic/` directory.

- [ ] **Step 2: Configure alembic.ini**

In `alembic.ini`, find `sqlalchemy.url` and set it to a placeholder (actual URL comes from env in env.py):

```ini
sqlalchemy.url = postgresql+asyncpg://marcelo:marcelo@localhost:5432/marcelo
```

- [ ] **Step 3: Replace alembic/env.py with async-compatible version**

```python
# alembic/env.py
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.repository.models import Base
from app.config import Settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    return Settings().database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(get_url())
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def do_run_migrations(connection: object) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)  # type: ignore[arg-type]
    with context.begin_transaction():
        context.run_migrations()


def run_async_migrations() -> None:
    asyncio.run(run_migrations_online())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_async_migrations()
```

- [ ] **Step 4: Create initial migration**

```bash
alembic revision --autogenerate -m "initial_schema"
```

This generates `alembic/versions/<hash>_initial_schema.py`. Open it and edit `upgrade()` to add the pgvector extension and indexes:

```python
# alembic/versions/<hash>_initial_schema.py
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "<generated-hash>"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE INDEX idx_conversations_updated_at ON conversations (updated_at DESC)")

    op.create_table(
        "messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("conversation_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    # vector(1536) column — pgvector type not in SQLAlchemy core, add via raw SQL
    op.execute("ALTER TABLE messages ADD COLUMN embedding vector(1536)")

    op.create_index("idx_messages_conversation_id", "messages", ["conversation_id"])
    op.create_index(
        "idx_messages_timestamp", "messages", ["conversation_id", "timestamp"]
    )
    op.execute(
        """
        CREATE INDEX idx_messages_embedding ON messages
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.drop_table("messages")
    op.drop_table("conversations")
    op.execute("DROP EXTENSION IF EXISTS vector")
```

- [ ] **Step 5: Verify alembic can generate SQL (offline)**

```bash
alembic upgrade head --sql
```

Expected: prints SQL for creating the tables without errors.

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/
git commit -m "feat(db): add alembic setup and initial schema migration"
```

---

## Task 9: PostgresRepository adapter

**Files:**
- Create: `app/adapters/repository/postgres_repository.py`

- [ ] **Step 1: Create the repository**

```python
# app/adapters/repository/postgres_repository.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.adapters.repository.models import ConversationModel, MessageModel
from app.domain.entities import Conversation, Message
from app.ports.repository import RepositoryPort

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


class PostgresRepository(RepositoryPort):
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

    async def save(self, conversation: Conversation) -> None:
        now = datetime.now(tz=UTC)
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                select(ConversationModel).where(ConversationModel.id == conversation.id)
            )
            conv_model = result.scalar_one_or_none()

            if conv_model is None:
                conv_model = ConversationModel(
                    id=conversation.id,
                    created_at=conversation.created_at,
                    updated_at=now,
                )
                session.add(conv_model)
            else:
                conv_model.updated_at = now

            existing_ids_result = await session.execute(
                select(MessageModel.id).where(
                    MessageModel.conversation_id == conversation.id
                )
            )
            existing_ids = {row[0] for row in existing_ids_result}

            for msg in conversation.messages:
                if msg.id not in existing_ids:
                    session.add(
                        MessageModel(
                            id=msg.id,
                            conversation_id=conversation.id,
                            role=msg.role,
                            content=msg.content,
                            timestamp=msg.timestamp,
                        )
                    )

            await session.commit()

    async def get(self, conversation_id: str) -> Conversation | None:
        async with AsyncSession(self._engine) as session:
            result = await session.execute(
                select(ConversationModel)
                .where(ConversationModel.id == conversation_id)
                .options(selectinload(ConversationModel.messages))
            )
            conv_model = result.scalar_one_or_none()
            if conv_model is None:
                return None

            messages = tuple(
                Message(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    timestamp=m.timestamp.replace(tzinfo=UTC),
                )
                for m in sorted(conv_model.messages, key=lambda m: m.timestamp)
            )
            return Conversation(
                id=conv_model.id,
                messages=messages,
                created_at=conv_model.created_at.replace(tzinfo=UTC),
            )
```

- [ ] **Step 2: Verify ruff + pyright**

```bash
ruff check app/adapters/repository/postgres_repository.py
pyright app/adapters/repository/postgres_repository.py
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/adapters/repository/postgres_repository.py
git commit -m "feat(adapters): add PostgresRepository with SQLAlchemy async"
```

---

## Task 10: PostgresRepository integration tests

**Files:**
- Create: `tests/integration/__init__.py`
- Create: `tests/integration/adapters/__init__.py`
- Create: `tests/integration/adapters/repository/__init__.py`
- Create: `tests/integration/adapters/repository/test_postgres_repository.py`

- [ ] **Step 1: Create `__init__.py` files**

Create empty files at:
- `tests/integration/__init__.py`
- `tests/integration/adapters/__init__.py`
- `tests/integration/adapters/repository/__init__.py`

- [ ] **Step 2: Create integration test**

```python
# tests/integration/adapters/repository/test_postgres_repository.py
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
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


@pytest.fixture(scope="session")
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
async def test_get_returns_none_for_missing(repo: PostgresRepository) -> None:
    result = await repo.get("nonexistent-id")
    assert result is None


@pytest.mark.integration
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
```

- [ ] **Step 3: Run integration tests (requires Docker)**

```bash
pytest tests/integration/adapters/repository/ -v -m integration
```

Expected: 4 PASS. If Docker not running, tests are skipped by testcontainers.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/
git commit -m "test(integration): add PostgresRepository integration tests"
```

---

## Task 11: AgnoAgent adapter

**Files:**
- Create: `app/adapters/agent/agno_agent.py`

- [ ] **Step 1: Create the adapter**

```python
# app/adapters/agent/agno_agent.py
from __future__ import annotations

from typing import TYPE_CHECKING

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.anthropic import Claude

from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.config import Settings
    from app.domain.entities import Conversation


class AgnoAgent(AgentPort):
    def __init__(self, settings: Settings) -> None:
        # Agno uses psycopg (sync driver); derive from asyncpg URL
        agno_db_url = settings.database_url.replace("+asyncpg", "+psycopg")
        db = PostgresDb(db_url=agno_db_url)
        self._agent = Agent(
            model=Claude(id=settings.agno_model_id),
            db=db,
            add_history_to_context=True,
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
        )

    async def run(self, message: str, conversation: Conversation) -> str:
        response = await self._agent.arun(message, session_id=conversation.id)
        if response is None or response.content is None:
            return ""
        return str(response.content)
```

- [ ] **Step 2: Verify ruff**

```bash
ruff check app/adapters/agent/agno_agent.py
```

Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/adapters/agent/agno_agent.py
git commit -m "feat(adapters): add AgnoAgent adapter implementing AgentPort"
```

---

## Task 12: AgnoAgent unit tests

**Files:**
- Create: `tests/unit/adapters/agent/test_agno_agent.py`

- [ ] **Step 1: Create tests**

```python
# tests/unit/adapters/agent/test_agno_agent.py
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.entities import Conversation

NOW = datetime.now(tz=UTC)


@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.database_url = "postgresql+asyncpg://test:test@localhost/test"
    s.agno_model_id = "claude-sonnet-4-6"
    s.agno_add_datetime = True
    s.agno_add_location = True
    return s


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-abc", messages=(), created_at=NOW)


@pytest.mark.unit
async def test_run_returns_response_content(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_response = MagicMock()
    mock_response.content = "Agent says hello"

    with (
        patch("app.adapters.agent.agno_agent.Agent") as MockAgent,
        patch("app.adapters.agent.agno_agent.PostgresDb"),
        patch("app.adapters.agent.agno_agent.Claude"),
    ):
        mock_inner = AsyncMock()
        MockAgent.return_value = mock_inner
        mock_inner.arun = AsyncMock(return_value=mock_response)

        from app.adapters.agent.agno_agent import AgnoAgent
        agent = AgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert result == "Agent says hello"


@pytest.mark.unit
async def test_run_passes_session_id_from_conversation(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_response = MagicMock()
    mock_response.content = "response"

    with (
        patch("app.adapters.agent.agno_agent.Agent") as MockAgent,
        patch("app.adapters.agent.agno_agent.PostgresDb"),
        patch("app.adapters.agent.agno_agent.Claude"),
    ):
        mock_inner = AsyncMock()
        MockAgent.return_value = mock_inner
        mock_inner.arun = AsyncMock(return_value=mock_response)

        from app.adapters.agent.agno_agent import AgnoAgent
        agent = AgnoAgent(mock_settings)
        await agent.run("Hello", conversation)

        mock_inner.arun.assert_called_once_with("Hello", session_id="conv-abc")


@pytest.mark.unit
async def test_run_returns_empty_string_when_content_is_none(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_response = MagicMock()
    mock_response.content = None

    with (
        patch("app.adapters.agent.agno_agent.Agent") as MockAgent,
        patch("app.adapters.agent.agno_agent.PostgresDb"),
        patch("app.adapters.agent.agno_agent.Claude"),
    ):
        mock_inner = AsyncMock()
        MockAgent.return_value = mock_inner
        mock_inner.arun = AsyncMock(return_value=mock_response)

        from app.adapters.agent.agno_agent import AgnoAgent
        agent = AgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert result == ""


@pytest.mark.unit
async def test_agno_agent_implements_port(mock_settings: MagicMock) -> None:
    from app.ports.agent import AgentPort

    with (
        patch("app.adapters.agent.agno_agent.Agent"),
        patch("app.adapters.agent.agno_agent.PostgresDb"),
        patch("app.adapters.agent.agno_agent.Claude"),
    ):
        from app.adapters.agent.agno_agent import AgnoAgent
        agent = AgnoAgent(mock_settings)
        assert isinstance(agent, AgentPort)
```

- [ ] **Step 2: Run unit tests**

```bash
pytest tests/unit/adapters/agent/test_agno_agent.py -v
```

Expected: 4 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/adapters/agent/test_agno_agent.py
git commit -m "test(unit): add AgnoAgent adapter unit tests"
```

---

## Task 13: Update api/deps.py and api/router.py

**Files:**
- Modify: `app/api/deps.py`
- Modify: `app/api/router.py`

- [ ] **Step 1: Update deps.py**

```python
# app/api/deps.py
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.agent.agno_agent import AgnoAgent
from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.repository.postgres_repository import PostgresRepository
from app.config import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


@lru_cache
def get_repo() -> RepositoryPort:
    return PostgresRepository(get_engine())


@lru_cache
def get_agent() -> AgentPort:
    return AgnoAgent(get_settings())
```

- [ ] **Step 2: Update router.py**

```python
# app/api/router.py
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.deps import get_agent, get_logger, get_repo
from app.api.schemas import IncomingMessageSchema, OutgoingMessageSchema
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage

if TYPE_CHECKING:
    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort

router = APIRouter()


@router.post("/messages", response_model=OutgoingMessageSchema)
async def receive_message(
    body: IncomingMessageSchema,
    agent: AgentPort = Depends(get_agent),
    repo: RepositoryPort = Depends(get_repo),
    log: LoggerPort = Depends(get_logger),
) -> OutgoingMessageSchema:
    use_case = ProcessIncomingMessage(agent=agent, repo=repo, log=log)
    incoming = IncomingMessage(
        id=str(uuid4()),
        sender=body.sender,
        content=body.content,
        channel=body.channel,
        timestamp=datetime.now(tz=UTC),
        conversation_id=body.conversation_id,
    )
    outgoing = await use_case.execute(incoming)
    return OutgoingMessageSchema(
        content=outgoing.content,
        channel=outgoing.channel,
        recipient=outgoing.recipient,
    )
```

- [ ] **Step 3: Run unit tests to catch regressions**

```bash
pytest tests/unit/ -v -m "not integration"
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add app/api/deps.py app/api/router.py
git commit -m "feat(api): wire AgentPort and PostgresRepository into FastAPI DI"
```

---

## Task 14: Verify or create main.py entrypoint

**Files:**
- Create: `main.py` (if not already present)

- [ ] **Step 1: Check if main.py exists**

```bash
python -c "import main; print('exists')"
```

If it prints `exists`, skip Step 2.

- [ ] **Step 2: Create main.py if missing**

```python
# main.py
from __future__ import annotations

import structlog
import uvicorn
from fastapi import FastAPI

from app.api.router import router
from app.config import Settings

settings = Settings()

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

app = FastAPI(title=settings.app_name)
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 3: Verify startup (without DB)**

```bash
python -c "from main import app; print(app.title)"
```

Expected: `marcelo`

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat: add FastAPI app entrypoint"
```

---

## Task 15: Dockerfile

**Files:**
- Create: `Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install build deps for asyncpg and psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir -e ".[api,agent,db]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Verify Dockerfile syntax (lint only)**

```bash
docker build --dry-run . 2>&1 | head -5
```

Or if `docker` isn't available locally, just verify the file is valid by checking no obvious errors.

- [ ] **Step 3: Commit**

```bash
git add Dockerfile
git commit -m "feat(docker): add Dockerfile for app service"
```

---

## Task 16: docker-compose.yml

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml**

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: marcelo
      POSTGRES_USER: marcelo
      POSTGRES_PASSWORD: marcelo
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U marcelo -d marcelo"]
      interval: 5s
      timeout: 5s
      retries: 10

  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
    environment:
      MARCELO_DATABASE_URL: postgresql+asyncpg://marcelo:marcelo@db:5432/marcelo
      MARCELO_AGNO_MODEL_ID: claude-sonnet-4-6
      MARCELO_AGNO_ADD_DATETIME: "true"
      MARCELO_AGNO_ADD_LOCATION: "true"
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    ports:
      - "8000:8000"

volumes:
  pgdata:
```

- [ ] **Step 2: Validate compose file**

```bash
docker compose config
```

Expected: prints resolved config with no errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(docker): add docker-compose with postgres+pgvector and app service"
```

---

## Task 17: End-to-end integration test

**Files:**
- Create: `tests/integration/api/__init__.py`
- Create: `tests/integration/api/test_messages_endpoint.py`

- [ ] **Step 1: Create `__init__.py`**

```python
# tests/integration/api/__init__.py
# (empty)
```

- [ ] **Step 2: Create e2e test**

```python
# tests/integration/api/test_messages_endpoint.py
from __future__ import annotations

from uuid import uuid4

import pytest
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


@pytest.fixture(scope="session")
async def prepared_engine(db_url: str):
    eng = create_async_engine(db_url)
    async with eng.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def client(prepared_engine):
    from main import app

    repo = PostgresRepository(prepared_engine)
    agent = StubAgent()

    # FastAPI dependency_overrides is the correct way to override DI in tests.
    # It bypasses lru_cache entirely — no cache manipulation needed.
    app.dependency_overrides[deps.get_repo] = lambda: repo
    app.dependency_overrides[deps.get_agent] = lambda: agent

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.integration
async def test_post_message_returns_200(client: AsyncClient) -> None:
    response = await client.post(
        "/messages",
        json={"sender": "user-1", "content": "Hello", "channel": "api"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["recipient"] == "user-1"
    assert data["channel"] == "api"
    assert isinstance(data["content"], str)


@pytest.mark.integration
async def test_conversation_persists_across_requests(client: AsyncClient) -> None:
    conv_id = str(uuid4())

    r1 = await client.post(
        "/messages",
        json={
            "sender": "user-1",
            "content": "First message",
            "channel": "api",
            "conversation_id": conv_id,
        },
    )
    assert r1.status_code == 200

    r2 = await client.post(
        "/messages",
        json={
            "sender": "user-1",
            "content": "Second message",
            "channel": "api",
            "conversation_id": conv_id,
        },
    )
    assert r2.status_code == 200


@pytest.mark.integration
async def test_missing_required_fields_returns_422(client: AsyncClient) -> None:
    response = await client.post("/messages", json={"sender": "user-1"})
    assert response.status_code == 422
```

- [ ] **Step 3: Run all integration tests**

```bash
pytest tests/integration/ -v -m integration
```

Expected: all PASS (7 total: 4 repo + 3 api)

- [ ] **Step 4: Run full test suite (unit only, no DB required)**

```bash
pytest tests/unit/ -v --cov=app --cov-report=term-missing
```

Expected: all PASS, coverage ≥ 80% on domain + application

- [ ] **Step 5: Run quality gates**

```bash
ruff check . && ruff format --check . && pyright
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add tests/integration/api/
git commit -m "test(integration): add end-to-end POST /messages integration test"
```

---

## Final verification

- [ ] **Run complete test suite**

```bash
pytest tests/unit/ -v
```

Expected: all unit tests PASS

- [ ] **Run integration tests (requires Docker)**

```bash
pytest tests/integration/ -v -m integration
```

Expected: all integration tests PASS

- [ ] **Quality gates**

```bash
ruff check . && ruff format --check . && pyright
```

Expected: no errors, no warnings

- [ ] **Smoke test docker compose (optional, requires ANTHROPIC_API_KEY)**

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
docker compose up --build -d
docker compose exec app alembic upgrade head
curl -X POST http://localhost:8000/messages \
  -H "Content-Type: application/json" \
  -d '{"sender":"test","content":"Hello!","channel":"api"}'
docker compose down
```

Expected: JSON response with `content`, `channel`, `recipient`.
