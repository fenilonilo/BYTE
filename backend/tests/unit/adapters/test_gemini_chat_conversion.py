from __future__ import annotations

import pytest

from app.adapters.gemini.chat_model import (
    SKIP_SIGNATURE_VALIDATION,
    to_gemini_contents,
    to_gemini_tools,
)
from app.domain.model import ModelMessage
from app.domain.tools import ToolCall, ToolSpec


@pytest.mark.unit
def test_system_goes_elsewhere_and_a_tool_batch_is_one_user_turn() -> None:
    calls = (
        ToolCall(id="a", name="list_lights", arguments="{}", signature=b"sig"),
        ToolCall(id="b", name="get_climate", arguments='{"x": 1}'),
    )
    contents = to_gemini_contents(
        [
            ModelMessage(role="system", content="sys"),
            ModelMessage(role="user", content="oi"),
            ModelMessage(role="assistant", content="", tool_calls=calls),
            ModelMessage(role="tool", content="luz: ligada", tool_call_id="a"),
            ModelMessage(role="tool", content="25 graus", tool_call_id="b"),
            ModelMessage(role="assistant", content="pronto"),
        ]
    )
    assert [c.role for c in contents] == ["user", "model", "user", "model"]
    model_parts = contents[1].parts or []
    assert [p.thought_signature for p in model_parts] == [b"sig", SKIP_SIGNATURE_VALIDATION]
    responses = [p.function_response for p in contents[2].parts or []]
    assert [(r.name, r.response) for r in responses if r] == [
        ("list_lights", {"output": "luz: ligada"}),
        ("get_climate", {"output": "25 graus"}),
    ]


@pytest.mark.unit
def test_tools_become_one_declaration_list_plus_web_search() -> None:
    spec = ToolSpec(
        name="set_light",
        description="Liga.",
        parameters={"type": "object", "properties": {}},
        segment="home",
    )
    tool, search = to_gemini_tools([spec])
    (declaration,) = tool.function_declarations or []
    assert (declaration.name, declaration.parameters_json_schema) == (
        "set_light",
        {"type": "object", "properties": {}},
    )
    assert search.google_search is not None


@pytest.mark.unit
def test_web_search_stays_when_a_segment_has_no_tools() -> None:
    (search,) = to_gemini_tools([])
    assert search.google_search is not None
