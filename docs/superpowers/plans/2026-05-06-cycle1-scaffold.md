# Cycle 1 Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully runnable hexagonal scaffold for the Marcelo personal AI assistant — domain entities, ports, registry, one use case, stub adapters, and a FastAPI endpoint — all green on ruff + pyright strict + pytest.

**Architecture:** Hexagonal (Ports & Adapters). Dependency arrows point inward: `domain` → zero deps; `ports` → domain; `application` → ports + domain; `adapters` → ports; `api` → everything. Each layer verified with `ruff + pyright` before next layer starts. TDD for all components with logic.

**Tech Stack:** Python 3.12, FastAPI, pydantic-settings, structlog, pytest + pytest-asyncio, ruff, pyright

---

## File Map

```
app/
├── __init__.py
├── config.py                                         # Task 13
├── domain/
│   ├── __init__.py
│   ├── entities.py                                   # Task 3
│   └── exceptions.py                                 # Task 2
├── ports/
│   ├── __init__.py
│   ├── logger.py                                     # Task 4  ┐
│   ├── messaging.py                                  # Task 5  │ parallel
│   ├── llm.py                                        # Task 6  │
│   └── repository.py                                 # Task 7  ┘
├── application/
│   ├── __init__.py
│   ├── registry.py                                   # Task 8  ┐ parallel
│   └── use_cases/
│       ├── __init__.py
│       └── process_incoming_message.py               # Task 9  ┘
├── adapters/
│   ├── __init__.py
│   ├── logging/
│   │   ├── __init__.py
│   │   └── structlog_logger.py                       # Task 10 ┐
│   ├── llm/
│   │   ├── __init__.py
│   │   └── stub_llm.py                               # Task 11 │ parallel
│   └── repository/
│       ├── __init__.py
│       └── in_memory_repository.py                   # Task 12 ┘
└── api/
    ├── __init__.py
    ├── schemas.py                                    # Task 14 ┐ parallel with 13
    ├── deps.py                                       # Task 15
    └── router.py                                     # Task 16
main.py                                               # Task 17
tests/
├── __init__.py
├── unit/
│   ├── __init__.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── test_exceptions.py                        # Task 2
│   │   └── test_entities.py                          # Task 3
│   └── application/
│       ├── __init__.py
│       ├── test_registry.py                          # Task 8
│       └── use_cases/
│           ├── __init__.py
│           └── test_process_incoming_message.py      # Task 9
```

---

## Phase 1 — Foundation (sequential)

### Task 1: Package structure

**Files:** All `__init__.py` listed in the file map above (15 files)

- [ ] **Step 1: Create all package init files**

Create each file with the content shown. Files marked "empty" get just a newline.

```python
# app/__init__.py  — empty

# app/domain/__init__.py
__all__ = ["entities", "exceptions"]

# app/ports/__init__.py
__all__ = ["logger", "messaging", "llm", "repository"]

# app/application/__init__.py
__all__ = ["registry", "use_cases"]

# app/application/use_cases/__init__.py
__all__ = ["process_incoming_message"]

# app/adapters/__init__.py  — empty
# app/adapters/logging/__init__.py  — empty
# app/adapters/llm/__init__.py  — empty
# app/adapters/repository/__init__.py  — empty
# app/api/__init__.py  — empty
# tests/__init__.py  — empty
# tests/unit/__init__.py  — empty
# tests/unit/domain/__init__.py  — empty
# tests/unit/application/__init__.py  — empty
# tests/unit/application/use_cases/__init__.py  — empty
```

- [ ] **Step 2: Verify Python can find packages**

```
python -c "import app"
```
Expected: no output (import succeeds)

- [ ] **Step 3: Commit**

```bash
git add app/ tests/
git commit -m "chore: initialize hexagonal package structure"
```

---

### Task 2: Domain exceptions (TDD)

**Files:**
- Create: `tests/unit/domain/test_exceptions.py`
- Create: `app/domain/exceptions.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/domain/test_exceptions.py
from __future__ import annotations

import pytest

from app.domain.exceptions import (
    DomainError,
    MessageError,
    RegistryDuplicateError,
    RegistryError,
    RegistryKeyError,
)


def test_domain_error_is_exception() -> None:
    assert issubclass(DomainError, Exception)


def test_domain_error_can_be_raised() -> None:
    with pytest.raises(DomainError):
        raise DomainError("something went wrong")


def test_message_error_is_domain_error() -> None:
    assert issubclass(MessageError, DomainError)


def test_registry_error_is_domain_error() -> None:
    assert issubclass(RegistryError, DomainError)


def test_registry_duplicate_error_is_registry_error() -> None:
    assert issubclass(RegistryDuplicateError, RegistryError)


def test_registry_key_error_is_registry_error() -> None:
    assert issubclass(RegistryKeyError, RegistryError)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/domain/test_exceptions.py -v
```
Expected: `ImportError` — `app.domain.exceptions` not found

- [ ] **Step 3: Implement exceptions**

```python
# app/domain/exceptions.py
from __future__ import annotations


class DomainError(Exception):
    """Base for all domain errors."""


class MessageError(DomainError):
    """Errors related to message processing."""


class RegistryError(DomainError):
    """Base for registry errors."""


class RegistryDuplicateError(RegistryError):
    """Raised when registering a key that already exists."""


class RegistryKeyError(RegistryError):
    """Raised when looking up a key that does not exist."""
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/unit/domain/test_exceptions.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Verify with ruff + pyright**

```
ruff check app/domain/exceptions.py && pyright app/domain/exceptions.py
```
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add app/domain/exceptions.py tests/unit/domain/test_exceptions.py
git commit -m "feat(domain): add DomainError exception hierarchy"
```

---

### Task 3: Domain entities (TDD)

**Files:**
- Create: `tests/unit/domain/test_entities.py`
- Create: `app/domain/entities.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/domain/test_entities.py
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from app.domain.entities import Conversation, IncomingMessage, Message, OutgoingMessage


NOW = datetime.now(tz=timezone.utc)


def test_message_fields() -> None:
    msg = Message(id="1", role="user", content="hello", timestamp=NOW)
    assert msg.id == "1"
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.timestamp == NOW


def test_message_is_frozen() -> None:
    msg = Message(id="1", role="user", content="hello", timestamp=NOW)
    with pytest.raises(Exception):
        msg.content = "changed"  # type: ignore[misc]


def test_incoming_message_defaults() -> None:
    msg = IncomingMessage(id="2", sender="alice", content="hi", channel="api", timestamp=NOW)
    assert msg.conversation_id is None


def test_incoming_message_with_conversation_id() -> None:
    msg = IncomingMessage(
        id="3",
        sender="alice",
        content="hi",
        channel="api",
        timestamp=NOW,
        conversation_id="conv-1",
    )
    assert msg.conversation_id == "conv-1"


def test_outgoing_message_fields() -> None:
    msg = OutgoingMessage(content="hello back", channel="api", recipient="alice")
    assert msg.content == "hello back"
    assert msg.channel == "api"
    assert msg.recipient == "alice"


def test_conversation_creation() -> None:
    conv = Conversation(id="c1", messages=(), created_at=NOW)
    assert conv.id == "c1"
    assert conv.messages == ()


def test_conversation_with_message_appends() -> None:
    conv = Conversation(id="c1", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    new_conv = conv.with_message(msg)
    assert len(new_conv.messages) == 1
    assert new_conv.messages[0] == msg


def test_conversation_with_message_original_unchanged() -> None:
    conv = Conversation(id="c1", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    conv.with_message(msg)
    assert len(conv.messages) == 0


def test_conversation_with_message_preserves_metadata() -> None:
    conv = Conversation(id="c1", messages=(), created_at=NOW)
    msg = Message(id="m1", role="user", content="hi", timestamp=NOW)
    new_conv = conv.with_message(msg)
    assert new_conv.id == "c1"
    assert new_conv.created_at == NOW
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/domain/test_entities.py -v
```
Expected: `ImportError` — `app.domain.entities` not found

- [ ] **Step 3: Implement entities**

```python
# app/domain/entities.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    role: str
    content: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    id: str
    sender: str
    content: str
    channel: str
    timestamp: datetime
    conversation_id: str | None = None


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    content: str
    channel: str
    recipient: str


@dataclass(frozen=True, slots=True)
class Conversation:
    id: str
    messages: tuple[Message, ...]
    created_at: datetime

    def with_message(self, msg: Message) -> Conversation:
        return Conversation(
            id=self.id,
            messages=(*self.messages, msg),
            created_at=self.created_at,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/domain/test_entities.py -v
```
Expected: 9 PASSED

- [ ] **Step 5: Verify entire domain layer**

```
ruff check app/domain/ && pyright app/domain/
```
Expected: no errors

- [ ] **Step 6: Run all domain tests**

```
pytest tests/unit/domain/ -v
```
Expected: 15 PASSED (6 exceptions + 9 entities)

- [ ] **Step 7: Commit**

```bash
git add app/domain/entities.py tests/unit/domain/test_entities.py
git commit -m "feat(domain): add Message, Conversation, IncomingMessage, OutgoingMessage entities"
```

---

## Phase 2 — Ports (Tasks 4–7 parallel, all depend on Phase 1)

> Tasks 4, 5, 6, 7 are independent — dispatch to parallel subagents after Task 3 completes.

### Task 4: LoggerPort

**Files:**
- Create: `app/ports/logger.py`

- [ ] **Step 1: Implement LoggerPort**

```python
# app/ports/logger.py
from __future__ import annotations

from abc import ABC, abstractmethod


class LoggerPort(ABC):
    @abstractmethod
    def debug(self, event: str, **fields: object) -> None: ...

    @abstractmethod
    def info(self, event: str, **fields: object) -> None: ...

    @abstractmethod
    def warning(self, event: str, **fields: object) -> None: ...

    @abstractmethod
    def error(self, event: str, **fields: object) -> None: ...
```

- [ ] **Step 2: Verify**

```
ruff check app/ports/logger.py && pyright app/ports/logger.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/ports/logger.py
git commit -m "feat(ports): add LoggerPort"
```

---

### Task 5: MessagingPort

**Files:**
- Create: `app/ports/messaging.py`

- [ ] **Step 1: Implement MessagingPort**

```python
# app/ports/messaging.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.domain.entities import IncomingMessage, OutgoingMessage


class MessagingPort(ABC):
    @abstractmethod
    async def send(self, message: OutgoingMessage) -> None: ...

    @abstractmethod
    def receive(self) -> AsyncIterator[IncomingMessage]: ...
```

- [ ] **Step 2: Verify**

```
ruff check app/ports/messaging.py && pyright app/ports/messaging.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/ports/messaging.py
git commit -m "feat(ports): add MessagingPort"
```

---

### Task 6: LLMPort

**Files:**
- Create: `app/ports/llm.py`

- [ ] **Step 1: Implement LLMPort**

```python
# app/ports/llm.py
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import Conversation


class LLMPort(ABC):
    @abstractmethod
    async def complete(self, prompt: str, conversation: Conversation) -> str: ...
```

- [ ] **Step 2: Verify**

```
ruff check app/ports/llm.py && pyright app/ports/llm.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/ports/llm.py
git commit -m "feat(ports): add LLMPort"
```

---

### Task 7: RepositoryPort

**Files:**
- Create: `app/ports/repository.py`

- [ ] **Step 1: Implement RepositoryPort**

```python
# app/ports/repository.py
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities import Conversation


class RepositoryPort(ABC):
    @abstractmethod
    async def save(self, conversation: Conversation) -> None: ...

    @abstractmethod
    async def get(self, conversation_id: str) -> Conversation | None: ...
```

- [ ] **Step 2: Verify**

```
ruff check app/ports/repository.py && pyright app/ports/repository.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/ports/repository.py
git commit -m "feat(ports): add RepositoryPort"
```

---

## Phase 3 — Application (Tasks 8–9 parallel, depend on Phase 2)

> Tasks 8 and 9 are independent — dispatch to parallel subagents after all Phase 2 tasks complete.

### Task 8: Registry (TDD)

**Files:**
- Create: `tests/unit/application/test_registry.py`
- Create: `app/application/registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/application/test_registry.py
from __future__ import annotations

import pytest

from app.application.registry import Registry
from app.domain.exceptions import RegistryDuplicateError, RegistryKeyError


def test_register_and_get_happy_path() -> None:
    registry: Registry[str] = Registry()
    registry.register("key", "value")
    assert registry.get("key") == "value"


def test_register_duplicate_raises() -> None:
    registry: Registry[str] = Registry()
    registry.register("key", "first")
    with pytest.raises(RegistryDuplicateError, match="key"):
        registry.register("key", "second")


def test_get_missing_key_raises() -> None:
    registry: Registry[str] = Registry()
    with pytest.raises(RegistryKeyError, match="missing"):
        registry.get("missing")


def test_lookup_case_insensitive() -> None:
    registry: Registry[str] = Registry()
    registry.register("WhatsApp", "adapter")
    assert registry.get("whatsapp") == "adapter"
    assert registry.get("WHATSAPP") == "adapter"
    assert registry.get("WhatsApp") == "adapter"


def test_register_duplicate_case_insensitive() -> None:
    registry: Registry[str] = Registry()
    registry.register("TELEGRAM", "adapter")
    with pytest.raises(RegistryDuplicateError):
        registry.register("telegram", "other")


def test_registry_stores_same_instance() -> None:
    class MyService:
        pass

    svc = MyService()
    registry: Registry[MyService] = Registry()
    registry.register("svc", svc)
    assert registry.get("svc") is svc
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/application/test_registry.py -v
```
Expected: `ImportError` — `app.application.registry` not found

- [ ] **Step 3: Implement Registry**

```python
# app/application/registry.py
from __future__ import annotations

from typing import Generic, TypeVar

from app.domain.exceptions import RegistryDuplicateError, RegistryKeyError

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self) -> None:
        self._store: dict[str, T] = {}

    def register(self, key: str, instance: T) -> None:
        normalized = key.lower()
        if normalized in self._store:
            raise RegistryDuplicateError(f"Key already registered: {key!r}")
        self._store[normalized] = instance

    def get(self, key: str) -> T:
        normalized = key.lower()
        if normalized not in self._store:
            raise RegistryKeyError(f"Key not found: {key!r}")
        return self._store[normalized]
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/application/test_registry.py -v
```
Expected: 6 PASSED

- [ ] **Step 5: Verify**

```
ruff check app/application/registry.py && pyright app/application/registry.py
```
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add app/application/registry.py tests/unit/application/test_registry.py
git commit -m "feat(application): add generic Registry with case-insensitive lookup"
```

---

### Task 9: ProcessIncomingMessage use case (TDD)

**Files:**
- Create: `tests/unit/application/use_cases/test_process_incoming_message.py`
- Create: `app/application/use_cases/process_incoming_message.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/application/use_cases/test_process_incoming_message.py
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import Conversation, IncomingMessage, OutgoingMessage


NOW = datetime.now(tz=timezone.utc)


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
def mock_llm() -> AsyncMock:
    llm = AsyncMock()
    llm.complete.return_value = "Hello back!"
    return llm


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
    mock_llm: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    assert result.content == "Hello back!"
    assert result.channel == "api"
    assert result.recipient == "user-1"


@pytest.mark.unit
async def test_execute_calls_llm(
    incoming_msg: IncomingMessage,
    mock_llm: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_llm.complete.assert_called_once()


@pytest.mark.unit
async def test_execute_saves_conversation(
    incoming_msg: IncomingMessage,
    mock_llm: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_repo.save.assert_called_once()


@pytest.mark.unit
async def test_execute_loads_existing_conversation(
    mock_llm: AsyncMock,
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
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    await use_case.execute(msg)
    mock_repo.get.assert_called_once_with("conv-123")


@pytest.mark.unit
async def test_execute_creates_conversation_when_none(
    incoming_msg: IncomingMessage,
    mock_llm: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    mock_repo.get.return_value = None
    use_case = ProcessIncomingMessage(llm=mock_llm, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    mock_repo.save.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/application/use_cases/test_process_incoming_message.py -v
```
Expected: `ImportError` — `app.application.use_cases.process_incoming_message` not found

- [ ] **Step 3: Implement use case**

```python
# app/application/use_cases/process_incoming_message.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.domain.entities import Conversation, IncomingMessage, Message, OutgoingMessage
from app.ports.llm import LLMPort
from app.ports.logger import LoggerPort
from app.ports.repository import RepositoryPort


class ProcessIncomingMessage:
    def __init__(self, llm: LLMPort, repo: RepositoryPort, log: LoggerPort) -> None:
        self._llm = llm
        self._repo = repo
        self._log = log

    async def execute(self, msg: IncomingMessage) -> OutgoingMessage:
        conv_id = msg.conversation_id or str(uuid4())
        conversation = await self._repo.get(conv_id)
        if conversation is None:
            conversation = Conversation(
                id=conv_id,
                messages=(),
                created_at=datetime.now(tz=timezone.utc),
            )

        user_msg = Message(
            id=str(uuid4()),
            role="user",
            content=msg.content,
            timestamp=msg.timestamp,
        )
        conversation = conversation.with_message(user_msg)

        self._log.info("llm.complete.start", conversation_id=conv_id)
        response_text = await self._llm.complete(
            prompt=msg.content,
            conversation=conversation,
        )

        assistant_msg = Message(
            id=str(uuid4()),
            role="assistant",
            content=response_text,
            timestamp=datetime.now(tz=timezone.utc),
        )
        conversation = conversation.with_message(assistant_msg)

        await self._repo.save(conversation)
        self._log.info("llm.complete.done", conversation_id=conv_id)

        return OutgoingMessage(
            content=response_text,
            channel=msg.channel,
            recipient=msg.sender,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/application/use_cases/test_process_incoming_message.py -v
```
Expected: 5 PASSED

- [ ] **Step 5: Verify**

```
ruff check app/application/ && pyright app/application/
```
Expected: no errors

- [ ] **Step 6: Run all application tests**

```
pytest tests/unit/application/ -v
```
Expected: 11 PASSED (6 registry + 5 use case)

- [ ] **Step 7: Commit**

```bash
git add app/application/use_cases/process_incoming_message.py tests/unit/application/use_cases/test_process_incoming_message.py
git commit -m "feat(application): add ProcessIncomingMessage use case"
```

---

## Phase 4 — Adapters (Tasks 10–12 parallel, depend on Phase 3)

> Tasks 10, 11, 12 are independent — dispatch to parallel subagents after all Phase 3 tasks complete.

### Task 10: StructlogLogger adapter

**Files:**
- Create: `app/adapters/logging/structlog_logger.py`

- [ ] **Step 1: Implement StructlogLogger**

```python
# app/adapters/logging/structlog_logger.py
from __future__ import annotations

import structlog

from app.ports.logger import LoggerPort


class StructlogLogger(LoggerPort):
    def __init__(self) -> None:
        self._logger = structlog.get_logger()

    def debug(self, event: str, **fields: object) -> None:
        self._logger.debug(event, **fields)

    def info(self, event: str, **fields: object) -> None:
        self._logger.info(event, **fields)

    def warning(self, event: str, **fields: object) -> None:
        self._logger.warning(event, **fields)

    def error(self, event: str, **fields: object) -> None:
        self._logger.error(event, **fields)
```

- [ ] **Step 2: Verify**

```
ruff check app/adapters/logging/structlog_logger.py && pyright app/adapters/logging/structlog_logger.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/adapters/logging/structlog_logger.py
git commit -m "feat(adapters): add StructlogLogger adapter"
```

---

### Task 11: StubLLM adapter

**Files:**
- Create: `app/adapters/llm/stub_llm.py`

- [ ] **Step 1: Implement StubLLM**

```python
# app/adapters/llm/stub_llm.py
from __future__ import annotations

from app.domain.entities import Conversation
from app.ports.llm import LLMPort


class StubLLM(LLMPort):
    """Cycle 1 stub. Returns a fixed echo — replace with real LLM adapter in Cycle 2."""

    async def complete(self, prompt: str, conversation: Conversation) -> str:
        return f"[stub] Echo: {prompt}"
```

- [ ] **Step 2: Verify**

```
ruff check app/adapters/llm/stub_llm.py && pyright app/adapters/llm/stub_llm.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/adapters/llm/stub_llm.py
git commit -m "feat(adapters): add StubLLM for Cycle 1 development"
```

---

### Task 12: InMemoryRepository adapter

**Files:**
- Create: `app/adapters/repository/in_memory_repository.py`

- [ ] **Step 1: Implement InMemoryRepository**

```python
# app/adapters/repository/in_memory_repository.py
from __future__ import annotations

from app.domain.entities import Conversation
from app.ports.repository import RepositoryPort


class InMemoryRepository(RepositoryPort):
    """Cycle 1 stub. Replace with aiosqlite adapter in Cycle 2."""

    def __init__(self) -> None:
        self._store: dict[str, Conversation] = {}

    async def save(self, conversation: Conversation) -> None:
        self._store[conversation.id] = conversation

    async def get(self, conversation_id: str) -> Conversation | None:
        return self._store.get(conversation_id)
```

- [ ] **Step 2: Verify**

```
ruff check app/adapters/repository/in_memory_repository.py && pyright app/adapters/repository/in_memory_repository.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/adapters/repository/in_memory_repository.py
git commit -m "feat(adapters): add InMemoryRepository for Cycle 1 development"
```

---

## Phase 5 — Config + API

> Tasks 13 + 14 parallel first. Then Tasks 15 + 16 + 17 parallel after 13+14 complete.

### Task 13: Settings

**Files:**
- Create: `app/config.py`

- [ ] **Step 1: Implement Settings**

```python
# app/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "marcelo"
    log_level: str = "INFO"
    default_channel: str = "api"

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
```

- [ ] **Step 2: Verify**

```
ruff check app/config.py && pyright app/config.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat(config): add pydantic-settings Settings"
```

---

### Task 14: API schemas

**Files:**
- Create: `app/api/schemas.py`

- [ ] **Step 1: Implement schemas**

```python
# app/api/schemas.py
from __future__ import annotations

from pydantic import BaseModel


class IncomingMessageSchema(BaseModel):
    sender: str
    content: str
    channel: str
    conversation_id: str | None = None


class OutgoingMessageSchema(BaseModel):
    content: str
    channel: str
    recipient: str
```

- [ ] **Step 2: Verify**

```
ruff check app/api/schemas.py && pyright app/api/schemas.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/api/schemas.py
git commit -m "feat(api): add IncomingMessageSchema and OutgoingMessageSchema"
```

---

### Task 15: API dependencies

**Files:**
- Create: `app/api/deps.py`

Depends on: Tasks 10, 11, 12, 13.

- [ ] **Step 1: Implement deps**

```python
# app/api/deps.py
from __future__ import annotations

from functools import lru_cache

from app.adapters.llm.stub_llm import StubLLM
from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.repository.in_memory_repository import InMemoryRepository
from app.config import Settings
from app.ports.llm import LLMPort
from app.ports.logger import LoggerPort
from app.ports.repository import RepositoryPort


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_llm() -> LLMPort:
    return StubLLM()


@lru_cache
def get_repo() -> RepositoryPort:
    return InMemoryRepository()
```

- [ ] **Step 2: Verify**

```
ruff check app/api/deps.py && pyright app/api/deps.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/api/deps.py
git commit -m "feat(api): add DI providers via lru_cache"
```

---

### Task 16: API router

**Files:**
- Create: `app/api/router.py`

Depends on: Tasks 14, 15.

- [ ] **Step 1: Implement router**

```python
# app/api/router.py
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.deps import get_llm, get_logger, get_repo
from app.api.schemas import IncomingMessageSchema, OutgoingMessageSchema
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage
from app.ports.llm import LLMPort
from app.ports.logger import LoggerPort
from app.ports.repository import RepositoryPort

router = APIRouter()


@router.post("/messages", response_model=OutgoingMessageSchema)
async def receive_message(
    body: IncomingMessageSchema,
    llm: LLMPort = Depends(get_llm),
    repo: RepositoryPort = Depends(get_repo),
    log: LoggerPort = Depends(get_logger),
) -> OutgoingMessageSchema:
    use_case = ProcessIncomingMessage(llm=llm, repo=repo, log=log)
    incoming = IncomingMessage(
        id=str(uuid4()),
        sender=body.sender,
        content=body.content,
        channel=body.channel,
        timestamp=datetime.now(tz=timezone.utc),
        conversation_id=body.conversation_id,
    )
    outgoing = await use_case.execute(incoming)
    return OutgoingMessageSchema(
        content=outgoing.content,
        channel=outgoing.channel,
        recipient=outgoing.recipient,
    )
```

- [ ] **Step 2: Verify**

```
ruff check app/api/router.py && pyright app/api/router.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add app/api/router.py
git commit -m "feat(api): add POST /messages endpoint"
```

---

### Task 17: Application entrypoint

**Files:**
- Create: `main.py`

Depends on: Tasks 13, 16.

- [ ] **Step 1: Implement main.py**

```python
# main.py
from __future__ import annotations

import structlog
from fastapi import FastAPI

from app.api.deps import get_settings
from app.api.router import router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer(),
    ]
)

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(router, prefix="/api/v1")
```

- [ ] **Step 2: Verify**

```
ruff check main.py && pyright main.py
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: add FastAPI application entrypoint"
```

---

## Phase 6 — Full Verification

### Task 18: Final gate

- [ ] **Step 1: Full ruff check**

```
ruff check . && ruff format --check .
```
Expected: no errors, no formatting issues. If formatting issues: run `ruff format .` then re-check.

- [ ] **Step 2: Full pyright**

```
pyright
```
Expected: 0 errors. Warnings about `reportUnknownMemberType` from structlog are allowed per `pyproject.toml` config.

- [ ] **Step 3: Full test suite**

```
pytest -v --tb=short
```
Expected: 26 PASSED (15 domain + 11 application), coverage ≥ 80% for `app/domain/` + `app/application/`.

- [ ] **Step 4: Pre-commit hooks**

```
pre-commit run --all-files
```
Expected: all hooks pass.

- [ ] **Step 5: Smoke test the running server**

```
uvicorn main:app --reload
```
Then in another terminal:
```
curl -X POST http://localhost:8000/api/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"sender": "test", "content": "hello", "channel": "api"}'
```
Expected response:
```json
{"content": "[stub] Echo: hello", "channel": "api", "recipient": "test"}
```

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "chore: cycle 1 scaffold complete — hexagonal structure, all tests green"
```
