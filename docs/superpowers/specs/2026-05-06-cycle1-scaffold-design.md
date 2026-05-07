# Cycle 1 Scaffold — Design Spec

**Date:** 2026-05-06
**Scope:** Full Cycle 1 implementation of Marcelo hexagonal scaffold
**Build order:** Layer-by-layer (approach B). Each layer verified before next starts.
**Parallelism:** Within layers 2, 3, and 5–6, files are independent → parallel subagents.

---

## Layers & Files

### Layer 1 — domain (sequential, foundation)

| File | Contents |
|---|---|
| `app/__init__.py` | empty |
| `app/domain/__init__.py` | `__all__` exports |
| `app/domain/entities.py` | `Message`, `Conversation`, `IncomingMessage`, `OutgoingMessage` — `@dataclass(frozen=True, slots=True)` |
| `app/domain/exceptions.py` | `DomainError`, `MessageError`, `RegistryError`, `RegistryDuplicateError`, `RegistryKeyError` |

**Constraints:**
- Zero external imports. stdlib only.
- No Pydantic.
- `from __future__ import annotations` on every module.

### Layer 2 — ports (parallel, depends on domain)

| File | Port | Methods |
|---|---|---|
| `app/ports/__init__.py` | — | `__all__` |
| `app/ports/logger.py` | `LoggerPort(ABC)` | `debug`, `info`, `warning`, `error` — all sync, `**fields: object` |
| `app/ports/messaging.py` | `MessagingPort(ABC)` | `async send(OutgoingMessage) -> None`, `async receive() -> AsyncIterator[IncomingMessage]` |
| `app/ports/llm.py` | `LLMPort(ABC)` | `async complete(prompt: str, conversation: Conversation) -> str` |
| `app/ports/repository.py` | `RepositoryPort(ABC)` | `async save(conversation: Conversation) -> None`, `async get(conversation_id: str) -> Conversation \| None` |

**Constraints:**
- `ABC` + `@abstractmethod`. No `Protocol`.
- Methods take/return domain entities only.

### Layer 3 — application (parallel, depends on ports + domain)

| File | Contents |
|---|---|
| `app/application/__init__.py` | `__all__` |
| `app/application/use_cases/__init__.py` | `__all__` |
| `app/application/registry.py` | `Registry[T]` generic class |
| `app/application/use_cases/process_incoming_message.py` | `ProcessIncomingMessage` use case |

**Registry contract:**
- Generic over `T`.
- `register(key: str, instance: T) -> None` — raises `RegistryDuplicateError` on duplicate (case-insensitive).
- `get(key: str) -> T` — raises `RegistryKeyError` on missing.
- Stores instances. Keys normalized to lowercase.

**ProcessIncomingMessage contract:**
- Constructor: `(llm: LLMPort, repo: RepositoryPort, log: LoggerPort)`
- One public method: `async execute(msg: IncomingMessage) -> OutgoingMessage`
- Flow: load/create conversation from repo → call LLM → save conversation → return OutgoingMessage.

### Layer 4 — adapters (sequential, depends on ports)

| File | Contents |
|---|---|
| `app/adapters/__init__.py` | empty |
| `app/adapters/logging/__init__.py` | empty |
| `app/adapters/logging/structlog_logger.py` | `StructlogLogger(LoggerPort)` using structlog |

**StructlogLogger:**
- Wraps `structlog.get_logger()`.
- Each method calls the structlog equivalent, passing `**fields` as bound vars.
- No domain logic.

### Layer 5 — config + api (parallel, depends on adapters)

| File | Contents |
|---|---|
| `app/config.py` | `Settings(BaseSettings)` — `app_name`, `log_level`, `default_channel` |
| `app/api/__init__.py` | empty |
| `app/api/schemas.py` | `IncomingMessageSchema(BaseModel)`, `OutgoingMessageSchema(BaseModel)` |
| `app/api/deps.py` | `get_settings()`, `get_logger()`, `get_llm()`, `get_repo()` — all via `lru_cache` |
| `app/api/router.py` | `POST /messages` — receives `IncomingMessageSchema`, runs `ProcessIncomingMessage`, returns `OutgoingMessageSchema` |

**Pydantic schemas:**
- `IncomingMessageSchema`: `sender: str`, `content: str`, `channel: str`
- `OutgoingMessageSchema`: `content: str`, `channel: str`
- Conversion to/from domain entities at boundary in router.

### Layer 6 — entrypoint + tests (parallel, depends on all)

| File | Contents |
|---|---|
| `main.py` | FastAPI app init, include router, configure structlog |
| `tests/__init__.py` | empty |
| `tests/conftest.py` | shared fixtures: `make_incoming_message()` factory |
| `tests/unit/__init__.py` | empty |
| `tests/unit/domain/__init__.py` | empty |
| `tests/unit/domain/test_entities.py` | entity creation, frozen/immutability |
| `tests/unit/domain/test_exceptions.py` | exception hierarchy |
| `tests/unit/application/__init__.py` | empty |
| `tests/unit/application/test_registry.py` | register/get happy path, duplicate raises, missing raises, case-insensitive |
| `tests/unit/application/use_cases/__init__.py` | empty |
| `tests/unit/application/use_cases/test_process_incoming_message.py` | mocked ports, execute returns OutgoingMessage |

---

## Verification gates

After **each layer**:
```
ruff check . && ruff format --check . && pyright
```

After **layer 6**:
```
pytest --tb=short
```

All gates must be green before next layer starts.

---

## Constraints (from CLAUDE.md)

- `domain/` → stdlib only, `@dataclass(frozen=True, slots=True)`, no Pydantic
- Ports → `ABC` + `@abstractmethod`, no Protocol
- One use case per file, one public method `execute`
- Async for all I/O ports
- `LoggerPort` — no `print()`, no naked `logging`
- Errors → all inherit `DomainError`
- No singletons → `lru_cache` in `api/deps.py`
- `pyright --strict` must pass, no `Any` without noqa
- Line length 100

---

## Out of scope (Cycle 2+)

- WhatsApp / Telegram / Email adapters
- OpenAI / Anthropic LLM adapters
- SQLite / aiosqlite repository adapter
- Authentication
- Multi-conversation state
