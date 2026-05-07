# Architecture

## Why Hexagonal

The assistant must speak through multiple channels (WhatsApp, Telegram, Email, CLI) and use multiple LLMs (Anthropic, OpenAI, local). The same conversation logic runs regardless. Hexagonal isolates that logic from the channel.

We chose Hexagonal over Onion or Clean because:

- **Smaller surface.** Two zones: inside (domain + use cases) vs outside (adapters).
- **Ports are explicit.** ABCs make the contract visible; no Protocol guessing.
- **Driving vs Driven** distinction matches our reality (API drives, channels/LLMs/DB are driven).

We rejected Clean Architecture's `entities/` vs `rules/` split — for a personal assistant, business rules live inside the entities or use cases. The split adds folders without adding clarity.

## Layers

```
┌──────────────────────────────────────────────────────────┐
│  api/  ──── driving adapter (FastAPI, CLI)               │
│         │                                                 │
│         ▼                                                 │
│  application/  ──── use cases + Registry                  │
│         │                                                 │
│         ▼                                                 │
│  domain/  ──── entities, value objects, domain errors     │
│         ▲                                                 │
│         │                                                 │
│  ports/  ──── ABCs the application calls                  │
│         ▲                                                 │
│         │                                                 │
│  adapters/  ──── concrete impls (driven side)             │
└──────────────────────────────────────────────────────────┘
```

**Dependency rule (strict):**

| Layer | May import |
|---|---|
| `domain/` | stdlib only |
| `ports/` | `domain/` + stdlib |
| `application/` | `domain/`, `ports/`, stdlib |
| `adapters/` | everything except `api/` |
| `api/` | everything |

Violations of this rule are caught by import linting (TID rule in ruff) + pyright.

## The Registry

The Registry is the project's only "framework-y" piece. It exists because the assistant must pick a channel or tool dynamically based on intent. Without it, every new channel is a `match` statement edit.

```python
registry = Registry[MessagingPort]()
registry.register("whatsapp", WhatsAppAdapter(...))
registry.register("telegram", TelegramAdapter(...))

channel = registry.get(intent.channel)  # case-insensitive
await channel.send(outgoing_message)
```

**Contract:** see `CLAUDE.md → Registry contract`.

## Patterns we use

| Pattern | Where | Why |
|---|---|---|
| Adapter | `adapters/**` | Heart of Hexagonal. |
| Registry | `application/registry.py` | Dynamic dispatch by name. |
| Strategy | prompt builders, summarizers | Interchangeable algorithms behind a port. |
| Dependency Injection | `api/deps.py` via `lru_cache` | No singletons, FastAPI-native. |

## Patterns we rejected

- **Factory Method as a class** — Registry already plays factory. A separate `MessagingFactory` adds a layer with no behavior.
- **Singleton** — `lru_cache` on a DI provider gives the same effect with zero ceremony and no global state.
- **Repository + UnitOfWork combo** — too heavy for a single-user assistant. We start with a simple `RepositoryPort`. Revisit if multi-aggregate transactions appear.

## Decisions log (ADRs)

### ADR-001: Hexagonal over Onion+Clean (2026-05-06)
**Context:** original spec stacked Onion + Hexagonal + Clean.
**Decision:** Hexagonal only.
**Why:** the three patterns overlap. Stacking them adds folders without isolation gain.
**Trade-off:** less "academic completeness," faster onboarding.

### ADR-002: Pydantic at boundary only (2026-05-06)
**Context:** original spec had `schemas/` at root with Pydantic everywhere.
**Decision:** Pydantic models live in `api/` and `config.py`. Domain uses `@dataclass(frozen=True, slots=True)`.
**Why:** keeps domain pure and dependency-free. Pydantic upgrades cannot break domain logic.
**Trade-off:** explicit conversion at the boundary (DTO ↔ entity). Worth the isolation.

### ADR-003: Async-first I/O (2026-05-06)
**Context:** decision between sync MVP + async migration vs async from day one.
**Decision:** async from day one for all I/O ports.
**Why:** rewriting sync→async later is painful. WhatsApp/Telegram clients are async-native.
**Trade-off:** slightly more boilerplate in tests (`pytest-asyncio`). Acceptable.

### ADR-004: One use case per file (2026-05-06)
**Context:** lean structure favored single `use_cases.py`.
**Decision:** `application/use_cases/<name>.py` from day one.
**Why:** use cases grow fast. Splitting later forces git-rename churn.
**Trade-off:** more files at start. Negligible.

### ADR-005: LoggerPort in Cycle 1 (2026-05-06)
**Context:** logging often deferred.
**Decision:** ship `LoggerPort` + structlog adapter in Cycle 1.
**Why:** retrofit cost is high; debugging without structured logs is slow.
**Trade-off:** ~30 lines extra in Cycle 1. Negligible.
