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
    assert isinstance(result.content[0], TextBlock)
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
