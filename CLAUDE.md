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
expenses, proactive reminders and alarms.

**Explicitly out of scope — reject on sight:**

- Any TUI or desktop client. The only GUI in scope is the single static control panel in `web/` (below).
- Computer vision, cameras, screen capture, OCR, image pipelines.
- Chat-channel adapters (WhatsApp, Telegram, Email).
- Multi-tenancy, user accounts, roles. One owner.

Voice is not a GUI. Audio endpoints belong here.

**Web control panel (`web/`)** — one static page (HTML/CSS/vanilla JS, no build step,
no framework) served by FastAPI. It is a *client* of `/api/v1`: bearer token typed by the
owner, kept in `sessionStorage`, never in a URL. It shows the 0/1 sphere agent and gives direct
control of lights, climate, music, agenda and expenses through the same `ToolRunner` +
confirmation rules as chat — no logic or credentials in the browser. Contract:
`docs/web-api-contract.md`.

## Tools and segments

There is **one agent with all tools**. No sub-agents, no Team, no routing hop.
The one exception, by the owner's rule, is **Lynus** (Spec 5, below): a separate agent on
Google's coding model that drives Claude Code on its own. Byte only hands it a project and a task.

A **segment** is a named group of tools, used only as an optional per-request
filter (`segment` omitted or `auto` = all tools; unknown segment = `404`).

| Segment | Tools talk to | Via port |
|---|---|---|
| `home` | Lights (Tuya, local network) and the air conditioner (LG ThinQ) | `LightPort`, `ClimatePort` |
| `music` | Spotify playback on a Spotify Connect device | `MusicPort` |
| `agenda` | Events (Google Calendar), reminders and alarms | `CalendarPort`, `ReminderStorePort` |
| `finance` | Monthly expenses, bills (Google Sheets) | `ExpensesPort` |
| `weather` | Current weather and forecast for the home city or any city (Open-Meteo) | `WeatherPort` |
| `projects` | Owner's programming projects: RAG over their `CLAUDE.md`; open/close `claude` in the panel terminal; hand a task to Lynus (`start_lynus`, `lynus_status`) | `KnowledgeStorePort`, `EmbedderPort`, `DocumentSourcePort`, `ProjectTerminalPort` |

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
| Model provider | OpenAI (chat + Realtime) or Gemini (chat + Live) behind `ChatModelPort` / `LiveSessionPort` | Gemini adds its built-in Google Search (web search runs on Google's side, not a `Tool`, no credentials). OpenAI has no web search yet. |
| Tuya | `tinytuya` over the local network (device id, address, local key) | Lights are physical. Keys come from the environment. |
| LG ThinQ | ThinQ Connect personal access token | The air conditioner. |
| Spotify | Web API with a refresh token (Premium) | Playback on a Connect device; `scripts/spotify_login.py` gets the token. |
| Google Calendar | OAuth 2.0 refresh token, REST over aiohttp | Google is the system of record, not our DB. `scripts/google_login.py` gets the token. |
| Piper | Local TTS (`piper-tts`, CPU, pt-BR voice in `models/`) behind `SpeechPort` | Speaks reminders. No network, no tokens. |
| Google Sheets | OAuth 2.0 | The expense spreadsheet you already use. |
| Open-Meteo | HTTPS over aiohttp, no key | Weather and city geocoding. Home city from `BYTE_WEATHER_HOME`. |

**Every integration is a driven adapter behind a port.** A vendor SDK type never
crosses the port boundary. Vendor errors are wrapped in a `DomainError`
subclass before they leave the adapter. The OpenAI SDK appears in
`adapters/openai/` and nowhere else; Tuya and Google SDKs in their own adapter
packages and nowhere else.

Google holds the truth for calendar and expenses so they stay editable from a
phone. A cache is never treated as the source of truth.

## Proactive reminders and alarms

Spec 3 (`docs/superpowers/specs/2026-10-21-calendar-reminders-design.md`). Byte speaks
first, and **firing never calls the model**: the model only creates a reminder through
`create_reminder`. `ReminderHub` (a 5 s loop in the lifespan) pushes due reminders, with
Piper speech, over `WS /ws/notifications`; a reminder leaves `ReminderStorePort` (a JSON
file) only when the device acks. Nothing connected → it waits and is spoken on reconnect,
never silently dropped. Calendar events get a warning 10 minutes before, recomputed from
Google every 5 min and expired at the event's start. An alarm rings on the device until the
local wake word stops it — no live session, no tokens. The model gets the current time as
one `Agora:` line in its prompt. WebSocket, not MQTT, until a real limit is hit.

## Lynus (Spec 5)

`docs/superpowers/specs/2026-10-24-claude-code-remote-design.md`. In the panel the owner
switches the chat to Lynus; Byte asks for the project and a short task and calls `start_lynus`;
Lynus (`application/lynus.py`, `BYTE_LYNUS_MODEL`) opens a fresh `claude` with
`--permission-mode default`, deepens the task with the owner, then works alone: it types
prompts into the PTY, reads each turn's last message (`Stop` hook), reads project files to
check specs and plans, and calls `finish`. Claude Code's `PermissionRequest`/`Stop` hooks reach
`POST /claude/hooks` (`ClaudeBridge`) with a per-session token that is not the owner's. **While
Lynus works, every permission request is allowed in code — owner's rule, not a bug.** Bounds:
explicit start for one project, stop button, turn budget and turn timeout, Byte's secrets kept
out of the child's environment.

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
  must not learn that it can act first and apologise later. (This rule governs Byte's tools.
  Inside a Lynus task, Claude Code's own permission requests are approved by Lynus, by the
  owner's rule — see **Lynus**.) Today only `delete_event`
  and `add_expense` ask; switching lights or the air conditioner on or off runs at once
  (owner's call). With a single configured lamp, `set_light` targets it whatever name the
  model says. The model only plays a `uri` that a search or the playlists returned.
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

**Project knowledge (Spec 4)** lives in Postgres 16 + pgvector (`BYTE_DATABASE_URL`,
SQLAlchemy asyncio + Alembic, `migrations/`, run at boot), or in memory when unset. Embeddings
are local (fastembed, CPU). Spec: `docs/superpowers/specs/2026-10-22-project-knowledge-terminal-design.md`.
`open_project`/`close_project` are `panel_only`: offered and run only when the request or live
start carries `client: "panel"` — routing, not security.

Today the conversation store is in memory: last 20 messages per request context,
max 50 conversations (LRU), lost on restart. `ConversationStorePort.append` is
atomic. Moving it to the same Postgres is a later spec, behind the same port.

Postgres will also store OAuth tokens and pending reminders. It will **not** store calendar events or expenses — Google owns those.

`InMemoryRepository` style adapters stay: unit tests use them. Integration tests
against Postgres use a real Postgres via testcontainers, never a mock.

## API

Prefix `/api/v1`. FastAPI. Everything async.

| Route | Purpose |
|---|---|
| `GET /health` | Liveness. Used by the Docker healthcheck. |
| `POST /messages` | Text in, text out. `segment` optional. May return `pending_confirmation.summary`. |
| `WS /live` | Spoken conversation. One session at a time; a new connection replaces the old (close code 4000). |
| `WS /ws/terminal` | Panel only: the open project's `claude` PTY (state JSON + binary I/O). One panel; a new one replaces the old (4000). 1008 where no terminal exists. |
| `WS /ws/panel` | Panel only: server pushes `{"type":"weather"}` when the shown city changes. One panel; a new one replaces the old (4000). |
| `GET /lynus`, `POST /lynus/messages`, `POST /lynus/stop` | Panel: Lynus's state and conversation; `{"type":"lynus"}` pushed on `/ws/panel`. 503 without terminal or Gemini key. |
| `POST /claude/hooks` | Only the `claude` process Byte runs: Claude Code hooks, per-session bridge token (owner token refused). |
| `WS /ws/notifications` | Proactive pushes: `{"type":"reminder","id","kind"}` + one binary PCM frame; the device replies `{"type":"ack","id"}`. One listener; a new one replaces the old (4000). |

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
| Voice client (`voice/`): wake word "Ei Byte" (custom model in `models/`), `/live` over the laptop mic and speaker | in progress (Spec 2: code done, hardware checks pending) |
| Tuya, ThinQ, Spotify adapters | done |
| Google Calendar adapter, reminders/alarms, Piper TTS, `/ws/notifications` (Spec 3) | done (real Google and Docker image not yet checked by hand) |
| Google Sheets adapter | not started (later spec) |
| Gemini Live adapter, A/B against OpenAI | not started (later spec) |
| Project knowledge (pgvector + local embeddings) and panel project terminal (Spec 4) | done (opening by voice in the panel not checked by hand) |
| Weather: tools, panel section, `/ws/panel` push (Spec 6) | done |
| Postgres for conversations, OAuth tokens, reminders | not started (later spec) |
| Lynus driving Claude Code on its own (Spec 5) | done (hooks spiked on `claude` 2.1.310) |

## Before you finish

Run `ruff check`, `pyright`, `pytest`. Three green = ship. Read
`docs/ARCHITECTURE.md` for the *why* (some ADRs are superseded by the spec) and
`docs/CONVENTIONS.md` for the *how*.

## Anti-patterns (reject on sight)

- Anything from **Explicitly out of scope** above.
- Pydantic in `domain/` — boundary leak.
- OpenAI, Tuya or Google SDK types outside their adapter package.
- Agno, a Team, or per-segment sub-agents — superseded by the single agent (Lynus is the
  owner's one sanctioned second agent, for Claude Code only).
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
