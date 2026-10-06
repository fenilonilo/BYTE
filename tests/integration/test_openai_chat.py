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
