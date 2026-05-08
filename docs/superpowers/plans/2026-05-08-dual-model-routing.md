# Dual-Model Routing (Groq + Gemini) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace single AgnoAgent (Claude/Anthropic) with a router-based dual-model system: Groq Llama 3.3 70B as default (with complexity classification via structured output) and Google Gemini 1.5 Flash for complex tasks and rate-limit fallback.

**Architecture:** `RoutingAgnoAgent` wraps `GroqAgnoAgent` and `GeminiAgnoAgent`. All agents return typed `AgentResponse` domain entities with multimodal `ContentBlock` support. Groq uses `output_schema=GroqOutputSchema` so it can signal complexity via an empty `content` list. Router checks `response.complexity == "complex"` or catches `groq.RateLimitError` to fall back to Gemini.

**Tech Stack:** agno>=1.5, groq>=0.11, google-generativeai>=0.8, Pydantic v2, SQLAlchemy async, FastAPI, pytest-asyncio

---

## File Map

### Created
- `app/adapters/agent/schemas.py` — Pydantic output schemas used as Agno `output_schema`
- `app/adapters/agent/groq_agno_agent.py` — GroqAgnoAgent (Llama 3.3 70B)
- `app/adapters/agent/gemini_agno_agent.py` — GeminiAgnoAgent (Gemini 1.5 Flash)
- `app/adapters/agent/routing_agno_agent.py` — RoutingAgnoAgent (implements AgentPort, routes between the two)
- `tests/unit/adapters/agent/test_groq_agno_agent.py`
- `tests/unit/adapters/agent/test_gemini_agno_agent.py`
- `tests/unit/adapters/agent/test_routing_agno_agent.py`

### Modified
- `app/domain/entities.py` — add TextBlock, ImageBlock, AudioBlock, ContentBlock, AgentResponse; add `model_used`/`routed_from` to OutgoingMessage; add `model_override` to IncomingMessage
- `app/ports/agent.py` — run() returns AgentResponse, accepts model_override
- `app/adapters/agent/stub_agent.py` — return AgentResponse
- `app/application/use_cases/process_incoming_message.py` — extract text from AgentResponse, pass model_override
- `app/api/schemas.py` — add model_override to IncomingMessageSchema; add model_used/routed_from to OutgoingMessageSchema
- `app/api/router.py` — thread model_override through, map new response fields
- `app/api/deps.py` — wire RoutingAgnoAgent instead of AgnoAgent
- `app/config.py` — add groq_api_key, google_api_key, groq_model_id, gemini_model_id; remove agno_model_id
- `pyproject.toml` — replace anthropic with groq + google-generativeai in agent extras
- `tests/unit/adapters/agent/test_stub_agent.py` — update assertions for AgentResponse
- `tests/unit/application/use_cases/test_process_incoming_message.py` — update mock to return AgentResponse

### Deleted
- `app/adapters/agent/agno_agent.py`
- `tests/unit/adapters/agent/test_agno_agent.py`

---

### Task 1: Add domain entities (TextBlock, ImageBlock, AudioBlock, AgentResponse, OutgoingMessage/IncomingMessage updates)

**Files:**
- Modify: `app/domain/entities.py`
- Modify: `tests/unit/domain/test_entities.py`

- [ ] **Step 1: Write failing tests for new entities**

Append to `tests/unit/domain/test_entities.py`:

```python
from dataclasses import FrozenInstanceError

from app.domain.entities import (
    AgentResponse,
    AudioBlock,
    ImageBlock,
    TextBlock,
)


@pytest.mark.unit
def test_text_block_defaults() -> None:
    block = TextBlock()
    assert block.type == "text"
    assert block.text == ""


@pytest.mark.unit
def test_text_block_is_frozen() -> None:
    block = TextBlock(text="hello")
    with pytest.raises(FrozenInstanceError):
        object.__setattr__(block, "text", "world")


@pytest.mark.unit
def test_image_block_default_mime_type() -> None:
    block = ImageBlock()
    assert block.mime_type == "image/jpeg"
    assert block.url is None
    assert block.base64_data is None


@pytest.mark.unit
def test_audio_block_default_mime_type() -> None:
    block = AudioBlock()
    assert block.mime_type == "audio/mpeg"


@pytest.mark.unit
def test_agent_response_simple() -> None:
    resp = AgentResponse(
        content=(TextBlock(text="hello"),),
        model_used="groq/llama-3.3-70b-versatile",
        complexity="simple",
        tools_called=(),
        routed_from=None,
    )
    assert resp.content[0].text == "hello"
    assert resp.complexity == "simple"
    assert resp.routed_from is None


@pytest.mark.unit
def test_agent_response_empty_content_is_handoff_signal() -> None:
    resp = AgentResponse(
        content=(),
        model_used="groq/llama-3.3-70b-versatile",
        complexity="complex",
        tools_called=(),
        routed_from=None,
    )
    assert resp.content == ()
    assert resp.complexity == "complex"


@pytest.mark.unit
def test_outgoing_message_model_fields_default() -> None:
    from app.domain.entities import OutgoingMessage

    msg = OutgoingMessage(content="hi", channel="api", recipient="user-1")
    assert msg.model_used == ""
    assert msg.routed_from is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/domain/test_entities.py -v -k "text_block or image_block or audio_block or agent_response or outgoing_message_model"
```

Expected: `ImportError` — TextBlock, ImageBlock, AudioBlock, AgentResponse not defined.

- [ ] **Step 3: Implement new entities in `app/domain/entities.py`**

Replace the full file with:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypeAlias

if TYPE_CHECKING:
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
    model_override: str | None = None  # "groq" | "gemini" | None


@dataclass(frozen=True, slots=True)
class TextBlock:
    type: Literal["text"] = "text"
    text: str = ""


@dataclass(frozen=True, slots=True)
class ImageBlock:
    type: Literal["image"] = "image"
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "image/jpeg"


@dataclass(frozen=True, slots=True)
class AudioBlock:
    type: Literal["audio"] = "audio"
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "audio/mpeg"


ContentBlock: TypeAlias = TextBlock | ImageBlock | AudioBlock


@dataclass(frozen=True, slots=True)
class AgentResponse:
    content: tuple[ContentBlock, ...]
    model_used: str
    complexity: Literal["simple", "complex"]
    tools_called: tuple[str, ...]
    routed_from: str | None


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    content: str
    channel: str
    recipient: str
    model_used: str = ""
    routed_from: str | None = None


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

Expected: all domain entity tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/domain/entities.py tests/unit/domain/test_entities.py
git commit -m "feat(domain): add multimodal content blocks, AgentResponse, update OutgoingMessage/IncomingMessage"
```

---

### Task 2: Update AgentPort contract

**Files:**
- Modify: `app/ports/agent.py`

- [ ] **Step 1: Update `app/ports/agent.py`**

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities import AgentResponse, Conversation


class AgentPort(ABC):
    @abstractmethod
    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse: ...
```

- [ ] **Step 2: Verify pyright catches any existing callers**

```
pyright app/ports/agent.py
```

Expected: no errors on the port file itself. (Callers will fail until updated — that is expected and fixed in subsequent tasks.)

- [ ] **Step 3: Commit**

```bash
git add app/ports/agent.py
git commit -m "feat(ports): update AgentPort.run() to return AgentResponse and accept model_override"
```

---

### Task 3: Update StubAgent and its tests

**Files:**
- Modify: `app/adapters/agent/stub_agent.py`
- Modify: `tests/unit/adapters/agent/test_stub_agent.py`

- [ ] **Step 1: Update the test file first**

Replace `tests/unit/adapters/agent/test_stub_agent.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.adapters.agent.stub_agent import StubAgent
from app.domain.entities import AgentResponse, Conversation, TextBlock
from app.ports.agent import AgentPort

NOW = datetime.now(tz=UTC)


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-1", messages=(), created_at=NOW)


@pytest.mark.unit
async def test_stub_agent_returns_agent_response(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation)
    assert isinstance(result, AgentResponse)


@pytest.mark.unit
async def test_stub_agent_content_is_text_block(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation)
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextBlock)
    assert "Hello" in result.content[0].text


@pytest.mark.unit
async def test_stub_agent_complexity_is_simple(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation)
    assert result.complexity == "simple"
    assert result.model_used == "stub"
    assert result.routed_from is None


@pytest.mark.unit
async def test_stub_agent_implements_port(conversation: Conversation) -> None:
    agent = StubAgent()
    assert isinstance(agent, AgentPort)


@pytest.mark.unit
async def test_stub_agent_accepts_model_override(conversation: Conversation) -> None:
    agent = StubAgent()
    result = await agent.run("Hello", conversation, model_override="gemini")
    assert isinstance(result, AgentResponse)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/adapters/agent/test_stub_agent.py -v
```

Expected: FAIL — StubAgent.run() still returns str.

- [ ] **Step 3: Update StubAgent implementation**

Replace `app/adapters/agent/stub_agent.py` with:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.entities import AgentResponse, TextBlock
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.domain.entities import Conversation


class StubAgent(AgentPort):
    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse:
        return AgentResponse(
            content=(TextBlock(text=f"[stub] Echo: {message}"),),
            model_used="stub",
            complexity="simple",
            tools_called=(),
            routed_from=None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/adapters/agent/test_stub_agent.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/agent/stub_agent.py tests/unit/adapters/agent/test_stub_agent.py
git commit -m "feat(adapters): update StubAgent to return AgentResponse"
```

---

### Task 4: Update ProcessIncomingMessage and its tests

**Files:**
- Modify: `app/application/use_cases/process_incoming_message.py`
- Modify: `tests/unit/application/use_cases/test_process_incoming_message.py`

- [ ] **Step 1: Update test fixtures to return AgentResponse**

Replace the `mock_agent` fixture and update affected tests in `tests/unit/application/use_cases/test_process_incoming_message.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import (
    AgentResponse,
    Conversation,
    IncomingMessage,
    OutgoingMessage,
    TextBlock,
)

NOW = datetime.now(tz=UTC)

_AGENT_RESPONSE = AgentResponse(
    content=(TextBlock(text="Hello back!"),),
    model_used="groq/llama-3.3-70b-versatile",
    complexity="simple",
    tools_called=(),
    routed_from=None,
)


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
def mock_agent() -> AsyncMock:
    agent = AsyncMock()
    agent.run.return_value = _AGENT_RESPONSE
    return agent


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
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    assert result.content == "Hello back!"
    assert result.channel == "api"
    assert result.recipient == "user-1"


@pytest.mark.unit
async def test_execute_propagates_model_used(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert result.model_used == "groq/llama-3.3-70b-versatile"
    assert result.routed_from is None


@pytest.mark.unit
async def test_execute_passes_model_override_to_agent(
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    msg = IncomingMessage(
        id="msg-x",
        sender="user-1",
        content="Hello!",
        channel="api",
        timestamp=NOW,
        model_override="gemini",
    )
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(msg)
    _, kwargs = mock_agent.run.call_args
    assert kwargs.get("model_override") == "gemini"


@pytest.mark.unit
async def test_execute_calls_agent(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_agent.run.assert_called_once()


@pytest.mark.unit
async def test_execute_saves_conversation(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(incoming_msg)
    mock_repo.save.assert_called_once()


@pytest.mark.unit
async def test_execute_loads_existing_conversation(
    mock_agent: AsyncMock,
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
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    await use_case.execute(msg)
    mock_repo.get.assert_called_once_with("conv-123")


@pytest.mark.unit
async def test_execute_creates_conversation_when_none(
    incoming_msg: IncomingMessage,
    mock_agent: AsyncMock,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    mock_repo.get.return_value = None
    use_case = ProcessIncomingMessage(agent=mock_agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert isinstance(result, OutgoingMessage)
    mock_repo.save.assert_called_once()


@pytest.mark.unit
async def test_execute_returns_empty_string_when_no_text_block(
    incoming_msg: IncomingMessage,
    mock_repo: AsyncMock,
    mock_log: MagicMock,
) -> None:
    empty_response = AgentResponse(
        content=(),
        model_used="groq/llama-3.3-70b-versatile",
        complexity="simple",
        tools_called=(),
        routed_from=None,
    )
    agent = AsyncMock()
    agent.run.return_value = empty_response
    use_case = ProcessIncomingMessage(agent=agent, repo=mock_repo, log=mock_log)
    result = await use_case.execute(incoming_msg)
    assert result.content == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/application/use_cases/test_process_incoming_message.py -v
```

Expected: FAIL — use case still treats agent.run() result as str.

- [ ] **Step 3: Update ProcessIncomingMessage**

Replace `app/application/use_cases/process_incoming_message.py` with:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from app.domain.entities import (
    Conversation,
    IncomingMessage,
    Message,
    OutgoingMessage,
    TextBlock,
)

if TYPE_CHECKING:
    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort


class ProcessIncomingMessage:
    def __init__(self, agent: AgentPort, repo: RepositoryPort, log: LoggerPort) -> None:
        self._agent = agent
        self._repo = repo
        self._log = log

    async def execute(self, msg: IncomingMessage) -> OutgoingMessage:
        conv_id = msg.conversation_id or str(uuid4())
        conversation = await self._repo.get(conv_id)
        if conversation is None:
            conversation = Conversation(
                id=conv_id,
                messages=(),
                created_at=datetime.now(tz=UTC),
            )

        user_msg = Message(
            id=str(uuid4()),
            role="user",
            content=msg.content,
            timestamp=msg.timestamp,
        )
        conversation = conversation.with_message(user_msg)

        self._log.info("agent.run.start", conversation_id=conv_id)
        response = await self._agent.run(
            message=msg.content,
            conversation=conversation,
            model_override=msg.model_override,
        )

        response_text = next(
            (block.text for block in response.content if isinstance(block, TextBlock)),
            "",
        )

        assistant_msg = Message(
            id=str(uuid4()),
            role="assistant",
            content=response_text,
            timestamp=datetime.now(tz=UTC),
        )
        conversation = conversation.with_message(assistant_msg)

        await self._repo.save(conversation)
        self._log.info("agent.run.done", conversation_id=conv_id)

        return OutgoingMessage(
            content=response_text,
            channel=msg.channel,
            recipient=msg.sender,
            model_used=response.model_used,
            routed_from=response.routed_from,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/application/use_cases/test_process_incoming_message.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5: Run full unit suite to catch regressions**

```
pytest tests/unit/ -v
```

Expected: all unit tests pass.

- [ ] **Step 6: Commit**

```bash
git add app/application/use_cases/process_incoming_message.py tests/unit/application/use_cases/test_process_incoming_message.py
git commit -m "feat(application): update ProcessIncomingMessage to handle AgentResponse and thread model_override"
```

---

### Task 5: Create Pydantic output schemas

**Files:**
- Create: `app/adapters/agent/schemas.py`

- [ ] **Step 1: Create `app/adapters/agent/schemas.py`**

```python
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.domain.entities import AudioBlock, ContentBlock, ImageBlock, TextBlock


class TextBlockSchema(BaseModel):
    type: Literal["text"] = "text"
    text: str = ""


class ImageBlockSchema(BaseModel):
    type: Literal["image"] = "image"
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "image/jpeg"


class AudioBlockSchema(BaseModel):
    type: Literal["audio"] = "audio"
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "audio/mpeg"


ContentBlockSchema = Annotated[
    TextBlockSchema | ImageBlockSchema | AudioBlockSchema,
    Field(discriminator="type"),
]


class GroqOutputSchema(BaseModel):
    complexity: Literal["simple", "complex"]
    content: list[ContentBlockSchema] = []
    tools_called: list[str] = []


class GeminiOutputSchema(BaseModel):
    content: list[ContentBlockSchema]
    tools_called: list[str] = []


def map_content_block(schema: TextBlockSchema | ImageBlockSchema | AudioBlockSchema) -> ContentBlock:
    if isinstance(schema, TextBlockSchema):
        return TextBlock(type=schema.type, text=schema.text)
    if isinstance(schema, ImageBlockSchema):
        return ImageBlock(
            type=schema.type,
            url=schema.url,
            base64_data=schema.base64_data,
            mime_type=schema.mime_type,
        )
    return AudioBlock(
        type=schema.type,
        url=schema.url,
        base64_data=schema.base64_data,
        mime_type=schema.mime_type,
    )
```

- [ ] **Step 2: Verify schemas parse correctly (quick sanity check)**

```
python -c "
from app.adapters.agent.schemas import GroqOutputSchema, GeminiOutputSchema, TextBlockSchema
r = GroqOutputSchema(complexity='simple', content=[{'type': 'text', 'text': 'hi'}])
print(r.content[0].text)
r2 = GroqOutputSchema(complexity='complex')
print(r2.content)
"
```

Expected output:
```
hi
[]
```

- [ ] **Step 3: Commit**

```bash
git add app/adapters/agent/schemas.py
git commit -m "feat(adapters): add Pydantic output schemas for Groq and Gemini Agno agents"
```

---

### Task 6: Update config.py and pyproject.toml

**Files:**
- Modify: `app/config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update `app/config.py`**

Replace full file with:

```python
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "marcelo"
    log_level: str = "INFO"
    default_channel: str = "api"

    # Database — asyncpg URL for SQLAlchemy; Agno adapters derive psycopg URL internally
    database_url: str = "postgresql+asyncpg://marcelo:marcelo@localhost:5432/marcelo"

    # Agno shared settings
    agno_add_datetime: bool = True
    agno_add_location: bool = True

    # Groq (Llama 3.3 70B — default model)
    groq_api_key: str = ""
    groq_model_id: str = "llama-3.3-70b-versatile"

    # Google Gemini (Gemini 1.5 Flash — complex/fallback model)
    google_api_key: str = ""
    gemini_model_id: str = "gemini-1.5-flash"

    model_config = SettingsConfigDict(
        env_prefix="MARCELO_",
        env_file=".env",
        env_file_encoding="utf-8",
    )
```

Env vars expected in `.env` or environment:
```
MARCELO_GROQ_API_KEY=gsk_...
MARCELO_GOOGLE_API_KEY=AIza...
```

- [ ] **Step 2: Update agent extras in `pyproject.toml`**

In `pyproject.toml`, replace the `agent` optional-dependencies section:

```toml
agent = [
    "agno>=1.5",
    "groq>=0.11",
    "google-generativeai>=0.8",
]
```

(Remove `"anthropic>=0.39"` — no longer used.)

- [ ] **Step 3: Install updated deps**

```
pip install -e ".[agent,api,db,dev]"
```

Expected: groq and google-generativeai installed, anthropic no longer required.

- [ ] **Step 4: Commit**

```bash
git add app/config.py pyproject.toml
git commit -m "chore(config): swap anthropic for groq+google-generativeai; add groq/gemini settings"
```

---

### Task 7: Create GroqAgnoAgent and tests

**Files:**
- Create: `app/adapters/agent/groq_agno_agent.py`
- Create: `tests/unit/adapters/agent/test_groq_agno_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/adapters/agent/test_groq_agno_agent.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.agent.schemas import GroqOutputSchema, TextBlockSchema
from app.domain.entities import AgentResponse, Conversation, TextBlock
from app.ports.agent import AgentPort

NOW = datetime.now(tz=UTC)


@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.database_url = "postgresql+asyncpg://test:test@localhost/test"
    s.groq_model_id = "llama-3.3-70b-versatile"
    s.agno_add_datetime = True
    s.agno_add_location = True
    return s


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-abc", messages=(), created_at=NOW)


def _make_agent_cls(output: GroqOutputSchema) -> tuple[MagicMock, AsyncMock]:
    mock_response = MagicMock()
    mock_response.content = output
    mock_inner = AsyncMock()
    mock_inner.arun = AsyncMock(return_value=mock_response)
    mock_cls = MagicMock(return_value=mock_inner)
    return mock_cls, mock_inner


@pytest.mark.unit
async def test_groq_agent_returns_simple_agent_response(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    output = GroqOutputSchema(
        complexity="simple",
        content=[TextBlockSchema(type="text", text="Hello!")],
        tools_called=[],
    )
    mock_cls, _ = _make_agent_cls(output)

    with (
        patch("app.adapters.agent.groq_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert isinstance(result, AgentResponse)
    assert result.complexity == "simple"
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextBlock)
    assert result.content[0].text == "Hello!"
    assert result.model_used == "groq/llama-3.3-70b-versatile"
    assert result.routed_from is None


@pytest.mark.unit
async def test_groq_agent_returns_complex_signal(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    output = GroqOutputSchema(complexity="complex", content=[], tools_called=[])
    mock_cls, _ = _make_agent_cls(output)

    with (
        patch("app.adapters.agent.groq_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        result = await agent.run("Complex task", conversation)

    assert result.complexity == "complex"
    assert result.content == ()


@pytest.mark.unit
async def test_groq_agent_passes_session_id(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    output = GroqOutputSchema(complexity="simple", content=[], tools_called=[])
    mock_cls, mock_inner = _make_agent_cls(output)

    with (
        patch("app.adapters.agent.groq_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        await agent.run("Hello", conversation)

    mock_inner.arun.assert_called_once_with("Hello", session_id="conv-abc")


@pytest.mark.unit
async def test_groq_agent_returns_empty_on_none_response(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_inner = AsyncMock()
    mock_inner.arun = AsyncMock(return_value=None)
    mock_cls = MagicMock(return_value=mock_inner)

    with (
        patch("app.adapters.agent.groq_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert result.content == ()
    assert result.complexity == "simple"


@pytest.mark.unit
async def test_groq_agent_implements_port(mock_settings: MagicMock) -> None:
    with (
        patch("app.adapters.agent.groq_agno_agent.Agent"),
        patch("app.adapters.agent.groq_agno_agent.PostgresDb"),
        patch("app.adapters.agent.groq_agno_agent.Groq"),
    ):
        from app.adapters.agent.groq_agno_agent import GroqAgnoAgent  # noqa: PLC0415

        agent = GroqAgnoAgent(mock_settings)
        assert isinstance(agent, AgentPort)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/adapters/agent/test_groq_agno_agent.py -v
```

Expected: `ModuleNotFoundError` — groq_agno_agent not defined.

- [ ] **Step 3: Create `app/adapters/agent/groq_agno_agent.py`**

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.groq import Groq

from app.adapters.agent.schemas import GroqOutputSchema, map_content_block
from app.domain.entities import AgentResponse
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.config import Settings
    from app.domain.entities import Conversation

_SYSTEM_PROMPT = (
    "Classify this task before responding. "
    "If the task requires deep multi-step reasoning, advanced mathematics, "
    "complex code generation, or long-form structured analysis: "
    "set complexity='complex' and content=[]. Do NOT answer the question. "
    "Otherwise: set complexity='simple' and fill content with your full answer."
)


class GroqAgnoAgent(AgentPort):
    def __init__(self, settings: Settings) -> None:
        self._model_id = settings.groq_model_id
        agno_db_url = settings.database_url.replace("+asyncpg", "+psycopg")
        db = PostgresDb(db_url=agno_db_url)
        self._agent = Agent(
            model=Groq(id=self._model_id),
            db=db,
            add_history_to_context=True,
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
            output_schema=GroqOutputSchema,
            instructions=[_SYSTEM_PROMPT],
        )

    @property
    def model_id(self) -> str:
        return f"groq/{self._model_id}"

    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse:
        response = await self._agent.arun(message, session_id=conversation.id)
        if response is None or response.content is None:
            return AgentResponse(
                content=(),
                model_used=self.model_id,
                complexity="simple",
                tools_called=(),
                routed_from=None,
            )
        output: GroqOutputSchema = response.content
        return AgentResponse(
            content=tuple(map_content_block(b) for b in output.content),
            model_used=self.model_id,
            complexity=output.complexity,
            tools_called=tuple(output.tools_called),
            routed_from=None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/adapters/agent/test_groq_agno_agent.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/agent/groq_agno_agent.py tests/unit/adapters/agent/test_groq_agno_agent.py
git commit -m "feat(adapters): add GroqAgnoAgent with complexity classification via output_schema"
```

---

### Task 8: Create GeminiAgnoAgent and tests

**Files:**
- Create: `app/adapters/agent/gemini_agno_agent.py`
- Create: `tests/unit/adapters/agent/test_gemini_agno_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/adapters/agent/test_gemini_agno_agent.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.agent.schemas import GeminiOutputSchema, TextBlockSchema
from app.domain.entities import AgentResponse, Conversation, TextBlock
from app.ports.agent import AgentPort

NOW = datetime.now(tz=UTC)


@pytest.fixture
def mock_settings() -> MagicMock:
    s = MagicMock()
    s.database_url = "postgresql+asyncpg://test:test@localhost/test"
    s.gemini_model_id = "gemini-1.5-flash"
    s.agno_add_datetime = True
    s.agno_add_location = True
    return s


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-abc", messages=(), created_at=NOW)


def _make_agent_cls(output: GeminiOutputSchema) -> tuple[MagicMock, AsyncMock]:
    mock_response = MagicMock()
    mock_response.content = output
    mock_inner = AsyncMock()
    mock_inner.arun = AsyncMock(return_value=mock_response)
    mock_cls = MagicMock(return_value=mock_inner)
    return mock_cls, mock_inner


@pytest.mark.unit
async def test_gemini_agent_returns_agent_response(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    output = GeminiOutputSchema(
        content=[TextBlockSchema(type="text", text="Detailed answer.")],
        tools_called=[],
    )
    mock_cls, _ = _make_agent_cls(output)

    with (
        patch("app.adapters.agent.gemini_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.gemini_agno_agent.PostgresDb"),
        patch("app.adapters.agent.gemini_agno_agent.Gemini"),
    ):
        from app.adapters.agent.gemini_agno_agent import GeminiAgnoAgent  # noqa: PLC0415

        agent = GeminiAgnoAgent(mock_settings)
        result = await agent.run("What is quantum entanglement?", conversation)

    assert isinstance(result, AgentResponse)
    assert len(result.content) == 1
    assert isinstance(result.content[0], TextBlock)
    assert result.content[0].text == "Detailed answer."
    assert result.model_used == "google/gemini-1.5-flash"
    assert result.complexity == "complex"
    assert result.routed_from is None


@pytest.mark.unit
async def test_gemini_agent_passes_session_id(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    output = GeminiOutputSchema(content=[], tools_called=[])
    mock_cls, mock_inner = _make_agent_cls(output)

    with (
        patch("app.adapters.agent.gemini_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.gemini_agno_agent.PostgresDb"),
        patch("app.adapters.agent.gemini_agno_agent.Gemini"),
    ):
        from app.adapters.agent.gemini_agno_agent import GeminiAgnoAgent  # noqa: PLC0415

        agent = GeminiAgnoAgent(mock_settings)
        await agent.run("Hello", conversation)

    mock_inner.arun.assert_called_once_with("Hello", session_id="conv-abc")


@pytest.mark.unit
async def test_gemini_agent_returns_empty_on_none_response(
    mock_settings: MagicMock, conversation: Conversation
) -> None:
    mock_inner = AsyncMock()
    mock_inner.arun = AsyncMock(return_value=None)
    mock_cls = MagicMock(return_value=mock_inner)

    with (
        patch("app.adapters.agent.gemini_agno_agent.Agent", mock_cls),
        patch("app.adapters.agent.gemini_agno_agent.PostgresDb"),
        patch("app.adapters.agent.gemini_agno_agent.Gemini"),
    ):
        from app.adapters.agent.gemini_agno_agent import GeminiAgnoAgent  # noqa: PLC0415

        agent = GeminiAgnoAgent(mock_settings)
        result = await agent.run("Hello", conversation)

    assert result.content == ()
    assert result.model_used == "google/gemini-1.5-flash"


@pytest.mark.unit
async def test_gemini_agent_implements_port(mock_settings: MagicMock) -> None:
    with (
        patch("app.adapters.agent.gemini_agno_agent.Agent"),
        patch("app.adapters.agent.gemini_agno_agent.PostgresDb"),
        patch("app.adapters.agent.gemini_agno_agent.Gemini"),
    ):
        from app.adapters.agent.gemini_agno_agent import GeminiAgnoAgent  # noqa: PLC0415

        agent = GeminiAgnoAgent(mock_settings)
        assert isinstance(agent, AgentPort)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/adapters/agent/test_gemini_agno_agent.py -v
```

Expected: `ModuleNotFoundError` — gemini_agno_agent not defined.

- [ ] **Step 3: Create `app/adapters/agent/gemini_agno_agent.py`**

```python
from __future__ import annotations

from typing import TYPE_CHECKING

from agno.agent import Agent
from agno.db.postgres import PostgresDb
from agno.models.google import Gemini

from app.adapters.agent.schemas import GeminiOutputSchema, map_content_block
from app.domain.entities import AgentResponse
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.config import Settings
    from app.domain.entities import Conversation


class GeminiAgnoAgent(AgentPort):
    def __init__(self, settings: Settings) -> None:
        self._model_id = settings.gemini_model_id
        agno_db_url = settings.database_url.replace("+asyncpg", "+psycopg")
        db = PostgresDb(db_url=agno_db_url)
        self._agent = Agent(
            model=Gemini(id=self._model_id),
            db=db,
            add_history_to_context=True,
            add_datetime_to_context=settings.agno_add_datetime,
            add_location_to_context=settings.agno_add_location,
            output_schema=GeminiOutputSchema,
        )

    @property
    def model_id(self) -> str:
        return f"google/{self._model_id}"

    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse:
        response = await self._agent.arun(message, session_id=conversation.id)
        if response is None or response.content is None:
            return AgentResponse(
                content=(),
                model_used=self.model_id,
                complexity="complex",
                tools_called=(),
                routed_from=None,
            )
        output: GeminiOutputSchema = response.content
        return AgentResponse(
            content=tuple(map_content_block(b) for b in output.content),
            model_used=self.model_id,
            complexity="complex",
            tools_called=tuple(output.tools_called),
            routed_from=None,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/adapters/agent/test_gemini_agno_agent.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/agent/gemini_agno_agent.py tests/unit/adapters/agent/test_gemini_agno_agent.py
git commit -m "feat(adapters): add GeminiAgnoAgent (Gemini 1.5 Flash)"
```

---

### Task 9: Create RoutingAgnoAgent and tests

**Files:**
- Create: `app/adapters/agent/routing_agno_agent.py`
- Create: `tests/unit/adapters/agent/test_routing_agno_agent.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/adapters/agent/test_routing_agno_agent.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.entities import AgentResponse, Conversation, TextBlock
from app.ports.agent import AgentPort

NOW = datetime.now(tz=UTC)


@pytest.fixture
def conversation() -> Conversation:
    return Conversation(id="conv-abc", messages=(), created_at=NOW)


def _simple_response(model: str) -> AgentResponse:
    return AgentResponse(
        content=(TextBlock(text="Simple answer"),),
        model_used=model,
        complexity="simple",
        tools_called=(),
        routed_from=None,
    )


def _complex_signal() -> AgentResponse:
    return AgentResponse(
        content=(),
        model_used="groq/llama-3.3-70b-versatile",
        complexity="complex",
        tools_called=(),
        routed_from=None,
    )


def _gemini_response() -> AgentResponse:
    return AgentResponse(
        content=(TextBlock(text="Complex answer"),),
        model_used="google/gemini-1.5-flash",
        complexity="complex",
        tools_called=(),
        routed_from=None,
    )


@pytest.mark.unit
async def test_simple_groq_response_returned_directly(conversation: Conversation) -> None:
    mock_groq = AsyncMock()
    mock_groq.run.return_value = _simple_response("groq/llama-3.3-70b-versatile")
    mock_groq.model_id = "groq/llama-3.3-70b-versatile"
    mock_gemini = AsyncMock()

    from app.adapters.agent.routing_agno_agent import RoutingAgnoAgent  # noqa: PLC0415

    router = RoutingAgnoAgent(mock_groq, mock_gemini)
    result = await router.run("Hello", conversation)

    assert result.model_used == "groq/llama-3.3-70b-versatile"
    assert result.routed_from is None
    mock_gemini.run.assert_not_called()


@pytest.mark.unit
async def test_complex_signal_routes_to_gemini(conversation: Conversation) -> None:
    mock_groq = AsyncMock()
    mock_groq.run.return_value = _complex_signal()
    mock_groq.model_id = "groq/llama-3.3-70b-versatile"
    mock_gemini = AsyncMock()
    mock_gemini.run.return_value = _gemini_response()

    from app.adapters.agent.routing_agno_agent import RoutingAgnoAgent  # noqa: PLC0415

    router = RoutingAgnoAgent(mock_groq, mock_gemini)
    result = await router.run("Explain quantum mechanics in depth", conversation)

    mock_gemini.run.assert_called_once()
    assert result.routed_from == "groq/llama-3.3-70b-versatile"
    assert result.model_used == "google/gemini-1.5-flash"
    assert result.content[0].text == "Complex answer"


@pytest.mark.unit
async def test_rate_limit_falls_back_to_gemini(conversation: Conversation) -> None:
    import groq as groq_sdk  # noqa: PLC0415

    mock_groq = AsyncMock()
    mock_groq.model_id = "groq/llama-3.3-70b-versatile"
    mock_groq.run.side_effect = groq_sdk.RateLimitError(
        message="Rate limit exceeded",
        response=MagicMock(status_code=429, headers={}),
        body=None,
    )
    mock_gemini = AsyncMock()
    mock_gemini.run.return_value = _gemini_response()

    from app.adapters.agent.routing_agno_agent import RoutingAgnoAgent  # noqa: PLC0415

    router = RoutingAgnoAgent(mock_groq, mock_gemini)
    result = await router.run("Hello", conversation)

    mock_gemini.run.assert_called_once()
    assert result.routed_from == "groq/llama-3.3-70b-versatile"


@pytest.mark.unit
async def test_model_override_gemini_skips_groq(conversation: Conversation) -> None:
    mock_groq = AsyncMock()
    mock_groq.model_id = "groq/llama-3.3-70b-versatile"
    mock_gemini = AsyncMock()
    mock_gemini.run.return_value = _gemini_response()

    from app.adapters.agent.routing_agno_agent import RoutingAgnoAgent  # noqa: PLC0415

    router = RoutingAgnoAgent(mock_groq, mock_gemini)
    result = await router.run("Hello", conversation, model_override="gemini")

    mock_groq.run.assert_not_called()
    assert result.model_used == "google/gemini-1.5-flash"


@pytest.mark.unit
async def test_model_override_groq_skips_routing(conversation: Conversation) -> None:
    mock_groq = AsyncMock()
    mock_groq.run.return_value = _simple_response("groq/llama-3.3-70b-versatile")
    mock_groq.model_id = "groq/llama-3.3-70b-versatile"
    mock_gemini = AsyncMock()

    from app.adapters.agent.routing_agno_agent import RoutingAgnoAgent  # noqa: PLC0415

    router = RoutingAgnoAgent(mock_groq, mock_gemini)
    result = await router.run("Hello", conversation, model_override="groq")

    mock_gemini.run.assert_not_called()
    assert result.model_used == "groq/llama-3.3-70b-versatile"


@pytest.mark.unit
async def test_routing_agent_implements_port(conversation: Conversation) -> None:
    mock_groq = AsyncMock()
    mock_groq.model_id = "groq/llama-3.3-70b-versatile"
    mock_gemini = AsyncMock()

    from app.adapters.agent.routing_agno_agent import RoutingAgnoAgent  # noqa: PLC0415

    router = RoutingAgnoAgent(mock_groq, mock_gemini)
    assert isinstance(router, AgentPort)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/adapters/agent/test_routing_agno_agent.py -v
```

Expected: `ModuleNotFoundError` — routing_agno_agent not defined.

- [ ] **Step 3: Create `app/adapters/agent/routing_agno_agent.py`**

```python
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import groq as groq_sdk

from app.domain.entities import AgentResponse
from app.ports.agent import AgentPort

if TYPE_CHECKING:
    from app.adapters.agent.gemini_agno_agent import GeminiAgnoAgent
    from app.adapters.agent.groq_agno_agent import GroqAgnoAgent
    from app.domain.entities import Conversation


class RoutingAgnoAgent(AgentPort):
    def __init__(self, groq_agent: GroqAgnoAgent, gemini_agent: GeminiAgnoAgent) -> None:
        self._groq = groq_agent
        self._gemini = gemini_agent

    async def run(
        self,
        message: str,
        conversation: Conversation,
        model_override: str | None = None,
    ) -> AgentResponse:
        if model_override == "gemini":
            return await self._gemini.run(message, conversation)
        if model_override == "groq":
            return await self._groq.run(message, conversation)

        # Tool-tag routing (spec priority 3): when tools are added with
        # metadata={"model": "gemini"}, inspect them here and route to Gemini.

        try:
            response = await self._groq.run(message, conversation)
        except groq_sdk.RateLimitError:
            result = await self._gemini.run(message, conversation)
            return replace(result, routed_from=self._groq.model_id)

        if response.complexity == "complex" and not response.content:
            result = await self._gemini.run(message, conversation)
            return replace(result, routed_from=self._groq.model_id)

        return response
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/adapters/agent/test_routing_agno_agent.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/adapters/agent/routing_agno_agent.py tests/unit/adapters/agent/test_routing_agno_agent.py
git commit -m "feat(adapters): add RoutingAgnoAgent with complexity routing and rate-limit fallback"
```

---

### Task 10: Update API layer (schemas, router, deps)

**Files:**
- Modify: `app/api/schemas.py`
- Modify: `app/api/router.py`
- Modify: `app/api/deps.py`

- [ ] **Step 1: Update `app/api/schemas.py`**

```python
from __future__ import annotations

from pydantic import BaseModel


class IncomingMessageSchema(BaseModel):
    sender: str
    content: str
    channel: str
    conversation_id: str | None = None
    model_override: str | None = None


class OutgoingMessageSchema(BaseModel):
    content: str
    channel: str
    recipient: str
    model_used: str = ""
    routed_from: str | None = None
```

- [ ] **Step 2: Update `app/api/router.py`**

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import APIRouter, Depends

from app.api.deps import get_agent, get_logger, get_repo
from app.api.schemas import IncomingMessageSchema, OutgoingMessageSchema
from app.application.use_cases.process_incoming_message import ProcessIncomingMessage
from app.domain.entities import IncomingMessage

if TYPE_CHECKING:
    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort

router = APIRouter()


@router.post("/messages", response_model=OutgoingMessageSchema)
async def receive_message(
    body: IncomingMessageSchema,
    agent: AgentPort = Depends(get_agent),
    repo: RepositoryPort = Depends(get_repo),
    log: LoggerPort = Depends(get_logger),
) -> OutgoingMessageSchema:
    use_case = ProcessIncomingMessage(agent=agent, repo=repo, log=log)
    incoming = IncomingMessage(
        id=str(uuid4()),
        sender=body.sender,
        content=body.content,
        channel=body.channel,
        timestamp=datetime.now(tz=UTC),
        conversation_id=body.conversation_id,
        model_override=body.model_override,
    )
    outgoing = await use_case.execute(incoming)
    return OutgoingMessageSchema(
        content=outgoing.content,
        channel=outgoing.channel,
        recipient=outgoing.recipient,
        model_used=outgoing.model_used,
        routed_from=outgoing.routed_from,
    )
```

- [ ] **Step 3: Update `app/api/deps.py`**

```python
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import create_async_engine

from app.adapters.agent.gemini_agno_agent import GeminiAgnoAgent
from app.adapters.agent.groq_agno_agent import GroqAgnoAgent
from app.adapters.agent.routing_agno_agent import RoutingAgnoAgent
from app.adapters.logging.structlog_logger import StructlogLogger
from app.adapters.repository.postgres_repository import PostgresRepository
from app.config import Settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.ports.agent import AgentPort
    from app.ports.logger import LoggerPort
    from app.ports.repository import RepositoryPort


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_logger() -> LoggerPort:
    return StructlogLogger()


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(get_settings().database_url)


@lru_cache
def get_repo() -> RepositoryPort:
    return PostgresRepository(get_engine())


@lru_cache
def get_agent() -> AgentPort:
    settings = get_settings()
    return RoutingAgnoAgent(
        groq_agent=GroqAgnoAgent(settings),
        gemini_agent=GeminiAgnoAgent(settings),
    )
```

- [ ] **Step 4: Run unit tests to verify no regressions**

```
pytest tests/unit/ -v
```

Expected: all unit tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/api/schemas.py app/api/router.py app/api/deps.py
git commit -m "feat(api): wire RoutingAgnoAgent, add model_override to request, model_used/routed_from to response"
```

---

### Task 11: Delete old AgnoAgent (Claude/Anthropic) and its tests

**Files:**
- Delete: `app/adapters/agent/agno_agent.py`
- Delete: `tests/unit/adapters/agent/test_agno_agent.py`

- [ ] **Step 1: Verify nothing imports agno_agent.py**

```
grep -r "agno_agent" app/ tests/
```

Expected: zero matches (deps.py was already updated in Task 10).

- [ ] **Step 2: Delete the files**

```bash
git rm app/adapters/agent/agno_agent.py
git rm tests/unit/adapters/agent/test_agno_agent.py
```

- [ ] **Step 3: Run full test suite to verify clean state**

```
pytest tests/unit/ -v
```

Expected: all tests pass, no references to deleted files.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(adapters): remove AgnoAgent (Claude/Anthropic) — replaced by GroqAgnoAgent + GeminiAgnoAgent"
```

---

### Task 12: Run quality gates

**Files:** none (verification only)

- [ ] **Step 1: Lint**

```
ruff check . && ruff format --check .
```

Expected: no errors. Fix any import-order or style issues before proceeding.

- [ ] **Step 2: Type check**

```
pyright
```

Expected: no errors. Common issues to watch:
- `response.content` in GroqAgnoAgent/GeminiAgnoAgent typed as `Any` from Agno — add `# type: ignore[assignment]` with comment if needed
- `ContentBlock` TypeAlias used in isinstance checks — use `(TextBlock, ImageBlock, AudioBlock)` tuple form

- [ ] **Step 3: Full test suite with coverage**

```
pytest
```

Expected: all tests pass, coverage ≥ 80% on domain + application layers.

- [ ] **Step 4: Final commit if any lint/type fixes were needed**

```bash
git add -u
git commit -m "chore: fix lint and type issues after dual-model routing implementation"
```
