from __future__ import annotations

import os

import pytest
from google import genai

from app.adapters.gemini.chat_model import GeminiChatModel
from app.domain.model import ModelMessage
from app.domain.tools import ToolSpec

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(
        not os.environ.get("BYTE_GEMINI_API_KEY"), reason="needs BYTE_GEMINI_API_KEY"
    ),
]

MODEL = os.environ.get("BYTE_GEMINI_CHAT_MODEL", "gemini-3.1-flash-lite")
LIST_LIGHTS = ToolSpec(
    name="list_lights",
    description="Lista as lâmpadas e se estão ligadas.",
    parameters={"type": "object", "properties": {}},
    segment="home",
)


async def test_a_tool_call_round_trip_ends_in_text() -> None:
    model = GeminiChatModel(genai.Client(api_key=os.environ["BYTE_GEMINI_API_KEY"]), MODEL)
    messages = [
        ModelMessage(role="system", content="Responda em português, curto."),
        ModelMessage(role="user", content="Quais lâmpadas existem? Use a ferramenta."),
    ]
    first = await model.complete(messages, [LIST_LIGHTS])
    assert [c.name for c in first.tool_calls] == ["list_lights"]
    messages += [
        ModelMessage(role="assistant", content=first.text, tool_calls=first.tool_calls),
        ModelMessage(role="tool", content="lampada: ligada", tool_call_id=first.tool_calls[0].id),
    ]
    second = await model.complete(messages, [LIST_LIGHTS])
    assert second.text
    assert not second.tool_calls
