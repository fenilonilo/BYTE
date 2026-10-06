from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from google.genai import errors, types

from app.domain.exceptions import AgentError
from app.domain.model import ModelTurn
from app.domain.tools import ToolCall
from app.ports.chat_model import ChatModelPort

if TYPE_CHECKING:
    from collections.abc import Sequence

    from google import genai

    from app.domain.model import ModelMessage
    from app.domain.tools import ToolSpec


# Gemini 3 rejects a function call without its thought signature; Google documents this value
# as the way to send one that was never produced by the model (history from another provider).
SKIP_SIGNATURE_VALIDATION = b"skip_thought_signature_validator"


def to_gemini_contents(messages: Sequence[ModelMessage]) -> list[types.Content]:
    """Transcript -> Gemini contents. System messages go to `system_instruction` instead."""
    names: dict[str, str] = {}
    contents: list[types.Content] = []
    for m in messages:
        if m.role == "system":
            continue
        if m.role == "tool":
            part = types.Part.from_function_response(
                name=names.get(m.tool_call_id or "", ""), response={"output": m.content}
            )
            if contents and contents[-1].role == "user" and _only_responses(contents[-1]):
                contents[-1].parts = [*(contents[-1].parts or []), part]  # one turn per batch
            else:
                contents.append(types.Content(role="user", parts=[part]))
        elif m.role == "assistant":
            parts = [types.Part.from_text(text=m.content)] if m.content else []
            for c in m.tool_calls:
                names[c.id] = c.name
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(name=c.name, args=json.loads(c.arguments)),
                        thought_signature=c.signature or SKIP_SIGNATURE_VALIDATION,
                    )
                )
            contents.append(types.Content(role="model", parts=parts))
        else:
            contents.append(
                types.Content(role="user", parts=[types.Part.from_text(text=m.content)])
            )
    return contents


def _only_responses(content: types.Content) -> bool:
    return all(p.function_response is not None for p in content.parts or ())


def to_gemini_tools(tools: Sequence[ToolSpec]) -> list[types.Tool]:
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters_json_schema=dict(t.parameters),
                )
                for t in tools
            ]
        )
    ]


class GeminiChatModel(ChatModelPort):
    """generateContent with function tools. The google-genai SDK never leaves this package."""

    def __init__(self, client: genai.Client, model: str) -> None:
        self._client = client
        self._model = model

    async def complete(
        self, messages: Sequence[ModelMessage], tools: Sequence[ToolSpec]
    ) -> ModelTurn:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            tools=to_gemini_tools(tools) if tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            response = await self._client.aio.models.generate_content(
                model=self._model,
                contents=cast("types.ContentListUnion", to_gemini_contents(messages)),
                config=config,
            )
        except errors.APIError as exc:
            raise AgentError(f"model call failed: {type(exc).__name__} status={exc.code}") from exc
        if not response.candidates:
            raise AgentError("model returned no candidates")
        parts = response.candidates[0].content.parts if response.candidates[0].content else None
        text = "".join(p.text for p in parts or () if p.text and not p.thought)
        calls = tuple(
            ToolCall(
                id=call.id or f"call-{i}",
                name=call.name or "",
                arguments=json.dumps(call.args or {}),
                signature=part.thought_signature or b"",
            )
            for i, (part, call) in enumerate(
                (p, p.function_call) for p in parts or () if p.function_call
            )
        )
        return ModelTurn(text=text, tool_calls=calls)
