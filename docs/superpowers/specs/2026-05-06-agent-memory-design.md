# Agent Memory & Persistence — Design Spec
**Date:** 2026-05-06  
**Status:** Approved  
**Cycle:** 2

---

## Overview

Introduce a real AI agent (Agno framework) as a driven adapter, persistent memory via PostgreSQL+pgvector, and Docker Compose infrastructure. The agent is fully decoupled from storage, LLM model, and framework internals.

---

## Decisions

| Topic | Decision |
|---|---|
| Agent framework | Agno |
| Framework boundary | Adapter only — `AgentPort` ABC separates use case from Agno |
| Datetime/location | Agno native flags (`add_datetime_to_context`, `add_location_to_context`) |
| Persistence | PostgreSQL 16 + pgvector extension |
| Domain schema | `public` — our source of truth |
| Agno schema | `agno` — Agno manages own session tables, same Postgres instance |
| Conversation history | Loaded via `RepositoryPort`, converted to Agno format inside adapter |
| Agno stateless | Yes — we pass full history per call; Agno schema is secondary/redundant |
| ORM | SQLAlchemy[asyncio] + asyncpg |
| Migrations | Alembic |
| Integration tests | testcontainers-python (real Postgres, no mocks) |

---

## Architecture

### New Port

```python
# app/ports/agent.py
class AgentPort(ABC):
    @abstractmethod
    async def run(self, message: str, conversation: Conversation) -> str: ...
```

`LLMPort` is preserved for future use (embeddings, raw summarization).  
`ProcessIncomingMessage` use case switches from `LLMPort` to `AgentPort`.

### Layer Map

```
ports/
  agent.py                    ← AgentPort ABC  [NEW]
  llm.py                      ← unchanged
  repository.py               ← unchanged

adapters/
  agent/
    __init__.py               [NEW]
    agno_agent.py             ← AgnoAgent implements AgentPort  [NEW]
    stub_agent.py             ← StubAgent for unit tests  [NEW]
  repository/
    postgres_repository.py    ← PostgresRepository implements RepositoryPort  [NEW]
    in_memory_repository.py   ← unchanged (unit tests)

application/use_cases/
  process_incoming_message.py ← LLMPort → AgentPort  [MODIFIED]

api/
  deps.py                     ← add get_agent()  [MODIFIED]

config.py                     ← add DB + Agno settings  [MODIFIED]
```

### Data Flow

```
POST /messages
  → ProcessIncomingMessage
      1. RepositoryPort.get(conv_id)          # load history
      2. AgentPort.run(message, conversation) # agent responds
         └─ AgnoAgent (internal):
              convert Conversation → Agno messages list
              Agno.run() with add_datetime=True, add_location=True
              return response str
      3. RepositoryPort.save(conversation)    # persist
  → OutgoingMessage
```

---

## Database Schema

### Schema: `public` (our domain)

```sql
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL,   -- 'user' | 'assistant'
    content         TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    embedding       vector(1536)     -- nullable, future semantic search
);

-- Indexes
CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_timestamp ON messages(conversation_id, timestamp);
CREATE INDEX idx_conversations_updated_at ON conversations(updated_at DESC);
CREATE INDEX idx_messages_embedding ON messages
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
```

### Schema: `agno` (Agno internals)

Agno creates and manages its own tables here automatically via `PostgresStorage`.  
Swap framework → `DROP SCHEMA agno CASCADE`, zero domain impact.

---

## Configuration

```python
# config.py additions
database_url: str           # postgresql+asyncpg://...
agno_model_id: str          # e.g. "claude-sonnet-4-6"
agno_add_datetime: bool = True
agno_add_location: bool = True
```

---

## AgnoAgent Adapter (internal design)

```python
class AgnoAgent(AgentPort):
    def __init__(self, settings: Settings) -> None:
        storage = PostgresStorage(
            table_name="agent_sessions",
            db_url=settings.database_url,
            schema="agno",
        )
        self._agent = Agent(
            model=...,                          # from settings.agno_model_id
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
            storage=storage,
        )

    async def run(self, message: str, conversation: Conversation) -> str:
        # convert Conversation domain entity → Agno messages list
        # call self._agent.run(message, messages=history)
        # return response string
```

Agno framework details are 100% internal to this file. `AgentPort` consumers see only `async run(message, conversation) -> str`.

---

## Docker Compose

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: marcelo
      POSTGRES_USER: marcelo
      POSTGRES_PASSWORD: marcelo
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U marcelo"]
      interval: 5s
      retries: 5

  app:
    build: .
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql+asyncpg://marcelo:marcelo@db:5432/marcelo
    ports: ["8000:8000"]

volumes:
  pgdata:
```

---

## Tests

| Test | Type | Tool |
|---|---|---|
| `AgentPort` contract via `StubAgent` | Unit | pytest |
| `ProcessIncomingMessage` with `StubAgent` | Unit | pytest |
| `AgnoAgent` adapter boundary | Unit | mock `agno.Agent` |
| `PostgresRepository` save/get | Integration | testcontainers-python |
| `POST /messages` end-to-end | Integration | httpx.AsyncClient + testcontainers |

Marker `@pytest.mark.integration` gates DB tests. CI can skip or run with Docker.

**StubAgent:**
```python
class StubAgent(AgentPort):
    async def run(self, message: str, conversation: Conversation) -> str:
        return "stub response"
```

---

## Files to Create / Modify

| File | Action |
|---|---|
| `app/ports/agent.py` | CREATE |
| `app/adapters/agent/__init__.py` | CREATE |
| `app/adapters/agent/agno_agent.py` | CREATE |
| `app/adapters/agent/stub_agent.py` | CREATE |
| `app/adapters/repository/postgres_repository.py` | CREATE |
| `app/application/use_cases/process_incoming_message.py` | MODIFY (LLMPort → AgentPort) |
| `app/api/deps.py` | MODIFY (add get_agent) |
| `app/config.py` | MODIFY (DB + Agno settings) |
| `docker-compose.yml` | CREATE |
| `Dockerfile` | CREATE |
| `alembic/` | CREATE (migrations) |
| `tests/unit/adapters/agent/test_agno_agent.py` | CREATE |
| `tests/unit/adapters/agent/test_stub_agent.py` | CREATE |
| `tests/integration/adapters/repository/test_postgres_repository.py` | CREATE |
| `tests/integration/api/test_messages_endpoint.py` | CREATE |
| `pyproject.toml` | MODIFY (add agno, sqlalchemy, asyncpg, alembic, testcontainers) |
