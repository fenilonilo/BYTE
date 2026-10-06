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
