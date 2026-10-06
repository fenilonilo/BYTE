from __future__ import annotations

import asyncio
import json
from functools import partial
from typing import TYPE_CHECKING, cast
from uuid import uuid4

from app.application.tools.args import object_schema
from app.domain.exceptions import DomainError, RegistryKeyError, ToolArgumentError
from app.domain.tools import ToolResult, ToolSpec

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.application.pending_actions import PendingActionStore
    from app.application.registry import Registry
    from app.application.tool import Tool
    from app.domain.tools import ToolCall
    from app.ports.logger import LoggerPort

CONFIRM_ACTION = "confirm_action"
CONFIRM_SPEC = ToolSpec(
    name=CONFIRM_ACTION,
    description=(
        "Executa a ação pendente depois que o usuário a confirmou na fala seguinte. "
        "Não recebe argumentos. Só chame depois de ler o resumo ao usuário e ouvir a resposta."
    ),
    parameters=object_schema({}),
    segment="*",
)
UNKNOWN_STATE = "estado desconhecido: verifique o dispositivo antes de tentar de novo"


def _parse(arguments: str) -> Mapping[str, object]:
    try:
        parsed: object = json.loads(arguments or "{}")
    except json.JSONDecodeError as exc:
        raise ToolArgumentError("argumentos não são JSON válido") from exc
    if not isinstance(parsed, dict):
        raise ToolArgumentError("argumentos devem ser um objeto JSON")
    return cast("dict[str, object]", parsed)  # JSON object keys are always str


class ToolRunner:
    """Runs tool calls: allowlist, confirmation gate, timeout, shielded execution."""

    def __init__(
        self,
        tools: Registry[Tool],
        pending: PendingActionStore,
        log: LoggerPort,
        *,
        tool_timeout: float = 10.0,
        max_output_chars: int = 2000,
    ) -> None:
        self._tools = tools
        self._pending = pending
        self._log = log
        self._timeout = tool_timeout
        self._max_chars = max_output_chars
        self._tasks: set[asyncio.Task[str]] = set()

    def segments(self) -> frozenset[str]:
        return frozenset(t.spec.segment for t in self._tools.values())

    def specs(self, segment: str | None) -> tuple[ToolSpec, ...]:
        chosen = tuple(
            t.spec for t in self._tools.values() if segment is None or t.spec.segment == segment
        )
        return (*chosen, CONFIRM_SPEC)

    async def run(self, call: ToolCall, conversation_id: str, segment: str | None) -> ToolResult:
        output = await self._dispatch(call, conversation_id, segment)
        return ToolResult(call_id=call.id, output=output[: self._max_chars])

    async def drain(self) -> None:
        """Wait for tool tasks still running (called on shutdown)."""
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _dispatch(self, call: ToolCall, conversation_id: str, segment: str | None) -> str:
        if call.name == CONFIRM_ACTION:
            return await self._confirm(conversation_id)
        try:
            tool = self._tools.get(call.name)
        except RegistryKeyError:
            return "erro: ferramenta desconhecida"
        if segment is not None and tool.spec.segment != segment:
            return "erro: ferramenta fora do segmento"
        try:
            args = _parse(call.arguments)
            if not tool.needs_confirmation(args):
                return await self._execute(tool, args, key=call.id)
            summary = tool.summarize(args)
        except DomainError as exc:
            return f"erro: {exc}"
        self._pending.create(conversation_id, call.name, call.arguments, summary, uuid4().hex)
        return (
            "needs_confirmation: leia ao usuário, palavra por palavra, e aguarde a resposta: "
            f'"{summary}". Se ele confirmar na fala seguinte, chame {CONFIRM_ACTION}.'
        )

    async def _confirm(self, conversation_id: str) -> str:
        action, reason = self._pending.confirm(conversation_id)
        if action is None:
            return f"erro: {reason}"
        try:
            tool = self._tools.get(action.tool)
            args = _parse(action.arguments)
        except DomainError as exc:
            return f"erro: {exc}"
        return await self._execute(tool, args, key=action.key)

    async def _execute(self, tool: Tool, args: Mapping[str, object], key: str) -> str:
        task = asyncio.create_task(tool.execute(args, key))
        self._tasks.add(task)
        task.add_done_callback(partial(self._finished, tool.spec.name))
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=self._timeout)
        except TimeoutError:
            return UNKNOWN_STATE
        except DomainError as exc:
            return f"erro: {exc}"
        except Exception:
            return "erro: falha interna na ferramenta"

    def _finished(self, name: str, task: asyncio.Task[str]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            self._log.warning("tool.cancelled", tool=name)
        elif (exc := task.exception()) is not None:
            self._log.error("tool.failed", tool=name, error=type(exc).__name__)
        else:
            self._log.info("tool.done", tool=name)
