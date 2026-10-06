# Byte — Personal Assistant Backend

> Auto-loaded project guidelines. Read before any code change.
> Target design: `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md`
> (Spec 1). Where this file and the code disagree, **Current state** says which
> side is ahead.

## What this is

A JARVIS-style personal assistant, running as a **headless backend** in Docker
on a home server. It controls smart-home devices, manages a calendar, and
tracks monthly expenses — through chat or by voice.

One agent, two modes:

- **chat** — a text message in, a text reply out (`POST /messages`).
- **live** — a spoken conversation over a WebSocket (`WS /live`); the agent
  executes tools while it talks.

The live client is a **custom ESP32-S3 device**: wake word locally, audio
streamed to this server. The ESP32 is one client of a plain WebSocket protocol;
a terminal script is another. Any application can use the HTTP API.

**One owner, one person, one household.** Not a product, not multi-tenant.

**In scope:** chat, live voice, tool execution, device control, calendar,
expenses, proactive reminders (later spec).

**Explicitly out of scope — reject on sight:**

- Any GUI, TUI, web page, or desktop client. This repository ships no frontend.
- Computer vision, cameras, screen capture, OCR, image pipelines.
- Chat-channel adapters (WhatsApp, Telegram, Email).
- Multi-tenancy, user accounts, roles. One owner.

Voice is not a GUI. Audio endpoints belong here; pixels do not.

## Tools and segments

There is **one agent with all tools**. No sub-agents, no Team, no routing hop.

A **segment** is a named group of tools, used only as an optional per-request
filter (`segment` omitted or `auto` = all tools; unknown segment = `404`).

| Segment | Tools talk to | Via port |
|---|---|---|
| `home` | Lights (Tuya, local network) and the air conditioner (LG ThinQ) | `LightPort`, `ClimatePort` |
| `music` | Spotify playback on a Spotify Connect device | `MusicPort` |
| `agenda` | Events, appointments (Google Calendar) | `CalendarPort` |
| `finance` | Monthly expenses, bills (Google Sheets) | `ExpensesPort` |

**Adding a tool:**

1. Write the `Tool` (ABC) under `application/tools/`. It calls a port, never an SDK.
2. If it needs a new capability from the world, add a port and an adapter.
3. Register it in `api/deps.py` under its segment.
4. Mark `requires_confirmation` if it is destructive or physical.
5. Test the tool's behavior with the in-memory adapter; the real adapter must
   pass the same port contract suite.

A tool receives a **device name or logical key**, never a raw device id or
spreadsheet id from the model. The adapter validates it against the configured
list.

`Tool` is application code, not a port. Ports are the seams to the outside
world: the model provider, the live session, the home, the calendar, the
expense sheet, the conversation store, the logger.

## Chat and live

```
chat:  POST /messages → ProcessChatMessage → ChatModelPort ⇄ ToolRunner → reply
live:  WS /live ⇄ RunLiveSession ⇄ LiveSessionPort ⇄ ToolRunner
```

- Both modes share the `Registry[Tool]`, `ToolRunner` and confirmation rules.
- **Audio is opaque `bytes`** to `application/`: relayed between the socket and
  the live-session port, never decoded, transcribed or transformed there. The
  vendor (speech-to-speech, or STT/LLM/TTS) lives in the adapter.
- Tools execute **server-side**. The provider chooses which tool to call; it
  never holds credentials.
- Live audio contract: PCM16 mono 24 kHz, binary frames. The firmware upsamples
  16 → 24 kHz and must use echo cancellation (or mute the mic while playing).
  Full protocol in the spec.
- Transcripts are saved under the same `conversation_id`, so chat can continue
  a spoken conversation. A live session starts cold (no stored history loaded).

## Integrations

| Target | Via | Notes |
|---|---|---|
| Model provider | OpenAI (chat + Realtime) behind `ChatModelPort` / `LiveSessionPort` | Second adapter planned: Gemini Live. |
| Tuya | `tinytuya` over the local network (device id, address, local key) | Lights are physical. Keys come from the environment. |
| LG ThinQ | ThinQ Connect personal access token | The air conditioner. |
| Spotify | Web API with a refresh token (Premium) | Playback on a Connect device; `scripts/spotify_login.py` gets the token. |
| Google Calendar | OAuth 2.0 | Google is the system of record, not our DB. |
| Google Sheets | OAuth 2.0 | The expense spreadsheet you already use. |

**Every integration is a driven adapter behind a port.** A vendor SDK type never
crosses the port boundary. Vendor errors are wrapped in a `DomainError`
subclass before they leave the adapter. The OpenAI SDK appears in
`adapters/openai/` and nowhere else; Tuya and Google SDKs in their own adapter
packages and nowhere else.

Google holds the truth for calendar and expenses so they stay editable from a
phone. A cache is never treated as the source of truth.

## Proactive reminders (not built)

Byte will speak first for bills and appointments: a scheduler adapter, a use
case that decides what is due (unit-testable without a clock), and a push over
`WS /ws/notifications`. If nothing is connected the reminder is persisted and
delivered on reconnect — never silently dropped. WebSocket, not MQTT, until a
real limit is hit; mark the swap with a `ponytail:` comment then.

## Safety and security

This service controls physical devices in a home and reads personal financial
data. Hard requirements, not polish:

- **Authentication**: every route except `GET /health`, and the WebSocket, require
  `Authorization: Bearer <token>`. `BYTE_API_TOKEN` is at least 32 characters;
  the app refuses to boot otherwise. Compare with `hmac.compare_digest`. Never
  put the token in a query string.
- **Network**: `docker-compose.yml` binds to `127.0.0.1` by default. LAN
  exposure for the ESP32 is opt-in through `BYTE_PUBLISH_HOST=<LAN IP>` and
  **requires TLS (`wss://`)** with a pinned certificate. Never `0.0.0.0` on a
  host with a public interface, never a tunnel or public port.
- **Never commit credentials.** Keys and OAuth tokens come from the environment
  or encrypted storage. `.env` is gitignored; `.env.example` holds names with
  empty values only.
- **Never log secrets, tool arguments, transcripts or message content.** Log ids,
  tool names, durations and status through `LoggerPort`.
- **Destructive or physical actions confirm in code, not in the prompt.** A tool
  with `requires_confirmation` does not run when called: `ToolRunner` stores one
  pending action per conversation. It executes only through the argument-free
  `confirm_action()`, and only if the **very next user utterance** after the
  request is affirmative (`is_affirmative`, whole-word pt-BR matcher, deny list
  wins). Any other utterance drops the pending action. 60 s expiry. An agent
  must not learn that it can act first and apologise later. Today `delete_event` and
  `add_expense` always ask, and `set_climate` asks whenever it switches the air
  conditioner on or off (`Tool.needs_confirmation`); lights and music never ask. The
  lamp is never switched twice within 5 s, and the model only plays a `uri` that a
  search or the playlists returned.
- **Bound the blast radius of tools.** A tool addresses a known device list or
  the configured spreadsheet, never an id the model names.
- **Tools are idempotent**, and execution is shielded from cancellation: a
  timeout reports `estado desconhecido`, never success or failure.

## Architecture

**Hexagonal (Ports & Adapters).** The model provider, the smart-home vendor,
Google, and the datastore are all swappable behind ports.

```
app/
├── domain/          # Pure Python. Zero external deps. dataclasses + pure functions.
├── ports/           # ABCs. Contracts to the outside world.
├── application/     # Use cases, ToolRunner, PendingActionStore, Registry, tools/.
├── adapters/        # Concrete implementations (driven side).
│   ├── openai/      # ChatModelPort + LiveSessionPort
│   ├── memory/      # Home, Calendar, Expenses, ConversationStore (in-memory)
│   └── logging/
├── api/             # Driving adapter (FastAPI). Pydantic DTOs live here.
└── config.py        # pydantic-settings
```

**Dependency rule:** arrows point inward.

| Layer | May import |
|---|---|
| `domain/` | stdlib only |
| `ports/` | `domain/` + stdlib |
| `application/` | `domain/`, `ports/`, stdlib |
| `adapters/` | everything except `api/` |
| `api/` | everything |

Singletons (`PendingActionStore`, conversation store, `Registry[Tool]`) are built
once through `lru_cache` in `api/deps.py`. Use cases are built per request and
hold no state. Time-dependent code receives an injected monotonic clock.

## Persistence

Today the conversation store is in memory: last 20 messages per request context,
max 50 conversations (LRU), lost on restart. `ConversationStorePort.append` is
atomic. **PostgreSQL 16 + pgvector** (SQLAlchemy asyncio, Alembic) is a later
spec and arrives behind the same port; the `db` extra is not declared until then.

It will store conversation history, OAuth tokens, pending reminders and memory
embeddings. It will **not** store calendar events or expenses — Google owns those.

`InMemoryRepository` style adapters stay: unit tests use them. Integration tests
against Postgres use a real Postgres via testcontainers, never a mock.

## API

Prefix `/api/v1`. FastAPI. Everything async.

| Route | Purpose |
|---|---|
| `GET /health` | Liveness. Used by the Docker healthcheck. |
| `POST /messages` | Text in, text out. `segment` optional. May return `pending_confirmation.summary`. |
| `WS /live` | Spoken conversation. One session at a time; a new connection replaces the old (close code 4000). |
| `WS /ws/notifications` | Proactive pushes. Not built. |

Rules:

- Pydantic models live in `api/schemas.py` and never leak inward.
- Domain errors map to HTTP status in the router: auth 401, validation 422,
  unknown segment 404, `AgentError` 502, other `DomainError` 500 with a generic
  body. Adapters never raise HTTP.
- Input limits: `content` 1–4,000 chars; `conversation_id`
  `^[A-Za-z0-9_-]{1,64}$`.
- Versioned in the path. Breaking a response shape means `/api/v2`.

## Docker

```
docker compose up --build
```

- Loopback by default; LAN exposure only as described in **Safety and security**.
- Config from env (`BYTE_` prefix, **including provider keys**). Settings are
  validated at boot in the FastAPI lifespan; a bad config fails fast.
- The container runs as a non-root user; dependencies are locked.
- `.env.example` is tracked; `.env` is not.
- A service joins compose in the same change that adds the code using it. No
  idle containers.

## Hard rules (do not violate)

1. **`domain/` is Pydantic-free.** `@dataclass(frozen=True, slots=True)`.
   Pydantic is boundary-only (`api/`, `config.py`).
2. **Every port is `ABC` + `@abstractmethod`.** No Protocol classes for ports.
3. **One use case per file** under `application/use_cases/`. Class name = file
   name in PascalCase.
4. **Async-first** for all I/O ports. Domain stays sync.
5. **Type hints mandatory.** `pyright --strict` must pass. No bare `Any`.
6. **No `print()`.** Use `LoggerPort`.
7. **Errors** inherit `app.domain.exceptions.DomainError`. Adapters wrap
   external errors before crossing the port boundary and keep `__cause__`.
8. **No singletons** except through `lru_cache` in `api/deps.py`.
9. **No new abstraction without a second concrete implementation in sight.**
10. **Audio bytes are opaque** below the API layer: relayed, never interpreted.

## Testing

- **TDD required for:** `Registry`, `ToolRunner` (full confirmation matrix),
  `is_affirmative`, `PendingActionStore`, the chat loop, `RunLiveSession`, use
  cases, domain entities with logic, router and auth behavior, settings
  validation.
- **Port contract suites**: one per port, run against every adapter, including
  negative cases (unknown device → `DomainError`). In-memory passes now; real
  adapters must pass the same suite (integration marker).
- **Test doubles**: `ScriptedChatModel`, `ScriptedLiveSession` under
  `tests/fakes/`. Time-dependent tests use the injected clock and never sleep.
- **Coverage ≥ 80%**, enforced in `pyproject.toml`. Only `adapters/openai/**`
  (and pure-ABC `ports/`) are omitted.
- **Integration tests** against a real vendor are marked `integration` + `slow`
  and are **excluded from the default `pytest`** run.
- **Layout mirrors source:** `tests/unit/<layer>/test_<module>.py`.
- Never mock the system under test. Never mock Postgres. Never let a unit test
  reach OpenAI, Tuya or Google.

## Tooling

| Tool | Role | Command |
|---|---|---|
| `ruff` | lint + format | `ruff check . && ruff format .` |
| `pyright` | type check (strict) | `pyright` |
| `pytest` | tests + coverage | `pytest` |
| `pre-commit` | gate before commit | `pre-commit run --all-files` |

Python 3.12+. Pyright config lives in `pyproject.toml` — do not add a
`pyrightconfig.json`, it silently overrides that file and drops strict mode.

## Conventions

- **Naming:** modules `snake_case`, classes `PascalCase`, functions
  `snake_case`, constants `UPPER_SNAKE`.
- **Imports:** absolute from `app.*`. No relative imports across layers.
- **Line length:** 100.
- **Docstrings:** public ports and use cases only. One-line summary; args and
  returns only when non-obvious.
- **No comments explaining *what*** — names do that. Comments only for
  non-obvious *why*, and for `ponytail:` markers on deliberate simplifications.
- **Suffixes:** Pydantic models end in `Schema`, ports end in `Port`, domain
  entities have no suffix. Use cases are verb phrases (`ProcessChatMessage`).
- Code, comments, docs and commits in English. The assistant's speech and agent
  prompts are in Brazilian Portuguese — a content decision, not a code one.

## Commits

Conventional Commits, enforced by pre-commit: `feat`, `fix`, `refactor`,
`test`, `chore`, `docs`, `perf`, `style`, `ci`, `build`, `revert`. Scope
optional — `feat(live): add realtime session adapter`.

## Current state

Spec 1 is done: chat and live voice run end to end on in-memory home, calendar and
expense adapters. What is left is replacing those adapters with real ones.

| Piece | Status |
|---|---|
| Hexagonal skeleton, structlog, in-memory store | done |
| Domain types, ports, `Tool`, `ToolRunner`, confirmation | done |
| OpenAI `ChatModelPort` + chat loop, `POST /messages` | done |
| Auth (bearer), input limits, boot validation, JSON logs | done |
| In-memory Home / Calendar / Expenses adapters | done |
| `WS /live` + OpenAI Realtime adapter | done |
| TLS, LAN exposure, locked dependencies, non-root image | done |
| Tuya, Google Calendar / Sheets adapters | not started (later spec) |
| Gemini Live adapter, A/B against OpenAI | not started (later spec) |
| Postgres + pgvector + Alembic | not started (later spec) |
| Scheduler + `/ws/notifications` | not started (later spec) |

## Before you finish

Run `ruff check`, `pyright`, `pytest`. Three green = ship. Read
`docs/ARCHITECTURE.md` for the *why* (some ADRs are superseded by the spec) and
`docs/CONVENTIONS.md` for the *how*.

## Anti-patterns (reject on sight)

- Anything from **Explicitly out of scope** above.
- Pydantic in `domain/` — boundary leak.
- OpenAI, Tuya or Google SDK types outside their adapter package.
- Agno, a Team, or per-segment sub-agents — superseded by the single agent.
- A use case importing an adapter directly — go through the port.
- Intent classification written by hand, or a `match` on segment names.
- A fallback tool set when a named segment is unknown — fail loudly (`404`).
- Audio decoded, transcribed or resampled below the API layer / adapter.
- A tool that accepts an arbitrary device ID or spreadsheet ID from the model.
- Confirmation enforced only in the prompt, or a pending action that survives
  more than the next utterance.
- Treating a cache of Google data as the source of truth.
- Logging tool arguments, transcripts or content; `print()` or naked `logging`.
- Exposing the service on a network without the token and TLS.
- A test that mocks the system under test, or reaches a real vendor by default.
- Function > 50 lines, or a class with > 5 public methods, without
  justification.
