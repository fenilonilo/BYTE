# Byte: Foundation and Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Agno multi-agent stack with one tool-using agent exposed as an authenticated, validated chat API (`POST /api/v1/messages`) that drives your lights, air conditioner and music plus a calendar and expenses, with confirmation enforced in code, OpenAI behind a port, and a service that refuses to boot on a bad config.

**Architecture:** Hexagonal. A `Tool` is application code that talks to the world only through ports (`LightPort`, `ClimatePort`, `MusicPort`, `CalendarPort`, `ExpensesPort`); a `ToolRunner` enforces the allowlist, timeouts, cancellation shielding and the confirmation gate; `ProcessChatMessage` runs the model/tool loop against `ChatModelPort` (OpenAI today). The same `Registry[Tool]`, `ToolRunner` and confirmation rules will serve the live mode in Plan 2. The adapters you already wrote (Tuya, ThinQ, Spotify) are used as they are.

**Tech Stack:** Python 3.12+, FastAPI, pydantic-settings, structlog, `openai` SDK >= 2.35 (Chat Completions), `tinytuya`, `thinqconnect`, `aiohttp` (your adapters), pytest + pytest-asyncio, ruff, pyright (strict).

**Spec:** `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md` (this is **Plan 1 of 2**; Plan 2, `2026-10-05-live-mode-and-hardening.md`, builds the live mode and the hardening on top of it). The spec predates your device adapters: Task 9 adds an amendment saying the home tools use your ports.

## Global Constraints

Every task's requirements include these (values copied from the spec and `CLAUDE.md`):

- Python `>=3.12`, line length 100, `ruff check` and `ruff format --check` clean, `pyright` strict at **0 errors** and **no new warnings**. Eight warnings remain from the Tuya and Spotify adapters (`tuya_light.py`, `spotify_music.py`: third-party libraries without types); they are not part of this plan and are never "fixed" here.
- Hexagonal rule: `domain/` imports stdlib only; `ports/` import `domain/`; `application/` imports `domain/` and `ports/`; `adapters/` import everything except `api/`. Ports are `ABC` + `@abstractmethod`. One use case per file under `application/use_cases/`. Absolute imports from `app.*`. No `print()` in `app/` (use `LoggerPort`). Errors inherit `DomainError`.
- Domain entities are `@dataclass(frozen=True, slots=True)`; Pydantic only in `api/` and `config.py`.
- Every outside resource (model provider, lights, air conditioner, music, calendar, expenses, storage) is an adapter behind a port; no SDK type crosses a port. The OpenAI SDK appears only in `adapters/openai/`.
- **The owner's device work is the base and is not redesigned:** `LightPort`, `ClimatePort`, `MusicPort`, their domain types (`LightChange`, `ClimateChange`, `PlaybackChange`...), their adapters and in-memory fakes, and the `thinq_*` / `tuya_lights` / `spotify_*` settings stay as they are. The agent's home and music tools are built **on** those ports.
- Segments are `home` (lights, air conditioner), `music`, `agenda`, `finance`. Confirmation: `delete_event` and `add_expense` always; `set_climate` only when it switches the unit on or off (`Tool.needs_confirmation(args)`); lights and music never. A lamp is not switched on or off twice within 5 s; the model only plays or queues a `uri` returned by `search_music` or `list_playlists`.
- Chat limits: the model sees the **last 20 messages**; at most **6 tool steps** per request; **10 s** per tool; tool output truncated to **2,000** characters; **30 s** per chat request (exceeding it raises `AgentError` -> 502).
- Confirmation: one pending action per conversation, **60 s** expiry, valid for the **very next** user utterance only; executed only through the argument-free `confirm_action()`; `is_affirmative` matches whole words, accepts 5 words or fewer, deny list wins.
- API: prefix `/api/v1`; every route except `GET /health` needs `Authorization: Bearer <token>`; `content` is 1-4,000 characters; `conversation_id` matches `^[A-Za-z0-9_-]{1,64}$`; an unknown `segment` is **404**, never a fallback.
- Config: every setting uses the `BYTE_` prefix **including the keys**; blank environment variables count as unset; `BYTE_API_TOKEN` is at least **32** characters; the app refuses to boot on a bad config (`ConfigError` names the fields, never the values).
- A device group with no real adapter configured runs against the in-memory one, and the boot log (`adapters.selected`) says so.
- Logs never contain tool arguments, transcripts or message content: only ids, tool names, durations, error types.
- Coverage floor **80%**; tests marked `integration` are excluded from the default `pytest` run.
- Docker binds to `127.0.0.1` by default (LAN exposure arrives with TLS in Plan 2).

## Review Focus

Inputs and conditions the spec implies but a happy-path test would not catch. Each line names the test that pins it.

1. **Garbage payloads** (empty or whitespace-only `content`, 4,001 characters, `../etc/passwd` as `conversation_id`) -> `422` and the model is never called. `test_invalid_payloads_are_422`.
2. **The model sends broken tool arguments** (not JSON, a list, a string, or `null` for an optional field) -> the model receives `erro: ...` text and the tool does not run; `null` simply means "leave it alone". `test_bad_arguments_become_an_error_text`, `test_optional_argument_helpers_treat_missing_and_null_as_absent`.
3. **A tool outlives its timeout, or the request is cancelled mid-tool** -> the model hears `estado desconhecido` (never "success"), and the physical action still finishes. `test_timeout_reports_unknown_state_and_the_tool_still_finishes`, `test_cancelling_the_caller_does_not_abort_the_tool`.
4. **"Apaga o dentista? / que horas são? / sim"** -> an unrelated message between the request and the "sim" cancels the pending action; the appointment stays. `test_an_unrelated_message_in_between_cancels_the_pending_action`.
5. **The model invents a device name** (a light called `cofre`) -> error text from your `UnknownLightDeviceError`, never a `500`. `test_unknown_device_from_the_model_becomes_error_text_not_a_crash`.

## How to run things

- `python` below means the interpreter that has the project's dependencies installed (in this repo's shell that is `C:/Users/fenil/anaconda3/python.exe`; elsewhere, the activated virtualenv). `ruff`, `pyright` and `pytest` are the same tools run as `python -m ruff`, `python -m pyright`, `python -m pytest`.
- One test file: `python -m pytest <path> -q --no-cov`. Full gate: `ruff check . && ruff format --check . && pyright && pytest`.
- Every task follows the same rhythm: write the tests, watch them fail, write the code, watch them pass, run the gate, commit. The code blocks are the verified end state of each file: copy them as they are.
- Commits use Conventional Commits (the pre-commit hook enforces it). Add the repository's usual `Co-Authored-By` trailer when an agent writes the commit.
- **Never stage the whole tree** (`git add -A` or `git add .` with no paths). Your working tree has notes that are not part of this work (`AR_Controle.md`, `Lampada_Controle.md`, `Spotfy_Controle.md`); every commit step stages explicit paths only (Task 8 uses `git add -A` restricted to a path list so the deletions are staged too).

## File structure

```
app/
  domain/        tools.py  model.py  world.py  affirmation.py  exceptions.py  entities.py
                 light.py  climate.py  music.py                          (yours, unchanged)
  ports/         chat_model.py  calendar.py  expenses.py  conversation_store.py  logger.py
                 light.py  climate.py  music.py                          (yours, unchanged)
  application/   registry.py  tool.py  tool_runner.py  pending_actions.py  prompts.py
                 tools/{args,lights,climate,music,agenda,finance,catalog}.py
                 use_cases/process_chat_message.py
  adapters/      memory/{in_memory_calendar,in_memory_expenses,in_memory_conversation_store}.py
                 memory/{in_memory_light,in_memory_climate,in_memory_music}.py   (yours)
                 tuya/  thinq/  spotify/                                 (yours)
                 openai/chat_model.py   logging/structlog_logger.py
  api/           schemas.py  auth.py  errors.py  deps.py  router.py
  config.py
main.py
tests/
  contracts/     one suite per new port; every future adapter must pass it
  fakes/         clock.py  logger.py  chat_model.py  events.py  world.py   (test doubles, never mocks of the system under test)
  unit/...       mirrors app/
  integration/   test_openai_chat.py  test_tuya_light.py(yours)  (real services, excluded by default)
```

Responsibilities in one line each: **domain** holds the vocabulary (tool specs, model messages, the pt-BR "yes" matcher); **ports** are the seams to the outside world; **application** owns the loop, the confirmation rule and the tools; **adapters** translate to the outside world; **api** is authentication, validation and HTTP shape.

---

### Task 0: Branch, environment, and your device adapters as the starting point

**Files:**
- Commit (as they are): your Tuya light, LG ThinQ climate and Spotify music work
- Modify: `tests/unit/domain/test_music.py` (4 type errors)

**Interfaces:**
- Consumes: your uncommitted device work: `LightPort`, `ClimatePort`, `MusicPort`, their domain types and adapters, `InMemoryLight/Climate/Music`, the Tuya/ThinQ/Spotify settings and `get_light/get_climate/get_music` in `deps.py`.
- Produces: a clean commit of that work on `feat/personal-agent`, and a baseline with `pyright` at 0 errors. This plan builds the agent's home and music tools **on your ports**; it does not change them.

While this plan was being written your working tree gained real device adapters (Tuya, ThinQ, Spotify) and edits to `config.py`, `deps.py`, `exceptions.py`, `pyproject.toml` and `.env.example`. The plan starts from that state, so it must be committed first. Later tasks **merge** into those five files (they keep your fields, errors and extras) instead of overwriting them.

Not included in the commit: `AR_Controle.md`, `Lampada_Controle.md`, `Spotfy_Controle.md` (they look like your own notes). Add them yourself if you want them tracked.

- [ ] **Step 1: Create the working branch**

```bash
git switch -c feat/personal-agent
git status --short
```

Expected: you are on `feat/personal-agent` and `git status` lists your device work (the files named in Step 4) plus the three `*_Controle.md` notes.

- [ ] **Step 2: Install what the new code needs**

```bash
pip install -e ".[api,agents,thinq,tuya,spotify,dev]" "openai>=2.35" httpx
```

(`agents` still exists until Task 8 renames the extra; it brings the Agno packages the old code needs in the meantime.)

- [ ] **Step 3: Record the baseline**

```bash
ruff check . && ruff format --check . && pyright && pytest
```

Expected: `ruff` clean; `pyright` reports **4 errors, all in `tests/unit/domain/test_music.py`**, plus 9 warnings (1 from Agno's `arun`, 8 from `spotify_music.py` and `tuya_light.py`, third-party libraries without types); `pytest` about `104 passed, 3 skipped`. Anything else is not caused by this plan: stop and ask.

- [ ] **Step 4: Commit your device work exactly as it is**

```bash
git add .env.example \
  .gitignore \
  pyproject.toml \
  app/config.py \
  app/api/deps.py \
  app/domain/exceptions.py \
  app/domain/climate.py \
  app/domain/light.py \
  app/domain/music.py \
  app/ports/climate.py \
  app/ports/light.py \
  app/ports/music.py \
  app/adapters/memory \
  app/adapters/spotify \
  app/adapters/thinq \
  app/adapters/tuya \
  scripts/spotify_login.py \
  tests/integration/test_tuya_light.py \
  tests/unit/adapters/test_in_memory_climate.py \
  tests/unit/adapters/test_in_memory_light.py \
  tests/unit/adapters/test_in_memory_music.py \
  tests/unit/adapters/test_spotify_music.py \
  tests/unit/adapters/test_thinq_climate.py \
  tests/unit/adapters/test_tuya_light.py \
  tests/unit/domain/test_climate.py \
  tests/unit/domain/test_light.py \
  tests/unit/domain/test_music.py
git commit -m "feat(devices): add Tuya light, LG ThinQ climate and Spotify music adapters"
```

Compare `git status --short` with the list above first: stage what is yours, nothing else. If you are still editing these files, finish and commit them your own way, then continue at the next step.

- [ ] **Step 5: Edit `tests/unit/domain/test_music.py`**

In `tests/unit/domain/test_music.py`, replace:

```python
from __future__ import annotations

import pytest

from app.domain.exceptions import MusicError
from app.domain.music import PlaybackChange, PlaybackState, Repeat, Skip

STATE = PlaybackState(True, None, 5000, 10000, 50, False, Repeat.OFF, "nest")


def test_empty_change_rejected() -> None:
    with pytest.raises(MusicError):
        PlaybackChange()


@pytest.mark.parametrize("kw", [{"volume": 101}, {"volume": -1}, {"seek_ms": -1}])
def test_bounds_rejected(kw: dict[str, int]) -> None:
    with pytest.raises(MusicError):
        PlaybackChange(**kw)
```

with:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.domain.exceptions import MusicError
from app.domain.music import PlaybackChange, PlaybackState, Repeat, Skip

if TYPE_CHECKING:
    from collections.abc import Callable

STATE = PlaybackState(True, None, 5000, 10000, 50, False, Repeat.OFF, "nest")


def test_empty_change_rejected() -> None:
    with pytest.raises(MusicError):
        PlaybackChange()


@pytest.mark.parametrize(
    "build",
    [
        lambda: PlaybackChange(volume=101),
        lambda: PlaybackChange(volume=-1),
        lambda: PlaybackChange(seek_ms=-1),
    ],
)
def test_bounds_rejected(build: Callable[[], PlaybackChange]) -> None:
    with pytest.raises(MusicError):
        build()
```

- [ ] **Step 6: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/domain/test_music.py -q --no-cov && pyright
```

Expected: the music tests pass and `pyright` now reports **0 errors** (9 warnings remain, none from this plan).

- [ ] **Step 7: Commit**

```bash
git add tests/unit/domain/test_music.py
git commit -m "test(music): type the parametrized bounds test so pyright passes"
```

> The parametrized test passed `**kw: dict[str, int]` into `PlaybackChange(...)`, whose fields have different types, so strict `pyright` rejected it. Each case is now a small factory; the behaviour tested is identical.

### Task 1: Domain types and the pt-BR affirmation matcher

**Files:**
- Create: `app/domain/tools.py`, `app/domain/model.py`, `app/domain/world.py`, `app/domain/affirmation.py`
- Modify: `app/domain/exceptions.py` (append 4 errors; your device errors stay)
- Test: `tests/unit/domain/test_affirmation.py`, `tests/unit/domain/test_exceptions.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces: `ToolSpec(name, description, parameters, segment, requires_confirmation=False)`, `ToolCall(id, name, arguments: str)`, `ToolResult(call_id, output)`, `PendingAction(tool, arguments, summary, key, expires_at, armed=False, armed_text='')`, `ModelMessage(role, content='', tool_calls=(), tool_call_id=None)`, `ModelTurn(text, tool_calls=())`, `CalendarEvent(id, title, start, duration_minutes)`, `Expense(key, amount_cents, category, description, day)`, `is_affirmative(text) -> bool`, and the errors `LiveSessionError`, `ConfigError`, `ToolArgumentError`, `EventNotFoundError` (next to the existing `AgentError`, `LightError`, `ClimateError`, `MusicError`...).

- [ ] **Step 1: Create `tests/unit/domain/test_affirmation.py`**

Create `tests/unit/domain/test_affirmation.py`:

```python
from __future__ import annotations

import pytest

from app.domain.affirmation import is_affirmative


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "sim",
        "Sim!",
        "pode",
        "confirmo",
        "manda ver",
        "sim, pode fazer",
        "claro que sim",
        "OK",
        "pode sim",
    ],
)
def test_affirmative(text: str) -> None:
    assert is_affirmative(text) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "assim",
        "pode deixar",
        "pode esquecer",
        "nem pensar",
        "espera",
        "não",
        "não, cancela",
        "sim, mas depois",
        "que horas são",
        "o jogo começou e eu disse sim para ele agora mesmo",
    ],
)
def test_not_affirmative(text: str) -> None:
    assert is_affirmative(text) is False


@pytest.mark.unit
def test_accents_are_folded() -> None:
    assert is_affirmative("NÃO") is False
    assert is_affirmative("não") is False
```

- [ ] **Step 2: Edit `tests/unit/domain/test_exceptions.py`**

In `tests/unit/domain/test_exceptions.py`, replace:

```python
from app.domain.exceptions import (
    DomainError,
    MessageError,
    RegistryDuplicateError,
    RegistryError,
    RegistryKeyError,
)
```

with:

```python
from app.domain.exceptions import (
    AgentError,
    ConfigError,
    DomainError,
    EventNotFoundError,
    LiveSessionError,
    MessageError,
    RegistryDuplicateError,
    RegistryError,
    RegistryKeyError,
    ToolArgumentError,
)
```

- [ ] **Step 3: Edit `tests/unit/domain/test_exceptions.py`**

In `tests/unit/domain/test_exceptions.py`, replace:

```python
def test_registry_key_error_is_registry_error() -> None:
    assert issubclass(RegistryKeyError, RegistryError)
```

with:

```python
def test_registry_key_error_is_registry_error() -> None:
    assert issubclass(RegistryKeyError, RegistryError)


@pytest.mark.parametrize(
    "error",
    [AgentError, LiveSessionError, ConfigError, ToolArgumentError, EventNotFoundError],
)
def test_other_errors_are_domain_errors(error: type[DomainError]) -> None:
    assert issubclass(error, DomainError)
```

- [ ] **Step 4: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/domain -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 5: Create `app/domain/tools.py`**

Create `app/domain/tools.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, object]
    segment: str
    requires_confirmation: bool = False


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    output: str


@dataclass(frozen=True, slots=True)
class PendingAction:
    tool: str
    arguments: str
    summary: str
    key: str
    expires_at: float
    armed: bool = False
    armed_text: str = ""
```

- [ ] **Step 6: Create `app/domain/model.py`**

Create `app/domain/model.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from app.domain.tools import ToolCall


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """One entry of the transcript the model sees during a single chat request."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ModelTurn:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
```

- [ ] **Step 7: Create `app/domain/world.py`**

Create `app/domain/world.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    id: str
    title: str
    start: datetime
    duration_minutes: int


@dataclass(frozen=True, slots=True)
class Expense:
    key: str
    amount_cents: int
    category: str
    description: str
    day: date
```

- [ ] **Step 8: Create `app/domain/affirmation.py`**

Create `app/domain/affirmation.py`:

```python
from __future__ import annotations

import re
import unicodedata

MAX_WORDS = 5

_YES = frozenset(
    {
        "sim",
        "pode",
        "confirmo",
        "confirma",
        "confirmado",
        "claro",
        "ok",
        "okay",
        "positivo",
        "autorizo",
        "isso",
        "certo",
    }
)

_DENY = frozenset(
    {
        "nao",
        "nem",
        "nunca",
        "negativo",
        "cancela",
        "cancelar",
        "para",
        "pare",
        "parar",
        "espera",
        "espere",
        "deixa",
        "deixe",
        "deixar",
        "esquece",
        "esqueca",
        "esquecer",
        "depois",
    }
)

_PHRASES = ("manda ver",)


def _words(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z]+", folded.lower())


def is_affirmative(text: str) -> bool:
    """True only for a short, unambiguous pt-BR "yes". The deny list always wins."""
    words = _words(text)
    if not words or len(words) > MAX_WORDS:
        return False
    if _DENY.intersection(words):
        return False
    joined = " ".join(words)
    return bool(_YES.intersection(words)) or any(p in joined for p in _PHRASES)
```

- [ ] **Step 9: Edit `app/domain/exceptions.py`**

In `app/domain/exceptions.py`, replace:

```python
class UnknownMusicDeviceError(MusicError):
    """Raised when a playback device name is not available."""
```

with:

```python
class UnknownMusicDeviceError(MusicError):
    """Raised when a playback device name is not available."""


class LiveSessionError(DomainError):
    """Raised when a live (voice) session cannot be opened or breaks."""


class ConfigError(DomainError):
    """Raised at boot when settings are invalid."""


class ToolArgumentError(DomainError):
    """Raised when the model passes missing or mistyped tool arguments."""


class EventNotFoundError(DomainError):
    """Raised when a calendar event id does not exist."""
```

- [ ] **Step 10: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/domain -q --no-cov
```

Expected: PASS.

- [ ] **Step 11: Commit**

```bash
git add app/domain/tools.py \
  app/domain/model.py \
  app/domain/world.py \
  app/domain/affirmation.py \
  app/domain/exceptions.py \
  tests/unit/domain/test_affirmation.py \
  tests/unit/domain/test_exceptions.py
git commit -m "feat(domain): add tool, model and world types and the pt-BR affirmation matcher"
```

### Task 2: Calendar, expenses and conversation-store ports, in-memory adapters, contract suites

**Files:**
- Create: `app/ports/calendar.py`, `app/ports/expenses.py`, `app/ports/conversation_store.py`
- Create: `app/adapters/memory/__init__.py`, `in_memory_calendar.py`, `in_memory_expenses.py`, `in_memory_conversation_store.py`
- Create: `tests/contracts/__init__.py`, `calendar_contract.py`, `expenses_contract.py`, `conversation_store_contract.py`, `tests/fakes/__init__.py`
- Test: `tests/unit/adapters/test_memory_adapters.py`

**Interfaces:**
- Consumes: Task 1 domain types (`CalendarEvent`, `Expense`), the existing `Message`, `EventNotFoundError`.
- Produces: `CalendarPort.list_events(day) / create_event(key, title, start, duration_minutes) / delete_event(event_id)`; `ExpensesPort.add_expense(key, amount_cents, category, description, day) / month_total(year, month)`; `ConversationStorePort.recent(conversation_id, limit) / append(conversation_id, messages)`; `InMemoryCalendar()`, `InMemoryExpenses()`, `InMemoryConversationStore(max_conversations=50)`, named like your `InMemoryLight/Climate/Music` and living in the same package. Each port has a contract suite in `tests/contracts/` that the future Google adapters must also pass. Test helpers `seed_event(calendar)` and `events_on_day(calendar)` (`tests/fakes/events.py`): one `dentista` appointment on 2026-10-06, the thing the tests delete; and `FakeClock` (`tests/fakes/clock.py`, callable, `.advance(seconds)`), the injectable clock the lamp guard and the pending actions are tested with.

Your lights, air conditioner and music already have ports and in-memory adapters, so this task only adds the three ports the agent still needs. The contract suites are abstract classes (`make()` returns the adapter under test); the concrete `Test...` classes in `test_memory_adapters.py` run them against the in-memory adapters.

- [ ] **Step 1: Create `tests/contracts/__init__.py`**

Create the empty file `tests/contracts/__init__.py`.

- [ ] **Step 2: Create `tests/fakes/__init__.py`**

Create the empty file `tests/fakes/__init__.py`.

- [ ] **Step 3: Create `tests/fakes/events.py`**

Create `tests/fakes/events.py`:

```python
from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.world import CalendarEvent
    from app.ports.calendar import CalendarPort

EVENT_DAY = date(2026, 10, 6)


async def seed_event(calendar: CalendarPort) -> CalendarEvent:
    """One appointment on EVENT_DAY. Deleting it is the sensitive action the tests confirm."""
    return await calendar.create_event(
        "seed", "dentista", datetime(2026, 10, 6, 15, 0, tzinfo=UTC), 60
    )


async def events_on_day(calendar: CalendarPort) -> tuple[CalendarEvent, ...]:
    return await calendar.list_events(EVENT_DAY)
```

- [ ] **Step 4: Create `tests/fakes/clock.py`**

Create `tests/fakes/clock.py`:

```python
from __future__ import annotations


class FakeClock:
    """Injectable monotonic clock: tests advance time instead of sleeping."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds
```

- [ ] **Step 5: Create `tests/contracts/calendar_contract.py`**

Create `tests/contracts/calendar_contract.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest

from app.domain.exceptions import EventNotFoundError

if TYPE_CHECKING:
    from app.ports.calendar import CalendarPort

DAY = date(2026, 10, 6)


def at(hour: int, day: date = DAY) -> datetime:
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=UTC)


class CalendarPortContract(ABC):
    """Every CalendarPort adapter must pass this. `make()` returns an empty calendar."""

    @abstractmethod
    def make(self) -> CalendarPort: ...

    async def test_create_then_list_sorted_by_start(self) -> None:
        cal = self.make()
        await cal.create_event("k2", "dentista", at(15), 60)
        await cal.create_event("k1", "reuniao", at(9), 30)
        titles = [e.title for e in await cal.list_events(DAY)]
        assert titles == ["reuniao", "dentista"]

    async def test_list_only_returns_that_day(self) -> None:
        cal = self.make()
        await cal.create_event("k1", "hoje", at(9), 30)
        await cal.create_event("k2", "amanha", at(9, date(2026, 10, 7)), 30)
        assert [e.title for e in await cal.list_events(DAY)] == ["hoje"]

    async def test_create_is_idempotent_per_key(self) -> None:
        cal = self.make()
        first = await cal.create_event("same", "reuniao", at(9), 30)
        second = await cal.create_event("same", "reuniao", at(9), 30)
        assert first.id == second.id
        assert len(await cal.list_events(DAY)) == 1

    async def test_delete_removes_event(self) -> None:
        cal = self.make()
        event = await cal.create_event("k1", "reuniao", at(9), 30)
        await cal.delete_event(event.id)
        assert await cal.list_events(DAY) == ()

    async def test_delete_unknown_raises(self) -> None:
        with pytest.raises(EventNotFoundError):
            await self.make().delete_event("nope")
```

- [ ] **Step 6: Create `tests/contracts/expenses_contract.py`**

Create `tests/contracts/expenses_contract.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.ports.expenses import ExpensesPort


class ExpensesPortContract(ABC):
    """Every ExpensesPort adapter must pass this. `make()` returns an empty ledger."""

    @abstractmethod
    def make(self) -> ExpensesPort: ...

    async def test_empty_month_totals_zero(self) -> None:
        assert await self.make().month_total(2026, 10) == 0

    async def test_total_sums_only_the_requested_month(self) -> None:
        ledger = self.make()
        await ledger.add_expense("a", 5000, "mercado", "feira", date(2026, 10, 2))
        await ledger.add_expense("b", 2500, "transporte", "uber", date(2026, 10, 9))
        await ledger.add_expense("c", 9999, "mercado", "setembro", date(2026, 9, 30))
        assert await ledger.month_total(2026, 10) == 7500

    async def test_same_key_never_writes_twice(self) -> None:
        ledger = self.make()
        await ledger.add_expense("dup", 5000, "mercado", "feira", date(2026, 10, 2))
        await ledger.add_expense("dup", 5000, "mercado", "feira", date(2026, 10, 2))
        assert await ledger.month_total(2026, 10) == 5000
```

- [ ] **Step 7: Create `tests/contracts/conversation_store_contract.py`**

Create `tests/contracts/conversation_store_contract.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.domain.entities import Message

if TYPE_CHECKING:
    from app.ports.conversation_store import ConversationStorePort

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def msg(n: int, role: str = "user") -> Message:
    return Message(id=f"m{n}", role=role, content=f"text {n}", timestamp=NOW)


class ConversationStorePortContract(ABC):
    """Every ConversationStorePort adapter must pass this. `make()` returns an empty store."""

    @abstractmethod
    def make(self) -> ConversationStorePort: ...

    async def test_unknown_conversation_is_empty(self) -> None:
        assert await self.make().recent("nope", 20) == ()

    async def test_append_creates_and_preserves_order(self) -> None:
        store = self.make()
        await store.append("c1", [msg(1), msg(2, "assistant")])
        await store.append("c1", [msg(3)])
        assert [m.id for m in await store.recent("c1", 20)] == ["m1", "m2", "m3"]

    async def test_recent_returns_only_the_last_n(self) -> None:
        store = self.make()
        await store.append("c1", [msg(i) for i in range(1, 6)])
        assert [m.id for m in await store.recent("c1", 2)] == ["m4", "m5"]

    async def test_conversations_are_isolated(self) -> None:
        store = self.make()
        await store.append("a", [msg(1)])
        await store.append("b", [msg(2)])
        assert [m.id for m in await store.recent("a", 20)] == ["m1"]
```

- [ ] **Step 8: Create `tests/unit/adapters/test_memory_adapters.py`**

Create `tests/unit/adapters/test_memory_adapters.py`:

```python
from __future__ import annotations

import pytest

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from tests.contracts.calendar_contract import CalendarPortContract
from tests.contracts.conversation_store_contract import (
    ConversationStorePortContract,
    msg,
)
from tests.contracts.expenses_contract import ExpensesPortContract


@pytest.mark.unit
class TestInMemoryCalendar(CalendarPortContract):
    def make(self) -> InMemoryCalendar:
        return InMemoryCalendar()


@pytest.mark.unit
class TestInMemoryExpenses(ExpensesPortContract):
    def make(self) -> InMemoryExpenses:
        return InMemoryExpenses()


@pytest.mark.unit
class TestInMemoryConversationStore(ConversationStorePortContract):
    def make(self) -> InMemoryConversationStore:
        return InMemoryConversationStore()

    async def test_least_recently_used_conversation_is_evicted(self) -> None:
        store = InMemoryConversationStore(max_conversations=2)
        await store.append("a", [msg(1)])
        await store.append("b", [msg(2)])
        await store.recent("a", 20)  # reading counts as use, so "b" is now the oldest
        await store.append("c", [msg(3)])
        assert await store.recent("b", 20) == ()
        assert [m.id for m in await store.recent("a", 20)] == ["m1"]

    async def test_append_to_evicted_id_creates_it_again(self) -> None:
        store = InMemoryConversationStore(max_conversations=1)
        await store.append("a", [msg(1)])
        await store.append("b", [msg(2)])
        await store.append("a", [msg(3)])
        assert [m.id for m in await store.recent("a", 20)] == ["m3"]
```

- [ ] **Step 9: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/adapters/test_memory_adapters.py -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 10: Create `app/ports/calendar.py`**

Create `app/ports/calendar.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime

    from app.domain.world import CalendarEvent


class CalendarPort(ABC):
    @abstractmethod
    async def list_events(self, day: date) -> tuple[CalendarEvent, ...]: ...

    @abstractmethod
    async def create_event(
        self, key: str, title: str, start: datetime, duration_minutes: int
    ) -> CalendarEvent:
        """Idempotent: the same `key` returns the event created the first time."""

    @abstractmethod
    async def delete_event(self, event_id: str) -> None:
        """Raises EventNotFoundError for an unknown id."""
```

- [ ] **Step 11: Create `app/ports/expenses.py`**

Create `app/ports/expenses.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from app.domain.world import Expense


class ExpensesPort(ABC):
    @abstractmethod
    async def add_expense(
        self, key: str, amount_cents: int, category: str, description: str, day: date
    ) -> Expense:
        """Idempotent: the same `key` never writes a second row."""

    @abstractmethod
    async def month_total(self, year: int, month: int) -> int:
        """Total in cents."""
```

- [ ] **Step 12: Create `app/ports/conversation_store.py`**

Create `app/ports/conversation_store.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities import Message


class ConversationStorePort(ABC):
    @abstractmethod
    async def recent(self, conversation_id: str, limit: int) -> tuple[Message, ...]:
        """Last `limit` messages, oldest first. Empty for an unknown conversation."""

    @abstractmethod
    async def append(self, conversation_id: str, messages: Sequence[Message]) -> None:
        """Atomically add whole messages; creates the conversation if it is unknown."""
```

- [ ] **Step 13: Create `app/adapters/memory/__init__.py`**

Create the empty file `app/adapters/memory/__init__.py`.

- [ ] **Step 14: Create `app/adapters/memory/in_memory_calendar.py`**

Create `app/adapters/memory/in_memory_calendar.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.exceptions import EventNotFoundError
from app.domain.world import CalendarEvent
from app.ports.calendar import CalendarPort

if TYPE_CHECKING:
    from datetime import date, datetime


class InMemoryCalendar(CalendarPort):
    def __init__(self) -> None:
        self._events: dict[str, CalendarEvent] = {}
        self._by_key: dict[str, str] = {}

    async def list_events(self, day: date) -> tuple[CalendarEvent, ...]:
        found = [e for e in self._events.values() if e.start.date() == day]
        return tuple(sorted(found, key=lambda e: e.start))

    async def create_event(
        self, key: str, title: str, start: datetime, duration_minutes: int
    ) -> CalendarEvent:
        existing = self._by_key.get(key)
        if existing is not None:
            return self._events[existing]
        event = CalendarEvent(
            id=f"evt-{len(self._by_key) + 1}",
            title=title,
            start=start,
            duration_minutes=duration_minutes,
        )
        self._events[event.id] = event
        self._by_key[key] = event.id
        return event

    async def delete_event(self, event_id: str) -> None:
        if self._events.pop(event_id, None) is None:
            raise EventNotFoundError(f"Unknown event: {event_id!r}")
```

- [ ] **Step 15: Create `app/adapters/memory/in_memory_expenses.py`**

Create `app/adapters/memory/in_memory_expenses.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.world import Expense
from app.ports.expenses import ExpensesPort

if TYPE_CHECKING:
    from datetime import date


class InMemoryExpenses(ExpensesPort):
    def __init__(self) -> None:
        self._rows: dict[str, Expense] = {}

    async def add_expense(
        self, key: str, amount_cents: int, category: str, description: str, day: date
    ) -> Expense:
        existing = self._rows.get(key)
        if existing is not None:
            return existing
        expense = Expense(
            key=key,
            amount_cents=amount_cents,
            category=category,
            description=description,
            day=day,
        )
        self._rows[key] = expense
        return expense

    async def month_total(self, year: int, month: int) -> int:
        return sum(
            e.amount_cents
            for e in self._rows.values()
            if (e.day.year, e.day.month) == (year, month)
        )
```

- [ ] **Step 16: Create `app/adapters/memory/in_memory_conversation_store.py`**

Create `app/adapters/memory/in_memory_conversation_store.py`:

```python
from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING

from app.ports.conversation_store import ConversationStorePort

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.entities import Message


class InMemoryConversationStore(ConversationStorePort):
    """LRU-bounded. `recent` and `append` both count as use."""

    def __init__(self, max_conversations: int = 50) -> None:
        self._max = max_conversations
        self._data: OrderedDict[str, list[Message]] = OrderedDict()

    async def recent(self, conversation_id: str, limit: int) -> tuple[Message, ...]:
        messages = self._data.get(conversation_id)
        if messages is None:
            return ()
        self._data.move_to_end(conversation_id)
        return tuple(messages[-limit:])

    async def append(self, conversation_id: str, messages: Sequence[Message]) -> None:
        self._data.setdefault(conversation_id, []).extend(messages)
        self._data.move_to_end(conversation_id)
        while len(self._data) > self._max:
            self._data.popitem(last=False)
```

- [ ] **Step 17: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/adapters/test_memory_adapters.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 18: Commit**

```bash
git add app/ports/calendar.py \
  app/ports/expenses.py \
  app/ports/conversation_store.py \
  app/adapters/memory \
  tests/contracts \
  tests/fakes \
  tests/unit/adapters/test_memory_adapters.py
git commit -m "feat(adapters): add calendar, expenses and conversation-store ports with in-memory adapters"
```

### Task 3: `Tool`, argument helpers, the sixteen tools and the catalog

**Files:**
- Create: `app/application/tool.py`, `app/application/tools/__init__.py`, `args.py`, `lights.py`, `climate.py`, `music.py`, `agenda.py`, `finance.py`, `catalog.py`
- Modify: `app/application/registry.py` (add `values()`)
- Test: `tests/unit/application/tools/__init__.py`, `tests/unit/application/tools/test_tools.py`, `tests/unit/application/test_registry.py`

**Interfaces:**
- Consumes: your `LightPort`, `ClimatePort`, `MusicPort` and their domain types (`LightChange`, `ClimateChange`, `PlaybackChange`...); Task 2 ports; Task 1 `ToolSpec` and errors; the existing `Registry[T]`.
- Produces: `Tool` (ABC: class attribute `spec: ToolSpec`, `async execute(args, key) -> str`, `summarize(args) -> str`, `needs_confirmation(args) -> bool`, which defaults to `spec.requires_confirmation`); `object_schema(properties, required=None)`, `str_arg`, `int_arg`, `date_arg`, `datetime_arg`, `opt_str`, `opt_int`, `opt_float`, `opt_bool`, `opt_enum`; `KnownUris`; `build_tool_registry(light, climate, music, calendar, expenses, now=time.monotonic) -> Registry[Tool]` with `list_lights`, `set_light` (5 s toggle guard), `list_climates`, `set_climate` (confirms only when `power` is present) (segment `home`); `music_state`, `list_music_devices`, `search_music`, `list_playlists`, `play_music`, `control_music`, `queue_music` (uris must come from a search or the playlists) (segment `music`); `list_events`, `create_event`, `delete_event` (confirms) (segment `agenda`); `add_expense` (confirms), `month_total` (segment `finance`); `Registry.values()`.

Tools hold ports, never SDKs, and the model never names a raw device id: it passes the **name** you configured (`lampada`, `ar-condicionado`, ...) and your adapters validate it (`UnknownLightDeviceError` and friends). Partial updates map straight onto your `LightChange`, `ClimateChange` and `PlaybackChange`, whose own validation (ranges, "choose one look", empty change) becomes the `erro: ...` text the model reads.

**Which calls ask for confirmation** follows your own notes: `delete_event` and `add_expense` always do (data you cannot undo by voice), and `set_climate` does **only when it switches the unit on or off** (`AR_Controle.md`: a physical action), through `Tool.needs_confirmation(args)`, so "põe o ar em 22" does not ask but "liga o ar" does. Lights and music never ask (`Lampada_Controle.md`, `Spotfy_Controle.md`: nothing destructive).

Three more rules from those notes live in the tools: a lamp is not switched on and off again within 5 s (`Lampada_Controle.md`: rapid toggling can reset it into pairing mode; the guard counts only explicit `power` changes and only after a successful one); the model can only play or queue a `uri` that `search_music` or `list_playlists` returned (`Spotfy_Controle.md`: the uri is never invented); and a unit reporting an error says so in its description. Scenes for the lamp and liking tracks are not exposed (YAGNI, as the notes say).

- [ ] **Step 1: Create `tests/unit/application/tools/__init__.py`**

Create the empty file `tests/unit/application/tools/__init__.py`.

- [ ] **Step 2: Create `tests/unit/application/tools/test_tools.py`**

Create `tests/unit/application/tools/test_tools.py`:

```python
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.tools.args import (
    int_arg,
    opt_bool,
    opt_enum,
    opt_float,
    opt_int,
    opt_str,
    str_arg,
)
from app.application.tools.catalog import build_tool_registry
from app.application.tools.climate import describe_climate
from app.domain.climate import ClimateMode
from app.domain.exceptions import (
    ClimateError,
    LightError,
    MusicError,
    ToolArgumentError,
    UnknownClimateDeviceError,
    UnknownLightDeviceError,
    UnknownMusicDeviceError,
)
from tests.fakes.clock import FakeClock

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.application.registry import Registry
    from app.application.tool import Tool

EXPENSE = {
    "amount_cents": 5000,
    "category": "mercado",
    "description": "feira",
    "date": "2026-10-06",
}
EVENT = {"title": "dentista", "start": "2026-10-06T15:00:00+00:00", "duration_minutes": 60}
WHITE = "modo white, brilho 100%, temperatura de cor 50%"


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def registry(clock: FakeClock) -> Registry[Tool]:
    return build_tool_registry(
        InMemoryLight(("lampada", "quarto")),
        InMemoryClimate(),
        InMemoryMusic(),
        InMemoryCalendar(),
        InMemoryExpenses(),
        now=clock,
    )


async def run(
    registry: Registry[Tool], name: str, args: Mapping[str, object], key: str = "k"
) -> str:
    return await registry.get(name).execute(args, key)


@pytest.mark.unit
def test_catalog_has_sixteen_tools_in_four_segments(registry: Registry[Tool]) -> None:
    specs = [t.spec for t in registry.values()]
    assert {s.name for s in specs} == {
        "list_lights",
        "set_light",
        "list_climates",
        "set_climate",
        "music_state",
        "list_music_devices",
        "search_music",
        "list_playlists",
        "play_music",
        "control_music",
        "queue_music",
        "list_events",
        "create_event",
        "delete_event",
        "add_expense",
        "month_total",
    }
    assert {s.segment for s in specs} == {"home", "music", "agenda", "finance"}


@pytest.mark.unit
def test_irreversible_data_changes_always_ask(registry: Registry[Tool]) -> None:
    flagged = {t.spec.name for t in registry.values() if t.spec.requires_confirmation}
    assert flagged == {"delete_event", "add_expense"}


@pytest.mark.unit
def test_the_air_conditioner_asks_only_when_it_is_switched_on_or_off(
    registry: Registry[Tool],
) -> None:
    climate = registry.get("set_climate")
    assert climate.needs_confirmation({"name": "ar-condicionado", "power": True}) is True
    assert climate.needs_confirmation({"name": "ar-condicionado", "power": False}) is True
    assert (
        climate.needs_confirmation({"name": "ar-condicionado", "target_temperature": 22}) is False
    )
    assert registry.get("set_light").needs_confirmation({"name": "lampada", "power": True}) is False


@pytest.mark.unit
def test_every_schema_is_a_strict_object_and_requires_only_known_fields(
    registry: Registry[Tool],
) -> None:
    for tool in registry.values():
        params = tool.spec.parameters
        assert params["type"] == "object"
        assert params["additionalProperties"] is False
        properties = params["properties"]
        assert isinstance(properties, dict)
        assert set(params["required"]) <= set(properties)  # type: ignore[call-overload]


@pytest.mark.unit
async def test_lights(registry: Registry[Tool]) -> None:
    listed = await run(registry, "list_lights", {})
    assert listed == f"lampada: desligada, {WHITE}; quarto: desligada, {WHITE}"
    assert await run(registry, "set_light", {"name": "lampada", "power": True}) == (
        f"lampada: ligada, {WHITE}"
    )
    dimmed = await run(registry, "set_light", {"name": "lampada", "brightness": 30})
    assert dimmed == "lampada: ligada, modo white, brilho 30%, temperatura de cor 50%"
    colour = await run(registry, "set_light", {"name": "Quarto", "hue": 120, "brightness": 40})
    assert colour == "Quarto: ligada, cor (matiz 120, saturação 100%, brilho 40%)"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"name": "cofre", "power": True}, UnknownLightDeviceError),
        ({"name": "lampada", "brightness": 0}, LightError),
        ({"name": "lampada", "hue": 120, "color_temperature": 10}, LightError),
        ({"name": "lampada"}, LightError),
        ({"name": "lampada", "brightness": "alto"}, ToolArgumentError),
        ({"power": True}, ToolArgumentError),
    ],
)
async def test_bad_light_requests(
    registry: Registry[Tool], args: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        await run(registry, "set_light", args)


@pytest.mark.unit
async def test_a_lamp_is_not_switched_again_within_five_seconds(
    registry: Registry[Tool], clock: FakeClock
) -> None:
    await run(registry, "set_light", {"name": "lampada", "power": True})
    clock.advance(4.9)
    with pytest.raises(LightError, match="aguarde"):
        await run(registry, "set_light", {"name": "lampada", "power": False})
    await run(registry, "set_light", {"name": "lampada", "brightness": 20})  # not a toggle
    await run(registry, "set_light", {"name": "quarto", "power": True})  # another lamp
    clock.advance(0.2)
    assert (await run(registry, "set_light", {"name": "lampada", "power": False})).startswith(
        "lampada: desligada"
    )


@pytest.mark.unit
async def test_a_failed_switch_does_not_start_the_waiting_period(
    registry: Registry[Tool],
) -> None:
    with pytest.raises(UnknownLightDeviceError):
        await run(registry, "set_light", {"name": "cofre", "power": True})
    assert (await run(registry, "set_light", {"name": "lampada", "power": True})).startswith(
        "lampada: ligada"
    )


@pytest.mark.unit
async def test_climate(registry: Registry[Tool]) -> None:
    assert await run(registry, "list_climates", {}) == (
        "ar-condicionado: desligado, modo cool, alvo 24°C, ambiente 25°C, ventilador auto"
    )
    changed = await run(
        registry,
        "set_climate",
        {"name": "ar-condicionado", "power": True, "mode": "dry", "target_temperature": 22.5},
    )
    assert changed == (
        "ar-condicionado: ligado, modo dry, alvo 22.5°C, ambiente 25°C, ventilador auto"
    )
    timer = await run(registry, "set_climate", {"name": "ar-condicionado", "stop_in_minutes": 30})
    assert timer.startswith("ar-condicionado: ligado")
    await run(registry, "set_climate", {"name": "ar-condicionado", "display_light": False})


@pytest.mark.unit
def test_climate_confirmation_summary_comes_from_code(registry: Registry[Tool]) -> None:
    climate = registry.get("set_climate")
    assert climate.summarize({"name": "ar-condicionado", "power": True}) == (
        "Ligar ar-condicionado"
    )
    assert climate.summarize({"name": "ar-condicionado", "power": False}) == (
        "Desligar ar-condicionado"
    )
    both = climate.summarize({"name": "ar-condicionado", "power": True, "target_temperature": 22})
    assert both == "Ligar ar-condicionado e aplicar os outros ajustes pedidos"


@pytest.mark.unit
async def test_a_unit_reporting_an_error_says_so() -> None:
    state = replace(await InMemoryClimate().get_state("ar-condicionado"), has_error=True)
    assert describe_climate("ar-condicionado", state).endswith("ATENÇÃO: o aparelho reporta erro")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("args", "error"),
    [
        ({"name": "ar-condicionado", "target_temperature": 40}, ClimateError),
        ({"name": "ar-condicionado"}, ClimateError),
        ({"name": "sala", "power": True}, UnknownClimateDeviceError),
        ({"name": "ar-condicionado", "mode": "heat"}, ToolArgumentError),
        ({"name": "ar-condicionado", "swing": "sim"}, ToolArgumentError),
    ],
)
async def test_bad_climate_requests(
    registry: Registry[Tool], args: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        await run(registry, "set_climate", args)


@pytest.mark.unit
async def test_music(registry: Registry[Tool]) -> None:
    assert await run(registry, "music_state", {}) == (
        "pausado: nada no aparelho nest mini, volume 50%"
    )
    assert await run(registry, "list_music_devices", {}) == "nest mini"
    assert await run(registry, "search_music", {"query": "queen"}) == (
        "spotify:track:1 | Bohemian Rhapsody Queen"
    )
    assert await run(registry, "search_music", {"query": "xyz"}) == "nada encontrado"
    assert await run(registry, "list_playlists", {}) == "spotify:playlist:1 | Treino"
    await run(registry, "search_music", {"query": "aquarela"})
    playing = await run(registry, "play_music", {"uri": "spotify:track:2"})
    assert playing == "tocando: Aquarela Toquinho no aparelho nest mini, volume 50%"
    louder = await run(registry, "control_music", {"volume": 20, "shuffle": True})
    assert louder == "tocando: Aquarela Toquinho no aparelho nest mini, volume 20%"
    assert await run(registry, "queue_music", {"uri": "spotify:track:2"}) == "adicionada à fila"
    assert (await run(registry, "play_music", {})).startswith("tocando")


@pytest.mark.unit
async def test_the_model_cannot_play_a_uri_it_never_searched_for(
    registry: Registry[Tool],
) -> None:
    for tool in ("play_music", "queue_music"):
        with pytest.raises(MusicError, match="search_music"):
            await run(registry, tool, {"uri": "spotify:track:2"})
    await run(registry, "list_playlists", {})  # playlists count as "returned by the API" too
    assert (await run(registry, "play_music", {"uri": "spotify:playlist:1"})).startswith("tocando")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tool", "args", "error"),
    [
        ("play_music", {"device": "geladeira"}, UnknownMusicDeviceError),
        ("control_music", {}, MusicError),
        ("control_music", {"volume": 101}, MusicError),
        ("control_music", {"repeat": "forever"}, ToolArgumentError),
        ("search_music", {"query": "queen", "kind": "podcast"}, ToolArgumentError),
        ("search_music", {}, ToolArgumentError),
    ],
)
async def test_bad_music_requests(
    registry: Registry[Tool], tool: str, args: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        await run(registry, tool, args)


@pytest.mark.unit
async def test_agenda_tools(registry: Registry[Tool]) -> None:
    first = await run(registry, "create_event", EVENT, "same-key")
    assert await run(registry, "create_event", EVENT, "same-key") == first
    listed = await run(registry, "list_events", {"date": "2026-10-06"})
    assert listed.count("dentista") == 1
    assert "evt-1" in listed
    assert await run(registry, "delete_event", {"event_id": "evt-1"}) == "Evento evt-1 apagado"
    assert await run(registry, "list_events", {"date": "2026-10-06"}) == "nenhum evento"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("list_events", {"date": "amanhã"}),
        ("create_event", {**EVENT, "start": "ontem"}),
        ("create_event", {**EVENT, "duration_minutes": 0}),
        ("add_expense", {**EXPENSE, "amount_cents": -5}),
        ("add_expense", {**EXPENSE, "amount_cents": True}),
        ("month_total", {"year": 2026, "month": 13}),
    ],
)
async def test_bad_arguments_raise_tool_argument_error(
    registry: Registry[Tool], tool: str, args: dict[str, object]
) -> None:
    with pytest.raises(ToolArgumentError):
        await run(registry, tool, args)


@pytest.mark.unit
async def test_finance_tools_and_idempotency(registry: Registry[Tool]) -> None:
    await run(registry, "add_expense", EXPENSE, "pending-1")
    await run(registry, "add_expense", EXPENSE, "pending-1")
    total = await run(registry, "month_total", {"year": 2026, "month": 10})
    assert total == "Total de 10/2026: R$ 50,00"


@pytest.mark.unit
def test_confirmation_summaries_come_from_code(registry: Registry[Tool]) -> None:
    summary = registry.get("add_expense").summarize({**EXPENSE, "amount_cents": 12345})
    assert summary == "Registrar gasto de R$ 123,45 em mercado: feira"
    delete = registry.get("delete_event").summarize({"event_id": "evt-1"})
    assert delete == "Apagar o evento evt-1"


@pytest.mark.unit
def test_required_argument_helpers_reject_wrong_types() -> None:
    with pytest.raises(ToolArgumentError):
        str_arg({"a": 3}, "a")
    with pytest.raises(ToolArgumentError):
        str_arg({"a": "   "}, "a")
    with pytest.raises(ToolArgumentError):
        int_arg({"a": "3"}, "a")
    with pytest.raises(ToolArgumentError):
        int_arg({"a": True}, "a")
    assert int_arg({"a": 3}, "a") == 3


@pytest.mark.unit
def test_optional_argument_helpers_treat_missing_and_null_as_absent() -> None:
    assert opt_str({}, "a") is None
    assert opt_int({"a": None}, "a") is None
    assert opt_bool({"a": None}, "a") is None
    assert opt_float({}, "a") is None
    assert opt_enum({"a": None}, "a", ClimateMode) is None


@pytest.mark.unit
def test_optional_argument_helpers_validate_what_is_present() -> None:
    assert opt_int({"a": 4}, "a") == 4
    assert opt_float({"a": 22}, "a") == 22.0
    assert opt_float({"a": 22.5}, "a") == 22.5
    assert opt_bool({"a": False}, "a") is False
    assert opt_str({"a": " x "}, "a") == "x"
    assert opt_enum({"a": "dry"}, "a", ClimateMode) is ClimateMode.DRY
    for bad in (
        lambda: opt_bool({"a": "sim"}, "a"),
        lambda: opt_float({"a": True}, "a"),
        lambda: opt_float({"a": "22"}, "a"),
        lambda: opt_int({"a": 1.5}, "a"),
    ):
        with pytest.raises(ToolArgumentError):
            bad()
    with pytest.raises(ToolArgumentError, match="cool, dry, fan, auto"):
        opt_enum({"a": "heat"}, "a", ClimateMode)
```

- [ ] **Step 3: Create `tests/unit/application/test_registry.py`**

Create `tests/unit/application/test_registry.py`:

```python
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
    registry.register("Sales", "agent")
    assert registry.get("sales") == "agent"
    assert registry.get("SALES") == "agent"
    assert registry.get("Sales") == "agent"


def test_register_duplicate_case_insensitive() -> None:
    registry: Registry[str] = Registry()
    registry.register("SUPPORT", "agent")
    with pytest.raises(RegistryDuplicateError):
        registry.register("support", "other")


def test_registry_stores_same_instance() -> None:
    class MyService:
        pass

    svc = MyService()
    registry: Registry[MyService] = Registry()
    registry.register("svc", svc)
    assert registry.get("svc") is svc


def test_values_returns_every_registered_instance() -> None:
    registry: Registry[str] = Registry()
    registry.register("a", "one")
    registry.register("B", "two")
    assert registry.values() == ("one", "two")
```

- [ ] **Step 4: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/application -q --no-cov
```

Expected: FAIL — `test_tools.py` cannot import `app.application.tools.catalog`, and `test_values_returns_every_registered_instance` fails.

- [ ] **Step 5: Create `app/application/registry.py`**

Create `app/application/registry.py`:

```python
from app.domain.exceptions import RegistryDuplicateError, RegistryKeyError


class Registry[T]:
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

    def values(self) -> tuple[T, ...]:
        return tuple(self._store.values())
```

- [ ] **Step 6: Create `app/application/tool.py`**

Create `app/application/tool.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.domain.tools import ToolSpec


class Tool(ABC):
    """Application code the model can call. It talks to the world only through ports."""

    spec: ToolSpec

    @abstractmethod
    async def execute(self, args: Mapping[str, object], key: str) -> str:
        """`key` is an idempotency key: the same key must never apply the change twice."""

    def summarize(self, args: Mapping[str, object]) -> str:
        """Code-generated, human-readable description used to ask for confirmation."""
        return self.spec.name

    def needs_confirmation(self, args: Mapping[str, object]) -> bool:
        """Static by default. Override when only some calls of the tool are sensitive."""
        return self.spec.requires_confirmation
```

- [ ] **Step 7: Create `app/application/tools/__init__.py`**

Create the empty file `app/application/tools/__init__.py`.

- [ ] **Step 8: Create `app/application/tools/args.py`**

Create `app/application/tools/args.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from app.domain.exceptions import ToolArgumentError

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def object_schema(
    properties: Mapping[str, tuple[str, str]], required: Sequence[str] | None = None
) -> dict[str, object]:
    """JSON schema for a tool. `properties` maps name -> (json type, description).

    Every property is required unless `required` lists the ones that are."""
    return {
        "type": "object",
        "properties": {
            name: {"type": json_type, "description": description}
            for name, (json_type, description) in properties.items()
        },
        "required": list(properties if required is None else required),
        "additionalProperties": False,
    }


def _invalid(name: str) -> ToolArgumentError:
    return ToolArgumentError(f"argumento {name!r} ausente ou inválido")


def str_arg(args: Mapping[str, object], name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise _invalid(name)
    return value.strip()


def int_arg(args: Mapping[str, object], name: str) -> int:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(name)
    return value


def date_arg(args: Mapping[str, object], name: str) -> date:
    try:
        return date.fromisoformat(str_arg(args, name))
    except ValueError as exc:
        raise ToolArgumentError(f"argumento {name!r} deve ser AAAA-MM-DD") from exc


def datetime_arg(args: Mapping[str, object], name: str) -> datetime:
    try:
        return datetime.fromisoformat(str_arg(args, name))
    except ValueError as exc:
        raise ToolArgumentError(f"argumento {name!r} deve ser ISO 8601") from exc


# Optional arguments: absent or null (models often send null) means "leave it alone".


def opt_str(args: Mapping[str, object], name: str) -> str | None:
    return None if args.get(name) is None else str_arg(args, name)


def opt_int(args: Mapping[str, object], name: str) -> int | None:
    return None if args.get(name) is None else int_arg(args, name)


def opt_float(args: Mapping[str, object], name: str) -> float | None:
    value = args.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise _invalid(name)
    return float(value)


def opt_bool(args: Mapping[str, object], name: str) -> bool | None:
    value = args.get(name)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _invalid(name)
    return value


def opt_enum[E: StrEnum](args: Mapping[str, object], name: str, enum_type: type[E]) -> E | None:
    value = args.get(name)
    if value is None:
        return None
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ToolArgumentError(f"argumento {name!r} deve ser um de: {allowed}") from exc
```

- [ ] **Step 9: Create `app/application/tools/lights.py`**

Create `app/application/tools/lights.py`:

```python
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    object_schema,
    opt_bool,
    opt_int,
    str_arg,
)
from app.domain.exceptions import LightError
from app.domain.light import Color, LightChange, LightMode
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from app.domain.light import LightState
    from app.ports.light import LightPort

# Switching the same lamp on and off in quick succession can reset it into pairing mode.
MIN_TOGGLE_SECONDS = 5.0


def describe_light(name: str, state: LightState) -> str:
    if state.mode is LightMode.COLOUR:
        c = state.color
        look = f"cor (matiz {c.hue}, saturação {c.saturation}%, brilho {c.brightness}%)"
    else:
        look = (
            f"modo {state.mode.value}, brilho {state.brightness}%, "
            f"temperatura de cor {state.color_temperature}%"
        )
    return f"{name}: {'ligada' if state.power else 'desligada'}, {look}"


class ListLights(Tool):
    spec = ToolSpec(
        name="list_lights",
        description="Lista as luzes da casa com o estado atual de cada uma.",
        parameters=object_schema({}),
        segment="home",
    )

    def __init__(self, light: LightPort) -> None:
        self._light = light

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        names = await self._light.devices()
        lines = [describe_light(n, await self._light.get_state(n)) for n in names]
        return "; ".join(lines) or "nenhuma luz configurada"


class SetLight(Tool):
    spec = ToolSpec(
        name="set_light",
        description=(
            "Muda uma luz. Só informe o que mudar. Escolha um visual: branco (brightness "
            "e/ou color_temperature) ou cor (hue, com saturation e brightness). "
            "Escolher um visual liga a luz. Não ligue e desligue a mesma luz em sequência rápida."
        ),
        parameters=object_schema(
            {
                "name": ("string", "Nome da luz, como em list_lights."),
                "power": ("boolean", "true liga, false desliga."),
                "brightness": ("integer", "Brilho de 1 a 100."),
                "color_temperature": ("integer", "Temperatura de cor de 0 (quente) a 100 (fria)."),
                "hue": ("integer", "Matiz de 0 a 360; ativa o modo cor."),
                "saturation": ("integer", "Saturação de 0 a 100 (com hue; padrão 100)."),
                "timer_minutes": ("integer", "Desliga/liga em N minutos; 0 cancela o timer."),
                "do_not_disturb": ("boolean", "Modo não perturbe."),
            },
            required=["name"],
        ),
        segment="home",
    )

    def __init__(self, light: LightPort, now: Callable[[], float] = time.monotonic) -> None:
        self._light = light
        self._now = now
        self._last_toggle: dict[str, float] = {}

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        name = str_arg(args, "name")
        power = opt_bool(args, "power")
        hue = opt_int(args, "hue")
        brightness = opt_int(args, "brightness")
        color = None
        if hue is not None:
            saturation = opt_int(args, "saturation")
            color = Color(
                hue,
                100 if saturation is None else saturation,
                100 if brightness is None else brightness,
            )
        change = LightChange(
            power=power,
            brightness=None if color is not None else brightness,
            color_temperature=opt_int(args, "color_temperature"),
            color=color,
            timer_minutes=opt_int(args, "timer_minutes"),
            do_not_disturb=opt_bool(args, "do_not_disturb"),
        )
        if power is not None:
            self._guard_toggle(name)
        state = await self._light.apply(name, change)
        if power is not None:
            self._last_toggle[name.lower()] = self._now()
        return describe_light(name, state)

    def _guard_toggle(self, name: str) -> None:
        last = self._last_toggle.get(name.lower())
        if last is not None and self._now() - last < MIN_TOGGLE_SECONDS:
            raise LightError(
                "aguarde alguns segundos antes de ligar ou desligar a mesma luz de novo"
            )
```

- [ ] **Step 10: Create `app/application/tools/climate.py`**

Create `app/application/tools/climate.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    object_schema,
    opt_bool,
    opt_enum,
    opt_float,
    opt_int,
    str_arg,
)
from app.domain.climate import ClimateChange, ClimateMode, FanSpeed
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.domain.climate import ClimateState
    from app.ports.climate import ClimatePort


def describe_climate(name: str, state: ClimateState) -> str:
    text = (
        f"{name}: {'ligado' if state.power else 'desligado'}, modo {state.mode.value}, "
        f"alvo {state.target_temperature:g}°C, ambiente {state.current_temperature:g}°C, "
        f"ventilador {state.fan_speed.value}"
    )
    return f"{text}, ATENÇÃO: o aparelho reporta erro" if state.has_error else text


class ListClimates(Tool):
    spec = ToolSpec(
        name="list_climates",
        description="Lista os ar-condicionados da casa com o estado atual de cada um.",
        parameters=object_schema({}),
        segment="home",
    )

    def __init__(self, climate: ClimatePort) -> None:
        self._climate = climate

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        names = await self._climate.devices()
        lines = [describe_climate(n, await self._climate.get_state(n)) for n in names]
        return "; ".join(lines) or "nenhum ar-condicionado configurado"


class SetClimate(Tool):
    """Turning the unit on or off is physical, so that (and only that) asks for confirmation."""

    spec = ToolSpec(
        name="set_climate",
        description=(
            "Muda um ar-condicionado. Só informe o que mudar. Ligar ou desligar (power) exige "
            "confirmação do usuário. Um aparelho desligado recusa ajustes: ligue-o antes."
        ),
        parameters=object_schema(
            {
                "name": ("string", "Nome do aparelho, como em list_climates."),
                "power": ("boolean", "true liga, false desliga."),
                "mode": ("string", "cool, dry, fan ou auto."),
                "target_temperature": ("number", "Temperatura alvo de 18 a 30, de 0,5 em 0,5."),
                "fan_speed": ("string", "auto, low, mid, high ou nature."),
                "swing": ("boolean", "Oscilação das aletas."),
                "power_save": ("boolean", "Modo economia."),
                "display_light": ("boolean", "Luz do display do aparelho."),
                "stop_in_minutes": ("integer", "Desliga em N minutos; 0 cancela."),
                "start_in_minutes": ("integer", "Liga em N minutos; 0 cancela."),
                "sleep_in_minutes": ("integer", "Modo dormir por N minutos; 0 cancela."),
            },
            required=["name"],
        ),
        segment="home",
    )

    def __init__(self, climate: ClimatePort) -> None:
        self._climate = climate

    def needs_confirmation(self, args: Mapping[str, object]) -> bool:
        return opt_bool(args, "power") is not None

    def summarize(self, args: Mapping[str, object]) -> str:
        verb = "Ligar" if opt_bool(args, "power") else "Desligar"
        others = [k for k, v in args.items() if k not in ("name", "power") and v is not None]
        extra = " e aplicar os outros ajustes pedidos" if others else ""
        return f"{verb} {str_arg(args, 'name')}{extra}"

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        name = str_arg(args, "name")
        change = ClimateChange(
            power=opt_bool(args, "power"),
            mode=opt_enum(args, "mode", ClimateMode),
            target_temperature=opt_float(args, "target_temperature"),
            fan_speed=opt_enum(args, "fan_speed", FanSpeed),
            swing=opt_bool(args, "swing"),
            power_save=opt_bool(args, "power_save"),
            display_light=opt_bool(args, "display_light"),
            stop_in_minutes=opt_int(args, "stop_in_minutes"),
            start_in_minutes=opt_int(args, "start_in_minutes"),
            sleep_in_minutes=opt_int(args, "sleep_in_minutes"),
        )
        return describe_climate(name, await self._climate.apply(name, change))
```

- [ ] **Step 11: Create `app/application/tools/music.py`**

Create `app/application/tools/music.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    object_schema,
    opt_bool,
    opt_enum,
    opt_int,
    opt_str,
    str_arg,
)
from app.domain.exceptions import MusicError
from app.domain.music import MediaKind, PlaybackChange, Repeat, Skip
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.domain.music import MusicItem, PlaybackState
    from app.ports.music import MusicPort


class KnownUris:
    """URIs the model may play: only ones that a search or the playlists returned.

    The model must never invent a uri; it asks for one first (oldest forgotten past `limit`)."""

    def __init__(self, limit: int = 200) -> None:
        self._limit = limit
        self._uris: dict[str, None] = {}

    def remember(self, items: tuple[MusicItem, ...]) -> None:
        for item in items:
            self._uris.pop(item.uri, None)
            self._uris[item.uri] = None
        while len(self._uris) > self._limit:
            del self._uris[next(iter(self._uris))]

    def require(self, uri: str) -> str:
        if uri not in self._uris:
            raise MusicError("uri desconhecida: use search_music ou list_playlists primeiro")
        return uri


def describe_playback(state: PlaybackState) -> str:
    what = "nada" if state.item is None else f"{state.item.name} {state.item.artist}".strip()
    status = "tocando" if state.playing else "pausado"
    return f"{status}: {what} no aparelho {state.device}, volume {state.volume}%"


def describe_items(items: tuple[MusicItem, ...]) -> str:
    lines = [f"{i.uri} | {i.name} {i.artist}".strip() for i in items]
    return "; ".join(lines) or "nada encontrado"


class MusicState(Tool):
    spec = ToolSpec(
        name="music_state",
        description="Mostra o que está tocando agora, o volume e o aparelho.",
        parameters=object_schema({}),
        segment="music",
    )

    def __init__(self, music: MusicPort) -> None:
        self._music = music

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        return describe_playback(await self._music.state())


class ListMusicDevices(Tool):
    spec = ToolSpec(
        name="list_music_devices",
        description="Lista os aparelhos onde a música pode tocar (pelo nome).",
        parameters=object_schema({}),
        segment="music",
    )

    def __init__(self, music: MusicPort) -> None:
        self._music = music

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        return "; ".join(await self._music.devices()) or "nenhum aparelho disponível"


class SearchMusic(Tool):
    spec = ToolSpec(
        name="search_music",
        description="Procura músicas, álbuns, playlists ou artistas. Devolve 'uri | nome artista'.",
        parameters=object_schema(
            {
                "query": ("string", "O que procurar."),
                "kind": ("string", "track, album, playlist ou artist (padrão track)."),
            },
            required=["query"],
        ),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        kind = opt_enum(args, "kind", MediaKind) or MediaKind.TRACK
        items = await self._music.search(str_arg(args, "query"), kind)
        self._known.remember(items)
        return describe_items(items)


class ListPlaylists(Tool):
    spec = ToolSpec(
        name="list_playlists",
        description="Lista as playlists do usuário. Devolve 'uri | nome'.",
        parameters=object_schema({}),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        items = await self._music.playlists()
        self._known.remember(items)
        return describe_items(items)


class PlayMusic(Tool):
    spec = ToolSpec(
        name="play_music",
        description=(
            "Toca uma uri devolvida por search_music ou list_playlists, ou retoma a reprodução "
            "se uri não for informada. 'device' move a reprodução para outro aparelho."
        ),
        parameters=object_schema(
            {
                "uri": ("string", "Uri a tocar (nunca invente uma)."),
                "device": ("string", "Nome do aparelho de destino."),
            },
            required=[],
        ),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        uri = opt_str(args, "uri")
        if uri is not None:
            self._known.require(uri)
        return describe_playback(await self._music.play(uri, opt_str(args, "device")))


class ControlMusic(Tool):
    spec = ToolSpec(
        name="control_music",
        description=(
            "Pausa, volume, aleatório, repetição, pular ou avançar. Só informe o que mudar."
        ),
        parameters=object_schema(
            {
                "paused": ("boolean", "true pausa, false retoma."),
                "volume": ("integer", "Volume de 0 a 100."),
                "shuffle": ("boolean", "Modo aleatório."),
                "repeat": ("string", "off, track ou context."),
                "skip": ("string", "next ou previous."),
                "seek_ms": ("integer", "Posição em milissegundos."),
            },
            required=[],
        ),
        segment="music",
    )

    def __init__(self, music: MusicPort) -> None:
        self._music = music

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        change = PlaybackChange(
            paused=opt_bool(args, "paused"),
            volume=opt_int(args, "volume"),
            shuffle=opt_bool(args, "shuffle"),
            repeat=opt_enum(args, "repeat", Repeat),
            seek_ms=opt_int(args, "seek_ms"),
            skip=opt_enum(args, "skip", Skip),
        )
        return describe_playback(await self._music.apply(change))


class QueueMusic(Tool):
    spec = ToolSpec(
        name="queue_music",
        description="Adiciona à fila uma uri devolvida por search_music ou list_playlists.",
        parameters=object_schema({"uri": ("string", "Uri a enfileirar (nunca invente uma).")}),
        segment="music",
    )

    def __init__(self, music: MusicPort, known: KnownUris) -> None:
        self._music = music
        self._known = known

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        await self._music.queue(self._known.require(str_arg(args, "uri")))
        return "adicionada à fila"
```

- [ ] **Step 12: Create `app/application/tools/agenda.py`**

Create `app/application/tools/agenda.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import (
    date_arg,
    datetime_arg,
    int_arg,
    object_schema,
    str_arg,
)
from app.domain.exceptions import ToolArgumentError
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.ports.calendar import CalendarPort


class ListEvents(Tool):
    spec = ToolSpec(
        name="list_events",
        description="Lista os eventos de um dia.",
        parameters=object_schema({"date": ("string", "Dia no formato AAAA-MM-DD.")}),
        segment="agenda",
    )

    def __init__(self, calendar: CalendarPort) -> None:
        self._calendar = calendar

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        events = await self._calendar.list_events(date_arg(args, "date"))
        lines = [f"{e.id}: {e.start:%H:%M} {e.title} ({e.duration_minutes} min)" for e in events]
        return "; ".join(lines) or "nenhum evento"


class CreateEvent(Tool):
    spec = ToolSpec(
        name="create_event",
        description="Cria um evento no calendário.",
        parameters=object_schema(
            {
                "title": ("string", "Título do evento."),
                "start": ("string", "Início em ISO 8601, ex.: 2026-10-06T15:00:00-03:00."),
                "duration_minutes": ("integer", "Duração em minutos."),
            }
        ),
        segment="agenda",
    )

    def __init__(self, calendar: CalendarPort) -> None:
        self._calendar = calendar

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        duration = int_arg(args, "duration_minutes")
        if duration <= 0:
            raise ToolArgumentError("duration_minutes deve ser positivo")
        event = await self._calendar.create_event(
            key, str_arg(args, "title"), datetime_arg(args, "start"), duration
        )
        return f"Evento criado: {event.id} {event.start:%d/%m %H:%M} {event.title}"


class DeleteEvent(Tool):
    spec = ToolSpec(
        name="delete_event",
        description="Apaga um evento do calendário. Exige confirmação do usuário.",
        parameters=object_schema({"event_id": ("string", "Id do evento, como em list_events.")}),
        segment="agenda",
        requires_confirmation=True,
    )

    def __init__(self, calendar: CalendarPort) -> None:
        self._calendar = calendar

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        event_id = str_arg(args, "event_id")
        await self._calendar.delete_event(event_id)
        return f"Evento {event_id} apagado"

    def summarize(self, args: Mapping[str, object]) -> str:
        return f"Apagar o evento {str_arg(args, 'event_id')}"
```

- [ ] **Step 13: Create `app/application/tools/finance.py`**

Create `app/application/tools/finance.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.tool import Tool
from app.application.tools.args import date_arg, int_arg, object_schema, str_arg
from app.domain.exceptions import ToolArgumentError
from app.domain.tools import ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.ports.expenses import ExpensesPort


def brl(cents: int) -> str:
    return f"R$ {cents // 100},{cents % 100:02d}"


class AddExpense(Tool):
    spec = ToolSpec(
        name="add_expense",
        description="Registra um gasto. Exige confirmação do usuário.",
        parameters=object_schema(
            {
                "amount_cents": ("integer", "Valor em centavos, ex.: R$ 50,00 = 5000."),
                "category": ("string", "Categoria, ex.: mercado."),
                "description": ("string", "Descrição curta."),
                "date": ("string", "Dia do gasto no formato AAAA-MM-DD."),
            }
        ),
        segment="finance",
        requires_confirmation=True,
    )

    def __init__(self, expenses: ExpensesPort) -> None:
        self._expenses = expenses

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        amount = int_arg(args, "amount_cents")
        if amount <= 0:
            raise ToolArgumentError("amount_cents deve ser positivo")
        expense = await self._expenses.add_expense(
            key,
            amount,
            str_arg(args, "category"),
            str_arg(args, "description"),
            date_arg(args, "date"),
        )
        return f"Gasto registrado: {brl(expense.amount_cents)} em {expense.category}"

    def summarize(self, args: Mapping[str, object]) -> str:
        return (
            f"Registrar gasto de {brl(int_arg(args, 'amount_cents'))} "
            f"em {str_arg(args, 'category')}: {str_arg(args, 'description')}"
        )


class MonthTotal(Tool):
    spec = ToolSpec(
        name="month_total",
        description="Total gasto em um mês.",
        parameters=object_schema(
            {"year": ("integer", "Ano, ex.: 2026."), "month": ("integer", "Mês de 1 a 12.")}
        ),
        segment="finance",
    )

    def __init__(self, expenses: ExpensesPort) -> None:
        self._expenses = expenses

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        year, month = int_arg(args, "year"), int_arg(args, "month")
        if not 1 <= month <= 12:  # noqa: PLR2004
            raise ToolArgumentError("month deve estar entre 1 e 12")
        total = await self._expenses.month_total(year, month)
        return f"Total de {month:02d}/{year}: {brl(total)}"
```

- [ ] **Step 14: Create `app/application/tools/catalog.py`**

Create `app/application/tools/catalog.py`:

```python
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from app.application.registry import Registry
from app.application.tools.agenda import CreateEvent, DeleteEvent, ListEvents
from app.application.tools.climate import ListClimates, SetClimate
from app.application.tools.finance import AddExpense, MonthTotal
from app.application.tools.lights import ListLights, SetLight
from app.application.tools.music import (
    ControlMusic,
    KnownUris,
    ListMusicDevices,
    ListPlaylists,
    MusicState,
    PlayMusic,
    QueueMusic,
    SearchMusic,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.application.tool import Tool
    from app.ports.calendar import CalendarPort
    from app.ports.climate import ClimatePort
    from app.ports.expenses import ExpensesPort
    from app.ports.light import LightPort
    from app.ports.music import MusicPort


def build_tool_registry(
    light: LightPort,
    climate: ClimatePort,
    music: MusicPort,
    calendar: CalendarPort,
    expenses: ExpensesPort,
    now: Callable[[], float] = time.monotonic,
) -> Registry[Tool]:
    known = KnownUris()
    registry: Registry[Tool] = Registry()
    tools: tuple[Tool, ...] = (
        ListLights(light),
        SetLight(light, now),
        ListClimates(climate),
        SetClimate(climate),
        MusicState(music),
        ListMusicDevices(music),
        SearchMusic(music, known),
        ListPlaylists(music, known),
        PlayMusic(music, known),
        ControlMusic(music),
        QueueMusic(music, known),
        ListEvents(calendar),
        CreateEvent(calendar),
        DeleteEvent(calendar),
        AddExpense(expenses),
        MonthTotal(expenses),
    )
    for tool in tools:
        registry.register(tool.spec.name, tool)
    return registry
```

- [ ] **Step 15: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/application -q --no-cov
```

Expected: PASS.

- [ ] **Step 16: Commit**

```bash
git add app/application/registry.py \
  app/application/tool.py \
  app/application/tools \
  tests/unit/application/tools \
  tests/unit/application/test_registry.py
git commit -m "feat(application): add Tool, argument helpers and the light, climate, music, agenda and finance tools"
```

### Task 4: `PendingActionStore`: one pending action, valid for the very next utterance

**Files:**
- Create: `app/application/pending_actions.py`
- Test: `tests/unit/application/test_pending_actions.py`

**Interfaces:**
- Consumes: `PendingAction` and `is_affirmative` from Task 1.
- Produces: `PendingActionStore(now, ttl_seconds=60.0)` with `create(conversation_id, tool, arguments, summary, key)`, `on_user_utterance(conversation_id, text)`, `peek(conversation_id)`, `confirm(conversation_id) -> (PendingAction | None, reason)`; constants `NOTHING_PENDING`, `NOT_ARMED`, `NOT_CONFIRMED`; test helper `FakeClock` (callable, `.advance(seconds)`).

The rule that closes the confirmation holes: `on_user_utterance` is called for **every** user utterance. The first one after `create` arms the action (and records its text); any later one drops it. `confirm` is synchronous, so check-and-pop is atomic and two parallel `confirm_action` calls cannot both win.

- [ ] **Step 1: Create `tests/unit/application/test_pending_actions.py`**

Create `tests/unit/application/test_pending_actions.py`:

```python
from __future__ import annotations

import pytest

from app.application.pending_actions import (
    NOT_ARMED,
    NOT_CONFIRMED,
    NOTHING_PENDING,
    PendingActionStore,
)
from tests.fakes.clock import FakeClock


def make() -> tuple[PendingActionStore, FakeClock]:
    clock = FakeClock()
    return PendingActionStore(clock, ttl_seconds=60), clock


def create(store: PendingActionStore, conversation_id: str = "c1") -> None:
    store.create(conversation_id, "delete_event", '{"event_id":"evt-1"}', "Apagar", "key-1")


@pytest.mark.unit
def test_nothing_pending() -> None:
    store, _ = make()
    assert store.confirm("c1") == (None, NOTHING_PENDING)


@pytest.mark.unit
def test_confirm_in_the_same_turn_is_refused_and_keeps_the_action() -> None:
    store, _ = make()
    create(store)
    assert store.confirm("c1") == (None, NOT_ARMED)
    assert store.peek("c1") is not None


@pytest.mark.unit
def test_next_affirmative_utterance_confirms_once() -> None:
    store, _ = make()
    create(store)
    store.on_user_utterance("c1", "sim, pode")
    action, reason = store.confirm("c1")
    assert action is not None
    assert action.key == "key-1"
    assert reason == ""
    assert store.confirm("c1") == (None, NOTHING_PENDING)


@pytest.mark.unit
def test_non_affirmative_utterance_consumes_the_action() -> None:
    store, _ = make()
    create(store)
    store.on_user_utterance("c1", "não, cancela")
    assert store.confirm("c1") == (None, NOT_CONFIRMED)
    assert store.peek("c1") is None


@pytest.mark.unit
def test_an_unrelated_utterance_between_request_and_yes_drops_the_action() -> None:
    store, _ = make()
    create(store)
    store.on_user_utterance("c1", "que horas são")
    store.on_user_utterance("c1", "sim")
    assert store.confirm("c1") == (None, NOTHING_PENDING)


@pytest.mark.unit
def test_expires_after_ttl() -> None:
    store, clock = make()
    create(store)
    store.on_user_utterance("c1", "sim")
    clock.advance(60)
    assert store.confirm("c1") == (None, NOTHING_PENDING)


@pytest.mark.unit
def test_pending_actions_are_isolated_per_conversation() -> None:
    store, _ = make()
    create(store, "a")
    store.on_user_utterance("b", "sim")
    assert store.confirm("b") == (None, NOTHING_PENDING)
    assert store.peek("a") is not None


@pytest.mark.unit
def test_a_new_request_replaces_the_old_one() -> None:
    store, _ = make()
    create(store)
    store.create("c1", "delete_event", '{"event_id":"evt-1"}', "Apagar", "key-2")
    store.on_user_utterance("c1", "sim")
    action, _ = store.confirm("c1")
    assert action is not None
    assert action.key == "key-2"
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/application/test_pending_actions.py -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 3: Create `app/application/pending_actions.py`**

Create `app/application/pending_actions.py`:

```python
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from app.domain.affirmation import is_affirmative
from app.domain.tools import PendingAction

if TYPE_CHECKING:
    from collections.abc import Callable

NOTHING_PENDING = "nada para confirmar"
NOT_ARMED = "aguarde a resposta do usuário antes de confirmar"
NOT_CONFIRMED = "o usuário não confirmou"


class PendingActionStore:
    """One pending action per conversation, valid for the very next user utterance only."""

    def __init__(self, now: Callable[[], float], ttl_seconds: float = 60.0) -> None:
        self._now = now
        self._ttl = ttl_seconds
        self._pending: dict[str, PendingAction] = {}

    def create(
        self, conversation_id: str, tool: str, arguments: str, summary: str, key: str
    ) -> PendingAction:
        action = PendingAction(
            tool=tool,
            arguments=arguments,
            summary=summary,
            key=key,
            expires_at=self._now() + self._ttl,
        )
        self._pending[conversation_id] = action
        return action

    def on_user_utterance(self, conversation_id: str, text: str) -> None:
        """Call for every user utterance. The first one after creation arms the action;
        any later one drops it, so an old request can never be confirmed by a later "sim"."""
        action = self.peek(conversation_id)
        if action is None:
            return
        if action.armed:
            del self._pending[conversation_id]
            return
        self._pending[conversation_id] = replace(action, armed=True, armed_text=text)

    def peek(self, conversation_id: str) -> PendingAction | None:
        action = self._pending.get(conversation_id)
        if action is None:
            return None
        if self._now() >= action.expires_at:
            del self._pending[conversation_id]
            return None
        return action

    def confirm(self, conversation_id: str) -> tuple[PendingAction | None, str]:
        """Synchronous, so the check-and-pop is atomic: two parallel calls cannot both win."""
        action = self.peek(conversation_id)
        if action is None:
            return None, NOTHING_PENDING
        if not action.armed:
            return None, NOT_ARMED
        del self._pending[conversation_id]
        if not is_affirmative(action.armed_text):
            return None, NOT_CONFIRMED
        return action, ""
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/application/test_pending_actions.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/application/pending_actions.py \
  tests/unit/application/test_pending_actions.py
git commit -m "feat(application): add PendingActionStore with next-utterance-only confirmation"
```

### Task 5: `ToolRunner`: allowlist, timeout, shielded execution and the confirmation gate

**Files:**
- Create: `app/application/tool_runner.py`, `tests/fakes/logger.py`
- Test: `tests/unit/application/test_tool_runner.py`

**Interfaces:**
- Consumes: `Registry[Tool]`, `Tool`, `object_schema`, `PendingActionStore`, `ToolCall`/`ToolResult`/`ToolSpec`, `LoggerPort`, Task 3 catalog.
- Produces: `ToolRunner(tools, pending, log, *, tool_timeout=10.0, max_output_chars=2000)` with `segments()`, `specs(segment) -> tuple[ToolSpec, ...]` (always ends with `confirm_action`), `async run(call, conversation_id, segment) -> ToolResult`, `async drain()`; constants `CONFIRM_ACTION`, `UNKNOWN_STATE`; test helper `RecordingLogger`.

Failures never reach the caller as exceptions: the model gets `erro: ...` text and can explain it. A tool runs as its own task shielded from cancellation (the runner keeps a strong reference and `drain()` waits for it at shutdown); if it outlives the timeout the model hears `estado desconhecido`, never success or failure. Sensitive tools only create a pending action; the built-in `confirm_action()` executes it, with the pending action's key as idempotency key.

- [ ] **Step 1: Create `tests/fakes/logger.py`**

Create `tests/fakes/logger.py`:

```python
from __future__ import annotations

from app.ports.logger import LoggerPort


class RecordingLogger(LoggerPort):
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, object]]] = []

    def debug(self, event: str, **fields: object) -> None:
        self.events.append(("debug", event, fields))

    def info(self, event: str, **fields: object) -> None:
        self.events.append(("info", event, fields))

    def warning(self, event: str, **fields: object) -> None:
        self.events.append(("warning", event, fields))

    def error(self, event: str, **fields: object) -> None:
        self.events.append(("error", event, fields))

    def names(self) -> list[str]:
        return [name for _, name, _ in self.events]
```

- [ ] **Step 2: Create `tests/unit/application/test_tool_runner.py`**

Create `tests/unit/application/test_tool_runner.py`:

```python
from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.pending_actions import PendingActionStore
from app.application.registry import Registry
from app.application.tool import Tool
from app.application.tool_runner import CONFIRM_ACTION, UNKNOWN_STATE, ToolRunner
from app.application.tools.args import object_schema
from app.application.tools.catalog import build_tool_registry
from app.domain.exceptions import DomainError
from app.domain.tools import ToolCall, ToolSpec
from tests.fakes.clock import FakeClock
from tests.fakes.events import events_on_day, seed_event
from tests.fakes.logger import RecordingLogger

if TYPE_CHECKING:
    from collections.abc import Mapping

CID = "c1"


class RecordingTool(Tool):
    def __init__(
        self,
        name: str,
        *,
        segment: str = "home",
        confirm: bool = False,
        output: str = "ok",
        gate: asyncio.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self.spec = ToolSpec(name, "d", object_schema({}), segment, confirm)
        self.calls: list[tuple[Mapping[str, object], str]] = []
        self.finished = False
        self._output = output
        self._gate = gate
        self._error = error

    async def execute(self, args: Mapping[str, object], key: str) -> str:
        self.calls.append((args, key))
        if self._gate is not None:
            await self._gate.wait()
        if self._error is not None:
            raise self._error
        self.finished = True
        return self._output

    def summarize(self, args: Mapping[str, object]) -> str:
        return f"Resumo de {self.spec.name}"


def build(
    *tools: Tool, timeout: float = 5.0, max_chars: int = 2000
) -> tuple[ToolRunner, PendingActionStore, RecordingLogger]:
    registry: Registry[Tool] = Registry()
    for tool in tools:
        registry.register(tool.spec.name, tool)
    pending = PendingActionStore(FakeClock(), ttl_seconds=60)
    log = RecordingLogger()
    runner = ToolRunner(registry, pending, log, tool_timeout=timeout, max_output_chars=max_chars)
    return runner, pending, log


def call(name: str, arguments: str = "{}", call_id: str = "call-1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


@pytest.mark.unit
async def test_unknown_tool() -> None:
    runner, _, _ = build()
    result = await runner.run(call("nope"), CID, None)
    assert result.output == "erro: ferramenta desconhecida"
    assert result.call_id == "call-1"


@pytest.mark.unit
async def test_tool_outside_the_segment_filter() -> None:
    runner, _, _ = build(RecordingTool("t", segment="home"))
    result = await runner.run(call("t"), CID, "finance")
    assert result.output == "erro: ferramenta fora do segmento"


@pytest.mark.unit
@pytest.mark.parametrize("arguments", ["{not json", "[1, 2]", '"text"'])
async def test_bad_arguments_become_an_error_text(arguments: str) -> None:
    tool = RecordingTool("t")
    runner, _, _ = build(tool)
    result = await runner.run(call("t", arguments), CID, None)
    assert result.output.startswith("erro:")
    assert tool.calls == []


@pytest.mark.unit
async def test_runs_a_safe_tool_with_the_call_id_as_idempotency_key() -> None:
    tool = RecordingTool("t", output="feito")
    runner, _, _ = build(tool)
    result = await runner.run(call("t", call_id="call-9"), CID, None)
    assert result.output == "feito"
    assert tool.calls == [({}, "call-9")]


@pytest.mark.unit
async def test_output_is_truncated() -> None:
    runner, _, _ = build(RecordingTool("t", output="x" * 50), max_chars=10)
    assert (await runner.run(call("t"), CID, None)).output == "x" * 10


@pytest.mark.unit
async def test_domain_error_is_reported_to_the_model() -> None:
    runner, _, _ = build(RecordingTool("t", error=DomainError("dispositivo sumiu")))
    assert (await runner.run(call("t"), CID, None)).output == "erro: dispositivo sumiu"


@pytest.mark.unit
async def test_unexpected_error_does_not_leak_details() -> None:
    runner, _, log = build(RecordingTool("t", error=RuntimeError("senha=123")))
    result = await runner.run(call("t"), CID, None)
    assert result.output == "erro: falha interna na ferramenta"
    await runner.drain()
    assert "tool.failed" in log.names()
    assert "senha" not in repr(log.events)


@pytest.mark.unit
async def test_timeout_reports_unknown_state_and_the_tool_still_finishes() -> None:
    gate = asyncio.Event()
    tool = RecordingTool("t", gate=gate)
    runner, _, log = build(tool, timeout=0.01)
    result = await runner.run(call("t"), CID, None)
    assert result.output == UNKNOWN_STATE
    gate.set()
    await runner.drain()
    assert tool.finished is True
    assert "tool.done" in log.names()


@pytest.mark.unit
async def test_cancelling_the_caller_does_not_abort_the_tool() -> None:
    gate = asyncio.Event()
    tool = RecordingTool("t", gate=gate)
    runner, _, _ = build(tool)
    caller = asyncio.create_task(runner.run(call("t"), CID, None))
    await asyncio.sleep(0.01)
    caller.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await caller
    gate.set()
    await runner.drain()
    assert tool.finished is True


@pytest.mark.unit
async def test_sensitive_tool_is_not_executed_when_called() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, pending, _ = build(tool)
    result = await runner.run(call("danger"), CID, None)
    assert result.output.startswith("needs_confirmation:")
    assert "Resumo de danger" in result.output
    assert tool.calls == []
    assert pending.peek(CID) is not None


@pytest.mark.unit
async def test_confirmation_flow_executes_once_with_the_pending_key() -> None:
    tool = RecordingTool("danger", confirm=True, output="feito")
    runner, pending, _ = build(tool)
    await runner.run(call("danger", '{"a": 1}'), CID, None)
    action = pending.peek(CID)
    assert action is not None
    pending.on_user_utterance(CID, "sim")

    first = await runner.run(call(CONFIRM_ACTION), CID, None)
    second = await runner.run(call(CONFIRM_ACTION), CID, None)

    assert first.output == "feito"
    assert tool.calls == [({"a": 1}, action.key)]
    assert second.output == "erro: nada para confirmar"


@pytest.mark.unit
async def test_confirm_in_the_same_turn_is_refused() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, _, _ = build(tool)
    await runner.run(call("danger"), CID, None)
    result = await runner.run(call(CONFIRM_ACTION), CID, None)
    assert result.output.startswith("erro: aguarde")
    assert tool.calls == []


@pytest.mark.unit
async def test_a_negative_answer_never_executes() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, pending, _ = build(tool)
    await runner.run(call("danger"), CID, None)
    pending.on_user_utterance(CID, "não, deixa pra lá")
    result = await runner.run(call(CONFIRM_ACTION), CID, None)
    assert result.output == "erro: o usuário não confirmou"
    assert tool.calls == []


@pytest.mark.unit
async def test_confirm_with_nothing_pending() -> None:
    runner, _, _ = build()
    assert (await runner.run(call(CONFIRM_ACTION), CID, None)).output == "erro: nada para confirmar"


@pytest.mark.unit
async def test_parallel_confirm_calls_execute_once() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, pending, _ = build(tool)
    await runner.run(call("danger"), CID, None)
    pending.on_user_utterance(CID, "sim")
    results = await asyncio.gather(
        runner.run(call(CONFIRM_ACTION, call_id="a"), CID, None),
        runner.run(call(CONFIRM_ACTION, call_id="b"), CID, None),
    )
    assert len(tool.calls) == 1
    assert sorted(r.output for r in results) == ["erro: nada para confirmar", "ok"]


@pytest.mark.unit
async def test_pending_action_of_another_conversation_cannot_be_confirmed() -> None:
    tool = RecordingTool("danger", confirm=True)
    runner, pending, _ = build(tool)
    await runner.run(call("danger"), "mine", None)
    pending.on_user_utterance("other", "sim")
    result = await runner.run(call(CONFIRM_ACTION), "other", None)
    assert result.output == "erro: nada para confirmar"
    assert tool.calls == []


@pytest.mark.unit
async def test_specs_always_include_confirm_action_and_respect_the_segment() -> None:
    runner, _, _ = build(RecordingTool("a", segment="home"), RecordingTool("b", segment="agenda"))
    assert [s.name for s in runner.specs(None)] == ["a", "b", CONFIRM_ACTION]
    assert [s.name for s in runner.specs("agenda")] == ["b", CONFIRM_ACTION]
    assert runner.segments() == frozenset({"home", "agenda"})


def real_tools_runner() -> tuple[ToolRunner, PendingActionStore, InMemoryCalendar, InMemoryClimate]:
    calendar = InMemoryCalendar()
    climate = InMemoryClimate()
    registry = build_tool_registry(
        InMemoryLight(), climate, InMemoryMusic(), calendar, InMemoryExpenses()
    )
    pending = PendingActionStore(FakeClock())
    return ToolRunner(registry, pending, RecordingLogger()), pending, calendar, climate


@pytest.mark.unit
async def test_switching_the_air_conditioner_on_asks_first_and_applies_everything_once() -> None:
    runner, pending, _, climate = real_tools_runner()
    args = '{"name": "ar-condicionado", "power": true, "target_temperature": 22}'

    asked = await runner.run(call("set_climate", args), CID, None)

    assert asked.output.startswith("needs_confirmation:")
    assert "Ligar ar-condicionado e aplicar os outros ajustes pedidos" in asked.output
    assert (await climate.get_state("ar-condicionado")).power is False

    pending.on_user_utterance(CID, "pode sim")
    done = await runner.run(call(CONFIRM_ACTION), CID, None)

    state = await climate.get_state("ar-condicionado")
    assert (state.power, state.target_temperature) == (True, 22.0)
    assert done.output.startswith("ar-condicionado: ligado")


@pytest.mark.unit
async def test_adjusting_the_air_conditioner_without_switching_it_does_not_ask() -> None:
    runner, _, _, climate = real_tools_runner()

    result = await runner.run(
        call("set_climate", '{"name": "ar-condicionado", "target_temperature": 21}'), CID, None
    )

    assert not result.output.startswith("needs_confirmation:")
    assert (await climate.get_state("ar-condicionado")).target_temperature == 21.0


@pytest.mark.unit
async def test_end_to_end_with_the_real_agenda_tools() -> None:
    runner, pending, calendar, _ = real_tools_runner()
    event = await seed_event(calendar)

    asked = await runner.run(call("delete_event", f'{{"event_id": "{event.id}"}}'), CID, None)
    assert "Apagar o evento evt-1" in asked.output
    assert len(await events_on_day(calendar)) == 1

    pending.on_user_utterance(CID, "pode sim")
    done = await runner.run(call(CONFIRM_ACTION), CID, None)

    assert done.output == "Evento evt-1 apagado"
    assert await events_on_day(calendar) == ()


@pytest.mark.unit
async def test_unknown_device_from_the_model_becomes_error_text_not_a_crash() -> None:
    runner, _, _, _ = real_tools_runner()

    result = await runner.run(call("set_light", '{"name": "cofre", "power": true}'), CID, None)

    assert result.output == "erro: unknown light: 'cofre'"
```

- [ ] **Step 3: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/application/test_tool_runner.py -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 4: Create `app/application/tool_runner.py`**

Create `app/application/tool_runner.py`:

```python
from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from app.application.tools.args import object_schema
from app.domain.exceptions import DomainError, RegistryKeyError, ToolArgumentError
from app.domain.tools import ToolResult, ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.application.pending_actions import PendingActionStore
    from app.application.registry import Registry
    from app.application.tool import Tool
    from app.domain.tools import ToolCall
    from app.ports.logger import LoggerPort

CONFIRM_ACTION = "confirm_action"
CONFIRM_SPEC = ToolSpec(
    name=CONFIRM_ACTION,
    description=(
        "Executa a ação pendente depois que o usuário a confirmou na fala seguinte. "
        "Não recebe argumentos. Só chame depois de ler o resumo ao usuário e ouvir a resposta."
    ),
    parameters=object_schema({}),
    segment="*",
)
UNKNOWN_STATE = "estado desconhecido: verifique o dispositivo antes de tentar de novo"


def _parse(arguments: str) -> Mapping[str, object]:
    try:
        parsed: object = json.loads(arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ToolArgumentError("argumentos não são JSON válido") from exc
    if not isinstance(parsed, dict):
        raise ToolArgumentError("argumentos devem ser um objeto JSON")
    return cast("dict[str, object]", parsed)  # JSON object keys are always str


class ToolRunner:
    """Runs tool calls: allowlist, confirmation gate, timeout, shielded execution."""

    def __init__(
        self,
        tools: Registry[Tool],
        pending: PendingActionStore,
        log: LoggerPort,
        *,
        tool_timeout: float = 10.0,
        max_output_chars: int = 2000,
    ) -> None:
        self._tools = tools
        self._pending = pending
        self._log = log
        self._timeout = tool_timeout
        self._max_chars = max_output_chars
        self._tasks: set[asyncio.Task[str]] = set()

    def segments(self) -> frozenset[str]:
        return frozenset(t.spec.segment for t in self._tools.values())

    def specs(self, segment: str | None) -> tuple[ToolSpec, ...]:
        chosen = tuple(
            t.spec for t in self._tools.values() if segment is None or t.spec.segment == segment
        )
        return (*chosen, CONFIRM_SPEC)

    async def run(self, call: ToolCall, conversation_id: str, segment: str | None) -> ToolResult:
        output = await self._dispatch(call, conversation_id, segment)
        return ToolResult(call_id=call.id, output=output[: self._max_chars])

    async def drain(self) -> None:
        """Wait for tool tasks still running (called on shutdown)."""
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _dispatch(self, call: ToolCall, conversation_id: str, segment: str | None) -> str:
        if call.name == CONFIRM_ACTION:
            return await self._confirm(conversation_id)
        try:
            tool = self._tools.get(call.name)
        except RegistryKeyError:
            return "erro: ferramenta desconhecida"
        if segment is not None and tool.spec.segment != segment:
            return "erro: ferramenta fora do segmento"
        try:
            args = _parse(call.arguments)
            if not tool.needs_confirmation(args):
                return await self._execute(tool, args, key=call.id)
            summary = tool.summarize(args)
        except DomainError as exc:
            return f"erro: {exc}"
        self._pending.create(conversation_id, call.name, call.arguments, summary, uuid4().hex)
        return (
            "needs_confirmation: leia ao usuário, palavra por palavra, e aguarde a resposta: "
            f'"{summary}". Se ele confirmar na fala seguinte, chame {CONFIRM_ACTION}.'
        )

    async def _confirm(self, conversation_id: str) -> str:
        action, reason = self._pending.confirm(conversation_id)
        if action is None:
            return f"erro: {reason}"
        try:
            tool = self._tools.get(action.tool)
            args = _parse(action.arguments)
        except DomainError as exc:
            return f"erro: {exc}"
        return await self._execute(tool, args, key=action.key)

    async def _execute(self, tool: Tool, args: Mapping[str, object], key: str) -> str:
        task = asyncio.create_task(tool.execute(args, key))
        self._tasks.add(task)
        task.add_done_callback(partial(self._finished, tool.spec.name))
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=self._timeout)
        except TimeoutError:
            return UNKNOWN_STATE
        except DomainError as exc:
            return f"erro: {exc}"
        except Exception:
            return "erro: falha interna na ferramenta"

    def _finished(self, name: str, task: asyncio.Task[str]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            self._log.warning("tool.cancelled", tool=name)
        elif (exc := task.exception()) is not None:
            self._log.error("tool.failed", tool=name, error=type(exc).__name__)
        else:
            self._log.info("tool.done", tool=name)
```

- [ ] **Step 5: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/application/test_tool_runner.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/application/tool_runner.py \
  tests/fakes/logger.py \
  tests/unit/application/test_tool_runner.py
git commit -m "feat(application): add ToolRunner with timeout, shielded execution and confirmation"
```

### Task 6: `ChatModelPort` and `ProcessChatMessage` (the tool loop)

**Files:**
- Create: `app/ports/chat_model.py`, `app/application/prompts.py`, `app/application/use_cases/process_chat_message.py`
- Create: `tests/fakes/chat_model.py`, `tests/fakes/world.py`
- Test: `tests/unit/application/use_cases/test_process_chat_message.py`

**Interfaces:**
- Consumes: Tasks 1-5 (`ModelMessage`, `ModelTurn`, `ToolRunner`, `PendingActionStore`, `ConversationStorePort`, in-memory adapters, fakes) and your `InMemoryLight/Climate/Music`.
- Produces: `ChatModelPort.complete(messages, tools) -> ModelTurn`; `SYSTEM_PROMPT`; `ChatReply(message, pending_summary)`; `ProcessChatMessage(model, store, runner, pending, log, *, max_steps=6, history_limit=20, timeout_seconds=30.0).execute(conversation_id, text, segment) -> ChatReply`; test helpers `ScriptedChatModel(turns)`, `World(turns, ...)` (with `light`, `calendar`), `text_turn`, `tool_turn`.

The loop: call the model, run the tool calls it asks for, feed the results back, repeat up to 6 times. Only user and assistant text is persisted (tool results are not), and only the last 20 messages are sent. Every request first calls `pending.on_user_utterance`, which is what arms or drops a pending action. A 30 s timeout becomes `AgentError`.

The confirmation tests use **deleting a calendar event** as the sensitive action (the seeded `dentista` appointment), since that is what actually asks for confirmation.

- [ ] **Step 1: Create `tests/fakes/chat_model.py`**

Create `tests/fakes/chat_model.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.ports.chat_model import ChatModelPort

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.model import ModelMessage, ModelTurn
    from app.domain.tools import ToolSpec


class ScriptedChatModel(ChatModelPort):
    """Returns the scripted turns in order and records every call it receives."""

    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self._turns = list(turns)
        self.calls: list[tuple[tuple[ModelMessage, ...], tuple[ToolSpec, ...]]] = []

    async def complete(
        self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        self.calls.append((tuple(messages), tuple(tools)))
        return self._turns.pop(0)
```

- [ ] **Step 2: Create `tests/fakes/world.py`**

Create `tests/fakes/world.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.use_cases.process_chat_message import ProcessChatMessage
from app.domain.model import ModelTurn
from app.domain.tools import ToolCall
from tests.fakes.chat_model import ScriptedChatModel
from tests.fakes.clock import FakeClock
from tests.fakes.logger import RecordingLogger

if TYPE_CHECKING:
    from collections.abc import Sequence


class World:
    """A complete in-memory Byte: scripted model, real use case, runner, tools and store."""

    def __init__(
        self,
        turns: Sequence[ModelTurn],
        *,
        max_steps: int = 6,
        history_limit: int = 20,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.light = InMemoryLight()
        self.calendar = InMemoryCalendar()
        self.store = InMemoryConversationStore()
        self.pending = PendingActionStore(FakeClock())
        self.log = RecordingLogger()
        registry = build_tool_registry(
            self.light, InMemoryClimate(), InMemoryMusic(), self.calendar, InMemoryExpenses()
        )
        self.runner = ToolRunner(registry, self.pending, self.log)
        self.model = ScriptedChatModel(turns)
        self.chat = ProcessChatMessage(
            self.model,
            self.store,
            self.runner,
            self.pending,
            self.log,
            max_steps=max_steps,
            history_limit=history_limit,
            timeout_seconds=timeout_seconds,
        )


def tool_turn(name: str, arguments: str = "{}", call_id: str = "call-1") -> ModelTurn:
    return ModelTurn(text="", tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),))


def text_turn(text: str) -> ModelTurn:
    return ModelTurn(text=text)
```

- [ ] **Step 3: Create `tests/unit/application/use_cases/test_process_chat_message.py`**

Create `tests/unit/application/use_cases/test_process_chat_message.py`:

```python
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.application.use_cases.process_chat_message import ProcessChatMessage
from app.domain.entities import Message
from app.domain.exceptions import AgentError
from app.domain.model import ModelMessage, ModelTurn
from app.ports.chat_model import ChatModelPort
from tests.fakes.events import events_on_day, seed_event
from tests.fakes.logger import RecordingLogger
from tests.fakes.world import World, text_turn, tool_turn

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.tools import ToolSpec

CID = "c1"


@pytest.mark.unit
async def test_plain_reply_is_returned_and_persisted() -> None:
    world = World([text_turn("Oi!")])
    reply = await world.chat.execute(CID, "olá", None)

    assert reply.message.role == "assistant"
    assert reply.message.content == "Oi!"
    assert reply.pending_summary is None
    stored = await world.store.recent(CID, 20)
    assert [(m.role, m.content) for m in stored] == [("user", "olá"), ("assistant", "Oi!")]
    messages, tools = world.model.calls[0]
    assert [m.role for m in messages] == ["system", "user"]
    assert "confirm_action" in [t.name for t in tools]


@pytest.mark.unit
async def test_tool_loop_feeds_results_back_but_never_persists_them() -> None:
    world = World([tool_turn("list_lights"), text_turn("A lâmpada está desligada.")])
    reply = await world.chat.execute(CID, "o que está ligado?", None)

    assert reply.message.content == "A lâmpada está desligada."
    second_call_messages, _ = world.model.calls[1]
    assert [m.role for m in second_call_messages] == ["system", "user", "assistant", "tool"]
    assert second_call_messages[-1].content == (
        "lampada: desligada, modo white, brilho 100%, temperatura de cor 50%"
    )
    assert second_call_messages[-1].tool_call_id == "call-1"
    stored = await world.store.recent(CID, 20)
    assert [m.role for m in stored] == ["user", "assistant"]


@pytest.mark.unit
async def test_only_the_last_n_messages_reach_the_model() -> None:
    world = World([text_turn("ok")], history_limit=20)
    now = datetime.now(tz=UTC)
    old = [Message(id=f"m{i}", role="user", content=f"old {i}", timestamp=now) for i in range(30)]
    await world.store.append(CID, old)

    await world.chat.execute(CID, "novo", None)

    messages, _ = world.model.calls[0]
    assert len(messages) == 1 + 20 + 1
    assert messages[1].content == "old 10"
    assert messages[-1].content == "novo"


@pytest.mark.unit
async def test_segment_filter_limits_the_tools_offered() -> None:
    world = World([text_turn("ok")])
    await world.chat.execute(CID, "oi", "finance")
    _, tools = world.model.calls[0]
    assert {t.segment for t in tools} == {"finance", "*"}


@pytest.mark.unit
async def test_step_limit_raises_agent_error() -> None:
    world = World([tool_turn("list_lights") for _ in range(3)], max_steps=3)
    with pytest.raises(AgentError, match="step limit"):
        await world.chat.execute(CID, "oi", None)
    assert await world.store.recent(CID, 20) == ()


@pytest.mark.unit
async def test_empty_model_text_raises_agent_error() -> None:
    world = World([text_turn("   ")])
    with pytest.raises(AgentError, match="no text"):
        await world.chat.execute(CID, "oi", None)


@pytest.mark.unit
async def test_timeout_raises_agent_error() -> None:
    class Hanging(ChatModelPort):
        async def complete(
            self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
        ) -> ModelTurn:
            await asyncio.sleep(10)
            return ModelTurn(text="never")

    world = World([], timeout_seconds=0.01)
    chat = ProcessChatMessage(
        Hanging(), world.store, world.runner, world.pending, RecordingLogger(), timeout_seconds=0.01
    )
    with pytest.raises(AgentError, match="timed out"):
        await chat.execute(CID, "oi", None)


DELETE = '{"event_id": "evt-1"}'


@pytest.mark.unit
async def test_confirmation_round_trip_across_two_requests() -> None:
    world = World(
        [
            tool_turn("delete_event", DELETE),
            text_turn("Apagar o evento evt-1. Posso?"),
            tool_turn("confirm_action", call_id="call-2"),
            text_turn("Pronto, apaguei."),
        ]
    )
    await seed_event(world.calendar)

    first = await world.chat.execute(CID, "apaga o dentista", None)
    assert first.pending_summary == "Apagar o evento evt-1"
    assert len(await events_on_day(world.calendar)) == 1

    second = await world.chat.execute(CID, "sim", None)
    assert second.pending_summary is None
    assert await events_on_day(world.calendar) == ()
    system_prompt = world.model.calls[2][0][0].content
    assert "Apagar o evento evt-1" in system_prompt


@pytest.mark.unit
async def test_an_unrelated_message_in_between_cancels_the_pending_action() -> None:
    world = World(
        [
            tool_turn("delete_event", DELETE),
            text_turn("Apagar o evento evt-1. Posso?"),
            text_turn("São três horas."),
            tool_turn("confirm_action", call_id="call-2"),
            text_turn("Não há nada para confirmar."),
        ]
    )
    await seed_event(world.calendar)
    await world.chat.execute(CID, "apaga o dentista", None)
    await world.chat.execute(CID, "que horas são", None)
    await world.chat.execute(CID, "sim", None)

    assert len(await events_on_day(world.calendar)) == 1
    tool_message = world.model.calls[4][0][-1]
    assert tool_message.role == "tool"
    assert tool_message.content == "erro: nada para confirmar"


@pytest.mark.unit
async def test_the_model_cannot_confirm_in_the_same_request() -> None:
    world = World(
        [
            tool_turn("delete_event", DELETE),
            tool_turn("confirm_action", call_id="call-2"),
            text_turn("Apagar o evento evt-1. Posso?"),
        ]
    )
    await seed_event(world.calendar)
    reply = await world.chat.execute(CID, "apaga o dentista", None)

    assert len(await events_on_day(world.calendar)) == 1
    assert reply.pending_summary == "Apagar o evento evt-1"
    refused: ModelMessage = world.model.calls[2][0][-1]
    assert refused.content.startswith("erro: aguarde")
```

- [ ] **Step 4: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/application/use_cases/test_process_chat_message.py -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 5: Create `app/ports/chat_model.py`**

Create `app/ports/chat_model.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.model import ModelMessage, ModelTurn
    from app.domain.tools import ToolSpec


class ChatModelPort(ABC):
    """One model call: a transcript and the available tools in, text or tool calls out."""

    @abstractmethod
    async def complete(
        self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn: ...
```

- [ ] **Step 6: Create `app/application/prompts.py`**

Create `app/application/prompts.py`:

```python
from __future__ import annotations

SYSTEM_PROMPT = (
    "Você é o Byte, assistente pessoal de uma única pessoa. "
    "Responda em português do Brasil, em frases curtas, sem markdown, listas ou emojis: "
    "a resposta pode ser falada em voz alta. "
    "Use as ferramentas para agir; nunca invente o resultado de uma ação. "
    "Ações sensíveis pedem confirmação: a ferramenta devolve needs_confirmation, "
    "você lê o resumo ao usuário palavra por palavra e espera. "
    "Só chame confirm_action depois que o usuário responder."
)
```

- [ ] **Step 7: Create `app/application/use_cases/process_chat_message.py`**

Create `app/application/use_cases/process_chat_message.py`:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from app.application.prompts import SYSTEM_PROMPT
from app.domain.entities import Message
from app.domain.exceptions import AgentError
from app.domain.model import ModelMessage

if TYPE_CHECKING:
    from app.application.pending_actions import PendingActionStore
    from app.application.tool_runner import ToolRunner
    from app.ports.chat_model import ChatModelPort
    from app.ports.conversation_store import ConversationStorePort
    from app.ports.logger import LoggerPort


@dataclass(frozen=True, slots=True)
class ChatReply:
    message: Message
    pending_summary: str | None


def _role(role: str) -> Literal["user", "assistant"]:
    return "assistant" if role == "assistant" else "user"


class ProcessChatMessage:
    """One chat request: history + new text -> model/tool loop -> reply, then persist."""

    def __init__(
        self,
        model: ChatModelPort,
        store: ConversationStorePort,
        runner: ToolRunner,
        pending: PendingActionStore,
        log: LoggerPort,
        *,
        max_steps: int = 6,
        history_limit: int = 20,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._model = model
        self._store = store
        self._runner = runner
        self._pending = pending
        self._log = log
        self._max_steps = max_steps
        self._history_limit = history_limit
        self._timeout = timeout_seconds

    async def execute(self, conversation_id: str, text: str, segment: str | None) -> ChatReply:
        try:
            return await asyncio.wait_for(self._run(conversation_id, text, segment), self._timeout)
        except TimeoutError as exc:
            raise AgentError("chat request timed out") from exc

    async def _run(self, conversation_id: str, text: str, segment: str | None) -> ChatReply:
        self._pending.on_user_utterance(conversation_id, text)
        user_msg = Message(
            id=str(uuid4()), role="user", content=text, timestamp=datetime.now(tz=UTC)
        )
        history = await self._store.recent(conversation_id, self._history_limit)
        messages = [
            ModelMessage(role="system", content=self._system_prompt(conversation_id)),
            *(ModelMessage(role=_role(m.role), content=m.content) for m in history),
            ModelMessage(role="user", content=text),
        ]
        tools = self._runner.specs(segment)
        self._log.info("chat.start", conversation_id=conversation_id)

        for _ in range(self._max_steps):
            turn = await self._model.complete(messages, tools)
            if not turn.tool_calls:
                return await self._finish(conversation_id, user_msg, turn.text)
            messages.append(
                ModelMessage(role="assistant", content=turn.text, tool_calls=turn.tool_calls)
            )
            for call in turn.tool_calls:
                result = await self._runner.run(call, conversation_id, segment)
                messages.append(
                    ModelMessage(role="tool", content=result.output, tool_call_id=result.call_id)
                )
        raise AgentError("tool loop exceeded the step limit")

    def _system_prompt(self, conversation_id: str) -> str:
        action = self._pending.peek(conversation_id)
        if action is None or not action.armed:
            return SYSTEM_PROMPT
        return (
            f"{SYSTEM_PROMPT} Há uma ação pendente de confirmação: {action.summary}. "
            "Se a fala do usuário a confirmar, chame confirm_action."
        )

    async def _finish(self, conversation_id: str, user_msg: Message, text: str) -> ChatReply:
        if not text.strip():
            raise AgentError("model returned no text")
        assistant_msg = Message(
            id=str(uuid4()), role="assistant", content=text, timestamp=datetime.now(tz=UTC)
        )
        await self._store.append(conversation_id, (user_msg, assistant_msg))
        action = self._pending.peek(conversation_id)
        summary = action.summary if action is not None and not action.armed else None
        self._log.info("chat.done", conversation_id=conversation_id)
        return ChatReply(message=assistant_msg, pending_summary=summary)
```

- [ ] **Step 8: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/application/use_cases/test_process_chat_message.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/ports/chat_model.py \
  app/application/prompts.py \
  app/application/use_cases/process_chat_message.py \
  tests/fakes \
  tests/unit/application/use_cases/test_process_chat_message.py
git commit -m "feat(application): add ChatModelPort and the ProcessChatMessage tool loop"
```

### Task 7: OpenAI chat adapter

**Files:**
- Create: `app/adapters/openai/__init__.py`, `app/adapters/openai/chat_model.py`
- Test: `tests/unit/adapters/test_openai_chat_conversion.py`, `tests/integration/test_openai_chat.py`

**Interfaces:**
- Consumes: `ChatModelPort`, `ModelMessage`, `ModelTurn`, `ToolSpec`, `ToolCall`, `AgentError`; the `openai` SDK (>= 2.35).
- Produces: `OpenAIChatModel(client: AsyncOpenAI, model: str)`, plus the pure functions `to_openai_messages` and `to_openai_tools`.

The OpenAI SDK appears in `adapters/openai/` and nowhere else. `parallel_tool_calls=False` keeps one tool call per step. SDK errors become `AgentError` carrying the exception type and HTTP status, never the request content. The SDK's default retries (2) cover 429/5xx.

The integration test hits the real API and skips itself without `BYTE_OPENAI_API_KEY`; it is excluded from the default run once Task 8 lands.

- [ ] **Step 1: Create `tests/unit/adapters/test_openai_chat_conversion.py`**

Create `tests/unit/adapters/test_openai_chat_conversion.py`:

```python
from __future__ import annotations

import pytest

from app.adapters.openai.chat_model import to_openai_messages, to_openai_tools
from app.domain.model import ModelMessage
from app.domain.tools import ToolCall, ToolSpec


@pytest.mark.unit
def test_messages_map_every_role() -> None:
    call = ToolCall(id="call-1", name="list_lights", arguments="{}")
    messages = [
        ModelMessage(role="system", content="sys"),
        ModelMessage(role="user", content="oi"),
        ModelMessage(role="assistant", content="", tool_calls=(call,)),
        ModelMessage(role="tool", content="lampada: ligada", tool_call_id="call-1"),
        ModelMessage(role="assistant", content="pronto"),
    ]

    assert to_openai_messages(messages) == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "oi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {"name": "list_lights", "arguments": "{}"},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": "lampada: ligada"},
        {"role": "assistant", "content": "pronto"},
    ]


@pytest.mark.unit
def test_tools_become_function_tools() -> None:
    spec = ToolSpec(
        name="set_light",
        description="Liga.",
        parameters={"type": "object", "properties": {}},
        segment="home",
    )

    assert to_openai_tools([spec]) == [
        {
            "type": "function",
            "function": {
                "name": "set_light",
                "description": "Liga.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
```

- [ ] **Step 2: Create `tests/integration/test_openai_chat.py`**

Create `tests/integration/test_openai_chat.py`:

```python
from __future__ import annotations

import os

import pytest
from openai import AsyncOpenAI

from app.adapters.openai.chat_model import OpenAIChatModel
from app.domain.model import ModelMessage
from app.domain.tools import ToolSpec

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("BYTE_OPENAI_API_KEY"), reason="needs BYTE_OPENAI_API_KEY"
    ),
]

MODEL = os.environ.get("BYTE_CHAT_MODEL", "gpt-4.1-mini")


def adapter() -> OpenAIChatModel:
    return OpenAIChatModel(AsyncOpenAI(api_key=os.environ["BYTE_OPENAI_API_KEY"]), MODEL)


async def test_plain_answer() -> None:
    turn = await adapter().complete(
        [ModelMessage(role="user", content="Responda apenas com a palavra: ok")], []
    )
    assert turn.text.strip()
    assert turn.tool_calls == ()


async def test_model_calls_a_tool() -> None:
    spec = ToolSpec(
        name="set_light",
        description="Liga um dispositivo da casa.",
        parameters={
            "type": "object",
            "properties": {"name": {"type": "string", "description": "Nome do dispositivo."}},
            "required": ["name"],
            "additionalProperties": False,
        },
        segment="home",
    )
    turn = await adapter().complete(
        [ModelMessage(role="user", content="Liga a luz da sala, por favor.")], [spec]
    )
    assert [c.name for c in turn.tool_calls] == ["set_light"]
```

- [ ] **Step 3: Run the tests and watch them fail**

```bash
python -m pytest tests/unit/adapters/test_openai_chat_conversion.py -q --no-cov
```

Expected: FAIL — collection error (`ModuleNotFoundError`/`ImportError`): the new code does not exist yet.

- [ ] **Step 4: Create `app/adapters/openai/__init__.py`**

Create the empty file `app/adapters/openai/__init__.py`.

- [ ] **Step 5: Create `app/adapters/openai/chat_model.py`**

Create `app/adapters/openai/chat_model.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from openai import APIStatusError, OpenAIError, omit

from app.domain.exceptions import AgentError
from app.domain.model import ModelTurn
from app.domain.tools import ToolCall
from app.ports.chat_model import ChatModelPort

if TYPE_CHECKING:
    from collections.abc import Sequence

    from openai import AsyncOpenAI
    from openai.types.chat import ChatCompletionMessageParam, ChatCompletionToolParam

    from app.domain.model import ModelMessage
    from app.domain.tools import ToolSpec


def to_openai_messages(messages: Sequence[ModelMessage]) -> list[ChatCompletionMessageParam]:
    out: list[ChatCompletionMessageParam] = []
    for m in messages:
        if m.role == "tool":
            out.append({"role": "tool", "tool_call_id": m.tool_call_id or "", "content": m.content})
        elif m.role == "assistant" and m.tool_calls:
            out.append(
                {
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": c.arguments},
                        }
                        for c in m.tool_calls
                    ],
                }
            )
        elif m.role == "assistant":
            out.append({"role": "assistant", "content": m.content})
        elif m.role == "system":
            out.append({"role": "system", "content": m.content})
        else:
            out.append({"role": "user", "content": m.content})
    return out


def to_openai_tools(tools: Sequence[ToolSpec]) -> list[ChatCompletionToolParam]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": dict(t.parameters),
            },
        }
        for t in tools
    ]


class OpenAIChatModel(ChatModelPort):
    """Chat Completions with function tools. The OpenAI SDK never leaves this module."""

    def __init__(self, client: AsyncOpenAI, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(
        self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=to_openai_messages(messages),
                tools=to_openai_tools(tools) if tools else omit,
                parallel_tool_calls=False if tools else omit,
            )
        except OpenAIError as exc:
            status = exc.status_code if isinstance(exc, APIStatusError) else None
            raise AgentError(f"model call failed: {type(exc).__name__} status={status}") from exc
        if not response.choices:
            raise AgentError("model returned no choices")
        message = response.choices[0].message
        calls = tuple(
            ToolCall(id=c.id, name=c.function.name, arguments=c.function.arguments)
            for c in message.tool_calls or ()
            if c.type == "function"
        )
        return ModelTurn(text=message.content or "", tool_calls=calls)
```

- [ ] **Step 6: Run the tests and watch them pass**

```bash
python -m pytest tests/unit/adapters/test_openai_chat_conversion.py -q --no-cov
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/adapters/openai \
  tests/unit/adapters/test_openai_chat_conversion.py \
  tests/integration/test_openai_chat.py
git commit -m "feat(adapters): add OpenAI chat adapter behind ChatModelPort"
```

### Task 8: Switch the API to the new core, merge your device settings, remove the Agno stack

**Files:**
- Delete: `app/adapters/agent/`, `app/adapters/repository/`, `app/ports/agent.py`, `app/ports/repository.py`, `app/application/use_cases/process_incoming_message.py` and their tests
- Replace (merging your device work): `app/config.py`, `app/api/deps.py`, `app/domain/exceptions.py`, `pyproject.toml`, `.env.example`
- Replace: `app/domain/entities.py`, `app/adapters/logging/structlog_logger.py`, `app/api/schemas.py`, `app/api/router.py`, `main.py`, `tests/fakes/world.py`
- Create: `app/api/auth.py`, `app/api/errors.py`, `tests/conftest.py`
- Test: `tests/unit/domain/test_entities.py`, `tests/unit/domain/test_exceptions.py`, `tests/unit/test_config.py`, `tests/unit/test_config_devices.py`, `tests/unit/test_main.py`, `tests/unit/api/test_auth.py`, `tests/unit/api/test_router.py`, `tests/unit/api/test_deps.py`, `tests/unit/adapters/test_structlog_logger.py`
- Modify: `Dockerfile` (extras), `tests/integration/test_tuya_light.py` (does not need the API token any more)

**Interfaces:**
- Consumes: everything built in Tasks 1-7, plus your `TuyaLightSettings`, ThinQ/Spotify settings and the three device adapters.
- Produces: `Settings` / `load_settings()` (raises `ConfigError` naming bad fields, never values; blank env vars count as unset), `configure_logging(level, *, json)`, `token_matches` / `require_token`, `install_error_handlers`, `deps.get_light / get_climate / get_music` (the real adapter when configured, the in-memory one otherwise) and the other `deps.get_*` singletons plus `get_process_chat`, `POST /api/v1/messages` (auth, limits, 404 on unknown segment, `pending_confirmation`), `GET /api/v1/health`, and `main.app` whose lifespan validates the config at boot, logs which adapter drives each device group, and drains running tools at shutdown.

This is the only task that cannot be split: the old `deps.py`, router, config and tests all depend on the Agno stack, so they switch together. **Do not run the suite between the first step and the last write step**: it is red by design while the old and new halves are mixed.

What the merge keeps from your work: `TuyaLightSettings`, the `thinq_*`, `tuya_lights` and `spotify_*` settings, the six device errors, the `thinq`/`tuya`/`spotify` extras and their `.env.example` blocks, and the lazy imports of the real adapters. What it changes: `get_light()`, `get_climate()` and `get_music()` no longer raise when a device is unconfigured; they fall back to your `InMemory*` adapter, and the boot log (`adapters.selected`) says which adapter is live, so a missing variable is visible, not silent. `env_ignore_empty` makes a blank `BYTE_TUYA_LIGHTS=` mean "unset" (the old `.env.example` would otherwise fail to parse). Review `git diff` of those five files when the task is done.

What changes for a caller: every route except `/health` needs `Authorization: Bearer <token>`; `content` is 1-4,000 characters; `conversation_id` must match `^[A-Za-z0-9_-]{1,64}$`; the process refuses to boot without a 32+ character `BYTE_API_TOKEN` and a non-empty `BYTE_OPENAI_API_KEY`; all settings, including the keys, use the `BYTE_` prefix.

- [ ] **Step 1: Remove the files this task replaces**

```bash
git rm -r app/adapters/agent \
  app/adapters/repository \
  app/ports/agent.py \
  app/ports/repository.py \
  app/application/use_cases/process_incoming_message.py \
  tests/integration/test_agno_agent.py \
  tests/unit/adapters/test_model_tiers.py \
  tests/unit/application/use_cases/test_process_incoming_message.py \
  tests/unit/api/test_deps.py \
  tests/unit/api/test_router.py
```

- [ ] **Step 2: Replace `tests/fakes/world.py`**

Replace `tests/fakes/world.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.use_cases.process_chat_message import ProcessChatMessage
from app.config import Settings
from app.domain.model import ModelTurn
from app.domain.tools import ToolCall
from tests.fakes.chat_model import ScriptedChatModel
from tests.fakes.clock import FakeClock
from tests.fakes.logger import RecordingLogger

if TYPE_CHECKING:
    from collections.abc import Sequence

TOKEN = "t" * 32


def make_settings() -> Settings:
    return Settings.model_validate({"api_token": TOKEN, "openai_api_key": "sk-test"})


class World:
    """A complete in-memory Byte: scripted model, real use case, runner, tools and store."""

    def __init__(
        self,
        turns: Sequence[ModelTurn],
        *,
        max_steps: int = 6,
        history_limit: int = 20,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.light = InMemoryLight()
        self.calendar = InMemoryCalendar()
        self.store = InMemoryConversationStore()
        self.pending = PendingActionStore(FakeClock())
        self.log = RecordingLogger()
        registry = build_tool_registry(
            self.light, InMemoryClimate(), InMemoryMusic(), self.calendar, InMemoryExpenses()
        )
        self.runner = ToolRunner(registry, self.pending, self.log)
        self.model = ScriptedChatModel(turns)
        self.chat = ProcessChatMessage(
            self.model,
            self.store,
            self.runner,
            self.pending,
            self.log,
            max_steps=max_steps,
            history_limit=history_limit,
            timeout_seconds=timeout_seconds,
        )


def tool_turn(name: str, arguments: str = "{}", call_id: str = "call-1") -> ModelTurn:
    return ModelTurn(text="", tool_calls=(ToolCall(id=call_id, name=name, arguments=arguments),))


def text_turn(text: str) -> ModelTurn:
    return ModelTurn(text=text)
```

- [ ] **Step 3: Create `tests/conftest.py`**

Create `tests/conftest.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.api import deps

if TYPE_CHECKING:
    from collections.abc import Iterator

_CACHED = (
    deps.get_settings,
    deps.get_logger,
    deps.get_store,
    deps.get_pending,
    deps.get_light,
    deps.get_climate,
    deps.get_music,
    deps.get_calendar,
    deps.get_expenses,
    deps.get_tools,
    deps.get_runner,
    deps.get_openai,
    deps.get_chat_model,
)


@pytest.fixture(autouse=True)
def clear_dependency_caches() -> Iterator[None]:
    """`lru_cache` singletons must not leak between tests."""
    for fn in _CACHED:
        fn.cache_clear()
    yield
    for fn in _CACHED:
        fn.cache_clear()
```

- [ ] **Step 4: Create `tests/unit/domain/test_entities.py`**

Create `tests/unit/domain/test_entities.py`:

```python
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from app.domain.entities import Message

NOW = datetime.now(tz=UTC)


def test_message_fields() -> None:
    msg = Message(id="1", role="user", content="hello", timestamp=NOW)
    assert msg.id == "1"
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.timestamp == NOW


def test_message_is_frozen() -> None:
    msg = Message(id="1", role="user", content="hello", timestamp=NOW)
    with pytest.raises(FrozenInstanceError):
        msg.content = "changed"  # type: ignore[misc]
```

- [ ] **Step 5: Create `tests/unit/domain/test_exceptions.py`**

Create `tests/unit/domain/test_exceptions.py`:

```python
from __future__ import annotations

import pytest

from app.domain.exceptions import (
    AgentError,
    ClimateError,
    ConfigError,
    DomainError,
    EventNotFoundError,
    LightError,
    LiveSessionError,
    MusicError,
    RegistryDuplicateError,
    RegistryError,
    RegistryKeyError,
    ToolArgumentError,
    UnknownClimateDeviceError,
    UnknownLightDeviceError,
    UnknownMusicDeviceError,
)


def test_domain_error_is_exception() -> None:
    assert issubclass(DomainError, Exception)


def test_domain_error_can_be_raised() -> None:
    with pytest.raises(DomainError):
        raise DomainError("something went wrong")


def test_registry_error_is_domain_error() -> None:
    assert issubclass(RegistryError, DomainError)


def test_registry_duplicate_error_is_registry_error() -> None:
    assert issubclass(RegistryDuplicateError, RegistryError)


def test_registry_key_error_is_registry_error() -> None:
    assert issubclass(RegistryKeyError, RegistryError)


@pytest.mark.parametrize(
    "error",
    [
        AgentError,
        LiveSessionError,
        ConfigError,
        ToolArgumentError,
        EventNotFoundError,
        ClimateError,
        LightError,
        MusicError,
    ],
)
def test_other_errors_are_domain_errors(error: type[DomainError]) -> None:
    assert issubclass(error, DomainError)


@pytest.mark.parametrize(
    ("unknown", "base"),
    [
        (UnknownClimateDeviceError, ClimateError),
        (UnknownLightDeviceError, LightError),
        (UnknownMusicDeviceError, MusicError),
    ],
)
def test_unknown_device_errors_specialise_their_group(
    unknown: type[DomainError], base: type[DomainError]
) -> None:
    assert issubclass(unknown, base)
```

- [ ] **Step 6: Create `tests/unit/test_config.py`**

Create `tests/unit/test_config.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.config import MIN_TOKEN_LENGTH, load_settings
from app.domain.exceptions import ConfigError

if TYPE_CHECKING:
    from pathlib import Path

GOOD_TOKEN = "k" * MIN_TOKEN_LENGTH


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """No .env in the working directory and no BYTE_* variables from the machine."""
    monkeypatch.chdir(tmp_path)
    for name in ("BYTE_API_TOKEN", "BYTE_OPENAI_API_KEY", "BYTE_CHAT_MODEL", "BYTE_LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_valid_environment_loads_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    settings = load_settings()
    assert settings.api_token.get_secret_value() == GOOD_TOKEN
    assert settings.chat_model == "gpt-4.1-mini"
    assert settings.log_level == "INFO"


@pytest.mark.unit
def test_short_token_refuses_to_boot_without_echoing_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "short-secret")
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with pytest.raises(ConfigError) as info:
        load_settings()
    assert "api_token" in str(info.value)
    assert "short-secret" not in str(info.value)


@pytest.mark.unit
def test_empty_openai_key_refuses_to_boot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "")
    with pytest.raises(ConfigError, match="openai_api_key"):
        load_settings()


@pytest.mark.unit
def test_missing_secrets_are_named(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ConfigError) as info:
        load_settings()
    assert "api_token" in str(info.value)
    assert "openai_api_key" in str(info.value)


@pytest.mark.unit
def test_unknown_log_level_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BYTE_LOG_LEVEL", "LOUD")
    with pytest.raises(ConfigError, match="log_level"):
        load_settings()
```

- [ ] **Step 7: Create `tests/unit/test_config_devices.py`**

Create `tests/unit/test_config_devices.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.config import load_settings

if TYPE_CHECKING:
    from pathlib import Path

GOOD_TOKEN = "k" * 32


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A valid core config, no .env in the working directory and no device configured."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BYTE_API_TOKEN", GOOD_TOKEN)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    for name in ("BYTE_TUYA_LIGHTS", "BYTE_THINQ_ACCESS_SECRET", "BYTE_SPOTIFY_CLIENT_ID"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_devices_default_to_unset() -> None:
    settings = load_settings()
    assert settings.tuya_lights == {}
    assert settings.thinq_access_secret is None
    assert settings.spotify_client_id is None


@pytest.mark.unit
def test_blank_device_variables_are_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_TUYA_LIGHTS", "")
    monkeypatch.setenv("BYTE_THINQ_ACCESS_SECRET", "")
    settings = load_settings()
    assert settings.tuya_lights == {}
    assert settings.thinq_access_secret is None


@pytest.mark.unit
def test_tuya_lights_are_read_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "BYTE_TUYA_LIGHTS",
        '{"lampada": {"device_id": "d", "address": "192.168.0.5", "local_key": "k"}}',
    )
    lamp = load_settings().tuya_lights["lampada"]
    assert (lamp.device_id, lamp.address, lamp.version) == ("d", "192.168.0.5", 3.3)
    assert lamp.local_key.get_secret_value() == "k"
```

- [ ] **Step 8: Create `tests/unit/test_main.py`**

Create `tests/unit/test_main.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.domain.exceptions import ConfigError
from main import app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("BYTE_API_TOKEN", raising=False)
    monkeypatch.delenv("BYTE_OPENAI_API_KEY", raising=False)


@pytest.mark.unit
def test_app_boots_with_a_valid_config_and_guards_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "k" * 32)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.post("/api/v1/messages", json={"content": "oi"}).status_code == 401


@pytest.mark.unit
def test_app_refuses_to_boot_with_a_bad_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_API_TOKEN", "too-short")
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    with pytest.raises(ConfigError), TestClient(app):
        pass
```

- [ ] **Step 9: Create `tests/unit/api/test_auth.py`**

Create `tests/unit/api/test_auth.py`:

```python
from __future__ import annotations

import pytest
from pydantic import SecretStr

from app.api.auth import token_matches

TOKEN = SecretStr("s" * 32)


@pytest.mark.unit
def test_exact_bearer_token_matches() -> None:
    assert token_matches("Bearer " + "s" * 32, TOKEN) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "s" * 32,
        "bearer " + "s" * 32,
        "Bearer " + "s" * 31,
        "Bearer " + "s" * 33,
        "Bearer ",
        "Basic " + "s" * 32,
    ],
)
def test_anything_else_is_rejected(header: str | None) -> None:
    assert token_matches(header, TOKEN) is False
```

- [ ] **Step 10: Create `tests/unit/api/test_router.py`**

Create `tests/unit/api/test_router.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_process_chat, get_runner, get_settings
from app.api.errors import install_error_handlers
from app.api.router import router
from app.domain.exceptions import AgentError, UnknownLightDeviceError
from tests.fakes.world import TOKEN, World, make_settings, text_turn, tool_turn

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.domain.model import ModelTurn

AUTH = {"Authorization": f"Bearer {TOKEN}"}
URL = "/api/v1/messages"


class ExplodingChat:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def execute(self, conversation_id: str, text: str, segment: str | None) -> object:
        raise self._error


def make_client(turns: Sequence[ModelTurn] = ()) -> tuple[TestClient, World]:
    world = World(turns)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    install_error_handlers(app)
    app.dependency_overrides[get_settings] = make_settings
    app.dependency_overrides[get_process_chat] = lambda: world.chat
    app.dependency_overrides[get_runner] = lambda: world.runner
    return TestClient(app), world


@pytest.mark.unit
def test_health_needs_no_token() -> None:
    client, _ = make_client()
    assert client.get("/api/v1/health").json() == {"status": "ok"}


@pytest.mark.unit
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}, {"Authorization": "Basic x"}],
)
def test_messages_require_the_bearer_token(headers: dict[str, str]) -> None:
    client, world = make_client([text_turn("não deveria rodar")])
    res = client.post(URL, json={"content": "oi"}, headers=headers)
    assert res.status_code == 401
    assert world.model.calls == []


@pytest.mark.unit
def test_reply_shape_and_generated_conversation_id() -> None:
    client, _ = make_client([text_turn("Oi!")])
    res = client.post(URL, json={"content": "olá"}, headers=AUTH)
    assert res.status_code == 200
    body = res.json()
    assert body["role"] == "assistant"
    assert body["content"] == "Oi!"
    assert body["conversation_id"]
    assert body["pending_confirmation"] is None


@pytest.mark.unit
def test_the_same_conversation_id_continues_the_history() -> None:
    client, world = make_client([text_turn("um"), text_turn("dois")])
    body = {"content": "oi", "conversation_id": "conv-1"}
    first = client.post(URL, json=body, headers=AUTH).json()
    client.post(URL, json=body, headers=AUTH)
    assert first["conversation_id"] == "conv-1"
    second_call_messages, _ = world.model.calls[1]
    assert [m.role for m in second_call_messages] == ["system", "user", "assistant", "user"]


@pytest.mark.unit
@pytest.mark.parametrize("segment", ["home", "HOME", "auto", " Agenda "])
def test_known_segments_and_auto_are_accepted(segment: str) -> None:
    client, _ = make_client([text_turn("ok")])
    res = client.post(URL, json={"content": "oi", "segment": segment}, headers=AUTH)
    assert res.status_code == 200


@pytest.mark.unit
def test_unknown_segment_is_404_and_never_falls_back() -> None:
    client, world = make_client([text_turn("não deveria rodar")])
    res = client.post(URL, json={"content": "oi", "segment": "nope"}, headers=AUTH)
    assert res.status_code == 404
    assert world.model.calls == []


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"content": ""},
        {"content": "    "},
        {"content": "x" * 4001},
        {"content": "oi", "conversation_id": "../etc/passwd"},
        {"content": "oi", "conversation_id": "a" * 65},
    ],
)
def test_invalid_payloads_are_422(payload: dict[str, str]) -> None:
    client, world = make_client([text_turn("não deveria rodar")])
    res = client.post(URL, json=payload, headers=AUTH)
    assert res.status_code == 422
    assert world.model.calls == []


@pytest.mark.unit
def test_content_at_the_limit_is_accepted() -> None:
    client, _ = make_client([text_turn("ok")])
    res = client.post(URL, json={"content": "x" * 4000}, headers=AUTH)
    assert res.status_code == 200


@pytest.mark.unit
def test_pending_confirmation_summary_is_returned_verbatim() -> None:
    client, _ = make_client(
        [
            tool_turn("delete_event", '{"event_id": "evt-1"}'),
            text_turn("Quer que eu desligue?"),
        ]
    )
    res = client.post(URL, json={"content": "apaga o dentista"}, headers=AUTH)
    assert res.json()["pending_confirmation"] == {"summary": "Apagar o evento evt-1"}


@pytest.mark.unit
def test_agent_error_is_502_without_leaking_the_cause() -> None:
    client, _ = make_client()
    exploding = ExplodingChat(AgentError("secret upstream detail"))
    client.app.dependency_overrides[get_process_chat] = lambda: exploding  # type: ignore[attr-defined]
    res = client.post(URL, json={"content": "oi"}, headers=AUTH)
    assert res.status_code == 502
    assert res.json() == {"detail": "Agent failed to produce a reply"}


@pytest.mark.unit
def test_other_domain_errors_are_a_generic_500() -> None:
    client, _ = make_client()
    exploding = ExplodingChat(UnknownLightDeviceError("cofre"))
    client.app.dependency_overrides[get_process_chat] = lambda: exploding  # type: ignore[attr-defined]
    res = client.post(URL, json={"content": "oi"}, headers=AUTH)
    assert res.status_code == 500
    assert res.json() == {"detail": "Internal error"}
```

- [ ] **Step 11: Create `tests/unit/api/test_deps.py`**

Create `tests/unit/api/test_deps.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.adapters.spotify.spotify_music import SpotifyMusic
from app.adapters.thinq.thinq_climate import ThinQClimate
from app.adapters.tuya.tuya_light import TuyaLight
from app.api import deps

if TYPE_CHECKING:
    from pathlib import Path

LAMP = '{"lampada": {"device_id": "d", "address": "192.168.0.5", "local_key": "k", "version": 3.3}}'
DEVICE_VARIABLES = (
    "BYTE_TUYA_LIGHTS",
    "BYTE_THINQ_ACCESS_SECRET",
    "BYTE_SPOTIFY_CLIENT_ID",
    "BYTE_SPOTIFY_REFRESH_TOKEN",
)


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A valid core config, no .env in the working directory and no device configured."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BYTE_API_TOKEN", "k" * 32)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    for name in DEVICE_VARIABLES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.unit
def test_unconfigured_devices_run_against_the_in_memory_adapters() -> None:
    assert isinstance(deps.get_light(), InMemoryLight)
    assert isinstance(deps.get_climate(), InMemoryClimate)
    assert isinstance(deps.get_music(), InMemoryMusic)


@pytest.mark.unit
def test_configured_lamps_select_the_tuya_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_TUYA_LIGHTS", LAMP)
    assert isinstance(deps.get_light(), TuyaLight)


@pytest.mark.unit
def test_a_thinq_token_selects_the_thinq_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BYTE_THINQ_ACCESS_SECRET", "token")
    assert isinstance(deps.get_climate(), ThinQClimate)


@pytest.mark.unit
def test_spotify_needs_both_the_client_id_and_the_refresh_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BYTE_SPOTIFY_CLIENT_ID", "client")
    assert isinstance(deps.get_music(), InMemoryMusic)
    deps.get_settings.cache_clear()
    deps.get_music.cache_clear()
    monkeypatch.setenv("BYTE_SPOTIFY_REFRESH_TOKEN", "refresh")
    assert isinstance(deps.get_music(), SpotifyMusic)


@pytest.mark.unit
def test_the_tool_registry_uses_whatever_adapters_were_selected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BYTE_TUYA_LIGHTS", LAMP)
    names = {t.spec.name for t in deps.get_tools().values()}
    assert {"set_light", "set_climate", "play_music", "delete_event", "add_expense"} <= names
```

- [ ] **Step 12: Create `tests/unit/adapters/test_structlog_logger.py`**

Create `tests/unit/adapters/test_structlog_logger.py`:

```python
from __future__ import annotations

import json

import pytest
import structlog

from app.adapters.logging.structlog_logger import StructlogLogger, configure_logging


@pytest.mark.unit
def test_json_mode_emits_one_json_object_per_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=True)
    StructlogLogger().info("tool.done", tool="list_lights")
    line = capsys.readouterr().out.strip()
    assert json.loads(line) | {"timestamp": "x"} == {
        "event": "tool.done",
        "tool": "list_lights",
        "level": "info",
        "timestamp": "x",
    }
    structlog.reset_defaults()


@pytest.mark.unit
def test_level_filters_lower_severities(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("WARNING", json=True)
    logger = StructlogLogger()
    logger.info("hidden")
    logger.debug("hidden")
    logger.error("shown")
    out = capsys.readouterr().out
    assert "shown" in out
    assert "hidden" not in out
    structlog.reset_defaults()


@pytest.mark.unit
def test_console_mode_is_human_readable(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", json=False)
    StructlogLogger().warning("careful")
    assert "careful" in capsys.readouterr().out
    structlog.reset_defaults()
```

- [ ] **Step 13: Create `app/domain/entities.py`**

Create `app/domain/entities.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


@dataclass(frozen=True, slots=True)
class Message:
    id: str
    role: str
    content: str
    timestamp: datetime
```

- [ ] **Step 14: Create `app/domain/exceptions.py`**

Create `app/domain/exceptions.py`:

```python
from __future__ import annotations


class DomainError(Exception):
    """Base for all domain errors."""


class RegistryError(DomainError):
    """Base for registry errors."""


class RegistryDuplicateError(RegistryError):
    """Raised when registering a key that already exists."""


class RegistryKeyError(RegistryError):
    """Raised when looking up a key that does not exist."""


class AgentError(DomainError):
    """Raised when an agent fails to produce a reply."""


class ClimateError(DomainError):
    """Raised when an air-conditioner operation is invalid or fails."""


class UnknownClimateDeviceError(ClimateError):
    """Raised when a climate device name is not in the configured list."""


class LightError(DomainError):
    """Raised when a light operation is invalid or fails."""


class UnknownLightDeviceError(LightError):
    """Raised when a light name is not in the configured list."""


class MusicError(DomainError):
    """Raised when a music operation is invalid or fails."""


class UnknownMusicDeviceError(MusicError):
    """Raised when a playback device name is not available."""


class LiveSessionError(DomainError):
    """Raised when a live (voice) session cannot be opened or breaks."""


class ConfigError(DomainError):
    """Raised at boot when settings are invalid."""


class ToolArgumentError(DomainError):
    """Raised when the model passes missing or mistyped tool arguments."""


class EventNotFoundError(DomainError):
    """Raised when a calendar event id does not exist."""
```

- [ ] **Step 15: Create `app/config.py`**

Create `app/config.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.exceptions import ConfigError

MIN_TOKEN_LENGTH = 32


class TuyaLightSettings(BaseModel):
    device_id: str
    address: str
    local_key: SecretStr
    version: float = 3.3


class Settings(BaseSettings):
    app_name: str = "byte"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    api_token: SecretStr
    openai_api_key: SecretStr
    chat_model: str = "gpt-4.1-mini"
    chat_timeout_seconds: float = 30.0
    tool_timeout_seconds: float = 10.0
    max_steps: int = 6
    history_limit: int = 20
    max_conversations: int = 50
    # Real devices. Leave a group unset and Byte runs against the in-memory adapter instead.
    thinq_access_secret: SecretStr | None = None
    thinq_country: str = "BR"
    thinq_client_id: str = "byte-thinq-client"
    tuya_lights: dict[str, TuyaLightSettings] = {}
    spotify_client_id: str | None = None
    spotify_refresh_token: SecretStr | None = None
    spotify_device: str = ""

    model_config = SettingsConfigDict(
        env_prefix="BYTE_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    @field_validator("api_token")
    @classmethod
    def _token_is_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_TOKEN_LENGTH:
            raise ValueError(f"must be at least {MIN_TOKEN_LENGTH} characters")
        return value

    @field_validator("openai_api_key")
    @classmethod
    def _key_is_not_empty(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("must not be empty")
        return value


def load_settings() -> Settings:
    """Build Settings or raise ConfigError naming the bad fields, never their values."""
    try:
        return Settings()  # pyright: ignore[reportCallIssue]
    except ValidationError as exc:
        problems = ", ".join(
            f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}"
            for err in exc.errors(include_input=False, include_url=False)
        )
        raise ConfigError(f"invalid settings ({problems})") from exc
```

- [ ] **Step 16: Create `app/adapters/logging/structlog_logger.py`**

Create `app/adapters/logging/structlog_logger.py`:

```python
from __future__ import annotations

import logging

import structlog

from app.ports.logger import LoggerPort


def configure_logging(level: str, *, json: bool) -> None:
    """JSON lines for containers, console rendering for a terminal."""
    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
    )


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

- [ ] **Step 17: Create `app/api/schemas.py`**

Create `app/api/schemas.py`:

```python
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MAX_CONTENT_CHARS = 4000


class IncomingMessageSchema(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=MAX_CONTENT_CHARS)
    segment: str = "auto"
    conversation_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class PendingConfirmationSchema(BaseModel):
    summary: str


class MessageSchema(BaseModel):
    id: str
    role: str
    content: str
    conversation_id: str
    pending_confirmation: PendingConfirmationSchema | None = None
```

- [ ] **Step 18: Create `app/api/auth.py`**

Create `app/api/auth.py`:

```python
from __future__ import annotations

import hmac
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, status

from app.api.deps import get_settings

if TYPE_CHECKING:
    from pydantic import SecretStr

    from app.config import Settings

BEARER = "Bearer "


def token_matches(header: str | None, token: SecretStr) -> bool:
    if header is None or not header.startswith(BEARER):
        return False
    return hmac.compare_digest(header[len(BEARER) :].encode(), token.get_secret_value().encode())


async def require_token(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not token_matches(authorization, settings.api_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
```

- [ ] **Step 19: Create `app/api/errors.py`**

Create `app/api/errors.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import status
from fastapi.responses import JSONResponse

from app.api.deps import get_logger
from app.domain.exceptions import AgentError, DomainError

if TYPE_CHECKING:
    from fastapi import FastAPI, Request


def _log_failure(event: str, exc: Exception) -> None:
    cause = type(exc.__cause__).__name__ if exc.__cause__ is not None else None
    get_logger().error(event, error=type(exc).__name__, cause=cause)


async def _agent_error(_: Request, exc: Exception) -> JSONResponse:
    _log_failure("agent.failed", exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "Agent failed to produce a reply"},
    )


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    _log_failure("domain.failed", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal error"}
    )


def install_error_handlers(app: FastAPI) -> None:
    """Map domain errors to HTTP. Logs the error type and cause type, never any content."""
    app.add_exception_handler(AgentError, _agent_error)
    app.add_exception_handler(DomainError, _domain_error)
```

- [ ] **Step 20: Create `app/api/deps.py`**

Create `app/api/deps.py`:

```python
from __future__ import annotations

import time
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Depends
from openai import AsyncOpenAI

from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.memory.in_memory_calendar import InMemoryCalendar
from app.adapters.memory.in_memory_climate import InMemoryClimate
from app.adapters.memory.in_memory_conversation_store import InMemoryConversationStore
from app.adapters.memory.in_memory_expenses import InMemoryExpenses
from app.adapters.memory.in_memory_light import InMemoryLight
from app.adapters.memory.in_memory_music import InMemoryMusic
from app.adapters.openai.chat_model import OpenAIChatModel
from app.application.pending_actions import PendingActionStore
from app.application.tool_runner import ToolRunner
from app.application.tools.catalog import build_tool_registry
from app.application.use_cases.process_chat_message import ProcessChatMessage
from app.config import Settings, load_settings

if TYPE_CHECKING:
    from app.application.registry import Registry
    from app.application.tool import Tool
    from app.ports.calendar import CalendarPort
    from app.ports.chat_model import ChatModelPort
    from app.ports.climate import ClimatePort
    from app.ports.conversation_store import ConversationStorePort
    from app.ports.expenses import ExpensesPort
    from app.ports.light import LightPort
    from app.ports.logger import LoggerPort
    from app.ports.music import MusicPort


@lru_cache
def get_settings() -> Settings:
    return load_settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_store() -> ConversationStorePort:
    return InMemoryConversationStore(get_settings().max_conversations)


@lru_cache
def get_pending() -> PendingActionStore:
    return PendingActionStore(time.monotonic)


# The three device groups pick the real adapter when it is configured and the in-memory one
# otherwise, so the whole service runs without hardware. The lifespan logs which one is active.
# Real adapters are imported lazily: their packages live in optional extras (tuya, thinq, spotify).


@lru_cache
def get_light() -> LightPort:
    lights = get_settings().tuya_lights
    if not lights:
        return InMemoryLight()
    from app.adapters.tuya.tuya_light import (  # noqa: PLC0415 - optional extra
        TuyaLight,
        TuyaLightDevice,
    )

    return TuyaLight(
        {
            name: TuyaLightDevice(s.device_id, s.address, s.local_key.get_secret_value(), s.version)
            for name, s in lights.items()
        }
    )


@lru_cache
def get_climate() -> ClimatePort:
    settings = get_settings()
    if settings.thinq_access_secret is None:
        return InMemoryClimate()
    from app.adapters.thinq.thinq_climate import ThinQClimate  # noqa: PLC0415 - optional extra

    return ThinQClimate(
        settings.thinq_access_secret.get_secret_value(),
        settings.thinq_country,
        settings.thinq_client_id,
    )


@lru_cache
def get_music() -> MusicPort:
    settings = get_settings()
    if settings.spotify_client_id is None or settings.spotify_refresh_token is None:
        return InMemoryMusic()
    from app.adapters.spotify.spotify_music import SpotifyMusic  # noqa: PLC0415 - optional extra

    return SpotifyMusic(
        settings.spotify_client_id,
        settings.spotify_refresh_token.get_secret_value(),
        settings.spotify_device,
    )


@lru_cache
def get_calendar() -> CalendarPort:
    # ponytail: in memory until the Google Calendar adapter exists
    return InMemoryCalendar()


@lru_cache
def get_expenses() -> ExpensesPort:
    # ponytail: in memory until the Google Sheets adapter exists
    return InMemoryExpenses()


@lru_cache
def get_tools() -> Registry[Tool]:
    return build_tool_registry(
        get_light(), get_climate(), get_music(), get_calendar(), get_expenses()
    )


@lru_cache
def get_runner() -> ToolRunner:
    return ToolRunner(
        get_tools(),
        get_pending(),
        get_logger(),
        tool_timeout=get_settings().tool_timeout_seconds,
    )


@lru_cache
def get_openai() -> AsyncOpenAI:
    settings = get_settings()
    return AsyncOpenAI(
        api_key=settings.openai_api_key.get_secret_value(),
        timeout=settings.chat_timeout_seconds,
    )


@lru_cache
def get_chat_model() -> ChatModelPort:
    return OpenAIChatModel(get_openai(), get_settings().chat_model)


def get_process_chat(
    model: ChatModelPort = Depends(get_chat_model),
    store: ConversationStorePort = Depends(get_store),
    runner: ToolRunner = Depends(get_runner),
    pending: PendingActionStore = Depends(get_pending),
    log: LoggerPort = Depends(get_logger),
    settings: Settings = Depends(get_settings),
) -> ProcessChatMessage:
    return ProcessChatMessage(
        model,
        store,
        runner,
        pending,
        log,
        max_steps=settings.max_steps,
        history_limit=settings.history_limit,
        timeout_seconds=settings.chat_timeout_seconds,
    )
```

- [ ] **Step 21: Create `app/api/router.py`**

Create `app/api/router.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import require_token
from app.api.deps import get_process_chat, get_runner
from app.api.schemas import IncomingMessageSchema, MessageSchema, PendingConfirmationSchema

if TYPE_CHECKING:
    from app.application.tool_runner import ToolRunner
    from app.application.use_cases.process_chat_message import ProcessChatMessage

AUTO = "auto"

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/messages", response_model=MessageSchema, dependencies=[Depends(require_token)])
async def receive_message(
    body: IncomingMessageSchema,
    chat: ProcessChatMessage = Depends(get_process_chat),
    runner: ToolRunner = Depends(get_runner),
) -> MessageSchema:
    segment = body.segment.strip().lower()
    if segment != AUTO and segment not in runner.segments():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown segment: {body.segment!r}"
        )
    conversation_id = body.conversation_id or uuid4().hex
    reply = await chat.execute(conversation_id, body.content, None if segment == AUTO else segment)
    return MessageSchema(
        id=reply.message.id,
        role=reply.message.role,
        content=reply.message.content,
        conversation_id=conversation_id,
        pending_confirmation=(
            PendingConfirmationSchema(summary=reply.pending_summary)
            if reply.pending_summary
            else None
        ),
    )
```

- [ ] **Step 22: Create `main.py`**

Create `main.py`:

```python
from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.adapters.logging.structlog_logger import configure_logging
from app.api.deps import (
    get_chat_model,
    get_climate,
    get_light,
    get_logger,
    get_music,
    get_runner,
    get_settings,
)
from app.api.errors import install_error_handlers
from app.api.router import router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()  # a bad config stops the boot here, not at the first request
    configure_logging(settings.log_level, json=not sys.stdout.isatty())
    get_chat_model()
    runner = get_runner()
    # Which adapter drives each device group: an in-memory name here means "not configured".
    get_logger().info(
        "adapters.selected",
        light=type(get_light()).__name__,
        climate=type(get_climate()).__name__,
        music=type(get_music()).__name__,
    )
    yield
    await runner.drain()


app = FastAPI(title="byte", lifespan=lifespan)
app.include_router(router, prefix="/api/v1")
install_error_handlers(app)
```

- [ ] **Step 23: Create `pyproject.toml`**

Create `pyproject.toml`:

```toml
[project]
name = "byte"
version = "0.1.0"
description = "Byte — personal assistant backend. Hexagonal architecture, one agent, chat + live voice, tools as adapters, Docker."
requires-python = ">=3.12"
authors = [{ name = "Felipe" }]
readme = "README.md"
license = { text = "Proprietary" }

dependencies = [
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "structlog>=24.4",
]

[project.optional-dependencies]
api = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
]
openai = [
    "openai>=2.35",
]
thinq = [
    "thinqconnect>=1.0.14",
    "aiohttp>=3.9",
]
tuya = [
    "tinytuya>=1.17",
]
spotify = [
    "aiohttp>=3.9",
]
dev = [
    "ruff>=0.7",
    "pyright>=1.1.385",
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "pytest-cov>=5.0",
    "pre-commit>=4.0",
    "httpx>=0.27",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

# ─────────────────────────────────────────────────────────────
# Ruff: lint + format (substitui black, isort, flake8, pyupgrade)
# ─────────────────────────────────────────────────────────────
[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = [".venv", "build", "dist"]

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # pyflakes
    "I",   # isort
    "N",   # pep8-naming
    "UP",  # pyupgrade
    "B",   # flake8-bugbear
    "SIM", # flake8-simplify
    "RUF", # ruff-specific
    "ASYNC", # flake8-async
    "S",   # flake8-bandit (security)
    "TID", # flake8-tidy-imports
    "TCH", # flake8-type-checking
    "PL",  # pylint
    "ANN", # flake8-annotations (type hints obrigatórios)
]
ignore = [
    "PLR0913", # too many arguments (use cases podem ter)
    "S101",   # assert (pytest usa)
    "B008",   # FastAPI Depends() in argument defaults
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["ANN", "S", "PLR2004"]
"main.py" = ["ANN"]

[tool.ruff.lint.isort]
known-first-party = ["app"]
combine-as-imports = true

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

# ─────────────────────────────────────────────────────────────
# Pyright: type checking strict
# ─────────────────────────────────────────────────────────────
[tool.pyright]
include = ["app", "tests", "main.py"]
exclude = [".venv", "build", "dist"]
typeCheckingMode = "strict"
pythonVersion = "3.12"
reportMissingTypeStubs = false
reportUnknownMemberType = "warning"
reportUnknownVariableType = "warning"
reportUnknownArgumentType = "warning"

# ─────────────────────────────────────────────────────────────
# Pytest
# ─────────────────────────────────────────────────────────────
[tool.pytest.ini_options]
minversion = "8.0"
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "-m",
    "not integration",
    "--cov=app",
    "--cov-report=term-missing",
    "--cov-fail-under=80",
]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
markers = [
    "unit: fast isolated tests (default)",
    "integration: hits real vendors (OpenAI, Tuya, Google). Run with: pytest -m integration",
    "slow: takes >1s",
]

[tool.coverage.run]
branch = true
source = ["app"]
omit = ["app/adapters/openai/**", "app/ports/**"]  # openai: integration only; ports: pure ABCs

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
```

- [ ] **Step 24: Create `.env.example`**

Create `.env.example`:

```bash
# --- required ---------------------------------------------------------------
# Bearer token for every route and the WebSocket. At least 32 characters; the app
# refuses to boot otherwise. Generate one: python -c "import secrets; print(secrets.token_urlsafe(48))"
BYTE_API_TOKEN=
BYTE_OPENAI_API_KEY=

# --- models -----------------------------------------------------------------
BYTE_CHAT_MODEL=gpt-4.1-mini

# --- devices (optional) -----------------------------------------------------
# A group left empty runs against an in-memory fake, and the log says so at boot.
# LG ThinQ Personal Access Token (https://connect-pat.lgthinq.com)
BYTE_THINQ_ACCESS_SECRET=
BYTE_THINQ_COUNTRY=BR
# Tuya lights over the LAN, by name: {"lampada":{"device_id":"","address":"","local_key":"","version":3.3}}
BYTE_TUYA_LIGHTS=
# Spotify (Premium). Client ID from developer.spotify.com; token via scripts/spotify_login.py
BYTE_SPOTIFY_CLIENT_ID=
BYTE_SPOTIFY_REFRESH_TOKEN=
# Spotify Connect device name, e.g. your Nest Mini
BYTE_SPOTIFY_DEVICE=

# --- runtime ----------------------------------------------------------------
BYTE_LOG_LEVEL=INFO
```

- [ ] **Step 25: Edit `Dockerfile`**

In `Dockerfile`, replace:

```dockerfile
RUN pip install --no-cache-dir ".[api,agents]"
```

with:

```dockerfile
RUN pip install --no-cache-dir ".[api,openai,thinq,tuya,spotify]"
```

- [ ] **Step 26: Edit `tests/integration/test_tuya_light.py`**

In `tests/integration/test_tuya_light.py`, replace:

```python
import pytest

from app.adapters.tuya.tuya_light import TuyaLight, TuyaLightDevice
from app.config import Settings
from app.domain.light import Color, LightChange, LightMode, LightState

LIGHTS = Settings().tuya_lights
```

with:

```python
import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.adapters.tuya.tuya_light import TuyaLight, TuyaLightDevice
from app.config import TuyaLightSettings  # noqa: TC001 - pydantic resolves it at runtime
from app.domain.light import Color, LightChange, LightMode, LightState


class _LampEnv(BaseSettings):
    """Just the lamp config: this test needs neither the API token nor the OpenAI key."""

    model_config = SettingsConfigDict(
        env_prefix="BYTE_", env_file=".env", env_ignore_empty=True, extra="ignore"
    )
    tuya_lights: dict[str, TuyaLightSettings] = {}


LIGHTS = _LampEnv().tuya_lights
```

- [ ] **Step 27: Run the tests and watch them pass**

```bash
python -m pytest
```

Expected: PASS — 262 passed, 3 deselected (the integration tests), coverage above 80% (about 90%).

- [ ] **Step 28: Commit**

```bash
git add -A app tests main.py pyproject.toml .env.example Dockerfile
git commit -m "feat!: replace the Agno agents with one tool-using agent behind authenticated chat"
```

> **Breaking change.** The commit message uses `feat!:` because `POST /messages` now requires a bearer token and the environment variables changed (`GEMINI_API_KEY`, `GROQ_API_KEY`, `BYTE_SEGMENTS` and the four `BYTE_*_MODEL` tier variables are gone; `BYTE_API_TOKEN`, `BYTE_OPENAI_API_KEY`, `BYTE_CHAT_MODEL` are new; your `BYTE_TUYA_LIGHTS`, `BYTE_THINQ_*` and `BYTE_SPOTIFY_*` keep working). Update your local `.env` before running the service.

### Task 9: README, `CLAUDE.md` and the spec for the chat release

**Files:**
- Replace: `README.md`
- Modify: `CLAUDE.md` (authentication wording, segments, integrations, confirmation note, Current state)
- Modify: the spec (status line and an amendment)

**Interfaces:**
- Consumes: the finished chat service.
- Produces: documentation that matches the code, and a final green gate.

- [ ] **Step 1: Create `README.md`**

Create `README.md`:

````markdown
# Byte

A personal assistant backend for one person, running headless in Docker on a home
server. It controls lights, an air conditioner and music, manages a calendar and tracks
monthly expenses. Chat today (`POST /api/v1/messages`); a live spoken mode comes next.

One agent holds every tool. Every outside resource (the model provider, the smart
home, the calendar, the expense sheet, storage) is an adapter behind a port.

No GUI, no computer vision, no chat-channel adapters, no multi-user support.

## Run

```bash
cp .env.example .env        # fill BYTE_API_TOKEN (32+ chars) and BYTE_OPENAI_API_KEY
docker compose up --build
```

API on `http://127.0.0.1:8000/api/v1`, interactive docs at `/docs`. Compose binds to
loopback only.

### Real devices

Each group runs against an in-memory fake until you configure the real thing, and the
boot log says which adapter is active (`adapters.selected`).

| Group | Adapter | Configure in `.env` |
|---|---|---|
| Lights | Tuya, over the LAN (`tinytuya`) | `BYTE_TUYA_LIGHTS`: JSON of name → `device_id`, `address`, `local_key`, `version` |
| Air conditioner | LG ThinQ | `BYTE_THINQ_ACCESS_SECRET` (personal access token), `BYTE_THINQ_COUNTRY` |
| Music | Spotify (Premium) | `BYTE_SPOTIFY_CLIENT_ID`, `BYTE_SPOTIFY_REFRESH_TOKEN` (get it with `python scripts/spotify_login.py`), `BYTE_SPOTIFY_DEVICE` |

## Chat

```bash
curl -X POST http://127.0.0.1:8000/api/v1/messages \
  -H "authorization: Bearer $BYTE_API_TOKEN" -H 'content-type: application/json' \
  -d '{"content": "apaga o dentista de amanhã"}'
```

```json
{
  "id": "…",
  "role": "assistant",
  "content": "Apagar o evento evt-1. Posso apagar?",
  "conversation_id": "…",
  "pending_confirmation": { "summary": "Apagar o evento evt-1" }
}
```

Send `conversation_id` on later calls to continue the conversation. `segment`
(`home`, `music`, `agenda`, `finance`) is an optional filter over the tools; omitted or
`auto` means all of them; an unknown segment returns `404`.

Sensitive actions (deleting a calendar event, recording an expense, switching the air
conditioner on or off) never run on the first request: the reply carries the exact action in
`pending_confirmation`, and only the user's very next message, if it is a clear
"sim", executes it.

## Develop

```bash
pip install -e ".[api,openai,thinq,tuya,spotify,dev]"
ruff check . && pyright && pytest
pytest -m integration        # hits the real OpenAI API (needs BYTE_OPENAI_API_KEY)
```

## Status

Chat is built end to end. Lights (Tuya), the air conditioner (ThinQ) and music (Spotify)
have real adapters; the calendar and the expenses are still **in memory**, so the whole
flow (tools, confirmation) also runs with no device at all. Not built yet: live voice, the
Google Calendar and Google Sheets adapters, Postgres persistence (history is in memory
and lost on restart) and the reminder scheduler.

See `CLAUDE.md` for the rules, `docs/ARCHITECTURE.md` for the decisions and
`docs/superpowers/specs/` for the design.
````

- [ ] **Step 2: Edit `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md`**

In `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md`, replace:

```markdown
Status: **DRAFT v3 — reviewer rounds 1-2 applied; awaiting owner review.** Not approved. No implementation before approval.
```

with:

```markdown
Status: **Approved by the owner (2026-10-05).** Plan 1 (chat) implemented; Plan 2 (live voice and hardening) pending.
```

- [ ] **Step 3: Edit `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md`**

In `docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md`, replace:

```markdown
## 0. Intent (agreed with owner)
```

with:

```markdown
> **Amendment (2026-10-05, found while planning):** the owner had already built real adapters behind `LightPort`, `ClimatePort` and `MusicPort` (Tuya on the LAN, LG ThinQ, Spotify). The demo `HomePort` of §1 is dropped: the `home` and new `music` tools use those ports, and `music` is a fourth segment. Following the owner's notes (`AR_Controle.md`, `Lampada_Controle.md`, `Spotfy_Controle.md`): `delete_event` and `add_expense` always require confirmation, `set_climate` only when it switches the unit on or off (`Tool.needs_confirmation`), lights and music never; a lamp is not switched twice within 5 s; the model only plays uris returned by a search or the playlists. Wherever this spec says `HomePort`, read `LightPort` / `ClimatePort`.

## 0. Intent (agreed with owner)
```

- [ ] **Step 4: Edit `CLAUDE.md`**

In `CLAUDE.md`, replace:

```markdown
- **Authentication**: every route and the WebSocket require
  `Authorization: Bearer <token>`.
```

with:

```markdown
- **Authentication**: every route except `GET /health`, and the WebSocket, require
  `Authorization: Bearer <token>`.
```

- [ ] **Step 5: Edit `CLAUDE.md`**

In `CLAUDE.md`, replace:

```markdown
| `home` | Lights, plugs, sensors, scenes (Tuya Cloud) | `HomePort` |
```

with:

```markdown
| `home` | Lights (Tuya, local network) and the air conditioner (LG ThinQ) | `LightPort`, `ClimatePort` |
| `music` | Spotify playback on a Spotify Connect device | `MusicPort` |
```

- [ ] **Step 6: Edit `CLAUDE.md`**

In `CLAUDE.md`, replace:

```markdown
| Tuya | Tuya Cloud API | Devices are physical. See **Safety**. |
```

with:

```markdown
| Tuya | `tinytuya` over the local network (device id, address, local key) | Lights are physical. Keys come from the environment. |
| LG ThinQ | ThinQ Connect personal access token | The air conditioner. |
| Spotify | Web API with a refresh token (Premium) | Playback on a Connect device; `scripts/spotify_login.py` gets the token. |
```

- [ ] **Step 7: Edit `CLAUDE.md`**

In `CLAUDE.md`, replace:

```markdown
wins). Any other utterance drops the pending action. 60 s expiry. An agent
  must not learn that it can act first and apologise later.
```

with:

```markdown
wins). Any other utterance drops the pending action. 60 s expiry. An agent
  must not learn that it can act first and apologise later. Today `delete_event` and
  `add_expense` always ask, and `set_climate` asks whenever it switches the air
  conditioner on or off (`Tool.needs_confirmation`); lights and music never ask. The
  lamp is never switched twice within 5 s, and the model only plays a `uri` that a
  search or the playlists returned.
```

- [ ] **Step 8: Edit `CLAUDE.md`**

In `CLAUDE.md`, replace:

```markdown
The repository is **mid-migration**. Code is on the old design (Agno Team +
`Registry[AgentPort]`, `POST /messages`, `GET /health`); this file and the Spec
describe the target. Migration order is in the spec (§4).

| Piece | Status |
|---|---|
| Hexagonal skeleton, in-memory store, structlog | done (old shape) |
| Agno agents + Team routing | **to be removed** (Spec 1) |
| Domain types, ports, `Tool`, `ToolRunner`, confirmation | not started |
| OpenAI `ChatModelPort` + chat loop | not started |
| Auth, TLS, input limits, boot validation | not started |
| `WS /live` + OpenAI Realtime adapter | not started |
| In-memory Home / Calendar / Expenses adapters | not started |
| Tuya, Google Calendar / Sheets adapters | not started (later spec) |
| Postgres + pgvector + Alembic | not started (later spec) |
| Scheduler + `/ws/notifications` | not started (later spec) |
```

with:

```markdown
Spec 1 is delivered in two plans. **Plan 1 (chat) is done**: one agent with tools,
code-enforced confirmation, OpenAI chat, bearer auth, fail-fast boot. **Plan 2 (live voice
and hardening) is next**; until it lands, `WS /live` and TLS in this file describe the
target, not the code.

| Piece | Status |
|---|---|
| Hexagonal skeleton, structlog, in-memory store | done |
| Domain types, ports, `Tool`, `ToolRunner`, confirmation | done |
| OpenAI `ChatModelPort` + chat loop, `POST /messages` | done |
| Auth (bearer), input limits, boot validation, JSON logs | done |
| Tuya lights, LG ThinQ air conditioner, Spotify music (+ in-memory fakes) | done |
| In-memory Calendar / Expenses adapters | done |
| `WS /live` + OpenAI Realtime adapter | not started (Plan 2) |
| TLS, LAN exposure, locked dependencies, non-root image | not started (Plan 2) |
| Google Calendar / Sheets adapters | not started (later spec) |
| Postgres + pgvector + Alembic | not started (later spec) |
| Scheduler + `/ws/notifications` | not started (later spec) |
```

- [ ] **Step 9: Run the tests and watch them pass**

```bash
python -m pytest
```

Expected: PASS — 262 passed, 3 deselected.

- [ ] **Step 10: Smoke-test the real service (needs a real OpenAI key for the last call)**

```bash
export BYTE_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export BYTE_OPENAI_API_KEY=sk-...        # your key
uvicorn main:app --port 8000 &
curl -s localhost:8000/api/v1/health
curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8000/api/v1/messages \
  -H 'content-type: application/json' -d '{"content": "oi"}'
curl -s -X POST localhost:8000/api/v1/messages -H "authorization: Bearer $BYTE_API_TOKEN" \
  -H 'content-type: application/json' -d '{"content": "acende a lâmpada na cor azul"}'
```

Expected: `{"status":"ok"}`, then `401`, then a JSON reply in Brazilian Portuguese. The boot log line `adapters.selected` shows `InMemoryLight`, `InMemoryClimate`, `InMemoryMusic` until you set the real device variables; with `BYTE_TUYA_LIGHTS` set it shows `TuyaLight` and the lamp really turns blue. Stop the server afterwards (`kill %1`).

- [ ] **Step 11: Merge-readiness gate**

```bash
ruff check . && ruff format --check . && pyright && pytest
```

Expected: `ruff` clean, `pyright` 0 errors (8 warnings remain, all in `spotify_music.py` and `tuya_light.py`), `262 passed, 3 deselected`.

- [ ] **Step 12: Commit**

```bash
git add README.md \
  CLAUDE.md \
  docs/superpowers/specs/2026-10-05-personal-agent-chat-live-design.md
git commit -m "docs: describe the chat release in README, CLAUDE.md and the spec"
```

---

## Done when

- `ruff check . && ruff format --check . && pyright && pytest` is clean: **262 passed, 3 deselected**, coverage about 90%, `pyright` 0 errors.
- `POST /api/v1/messages` answers `401` without the token, `422` on invalid input, `404` on an unknown segment, and a Portuguese reply with `pending_confirmation` when a sensitive tool was requested.
- The agent can switch a light, the air conditioner and the music through your adapters (or their in-memory fakes), and the boot log shows which one is live.
- No Agno, Groq or Gemini dependency is left in `pyproject.toml`, and the service refuses to start with a short token.

Next: Plan 2, `docs/superpowers/plans/2026-10-05-live-mode-and-hardening.md`.
