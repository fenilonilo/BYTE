# Architecture

## Why Hexagonal

Byte is a headless voice assistant: audio or text in, an answer out. The pieces that will change are the agent framework (Agno today), the models behind it, the smart-home vendor (Tuya), the calendar and spreadsheet providers (Google), the speech engines, and the datastore. The conversation lifecycle does not change. Hexagonal isolates that lifecycle from all of them.

We chose Hexagonal over Onion or Clean because:

- **Smaller surface.** Two zones: inside (domain + use cases) vs outside (adapters).
- **Ports are explicit.** ABCs make the contract visible; no Protocol guessing.
- **Driving vs Driven** distinction matches our reality (the HTTP API and the scheduler drive; agents, Tuya, Google, speech, DB and logging are driven).

We rejected Clean Architecture's `entities/` vs `rules/` split — business rules live inside the entities or use cases here. The split adds folders without adding clarity.

## Layers

```
┌──────────────────────────────────────────────────────────┐
│  api/  ──── driving adapter (FastAPI). Only entrypoint.  │
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

The Registry is the project's only "framework-y" piece. It is what makes the system multi-agent: one entry per segment, resolved by name at request time. Without it, every new segment is a `match` statement edit in the router.

```python
registry = Registry[AgentPort]()
registry.register("sales", AgnoAgent(segment="sales", ...))
registry.register("support", AgnoAgent(segment="support", ...))

agent = registry.get(body.segment)  # case-insensitive; raises on unknown
reply = await agent.run(body.content, conversation)
```

**Contract:** case-insensitive lookup, duplicate registration raises `RegistryDuplicateError`, missing key raises `RegistryKeyError` (mapped to HTTP 404 in the router). Stores instances, one per segment. Generic over `T` so it can serve future port types unchanged.

## Patterns we use

| Pattern | Where | Why |
|---|---|---|
| Adapter | `adapters/**` | Heart of Hexagonal. One agent adapter per segment. |
| Registry | `application/registry.py` | Dynamic dispatch by segment name. |
| Strategy | prompt builders, summarizers | Interchangeable algorithms behind a port. |
| Dependency Injection | `api/deps.py` via `lru_cache` | No singletons, FastAPI-native. |

## Patterns we rejected

- **Factory Method as a class** — Registry already plays factory. A separate `AgentFactory` adds a layer with no behavior.
- **Singleton** — `lru_cache` on a DI provider gives the same effect with zero ceremony and no global state.
- **Repository + UnitOfWork combo** — too heavy for a single-aggregate backend. We start with a simple `RepositoryPort`. Revisit if multi-aggregate transactions appear.
- **Agent-to-agent handoff** — agents do not call each other. Cross-segment work is a use case that calls two ports. Keeps the call graph a tree, not a mesh.

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
**Why:** rewriting sync→async later is painful. Agent SDKs and asyncpg are async-native.
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

### ADR-006: API-only, no channel adapters (2026-09-01)
**Context:** the original design targeted a personal assistant reachable over WhatsApp/Telegram/Email, with an eye on a GUI and vision input.
**Decision:** Byte is a headless backend. HTTP is the only interface. No GUI, no computer vision, no chat-channel adapters.
**Why:** Byte runs on a local server and serves other applications. Those consumers already own their own channels and UIs; duplicating that inside Byte doubles the surface for zero gain.
**Trade-off:** nothing talks to Byte directly out of the box — a consumer must exist. Accepted: that is the deployment model.
**Consequence:** `MessagingPort` deleted; `channel`, `sender` and `recipient` removed from the domain.

### ADR-007: One agent per segment, explicit routing (2026-09-01)
**Context:** a single general agent versus several specialised ones, and how a request reaches the right one.
**Decision:** one `AgentPort` instance per segment, held in `Registry[AgentPort]`. The caller names the segment in the request body.
**Why:** each segment gets its own instructions, tools and model without conditionals in the use case. Explicit routing keeps the request deterministic and debuggable — no classifier silently picking the wrong agent.
**Trade-off:** the consumer must know the segment names. Cheap: they are a short, stable list.
**Alternative kept open:** an intent-classification use case in front of the registry, if auto-routing is ever wanted. It composes; it does not replace.

### ADR-008: AgentPort replaces LLMPort (2026-09-01)
**Context:** Cycle 1 shipped `LLMPort.complete()`; the Cycle 2 design added `AgentPort.run()` alongside it, keeping `LLMPort` "for embeddings later".
**Decision:** one port. `LLMPort` and `StubLLM` deleted; `AgentPort.run(message, conversation) -> str` is the contract.
**Why:** two ports with the same shape and one implementation each is a speculative abstraction. Embeddings are not on the roadmap; when they arrive they get their own port with a real signature instead of a guessed one.
**Trade-off:** if raw completions are needed, a port has to be reintroduced. Small, and better designed with the actual requirement in hand.

### ADR-009: Speech runs on the server (2026-09-01)
**Context:** the client is a custom ESP32-S3. Speech-to-text and text-to-speech could run on the device or on the server.
**Decision:** the device does wake-word detection locally (ESP-SR) and streams raw audio. Transcription, reasoning and synthesis all happen server-side; audio comes back over the same request.
**Why:** on-device recognition on an ESP32-S3 is limited to a fixed command set, which is the opposite of an assistant you can talk to freely. Keeping speech on the server also means the engine can be swapped without reflashing hardware, and a second client gets voice for free.
**Trade-off:** more bandwidth, and round-trip latency now includes the network. Accepted — the device is on the same LAN as the server.
**Consequence:** `SpeechToTextPort` and `TextToSpeechPort`, plus `POST /voice`. Audio never travels below the API layer; the use case still receives text.

### ADR-010: Agno Team (route mode) for intent routing (2026-09-01)
**Context:** ADR-007 had the caller name the segment explicitly. A person speaking a sentence to a device cannot do that, so something must map an utterance onto a segment. Options: a hand-written classifier use case in front of `Registry[AgentPort]`, a single agent holding every tool, or Agno's Team in route mode.
**Decision:** Agno Team in route mode, wrapped as `AgnoTeamAgent(AgentPort)` and registered under the key `auto`. Explicit `segment` from ADR-007 survives as a direct path that skips the routing hop.
**Why:** the routing logic is already written, tested and maintained inside Agno. Writing our own classifier means owning prompt tuning and a second failure mode for no differentiated gain. Keeping per-segment agents (rather than one agent with every tool) keeps prompts and tool sets small and separately testable.
**Trade-off — accepted knowingly:** orchestration now lives inside the framework instead of inside `application/`, which is a genuine softening of the hexagonal boundary. This project's rule that "orchestration is a use case, not an agent calling an agent" is relaxed for the routing layer specifically, and for nothing else.
**Containment:** the Team is exposed as a single `AgentPort`. Nothing above `adapters/agent/` knows a Team exists. Agno types do not cross the port.
**Exit:** if Team routing becomes limiting — ordering, retries, partial failures across segments — the replacement is a `RouteUtterance` use case calling the registry directly. `AgentPort` does not change, so the swap touches one adapter and its registration.

### ADR-011: Google owns calendar and expenses (2026-09-01)
**Context:** events and monthly expenses could live in our Postgres, in Google Calendar and Sheets, or in Postgres with a sync to Google.
**Decision:** Google Calendar and Google Sheets are the system of record. Postgres holds conversation history, OAuth tokens, pending reminders and memory embeddings — never a second copy of the truth.
**Why:** the spreadsheet and the calendar are already used from a phone every day. Making Postgres authoritative would mean building an interface to view and edit them, which is a frontend, which is out of scope. Bidirectional sync was rejected outright: it is the option that generates conflict bugs.
**Trade-off:** Byte now depends on OAuth, refresh tokens and Google rate limits, and it degrades when Google is unreachable. Cached reads are allowed for latency; a cache is never promoted to source of truth.

### ADR-012: Reminders pushed over WebSocket (2026-09-01)
**Context:** bill and appointment reminders must reach the device unprompted. Options: the device polls, the server pushes over WebSocket, or the server publishes to an MQTT broker.
**Decision:** the server pushes over a WebSocket at `/ws/notifications`. A scheduler adapter wakes periodically; deciding what is due is a use case, testable without a real clock.
**Why:** polling adds latency for something time-sensitive. Between the two push options, FastAPI serves WebSocket natively, so it costs no broker container and no extra operational surface.
**Trade-off:** the server now holds connection state and must handle reconnects, which a broker would have handled. Undelivered reminders are persisted and replayed on reconnect rather than dropped.
**Revisit when:** the device sleeps deeply enough to miss pushes, or more than one client connects. That is when MQTT earns its container — not before.
