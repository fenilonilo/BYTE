# Marcelo — Personal AI Assistant

> Auto-loaded project guidelines. Read these before any code change.

## Project type

Single-user personal AI assistant. **Not** SaaS, not multi-tenant. Optimize for solo dev velocity + future channel/tool extensibility.

## Architecture

**Hexagonal (Ports & Adapters)** — chosen because the project must swap channels (WhatsApp ↔ Telegram ↔ Email) and LLMs without rewriting domain logic.

```
app/
├── domain/          # Pure Python. Zero external deps. dataclasses only.
├── ports/           # ABCs. Contracts.
├── application/     # Use cases + Registry. Imports domain + ports only.
├── adapters/        # Concrete implementations of ports (driven side).
│   ├── messaging/
│   ├── tools/
│   ├── llm/
│   └── repository/
├── api/             # Driving adapter (FastAPI). DTOs (Pydantic) live here.
└── config.py        # pydantic-settings
```

**Dependency rule:** arrows point inward. `domain` knows nothing. `application` knows `domain` + `ports`. `adapters` + `api` know everything.

## Hard rules (do not violate)

1. **`domain/` is Pydantic-free.** Use `@dataclass(frozen=True, slots=True)`. Pydantic = boundary only (api/, config).
2. **Every port is `ABC` + `@abstractmethod`.** No Protocol classes for ports — explicit > duck typing here.
3. **One use case per file** under `application/use_cases/`. Class name = file name in PascalCase.
4. **Async-first** for all I/O ports (messaging, llm, repository, tools). Domain stays sync.
5. **Type hints mandatory.** `pyright --strict` must pass. No `Any` without `# noqa: <reason>`.
6. **No `print()`.** Use `LoggerPort` (structlog adapter).
7. **Errors:** all domain errors inherit `app.domain.exceptions.DomainError`. Adapters wrap external errors before crossing the port boundary.
8. **No singleton classes.** Use `lru_cache` in `api/deps.py` for DI.

## Testing

- **TDD required for:** Registry, Ports contracts, Use Cases, domain entities with logic.
- **TDD optional for:** adapters (use integration tests when adapter is real).
- **Coverage targets:** `domain/` + `application/` ≥ 80%. Adapters not measured (excluded in `pyproject.toml`).
- **Test layout mirrors source:** `tests/unit/application/test_process_message.py` ↔ `app/application/use_cases/process_message.py`.
- **Markers:** `@pytest.mark.unit` (default), `integration`, `slow`.

## Tooling

| Tool | Role | Command |
|---|---|---|
| `ruff` | lint + format | `ruff check . && ruff format .` |
| `pyright` | type check (strict) | `pyright` |
| `pytest` | tests + coverage | `pytest` |
| `pre-commit` | gate before commit | `pre-commit run --all-files` |

Python 3.12+. `uv` or `pip` — agnostic.

## Coding conventions

- **Naming:** modules `snake_case`, classes `PascalCase`, functions `snake_case`, constants `UPPER_SNAKE`.
- **Imports:** absolute from `app.*`. No relative imports across layers.
- **Line length:** 100.
- **Docstrings:** only for public ports + use cases. Format: one-line summary + args/returns if non-obvious. No docstrings on dataclasses or trivial helpers.
- **No comments** explaining what — names should. Comments only for non-obvious why.
- **Pydantic models** end with `Schema` suffix (`IncomingMessageSchema`). Domain entities have no suffix (`Message`).
- **Ports** end with `Port` (`MessagingPort`).
- **Use cases** are verb phrases (`ProcessIncomingMessage`, not `MessageProcessor`).

## Commits

Conventional Commits enforced via pre-commit:
- `feat:` new capability
- `fix:` bug fix
- `refactor:` no behavior change
- `test:` test-only change
- `chore:` deps, config, scaffolding
- `docs:` docs only

Scope optional: `feat(messaging): add telegram adapter`.

## Registry contract

The `Registry[T]` in `application/registry.py` is the project's central extension point. Rules:

- **Lookup:** case-insensitive on string keys.
- **Duplicate registration:** raises `RegistryDuplicateError`. No silent overwrites.
- **Missing key:** raises `RegistryKeyError`.
- **Lifecycle:** stores instances (singleton-per-registry). For per-call factories, register a callable and document it.
- **Generic over `T`** so the same class powers messaging, tools, LLMs.

## What Claude should do in future sessions

- **Before writing code:** verify the layer (`domain`/`application`/`adapters`/`api`). Check the dependency rule.
- **Before adding a dep:** confirm it lives outside `domain/`. If it must touch domain, that's a smell — ask first.
- **Before "just adding" a feature:** check if a use case already exists. Extend, don't duplicate.
- **Before merging:** run `ruff check`, `pyright`, `pytest`. All three green = ship.
- **When stuck:** read `docs/ARCHITECTURE.md` for the *why*, `docs/CONVENTIONS.md` for the *how*.

## Anti-patterns (reject on sight)

- Pydantic in `domain/` — boundary leak.
- `print()` or naked `logging` calls — use `LoggerPort`.
- Use case importing an adapter directly — must go through a port.
- New abstraction without a second concrete implementation in sight — YAGNI.
- Test that mocks the SUT — refactor instead.
- Function > 50 lines without justification — split.
- Class with > 5 public methods — likely SRP violation.
