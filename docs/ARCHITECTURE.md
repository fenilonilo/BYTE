# Architecture

## Why Hexagonal

Byte is a headless personal assistant for one person: text or voice in, an answer out, with tools that act on the home, the calendar and the expenses. The pieces that will change are the model provider (OpenAI today, Gemini Live next), the smart-home vendor (Tuya), the calendar and spreadsheet providers (Google), and the datastore. The conversation and tool lifecycle does not change. Hexagonal isolates that lifecycle from all of them.

We chose Hexagonal over Onion or Clean because:

- **Smaller surface.** Two zones: inside (domain + use cases) vs outside (adapters).
- **Ports are explicit.** ABCs make the contract visible; no Protocol guessing.
- **Driving vs Driven** distinction matches our reality (the HTTP/WebSocket API and the scheduler drive; the model provider, Tuya, Google, DB and logging are driven).

We rejected Clean Architecture's `entities/` vs `rules/` split — business rules live inside the entities or use cases here. The split adds folders without adding clarity.

## Layers

```
┌──────────────────────────────────────────────────────────┐
│  api/  ──── driving adapter (FastAPI). Only entrypoint.  │
│         │                                                 │
│         ▼                                                 │
│  application/  ──── use cases, ToolRunner, tools, Registry│
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

## The tool loop

There is **one agent with all tools**. A `Tool` (ABC in `application/`) has a `ToolSpec` (name, JSON schema, segment, `requires_confirmation`) and an async `execute(args, key)` that talks to the world only through ports (`LightPort`, `ClimatePort`, `MusicPort`, `CalendarPort`, `ExpensesPort`). Tools live in a `Registry[Tool]`; `segment` is only an optional filter over it.

```python
registry = build_tool_registry(light, climate, music, calendar, expenses)   # Registry[Tool]
runner = ToolRunner(registry, pending, log)                # allowlist, timeout, shield, confirmation
reply = await ProcessChatMessage(model, store, runner, pending, log).execute(cid, text, segment)
```

Chat (`POST /messages`) and live (`WS /live`) share the registry, the runner and the confirmation rules; only the transport differs. A sensitive tool does not run when called: `ToolRunner` stores one `PendingAction` per conversation, and only the argument-free `confirm_action()` executes it, iff the very next user utterance is affirmative (`is_affirmative`). Tool execution is shielded from cancellation and bounded by a timeout that reports `estado desconhecido` rather than success or failure.

**Contract of `Registry[T]`:** case-insensitive lookup, duplicate registration raises `RegistryDuplicateError`, a missing key raises `RegistryKeyError`, `values()` lists the registered instances.

## Patterns we use

| Pattern | Where | Why |
|---|---|---|
| Adapter | `adapters/**` | Heart of Hexagonal. One adapter per outside resource. |
| Registry | `application/registry.py` | Tools by name; segments are a filter. |
| Strategy | prompt builders, summarizers | Interchangeable algorithms behind a port. |
| Dependency Injection | `api/deps.py` via `lru_cache` | No singletons, FastAPI-native. |

## Patterns we rejected

- **Factory Method as a class** — Registry already plays factory. A separate `ToolFactory` adds a layer with no behavior.
- **Singleton** — `lru_cache` on a DI provider gives the same effect with zero ceremony and no global state.
- **Repository + UnitOfWork combo** — too heavy for a single-aggregate backend. We start with a simple `ConversationStorePort`. Revisit if multi-aggregate transactions appear.
- **Sub-agents, Teams, agent-to-agent handoff** — one owner and about sixteen tools do not need routing. Cross-segment work is the single agent calling two tools. Keeps the call graph a line, not a mesh.

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
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** a single general agent versus several specialised ones, and how a request reaches the right one.
**Decision:** one `AgentPort` instance per segment, held in `Registry[AgentPort]`. The caller names the segment in the request body.
**Why:** each segment gets its own instructions, tools and model without conditionals in the use case. Explicit routing keeps the request deterministic and debuggable — no classifier silently picking the wrong agent.
**Trade-off:** the consumer must know the segment names. Cheap: they are a short, stable list.
**Alternative kept open:** an intent-classification use case in front of the registry, if auto-routing is ever wanted. It composes; it does not replace.

### ADR-008: AgentPort replaces LLMPort (2026-09-01)
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** Cycle 1 shipped `LLMPort.complete()`; the Cycle 2 design added `AgentPort.run()` alongside it, keeping `LLMPort` "for embeddings later".
**Decision:** one port. `LLMPort` and `StubLLM` deleted; `AgentPort.run(message, conversation) -> str` is the contract.
**Why:** two ports with the same shape and one implementation each is a speculative abstraction. Embeddings are not on the roadmap; when they arrive they get their own port with a real signature instead of a guessed one.
**Trade-off:** if raw completions are needed, a port has to be reintroduced. Small, and better designed with the actual requirement in hand.

### ADR-009: Speech runs on the server (2026-09-01)
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** the client is a custom ESP32-S3. Speech-to-text and text-to-speech could run on the device or on the server.
**Decision:** the device does wake-word detection locally (ESP-SR) and streams raw audio. Transcription, reasoning and synthesis all happen server-side; audio comes back over the same request.
**Why:** on-device recognition on an ESP32-S3 is limited to a fixed command set, which is the opposite of an assistant you can talk to freely. Keeping speech on the server also means the engine can be swapped without reflashing hardware, and a second client gets voice for free.
**Trade-off:** more bandwidth, and round-trip latency now includes the network. Accepted — the device is on the same LAN as the server.
**Consequence:** `SpeechToTextPort` and `TextToSpeechPort`, plus `POST /voice`. Audio never travels below the API layer; the use case still receives text.

### ADR-010: Agno Team (route mode) for intent routing (2026-09-01)
**Status:** Superseded by ADR-014 (2026-10-05).
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

### ADR-013: Model tier per role, cross-provider fallback (2026-09-02)
**Status:** Superseded by ADR-014 (2026-10-05).
**Context:** every agent ran on one model from one vendor. Byte answers by voice, so a trivial "apaga a luz" pays the same latency and price as a question that actually needs reasoning, and a single provider outage takes the whole assistant down.
**Decision:** each role gets a tier fixed at build time — the routing Team and `home` on Groq (fastest), `agenda` and `finance` on Gemini — and every tier declares an Agno `FallbackConfig`. `on_error` prefers another provider first; `on_rate_limit` prefers the same provider's other tier first. Models are configured as `<provider>:<model_id>` strings, which Agno resolves natively.
**Why:** the difficulty of a segment's work is known when the segment is written, so paying an LLM hop to classify difficulty at runtime buys nothing and costs latency on every utterance — the same reasoning ADR-010 used against a hand-written router. Splitting the two fallback lists follows the failure modes: a 429 means that model is busy while the provider is up, an error may mean it is not.
**Trade-off:** a request whose difficulty is unusual for its segment gets the wrong tier. Accepted — retuning is one env var, and the tier table lives in one dict.
**Consequence:** Anthropic is not wired in; there is no key for it. Adding it later is a config string, not a code change. `google-genai` and `groq` join the `agents` extra.
**Note:** the free Gemini tier serves no `pro` model — `gemini-2.5-pro` is closed to new accounts and `gemini-3.1-pro-preview` has a zero quota — so the heavy tier is `gemini-3.7-flash`. Revisit when the account is paid.

### ADR-014: One agent, own tool loop, OpenAI behind ports (2026-10-05)
**Context:** the Agno Team routed each utterance to a per-segment agent. The owner wants two modes — chat and a live spoken conversation that executes tools mid-conversation — for one person, with every outside integration as an adapter.
**Decision:** one agent holding every tool, a small tool loop in `ProcessChatMessage`, and OpenAI behind `ChatModelPort` (chat) and `LiveSessionPort` (Realtime, `gpt-realtime-2.1-mini`). Agno, the Team, `AgentPort` and `Registry[AgentPort]` are removed. Gemini Live is the planned second `LiveSessionPort` adapter.
**Why:** with one owner and about sixteen tools the routing hop is latency with no gain, and Agno cannot do speech-to-speech, so live would have bypassed it and defined every tool twice. At personal scale the price gap between providers is $10-40 per month, so quality (tool-call reliability, pt-BR, latency) decides, settled by an A/B day.
**Trade-off:** cross-provider fallback is gone for now; the OpenAI SDK's default retries cover 429/5xx. A second provider returns with its own adapter.
**Consequence:** supersedes ADR-007, 008, 009, 010 and 013. `segment` is an optional tool filter; an unknown segment still fails with 404.

### ADR-015: Confirmation is enforced in code (2026-10-05)
**Context:** "confirm before acting" lived only in the prompt, so a model could act first and apologise later; in live mode, noise or the assistant's own echo can look like consent.
**Decision:** a tool with `requires_confirmation` is never executed when called. `ToolRunner` stores one `PendingAction` per conversation (frozen arguments, code-generated summary, 60 s expiry). The argument-free `confirm_action()` runs it iff the pending action is armed by the very next user utterance and that utterance passes `is_affirmative` (whole words, five words or fewer, deny list wins). In live, speech that starts while the assistant is talking never confirms, and `confirm_action` waits up to 2 s for the transcript.
**Why:** the model cannot guess an id, replay one across conversations or confirm in the same turn. A restart drops pending actions, which fails safe.
**Residual risk:** a spoken "sim" from a TV or another person in the room still counts; the 60 s expiry, the next-utterance rule and the code-generated summary limit the window. In live the user hears the model's wording of the summary.

### ADR-016: Live over WebSocket, LAN exposure with TLS (2026-10-05)
**Context:** the live client is an ESP32-S3 on the LAN, which cannot reach a loopback-bound server; plain `ws://` would send the bearer token in cleartext.
**Decision:** `WS /api/v1/live` carries PCM16 mono 24 kHz audio as opaque binary frames plus JSON control events. Auth is `Authorization: Bearer` (a token of at least 32 characters). Compose binds to `127.0.0.1` by default; `BYTE_PUBLISH_HOST=<LAN IP>` opts in to LAN exposure, which requires `wss://` with a self-signed certificate pinned in the firmware. One live session at a time; a new connection replaces the old one (close code 4000).
**Why:** audio stays opaque below the API layer, the provider session is an adapter, and a half-open socket after a Wi-Fi drop cannot lock the owner out.
**Firmware requirements:** upsample 16 to 24 kHz, echo cancellation or mute while playing, buffer microphone audio until `ready`, pin the certificate, do not auto-reconnect after close code 4000.
