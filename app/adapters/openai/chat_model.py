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
