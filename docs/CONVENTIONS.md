# Coding Conventions

> Mechanical rules. For the *why*, see `ARCHITECTURE.md`. For project-wide guardrails, see `CLAUDE.md`.

## Naming

| Kind | Style | Example |
|---|---|---|
| Module | `snake_case` | `process_message.py` |
| Package | `snake_case` | `agent` |
| Class | `PascalCase` | `AgentPort` |
| Function/method | `snake_case` | `run_agent` |
| Constant | `UPPER_SNAKE` | `DEFAULT_TIMEOUT_S` |
| Private | leading `_` | `_internal_state` |
| Type var | single upper letter | `T`, `K`, `V` |

### Suffix conventions

| Kind | Suffix | Example |
|---|---|---|
| Port (ABC) | `Port` | `AgentPort`, `RepositoryPort` |
| Adapter | adapter target | `AgnoAgent`, `PostgresRepository` |
| Pydantic schema | `Schema` | `IncomingMessageSchema` |
| Domain entity | none | `Message`, `Conversation` |
| Use case | verb phrase | `ProcessIncomingMessage` |
| Exception | `Error` | `RegistryDuplicateError` |

## Files & layout

- One **public** class per module. Helpers may share if used only by that class.
- Test path mirrors source: `app/application/use_cases/x.py` → `tests/unit/application/use_cases/test_x.py`.
- `__init__.py` exports only public surface. Use explicit `__all__`.

## Imports

- **Absolute** from `app.*`. No `from ..foo import bar`.
- Group: stdlib → third-party → first-party. `ruff` enforces.
- `from __future__ import annotations` at top of every module.
- Type-only imports inside `if TYPE_CHECKING:`.

## Type hints

- Mandatory on every function signature, including return type (use `-> None` explicitly).
- Use `from collections.abc import` for `Sequence`, `Mapping`, `Iterable`, `Awaitable`.
- Prefer `list[X]` over `List[X]` (we are 3.12+).
- Generics: declare `TypeVar` at module top with `bound=` when applicable.
- `Any` is banned. If unavoidable, add `# noqa: ANN401` with a one-line justification.

## Domain entities

```python
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True, slots=True)
class Message:
    id: str
    role: str
    content: str
    timestamp: datetime
```

Rules:
- `frozen=True` always.
- `slots=True` always.
- No methods that touch I/O. Pure logic only.
- No Pydantic. No external libs.

## Ports

```python
from abc import ABC, abstractmethod
from app.domain.entities import Conversation

class AgentPort(ABC):
    @abstractmethod
    async def run(self, message: str, conversation: Conversation) -> str: ...
```

Rules:
- `ABC` + `@abstractmethod`. No `Protocol`.
- Methods take/return domain entities, never DTOs.
- Async for I/O. Sync for pure computation.

## Use cases

```python
class ProcessIncomingMessage:
    def __init__(self, agent: AgentPort, repo: RepositoryPort, log: LoggerPort) -> None:
        self._agent = agent
        self._repo = repo
        self._log = log

    async def execute(self, msg: IncomingMessage) -> Message:
        ...
```

Rules:
- Constructor takes ports. No defaults pointing to concrete classes.
- One public method, named `execute`.
- Returns a domain entity or `None`. Never a DTO.

## Adapters

- Translate external lib types ↔ domain entities at the boundary.
- Wrap external exceptions: `try: ... except AgnoError as e: raise AgentError(...) from e`.
- No domain logic inside adapters.

## Errors

```python
# app/domain/exceptions.py
class DomainError(Exception): ...
class AgentError(DomainError): ...
class RegistryError(DomainError): ...
class RegistryDuplicateError(RegistryError): ...
class RegistryKeyError(RegistryError): ...
```

Rules:
- All raise paths through `DomainError` subclasses.
- Adapters define their own subclass of `DomainError` (e.g., `AgentError`).
- Never raise `Exception` or `RuntimeError` directly in app code.

## Async

- I/O = async. CPU = sync.
- No `asyncio.run()` outside `main.py`.
- No `time.sleep` — use `asyncio.sleep`.
- Tests: `pytest-asyncio` with `asyncio_mode = "auto"` (already set).

## Logging

```python
class LoggerPort(ABC):
    @abstractmethod
    def info(self, event: str, **fields: object) -> None: ...
    # debug, warning, error similar
```

Rules:
- Structured. Pass fields as kwargs, not f-strings.
- Never log raw user content without redaction (PII).
- `event` is a stable string id, not a sentence.

## Testing

- **Arrange / Act / Assert** with blank lines separating.
- One assertion concept per test (multiple `assert` lines OK if they verify the same outcome).
- Test names: `test_<unit>_<condition>_<expected>`. Example: `test_registry_duplicate_key_raises`.
- Fixtures in nearest `conftest.py`. No global mocks.
- Never mock the SUT. If you need to, the design is wrong.

## Commits

Conventional Commits. Examples:

```
feat(agent): add sales segment adapter
fix(registry): case-insensitive lookup ignored unicode
refactor(application): extract prompt strategy
test(domain): add Message equality cases
chore(deps): bump pydantic to 2.10
docs: ADR-009 add caching strategy
```

Body (optional) explains *why*. Footer for breaking changes:

```
BREAKING CHANGE: AgentPort.run now returns a Message.
```

## Pull request / branch (when applicable)

- Branch: `<type>/<short-slug>` — `feat/sales-agent`, `fix/registry-case`.
- One concern per PR. If it touches > 3 layers, split it.
- PR description: what + why + how to verify. Link to ADR if architectural.
