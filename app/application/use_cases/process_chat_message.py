from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from app.application.prompts import SYSTEM_PROMPT, now_line, projects_line
from app.domain.entities import Message
from app.domain.exceptions import AgentError
from app.domain.model import ModelMessage

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

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
        clock: Callable[[], datetime],
        max_steps: int = 6,
        history_limit: int = 20,
        timeout_seconds: float = 30.0,
        projects: Sequence[str] = (),
    ) -> None:
        self._model = model
        self._store = store
        self._runner = runner
        self._pending = pending
        self._log = log
        self._clock = clock
        self._max_steps = max_steps
        self._history_limit = history_limit
        self._timeout = timeout_seconds
        self._projects_line = projects_line(projects)

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
        base = " ".join(
            p for p in (SYSTEM_PROMPT, now_line(self._clock()), self._projects_line) if p
        )
        action = self._pending.peek(conversation_id)
        if action is None or not action.armed:
            return base
        return (
            f"{base} Há uma ação pendente de confirmação: {action.summary}. "
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
