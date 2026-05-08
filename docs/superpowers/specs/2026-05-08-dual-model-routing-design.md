# Dual-Model Routing Design
Date: 2026-05-08
Branch: feat/cycle2-agno-postgres-memory

## Overview

Replace single `AgnoAgent` (Claude/Anthropic) with a router-based dual-model system:
- **Groq Llama 3.3 70B** — default model, classifies complexity
- **Google Gemini 1.5 Flash** — handles complex tasks and rate-limit fallbacks

## 1. Domain Entities

### Content Blocks (`app/domain/entities.py`)

New multimodal content block types added to domain:

```python
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

ContentBlock = TextBlock | ImageBlock | AudioBlock
```

### AgentResponse (`app/domain/entities.py`)

Replaces raw `str` return from agents:

```python
@dataclass(frozen=True, slots=True)
class AgentResponse:
    content: tuple[ContentBlock, ...]        # empty = handoff signal
    model_used: str                          # e.g. "groq/llama-3.3-70b-versatile"
    complexity: Literal["simple", "complex"]
    tools_called: tuple[str, ...]
    routed_from: str | None                  # set when Gemini received a handoff
```

## 2. Port Contract

`AgentPort.run()` updated signature:

```python
async def run(
    self,
    message: str,
    conversation: Conversation,
    model_override: str | None = None,
) -> AgentResponse: ...
```

`model_override` accepted values: `"groq"`, `"gemini"`. `None` = default routing logic.

## 3. Adapter Architecture

### Files

```
app/adapters/agent/
├── __init__.py
├── stub_agent.py                 # updated to return AgentResponse
├── groq_agno_agent.py            # GroqAgnoAgent — Llama 3.3 70B
├── gemini_agno_agent.py          # GeminiAgnoAgent — Gemini 1.5 Flash
├── routing_agno_agent.py         # RoutingAgnoAgent — implements AgentPort
└── schemas.py                    # Pydantic output schemas for Agno
```

`agno_agent.py` (old Claude adapter) is removed.

### GroqAgnoAgent

- Model: `agno.models.groq.Groq(id="llama-3.3-70b-versatile")`
- `output_schema=GroqOutputSchema`
- System prompt instructs: classify complexity first; if complex, return `content=[]`; if simple, answer fully
- Returns `AgentResponse`; `content=()` signals handoff

### GeminiAgnoAgent

- Model: `agno.models.google.Gemini(id="gemini-1.5-flash")`
- `output_schema=GeminiOutputSchema`
- Always answers; never classifies
- Returns `AgentResponse` with `routed_from` set by caller (router)

### RoutingAgnoAgent

Implements `AgentPort`. Routing priority:

```
1. model_override == "gemini"            →  send to Gemini directly
2. model_override == "groq"              →  send to Groq directly
3. tool tag requires model="gemini"      →  send to Gemini directly
4. default: send to Groq
   a. response.complexity == "complex" (content empty)  →  re-send to Gemini
   b. Groq raises RateLimitError (HTTP 429)             →  fallback to Gemini
   c. Groq responds normally                            →  return as-is
```

Tool tags are metadata on Agno `@tool` decorated functions:

```python
@tool(metadata={"model": "gemini"})
def analyze_image(url: str) -> str: ...
```

Router inspects `conversation` or message context for which tools are relevant; if any required tool has `metadata["model"] == "gemini"`, skips Groq entirely.

When routing to Gemini after Groq, sets `routed_from="groq/llama-3.3-70b-versatile"` on the final `AgentResponse`.

## 4. Pydantic Output Schemas (`app/adapters/agent/schemas.py`)

Pydantic models used as `output_schema` in Agno agents. Domain-free — adapters only.

```python
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
    Field(discriminator="type")
]

class GroqOutputSchema(BaseModel):
    complexity: Literal["simple", "complex"]
    content: list[ContentBlockSchema] = []   # empty list = handoff
    tools_called: list[str] = []

class GeminiOutputSchema(BaseModel):
    content: list[ContentBlockSchema]
    tools_called: list[str] = []
```

Adapters map `list[ContentBlockSchema]` → `tuple[ContentBlock, ...]` converting each Pydantic model to its domain dataclass equivalent.

## 5. Config (`app/config.py`)

```python
# API keys
groq_api_key: str = ""
google_api_key: str = ""

# Model IDs (overridable via env)
groq_model_id: str = "llama-3.3-70b-versatile"
gemini_model_id: str = "gemini-1.5-flash"
```

Env vars: `MARCELO_GROQ_API_KEY`, `MARCELO_GOOGLE_API_KEY`, `MARCELO_GROQ_MODEL_ID`, `MARCELO_GEMINI_MODEL_ID`.

## 6. Dependencies (`pyproject.toml`)

```toml
agent = [
    "agno>=1.5",
    "groq>=0.11",
    "google-generativeai>=0.8",
]
```

`anthropic` removed — no longer used.

## 7. Downstream Contract Changes

### `ProcessIncomingMessage`

Extracts text from `AgentResponse` for text channels:

```python
response: AgentResponse = await self._agent.run(message, conversation)
text = next(
    (block.text for block in response.content if isinstance(block, TextBlock)),
    "",
)
```

### `StubAgent`

Updated to return `AgentResponse(content=(TextBlock(text=message),), complexity="simple", ...)`.

### API response schema

`MessageResponseSchema` updated to include `model_used` and `routed_from` fields from `AgentResponse`.

## 8. Testing

| File | Cases |
|------|-------|
| `test_groq_agno_agent.py` | returns simple response; returns empty content when complex; maps blocks correctly |
| `test_gemini_agno_agent.py` | returns full response; maps blocks correctly; implements AgentPort |
| `test_routing_agno_agent.py` | Groq simple → direct return; Groq complex → routes to Gemini; Groq 429 → fallback Gemini; model_override="gemini" → skips Groq; model_override="groq" → skips routing |
| `test_stub_agent.py` | updated for AgentResponse return type |
| `test_process_message.py` | updated mock returns AgentResponse |

## 9. Files Changed / Created / Deleted

| Action | File |
|--------|------|
| Modified | `app/domain/entities.py` |
| Modified | `app/ports/agent.py` |
| Modified | `app/config.py` |
| Modified | `app/adapters/agent/stub_agent.py` |
| Modified | `app/api/deps.py` |
| Modified | `app/api/router.py` |
| Modified | `app/application/use_cases/process_incoming_message.py` |
| Modified | `pyproject.toml` |
| Created | `app/adapters/agent/schemas.py` |
| Created | `app/adapters/agent/groq_agno_agent.py` |
| Created | `app/adapters/agent/gemini_agno_agent.py` |
| Created | `app/adapters/agent/routing_agno_agent.py` |
| Created | `tests/unit/adapters/agent/test_groq_agno_agent.py` |
| Created | `tests/unit/adapters/agent/test_gemini_agno_agent.py` |
| Created | `tests/unit/adapters/agent/test_routing_agno_agent.py` |
| Deleted | `app/adapters/agent/agno_agent.py` |
| Deleted | `tests/unit/adapters/agent/test_agno_agent.py` |
