# Byte — Personal Voice Assistant Backend

> Auto-loaded project guidelines. Read before any code change.

## What this is

A JARVIS-style personal assistant, running as a **headless backend** in Docker
on a home server. It controls smart-home devices, manages a calendar, and
tracks monthly expenses — spoken to, not clicked.

The intended client is a **custom ESP32-S3 device**: a personal Alexa that does
wake-word detection locally and streams audio to this server. Any other
application can consume the same HTTP API.

Single user, single household. Not a product, not multi-tenant.

**In scope:** audio in / audio out, agent reasoning, device control, calendar,
expenses, proactive reminders.

**Explicitly out of scope — reject on sight:**

- Any GUI, TUI, web page, or desktop client. This repository ships no frontend.
- Computer vision, cameras, screen capture, OCR, image pipelines.
- Chat-channel adapters (WhatsApp, Telegram, Email).
- Multi-tenancy, user accounts, roles. One owner.

Voice is not a GUI. Audio endpoints belong here; pixels do not.

## Segments

A segment is a bounded area one agent owns. One segment = one `AgentPort`
instance = one entry in `Registry[AgentPort]`.

| Segment | Owns | Talks to |
|---|---|---|
| `home` | Lights, plugs, sensors, scenes | Tuya Cloud API |
| `agenda` | Events, appointments, reminders | Google Calendar |
| `finance` | Monthly expenses, bills, spend totals | Google Sheets |

Agents do not call each other. Cross-segment work ("lembra do boleto e apaga a
luz") is the router's job, not an agent's.

**Adding a segment:**

1. Write the adapter under `app/adapters/agent/`, implementing `AgentPort`.
2. Add the name to `BYTE_SEGMENTS`.
3. Register it in `api/deps.py::get_agents()`.
4. Add it as a member of the routing Team.
5. Test the adapter's behavior, not the framework's.

## Routing

Two ways in, deliberately:

- **`segment` given** → the registry resolves that agent directly. One LLM hop.
  This is how an application that already knows what it wants calls Byte.
  Unknown segment → `404`. Never a fallback agent.
- **`segment` omitted** → the **Agno Team in route mode** classifies the
  utterance and dispatches to a member agent. This is the voice path: the
  ESP32 hears a sentence, not a segment.

**The Team is itself an `AgentPort`.** `AgnoTeamAgent` wraps the Team and is
registered under `auto`. Everything above the adapter sees one port, one
`run()`. That is the whole containment strategy — see ADR-010 for the leak this
accepts and the exit if it bites.

Never put intent classification in the router module. Never write a `match` on
segment names anywhere.

## Voice pipeline

Speech-to-text and text-to-speech run **on the server**. The ESP32-S3 does
wake-word detection locally and nothing else.

```
ESP32 wake word → stream audio → POST /voice
   → SpeechToTextPort.transcribe(audio) -> str
   → AgentPort.run(text, conversation) -> str          # the Team, routing
   → TextToSpeechPort.synthesize(text) -> bytes
   → audio back to ESP32
```

Rules:

- `SpeechToTextPort` and `TextToSpeechPort` are ports like any other. The
  vendor (Whisper, local, hosted) lives in an adapter and is swappable.
- Audio bytes never reach `domain/` or `application/`. Transcription happens in
  the API layer; the use case receives text.
- `POST /messages` (text) and `POST /voice` (audio) run the same use case. Voice
  is a transport, not a second brain.

## Integrations

| Target | Via | Notes |
|---|---|---|
| Tuya | Tuya Cloud API | Devices are physical. See **Safety** below. |
| Google Calendar | OAuth 2.0 | Google is the system of record, not our DB. |
| Google Sheets | OAuth 2.0 | The expense spreadsheet you already use. |

Google holds the truth for calendar and expenses so they stay editable from a
phone without Byte building an app. Our Postgres holds conversation history and
OAuth tokens, and caches reads when the API is slow — a cache is never treated
as the source of truth.

Every integration is a driven adapter behind a port. A vendor SDK type never
crosses the port boundary. Vendor errors are wrapped in a `DomainError`
subclass before they leave the adapter.

## Proactive reminders

Byte speaks first for bills and appointments. A scheduler wakes up, finds what
is due, and pushes it to the connected device over a **WebSocket** at
`/ws/notifications`.

- WebSocket, not MQTT: FastAPI serves it natively, so there is no broker
  container to run. If the device starts sleeping deeply or several clients
  appear, MQTT becomes the right answer — mark the swap with a `ponytail:`
  comment when the limit is actually hit, not before.
- The scheduler is a driven adapter behind a port. Deciding *what* is due is a
  use case in `application/`, and it is unit-testable without a clock.
- A push is fire-and-forget. If nothing is connected, the reminder is persisted
  and delivered on reconnect. Never silently dropped.

## Safety and security

This service controls physical devices in a home and reads personal financial
data. Treat these as hard requirements, not polish:

- **The API has no authentication yet.** Until it does, `docker-compose.yml`
  binds to `127.0.0.1` only. Do not remove that bind, expose a port, or add a
  tunnel in any change that does not also add authentication.
- **Never commit credentials.** Tuya access keys and Google OAuth tokens come
  from the environment or from encrypted storage. `.env` is gitignored;
  `.env.example` holds names with empty values only.
- **Never log secrets or raw user speech.** `LoggerPort` calls take structured
  fields; redact content before it reaches them.
- **Destructive or physical actions confirm first.** Unlocking a door, turning
  off something that is running, or deleting a calendar event asks for
  confirmation before it executes. An agent must not learn that it can act
  first and apologise later.
- **Bound the blast radius of tools.** A Tuya tool addresses a known device
  list, not arbitrary device IDs from the model. A Sheets tool writes to the
  configured spreadsheet, not to one the model names.

## Architecture

**Hexagonal (Ports & Adapters).** The agent framework, the models, the smart
home vendor, and the datastore are all swappable behind ports.

```
app/
├── domain/          # Pure Python. Zero external deps. dataclasses only.
├── ports/           # ABCs. Contracts.
├── application/     # Use cases + Registry. Imports domain + ports only.
├── adapters/        # Concrete implementations (driven side).
│   ├── agent/       # AgentPort impls — one per segment, plus the Team
│   ├── logging/
│   └── repository/
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

Agno appears in `adapters/agent/` and nowhere else. Tuya and Google SDKs appear
in their own adapter packages and nowhere else.

## Persistence

**PostgreSQL 16 + pgvector**, behind `RepositoryPort`. SQLAlchemy[asyncio] +
asyncpg, migrations with Alembic. Schema `public` is ours; Agno's session
tables live in schema `agno` and are never read as source of truth.

It stores conversation history, OAuth tokens, pending reminders, and long-term
memory embeddings. It does **not** store calendar events or expenses — Google
owns those.

`InMemoryRepository` stays: it is what unit tests use. Integration tests run
against a real Postgres via testcontainers, never a mock.

## API

Prefix `/api/v1`. FastAPI. Everything async.

| Route | Purpose |
|---|---|
| `GET /health` | Liveness. Used by the Docker healthcheck. |
| `POST /messages` | Text in, text out. `segment` optional — omitted routes via the Team. |
| `POST /voice` | Audio in, audio out. Not implemented yet. |
| `WS /ws/notifications` | Proactive pushes to the device. Not implemented yet. |

Rules:

- Pydantic models live in `api/schemas.py` and never leak inward.
- Domain errors map to HTTP status in the router. Adapters never raise HTTP.
- Versioned in the path. Breaking a response shape means `/api/v2`.

## Docker

```
docker compose up --build
```

- Published on `127.0.0.1` only — see **Safety and security**.
- Config from env (`BYTE_` prefix). Nothing secret baked into the image.
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
   external errors before crossing the port boundary.
8. **No singletons.** `lru_cache` in `api/deps.py` for DI.
9. **No new abstraction without a second concrete implementation in sight.**

## Testing

- **TDD required for:** Registry, port contracts, use cases, domain entities
  with logic, router behavior, reminder-due logic.
- **TDD optional for:** adapters — cover those with integration tests against
  the real thing.
- **Coverage ≥ 80%**, enforced in `pyproject.toml`. `adapters/` and `ports/`
  are excluded (integration-tested / pure ABCs).
- **Layout mirrors source:** `tests/unit/<layer>/test_<module>.py`.
- **Markers:** `unit` (default), `integration`, `slow`.
- Never mock the system under test. Never mock Postgres. Never let a unit test
  reach Tuya, Google, or an LLM.

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
  non-obvious *why*.
- **Suffixes:** Pydantic models end in `Schema`, ports end in `Port`, domain
  entities have no suffix. Use cases are verb phrases
  (`ProcessIncomingMessage`, not `MessageProcessor`).
- Code, comments, docs and commits in English. Agent prompts and the assistant's
  speech are in Brazilian Portuguese — that is a content decision, not a code
  one.

## Commits

Conventional Commits, enforced by pre-commit: `feat`, `fix`, `refactor`,
`test`, `chore`, `docs`, `perf`, `style`, `ci`, `build`, `revert`. Scope
optional — `feat(agent): add home segment adapter`.

## Current state

| Piece | Status |
|---|---|
| Hexagonal skeleton | done |
| `Registry[AgentPort]` + direct segment routing | done |
| Segments `home` / `agenda` / `finance` declared | done |
| `POST /messages`, `GET /health` | done |
| Dockerfile + compose (API only) | done |
| Agno agents per segment (no tools yet) | done |
| Model tier per role + cross-provider fallback | done |
| Agno adapter + Team routing under `auto` | done |
| Postgres + pgvector + Alembic | not started |
| Tuya adapter | not started |
| Google Calendar / Sheets adapters | not started |
| Voice (`/voice`, STT, TTS) | not started |
| Scheduler + `/ws/notifications` | not started |
| **API authentication** | **not started — blocks exposure** |

## Before you finish

Run `ruff check`, `pyright`, `pytest`. Three green = ship. Read
`docs/ARCHITECTURE.md` for the *why*, `docs/CONVENTIONS.md` for the *how*.

## Anti-patterns (reject on sight)

- Anything from **Explicitly out of scope** above.
- Pydantic in `domain/` — boundary leak.
- Agno, Tuya, or Google SDK types outside their adapter package.
- A use case importing an adapter directly — go through the port.
- Intent classification written by hand in the router.
- A fallback agent when a named segment is unknown — fail loudly.
- Audio bytes below the API layer.
- A tool that accepts an arbitrary device ID or spreadsheet ID from the model.
- Treating a cache of Google data as the source of truth.
- `print()` or naked `logging` — use `LoggerPort`.
- A test that mocks the system under test, or reaches a real vendor.
- Function > 50 lines, or a class with > 5 public methods, without
  justification.
